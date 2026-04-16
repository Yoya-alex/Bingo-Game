from django.db import models
from django.db import transaction
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.utils import timezone
from users.models import User
import json
from decimal import Decimal
from bot.utils.game_logic import generate_bingo_card


class Game(models.Model):
    GAME_STATES = [
        ('no_game', 'No Game'),
        ('waiting', 'Waiting'),
        ('playing', 'Playing'),
        ('finished', 'Finished'),
    ]
    
    state = models.CharField(max_length=20, choices=GAME_STATES, default='no_game')
    stake_amount = models.IntegerField(default=10, db_index=True)
    created_at = models.DateTimeField(default=timezone.now)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    winner = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='won_games')
    prize_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    called_numbers = models.TextField(default='[]')
    has_bots = models.BooleanField(default=False)
    real_players_count = models.IntegerField(default=0)
    real_prize_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    system_revenue = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    class Meta:
        db_table = 'games'
        ordering = ['-created_at']
    
    def get_called_number_entries(self):
        try:
            raw_values = json.loads(self.called_numbers)
        except Exception:
            raw_values = []

        entries = []
        for item in raw_values:
            if isinstance(item, dict):
                number = item.get('number')
                called_at = item.get('called_at')
            else:
                number = item
                called_at = None

            try:
                normalized_number = int(number)
            except (TypeError, ValueError):
                continue

            entries.append({
                'number': normalized_number,
                'called_at': called_at,
            })
        return entries

    def get_called_numbers(self):
        return [entry['number'] for entry in self.get_called_number_entries()]
    
    def set_called_numbers(self, numbers):
        normalized = []
        for item in numbers:
            if isinstance(item, dict):
                number = item.get('number')
                called_at = item.get('called_at')
            else:
                number = item
                called_at = None

            try:
                normalized_number = int(number)
            except (TypeError, ValueError):
                continue

            normalized.append({
                'number': normalized_number,
                'called_at': called_at,
            })

        self.called_numbers = json.dumps(normalized)
    
    def __str__(self):
        return f"Game {self.id} - {self.state} - {self.stake_amount} Br"


class StakeLobbyLock(models.Model):
    """DB-backed lock row used to serialize lobby game creation per stake."""

    stake_amount = models.IntegerField(unique=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'stake_lobby_lock'

    def __str__(self):
        return f"Stake lock {self.stake_amount} Br"


class SystemBalance(models.Model):
    balance = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'system_balance'

    @classmethod
    def get_singleton_for_update(cls):
        snapshot, _ = cls.objects.select_for_update().get_or_create(
            pk=1,
            defaults={'balance': Decimal('0.00')}
        )
        return snapshot

    def __str__(self):
        return f"System Balance: {self.balance}"


class SystemBalanceLedger(models.Model):
    EVENT_TYPES = [
        ('game_commission', 'Game Commission'),
        ('game_no_winner', 'Game No Winner'),
        ('reward_payout', 'Reward Payout'),
        ('admin_adjustment', 'Admin Adjustment'),
    ]
    
    DIRECTIONS = [
        ('credit', 'Credit'),
        ('debit', 'Debit'),
    ]

    event_type = models.CharField(max_length=30, choices=EVENT_TYPES)
    direction = models.CharField(max_length=10, choices=DIRECTIONS)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    balance_before = models.DecimalField(max_digits=14, decimal_places=2)
    balance_after = models.DecimalField(max_digits=14, decimal_places=2)
    game = models.ForeignKey(Game, on_delete=models.SET_NULL, null=True, blank=True, related_name='system_balance_entries')
    description = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    idempotency_key = models.CharField(max_length=120, null=True, blank=True, unique=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'system_balance_ledger'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['event_type']),
            models.Index(fields=['created_at']),
        ]

    @classmethod
    def append_entry(
        cls,
        *,
        event_type,
        direction,
        amount,
        game=None,
        description='',
        metadata=None,
        idempotency_key=None,
    ):
        amount = Decimal(str(amount))
        if amount <= 0:
            raise ValueError('Amount must be greater than zero.')

        with transaction.atomic():
            if idempotency_key:
                existing = cls.objects.filter(idempotency_key=idempotency_key).first()
                if existing:
                    return existing

            snapshot = SystemBalance.get_singleton_for_update()
            balance_before = Decimal(str(snapshot.balance))

            if direction == 'credit':
                balance_after = balance_before + amount
            elif direction == 'debit':
                balance_after = balance_before - amount
            else:
                raise ValueError('Invalid direction for system balance ledger entry.')

            if balance_after < 0:
                raise ValueError('System balance cannot be negative.')

            entry = cls.objects.create(
                event_type=event_type,
                direction=direction,
                amount=amount,
                balance_before=balance_before,
                balance_after=balance_after,
                game=game,
                description=description,
                metadata=metadata or {},
                idempotency_key=idempotency_key,
            )

            snapshot.balance = balance_after
            snapshot.save(update_fields=['balance', 'updated_at'])
            return entry

    def __str__(self):
        return f"{self.event_type} {self.direction} {self.amount}"


