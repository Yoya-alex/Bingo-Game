import csv
from datetime import timedelta
from decimal import Decimal

from django.contrib import admin
from django.contrib import messages
from django.db.models import Q, Sum
from django.http import HttpResponse
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html, format_html_join
from django.utils import timezone
from users.models import User
from .models import (
    BusinessRuleSettings,
    BusinessRuleSettingsAudit,
    Game,
    GameEngineSettings,
    BingoCard,
    LiveEvent,
    MissionTemplate,
    PromoCode,
    PromoCodeRedemption,
    PromoVerificationRequest,
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
        'get_active_users',
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

    def get_active_users(self, obj):
        if obj.state not in ('waiting', 'playing'):
            return '-'

        cards = list(
            obj.cards.select_related('user').order_by('created_at')[:9]
        )
        if not cards:
            return 'No active users'

        entries = []
        for card in cards[:8]:
            user = card.user
            username = f" (@{user.username})" if user and user.username else ''
            entries.append(f"#{card.card_number} - {user.first_name}{username}")

        if len(cards) > 8:
            entries.append('...')

        return format_html_join('<br/>', '{}', ((entry,) for entry in entries))
    get_active_users.short_description = 'Active Users'
    
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
    list_display = ['id', 'balance', 'balance_health', 'analysis_page', 'updated_at']
    readonly_fields = ['created_at', 'updated_at']

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                'analysis/',
                self.admin_site.admin_view(self.analysis_view),
                name='game_systembalance_analysis',
            ),
            path(
                'analysis/export/',
                self.admin_site.admin_view(self.analysis_export_view),
                name='game_systembalance_analysis_export',
            ),
        ]
        return custom_urls + urls

    @staticmethod
    def _sum_amount(queryset):
        return queryset.aggregate(total=Sum('amount')).get('total') or Decimal('0.00')

    @staticmethod
    def _to_money(value):
        return Decimal(value).quantize(Decimal('0.01'))

    def _build_analysis_context(self, days):
        policy = RewardSafetyPolicy.get_active()
        system_balance, _ = SystemBalance.objects.get_or_create(pk=1)

        today = timezone.localdate()
        start_date = today - timedelta(days=days - 1)
        ledger = SystemBalanceLedger.objects.filter(created_at__date__gte=start_date)

        inflow_total = self._sum_amount(ledger.filter(direction='credit'))
        outflow_total = self._sum_amount(ledger.filter(direction='debit'))
        net_total = inflow_total - outflow_total

        reward_outflow_total = self._sum_amount(
            ledger.filter(direction='debit', event_type='reward_payout')
        )

        promo_filter = (
            Q(metadata__reward_description__icontains='Promo code')
            | Q(description__icontains='Promo code')
        )
        mission_filter = (
            Q(metadata__reward_description__icontains='Mission ')
            | Q(description__icontains='Mission ')
        )

        promo_reward_total = self._sum_amount(
            ledger.filter(direction='debit', event_type='reward_payout').filter(promo_filter)
        )
        mission_reward_total = self._sum_amount(
            ledger.filter(direction='debit', event_type='reward_payout').filter(mission_filter)
        )
        other_reward_total = reward_outflow_total - promo_reward_total - mission_reward_total
        if other_reward_total < 0:
            other_reward_total = Decimal('0.00')

        day_count = Decimal(str(days))
        avg_daily_inflow = inflow_total / day_count
        avg_daily_outflow = outflow_total / day_count
        avg_daily_reward_outflow = reward_outflow_total / day_count
        avg_daily_non_reward_outflow = avg_daily_outflow - avg_daily_reward_outflow
        if avg_daily_non_reward_outflow < 0:
            avg_daily_non_reward_outflow = Decimal('0.00')

        sustainability_ratio = None
        if avg_daily_outflow > 0:
            sustainability_ratio = avg_daily_inflow / avg_daily_outflow

        daily_deficit = avg_daily_outflow - avg_daily_inflow
        if daily_deficit < 0:
            daily_deficit = Decimal('0.00')

        runway_days = None
        if daily_deficit > 0 and system_balance.balance > 0:
            runway_days = float(system_balance.balance / daily_deficit)

        projected_scenarios = []
        for label, reward_multiplier in [
            ('Conservative (80% reward spending)', Decimal('0.80')),
            ('Base (current reward spending)', Decimal('1.00')),
            ('Growth Push (120% reward spending)', Decimal('1.20')),
        ]:
            scenario_reward_outflow = avg_daily_reward_outflow * reward_multiplier
            scenario_daily_outflow = avg_daily_non_reward_outflow + scenario_reward_outflow
            scenario_daily_net = avg_daily_inflow - scenario_daily_outflow

            projected_scenarios.append({
                'label': label,
                'daily_net': self._to_money(scenario_daily_net),
                'in_30_days': self._to_money(system_balance.balance + (scenario_daily_net * Decimal('30'))),
                'in_60_days': self._to_money(system_balance.balance + (scenario_daily_net * Decimal('60'))),
                'in_90_days': self._to_money(system_balance.balance + (scenario_daily_net * Decimal('90'))),
            })

        recommended_daily_budget = self._to_money(max(avg_daily_inflow * Decimal('0.75'), Decimal('0.00')))
        max_safe_daily_budget = self._to_money(max(avg_daily_inflow * Decimal('0.90'), Decimal('0.00')))
        min_reserve = self._to_money(avg_daily_outflow * Decimal('30'))

        if system_balance.balance <= 0:
            risk_level = 'Critical'
            recommendation = 'Pause non-essential promo and mission giveaways. Refill system balance immediately before allowing further reward claims.'
        elif runway_days is not None and runway_days < 14:
            risk_level = 'High'
            recommendation = (
                'Reduce giveaway spending by 25%-40%, prioritize mission rewards over promo bursts, '
                'and replenish system balance to at least 30-day reserve.'
            )
        elif sustainability_ratio is not None and sustainability_ratio < Decimal('0.90'):
            risk_level = 'Medium'
            recommendation = (
                'Current reward burn is near/above inflow. Tighten promo eligibility and keep daily giveaways near recommended budget.'
            )
        else:
            risk_level = 'Healthy'
            recommendation = (
                'Reward strategy is sustainable. Maintain current missions, run controlled promo campaigns, '
                'and monitor runway weekly.'
            )

        return {
            'policy': policy,
            'system_balance': system_balance,
            'days': days,
            'start_date': start_date,
            'today': today,
            'inflow_total': self._to_money(inflow_total),
            'outflow_total': self._to_money(outflow_total),
            'net_total': self._to_money(net_total),
            'reward_outflow_total': self._to_money(reward_outflow_total),
            'promo_reward_total': self._to_money(promo_reward_total),
            'mission_reward_total': self._to_money(mission_reward_total),
            'other_reward_total': self._to_money(other_reward_total),
            'avg_daily_inflow': self._to_money(avg_daily_inflow),
            'avg_daily_outflow': self._to_money(avg_daily_outflow),
            'avg_daily_reward_outflow': self._to_money(avg_daily_reward_outflow),
            'sustainability_ratio': round(float(sustainability_ratio), 2) if sustainability_ratio is not None else None,
            'runway_days': round(runway_days, 1) if runway_days is not None else None,
            'recommended_daily_budget': recommended_daily_budget,
            'max_safe_daily_budget': max_safe_daily_budget,
            'minimum_recommended_reserve': min_reserve,
            'risk_level': risk_level,
            'recommendation': recommendation,
            'projected_scenarios': projected_scenarios,
        }

    def analysis_view(self, request):
        try:
            days = int(request.GET.get('days', '30'))
        except ValueError:
            days = 30
        days = max(7, min(days, 180))

        context = dict(
            self.admin_site.each_context(request),
            title='System Balance Analysis & Recommendations',
            opts=self.model._meta,
            analysis=self._build_analysis_context(days),
            days_options=[7, 14, 30, 60, 90, 180],
        )
        return TemplateResponse(request, 'admin/game/system_balance/analysis.html', context)

    def analysis_export_view(self, request):
        try:
            days = int(request.GET.get('days', '30'))
        except ValueError:
            days = 30
        days = max(7, min(days, 180))

        analysis = self._build_analysis_context(days)

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="system_balance_analysis_{days}d.csv"'

        writer = csv.writer(response)
        writer.writerow(['Section', 'Metric', 'Value'])
        writer.writerow(['Summary', 'Period Start', analysis['start_date']])
        writer.writerow(['Summary', 'Period End', analysis['today']])
        writer.writerow(['Summary', 'Current Balance', analysis['system_balance'].balance])
        writer.writerow(['Summary', 'Risk Level', analysis['risk_level']])
        writer.writerow(['Summary', 'Runway Days', analysis['runway_days'] if analysis['runway_days'] is not None else 'Stable/Growing'])
        writer.writerow(['Summary', 'Sustainability Ratio', analysis['sustainability_ratio'] if analysis['sustainability_ratio'] is not None else 'N/A'])

        writer.writerow(['Cashflow', 'Total Inflow', analysis['inflow_total']])
        writer.writerow(['Cashflow', 'Total Outflow', analysis['outflow_total']])
        writer.writerow(['Cashflow', 'Net Total', analysis['net_total']])
        writer.writerow(['Cashflow', 'Average Daily Inflow', analysis['avg_daily_inflow']])
        writer.writerow(['Cashflow', 'Average Daily Outflow', analysis['avg_daily_outflow']])

        writer.writerow(['Rewards', 'Total Reward Payout', analysis['reward_outflow_total']])
        writer.writerow(['Rewards', 'Promo Rewards', analysis['promo_reward_total']])
        writer.writerow(['Rewards', 'Mission Rewards', analysis['mission_reward_total']])
        writer.writerow(['Rewards', 'Other Rewards', analysis['other_reward_total']])
        writer.writerow(['Rewards', 'Average Daily Reward Spend', analysis['avg_daily_reward_outflow']])

        writer.writerow(['Recommendations', 'Recommended Daily Giveaway Budget', analysis['recommended_daily_budget']])
        writer.writerow(['Recommendations', 'Maximum Safe Daily Giveaway Budget', analysis['max_safe_daily_budget']])
        writer.writerow(['Recommendations', 'Minimum Recommended Reserve', analysis['minimum_recommended_reserve']])
        writer.writerow(['Recommendations', 'Low Balance Warning Threshold', analysis['policy'].low_system_balance_warning_threshold])
        writer.writerow(['Recommendations', 'Narrative', analysis['recommendation']])

        writer.writerow([])
        writer.writerow(['Scenario Forecast', 'Scenario', 'Daily Net', 'In 30 Days', 'In 60 Days', 'In 90 Days'])
        for row in analysis['projected_scenarios']:
            writer.writerow([
                'Scenario Forecast',
                row['label'],
                row['daily_net'],
                row['in_30_days'],
                row['in_60_days'],
                row['in_90_days'],
            ])

        return response

    def _warning_threshold(self):
        return RewardSafetyPolicy.get_active().low_system_balance_warning_threshold

    def _warn_if_low_balance(self, request):
        snapshot = SystemBalance.objects.filter(pk=1).first()
        if not snapshot:
            self.message_user(
                request,
                'System balance record is missing. Create it in this page to avoid reward payout failures.',
                level=messages.WARNING,
            )
            return

        threshold = self._warning_threshold()
        if snapshot.balance <= 0:
            self.message_user(
                request,
                'System balance is empty. Promo and mission claims will fail until you top up.',
                level=messages.ERROR,
            )
        elif snapshot.balance <= threshold:
            self.message_user(
                request,
                f'System balance is low ({snapshot.balance} Birr). Top up soon to avoid reward claim failures.',
                level=messages.WARNING,
            )

    def changelist_view(self, request, extra_context=None):
        self._warn_if_low_balance(request)
        self.message_user(
            request,
            format_html(
                'Need projection and guidance? <a href="{}">Open System Balance Analysis & Recommendations</a>.',
                reverse('admin:game_systembalance_analysis'),
            ),
            level=messages.INFO,
        )
        return super().changelist_view(request, extra_context=extra_context)

    def change_view(self, request, object_id, form_url='', extra_context=None):
        self._warn_if_low_balance(request)
        return super().change_view(request, object_id, form_url=form_url, extra_context=extra_context)

    def balance_health(self, obj):
        threshold = self._warning_threshold()
        if obj.balance <= 0:
            return format_html('<span style="color: #b91c1c; font-weight: 700;">Critical</span>')
        if obj.balance <= threshold:
            return format_html('<span style="color: #b45309; font-weight: 700;">Low</span>')
        return format_html('<span style="color: #166534; font-weight: 700;">Healthy</span>')
    balance_health.short_description = 'Health'

    def analysis_page(self, obj):
        return format_html(
            '<a class="button" href="{}">Open analysis</a>',
            reverse('admin:game_systembalance_analysis'),
        )
    analysis_page.short_description = 'Analysis'


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
    list_display = [
        'id',
        'daily_reward_cap',
        'low_system_balance_warning_threshold',
        'min_seconds_between_rewards',
        'max_reward_redemptions_per_hour',
        'updated_at',
    ]


