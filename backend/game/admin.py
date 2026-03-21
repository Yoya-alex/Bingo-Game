from django.contrib import admin
from django.utils.html import format_html
from .models import (
    Game,
    BingoCard,
    LiveEvent,
    MissionTemplate,
    PromoCode,
    PromoCodeRedemption,
    RewardSafetyPolicy,
    Season,
    SystemBalance,
    SystemBalanceLedger,
    UserMissionProgress,
    UserRewardWindow,
    UserStreak,
)


@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    list_display = [
        'id', 
        'stake_amount',
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
            'fields': ('state', 'stake_amount', 'winner', 'prize_amount')
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


@admin.register(RewardSafetyPolicy)
class RewardSafetyPolicyAdmin(admin.ModelAdmin):
    list_display = ['id', 'daily_reward_cap', 'min_seconds_between_rewards', 'max_reward_redemptions_per_hour', 'updated_at']


@admin.register(UserRewardWindow)
class UserRewardWindowAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'reward_date', 'reward_total', 'redemption_count', 'last_reward_at']
    list_filter = ['reward_date']
    search_fields = ['user__first_name', 'user__username', 'user__telegram_id']


@admin.register(PromoCode)
class PromoCodeAdmin(admin.ModelAdmin):
    list_display = ['code', 'tier', 'reward_amount', 'reward_balance', 'is_active', 'is_visible_in_frontend', 'starts_at', 'ends_at']
    list_filter = ['tier', 'reward_balance', 'is_active', 'is_visible_in_frontend', 'starts_at']
    search_fields = ['code', 'title']


@admin.register(PromoCodeRedemption)
class PromoCodeRedemptionAdmin(admin.ModelAdmin):
    list_display = ['id', 'promo_code', 'user', 'amount', 'created_at']
    list_filter = ['promo_code', 'created_at']
    search_fields = ['promo_code__code', 'user__first_name', 'user__username', 'user__telegram_id']


@admin.register(MissionTemplate)
class MissionTemplateAdmin(admin.ModelAdmin):
    list_display = ['key', 'title', 'mission_type', 'period', 'target_value', 'reward_amount', 'reward_balance', 'is_active', 'sort_order']
    list_filter = ['mission_type', 'period', 'reward_balance', 'is_active']
    search_fields = ['key', 'title', 'description']


@admin.register(UserMissionProgress)
class UserMissionProgressAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'mission', 'period_start', 'progress_value', 'reward_amount', 'completed_at', 'claimed_at']
    list_filter = ['mission__period', 'period_start', 'claimed_at']
    search_fields = ['user__first_name', 'user__username', 'mission__key', 'mission__title']


@admin.register(UserStreak)
class UserStreakAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'current_streak', 'best_streak', 'streak_protect_tokens', 'last_active_date', 'updated_at']
    search_fields = ['user__first_name', 'user__username', 'user__telegram_id']


@admin.register(LiveEvent)
class LiveEventAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'event_type', 'bonus_multiplier', 'starts_at', 'ends_at', 'is_active', 'auto_announce', 'announced_at']
    list_filter = ['event_type', 'is_active', 'auto_announce', 'starts_at']
    search_fields = ['name', 'description']


@admin.register(Season)
class SeasonAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'starts_at', 'ends_at', 'is_active', 'top_1_reward', 'top_2_reward', 'top_3_reward', 'participation_reward']
    list_filter = ['is_active', 'starts_at']
    search_fields = ['name']
