"""
Game Engine Management Command
Automatically starts games and calls numbers
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from game.models import Game
from bot.utils.game_logic import get_next_number
import time
from datetime import timedelta


class Command(BaseCommand):
    help = 'Run the game engine to auto-start games and call numbers'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('🎮 Game Engine Started'))
        self.stdout.write('Monitoring games every second...\n')
        
        while True:
            try:
                # Check for games in waiting state that should start
                waiting_games = Game.objects.filter(state='waiting')
                
                for game in waiting_games:
                    # Check if 25 seconds have passed since creation
                    time_elapsed = (timezone.now() - game.created_at).total_seconds()
                    
                    if time_elapsed >= 25:
                        # Start the game
                        game.state = 'playing'
                        game.started_at = timezone.now()
                        game.save()
                        
                        player_count = game.cards.count()
                        self.stdout.write(
                            self.style.SUCCESS(
                                f'✅ Game #{game.id} STARTED with {player_count} players'
                            )
                        )
                
                # Check for games in playing state that need number calling
                playing_games = Game.objects.filter(state='playing')
                
                for game in playing_games:
                    called_numbers = game.get_called_numbers()
                    
                    # Check if we should call a new number (every 3 seconds)
                    if game.started_at:
                        time_since_start = (timezone.now() - game.started_at).total_seconds()
                        expected_calls = int(time_since_start / 3)
                        
                        if len(called_numbers) < expected_calls and len(called_numbers) < 75:
                            # Call a new number
                            next_num = get_next_number(called_numbers)
                            if next_num:
                                called_numbers.append(next_num)
                                game.set_called_numbers(called_numbers)
                                game.save()
                                
                                self.stdout.write(
                                    f'📢 Game #{game.id}: Called number {next_num} '
                                    f'({len(called_numbers)}/75)'
                                )
                
                # Sleep for 1 second before next check
                time.sleep(1)
                
            except KeyboardInterrupt:
                self.stdout.write(self.style.WARNING('\n⏹ Game Engine Stopped'))
                break
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'❌ Error: {str(e)}'))
                time.sleep(1)
