"""
Game Engine Management Command
Automatically starts games and calls numbers
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.conf import settings
from game.models import Game, BingoCard, SystemBalanceLedger
from users.models import User
from wallet.models import Wallet
from bot.utils.game_logic import get_next_number, check_bingo_win, generate_winning_grid_from_called_numbers
from decimal import Decimal
import time
import random


class Command(BaseCommand):
    help = 'Run the game engine to auto-start games and call numbers'
    BOT_TELEGRAM_ID_THRESHOLD = 9000000000
    MIN_REAL_USERS_TO_START = 2
    
    bot_users_added = {}  # Track which games have bot users added
    bot_win_targets = {}  # Track at which number each game's bot should win

    @staticmethod
    def game_stake(game):
        return int(getattr(game, 'stake_amount', settings.CARD_PRICE))

    def sync_missing_system_balance_entries(self):
        """Backfill ledger entries for finished games that have revenue but no ledger entry."""
        candidates = Game.objects.filter(state='finished', system_revenue__gt=0)
        for game in candidates:
            if SystemBalanceLedger.objects.filter(game=game).exists():
                continue

            event_type = 'game_commission' if game.winner_id else 'game_no_winner'
            idempotency_key = (
                f"game:{game.id}:winner_commission"
                if game.winner_id
                else f"game:{game.id}:no_winner"
            )

            SystemBalanceLedger.append_entry(
                event_type=event_type,
                direction='credit',
                amount=game.system_revenue,
                game=game,
                description=f'Engine auto-sync for finished Game #{game.id}.',
                metadata={
                    'auto_synced_by_engine': True,
                    'winner_id': game.winner_id,
                },
                idempotency_key=idempotency_key,
            )

            self.stdout.write(
                self.style.WARNING(
                    f'🔁 Backfilled missing ledger entry for Game #{game.id} ({game.system_revenue} Birr)'
                )
            )

    def create_bot_user(self, index):
        """Create a bot user"""
        bot_names = [
            "Abebe Bekele", "Kebede Alemu", "Almaz Tadesse", "Tigist Haile", "Dawit Tesfaye", 
            "Meron Girma", "Yonas Mulugeta", "Hanna Desta", "Samuel Getachew", "Rahel Assefa",
            "Biruk Lemma", "Selam Worku", "Daniel Negash", "Bethlehem Yohannes", "Yared Mekonnen",
            "Mahlet Tekle", "Elias Abera", "Sara Gebru", "Mulugeta Amare", "Tsion Kebede",
            "Fitsum Tadesse", "Mekdes Hailu", "Yosef Bekele", "Selamawit Tefera", "Amanuel Desta",
            "Hiwot Alemu", "Bereket Girma", "Eyerusalem Negash", "Yonatan Assefa", "Meseret Worku",
            "Getachew Lemma", "Senait Mekonnen", "Addis Tekle", "Liya Abera", "Henok Gebru",
            "Marta Amare", "Binyam Haile", "Kidist Tesfaye", "Yared Mulugeta", "Aster Getachew"
        ]
        
        bot_usernames = [
            "abebe_b", "kebede_a", "almaz_t", "tigist_h", "dawit_t",
            "meron_g", "yonas_m", "hanna_d", "samuel_g", "rahel_a",
            "biruk_l", "selam_w", "daniel_n", "bethlehem_y", "yared_m",
            "mahlet_t", "elias_a", "sara_g", "mulugeta_a", "tsion_k",
            "fitsum_t", "mekdes_h", "yosef_b", "selamawit_t", "amanuel_d",
            "hiwot_a", "bereket_g", "eyerusalem_n", "yonatan_a", "meseret_w",
            "getachew_l", "senait_m", "addis_t", "liya_a", "henok_g",
            "marta_a", "binyam_h", "kidist_t", "yared_mul", "aster_g"
        ]
        
        # Generate unique telegram_id for bot
        telegram_id = 9000000000 + index
        
        # Pick random name and username
        full_name = random.choice(bot_names)
        username = random.choice(bot_usernames)
        
        # Check if bot user already exists
        user, created = User.objects.get_or_create(
            telegram_id=telegram_id,
            defaults={
                'username': username,
                'first_name': full_name,
                'is_active': True,
            }
        )
        
        # Update username for existing users to randomize each game
        if not created:
            user.username = username
            user.first_name = full_name
            user.save()
        
        # Create wallet if doesn't exist
        if created:
            Wallet.objects.create(
                user=user,
                main_balance=1000,
                bonus_balance=0
            )
        
        return user

    def add_bot_users_to_game(self, game, count):
        """Add bot users to a game"""
        # Track real players before adding bots
        real_players = game.cards.filter(user__telegram_id__lt=9000000000).count()
        
        taken_cards = set(game.cards.values_list('card_number', flat=True))
        available_cards = [i for i in range(1, 401) if i not in taken_cards]
        
        if len(available_cards) < count:
            count = len(available_cards)
        
        selected_cards = random.sample(available_cards, count)
        
        for i, card_number in enumerate(selected_cards):
            bot_user = self.create_bot_user(game.id * 100 + i)
            
            # Create card for bot user
            BingoCard.objects.create(
                game=game,
                user=bot_user,
                card_number=card_number
            )
            
            self.stdout.write(f'🤖 Bot user {bot_user.first_name} joined game #{game.id} with card #{card_number}')
            time.sleep(1)  # Add 1 bot per second
        
        # Update game with bot tracking info
        game.has_bots = True
        game.real_players_count = real_players
        game.real_prize_amount = Decimal(real_players) * Decimal(self.game_stake(game)) * Decimal("0.8")
        game.save()
        
        self.stdout.write(
            self.style.WARNING(
                f'📊 Game #{game.id}: Real players: {real_players}, Real prize: {game.real_prize_amount} Birr'
            )
        )

    def check_bot_wins(self, game):
        """Force bot to win at the target number if bots were added"""
        called_number_entries = game.get_called_number_entries()
        called_numbers = [entry['number'] for entry in called_number_entries]
        
        # Only proceed if game has bots
        if not game.has_bots:
            return False
        
        # Get a random bot card to win
        bot_cards = list(game.cards.filter(user__telegram_id__gte=9000000000, is_winner=False))
        
        if not bot_cards:
            return False
        
        winning_card = random.choice(bot_cards)
        
        # Generate a winning grid from the called numbers with random pattern
        winning_grid, pattern_name = generate_winning_grid_from_called_numbers(called_numbers)
        
        if winning_grid:
            # Save the custom winning grid to the card
            winning_card.set_grid(winning_grid)
            
            # Verify it's actually a winning grid
            is_winner, verified_pattern = check_bingo_win(winning_grid, called_numbers)
            
            if not is_winner:
                self.stdout.write(
                    self.style.ERROR(
                        f'❌ Failed to generate valid winning grid for bot'
                    )
                )
                return False
            
            # Use the verified pattern name
            if verified_pattern:
                pattern_name = verified_pattern
        else:
            pattern_name = "Generated Pattern"
        
        # Calculate prizes and system revenue
        total_players = game.cards.count()
        real_players = game.real_players_count
        fake_players = total_players - real_players
        
        # Total pool (real + fake)
        stake_amount = self.game_stake(game)
        total_pool = Decimal(total_players) * Decimal(stake_amount)
        total_prize = total_pool * Decimal("0.8")  # 80% of total pool for display
        
        # Real players' pool
        real_pool = Decimal(real_players) * Decimal(stake_amount)
        real_prize = real_pool * Decimal("0.8")  # 80% to winner (actual amount)
        
        # When bot wins: system keeps entire real pool (100%)
        system_revenue = real_pool
        
        # Bot wins!
        game.state = 'finished'
        game.finished_at = timezone.now()
        game.winner = winning_card.user
        game.prize_amount = total_prize  # Display total prize (real + fake)
        game.system_revenue = system_revenue
        game.save()

        if system_revenue > 0:
            SystemBalanceLedger.append_entry(
                event_type='game_commission',
                direction='credit',
                amount=system_revenue,
                game=game,
                description=f'Game #{game.id} bot win settlement credited to system.',
                metadata={
                    'has_bots': True,
                    'real_players': int(real_players),
                    'fake_players': int(fake_players),
                    'real_prize': str(real_prize),
                    'display_prize': str(total_prize),
                },
                idempotency_key=f'game:{game.id}:winner_commission',
            )
        
        winning_card.is_winner = True
        winning_card.save()
        
        # Credit bot's wallet with real prize to WINNINGS balance
        wallet = winning_card.user.wallet
        wallet.winnings_balance += real_prize
        wallet.save()
        
        self.stdout.write(
            self.style.SUCCESS(
                f'🎉 Bot {winning_card.user.first_name} won Game #{game.id} after {len(called_numbers)} numbers!\n'
                f'   Pattern: {pattern_name}\n'
                f'   Real Players: {real_players} | Fake Players: {fake_players}\n'
                f'   Displayed Prize: {total_prize} Birr (80% of total pool)\n'
                f'   Actual Prize to Bot: {real_prize} Birr (80% of real pool)\n'
                f'   System Revenue: {system_revenue} Birr (100% of real pool)\n'
                f'   Winning Card: #{winning_card.card_number}'
            )
        )
        return True

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('🎮 Game Engine Started'))
        self.stdout.write('Monitoring games every second...\n')
        
        while True:
            try:
                self.sync_missing_system_balance_entries()

                # Check for games in waiting state that should start
                waiting_games = Game.objects.filter(state='waiting')
                
                for game in waiting_games:
                    # Check if waiting period has passed since creation
                    time_elapsed = (timezone.now() - game.created_at).total_seconds()
                    player_count = game.cards.count()
                    real_player_count = game.cards.filter(user__telegram_id__lt=self.BOT_TELEGRAM_ID_THRESHOLD).count()

                    # Safety cleanup: if a waiting game has only bots, remove them and reset bot flags.
                    if player_count > 0 and real_player_count == 0 and game.has_bots:
                        game.cards.filter(user__telegram_id__gte=self.BOT_TELEGRAM_ID_THRESHOLD).delete()
                        game.has_bots = False
                        game.real_players_count = 0
                        game.real_prize_amount = Decimal("0")
                        game.save(update_fields=['has_bots', 'real_players_count', 'real_prize_amount'])
                        self.bot_users_added.pop(game.id, None)
                        self.bot_win_targets.pop(game.id, None)
                        self.stdout.write(
                            self.style.WARNING(
                                f'🧹 Cleared bot-only waiting game #{game.id} before start checks.'
                            )
                        )
                        player_count = game.cards.count()
                    
                    # Start immediately if all 400 cards are selected
                    if player_count >= 400:
                        if player_count >= settings.GAME_MIN_PLAYERS and real_player_count >= self.MIN_REAL_USERS_TO_START:
                            game.state = 'playing'
                            game.started_at = timezone.now()
                            game.save()
                            
                            self.stdout.write(
                                self.style.SUCCESS(
                                    f'✅ Game #{game.id} STARTED IMMEDIATELY - All 400 cards selected! Players: {player_count}'
                                )
                            )
                        continue
                    
                    # Add bot users when countdown reaches 10 seconds and less than 5 players
                    remaining_time = settings.WAITING_TIME - time_elapsed
                    
                    if (
                        remaining_time <= 10
                        and player_count < 5
                        and real_player_count >= self.MIN_REAL_USERS_TO_START
                        and game.id not in self.bot_users_added
                    ):
                        bots_to_add = 10
                        self.stdout.write(
                            self.style.WARNING(
                                f'⚠️ Game #{game.id} has only {player_count} players. Adding {bots_to_add} bot users...'
                            )
                        )
                        self.add_bot_users_to_game(game, bots_to_add)
                        self.bot_users_added[game.id] = True
                        
                        # Set random win target between 16 and 20
                        win_target = random.randint(16, 20)
                        self.bot_win_targets[game.id] = win_target
                        self.stdout.write(
                            self.style.WARNING(
                                f'🎯 Bot will win at {win_target} numbers for Game #{game.id}'
                            )
                        )
                        
                        player_count = game.cards.count()  # Update count
                    
                    if time_elapsed >= settings.WAITING_TIME:
                        if player_count >= settings.GAME_MIN_PLAYERS and real_player_count >= self.MIN_REAL_USERS_TO_START:
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
                    real_player_count = game.cards.filter(user__telegram_id__lt=self.BOT_TELEGRAM_ID_THRESHOLD).count()
                    if real_player_count < self.MIN_REAL_USERS_TO_START:
                        game.state = 'waiting'
                        game.started_at = None
                        game.save(update_fields=['state', 'started_at'])
                        self.stdout.write(
                            self.style.WARNING(
                                f'⏸️ Reverted Game #{game.id} to waiting: real users below {self.MIN_REAL_USERS_TO_START}.'
                            )
                        )
                        continue

                    called_number_entries = game.get_called_number_entries()
                    called_numbers = [entry['number'] for entry in called_number_entries]
                    
                    # Check if bot should win (if game has bots and reached target)
                    win_target = self.bot_win_targets.get(game.id)
                    if game.has_bots and win_target and len(called_numbers) >= win_target:
                        # Bot should have won by now, force win
                        if self.check_bot_wins(game):
                            continue  # Game finished, move to next
                    
                    # Check if game reached max numbers without a winner
                    if len(called_numbers) >= settings.BINGO_NUMBER_MAX:
                        # Calculate system revenue - system keeps real pool when no winner
                        total_players = game.cards.count()
                        
                        if game.has_bots:
                            # Game has bots: system keeps only real pool
                            real_pool = Decimal(game.real_players_count) * Decimal(self.game_stake(game))
                            system_revenue = real_pool
                        else:
                            # No bots: system keeps entire pool
                            total_pool = Decimal(total_players) * Decimal(self.game_stake(game))
                            system_revenue = total_pool
                        
                        game.state = 'finished'
                        game.finished_at = timezone.now()
                        game.system_revenue = system_revenue
                        game.save()

                        if system_revenue > 0:
                            SystemBalanceLedger.append_entry(
                                event_type='game_no_winner',
                                direction='credit',
                                amount=system_revenue,
                                game=game,
                                description=f'Game #{game.id} ended with no winner; full settlement credited to system.',
                                metadata={
                                    'has_bots': bool(game.has_bots),
                                    'total_players': int(total_players),
                                    'real_players': int(game.real_players_count) if game.has_bots else int(total_players),
                                },
                                idempotency_key=f'game:{game.id}:no_winner',
                            )
                        
                        self.stdout.write(
                            self.style.WARNING(
                                f'⚠️ Game #{game.id} ended - reached max numbers ({settings.BINGO_NUMBER_MAX}) without winner\n'
                                f'   System Revenue: {system_revenue} Birr (real pool - no winner)'
                            )
                        )
                        continue
                    
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