class BingoCard(models.Model):
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name='cards')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='bingo_cards')
    card_number = models.IntegerField()
    marked_positions = models.TextField(default='[]')
    is_winner = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)
    custom_grid = models.TextField(null=True, blank=True)  # For bot-generated winning grids
    
    class Meta:
        db_table = 'bingo_cards'
        unique_together = ['game', 'card_number']
    
    def get_grid(self):
        # If custom grid exists (for bot winners), use it
        if self.custom_grid:
            try:
                return json.loads(self.custom_grid)
            except:
                pass
        return generate_bingo_card(self.card_number)
    
    def set_grid(self, grid_data):
        self.custom_grid = json.dumps(grid_data)
    
    def get_marked_positions(self):
        return json.loads(self.marked_positions)
    
    def set_marked_positions(self, positions):
        self.marked_positions = json.dumps(positions)
    
    def __str__(self):
        return f"Card {self.card_number} - Game {self.game.id} - {self.user.first_name}"


class RewardSafetyPolicy(models.Model):
    daily_reward_cap = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('500.00'))
    low_system_balance_warning_threshold = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('500.00'))
    min_seconds_between_rewards = models.IntegerField(default=20)
    max_reward_redemptions_per_hour = models.IntegerField(default=20)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'reward_safety_policy'

    @classmethod
    def get_active(cls):
        policy, _ = cls.objects.get_or_create(pk=1)
        return policy

    def __str__(self):
        return f"Reward Safety Policy #{self.pk}"


class GameEngineSettings(models.Model):
    enable_fake_users = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'game_engine_settings'

    @classmethod
    def get_active(cls):
        settings_row, _ = cls.objects.get_or_create(pk=1)
        return settings_row

    def __str__(self):
        state = 'Enabled' if self.enable_fake_users else 'Disabled'
        return f"Game Engine Settings (Fake Users: {state})"


class BusinessRuleSettings(models.Model):
    ethiopian_phone_validator = RegexValidator(
        regex=r'^(?:\+?2519\d{8}|09\d{8})$',
        message='Enter a valid Ethiopian phone number (e.g. 09XXXXXXXX or +2519XXXXXXXX).',
    )

    minimum_withdrawable_balance = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('100.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
    )
    referral_bonus_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('10.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
    )
    derash_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('80.00'),
        validators=[MinValueValidator(Decimal('0.00')), MaxValueValidator(Decimal('100.00'))],
    )
    system_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('20.00'),
        validators=[MinValueValidator(Decimal('0.00')), MaxValueValidator(Decimal('100.00'))],
    )
    telebirr_receiving_phone_number = models.CharField(
        max_length=20,
        validators=[ethiopian_phone_validator],
    )
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='updated_business_rule_settings',
    )
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'business_rule_settings'

    @classmethod
    def get_active(cls):
        from django.conf import settings

        defaults = {
            'minimum_withdrawable_balance': Decimal(str(getattr(settings, 'MIN_WITHDRAWAL', 100))),
            'referral_bonus_amount': Decimal(str(getattr(settings, 'REFERRAL_REWARD', 10))),
            'derash_percentage': Decimal('80.00'),
            'system_percentage': Decimal('20.00'),
            'telebirr_receiving_phone_number': str(getattr(settings, 'TELEBIRR_NUMBER', '0912345678')),
        }
        settings_row, _ = cls.objects.get_or_create(pk=1, defaults=defaults)
        return settings_row

    def clean(self):
        super().clean()
        if not self.telebirr_receiving_phone_number:
            raise ValidationError({'telebirr_receiving_phone_number': 'Telebirr receiving phone number is required.'})
        total = (self.derash_percentage or Decimal('0')) + (self.system_percentage or Decimal('0'))
        if total != Decimal('100'):
            raise ValidationError({'system_percentage': 'Derash Percentage + System Percentage must equal 100.'})

    def save(self, *args, **kwargs):
        self.pk = 1
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return (
            f"Business Rules (Min Withdraw: {self.minimum_withdrawable_balance}, "
            f"Referral: {self.referral_bonus_amount}, "
            f"Derash/System: {self.derash_percentage}/{self.system_percentage})"
        )