@admin.register(GameEngineSettings)
class GameEngineSettingsAdmin(admin.ModelAdmin):
    list_display = ['id', 'enable_fake_users', 'updated_at']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(BusinessRuleSettings)
class BusinessRuleSettingsAdmin(admin.ModelAdmin):
    list_display = [
        'id',
        'minimum_withdrawable_balance',
        'referral_bonus_amount',
        'countdown_seconds',
        'rejoin_start_delay_minutes',
        'derash_percentage',
        'system_percentage',
        'telebirr_receiving_phone_number',
        'telebirr_receiving_account_name',
        'updated_by',
        'updated_at',
    ]
    readonly_fields = ['created_at', 'updated_at', 'updated_by']

    def has_add_permission(self, request):
        return not BusinessRuleSettings.objects.exists()

    def save_model(self, request, obj, form, change):
        previous = {}
        if change and obj.pk:
            old = BusinessRuleSettings.objects.filter(pk=obj.pk).first()
            if old:
                previous = {
                    'minimum_withdrawable_balance': str(old.minimum_withdrawable_balance),
                    'referral_bonus_amount': str(old.referral_bonus_amount),
                    'countdown_seconds': old.countdown_seconds,
                    'rejoin_start_delay_minutes': old.rejoin_start_delay_minutes,
                    'derash_percentage': str(old.derash_percentage),
                    'system_percentage': str(old.system_percentage),
                    'telebirr_receiving_phone_number': old.telebirr_receiving_phone_number,
                    'telebirr_receiving_account_name': old.telebirr_receiving_account_name,
                }

        admin_user = None
        if getattr(request, 'user', None) and request.user.is_authenticated:
            admin_user = User.objects.filter(username=request.user.username).first()

        obj.updated_by = admin_user
        super().save_model(request, obj, form, change)

        new_values = {
            'minimum_withdrawable_balance': str(obj.minimum_withdrawable_balance),
            'referral_bonus_amount': str(obj.referral_bonus_amount),
            'countdown_seconds': obj.countdown_seconds,
            'rejoin_start_delay_minutes': obj.rejoin_start_delay_minutes,
            'derash_percentage': str(obj.derash_percentage),
            'system_percentage': str(obj.system_percentage),
            'telebirr_receiving_phone_number': obj.telebirr_receiving_phone_number,
            'telebirr_receiving_account_name': obj.telebirr_receiving_account_name,
        }

        BusinessRuleSettingsAudit.objects.create(
            business_settings=obj,
            changed_by=admin_user,
            previous_values=previous,
            new_values=new_values,
        )


