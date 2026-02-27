from django.db import models
from django.utils import timezone
from users.models import User
import json
from bot.utils.game_logic import generate_bingo_card


class Game(models.Model):
    GAME_STATES = [
        ('no_game', 'No Game'),
        ('waiting', 'Waiting'),
        ('playing', 'Playing'),
        ('finished', 'Finished'),
    ]
    
    state = models.CharField(max_length=20, choices=GAME_STATES, default='no_game')
    created_at = models.DateTimeField(default=timezone.now)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    winner = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='won_games')
    prize_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    called_numbers = models.TextField(default='[]')
    has_bots = models.BooleanField(default=False)
    real_players_count = models.IntegerField(default=0)
    real_prize_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    system_revenue = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    class Meta:
        db_table = 'games'
        ordering = ['-created_at']
    
    def get_called_number_entries(self):
        try:
            raw_values = json.loads(self.called_numbers)
        except Exception:
            raw_values = []

        entries = []
        for item in raw_values:
            if isinstance(item, dict):
                number = item.get('number')
                called_at = item.get('called_at')
            else:
                number = item
                called_at = None

            try:
                normalized_number = int(number)
            except (TypeError, ValueError):
                continue

            entries.append({
                'number': normalized_number,
                'called_at': called_at,
            })
        return entries

    def get_called_numbers(self):
        return [entry['number'] for entry in self.get_called_number_entries()]
    
    def set_called_numbers(self, numbers):
        normalized = []
        for item in numbers:
            if isinstance(item, dict):
                number = item.get('number')
                called_at = item.get('called_at')
            else:
                number = item
                called_at = None

            try:
                normalized_number = int(number)
            except (TypeError, ValueError):
                continue

            normalized.append({
                'number': normalized_number,
                'called_at': called_at,
            })

        self.called_numbers = json.dumps(normalized)
    
    def __str__(self):
        return f"Game {self.id} - {self.state}"


class BingoCard(models.Model):
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name='cards')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='bingo_cards')
    card_number = models.IntegerField()
    marked_positions = models.TextField(default='[]')
    is_winner = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)
    custom_grid = models.TextField(null=True, blank=True)  # For bot-generated winning grids
    
    class Meta:
        db_table = 'bingo_cards'
        unique_together = ['game', 'card_number']
    
    def get_grid(self):
        # If custom grid exists (for bot winners), use it
        if self.custom_grid:
            try:
                return json.loads(self.custom_grid)
            except:
                pass
        return generate_bingo_card(self.card_number)
    
    def set_grid(self, grid_data):
        self.custom_grid = json.dumps(grid_data)
    
    def get_marked_positions(self):
        return json.loads(self.marked_positions)
    
    def set_marked_positions(self, positions):
        self.marked_positions = json.dumps(positions)
    
    def __str__(self):
        return f"Card {self.card_number} - Game {self.game.id} - {self.user.first_name}"