class BusinessRuleSettingsAudit(models.Model):
    business_settings = models.ForeignKey(
        BusinessRuleSettings,
        on_delete=models.CASCADE,
        related_name='audit_entries',
    )
    changed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='business_rule_audit_entries',
    )
    previous_values = models.JSONField(default=dict, blank=True)
    new_values = models.JSONField(default=dict, blank=True)
    changed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'business_rule_settings_audit'
        ordering = ['-changed_at']

    def __str__(self):
        return f"BusinessRuleAudit({self.id}) by {self.changed_by_id}"


class UserRewardWindow(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reward_windows')
    reward_date = models.DateField()
    reward_total = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    redemption_count = models.IntegerField(default=0)
    last_reward_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'user_reward_window'
        unique_together = ['user', 'reward_date']
        indexes = [
            models.Index(fields=['reward_date']),
            models.Index(fields=['user', 'reward_date']),
        ]

    def __str__(self):
        return f"RewardWindow({self.user_id}, {self.reward_date})"


class PromoCode(models.Model):
    TIER_COMMON = 'common'
    TIER_RARE = 'rare'
    TIER_LEGENDARY = 'legendary'
    TIER_CHOICES = [
        (TIER_COMMON, 'Common'),
        (TIER_RARE, 'Rare'),
        (TIER_LEGENDARY, 'Legendary'),
    ]

    BALANCE_BONUS = 'bonus'
    BALANCE_MAIN = 'main'
    BALANCE_WINNINGS = 'winnings'
    BALANCE_CHOICES = [
        (BALANCE_BONUS, 'Bonus Balance'),
        (BALANCE_MAIN, 'Main Balance'),
        (BALANCE_WINNINGS, 'Winnings Balance'),
    ]

    code = models.CharField(max_length=40, unique=True, db_index=True)
    title = models.CharField(max_length=120, blank=True)
    tier = models.CharField(max_length=20, choices=TIER_CHOICES, default=TIER_COMMON)
    reward_amount = models.DecimalField(max_digits=10, decimal_places=2)
    reward_balance = models.CharField(max_length=20, choices=BALANCE_CHOICES, default=BALANCE_BONUS)
    starts_at = models.DateTimeField(default=timezone.now)
    ends_at = models.DateTimeField()
    max_redemptions = models.IntegerField(default=0)
    per_user_limit = models.IntegerField(default=1)
    min_account_age_days = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    is_visible_in_frontend = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'promo_codes'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['code']),
            models.Index(fields=['is_active', 'starts_at', 'ends_at']),
        ]

    def is_live(self):
        now = timezone.now()
        return bool(self.is_active and self.starts_at <= now <= self.ends_at)

    def save(self, *args, **kwargs):
        if self.code:
            self.code = self.code.strip().upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.code} ({self.tier})"


class PromoVerificationRequest(models.Model):
    STATUS_PENDING = 'pending_verification'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending Verification'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_REJECTED, 'Rejected'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='promo_verification_requests')
    promo_code = models.ForeignKey(PromoCode, on_delete=models.CASCADE, related_name='verification_requests')
    submitted_at = models.DateTimeField(default=timezone.now)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default=STATUS_PENDING)
    admin_reviewer = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_promo_verifications',
    )
    review_reason = models.TextField(blank=True)
    decision_time = models.DateTimeField(null=True, blank=True)
    credited_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))

    class Meta:
        db_table = 'promo_verification_requests'
        ordering = ['-submitted_at']
        indexes = [
            models.Index(fields=['status', 'submitted_at']),
            models.Index(fields=['user', 'submitted_at']),
            models.Index(fields=['promo_code', 'submitted_at']),
        ]

    def __str__(self):
        return f"PromoVerification({self.promo_code_id}, {self.user_id}, {self.status})"


class PromoCodeRedemption(models.Model):
    promo_code = models.ForeignKey(PromoCode, on_delete=models.CASCADE, related_name='redemptions')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='promo_redemptions')
    verification_request = models.OneToOneField(
        PromoVerificationRequest,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='redemption',
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'promo_code_redemptions'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['promo_code', 'created_at']),
            models.Index(fields=['user', 'created_at']),
        ]

    def __str__(self):
        return f"PromoRedemption({self.promo_code_id}, {self.user_id})"


