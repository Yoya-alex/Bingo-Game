"""
Test script to verify game flow
Run this to test the complete game cycle
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bingo_project.settings')
django.setup()

from game.models import Game, BingoCard
from users.models import User
from django.utils import timezone

def test_game_flow():
    print("=" * 60)
    print("🧪 TESTING GAME FLOW")
    print("=" * 60)
    print()
    
    # Get test user
    try:
        user = User.objects.get(telegram_id=5217880016)
        print(f"✅ Found test user: {user.first_name}")
    except User.DoesNotExist:
        print("❌ Test user not found. Please start the bot first.")
        return
    
    # Check for active game
    game = Game.objects.filter(state='waiting').first()
    if not game:
        print("📝 Creating new game...")
        game = Game.objects.create(state='waiting')
        print(f"✅ Game #{game.id} created")
    else:
        print(f"✅ Found active game #{game.id}")
    
    # Check game age
    age = (timezone.now() - game.created_at).total_seconds()
    print(f"⏱  Game age: {int(age)} seconds")
    print(f"⏱  Countdown: {max(0, int(25 - age))} seconds")
    
    # Check players
    player_count = game.cards.count()
    print(f"👥 Players: {player_count}")
    
    # Check if user has card
    user_card = game.cards.filter(user=user).first()
    if user_card:
        print(f"🎴 User has card #{user_card.card_number}")
    else:
        print("⚠️  User has no card yet")
    
    # Check game state
    print(f"🎮 Game state: {game.state.upper()}")
    
    if game.state == 'playing':
        called = game.get_called_numbers()
        print(f"📢 Called numbers: {len(called)}/75")
        if called:
            print(f"   Last 3: {called[-3:]}")
    
    print()
    print("=" * 60)
    print("🔗 Test URLs:")
    print(f"   Lobby: http://localhost:8000/game/lobby/5217880016/")
    if user_card:
        print(f"   Play:  http://localhost:8000/game/play/5217880016/{game.id}/")
    print("=" * 60)

if __name__ == '__main__':
    test_game_flow()
