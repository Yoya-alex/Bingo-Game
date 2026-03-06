from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.cache import never_cache
from django.conf import settings
from django.utils import timezone
from django.db import transaction
from django.db.models import Count, Max, Sum
from decimal import Decimal
from datetime import timedelta
from users.models import User
from game.models import Game, BingoCard, StakeLobbyLock, SystemBalanceLedger
from wallet.models import Wallet, Transaction
import json


BOT_TELEGRAM_ID_THRESHOLD = 9000000000
MIN_REAL_USERS_TO_START = 2


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
    return max(0, int(settings.WAITING_TIME - time_elapsed))


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
    derash = Decimal(real_players) * Decimal(stake_amount) * Decimal('0.8')
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
            status_label = f'Starting in {countdown}s'
        else:
            status_label = 'Waiting for players'

    action = 'none'
    action_label = 'In Progress' if game.state == 'playing' else 'Unavailable'
    if user_has_card:
        action = 'play'
        action_label = 'Play'
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
            time_elapsed >= settings.WAITING_TIME
            and total_players >= settings.GAME_MIN_PLAYERS
            and real_players >= MIN_REAL_USERS_TO_START
        ):
            game.state = 'playing'
            game.started_at = timezone.now()
            game.save()
        return game


def game_lobby(request, telegram_id):
    """Game lobby - show card selection"""
    try:
        user = User.objects.select_related('wallet').get(telegram_id=telegram_id)
    except User.DoesNotExist:
        return render(request, 'game/error.html', {
            'error': 'User not found. Please start the bot first.'
        })

    return redirect(f"{settings.REACT_APP_URL}/home/{telegram_id}")


def game_play(request, telegram_id, game_id):
    """Game play screen - show user's bingo card"""
    try:
        user = User.objects.get(telegram_id=telegram_id)
    except User.DoesNotExist:
        return render(request, 'game/error.html', {
            'error': 'User not found.'
        })

    return redirect(f"{settings.REACT_APP_URL}/play/{telegram_id}/{game_id}")


@csrf_exempt
def select_card_api(request):
    """API endpoint to select a card"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        data = json.loads(request.body)
        telegram_id = data.get('telegram_id')
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
            wallet, _ = Wallet.objects.select_for_update().get_or_create(user=user)

            user_cards_qs = BingoCard.objects.select_related('game').filter(user=user, game__state='waiting')
            if stake_amount is not None:
                user_cards_qs = user_cards_qs.filter(game__stake_amount=stake_amount)
            user_card = user_cards_qs.order_by('-game__created_at').first()

            if user_card:
                game = Game.objects.select_for_update().get(pk=user_card.game_id)
                previous_player_count = game.cards.count()
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

                current_player_count = previous_player_count + 1
                if previous_player_count < settings.GAME_MIN_PLAYERS <= current_player_count:
                    game.created_at = timezone.now()
                    game.save(update_fields=['created_at'])
        
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
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@never_cache
def game_status_api(request, game_id):
    """API endpoint to get game status (for real-time updates)"""
    try:
        game = ensure_game_started(game_id)
        
        # Calculate countdown
        countdown = get_game_countdown(game)
        stake_amount = get_game_stake(game)
        total_players = game.cards.count()
        derash = Decimal(total_players) * Decimal(stake_amount) * Decimal('0.8')
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
        return JsonResponse({'error': str(e)}, status=500)


@never_cache
def lobby_state_api(request, telegram_id):
    """Return lobby data for React UI."""
    try:
        user = User.objects.select_related('wallet').get(telegram_id=telegram_id)
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
        derash = Decimal(total_players) * Decimal(stake_amount) * Decimal('0.8')
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
def play_state_api(request, telegram_id, game_id):
    """Return play data for React UI."""
    try:
        user = User.objects.get(telegram_id=telegram_id)
        game = ensure_game_started(game_id)
        user_card = get_object_or_404(BingoCard, game=game, user=user)
    except User.DoesNotExist:
        return JsonResponse({'error': 'User not found.'}, status=404)

    grid = user_card.get_grid()
    called_numbers = game.get_called_numbers()
    total_players = game.cards.count()
    stake_amount = get_game_stake(game)
    if game.prize_amount == 0:
        prize_amount = Decimal(total_players) * Decimal(stake_amount) * Decimal("0.8")
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
        },
        'bingo_number_max': settings.BINGO_NUMBER_MAX,
        'marked_numbers': user_card.get_marked_positions(),
        'called_numbers': game.get_called_number_entries(),
        'total_players': total_players,
        'prize_amount': float(prize_amount),
        'winner': game.winner.first_name if game.winner else None,
        'countdown': countdown,
        'winner_card': winner_card,
    })


@never_cache
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
        'recent_activity': recent_transactions,
        'game_history': game_history,
    })


@never_cache
def wallet_state_api(request, telegram_id):
    """Return read-only wallet information for React UI."""
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
            'Net values compare wins against game entry spending.',
            'Pending transactions are informational and may still change status.',
        ],
    })


@never_cache
def trophy_state_api(request, telegram_id):
    """Return trophy/leaderboard data for React UI."""
    try:
        user = User.objects.get(telegram_id=telegram_id)
    except User.DoesNotExist:
        return JsonResponse({'error': 'User not found. Please start the bot first.'}, status=404)

    period = (request.GET.get('period') or 'all').lower()
    stake_param = request.GET.get('stake')

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
    if period == 'today':
        start_at = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == 'week':
        start_at = now - timedelta(days=7)
    elif period == 'month':
        start_at = now - timedelta(days=30)
    elif period != 'all':
        return JsonResponse({'error': 'Invalid period filter.'}, status=400)

    finished_games = Game.objects.filter(state='finished')
    if start_at is not None:
        finished_games = finished_games.filter(finished_at__gte=start_at)
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
            'available_stakes': stakes,
            'available_periods': ['today', 'week', 'month', 'all'],
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
    })


@csrf_exempt
def mark_number_api(request):
    """Mark only the current called number on the player's bingo card."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        data = json.loads(request.body)
        telegram_id = data.get('telegram_id')
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

        current_called_number = called_number_entries[-1]['number']
        if number != current_called_number:
            return JsonResponse({'error': 'You can only mark the current called number.'}, status=400)

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
    except ValueError:
        return JsonResponse({'error': 'Invalid number'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
def claim_bingo_api(request):
    """API endpoint to validate BINGO claim"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        data = json.loads(request.body)
        telegram_id = data.get('telegram_id')
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
            display_prize = total_pool * Decimal("0.8")  # 80% of total pool
            
            if game.has_bots:
                # Game has bots: winner gets only real players' contribution
                real_players = game.real_players_count
                
                # Real players' pool
                real_pool = Decimal(real_players) * Decimal(stake_amount)
                actual_prize = real_pool * Decimal("0.8")  # 80% to winner (actual amount)
                real_commission = real_pool * Decimal("0.2")  # 20% commission
                
                # System revenue: only commission from real players (no fake pool)
                system_revenue = real_commission
                game.system_revenue = system_revenue
            else:
                # No bots: normal calculation with 20% commission
                actual_prize = display_prize  # Same as display prize
                system_revenue = Decimal(total_players) * Decimal(stake_amount) * Decimal("0.2")
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

            if system_revenue > 0:
                SystemBalanceLedger.append_entry(
                    event_type='game_commission',
                    direction='credit',
                    amount=system_revenue,
                    game=game,
                    description=f'Game #{game.id} winner commission (20%).',
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
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
