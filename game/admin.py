from django.contrib import admin
from .models import Game, BingoCard


@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    list_display = ['id', 'state', 'get_player_count', 'winner', 'prize_amount', 'created_at']
    list_filter = ['state', 'created_at']
    readonly_fields = ['created_at', 'started_at', 'finished_at']
    
    def get_player_count(self, obj):
        return obj.cards.count()
    get_player_count.short_description = 'Players'
    
    fieldsets = (
        ('Game Info', {
            'fields': ('state', 'winner', 'prize_amount')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'started_at', 'finished_at')
        }),
        ('Called Numbers', {
            'fields': ('called_numbers',),
            'classes': ('collapse',)
        }),
    )


@admin.register(BingoCard)
class BingoCardAdmin(admin.ModelAdmin):
    list_display = ['card_number', 'game', 'user', 'is_winner', 'created_at']
    list_filter = ['is_winner', 'game__state', 'created_at']
    search_fields = ['user__first_name', 'user__username', 'card_number']
    readonly_fields = ['created_at']