@admin.register(BusinessRuleSettingsAudit)
class BusinessRuleSettingsAuditAdmin(admin.ModelAdmin):
    list_display = ['id', 'business_settings', 'changed_by', 'changed_at']
    list_filter = ['changed_at']
    search_fields = ['changed_by__first_name', 'changed_by__username']
    readonly_fields = ['business_settings', 'changed_by', 'previous_values', 'new_values', 'changed_at']


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

    def save_model(self, request, obj, form, change):
        if obj.code:
            obj.code = obj.code.strip().upper()
        super().save_model(request, obj, form, change)


@admin.register(PromoCodeRedemption)
class PromoCodeRedemptionAdmin(admin.ModelAdmin):
    list_display = ['id', 'promo_code', 'user', 'verification_request', 'amount', 'created_at']
    list_filter = ['promo_code', 'created_at']
    search_fields = ['promo_code__code', 'user__first_name', 'user__username', 'user__telegram_id']


@admin.register(PromoVerificationRequest)
class PromoVerificationRequestAdmin(admin.ModelAdmin):
    list_display = [
        'id',
        'promo_code',
        'user',
        'status',
        'admin_reviewer',
        'credited_amount',
        'submitted_at',
        'decision_time',
    ]
    list_filter = ['status', 'submitted_at', 'decision_time']
    search_fields = [
        'promo_code__code',
        'user__first_name',
        'user__username',
        'user__telegram_id',
        'review_reason',
    ]
    readonly_fields = ['submitted_at', 'decision_time', 'credited_amount']


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
