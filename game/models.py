from django.db import models
from django.utils import timezone
from users.models import User
import json


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
    
    class Meta:
        db_table = 'games'
        ordering = ['-created_at']
    
    def get_called_numbers(self):
        return json.loads(self.called_numbers)
    
    def set_called_numbers(self, numbers):
        self.called_numbers = json.dumps(numbers)
    
    def __str__(self):
        return f"Game {self.id} - {self.state}"


class BingoCard(models.Model):
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name='cards')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='bingo_cards')
    card_number = models.IntegerField()
    grid = models.TextField()
    marked_positions = models.TextField(default='[]')
    is_winner = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)
    
    class Meta:
        db_table = 'bingo_cards'
        unique_together = ['game', 'card_number']
    
    def get_grid(self):
        return json.loads(self.grid)
    
    def set_grid(self, grid_data):
        self.grid = json.dumps(grid_data)
    
    def get_marked_positions(self):
        return json.loads(self.marked_positions)
    
    def set_marked_positions(self, positions):
        self.marked_positions = json.dumps(positions)
    
    def __str__(self):
        return f"Card {self.card_number} - Game {self.game.id} - {self.user.first_name}"
