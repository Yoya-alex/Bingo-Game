from django.db import models
from django.utils import timezone

from users.models import User


class Notification(models.Model):
    NOTIFICATION_TYPES = [
        ("admin_announcement", "Admin Announcement"),
    ]

    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("sending", "Sending"),
        ("completed", "Completed"),
        ("failed", "Failed"),
    ]

    notification_type = models.CharField(
        max_length=50, choices=NOTIFICATION_TYPES, default="admin_announcement"
    )
    title = models.CharField(max_length=255, blank=True)
    message = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft")

    total_recipients = models.PositiveIntegerField(default=0)
    delivered_count = models.PositiveIntegerField(default=0)
    failed_count = models.PositiveIntegerField(default=0)

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_notifications",
    )
    created_at = models.DateTimeField(default=timezone.now)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "notification"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.notification_type} - {self.status} - #{self.id}"


class NotificationDelivery(models.Model):
    DELIVERY_STATUS_CHOICES = [
        ("pending", "Pending"),
        ("delivered", "Delivered"),
        ("failed", "Failed"),
    ]

    notification = models.ForeignKey(
        Notification,
        on_delete=models.CASCADE,
        related_name="deliveries",
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="notification_deliveries",
    )
    status = models.CharField(
        max_length=20,
        choices=DELIVERY_STATUS_CHOICES,
        default="pending",
    )
    error_message = models.TextField(blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "notification_delivery"
        ordering = ["-created_at"]
        unique_together = ("notification", "user")

    def __str__(self):
        return (
            f"NotificationDelivery(notification={self.notification_id}, "
            f"user={self.user_id}, status={self.status})"
        )
