from django.contrib import admin
from django.utils.html import format_html
from .models import Game, BingoCard, SystemBalance, SystemBalanceLedger


@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    list_display = [
        'id', 
        'state', 
        'get_player_info', 
        'get_winner_info',
        'get_prize_info',
        'has_bots_display',
        'created_at'
    ]
    list_filter = ['state', 'has_bots', 'created_at']
    readonly_fields = ['created_at', 'started_at', 'finished_at']
    
    def get_player_info(self, obj):
        total = obj.cards.count()
        if obj.has_bots:
            real = obj.real_players_count
            fake = total - real
            return format_html(
                '<span style="color: green;">Real: {}</span> | '
                '<span style="color: orange;">Fake: {}</span> | '
                '<strong>Total: {}</strong>',
                real, fake, total
            )
        return f'{total} players'
    get_player_info.short_description = 'Players'
    
    def get_winner_info(self, obj):
        if not obj.winner:
            return '-'
        
        is_bot = obj.winner.telegram_id >= 9000000000
        winner_type = '🤖 Bot' if is_bot else '👤 Real User'
        
        return format_html(
            '{}<br/><small>{}</small>',
            obj.winner.first_name,
            winner_type
        )
    get_winner_info.short_description = 'Winner'
    
    def get_prize_info(self, obj):
        if obj.has_bots:
            return format_html(
                '<strong>Total: {} Birr</strong><br/>'
                '<small style="color: green;">Real Prize: {} Birr</small>',
                obj.prize_amount,
                obj.real_prize_amount
            )
        return f'{obj.prize_amount} Birr'
    get_prize_info.short_description = 'Prize'
    
    def has_bots_display(self, obj):
        if obj.has_bots:
            return format_html('<span style="color: orange;">✓ Yes</span>')
        return format_html('<span style="color: green;">✗ No</span>')
    has_bots_display.short_description = 'Has Bots'
    
    fieldsets = (
        ('Game Info', {
            'fields': ('state', 'winner', 'prize_amount')
        }),
        ('Bot Tracking', {
            'fields': ('has_bots', 'real_players_count', 'real_prize_amount'),
            'classes': ('collapse',)
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
    list_display = ['card_number', 'game', 'get_user_info', 'is_winner', 'created_at']
    list_filter = ['is_winner', 'game__state', 'created_at']
    search_fields = ['user__first_name', 'user__username', 'card_number']
    readonly_fields = ['created_at']
    
    def get_user_info(self, obj):
        is_bot = obj.user.telegram_id >= 9000000000
        user_type = '🤖' if is_bot else '👤'
        return format_html(
            '{} {}',
            user_type,
            obj.user.first_name
        )
    get_user_info.short_description = 'User'


@admin.register(SystemBalance)
class SystemBalanceAdmin(admin.ModelAdmin):
    list_display = ['id', 'balance', 'updated_at']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(SystemBalanceLedger)
class SystemBalanceLedgerAdmin(admin.ModelAdmin):
    list_display = [
        'id',
        'event_type',
        'direction',
        'amount',
        'balance_before',
        'balance_after',
        'game',
        'created_at',
    ]
    list_filter = ['event_type', 'direction', 'created_at']
    search_fields = ['description', 'idempotency_key', 'game__id']
    readonly_fields = [
        'event_type',
        'direction',
        'amount',
        'balance_before',
        'balance_after',
        'game',
        'description',
        'metadata',
        'idempotency_key',
        'created_at',
    ]
