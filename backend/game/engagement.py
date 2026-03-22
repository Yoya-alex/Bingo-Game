from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from game.models import (
    LiveEvent,
    MissionTemplate,
    PromoCode,
    SystemBalanceLedger,
    UserMissionProgress,
    UserRewardWindow,
    UserStreak,
    RewardSafetyPolicy,
)
from wallet.models import Transaction, Wallet


class RewardSafetyError(ValueError):
    pass


def get_period_bounds(period: str, now=None):
    now = now or timezone.now()
    today = now.date()

    if period == MissionTemplate.PERIOD_DAILY:
        return today, today

    if period == MissionTemplate.PERIOD_WEEKLY:
        start = today - timedelta(days=today.weekday())
        end = start + timedelta(days=6)
        return start, end

    raise ValueError("Unsupported mission period")


def get_live_reward_multiplier():
    now = timezone.now()
    event = (
        LiveEvent.objects.filter(
            is_active=True,
            event_type=LiveEvent.TYPE_DOUBLE_REWARD,
            starts_at__lte=now,
            ends_at__gte=now,
        )
        .order_by('-bonus_multiplier', 'starts_at')
        .first()
    )
    if not event:
        return Decimal('1.00')
    return Decimal(str(event.bonus_multiplier))


def _apply_wallet_credit(wallet: Wallet, amount: Decimal, reward_balance: str):
    if reward_balance == PromoCode.BALANCE_MAIN:
        wallet.main_balance += amount
    elif reward_balance == PromoCode.BALANCE_WINNINGS:
        wallet.winnings_balance += amount
    else:
        wallet.bonus_balance += amount


def enforce_reward_safety(user, amount: Decimal):
    policy = RewardSafetyPolicy.get_active()
    amount = Decimal(str(amount))
    if amount <= 0:
        raise RewardSafetyError("Reward amount must be greater than zero.")

    now = timezone.now()
    today = now.date()

    window, _ = UserRewardWindow.objects.select_for_update().get_or_create(
        user=user,
        reward_date=today,
        defaults={
            'reward_total': Decimal('0.00'),
            'redemption_count': 0,
            'last_reward_at': None,
        },
    )

    if window.last_reward_at:
        diff_seconds = (now - window.last_reward_at).total_seconds()
        if diff_seconds < policy.min_seconds_between_rewards:
            raise RewardSafetyError("Too many reward actions. Please wait a moment.")

    if window.reward_total + amount > policy.daily_reward_cap:
        raise RewardSafetyError("Daily reward cap reached for this account.")

    hour_ago = now - timedelta(hours=1)
    recent = Transaction.objects.filter(
        user=user,
        transaction_type='bonus',
        status__in=['approved', 'completed'],
        created_at__gte=hour_ago,
        description__icontains='Reward:',
    ).count()
    if recent >= policy.max_reward_redemptions_per_hour:
        raise RewardSafetyError("Hourly reward redemption limit reached.")

    return window


def credit_user_reward(user, amount, reward_balance, description):
    amount = Decimal(str(amount))
    if amount <= 0:
        raise RewardSafetyError("Reward amount must be positive.")

    multiplier = get_live_reward_multiplier()
    final_amount = (amount * multiplier).quantize(Decimal('0.01'))

    with transaction.atomic():
        wallet, _ = Wallet.objects.select_for_update().get_or_create(user=user)
        window = enforce_reward_safety(user, final_amount)

        try:
            SystemBalanceLedger.append_entry(
                event_type='reward_payout',
                direction='debit',
                amount=final_amount,
                description=f'Reward payout to user #{user.id}: {description}',
                metadata={
                    'user_id': user.id,
                    'telegram_id': user.telegram_id,
                    'reward_balance': reward_balance,
                    'reward_description': description,
                },
            )
        except ValueError as exc:
            if 'cannot be negative' in str(exc).lower():
                raise RewardSafetyError('System balance is insufficient for this reward right now.')
            raise

        _apply_wallet_credit(wallet, final_amount, reward_balance)
        wallet.save(update_fields=['main_balance', 'bonus_balance', 'winnings_balance', 'updated_at'])

        Transaction.objects.create(
            user=user,
            transaction_type='bonus',
            amount=final_amount,
            status='approved',
            description=f"Reward: {description}",
        )

        now = timezone.now()
        window.reward_total = (window.reward_total + final_amount).quantize(Decimal('0.01'))
        window.redemption_count += 1
        window.last_reward_at = now
        window.save(update_fields=['reward_total', 'redemption_count', 'last_reward_at', 'updated_at'])

    return final_amount


def increment_missions(user, mission_type: str, amount: int = 1):
    if amount <= 0:
        return

    now = timezone.now()
    templates = MissionTemplate.objects.filter(is_active=True, mission_type=mission_type)

    for mission in templates:
        period_start, period_end = get_period_bounds(mission.period, now=now)
        progress, _ = UserMissionProgress.objects.get_or_create(
            user=user,
            mission=mission,
            period_start=period_start,
            defaults={
                'period_end': period_end,
                'progress_value': 0,
                'reward_amount': mission.reward_amount,
            },
        )

        if progress.claimed_at:
            continue

        progress.progress_value += amount
        if progress.progress_value >= mission.target_value and not progress.completed_at:
            progress.completed_at = now

        progress.reward_amount = mission.reward_amount
        progress.period_end = period_end
        progress.save(update_fields=['progress_value', 'completed_at', 'reward_amount', 'period_end', 'updated_at'])


def claim_mission(user, progress_id: int):
    with transaction.atomic():
        progress = (
            UserMissionProgress.objects.select_for_update()
            .select_related('mission')
            .filter(id=progress_id, user=user)
            .first()
        )
        if not progress:
            raise ValueError('Mission progress not found.')
        if progress.claimed_at:
            raise ValueError('Mission reward already claimed.')
        if progress.progress_value < progress.mission.target_value:
            raise ValueError('Mission is not complete yet.')

        amount = credit_user_reward(
            user=user,
            amount=progress.reward_amount,
            reward_balance=progress.mission.reward_balance,
            description=f"Mission {progress.mission.key}",
        )

        progress.claimed_at = timezone.now()
        progress.save(update_fields=['claimed_at', 'updated_at'])

    return amount, progress


def touch_user_streak(user):
    today = timezone.now().date()
    week_key = f"{today.isocalendar().year}{today.isocalendar().week:02d}"

    streak, _ = UserStreak.objects.get_or_create(user=user)

    if streak.last_protect_grant_week != week_key:
        streak.streak_protect_tokens += 1
        streak.last_protect_grant_week = week_key

    if streak.last_active_date is None:
        streak.current_streak = 1
        streak.best_streak = max(streak.best_streak, streak.current_streak)
        streak.last_active_date = today
        streak.save()
        return streak

    gap = (today - streak.last_active_date).days
    if gap == 0:
        streak.save(update_fields=['streak_protect_tokens', 'last_protect_grant_week', 'updated_at'])
        return streak

    if gap == 1:
        streak.current_streak += 1
    else:
        if streak.streak_protect_tokens > 0 and gap == 2:
            streak.streak_protect_tokens -= 1
            streak.current_streak += 1
        else:
            streak.current_streak = 1

    streak.best_streak = max(streak.best_streak, streak.current_streak)
    streak.last_active_date = today
    streak.save()
    return streak
