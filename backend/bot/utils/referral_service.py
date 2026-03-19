from decimal import Decimal
from typing import Optional

from django.conf import settings
from django.db import transaction as db_transaction
from django.db import models
from django.db.models import Sum
from django.utils import timezone

from users.models import User, Referral, ReferralEvent
from wallet.models import Wallet, Transaction


def _resolve_start_param(start_param: str) -> Optional[str]:
    if not start_param:
        return None
    start_param = start_param.strip()
    if not start_param.startswith("ref_"):
        return None
    code = start_param[4:].strip().upper()
    if not code:
        return None
    return code


def register_referral_for_new_user(new_user: User, start_param: Optional[str]):
    invite_code = _resolve_start_param(start_param or "")
    if not invite_code:
        return None

    inviter = User.objects.filter(invite_code=invite_code).first()
    if not inviter:
        return None

    with db_transaction.atomic():
        locked_new_user = User.objects.select_for_update().get(id=new_user.id)

        if locked_new_user.referred_by_id is not None:
            return None

        if inviter.id == locked_new_user.id:
            referral = Referral.objects.create(
                inviter=inviter,
                referred_user=locked_new_user,
                status=Referral.STATUS_INVALID,
                invalid_reason="SELF_REFERRAL",
            )
            ReferralEvent.objects.create(
                referral=referral,
                event_type=ReferralEvent.EVENT_INVALIDATED,
                metadata={"reason": "self_referral"},
            )
            return referral

        locked_new_user.referred_by = inviter
        locked_new_user.save(update_fields=["referred_by"])

        referral = Referral.objects.create(
            inviter=inviter,
            referred_user=locked_new_user,
            status=Referral.STATUS_PENDING,
        )
        User.objects.filter(id=inviter.id).update(referral_count=models.F("referral_count") + 1)

        ReferralEvent.objects.create(
            referral=referral,
            event_type=ReferralEvent.EVENT_REGISTERED,
            metadata={"invite_code": invite_code},
        )

        return referral


def _inviter_daily_reward_count(inviter: User):
    today = timezone.now().date()
    return Referral.objects.filter(
        inviter=inviter,
        status=Referral.STATUS_REWARDED,
        rewarded_at__date=today,
    ).count()


def _inviter_total_rewarded_amount(inviter: User):
    return (
        Referral.objects.filter(
            inviter=inviter,
            status=Referral.STATUS_REWARDED,
        ).aggregate(total=Sum("reward_amount"))["total"]
        or Decimal("0")
    )


def try_process_referral_reward_for_deposit(deposit_tx: Transaction):
    if deposit_tx.transaction_type != "deposit" or deposit_tx.status != "completed":
        return None

    if deposit_tx.amount is None:
        return None

    if Decimal(deposit_tx.amount) < Decimal(str(settings.MIN_DEPOSIT_FOR_REWARD)):
        return None

    referred_user = deposit_tx.user

    with db_transaction.atomic():
        try:
            referral = (
                Referral.objects.select_for_update()
                .select_related("inviter", "referred_user")
                .get(referred_user=referred_user)
            )
        except Referral.DoesNotExist:
            return None

        if referral.status in [Referral.STATUS_INVALID, Referral.STATUS_REWARDED]:
            return None

        if referral.status == Referral.STATUS_PENDING:
            referral.status = Referral.STATUS_QUALIFIED
            referral.qualified_at = timezone.now()
            referral.qualified_deposit_amount = deposit_tx.amount
            referral.save(update_fields=["status", "qualified_at", "qualified_deposit_amount", "updated_at"])

            ReferralEvent.objects.create(
                referral=referral,
                event_type=ReferralEvent.EVENT_QUALIFIED,
                metadata={
                    "deposit_tx_id": deposit_tx.id,
                    "deposit_amount": str(deposit_tx.amount),
                },
            )

        inviter = referral.inviter
        daily_cap = int(getattr(settings, "MAX_REWARDED_REFERRALS_PER_DAY", 20) or 0)
        if daily_cap > 0 and _inviter_daily_reward_count(inviter) >= daily_cap:
            return {"rewarded": False, "reason": "daily_cap"}

        total_cap = int(getattr(settings, "MAX_TOTAL_REFERRAL_REWARDS_PER_USER", 0) or 0)
        reward_amount = Decimal(str(settings.REFERRAL_REWARD))
        if total_cap > 0:
            current_total = _inviter_total_rewarded_amount(inviter)
            if current_total + reward_amount > Decimal(str(total_cap)):
                return {"rewarded": False, "reason": "total_cap"}

        inviter_wallet = Wallet.objects.select_for_update().get(user=inviter)
        inviter_wallet.bonus_balance += reward_amount
        inviter_wallet.save(update_fields=["bonus_balance", "updated_at"])

        referral.status = Referral.STATUS_REWARDED
        referral.reward_amount = reward_amount
        referral.rewarded_at = timezone.now()
        referral.save(update_fields=["status", "reward_amount", "rewarded_at", "updated_at"])

        tx = Transaction.objects.create(
            user=inviter,
            transaction_type="referral_bonus",
            amount=reward_amount,
            status="approved",
            reference=f"referral:{referral.id}",
            description=(
                f"Referral bonus for user {referred_user.first_name} "
                f"(deposit tx #{deposit_tx.id})"
            ),
        )

        ReferralEvent.objects.create(
            referral=referral,
            event_type=ReferralEvent.EVENT_REWARDED,
            metadata={
                "deposit_tx_id": deposit_tx.id,
                "reward_tx_id": tx.id,
                "reward_amount": str(reward_amount),
            },
        )

        return {
            "rewarded": True,
            "inviter": inviter,
            "referral": referral,
            "reward_amount": reward_amount,
        }


def get_user_referral_stats(user: User):
    qs = Referral.objects.filter(inviter=user)
    total = qs.count()
    rewarded = qs.filter(status=Referral.STATUS_REWARDED).count()
    qualified = qs.filter(status__in=[Referral.STATUS_QUALIFIED, Referral.STATUS_REWARDED]).count()
    pending = qs.filter(status=Referral.STATUS_PENDING).count()
    total_bonus = qs.filter(status=Referral.STATUS_REWARDED).aggregate(total=Sum("reward_amount"))["total"] or Decimal("0")

    return {
        "total": total,
        "qualified": qualified,
        "rewarded": rewarded,
        "pending": pending,
        "total_bonus": total_bonus,
    }


def get_referral_overview():
    total = Referral.objects.count()
    pending = Referral.objects.filter(status=Referral.STATUS_PENDING).count()
    qualified = Referral.objects.filter(status=Referral.STATUS_QUALIFIED).count()
    rewarded = Referral.objects.filter(status=Referral.STATUS_REWARDED).count()
    invalid = Referral.objects.filter(status=Referral.STATUS_INVALID).count()
    rewards_distributed = Referral.objects.filter(status=Referral.STATUS_REWARDED).aggregate(total=Sum("reward_amount"))["total"] or Decimal("0")

    top_inviters = list(
        User.objects.filter(sent_referrals__status=Referral.STATUS_REWARDED)
        .annotate(rewarded_count=models.Count("sent_referrals"))
        .order_by("-rewarded_count")[:5]
    )

    return {
        "total": total,
        "pending": pending,
        "qualified": qualified,
        "rewarded": rewarded,
        "invalid": invalid,
        "rewards_distributed": rewards_distributed,
        "top_inviters": top_inviters,
    }
