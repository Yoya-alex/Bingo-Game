from django.db import models
from django.utils import timezone
import random
import string


class User(models.Model):
    telegram_id = models.BigIntegerField(unique=True, db_index=True)
    username = models.CharField(max_length=255, null=True, blank=True)
    first_name = models.CharField(max_length=255)
    invite_code = models.CharField(max_length=10, unique=True, db_index=True, blank=True)
    referred_by = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='referred_users'
    )
    referral_count = models.PositiveIntegerField(default=0)
    registration_date = models.DateTimeField(default=timezone.now)
    is_active = models.BooleanField(default=True)
    is_admin = models.BooleanField(default=False)
    
    class Meta:
        db_table = 'users'
        ordering = ['-registration_date']
    
    def __str__(self):
        return f"{self.first_name} (@{self.username})"

    @classmethod
    def generate_invite_code(cls, min_length=6, max_length=10):
        alphabet = string.ascii_uppercase + string.digits
        for _ in range(20):
            length = random.randint(min_length, max_length)
            code = ''.join(random.choice(alphabet) for _ in range(length))
            if not cls.objects.filter(invite_code=code).exists():
                return code
        raise ValueError("Unable to generate unique invite code")

    def save(self, *args, **kwargs):
        if not self.invite_code:
            self.invite_code = self.generate_invite_code()
        super().save(*args, **kwargs)


class Referral(models.Model):
    STATUS_PENDING = 'PENDING'
    STATUS_QUALIFIED = 'QUALIFIED'
    STATUS_REWARDED = 'REWARDED'
    STATUS_INVALID = 'INVALID'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_QUALIFIED, 'Qualified'),
        (STATUS_REWARDED, 'Rewarded'),
        (STATUS_INVALID, 'Invalid'),
    ]

    inviter = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_referrals')
    referred_user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='referral')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    reward_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    qualified_deposit_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    invalid_reason = models.CharField(max_length=255, blank=True)
    qualified_at = models.DateTimeField(null=True, blank=True)
    rewarded_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'referrals'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['inviter', 'status']),
            models.Index(fields=['status', 'created_at']),
        ]

    def __str__(self):
        return f"Referral({self.inviter_id}->{self.referred_user_id}, {self.status})"


class ReferralEvent(models.Model):
    EVENT_REGISTERED = 'REFERRAL_REGISTERED'
    EVENT_QUALIFIED = 'REFERRAL_QUALIFIED'
    EVENT_REWARDED = 'REFERRAL_REWARDED'
    EVENT_INVALIDATED = 'REFERRAL_INVALIDATED'

    EVENT_CHOICES = [
        (EVENT_REGISTERED, 'Referral Registered'),
        (EVENT_QUALIFIED, 'Referral Qualified'),
        (EVENT_REWARDED, 'Referral Rewarded'),
        (EVENT_INVALIDATED, 'Referral Invalidated'),
    ]

    referral = models.ForeignKey(Referral, on_delete=models.CASCADE, related_name='events')
    event_type = models.CharField(max_length=40, choices=EVENT_CHOICES)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'referral_events'
        ordering = ['-created_at']

    def __str__(self):
        return f"ReferralEvent({self.referral_id}, {self.event_type})"
