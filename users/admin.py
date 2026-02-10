from django.contrib import admin
from .models import User


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ['telegram_id', 'first_name', 'username', 'registration_date', 'is_admin']
    list_filter = ['is_admin', 'is_active', 'registration_date']
    search_fields = ['telegram_id', 'username', 'first_name']
    readonly_fields = ['telegram_id', 'registration_date']
    
    fieldsets = (
        ('User Info', {
            'fields': ('telegram_id', 'username', 'first_name')
        }),
        ('Status', {
            'fields': ('is_active', 'is_admin', 'registration_date')
        }),
    )
