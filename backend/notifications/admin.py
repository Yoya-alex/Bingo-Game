from django.contrib import admin

from .models import Notification, NotificationDelivery


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "notification_type",
        "status",
        "total_recipients",
        "delivered_count",
        "failed_count",
        "created_at",
        "sent_at",
    )
    list_filter = ("notification_type", "status", "created_at")
    search_fields = ("message", "title")


@admin.register(NotificationDelivery)
class NotificationDeliveryAdmin(admin.ModelAdmin):
    list_display = ("id", "notification", "user", "status", "delivered_at", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("user__username", "user__first_name", "error_message")