class MissionTemplate(models.Model):
    TYPE_PLAY_GAMES = 'play_games'
    TYPE_WIN_GAMES = 'win_games'
    TYPE_REDEEM_PROMO = 'redeem_promo'
    TYPE_INVITE_USERS = 'invite_users'
    TYPE_CHOICES = [
        (TYPE_PLAY_GAMES, 'Play Games'),
        (TYPE_WIN_GAMES, 'Win Games'),
        (TYPE_REDEEM_PROMO, 'Redeem Promo'),
        (TYPE_INVITE_USERS, 'Invite Users'),
    ]

    PERIOD_DAILY = 'daily'
    PERIOD_WEEKLY = 'weekly'
    PERIOD_CHOICES = [
        (PERIOD_DAILY, 'Daily'),
        (PERIOD_WEEKLY, 'Weekly'),
    ]

    key = models.CharField(max_length=60, unique=True, db_index=True)
    title = models.CharField(max_length=120)
    description = models.CharField(max_length=255, blank=True)
    mission_type = models.CharField(max_length=30, choices=TYPE_CHOICES)
    period = models.CharField(max_length=10, choices=PERIOD_CHOICES, default=PERIOD_DAILY)
    target_value = models.IntegerField(default=1)
    reward_amount = models.DecimalField(max_digits=10, decimal_places=2)
    reward_balance = models.CharField(max_length=20, choices=PromoCode.BALANCE_CHOICES, default=PromoCode.BALANCE_BONUS)
    is_active = models.BooleanField(default=True)
    sort_order = models.IntegerField(default=100)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'mission_templates'
        ordering = ['sort_order', 'id']
        indexes = [
            models.Index(fields=['is_active', 'period']),
            models.Index(fields=['mission_type']),
        ]

    def __str__(self):
        return f"{self.key} ({self.period})"


class UserMissionProgress(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='mission_progress')
    mission = models.ForeignKey(MissionTemplate, on_delete=models.CASCADE, related_name='progress_rows')
    period_start = models.DateField()
    period_end = models.DateField()
    progress_value = models.IntegerField(default=0)
    completed_at = models.DateTimeField(null=True, blank=True)
    claimed_at = models.DateTimeField(null=True, blank=True)
    reward_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'user_mission_progress'
        unique_together = ['user', 'mission', 'period_start']
        ordering = ['-period_start', 'mission_id']
        indexes = [
            models.Index(fields=['user', 'period_start']),
            models.Index(fields=['period_end']),
        ]

    @property
    def is_completed(self):
        return self.progress_value >= self.mission.target_value

    @property
    def is_claimed(self):
        return bool(self.claimed_at)

    def __str__(self):
        return f"MissionProgress({self.user_id}, {self.mission_id}, {self.period_start})"


class UserStreak(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='streak')
    current_streak = models.IntegerField(default=0)
    best_streak = models.IntegerField(default=0)
    last_active_date = models.DateField(null=True, blank=True)
    streak_protect_tokens = models.IntegerField(default=1)
    last_protect_grant_week = models.CharField(max_length=8, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'user_streaks'

    def __str__(self):
        return f"Streak({self.user_id}) current={self.current_streak}"


class LiveEvent(models.Model):
    TYPE_HAPPY_HOUR = 'happy_hour'
    TYPE_FLASH_PROMO = 'flash_promo'
    TYPE_DOUBLE_REWARD = 'double_reward'
    TYPE_CHOICES = [
        (TYPE_HAPPY_HOUR, 'Happy Hour'),
        (TYPE_FLASH_PROMO, 'Flash Promo'),
        (TYPE_DOUBLE_REWARD, 'Double Reward'),
    ]

    name = models.CharField(max_length=120)
    event_type = models.CharField(max_length=30, choices=TYPE_CHOICES)
    description = models.CharField(max_length=255, blank=True)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    bonus_multiplier = models.DecimalField(max_digits=4, decimal_places=2, default=Decimal('1.00'))
    is_active = models.BooleanField(default=True)
    auto_announce = models.BooleanField(default=True)
    announced_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'live_events'
        ordering = ['starts_at', 'id']
        indexes = [
            models.Index(fields=['is_active', 'starts_at', 'ends_at']),
            models.Index(fields=['event_type']),
        ]

    def is_live(self):
        now = timezone.now()
        return bool(self.is_active and self.starts_at <= now <= self.ends_at)

    def __str__(self):
        return f"{self.name} ({self.event_type})"


class Season(models.Model):
    name = models.CharField(max_length=120)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    top_1_reward = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    top_2_reward = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    top_3_reward = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    participation_reward = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'seasons'
        ordering = ['-starts_at']
        indexes = [
            models.Index(fields=['is_active', 'starts_at', 'ends_at']),
        ]

    @classmethod
    def get_current(cls):
        now = timezone.now()
        return cls.objects.filter(is_active=True, starts_at__lte=now, ends_at__gte=now).order_by('-starts_at').first()

    def __str__(self):
        return self.name
