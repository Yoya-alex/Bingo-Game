"""
Game Engine Management Command
Automatically starts games and calls numbers
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.conf import settings
from game.models import Game
from bot.utils.game_logic import get_next_number
import time


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
                    # Check if waiting period has passed since creation
                    time_elapsed = (timezone.now() - game.created_at).total_seconds()
                    
                    if time_elapsed >= settings.WAITING_TIME:
                        player_count = game.cards.count()
                        if player_count >= settings.GAME_MIN_PLAYERS:
                            # Start the game
                            game.state = 'playing'
                            game.started_at = timezone.now()
                            game.save()
                            
                            self.stdout.write(
                                self.style.SUCCESS(
                                    f'✅ Game #{game.id} STARTED with {player_count} players'
                                )
                            )
                
                # Check for games in playing state that need number calling
                playing_games = Game.objects.filter(state='playing')
                
                for game in playing_games:
                    called_number_entries = game.get_called_number_entries()
                    called_numbers = [entry['number'] for entry in called_number_entries]
                    
                    # Check if we should call a new number based on configured interval
                    if game.started_at:
                        time_since_start = (timezone.now() - game.started_at).total_seconds()
                        expected_calls = int(time_since_start / settings.NUMBER_CALL_INTERVAL)
                        
                        if len(called_numbers) < expected_calls and len(called_numbers) < settings.BINGO_NUMBER_MAX:
                            # Call a new number
                            next_num = get_next_number(called_numbers)
                            if next_num:
                                called_number_entries.append({
                                    'number': next_num,
                                    'called_at': timezone.now().isoformat(),
                                })
                                game.set_called_numbers(called_number_entries)
                                game.save()
                                
                                self.stdout.write(
                                    f'📢 Game #{game.id}: Called number {next_num} '
                                    f'({len(called_number_entries)}/{settings.BINGO_NUMBER_MAX})'
                                )
                
                # Sleep for 1 second before next check
                time.sleep(1)
                
            except KeyboardInterrupt:
                self.stdout.write(self.style.WARNING('\n⏹ Game Engine Stopped'))
                break
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'❌ Error: {str(e)}'))
                time.sleep(1)
