from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from django.conf import settings
from django.utils import timezone
from django.db import transaction
from django.db.models import Count, Max, Sum, Q
from decimal import Decimal
from datetime import timedelta
from users.models import User
from game.models import (
    Game,
    BingoCard,
    StakeLobbyLock,
    SystemBalanceLedger,
    LiveEvent,
    MissionTemplate,
    PromoCode,
    PromoCodeRedemption,
    PromoVerificationRequest,
    Season,
    UserMissionProgress,
)
from game.business_rules import get_business_rules, get_countdown_seconds, get_derash_multiplier, get_system_multiplier
from game.engagement import claim_mission, credit_user_reward, increment_missions, touch_user_streak, RewardSafetyError
from wallet.models import Wallet, Transaction
from game.security import (
    create_user_access_token,
    get_request_access_token,
    rate_limit,
    require_path_telegram_auth,
    require_valid_web_token,
    verify_user_access_token,
)
from bot.utils.url_helpers import build_react_url, can_use_telegram_button_url
import json
import logging
from urllib import error as urllib_error
from urllib import request as urllib_request


BOT_TELEGRAM_ID_THRESHOLD = 9000000000
MIN_REAL_USERS_TO_START = 2
logger = logging.getLogger(__name__)


def _calculate_derash(total_players, stake_amount):
    return Decimal(total_players) * Decimal(stake_amount) * get_derash_multiplier()


def _calculate_system_share(total_players, stake_amount):
    return Decimal(total_players) * Decimal(stake_amount) * get_system_multiplier()


def _serialize_promo_claim(claim):
    return {
        'id': claim.id,
        'promo_code': claim.promo_code.code,
        'submitted_at': claim.submitted_at.isoformat(),
        'status': claim.status,
        'admin_reviewer': claim.admin_reviewer.first_name if claim.admin_reviewer else None,
        'review_reason': claim.review_reason,
        'decision_time': claim.decision_time.isoformat() if claim.decision_time else None,
        'credited_amount': float(claim.credited_amount),
    }


def _notify_admins_hidden_promo_claim(claim):
    bot_token = (getattr(settings, 'BOT_TOKEN', '') or '').strip()
    admin_ids = [int(admin_id) for admin_id in getattr(settings, 'ADMIN_IDS', [])]
    if not bot_token or not admin_ids:
        return

    text = (
        'New hidden promo verification request\n\n'
        f'Request: #{claim.id}\n'
        f'User: {claim.user.first_name} (@{claim.user.username or claim.user.telegram_id})\n'
        f'Promo: {claim.promo_code.code}\n'
        f'Submitted: {claim.submitted_at:%Y-%m-%d %H:%M:%S} UTC\n\n'
        'Use the buttons below to approve or reject.'
    )
    reply_markup = {
        'inline_keyboard': [[
            {'text': 'Approve', 'callback_data': f'promo_verify:approve:{claim.id}'},
            {'text': 'Reject', 'callback_data': f'promo_verify:reject:{claim.id}'},
        ]]
    }

    for admin_id in admin_ids:
        payload = json.dumps({
            'chat_id': admin_id,
            'text': text,
            'reply_markup': reply_markup,
        }).encode('utf-8')
        req = urllib_request.Request(
            url=f'https://api.telegram.org/bot{bot_token}/sendMessage',
            data=payload,
            headers={'Content-Type': 'application/json'},
            method='POST',
        )
        try:
            urllib_request.urlopen(req, timeout=5)
        except (urllib_error.URLError, urllib_error.HTTPError, TimeoutError):
            continue


