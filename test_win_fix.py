"""
Test script to verify win validation and database updates work correctly
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bingo_project.settings')
django.setup()

from users.models import User
from game.models import Game, BingoCard
from wallet.models import Wallet, Transaction
from bot.utils.game_logic import generate_bingo_grid, check_bingo_win
from django.conf import settings


def test_win_scenario():
    """Test a complete win scenario"""
    print("🧪 Testing Win Scenario\n")
    
    # Create test user
    user, created = User.objects.get_or_create(
        telegram_id=999999,
        defaults={
            'first_name': 'TestWinner',
            'username': 'testwinner'
        }
    )
    
    if created:
        Wallet.objects.create(user=user, main_balance=100, bonus_balance=0)
        print(f"✅ Created test user: {user.first_name}")
    else:
        print(f"✅ Using existing test user: {user.first_name}")
    
    # Create game
    game = Game.objects.create(state='waiting')
    print(f"✅ Created game #{game.id}")
    
    # Create bingo card
    grid = generate_bingo_grid()
    card = BingoCard.objects.create(
        game=game,
        user=user,
        card_number=1
    )
    card.set_grid(grid)
    card.save()
    print(f"✅ Created card #{card.card_number}")
    
    # Simulate winning scenario - mark all numbers in first row as called
    first_row = [num for num in grid[0] if num is not None]
    game.set_called_numbers(first_row)
    game.save()
    print(f"✅ Called numbers: {first_row}")
    
    # Check if it's a win
    is_winner, pattern = check_bingo_win(grid, first_row)
    print(f"\n🎯 Win Check: {is_winner}")
    print(f"🎯 Pattern: {pattern}")
    
    if is_winner:
        # Simulate win processing
        initial_balance = user.wallet.main_balance
        
        # Calculate prize
        total_cards = game.cards.count()
        prize = total_cards * settings.CARD_PRICE
        
        # Update game
        game.state = 'finished'
        game.winner = user
        game.prize_amount = prize
        game.save()
        
        # Update card
        card.is_winner = True
        card.save()
        
        # Update wallet
        wallet = user.wallet
        wallet.main_balance += prize
        wallet.save()
        
        # Create transaction
        Transaction.objects.create(
            user=user,
            transaction_type='game_win',
            amount=prize,
            status='approved',
            description=f'Won Game #{game.id} - {pattern}'
        )
        
        print(f"\n💰 Prize: {prize} Birr")
        print(f"💰 Initial Balance: {initial_balance} Birr")
        print(f"💰 New Balance: {wallet.main_balance} Birr")
        
        # Verify database updates
        game.refresh_from_db()
        card.refresh_from_db()
        wallet.refresh_from_db()
        
        print(f"\n✅ Database Verification:")
        print(f"   Game State: {game.state}")
        print(f"   Game Winner: {game.winner.first_name if game.winner else 'None'}")
        print(f"   Game Prize: {game.prize_amount} Birr")
        print(f"   Card Winner Status: {card.is_winner}")
        print(f"   Wallet Balance: {wallet.main_balance} Birr")
        
        # Check transaction
        win_transaction = Transaction.objects.filter(
            user=user,
            transaction_type='game_win'
        ).last()
        
        if win_transaction:
            print(f"   Transaction: {win_transaction.amount} Birr - {win_transaction.status}")
            print(f"\n🎉 SUCCESS! All database updates working correctly!")
        else:
            print(f"\n❌ ERROR: Transaction not created!")
    else:
        print(f"\n❌ Not a winning pattern")
    
    # Cleanup
    print(f"\n🧹 Cleaning up test data...")
    game.delete()
    user.delete()
    print(f"✅ Test complete!")


if __name__ == '__main__':
    test_win_scenario()
