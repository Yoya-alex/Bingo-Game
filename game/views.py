from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.cache import never_cache
from django.conf import settings
from django.utils import timezone
from django.db import transaction
from decimal import Decimal
from users.models import User
from game.models import Game, BingoCard
from wallet.models import Transaction
import json


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

        if game.state == 'playing' and game.cards.count() < settings.GAME_MIN_PLAYERS:
            game.state = 'waiting'
            game.started_at = None
            game.save()
            return game

        if game.state == 'playing' and len(called_numbers) >= settings.BINGO_NUMBER_MAX:
            game.state = 'finished'
            if not game.finished_at:
                game.finished_at = timezone.now()
            game.save()
            return game

        if game.state != 'waiting':
            return game

        time_elapsed = (timezone.now() - game.created_at).total_seconds()
        if time_elapsed >= settings.WAITING_TIME and game.cards.count() >= settings.GAME_MIN_PLAYERS:
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

    return redirect(f"{settings.REACT_APP_URL}/lobby/{telegram_id}")


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
        
        user = User.objects.select_related('wallet').get(telegram_id=telegram_id)
        wallet = user.wallet
        
        if card_number < 1 or card_number > settings.CARD_COUNT:
            return JsonResponse({'error': 'Invalid card number'}, status=400)

        user_card = (
            BingoCard.objects.select_related('game')
            .filter(user=user, game__state='waiting')
            .order_by('-game__created_at')
            .first()
        )

        if user_card:
            game = user_card.game
        else:
            # Use a waiting game that already has participants, otherwise create a fresh one.
            game = Game.objects.filter(state='waiting', cards__isnull=False).order_by('-created_at').first()
            if not game:
                game = Game.objects.create(state='waiting')

        # Check if card is available for this user
        if game.cards.filter(card_number=card_number).exclude(user=user).exists():
            return JsonResponse({'error': 'Card already taken'}, status=400)
        
        if user_card:
            user_card.card_number = card_number
            user_card.save()
            card = user_card
        else:
            # Check balance
            if wallet.total_balance < settings.CARD_PRICE:
                return JsonResponse({'error': 'Insufficient balance'}, status=400)

            # Deduct balance
            if wallet.main_balance >= settings.CARD_PRICE:
                wallet.main_balance -= settings.CARD_PRICE
            else:
                remaining = settings.CARD_PRICE - wallet.main_balance
                wallet.main_balance = 0
                wallet.bonus_balance -= remaining
            wallet.save()

            # Log transaction
            Transaction.objects.create(
                user=user,
                transaction_type='game_entry',
                amount=settings.CARD_PRICE,
                status='approved',
                description=f'Game #{game.id} - Card #{card_number}'
            )

            # Create card
            card = BingoCard.objects.create(
                game=game,
                user=user,
                card_number=card_number
            )
        
        return JsonResponse({
            'success': True,
            'game_id': game.id,
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
        time_elapsed = (timezone.now() - game.created_at).total_seconds()
        countdown = max(0, int(settings.WAITING_TIME - time_elapsed))
        winner_card = get_winner_card_payload(game)

        return JsonResponse({
            'game_id': game.id,
            'state': game.state,
            'server_time': timezone.now().isoformat(),
            'number_call_interval': settings.NUMBER_CALL_INTERVAL,
            'countdown': countdown,
            'total_players': game.cards.count(),
            'called_numbers': game.get_called_number_entries(),
            'winner': game.winner.first_name if game.winner else None,
            'prize_amount': float(game.prize_amount) if game.prize_amount else 0,
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

    def get_active_game():
        user_waiting_game = (
            Game.objects.filter(state='waiting', cards__user=user)
            .order_by('-created_at')
            .first()
        )
        if user_waiting_game:
            return user_waiting_game

        waiting_game = Game.objects.filter(state='waiting', cards__isnull=False).order_by('-created_at').first()
        playing_game = Game.objects.filter(state='playing').order_by('-created_at').first()
        return waiting_game or playing_game

    game = get_active_game()
    if game:
        game = ensure_game_started(game.id)
        if game.state == 'finished':
            game = get_active_game()
            if game:
                game = ensure_game_started(game.id)

    if not game:
        return JsonResponse({
            'user': {
                'first_name': user.first_name,
                'telegram_id': user.telegram_id,
            },
            'game': {
                'id': None,
                'state': 'waiting',
            },
            'server_time': timezone.now().isoformat(),
            'number_call_interval': settings.NUMBER_CALL_INTERVAL,
            'wallet_balance': float(user.wallet.total_balance),
            'taken_cards': [],
            'all_numbers': list(range(1, settings.CARD_COUNT + 1)),
            'total_players': 0,
            'available_cards': settings.CARD_COUNT,
            'stake': settings.CARD_PRICE,
            'countdown': 0,
            'called_numbers': [],
            'winner': None,
            'prize_amount': 0,
            'winner_card': None,
            'user_card': None,
        })

    taken_cards = list(game.cards.values_list('card_number', flat=True))
    time_elapsed = (timezone.now() - game.created_at).total_seconds()
    countdown = max(0, int(settings.WAITING_TIME - time_elapsed))
    total_players = game.cards.count()
    winner_card = get_winner_card_payload(game)
    user_card = game.cards.filter(user=user).first()

    return JsonResponse({
        'user': {
            'first_name': user.first_name,
            'telegram_id': user.telegram_id,
        },
        'game': {
            'id': game.id,
            'state': game.state,
        },
        'server_time': timezone.now().isoformat(),
        'number_call_interval': settings.NUMBER_CALL_INTERVAL,
        'wallet_balance': float(user.wallet.total_balance),
        'taken_cards': taken_cards,
        'all_numbers': list(range(1, settings.CARD_COUNT + 1)),
        'total_players': total_players,
        'available_cards': settings.CARD_COUNT - len(taken_cards),
        'stake': settings.CARD_PRICE,
        'countdown': countdown,
        'called_numbers': game.get_called_number_entries(),
        'winner': game.winner.first_name if game.winner else None,
        'prize_amount': float(game.prize_amount) if game.prize_amount else 0,
        'winner_card': winner_card,
        'user_card': {
            'card_number': user_card.card_number,
            'grid': user_card.get_grid(),
        } if user_card else None,
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
    if game.prize_amount == 0:
        prize_amount = Decimal(total_players) * Decimal(settings.CARD_PRICE) * Decimal("0.8")
    else:
        prize_amount = game.prize_amount

    time_elapsed = (timezone.now() - game.created_at).total_seconds()
    countdown = max(0, int(settings.WAITING_TIME - time_elapsed))
    winner_card = get_winner_card_payload(game)

    return JsonResponse({
        'user': {
            'first_name': user.first_name,
            'telegram_id': user.telegram_id,
        },
        'game': {
            'id': game.id,
            'state': game.state,
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


@csrf_exempt
def mark_number_api(request):
    """Mark any called number on the player's bingo card."""
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

        # Get all called numbers (not just the current one)
        called_numbers = [entry['number'] for entry in called_number_entries]
        
        # Check if the number has been called
        if number not in called_numbers:
            return JsonResponse({'error': 'This number has not been called yet.'}, status=400)

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
        if game.state == 'waiting' and game.cards.count() >= settings.GAME_MIN_PLAYERS:
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
            
            # Total prize for display (includes fake players)
            total_pool = Decimal(total_players) * Decimal(settings.CARD_PRICE)
            display_prize = total_pool * Decimal("0.8")  # 80% of total pool
            
            if game.has_bots:
                # Game has bots: winner gets only real players' contribution
                real_players = game.real_players_count
                
                # Real players' pool
                real_pool = Decimal(real_players) * Decimal(settings.CARD_PRICE)
                actual_prize = real_pool * Decimal("0.8")  # 80% to winner (actual amount)
                real_commission = real_pool * Decimal("0.2")  # 20% commission
                
                # System revenue: only commission from real players (no fake pool)
                system_revenue = real_commission
                game.system_revenue = system_revenue
            else:
                # No bots: normal calculation with 20% commission
                actual_prize = display_prize  # Same as display prize
                system_revenue = Decimal(total_players) * Decimal(settings.CARD_PRICE) * Decimal("0.2")
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
