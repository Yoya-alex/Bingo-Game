from django.contrib import admin
from .models import User, Referral, ReferralEvent


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ['telegram_id', 'first_name', 'username', 'invite_code', 'referred_by', 'referral_count', 'site_status', 'last_site_seen_at', 'registration_date', 'is_admin']
    list_filter = ['is_admin', 'is_active', 'registration_date']
    search_fields = ['telegram_id', 'username', 'first_name', 'invite_code']
    readonly_fields = ['telegram_id', 'registration_date', 'invite_code', 'referral_count', 'last_site_seen_at']
    
    fieldsets = (
        ('User Info', {
            'fields': ('telegram_id', 'username', 'first_name', 'invite_code', 'referred_by', 'referral_count')
        }),
        ('Status', {
            'fields': ('is_active', 'is_admin', 'last_site_seen_at', 'registration_date')
        }),
    )

    def site_status(self, obj):
        if not obj.last_site_seen_at:
            return 'Offline'
        from django.utils import timezone
        delta = (timezone.now() - obj.last_site_seen_at).total_seconds()
        return 'Online' if delta <= 45 else 'Offline'

    site_status.short_description = 'Site Status'


@admin.register(Referral)
class ReferralAdmin(admin.ModelAdmin):
    list_display = ['id', 'inviter', 'referred_user', 'status', 'reward_amount', 'created_at', 'qualified_at', 'rewarded_at']
    list_filter = ['status', 'created_at', 'qualified_at', 'rewarded_at']
    search_fields = ['inviter__username', 'inviter__first_name', 'referred_user__username', 'referred_user__first_name']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(ReferralEvent)
class ReferralEventAdmin(admin.ModelAdmin):
    list_display = ['id', 'referral', 'event_type', 'created_at']
    list_filter = ['event_type', 'created_at']
    readonly_fields = ['created_at']