def _send_telegram_text_message(chat_id, text, reply_markup=None):
    bot_token = (getattr(settings, 'BOT_TOKEN', '') or '').strip()
    if not bot_token or not chat_id or not text:
        return False

    payload_data = {
        'chat_id': int(chat_id),
        'text': text,
    }
    if reply_markup:
        payload_data['reply_markup'] = reply_markup

    payload = json.dumps(payload_data).encode('utf-8')
    req = urllib_request.Request(
        url=f'https://api.telegram.org/bot{bot_token}/sendMessage',
        data=payload,
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    try:
        urllib_request.urlopen(req, timeout=5)
        return True
    except (urllib_error.URLError, urllib_error.HTTPError, TimeoutError, ValueError):
        return False


def touch_site_presence(telegram_id):
    if not telegram_id:
        return
    now = timezone.now()
    touch_interval_seconds = int(getattr(settings, 'WEB_PRESENCE_TOUCH_INTERVAL_SECONDS', 15) or 15)
    refresh_cutoff = now - timedelta(seconds=max(1, touch_interval_seconds))
    User.objects.filter(telegram_id=telegram_id).filter(
        Q(last_site_seen_at__isnull=True) | Q(last_site_seen_at__lt=refresh_cutoff)
    ).update(last_site_seen_at=now)


def is_user_online_on_site(user):
    last_seen = getattr(user, 'last_site_seen_at', None)
    if not last_seen:
        return False
    timeout_seconds = int(getattr(settings, 'WEB_ONLINE_TIMEOUT_SECONDS', 45) or 45)
    return (timezone.now() - last_seen).total_seconds() <= max(5, timeout_seconds)


def notify_lonely_waiting_players(game, joined_user, delay_minutes):
    recipients = list(
        User.objects.filter(
            id__in=game.cards.exclude(user_id=joined_user.id).values_list('user_id', flat=True),
            telegram_id__lt=BOT_TELEGRAM_ID_THRESHOLD,
        ).only('telegram_id', 'last_site_seen_at')
    )
    recipient_ids = [recipient.telegram_id for recipient in recipients if not is_user_online_on_site(recipient)]
    if not recipient_ids:
        return

    countdown_seconds = int(get_countdown_seconds())
    total_wait_seconds = (max(0, int(delay_minutes)) * 60) + countdown_seconds
    joined_name = joined_user.first_name or 'A player'
    stake_amount = get_game_stake(game)
    message = (
        f"Good news! {joined_name} joined your waiting game (#{game.id}, {stake_amount} Birr tier).\n"
        f"Please rejoin now. The game can start in about {total_wait_seconds} seconds."
    )

    def _send_notification(chat_id):
        access_token = create_user_access_token(chat_id)
        play_url = build_react_url('/', telegram_id=chat_id, token=access_token)
        reply_markup = None
        if can_use_telegram_button_url(play_url):
            reply_markup = {
                'inline_keyboard': [[
                    {'text': '▶️ Play Now', 'url': play_url},
                ]]
            }
        _send_telegram_text_message(chat_id, message, reply_markup=reply_markup)

    transaction.on_commit(
        lambda: [
            _send_notification(chat_id)
            for chat_id in recipient_ids
        ]
    )


def _serialize_mission_progress(progress):
    mission = progress.mission
    return {
        'progress_id': progress.id,
        'mission_key': mission.key,
        'title': mission.title,
        'description': mission.description,
        'mission_type': mission.mission_type,
        'period': mission.period,
        'target_value': mission.target_value,
        'progress_value': progress.progress_value,
        'is_completed': progress.progress_value >= mission.target_value,
        'is_claimed': bool(progress.claimed_at),
        'reward_amount': float(progress.reward_amount),
        'reward_balance': mission.reward_balance,
        'period_start': progress.period_start.isoformat(),
        'period_end': progress.period_end.isoformat(),
    }


def get_supported_stakes():
    tiers = list(getattr(settings, 'GAME_STAKE_TIERS', [10, 20, 50, 100]))
    normalized = sorted({int(value) for value in tiers if int(value) > 0})
    return normalized or [10, 20, 50, 100]


def get_game_stake(game):
    return int(getattr(game, 'stake_amount', settings.CARD_PRICE))


def get_game_countdown(game):
    if game.state != 'waiting':
        return 0
    time_elapsed = (timezone.now() - game.created_at).total_seconds()
    return max(0, int(get_countdown_seconds() - time_elapsed))


def cleanup_bot_only_waiting_game(game):
    """Remove stale bot cards from waiting games until minimum real users threshold is met."""
    if game.state != 'waiting' or not game.has_bots:
        return game

    real_players = game.cards.filter(user__telegram_id__lt=BOT_TELEGRAM_ID_THRESHOLD).count()
    if real_players >= MIN_REAL_USERS_TO_START:
        return game

    bot_cards_qs = game.cards.filter(user__telegram_id__gte=BOT_TELEGRAM_ID_THRESHOLD)
    if not bot_cards_qs.exists():
        if game.has_bots or game.real_players_count or game.real_prize_amount:
            game.has_bots = False
            game.real_players_count = 0
            game.real_prize_amount = Decimal('0')
            game.save(update_fields=['has_bots', 'real_players_count', 'real_prize_amount'])
        return game

    bot_cards_qs.delete()
    game.has_bots = False
    game.real_players_count = 0
    game.real_prize_amount = Decimal('0')
    game.save(update_fields=['has_bots', 'real_players_count', 'real_prize_amount'])
    return game


def consolidate_waiting_games_for_stake(stake_amount):
    """Merge duplicate waiting games for a stake into one canonical waiting game."""
    waiting_games = list(
        Game.objects.select_for_update()
        .filter(stake_amount=stake_amount, state='waiting')
        .order_by('created_at', 'id')
    )
    if not waiting_games:
        return None
    if len(waiting_games) == 1:
        return waiting_games[0]

    game_sizes = [(game, game.cards.count()) for game in waiting_games]
    primary_game, _ = max(game_sizes, key=lambda entry: (entry[1], -entry[0].id))

    used_numbers = set(primary_game.cards.values_list('card_number', flat=True))
    users_in_primary = set(primary_game.cards.values_list('user_id', flat=True))

    for duplicate in waiting_games:
        if duplicate.id == primary_game.id:
            continue

        duplicate_cards = list(duplicate.cards.order_by('created_at', 'id'))
        for card in duplicate_cards:
            if card.user_id in users_in_primary:
                continue

            target_card_number = card.card_number
            if target_card_number in used_numbers:
                target_card_number = None
                for candidate in range(1, settings.CARD_COUNT + 1):
                    if candidate not in used_numbers:
                        target_card_number = candidate
                        break

                if target_card_number is None:
                    continue

            card.game = primary_game
            if card.card_number != target_card_number:
                card.card_number = target_card_number
                card.save(update_fields=['game', 'card_number'])
            else:
                card.save(update_fields=['game'])

            used_numbers.add(target_card_number)
            users_in_primary.add(card.user_id)

        if not duplicate.cards.exists():
            duplicate.delete()

    return primary_game


def get_or_create_lobby_game_for_stake(stake_amount):
    with transaction.atomic():
        lock_row, _ = StakeLobbyLock.objects.get_or_create(stake_amount=stake_amount)
        StakeLobbyLock.objects.select_for_update().get(pk=lock_row.pk)

        playing_game = (
            Game.objects.select_for_update()
            .filter(stake_amount=stake_amount, state='playing')
            .order_by('-created_at')
            .first()
        )
        if playing_game:
            return ensure_game_started(playing_game.id)

        waiting_game = consolidate_waiting_games_for_stake(stake_amount)
        if waiting_game:
            waiting_game = cleanup_bot_only_waiting_game(waiting_game)
            waiting_game = ensure_game_started(waiting_game.id)
            if waiting_game.state in ['waiting', 'playing']:
                return waiting_game

        return Game.objects.create(state='waiting', stake_amount=stake_amount)


def build_lobby_game_row(game, user):
    stake_amount = get_game_stake(game)
    total_players = game.cards.count()
    real_players = game.cards.filter(user__telegram_id__lt=BOT_TELEGRAM_ID_THRESHOLD).count()
    derash = _calculate_derash(real_players, stake_amount)
    countdown = get_game_countdown(game)
    user_card = game.cards.filter(user=user).first()
    user_has_card = bool(user_card)
    taken_cards = list(game.cards.values_list('card_number', flat=True))

    if game.state == 'playing':
        status_key = 'PLAYING'
        status_label = 'Active'
    else:
        status_key = 'WAITING'
        if total_players >= settings.GAME_MIN_PLAYERS and real_players >= MIN_REAL_USERS_TO_START and countdown > 0:
            status_label = str(countdown)
        else:
            status_label = 'Waiting for players'

    action = 'none'
    action_label = 'Watch' if game.state == 'playing' else 'Unavailable'
    if user_has_card:
        action = 'play'
        action_label = 'Play'
    elif game.state == 'playing':
        action = 'watch'
        action_label = 'Watch'
    elif game.state == 'waiting':
        action = 'join'
        action_label = 'Join Now'

    return {
        'game_id': game.id,
        'stake_amount': stake_amount,
        'medb': stake_amount,
        'derash': float(derash),
        'players': real_players,
        'status_key': status_key,
        'status_label': status_label,
        'state': game.state,
        'countdown': countdown,
        'user_has_card': user_has_card,
        'user_card_number': user_card.card_number if user_card else None,
        'taken_cards': taken_cards,
        'available_cards': settings.CARD_COUNT - len(taken_cards),
        'action': action,
        'action_label': action_label,
    }


def get_winner_card_payload(game):
    if not game.winner_id:
        return None
    winner_card = game.cards.filter(user=game.winner, is_winner=True).first()
    if not winner_card:
        winner_card = game.cards.filter(user=game.winner).first()
    if not winner_card:
        return None
    return {
        'card_number': winner_card.card_number,
        'grid': winner_card.get_grid(),
        'winner_name': game.winner.first_name,
        'winner_username': game.winner.username if game.winner.username else None,
    }


def ensure_game_started(game_id):
    """Atomically transition a waiting game to playing when countdown ends."""
    with transaction.atomic():
        game = Game.objects.select_for_update().get(id=game_id)
        called_numbers = game.get_called_numbers()

        total_players = game.cards.count()
        real_players = game.cards.filter(user__telegram_id__lt=BOT_TELEGRAM_ID_THRESHOLD).count()

        if (
            game.state == 'playing'
            and (
                total_players < settings.GAME_MIN_PLAYERS
                or real_players < MIN_REAL_USERS_TO_START
            )
        ):
            game.state = 'waiting'
            game.started_at = None
            game.save()
            return game

        if game.state == 'playing' and len(called_numbers) >= settings.BINGO_NUMBER_MAX:
            total_players = game.cards.count()
            if game.has_bots:
                settlement_players = game.real_players_count
            else:
                settlement_players = total_players

            settlement_pool = Decimal(settlement_players) * Decimal(get_game_stake(game))
            game.prize_amount = Decimal('0.00')
            game.system_revenue = settlement_pool
            game.state = 'finished'
            if not game.finished_at:
                game.finished_at = timezone.now()
            game.save()

            if settlement_pool > 0:
                SystemBalanceLedger.append_entry(
                    event_type='game_no_winner',
                    direction='credit',
                    amount=settlement_pool,
                    game=game,
                    description=f'Game #{game.id} finished with no winner; system keeps full pool.',
                    metadata={
                        'settlement_players': int(settlement_players),
                        'pool_amount': str(settlement_pool),
                    },
                    idempotency_key=f'game:{game.id}:no_winner',
                )
            return game

        if game.state != 'waiting':
            return game

        time_elapsed = (timezone.now() - game.created_at).total_seconds()
        if (
            time_elapsed >= get_countdown_seconds()
            and total_players >= settings.GAME_MIN_PLAYERS
            and real_players >= MIN_REAL_USERS_TO_START
        ):
            game.state = 'playing'
            game.started_at = timezone.now()
            game.save()
        return game


def game_lobby(request, telegram_id):
    """Game lobby - show card selection"""
    token = get_request_access_token(request)
    if not token:
        return render(request, 'game/error.html', {
            'error': 'Missing access token. Please open the game from Telegram.'
        })

    auth_tid = verify_user_access_token(token)
    if auth_tid is None or int(auth_tid) != int(telegram_id):
        return render(request, 'game/error.html', {
            'error': 'Invalid or expired access token. Please open the game from Telegram.'
        })

    try:
        user = User.objects.select_related('wallet').get(telegram_id=telegram_id)
    except User.DoesNotExist:
        return render(request, 'game/error.html', {
            'error': 'User not found. Please start the bot first.'
        })

    return redirect(f"{settings.REACT_APP_URL}/home/{telegram_id}?token={token}")


def game_play(request, telegram_id, game_id):
    """Game play screen - show user's bingo card"""
    token = get_request_access_token(request)
    if not token:
        return render(request, 'game/error.html', {
            'error': 'Missing access token. Please open the game from Telegram.'
        })

    auth_tid = verify_user_access_token(token)
    if auth_tid is None or int(auth_tid) != int(telegram_id):
        return render(request, 'game/error.html', {
            'error': 'Invalid or expired access token. Please open the game from Telegram.'
        })

    try:
        user = User.objects.get(telegram_id=telegram_id)
    except User.DoesNotExist:
        return render(request, 'game/error.html', {
            'error': 'User not found.'
        })

    return redirect(f"{settings.REACT_APP_URL}/play/{telegram_id}/{game_id}?token={token}")


@csrf_exempt
@require_POST
@rate_limit(key_prefix='select-card', max_requests=25, window_seconds=60)
@require_valid_web_token
def select_card_api(request):
    """API endpoint to select a card"""
    try:
        data = json.loads(request.body)
        telegram_id = int(data.get('telegram_id'))
        if telegram_id != int(request.auth_telegram_id):
            return JsonResponse({'error': 'Forbidden.'}, status=403)
        card_number = int(data.get('card_number'))
        stake_amount = data.get('stake_amount')
        supported_stakes = get_supported_stakes()
        if stake_amount is not None:
            stake_amount = int(stake_amount)
            if stake_amount not in supported_stakes:
                return JsonResponse({'error': 'Invalid game tier'}, status=400)
        
        if card_number < 1 or card_number > settings.CARD_COUNT:
            return JsonResponse({'error': 'Invalid card number'}, status=400)

        with transaction.atomic():
            user = User.objects.select_for_update().get(telegram_id=telegram_id)
            touch_site_presence(user.telegram_id)
            wallet, _ = Wallet.objects.select_for_update().get_or_create(user=user)
            business_rules = get_business_rules()

            user_cards_qs = BingoCard.objects.select_related('game').filter(user=user, game__state='waiting')
            if stake_amount is not None:
                user_cards_qs = user_cards_qs.filter(game__stake_amount=stake_amount)
            user_card = user_cards_qs.order_by('-game__created_at').first()

            if user_card:
                game = Game.objects.select_for_update().get(pk=user_card.game_id)
                previous_player_count = game.cards.count()
                previous_real_player_count = game.cards.filter(
                    user__telegram_id__lt=BOT_TELEGRAM_ID_THRESHOLD
                ).count()
            else:
                if stake_amount is None:
                    return JsonResponse({'error': 'Game tier is required for new join.'}, status=400)

                lock_row, _ = StakeLobbyLock.objects.get_or_create(stake_amount=stake_amount)
                StakeLobbyLock.objects.select_for_update().get(pk=lock_row.pk)

                game = consolidate_waiting_games_for_stake(stake_amount)
                if not game:
                    if Game.objects.filter(state='playing', stake_amount=stake_amount).exists():
                        return JsonResponse({'error': 'This game is currently active. Please wait for next round.'}, status=400)
                    game = Game.objects.create(state='waiting', stake_amount=stake_amount)
                previous_player_count = game.cards.count()
                previous_real_player_count = game.cards.filter(
                    user__telegram_id__lt=BOT_TELEGRAM_ID_THRESHOLD
                ).count()

            # Check if card is available for this user
            if game.cards.filter(card_number=card_number).exclude(user=user).exists():
                return JsonResponse({'error': 'Card already taken'}, status=400)

            if user_card:
                user_card.card_number = card_number
                user_card.save(update_fields=['card_number'])
                card = user_card
            else:
                # Check balance
                entry_fee = Decimal(str(get_game_stake(game)))
                if wallet.total_balance < entry_fee:
                    return JsonResponse({'error': 'Insufficient balance'}, status=400)

                # Deduct balance
                remaining = entry_fee

                main_to_use = min(wallet.main_balance, remaining)
                wallet.main_balance -= main_to_use
                remaining -= main_to_use

                if remaining > 0:
                    bonus_to_use = min(wallet.bonus_balance, remaining)
                    wallet.bonus_balance -= bonus_to_use
                    remaining -= bonus_to_use

                if remaining > 0:
                    winnings_to_use = min(wallet.winnings_balance, remaining)
                    wallet.winnings_balance -= winnings_to_use
                    remaining -= winnings_to_use

                if remaining > 0:
                    return JsonResponse({'error': 'Insufficient balance'}, status=400)

                if wallet.main_balance < 0 or wallet.bonus_balance < 0 or wallet.winnings_balance < 0:
                    return JsonResponse({'error': 'Balance underflow detected'}, status=400)
                wallet.save()

                # Log transaction
                Transaction.objects.create(
                    user=user,
                    transaction_type='game_entry',
                    amount=entry_fee,
                    status='approved',
                    description=f'Game #{game.id} ({get_game_stake(game)} Br) - Card #{card_number}'
                )

                # Create card
                card = BingoCard.objects.create(
                    game=game,
                    user=user,
                    card_number=card_number
                )

                increment_missions(user, MissionTemplate.TYPE_PLAY_GAMES, amount=1)
                touch_user_streak(user)

                current_player_count = previous_player_count + 1
                current_real_player_count = previous_real_player_count + 1
                if previous_player_count < settings.GAME_MIN_PLAYERS <= current_player_count:
                    delay_minutes = int(getattr(business_rules, 'rejoin_start_delay_minutes', 0) or 0)
                    game.created_at = timezone.now() + timedelta(minutes=max(0, delay_minutes))
                    game.save(update_fields=['created_at'])

                    if previous_real_player_count == 1 and current_real_player_count >= MIN_REAL_USERS_TO_START:
                        notify_lonely_waiting_players(game, user, delay_minutes)
        
        return JsonResponse({
            'success': True,
            'game_id': game.id,
            'stake_amount': get_game_stake(game),
            'card_number': card_number,
            'card': {
                'card_number': card.card_number,
                'grid': card.get_grid(),
            },
        })
    except (TypeError, ValueError, json.JSONDecodeError):
        return JsonResponse({'error': 'Invalid request payload.'}, status=400)
    except Exception as e:
        logger.exception('select_card_api failed: %s', e)
        return JsonResponse({'error': 'Unable to complete card selection right now.'}, status=500)


@never_cache
@rate_limit(key_prefix='game-status', max_requests=60, window_seconds=60)
@require_valid_web_token
def game_status_api(request, game_id):
    """API endpoint to get game status (for real-time updates)"""
    try:
        touch_site_presence(getattr(request, 'auth_telegram_id', None))
        game = ensure_game_started(game_id)
        
        # Calculate countdown
        countdown = get_game_countdown(game)
        stake_amount = get_game_stake(game)
        total_players = game.cards.count()
        derash = _calculate_derash(total_players, stake_amount)
        winner_card = get_winner_card_payload(game)

        return JsonResponse({
            'game_id': game.id,
            'stake_amount': stake_amount,
            'state': game.state,
            'server_time': timezone.now().isoformat(),
            'number_call_interval': settings.NUMBER_CALL_INTERVAL,
            'countdown': countdown,
            'total_players': total_players,
            'called_numbers': game.get_called_number_entries(),
            'winner': game.winner.first_name if game.winner else None,
            'prize_amount': float(game.prize_amount) if game.prize_amount else float(derash),
            'winner_card': winner_card,
        })
    except Exception as e:
        logger.exception('game_status_api failed for game %s: %s', game_id, e)
        return JsonResponse({'error': 'Unable to fetch game status right now.'}, status=500)


@never_cache
@rate_limit(key_prefix='lobby-state', max_requests=60, window_seconds=60)
@require_path_telegram_auth
def lobby_state_api(request, telegram_id):
    """Return lobby data for React UI."""
    try:
        user = User.objects.select_related('wallet').get(telegram_id=telegram_id)
        touch_site_presence(user.telegram_id)
    except User.DoesNotExist:
        return JsonResponse({'error': 'User not found. Please start the bot first.'}, status=404)

    stakes = get_supported_stakes()
    games = [get_or_create_lobby_game_for_stake(stake) for stake in stakes]
    rows = [build_lobby_game_row(game, user) for game in games]

    user_card = (
        BingoCard.objects.select_related('game')
        .filter(user=user, game__state__in=['waiting', 'playing'])
        .order_by('-game__created_at')
        .first()
    )
    selected_game = user_card.game if user_card else None
    selected_game_payload = None

    if selected_game:
        selected_game = ensure_game_started(selected_game.id)
        taken_cards = list(selected_game.cards.values_list('card_number', flat=True))
        total_players = selected_game.cards.count()
        stake_amount = get_game_stake(selected_game)
        derash = _calculate_derash(total_players, stake_amount)
        selected_game_payload = {
            'id': selected_game.id,
            'state': selected_game.state,
            'stake_amount': stake_amount,
            'medb': stake_amount,
            'countdown': get_game_countdown(selected_game),
            'total_players': total_players,
            'derash': float(derash),
            'taken_cards': taken_cards,
            'all_numbers': list(range(1, settings.CARD_COUNT + 1)),
            'available_cards': settings.CARD_COUNT - len(taken_cards),
            'called_numbers': selected_game.get_called_number_entries(),
            'winner': selected_game.winner.first_name if selected_game.winner else None,
            'winner_card': get_winner_card_payload(selected_game),
            'user_card': {
                'card_number': user_card.card_number,
                'grid': user_card.get_grid(),
            },
        }

    return JsonResponse({
        'user': {
            'first_name': user.first_name,
            'telegram_id': user.telegram_id,
        },
        'games': rows,
        'stakes': stakes,
        'selected_game': selected_game_payload,
        'server_time': timezone.now().isoformat(),
        'number_call_interval': settings.NUMBER_CALL_INTERVAL,
        'wallet_balance': float(user.wallet.total_balance),
        'all_numbers': list(range(1, settings.CARD_COUNT + 1)),
    })


@never_cache
@rate_limit(key_prefix='play-state', max_requests=60, window_seconds=60)
@require_path_telegram_auth
def play_state_api(request, telegram_id, game_id):
    """Return play data for React UI."""
    try:
        user = User.objects.get(telegram_id=telegram_id)
        touch_site_presence(user.telegram_id)
        game = ensure_game_started(game_id)
    except User.DoesNotExist:
        return JsonResponse({'error': 'User not found.'}, status=404)

    user_card = BingoCard.objects.filter(game=game, user=user).first()
    grid = user_card.get_grid() if user_card else None
    called_numbers = game.get_called_numbers()
    total_players = game.cards.count()
    stake_amount = get_game_stake(game)
    if game.prize_amount == 0:
        prize_amount = _calculate_derash(total_players, stake_amount)
    else:
        prize_amount = game.prize_amount

    countdown = get_game_countdown(game)
    winner_card = get_winner_card_payload(game)

    return JsonResponse({
        'user': {
            'first_name': user.first_name,
            'telegram_id': user.telegram_id,
        },
        'game': {
            'id': game.id,
            'state': game.state,
            'stake_amount': stake_amount,
        },
        'server_time': timezone.now().isoformat(),
        'number_call_interval': settings.NUMBER_CALL_INTERVAL,
        'card': {
            'card_number': user_card.card_number,
            'grid': grid,
        } if user_card else None,
        'bingo_number_max': settings.BINGO_NUMBER_MAX,
        'marked_numbers': user_card.get_marked_positions() if user_card else [],
        'called_numbers': game.get_called_number_entries(),
        'total_players': total_players,
        'prize_amount': float(prize_amount),
        'winner': game.winner.first_name if game.winner else None,
        'countdown': countdown,
        'winner_card': winner_card,
    })


@never_cache
@rate_limit(key_prefix='profile-state', max_requests=40, window_seconds=60)
@require_path_telegram_auth
def profile_state_api(request, telegram_id):
    """Return profile data for React UI."""
    try:
        user = User.objects.select_related('wallet').get(telegram_id=telegram_id)
    except User.DoesNotExist:
        return JsonResponse({'error': 'User not found. Please start the bot first.'}, status=404)

    wallet, _ = Wallet.objects.get_or_create(user=user)

    user_cards_qs = BingoCard.objects.filter(user=user)
    games_joined = user_cards_qs.count()
    wins = Game.objects.filter(winner=user).count()
    win_rate = round((wins / games_joined) * 100, 2) if games_joined else 0

    entry_spent = (
        Transaction.objects.filter(user=user, transaction_type='game_entry', status__in=['approved', 'completed'])
        .aggregate(total=Sum('amount'))
        .get('total')
        or Decimal('0')
    )
    total_won = (
        Transaction.objects.filter(user=user, transaction_type='game_win', status__in=['approved', 'completed'])
        .aggregate(total=Sum('amount'))
        .get('total')
        or Decimal('0')
    )
    biggest_win = (
        Transaction.objects.filter(user=user, transaction_type='game_win', status__in=['approved', 'completed'])
        .aggregate(max_value=Max('amount'))
        .get('max_value')
        or Decimal('0')
    )
    referral_bonus_earned = (
        Transaction.objects.filter(user=user, transaction_type='referral_bonus', status__in=['approved', 'completed'])
        .aggregate(total=Sum('amount'))
        .get('total')
        or Decimal('0')
    )

    recent_transactions = []
    for txn in Transaction.objects.filter(user=user).order_by('-created_at')[:15]:
        recent_transactions.append({
            'id': txn.id,
            'type': txn.transaction_type,
            'status': txn.status,
            'amount': float(txn.amount) if txn.amount is not None else None,
            'description': txn.description,
            'created_at': txn.created_at.isoformat(),
        })

    game_history = []
    for card in (
        BingoCard.objects.select_related('game', 'game__winner')
        .filter(user=user, game__state='finished')
        .order_by('-game__finished_at', '-created_at')[:20]
    ):
        game = card.game
        is_win = game.winner_id == user.id
        game_history.append({
            'game_id': game.id,
            'stake_amount': get_game_stake(game),
            'card_number': card.card_number,
            'result': 'won' if is_win else 'lost',
            'prize': float(game.prize_amount) if is_win else 0,
            'finished_at': game.finished_at.isoformat() if game.finished_at else game.created_at.isoformat(),
        })

    # Fall back to tracked referral_count if detailed referral rows are absent.
    rewarded_referrals = user.referral_count

    promo_claims = [
        _serialize_promo_claim(claim)
        for claim in PromoVerificationRequest.objects.select_related('promo_code', 'admin_reviewer')
        .filter(user=user)
        .order_by('-submitted_at')[:20]
    ]

    return JsonResponse({
        'user': {
            'first_name': user.first_name,
            'username': user.username,
            'telegram_id': user.telegram_id,
            'invite_code': user.invite_code,
            'referral_count': user.referral_count,
            'registration_date': user.registration_date.isoformat(),
        },
        'wallet': {
            'total_balance': float(wallet.total_balance),
            'main_balance': float(wallet.main_balance),
            'bonus_balance': float(wallet.bonus_balance),
            'winnings_balance': float(wallet.winnings_balance),
            'withdrawable_balance': float(wallet.withdrawable_balance),
        },
        'stats': {
            'games_joined': games_joined,
            'wins': wins,
            'win_rate': win_rate,
            'total_entry_spent': float(entry_spent),
            'total_won': float(total_won),
            'biggest_win': float(biggest_win),
        },
        'referrals': {
            'invite_code': user.invite_code,
            'referred_count': user.referral_count,
            'rewarded_referrals': rewarded_referrals,
            'referral_bonus_earned': float(referral_bonus_earned),
        },
        'promo_claims': promo_claims,
        'recent_activity': recent_transactions,
        'game_history': game_history,
    })


@never_cache
@rate_limit(key_prefix='wallet-state', max_requests=40, window_seconds=60)
@require_path_telegram_auth
def wallet_state_api(request, telegram_id):
    """Return read-only wallet information for React UI."""
    business_rules = get_business_rules()

    try:
        user = User.objects.select_related('wallet').get(telegram_id=telegram_id)
    except User.DoesNotExist:
        return JsonResponse({'error': 'User not found. Please start the bot first.'}, status=404)

    wallet, _ = Wallet.objects.get_or_create(user=user)

    type_filter = (request.GET.get('type') or 'all').lower()
    status_filter = (request.GET.get('status') or 'all').lower()

    valid_types = {choice[0] for choice in Transaction.TRANSACTION_TYPES}
    valid_statuses = {choice[0] for choice in Transaction.STATUS_CHOICES}

    if type_filter != 'all' and type_filter not in valid_types:
        return JsonResponse({'error': 'Invalid transaction type filter.'}, status=400)
    if status_filter != 'all' and status_filter not in valid_statuses:
        return JsonResponse({'error': 'Invalid transaction status filter.'}, status=400)

    completed_statuses = ['approved', 'completed']
    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = now - timedelta(days=30)

    base_txn_qs = Transaction.objects.filter(user=user)
    filtered_qs = base_txn_qs
    if type_filter != 'all':
        filtered_qs = filtered_qs.filter(transaction_type=type_filter)
    if status_filter != 'all':
        filtered_qs = filtered_qs.filter(status=status_filter)

    recent_transactions = []
    recent_qs = (
        filtered_qs
        .select_related('deposit_detail', 'withdrawal_detail')
        .order_by('-created_at')[:30]
    )
    for txn in recent_qs:
        payment_method = ''
        if hasattr(txn, 'deposit_detail') and txn.deposit_detail:
            payment_method = txn.deposit_detail.payment_method
        elif hasattr(txn, 'withdrawal_detail') and txn.withdrawal_detail:
            payment_method = txn.withdrawal_detail.payment_method

        recent_transactions.append({
            'id': txn.id,
            'type': txn.transaction_type,
            'status': txn.status,
            'amount': float(txn.amount) if txn.amount is not None else None,
            'reference': txn.reference,
            'description': txn.description,
            'payment_method': payment_method,
            'created_at': txn.created_at.isoformat(),
            'processed_at': txn.processed_at.isoformat() if txn.processed_at else None,
        })

    total_entry_spent = (
        base_txn_qs
        .filter(transaction_type='game_entry', status__in=completed_statuses)
        .aggregate(total=Sum('amount'))
        .get('total')
        or Decimal('0')
    )
    total_game_won = (
        base_txn_qs
        .filter(transaction_type='game_win', status__in=completed_statuses)
        .aggregate(total=Sum('amount'))
        .get('total')
        or Decimal('0')
    )
    total_referral_bonus = (
        base_txn_qs
        .filter(transaction_type='referral_bonus', status__in=completed_statuses)
        .aggregate(total=Sum('amount'))
        .get('total')
        or Decimal('0')
    )
    biggest_win = (
        base_txn_qs
        .filter(transaction_type='game_win', status__in=completed_statuses)
        .aggregate(max_value=Max('amount'))
        .get('max_value')
        or Decimal('0')
    )

    today_spent = (
        base_txn_qs
        .filter(transaction_type='game_entry', status__in=completed_statuses, created_at__gte=today_start)
        .aggregate(total=Sum('amount'))
        .get('total')
        or Decimal('0')
    )
    today_won = (
        base_txn_qs
        .filter(transaction_type='game_win', status__in=completed_statuses, created_at__gte=today_start)
        .aggregate(total=Sum('amount'))
        .get('total')
        or Decimal('0')
    )
    month_spent = (
        base_txn_qs
        .filter(transaction_type='game_entry', status__in=completed_statuses, created_at__gte=month_start)
        .aggregate(total=Sum('amount'))
        .get('total')
        or Decimal('0')
    )
    month_won = (
        base_txn_qs
        .filter(transaction_type='game_win', status__in=completed_statuses, created_at__gte=month_start)
        .aggregate(total=Sum('amount'))
        .get('total')
        or Decimal('0')
    )

    latest_txn = base_txn_qs.order_by('-created_at').first()

    return JsonResponse({
        'user': {
            'first_name': user.first_name,
            'telegram_id': user.telegram_id,
            'registration_date': user.registration_date.isoformat(),
        },
        'wallet': {
            'total_balance': float(wallet.total_balance),
            'main_balance': float(wallet.main_balance),
            'bonus_balance': float(wallet.bonus_balance),
            'winnings_balance': float(wallet.winnings_balance),
            'withdrawable_balance': float(wallet.withdrawable_balance),
            'updated_at': wallet.updated_at.isoformat(),
        },
        'overview': {
            'total_transactions': base_txn_qs.count(),
            'pending_transactions': base_txn_qs.filter(status='pending').count(),
            'completed_transactions': base_txn_qs.filter(status__in=completed_statuses).count(),
            'rejected_transactions': base_txn_qs.filter(status='rejected').count(),
            'last_transaction_at': latest_txn.created_at.isoformat() if latest_txn else None,
        },
        'finance_summary': {
            'total_entry_spent': float(total_entry_spent),
            'total_game_won': float(total_game_won),
            'total_referral_bonus': float(total_referral_bonus),
            'net_profit_loss': float((total_game_won + total_referral_bonus) - total_entry_spent),
            'biggest_win': float(biggest_win),
            'today_spent': float(today_spent),
            'today_won': float(today_won),
            'today_net': float(today_won - today_spent),
            'month_spent': float(month_spent),
            'month_won': float(month_won),
            'month_net': float(month_won - month_spent),
        },
        'filters': {
            'current_type': type_filter,
            'current_status': status_filter,
            'types': ['all'] + [choice[0] for choice in Transaction.TRANSACTION_TYPES],
            'statuses': ['all'] + [choice[0] for choice in Transaction.STATUS_CHOICES],
        },
        'recent_transactions': recent_transactions,
        'informational_notes': [
            'Total balance includes main, bonus, and winnings balances.',
            'Only winnings balance is withdrawable.',
            f"Minimum withdrawal is {business_rules.minimum_withdrawable_balance} Birr.",
            (
                f"Telebirr receiving number: {business_rules.telebirr_receiving_phone_number} "
                f"({business_rules.telebirr_receiving_account_name})."
            ),
            'Net values compare wins against game entry spending.',
            'Pending transactions are informational and may still change status.',
        ],
    })


@never_cache
@rate_limit(key_prefix='trophy-state', max_requests=40, window_seconds=60)
@require_path_telegram_auth
def trophy_state_api(request, telegram_id):
    """Return trophy/leaderboard data for React UI."""
    try:
        user = User.objects.get(telegram_id=telegram_id)
    except User.DoesNotExist:
        return JsonResponse({'error': 'User not found. Please start the bot first.'}, status=404)

    period = (request.GET.get('period') or 'all').lower()
    stake_param = request.GET.get('stake')
    season_id = request.GET.get('season_id')

    stakes = get_supported_stakes()
    stake_value = None
    if stake_param and stake_param.lower() != 'all':
        try:
            stake_value = int(stake_param)
        except ValueError:
            return JsonResponse({'error': 'Invalid stake filter.'}, status=400)
        if stake_value not in stakes:
            return JsonResponse({'error': 'Unsupported stake filter.'}, status=400)

    now = timezone.now()
    start_at = None
    current_season = None
    if period == 'today':
        start_at = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == 'week':
        start_at = now - timedelta(days=7)
    elif period == 'month':
        start_at = now - timedelta(days=30)
    elif period == 'season':
        if season_id:
            try:
                current_season = Season.objects.get(id=int(season_id))
            except (ValueError, Season.DoesNotExist):
                return JsonResponse({'error': 'Invalid season filter.'}, status=400)
        else:
            current_season = Season.get_current()

        if not current_season:
            return JsonResponse({'error': 'No active season found.'}, status=404)

        start_at = current_season.starts_at
        end_at = current_season.ends_at
    elif period != 'all':
        return JsonResponse({'error': 'Invalid period filter.'}, status=400)

    finished_games = Game.objects.filter(state='finished')
    if start_at is not None:
        finished_games = finished_games.filter(finished_at__gte=start_at)
    if period == 'season' and current_season:
        finished_games = finished_games.filter(finished_at__lte=end_at)
    if stake_value is not None:
        finished_games = finished_games.filter(stake_amount=stake_value)

    joined_counts = {
        row['user_id']: row['joined_games']
        for row in (
            BingoCard.objects.filter(game__in=finished_games)
            .values('user_id')
            .annotate(joined_games=Count('id'))
        )
    }

    leaderboard_rows = []
    win_aggregates = (
        finished_games.filter(winner__isnull=False)
        .values('winner_id', 'winner__first_name', 'winner__username')
        .annotate(
            total_winnings=Sum('prize_amount'),
            wins=Count('id'),
            biggest_win=Max('prize_amount'),
        )
        .order_by('-total_winnings', '-wins', 'winner_id')
    )

    for rank, row in enumerate(win_aggregates, start=1):
        joined = int(joined_counts.get(row['winner_id'], 0))
        wins = int(row['wins'] or 0)
        win_rate = round((wins / joined) * 100, 2) if joined else 0
        leaderboard_rows.append({
            'rank': rank,
            'user_id': row['winner_id'],
            'first_name': row['winner__first_name'],
            'username': row['winner__username'],
            'total_winnings': float(row['total_winnings'] or 0),
            'wins': wins,
            'season_points': int(wins * 3),
            'games_joined': joined,
            'win_rate': win_rate,
            'biggest_win': float(row['biggest_win'] or 0),
        })

    top_rows = leaderboard_rows[:20]
    podium = top_rows[:3]

    user_position = {
        'user_id': user.id,
        'rank': None,
        'total_winnings': 0.0,
        'wins': 0,
        'games_joined': int(joined_counts.get(user.id, 0)),
        'win_rate': 0.0,
        'biggest_win': 0.0,
        'gap_to_next_rank': None,
    }

    for row in leaderboard_rows:
        if row['user_id'] != user.id:
            continue
        user_position.update({
            'rank': row['rank'],
            'total_winnings': row['total_winnings'],
            'wins': row['wins'],
            'games_joined': row['games_joined'],
            'win_rate': row['win_rate'],
            'biggest_win': row['biggest_win'],
        })
        if row['rank'] > 1:
            previous_row = leaderboard_rows[row['rank'] - 2]
            gap = max(0, previous_row['total_winnings'] - row['total_winnings'])
            user_position['gap_to_next_rank'] = round(gap, 2)
        break

    recent_big_wins = []
    for game in finished_games.filter(winner__isnull=False).select_related('winner').order_by('-prize_amount', '-finished_at')[:10]:
        recent_big_wins.append({
            'game_id': game.id,
            'winner_name': game.winner.first_name,
            'winner_username': game.winner.username,
            'stake_amount': get_game_stake(game),
            'prize_amount': float(game.prize_amount or 0),
            'finished_at': (game.finished_at or game.created_at).isoformat(),
        })

    most_active = []
    active_rows = (
        BingoCard.objects.filter(game__in=finished_games)
        .values('user_id', 'user__first_name', 'user__username')
        .annotate(games_joined=Count('id'))
        .order_by('-games_joined', 'user_id')[:10]
    )
    for row in active_rows:
        most_active.append({
            'user_id': row['user_id'],
            'first_name': row['user__first_name'],
            'username': row['user__username'],
            'games_joined': int(row['games_joined'] or 0),
        })

    return JsonResponse({
        'filters': {
            'period': period,
            'stake': stake_value,
            'season_id': current_season.id if current_season else None,
            'season_name': current_season.name if current_season else None,
            'available_stakes': stakes,
            'available_periods': ['today', 'week', 'month', 'season', 'all'],
        },
        'leaderboard': top_rows,
        'podium': podium,
        'your_position': user_position,
        'recent_big_wins': recent_big_wins,
        'most_active_players': most_active,
        'refresh_time': timezone.now().isoformat(),
        'tie_break_rules': [
            'Higher total winnings ranks first.',
            'If tied, higher wins ranks first.',
            'If still tied, earlier achiever ranks first.',
        ],
        'season_rules': {
            'point_formula': '3 points per win',
            'top_rewards': {
                'top_1': float(current_season.top_1_reward) if current_season else 0,
                'top_2': float(current_season.top_2_reward) if current_season else 0,
                'top_3': float(current_season.top_3_reward) if current_season else 0,
                'participation': float(current_season.participation_reward) if current_season else 0,
            },
        },
    })


@never_cache
@rate_limit(key_prefix='missions-state', max_requests=40, window_seconds=60)
@require_path_telegram_auth
def missions_state_api(request, telegram_id):
    try:
        user = User.objects.get(telegram_id=telegram_id)
    except User.DoesNotExist:
        return JsonResponse({'error': 'User not found. Please start the bot first.'}, status=404)

    touch_user_streak(user)
    templates = MissionTemplate.objects.filter(is_active=True).order_by('sort_order', 'id')

    now = timezone.now().date()
    weekly_start = now - timedelta(days=now.weekday())

    progress_rows = []
    for mission in templates:
        if mission.period == MissionTemplate.PERIOD_DAILY:
            period_start = now
        else:
            period_start = weekly_start

        progress = (
            UserMissionProgress.objects.select_related('mission')
            .filter(user=user, mission=mission, period_start=period_start)
            .first()
        )
        if not progress:
            period_end = period_start if mission.period == MissionTemplate.PERIOD_DAILY else (weekly_start + timedelta(days=6))
            progress = UserMissionProgress.objects.create(
                user=user,
                mission=mission,
                period_start=period_start,
                period_end=period_end,
                reward_amount=mission.reward_amount,
            )
        progress_rows.append(_serialize_mission_progress(progress))

    streak = getattr(user, 'streak', None)
    return JsonResponse({
        'missions': progress_rows,
        'streak': {
            'current_streak': streak.current_streak if streak else 0,
            'best_streak': streak.best_streak if streak else 0,
            'last_active_date': streak.last_active_date.isoformat() if streak and streak.last_active_date else None,
            'streak_protect_tokens': streak.streak_protect_tokens if streak else 1,
        },
        'server_time': timezone.now().isoformat(),
    })


@csrf_exempt
@require_POST
@rate_limit(key_prefix='mission-claim', max_requests=20, window_seconds=60)
@require_valid_web_token
def claim_mission_api(request):
    try:
        data = json.loads(request.body)
        telegram_id = int(data.get('telegram_id'))
        if telegram_id != int(request.auth_telegram_id):
            return JsonResponse({'error': 'Forbidden.'}, status=403)
        progress_id = int(data.get('progress_id'))

        user = User.objects.get(telegram_id=telegram_id)
        amount, progress = claim_mission(user, progress_id)
        return JsonResponse({
            'success': True,
            'reward_amount': float(amount),
            'progress': _serialize_mission_progress(progress),
        })
    except RewardSafetyError as exc:
        return JsonResponse({'error': str(exc)}, status=429)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        return JsonResponse({'error': str(exc) or 'Invalid request payload.'}, status=400)
    except User.DoesNotExist:
        return JsonResponse({'error': 'User not found.'}, status=404)
    except Exception as exc:
        logger.exception('claim_mission_api failed: %s', exc)
        return JsonResponse({'error': 'Unable to claim mission right now.'}, status=500)


@never_cache
@rate_limit(key_prefix='events-state', max_requests=50, window_seconds=60)
@require_path_telegram_auth
def live_events_api(request, telegram_id):
    try:
        User.objects.get(telegram_id=telegram_id)
    except User.DoesNotExist:
        return JsonResponse({'error': 'User not found. Please start the bot first.'}, status=404)

    now = timezone.now()
    active = LiveEvent.objects.filter(is_active=True, starts_at__lte=now, ends_at__gte=now).order_by('ends_at')
    upcoming = LiveEvent.objects.filter(is_active=True, starts_at__gt=now).order_by('starts_at')[:10]

    def serialize_event(event):
        return {
            'id': event.id,
            'name': event.name,
            'event_type': event.event_type,
            'description': event.description,
            'starts_at': event.starts_at.isoformat(),
            'ends_at': event.ends_at.isoformat(),
            'bonus_multiplier': float(event.bonus_multiplier),
            'is_live': event.is_live(),
        }

    return JsonResponse({
        'active_events': [serialize_event(event) for event in active],
        'upcoming_events': [serialize_event(event) for event in upcoming],
        'server_time': now.isoformat(),
    })


@csrf_exempt
@require_POST
@rate_limit(key_prefix='promo-redeem', max_requests=20, window_seconds=60)
@require_valid_web_token
def redeem_promo_code_api(request):
    try:
        data = json.loads(request.body)
        telegram_id = int(data.get('telegram_id'))
        if telegram_id != int(request.auth_telegram_id):
            return JsonResponse({'error': 'Forbidden.'}, status=403)

        promo_code = str(data.get('code', '')).strip().upper()
        if not promo_code:
            return JsonResponse({'error': 'Promo code is required.'}, status=400)

        user = User.objects.get(telegram_id=telegram_id)
        promo = PromoCode.objects.filter(code__iexact=promo_code).first()
        if not promo:
            return JsonResponse({'error': 'Promo code not found.'}, status=404)

        now = timezone.now()
        if not promo.is_active or now < promo.starts_at or now > promo.ends_at:
            return JsonResponse({'error': 'Promo code is not active right now.'}, status=400)

        account_age_days = (now.date() - user.registration_date.date()).days
        if account_age_days < promo.min_account_age_days:
            return JsonResponse({'error': 'Account is too new for this promo code.'}, status=400)

        with transaction.atomic():
            PromoCode.objects.select_for_update().get(pk=promo.pk)

            total_redemptions = PromoCodeRedemption.objects.filter(promo_code=promo).count()
            if promo.max_redemptions > 0 and total_redemptions >= promo.max_redemptions:
                return JsonResponse({'error': 'Promo redemption limit reached.'}, status=400)

            user_redemptions = PromoCodeRedemption.objects.filter(promo_code=promo, user=user).count()
            if user_redemptions >= promo.per_user_limit:
                return JsonResponse({'error': 'You already redeemed this promo code.'}, status=400)

            if not promo.is_visible_in_frontend:
                existing_pending = PromoVerificationRequest.objects.filter(
                    user=user,
                    promo_code=promo,
                    status=PromoVerificationRequest.STATUS_PENDING,
                ).first()
                if existing_pending:
                    return JsonResponse({
                        'success': True,
                        'requires_verification': True,
                        'status': existing_pending.status,
                        'request_id': existing_pending.id,
                        'message': 'Your hidden promo claim is already pending verification.',
                    })

                claim = PromoVerificationRequest.objects.create(
                    user=user,
                    promo_code=promo,
                    status=PromoVerificationRequest.STATUS_PENDING,
                )
                _notify_admins_hidden_promo_claim(claim)

                return JsonResponse({
                    'success': True,
                    'requires_verification': True,
                    'status': claim.status,
                    'request_id': claim.id,
                    'message': 'Promo submitted for admin verification.',
                })

            credited_amount = credit_user_reward(
                user=user,
                amount=promo.reward_amount,
                reward_balance=promo.reward_balance,
                description=f"Promo code {promo.code}",
            )

            PromoCodeRedemption.objects.create(
                promo_code=promo,
                user=user,
                amount=credited_amount,
            )

        increment_missions(user, MissionTemplate.TYPE_REDEEM_PROMO, amount=1)
        touch_user_streak(user)

        return JsonResponse({
            'success': True,
            'code': promo.code,
            'tier': promo.tier,
            'credited_amount': float(credited_amount),
            'reward_balance': promo.reward_balance,
            'expires_at': promo.ends_at.isoformat(),
        })
    except RewardSafetyError as exc:
        return JsonResponse({'error': str(exc)}, status=429)
    except User.DoesNotExist:
        return JsonResponse({'error': 'User not found.'}, status=404)
    except (TypeError, ValueError, json.JSONDecodeError):
        return JsonResponse({'error': 'Invalid request payload.'}, status=400)
    except Exception as exc:
        logger.exception('redeem_promo_code_api failed: %s', exc)
        return JsonResponse({'error': 'Unable to redeem promo code right now.'}, status=500)


@never_cache
@rate_limit(key_prefix='promo-list', max_requests=30, window_seconds=60)
@require_path_telegram_auth
def promo_codes_api(request, telegram_id):
    try:
        user = User.objects.get(telegram_id=telegram_id)
    except User.DoesNotExist:
        return JsonResponse({'error': 'User not found. Please start the bot first.'}, status=404)

    now = timezone.now()
    rows = []
    promos = PromoCode.objects.filter(
        is_active=True,
        is_visible_in_frontend=True,
        ends_at__gte=now,
    ).order_by('starts_at', 'id')[:40]

    claims_by_promo = {}
    claim_rows = (
        PromoVerificationRequest.objects.select_related('promo_code')
        .filter(user=user)
        .order_by('promo_code_id', '-submitted_at')
    )
    for claim in claim_rows:
        if claim.promo_code_id not in claims_by_promo:
            claims_by_promo[claim.promo_code_id] = claim

    for promo in promos:
        user_uses = PromoCodeRedemption.objects.filter(promo_code=promo, user=user).count()
        global_uses = PromoCodeRedemption.objects.filter(promo_code=promo).count()
        claim = claims_by_promo.get(promo.id)
        rows.append({
            'id': promo.id,
            'code': promo.code,
            'title': promo.title,
            'tier': promo.tier,
            'reward_amount': float(promo.reward_amount),
            'reward_balance': promo.reward_balance,
            'starts_at': promo.starts_at.isoformat(),
            'ends_at': promo.ends_at.isoformat(),
            'is_live': promo.starts_at <= now <= promo.ends_at,
            'max_redemptions': promo.max_redemptions,
            'global_redemptions': global_uses,
            'per_user_limit': promo.per_user_limit,
            'user_redemptions': user_uses,
            'claim_status': claim.status if claim else None,
            'claim_submitted_at': claim.submitted_at.isoformat() if claim else None,
            'claim_decision_time': claim.decision_time.isoformat() if claim and claim.decision_time else None,
            'claim_review_reason': claim.review_reason if claim else '',
            'is_hidden_claim': False,
        })

    hidden_claim_rows = (
        PromoVerificationRequest.objects.select_related('promo_code')
        .filter(user=user, promo_code__is_visible_in_frontend=False)
        .order_by('-submitted_at')[:30]
    )
    for claim in hidden_claim_rows:
        promo = claim.promo_code
        user_uses = PromoCodeRedemption.objects.filter(promo_code=promo, user=user).count()
        global_uses = PromoCodeRedemption.objects.filter(promo_code=promo).count()
        rows.append({
            'id': promo.id,
            'code': promo.code,
            'title': promo.title,
            'tier': promo.tier,
            'reward_amount': float(promo.reward_amount),
            'reward_balance': promo.reward_balance,
            'starts_at': promo.starts_at.isoformat(),
            'ends_at': promo.ends_at.isoformat(),
            'is_live': promo.starts_at <= now <= promo.ends_at,
            'max_redemptions': promo.max_redemptions,
            'global_redemptions': global_uses,
            'per_user_limit': promo.per_user_limit,
            'user_redemptions': user_uses,
            'claim_status': claim.status,
            'claim_submitted_at': claim.submitted_at.isoformat(),
            'claim_decision_time': claim.decision_time.isoformat() if claim.decision_time else None,
            'claim_review_reason': claim.review_reason,
            'is_hidden_claim': True,
        })

    rows.sort(key=lambda item: (item.get('claim_submitted_at') or item.get('starts_at') or ''), reverse=True)

    return JsonResponse({
        'promo_codes': rows,
        'server_time': now.isoformat(),
    })


@never_cache
@rate_limit(key_prefix='promo-claims', max_requests=40, window_seconds=60)
@require_path_telegram_auth
def promo_claims_api(request, telegram_id):
    try:
        user = User.objects.get(telegram_id=telegram_id)
    except User.DoesNotExist:
        return JsonResponse({'error': 'User not found. Please start the bot first.'}, status=404)

    rows = [
        _serialize_promo_claim(claim)
        for claim in PromoVerificationRequest.objects.select_related('promo_code', 'admin_reviewer')
        .filter(user=user)
        .order_by('-submitted_at')[:50]
    ]

    return JsonResponse({'promo_claims': rows, 'server_time': timezone.now().isoformat()})


@csrf_exempt
@require_POST
@rate_limit(key_prefix='mark-number', max_requests=30, window_seconds=60)
@require_valid_web_token
def mark_number_api(request):
    """Mark any number that has already been called on the player's bingo card."""
    try:
        data = json.loads(request.body)
        telegram_id = int(data.get('telegram_id'))
        if telegram_id != int(request.auth_telegram_id):
            return JsonResponse({'error': 'Forbidden.'}, status=403)
        game_id = data.get('game_id')
        number = int(data.get('number'))

        user = User.objects.get(telegram_id=telegram_id)
        game = get_object_or_404(Game, id=game_id)
        card = get_object_or_404(BingoCard, game=game, user=user)

        if game.state != 'playing':
            return JsonResponse({'error': 'Marking is available only while game is playing.'}, status=400)

        called_number_entries = game.get_called_number_entries()
        if not called_number_entries:
            return JsonResponse({'error': 'No numbers have been called yet.'}, status=400)

        called_number_set = {int(entry['number']) for entry in called_number_entries if 'number' in entry}
        if number not in called_number_set:
            return JsonResponse({'error': 'You can only mark numbers that have been called.'}, status=400)

        # Check if the number is on the player's card
        grid_values = {value for row in card.get_grid() for value in row if value is not None}
        if number not in grid_values:
            return JsonResponse({'error': 'This number is not on your card.'}, status=400)

        # Mark the number
        marked_numbers = card.get_marked_positions()
        if number not in marked_numbers:
            marked_numbers.append(number)
            card.set_marked_positions(marked_numbers)
            card.save(update_fields=['marked_positions'])

        return JsonResponse({
            'success': True,
            'marked_numbers': marked_numbers,
            'marked_number': number,
        })
    except (TypeError, ValueError, json.JSONDecodeError):
        return JsonResponse({'error': 'Invalid number'}, status=400)
    except Exception as e:
        logger.exception('mark_number_api failed: %s', e)
        return JsonResponse({'error': 'Unable to mark number right now.'}, status=500)


@csrf_exempt
@require_POST
@rate_limit(key_prefix='claim-bingo', max_requests=15, window_seconds=60)
@require_valid_web_token
def claim_bingo_api(request):
    """API endpoint to validate BINGO claim"""
    try:
        data = json.loads(request.body)
        telegram_id = int(data.get('telegram_id'))
        if telegram_id != int(request.auth_telegram_id):
            return JsonResponse({'error': 'Forbidden.'}, status=403)
        game_id = data.get('game_id')
        
        user = User.objects.get(telegram_id=telegram_id)
        game = get_object_or_404(Game, id=game_id)
        card = get_object_or_404(BingoCard, game=game, user=user)
        
        # Check if game is finished (already has a winner)
        if game.state == 'finished':
            return JsonResponse({'error': 'Game already finished'}, status=400)
        
        # Auto-transition to playing if still waiting and enough players joined
        real_players = game.cards.filter(user__telegram_id__lt=BOT_TELEGRAM_ID_THRESHOLD).count()
        if (
            game.state == 'waiting'
            and game.cards.count() >= settings.GAME_MIN_PLAYERS
            and real_players >= MIN_REAL_USERS_TO_START
        ):
            game.state = 'playing'
            game.started_at = timezone.now()
            game.save()
        
        # Check if game is in a valid state for claiming
        if game.state not in ['waiting', 'playing']:
            return JsonResponse({'error': 'Game is not active'}, status=400)
        
        # Validate BINGO
        from bot.utils.game_logic import check_bingo_win
        grid = card.get_grid()
        called_numbers = game.get_called_numbers()

        called_set = set(called_numbers)
        marked_numbers = [number for number in card.get_marked_positions() if number in called_set]
        is_winner, pattern = check_bingo_win(grid, marked_numbers)
        
        if is_winner:
            # Calculate prize based on total players for display, but credit based on real players
            total_players = game.cards.count()
            stake_amount = get_game_stake(game)
            
            # Total prize for display (includes fake players)
            total_pool = Decimal(total_players) * Decimal(stake_amount)
            derash_multiplier = get_derash_multiplier()
            system_multiplier = get_system_multiplier()
            display_prize = total_pool * derash_multiplier
            
            if game.has_bots:
                # Game has bots: winner gets only real players' contribution
                real_players = game.real_players_count
                
                # Real players' pool
                real_pool = Decimal(real_players) * Decimal(stake_amount)
                actual_prize = real_pool * derash_multiplier
                real_commission = real_pool * system_multiplier
                
                # System revenue: only commission from real players (no fake pool)
                system_revenue = real_commission
                game.system_revenue = system_revenue
            else:
                # No bots: normal calculation with 20% commission
                actual_prize = display_prize  # Same as display prize
                system_revenue = _calculate_system_share(total_players, stake_amount)
                game.system_revenue = system_revenue
            
            # Update game state
            game.state = 'finished'
            game.finished_at = timezone.now()
            game.winner = user
            game.prize_amount = display_prize  # Display total prize
            game.save()
            
            # Mark card as winner
            card.is_winner = True
            card.save()
            
            # Credit winner's wallet with actual prize to WINNINGS balance
            wallet = user.wallet
            wallet.winnings_balance += actual_prize
            wallet.save()
            
            # Log transaction with actual prize
            Transaction.objects.create(
                user=user,
                transaction_type='game_win',
                amount=actual_prize,
                status='approved',
                description=f'Won Game #{game.id} - {pattern}'
            )

            increment_missions(user, MissionTemplate.TYPE_WIN_GAMES, amount=1)
            touch_user_streak(user)

            if system_revenue > 0:
                SystemBalanceLedger.append_entry(
                    event_type='game_commission',
                    direction='credit',
                    amount=system_revenue,
                    game=game,
                    description=f'Game #{game.id} winner commission ({get_business_rules().system_percentage}%).',
                    metadata={
                        'total_players': int(total_players),
                        'has_bots': bool(game.has_bots),
                        'actual_prize': str(actual_prize),
                        'display_prize': str(display_prize),
                    },
                    idempotency_key=f'game:{game.id}:winner_commission',
                )
            
            return JsonResponse({
                'success': True,
                'winner': True,
                'pattern': pattern,
                'prize': float(display_prize),  # Return display prize for UI
                'winner_card': {
                    'card_number': card.card_number,
                    'grid': grid,
                },
                'message': f'🎉 BINGO! You won {display_prize} Birr!'
            })
        else:
            return JsonResponse({
                'success': True,
                'winner': False,
                'message': '❌ Not a valid BINGO yet. Keep playing!'
            })
        
    except (TypeError, ValueError, json.JSONDecodeError):
        return JsonResponse({'error': 'Invalid request payload.'}, status=400)
    except Exception as e:
        logger.exception('claim_bingo_api failed: %s', e)
        return JsonResponse({'error': 'Unable to validate bingo claim right now.'}, status=500)
