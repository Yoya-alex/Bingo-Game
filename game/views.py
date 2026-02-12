from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.utils import timezone
from users.models import User
from game.models import Game, BingoCard
from wallet.models import Transaction
import json


def game_lobby(request, telegram_id):
    """Game lobby - show 80 cards table"""
    try:
        user = User.objects.select_related('wallet').get(telegram_id=telegram_id)
    except User.DoesNotExist:
        return render(request, 'game/error.html', {
            'error': 'User not found. Please start the bot first.'
        })
    
    # Get or create active game
    game = Game.objects.filter(state='waiting').first()
    if not game:
        game = Game.objects.create(state='waiting')
    
    # Check if user already has a card
    user_card = game.cards.filter(user=user).first()
    if user_card:
        return redirect('game_play', telegram_id=telegram_id, game_id=game.id)
    
    # Get taken cards (1-80)
    taken_cards = list(game.cards.values_list('card_number', flat=True))
    
    context = {
        'user': user,
        'game': game,
        'wallet': user.wallet,
        'taken_cards': taken_cards,
        'card_price': settings.CARD_PRICE,
        'total_players': game.cards.count(),
        'total_games': Game.objects.count(),
    }
    
    return render(request, 'game/lobby.html', context)


def game_play(request, telegram_id, game_id):
    """Game play screen - show user's bingo card"""
    try:
        user = User.objects.get(telegram_id=telegram_id)
        game = get_object_or_404(Game, id=game_id)
        user_card = get_object_or_404(BingoCard, game=game, user=user)
    except User.DoesNotExist:
        return render(request, 'game/error.html', {
            'error': 'User not found.'
        })
    
    # Get grid and game info
    grid = user_card.get_grid()
    called_numbers = game.get_called_numbers()
    marked_positions = user_card.get_marked_positions()
    total_players = game.cards.count()
    prize_amount = total_players * settings.CARD_PRICE if game.prize_amount == 0 else game.prize_amount
    
    context = {
        'user': user,
        'game': game,
        'card': user_card,
        'grid': grid,
        'called_numbers': called_numbers,
        'marked_positions': marked_positions,
        'total_players': total_players,
        'prize_amount': prize_amount,
    }
    
    return render(request, 'game/play.html', context)


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
        
        # Get active game
        game = Game.objects.filter(state='waiting').first()
        if not game:
            return JsonResponse({'error': 'No active game'}, status=400)
        
        # Check if card is available
        if game.cards.filter(card_number=card_number).exists():
            return JsonResponse({'error': 'Card already taken'}, status=400)
        
        # Check if user already has a card
        if game.cards.filter(user=user).exists():
            return JsonResponse({'error': 'You already have a card'}, status=400)
        
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
        
        # Generate bingo grid
        from bot.utils.game_logic import generate_bingo_grid
        grid = generate_bingo_grid()
        
        # Create card
        card = BingoCard.objects.create(
            game=game,
            user=user,
            card_number=card_number
        )
        card.set_grid(grid)
        card.save()
        
        return JsonResponse({
            'success': True,
            'game_id': game.id,
            'card_number': card_number,
            'redirect_url': f'/game/play/{telegram_id}/{game.id}/'
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
def game_status_api(request, game_id):
    """API endpoint to get game status (for real-time updates)"""
    try:
        game = get_object_or_404(Game, id=game_id)
        
        # Calculate countdown
        time_elapsed = (timezone.now() - game.created_at).total_seconds()
        countdown = max(0, int(25 - time_elapsed))
        
        return JsonResponse({
            'game_id': game.id,
            'state': game.state,
            'countdown': countdown,
            'total_players': game.cards.count(),
            'called_numbers': game.get_called_numbers(),
            'winner': game.winner.first_name if game.winner else None,
            'prize_amount': float(game.prize_amount) if game.prize_amount else 0,
        })
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
        
        # Auto-transition to playing if still waiting and has players
        if game.state == 'waiting' and game.cards.count() > 0:
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
        
        is_winner, pattern = check_bingo_win(grid, called_numbers)
        
        if is_winner:
            # Calculate prize
            total_players = game.cards.count()
            prize = total_players * settings.CARD_PRICE
            
            # Update game state
            game.state = 'finished'
            game.finished_at = timezone.now()
            game.winner = user
            game.prize_amount = prize
            game.save()
            
            # Mark card as winner
            card.is_winner = True
            card.save()
            
            # Credit winner's wallet
            wallet = user.wallet
            wallet.main_balance += prize
            wallet.save()
            
            # Log transaction
            Transaction.objects.create(
                user=user,
                transaction_type='game_win',
                amount=prize,
                status='approved',
                description=f'Won Game #{game.id} - {pattern}'
            )
            
            return JsonResponse({
                'success': True,
                'winner': True,
                'pattern': pattern,
                'prize': float(prize),
                'message': f'🎉 BINGO! You won {prize} Birr!'
            })
        else:
            return JsonResponse({
                'success': True,
                'winner': False,
                'message': '❌ Not a valid BINGO yet. Keep playing!'
            })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
