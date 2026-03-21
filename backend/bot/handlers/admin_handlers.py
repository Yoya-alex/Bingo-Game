from aiogram import Router, F
from decimal import Decimal, InvalidOperation
from datetime import timedelta
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from asgiref.sync import sync_to_async
from django.utils import timezone
from django.db.models import Sum

from django.conf import settings
from users.models import User
from wallet.models import Wallet, Transaction
from game.models import (
    Game,
    LiveEvent,
    MissionTemplate,
    PromoCode,
    PromoCodeRedemption,
    RewardSafetyPolicy,
    Season,
    SystemBalance,
    SystemBalanceLedger,
)
from notifications.models import Notification, NotificationDelivery
from bot.keyboards import (
    admin_main_menu_keyboard,
    engagement_balance_target_keyboard,
    engagement_frontend_visibility_keyboard,
    engagement_event_type_keyboard,
    engagement_main_keyboard,
    engagement_promo_tier_keyboard,
    main_menu_keyboard,
    system_balance_action_keyboard,
    wallet_balance_type_keyboard,
    wallet_direction_keyboard,
)
from bot.utils.admin_helpers import is_admin, get_admin_user
from bot.utils.notification_service import send_admin_notification
from bot.utils.referral_service import try_process_referral_reward_for_deposit, get_referral_overview


router = Router()


class WalletAdjustStates(StatesGroup):
    waiting_for_user_id = State()
    waiting_for_balance_type = State()
    waiting_for_direction = State()
    waiting_for_amount = State()
    waiting_for_reason = State()


class DepositApprovalStates(StatesGroup):
    waiting_for_amount = State()
    waiting_for_confirm = State()


class AnnouncementStates(StatesGroup):
    waiting_for_message = State()
    waiting_for_confirm = State()


class SystemBalanceAdjustStates(StatesGroup):
    waiting_for_amount = State()
    waiting_for_reason = State()


class PromoCreateStates(StatesGroup):
    waiting_for_code = State()
    waiting_for_tier = State()
    waiting_for_amount = State()
    waiting_for_balance = State()
    waiting_for_start_minutes = State()
    waiting_for_duration_minutes = State()
    waiting_for_max_redemptions = State()
    waiting_for_per_user_limit = State()
    waiting_for_frontend_visibility = State()


class EventCreateStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_type = State()
    waiting_for_multiplier = State()
    waiting_for_start_minutes = State()
    waiting_for_duration_minutes = State()


class SeasonCreateStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_days = State()
    waiting_for_top1 = State()
    waiting_for_top2 = State()
    waiting_for_top3 = State()
    waiting_for_participation = State()


class RewardPolicyStates(StatesGroup):
    waiting_for_daily_cap = State()
    waiting_for_cooldown_seconds = State()
    waiting_for_hourly_limit = State()


@sync_to_async
def _get_dashboard_stats():
    """Collect high-level stats for the admin dashboard."""
    from django.db.models import Sum
    
    users_count = User.objects.count()
    pending_deposits = Transaction.objects.filter(
        transaction_type="deposit", status="pending"
    ).count()
    pending_withdrawals = Transaction.objects.filter(
        transaction_type="withdrawal", status="pending"
    ).count()
    active_game = Game.objects.filter(state__in=["waiting", "playing"]).select_related('winner').first()
    active_game_player_count = active_game.cards.count() if active_game else 0
    last_game = Game.objects.select_related('winner').order_by("-created_at").first()
    
    # Calculate total system revenue from all finished games
    total_system_revenue = Game.objects.filter(state='finished').aggregate(
        total=Sum('system_revenue')
    )['total'] or 0

    return {
        "users_count": users_count,
        "pending_deposits": pending_deposits,
        "pending_withdrawals": pending_withdrawals,
        "active_game": active_game,
        "active_game_player_count": active_game_player_count,
        "last_game": last_game,
        "total_system_revenue": total_system_revenue,
    }


@sync_to_async
def _get_pending_deposits(limit: int = 5):
    """Return newest-first pending deposit transactions with user info."""
    qs = (
        Transaction.objects.select_related("user")
        .filter(transaction_type="deposit", status="pending")
        .order_by("-created_at")[:limit]
    )
    return list(qs)


@sync_to_async
def _get_pending_withdrawals(limit: int = 5):
    """Return newest-first pending withdrawal transactions with user info."""
    qs = (
        Transaction.objects.select_related("user")
        .filter(transaction_type="withdrawal", status="pending")
        .order_by("-created_at")[:limit]
    )
    return list(qs)



@sync_to_async
def _get_transaction_or_none(tx_id: int):
    try:
        return Transaction.objects.select_related("user__wallet", "deposit_detail").get(id=tx_id)
    except Transaction.DoesNotExist:
        return None


@sync_to_async
def _approve_deposit_atomic(tx_id: int, admin_telegram_id: int, amount: Decimal):
    """
    Atomically approve a deposit:
    - lock wallet row
    - credit main balance
    - set verified amount
    - mark transaction completed
    - record processed_by when possible
    """
    from django.db import transaction as db_transaction

    with db_transaction.atomic():
        tx = Transaction.objects.select_for_update().get(
            id=tx_id, transaction_type="deposit"
        )

        if tx.status != "pending":
            return False, "Transaction already processed.", None, None

        wallet = Wallet.objects.select_for_update().get(user=tx.user)
        before_main = wallet.main_balance
        before_bonus = wallet.bonus_balance

        wallet.main_balance += amount
        wallet.save()

        admin_user = None
        try:
            admin_user = User.objects.get(telegram_id=admin_telegram_id)
        except User.DoesNotExist:
            admin_user = None

        tx.amount = amount
        base_description = tx.description or "Deposit verified"
        tx.description = f"{base_description} | Admin amount: {amount} Birr"
        tx.status = "completed"
        tx.processed_at = timezone.now()
        tx.processed_by = admin_user
        tx.save()

        return True, "Deposit approved.", (before_main, before_bonus), (
            wallet.main_balance,
            wallet.bonus_balance,
        )


@sync_to_async
def _reject_deposit_atomic(tx_id: int, admin_telegram_id: int):
    """Atomically mark a deposit as rejected without changing balances."""
    from django.db import transaction as db_transaction

    with db_transaction.atomic():
        tx = Transaction.objects.select_for_update().get(
            id=tx_id, transaction_type="deposit"
        )

        if tx.status != "pending":
            return False, "Transaction already processed."

        admin_user = None
        try:
            admin_user = User.objects.get(telegram_id=admin_telegram_id)
        except User.DoesNotExist:
            admin_user = None

        tx.status = "rejected"
        tx.processed_at = timezone.now()
        tx.processed_by = admin_user
        tx.save()

        return True, "Deposit rejected."


@sync_to_async
def _approve_withdrawal_atomic(tx_id: int, admin_telegram_id: int):
    """
    Atomically approve a withdrawal:
    - lock wallet
    - ensure sufficient main balance
    - deduct amount
    - mark transaction approved
    """
    from django.db import transaction as db_transaction

    with db_transaction.atomic():
        tx = Transaction.objects.select_for_update().get(
            id=tx_id, transaction_type="withdrawal"
        )

        if tx.status != "pending":
            return False, "Transaction already processed.", None, None

        wallet = Wallet.objects.select_for_update().get(user=tx.user)
        if wallet.main_balance < tx.amount:
            return False, "Insufficient main balance to approve withdrawal.", None, None

        before_main = wallet.main_balance
        before_bonus = wallet.bonus_balance

        wallet.main_balance -= tx.amount
        wallet.save()

        admin_user = None
        try:
            admin_user = User.objects.get(telegram_id=admin_telegram_id)
        except User.DoesNotExist:
            admin_user = None

        tx.status = "approved"
        tx.processed_at = timezone.now()
        tx.processed_by = admin_user
        tx.save()

        return True, "Withdrawal approved.", (before_main, before_bonus), (
            wallet.main_balance,
            wallet.bonus_balance,
        )


@sync_to_async
def _reject_withdrawal_atomic(tx_id: int, admin_telegram_id: int):
    """Atomically reject a withdrawal (no balance changes)."""
    from django.db import transaction as db_transaction

    with db_transaction.atomic():
        tx = Transaction.objects.select_for_update().get(
            id=tx_id, transaction_type="withdrawal"
        )

        if tx.status != "pending":
            return False, "Transaction already processed."

        admin_user = None
        try:
            admin_user = User.objects.get(telegram_id=admin_telegram_id)
        except User.DoesNotExist:
            admin_user = None

        tx.status = "rejected"
        tx.processed_at = timezone.now()
        tx.processed_by = admin_user
        tx.save()

        return True, "Withdrawal rejected."


@sync_to_async
def _get_wallet_by_telegram_id_or_none(telegram_id: int):
    """Fetch wallet and user by telegram_id, if it exists."""
    try:
        return Wallet.objects.select_related("user").get(user__telegram_id=telegram_id)
    except Wallet.DoesNotExist:
        return None


@sync_to_async
def _adjust_wallet_atomic(
    target_telegram_id: int,
    balance_type: str,
    direction: str,
    amount: Decimal,
    reason: str,
    admin_telegram_id: int,
):
    """
    Atomically adjust a wallet and create an admin_adjustment transaction.

    balance_type: 'main' or 'bonus'
    direction: 'add' or 'subtract'
    """
    from django.db import transaction as db_transaction

    with db_transaction.atomic():
        amount = Decimal(amount)
        try:
            wallet = (
                Wallet.objects.select_for_update()
                .select_related("user")
                .get(user__telegram_id=target_telegram_id)
            )
        except Wallet.DoesNotExist:
            return False, "Wallet not found for this Telegram ID.", None, None, None

        before_main = wallet.main_balance
        before_bonus = wallet.bonus_balance

        if balance_type == "main":
            if direction == "add":
                wallet.main_balance += amount
            else:
                if wallet.main_balance < amount:
                    return False, "Insufficient main balance for deduction.", None, None, None
                wallet.main_balance -= amount
        else:
            if direction == "add":
                wallet.bonus_balance += amount
            else:
                if wallet.bonus_balance < amount:
                    return False, "Insufficient bonus balance for deduction.", None, None, None
                wallet.bonus_balance -= amount

        wallet.save()

        admin_user = None
        try:
            admin_user = User.objects.get(telegram_id=admin_telegram_id)
        except User.DoesNotExist:
            admin_user = None

        # Record admin adjustment as a separate transaction (immutable ledger)
        Transaction.objects.create(
            user=wallet.user,
            transaction_type="admin_adjustment",
            amount=amount,
            status="approved",
            description=f"Admin adjustment ({direction} {balance_type}) - {reason}",
            processed_at=timezone.now(),
            processed_by=admin_user,
        )

        return True, "Wallet adjusted successfully.", (before_main, before_bonus), (
            wallet.main_balance,
            wallet.bonus_balance,
        ), wallet.user


@sync_to_async
def _get_wallet_stats():
    """Aggregate high-level wallet/transaction statistics for /wallet_stats."""
    qs = Transaction.objects.filter(status__in=["approved", "completed"])

    def _sum_for(tx_type: str):
        return (
            qs.filter(transaction_type=tx_type).aggregate(total=Sum("amount"))[
                "total"
            ]
            or 0
        )

    total_deposits = _sum_for("deposit")
    total_withdrawals = _sum_for("withdrawal")
    total_game_wins = _sum_for("game_win")

    pending_deposits = Transaction.objects.filter(
        transaction_type="deposit", status="pending"
    ).count()
    pending_withdrawals = Transaction.objects.filter(
        transaction_type="withdrawal", status="pending"
    ).count()

    # Simple net revenue estimate: deposits - withdrawals - game winnings
    net_revenue = total_deposits - total_withdrawals - total_game_wins

    return {
        "total_deposits": total_deposits,
        "total_withdrawals": total_withdrawals,
        "total_game_wins": total_game_wins,
        "net_revenue": net_revenue,
        "pending_deposits": pending_deposits,
        "pending_withdrawals": pending_withdrawals,
    }


@sync_to_async
def _get_system_balance_overview(limit: int = 5):
    snapshot = SystemBalance.objects.first()
    current_balance = snapshot.balance if snapshot else Decimal("0.00")

    total_credits = (
        SystemBalanceLedger.objects.filter(direction='credit').aggregate(total=Sum('amount'))['total']
        or Decimal("0.00")
    )
    total_debits = (
        SystemBalanceLedger.objects.filter(direction='debit').aggregate(total=Sum('amount'))['total']
        or Decimal("0.00")
    )

    recent_entries = list(
        SystemBalanceLedger.objects.select_related('game').order_by('-created_at')[:limit]
    )

    return {
        "current_balance": current_balance,
        "total_credits": total_credits,
        "total_debits": total_debits,
        "entries_count": SystemBalanceLedger.objects.count(),
        "recent_entries": recent_entries,
    }


@sync_to_async
def _adjust_system_balance_atomic(action: str, amount: Decimal, reason: str, admin_telegram_id: int):
    amount = Decimal(amount)

    admin_user = None
    try:
        admin_user = User.objects.get(telegram_id=admin_telegram_id)
    except User.DoesNotExist:
        admin_user = None

    if action == "cash_in":
        direction = "debit"
        human_action = "Cash In"
    elif action == "cash_out":
        direction = "credit"
        human_action = "Cash Out"
    else:
        return False, "Invalid action.", None

    metadata = {
        "action": action,
        "admin_telegram_id": admin_telegram_id,
        "admin_user_id": admin_user.id if admin_user else None,
    }

    entry = SystemBalanceLedger.append_entry(
        event_type='admin_adjustment',
        direction=direction,
        amount=amount,
        description=f"{human_action} by admin: {reason}",
        metadata=metadata,
    )

    return True, "System balance updated.", entry


def _format_system_balance_text(data):
    lines = [
        "<b>💼 System Balance</b>",
        "",
        f"💰 Current Balance: {data['current_balance']} Birr",
        f"📥 Total Credits: {data['total_credits']} Birr",
        f"📤 Total Debits: {data['total_debits']} Birr",
        f"📜 Ledger Entries: {data['entries_count']}",
        "",
        "<b>Recent Ledger Activity:</b>",
    ]

    recent_entries = data.get("recent_entries") or []
    if not recent_entries:
        lines.append("No ledger entries yet.")
    else:
        for entry in recent_entries:
            game_ref = f"Game #{entry.game_id}" if entry.game_id else "Manual"
            lines.append(
                f"• #{entry.id} {entry.event_type} | {entry.direction} {entry.amount} Birr | "
                f"Bal: {entry.balance_before} → {entry.balance_after} | {game_ref} | "
                f"{entry.created_at:%Y-%m-%d %H:%M}"
            )

    lines.extend([
        "",
        "Cash In will subtract from system balance.",
        "Cash Out will add to system balance.",
    ])
    return "\n".join(lines)


@sync_to_async
def _get_active_users_for_notifications():
    """Return active non-admin users with telegram IDs for broadcast delivery."""
    return list(
        User.objects.filter(is_active=True, is_admin=False)
        .exclude(telegram_id__isnull=True)
        .only("id", "telegram_id")
    )


@sync_to_async
def _create_announcement_notification(admin_telegram_id: int, message: str, total: int):
    """Create persisted notification record before broadcasting."""
    admin_user = None
    try:
        admin_user = User.objects.get(telegram_id=admin_telegram_id)
    except User.DoesNotExist:
        admin_user = None

    return Notification.objects.create(
        notification_type="admin_announcement",
        title="Admin Announcement",
        message=message,
        status="sending",
        total_recipients=total,
        created_by=admin_user,
    )


@sync_to_async
def _create_notification_delivery(
    notification_id: int,
    user_id: int,
    status: str,
    error_message: str = "",
):
    """Create delivery log for one user."""
    delivered_at = timezone.now() if status == "delivered" else None
    return NotificationDelivery.objects.create(
        notification_id=notification_id,
        user_id=user_id,
        status=status,
        error_message=error_message,
        delivered_at=delivered_at,
    )


@sync_to_async
def _finalize_announcement_notification(
    notification_id: int,
    delivered_count: int,
    failed_count: int,
):
    """Finalize aggregate counters and status after broadcast loop."""
    final_status = "completed" if delivered_count > 0 else "failed"
    Notification.objects.filter(id=notification_id).update(
        delivered_count=delivered_count,
        failed_count=failed_count,
        status=final_status,
        sent_at=timezone.now(),
    )


async def _ensure_admin(message_or_callback) -> bool:
    """
    Reusable guard: return True if caller is admin, else send access denied message.
    """
    from_user = (
        message_or_callback.from_user
        if hasattr(message_or_callback, "from_user")
        else message_or_callback.message.from_user
    )
    if not await is_admin(from_user.id):
        text = "❌ Admin access only.\nThis section is restricted to administrators."
        if isinstance(message_or_callback, Message):
            await message_or_callback.answer(text)
        else:
            await message_or_callback.answer(text, show_alert=True)
        return False
    return True


@router.message(Command("admin"))
async def admin_entry(message: Message):
    """Entry point for admin mode: /admin."""
    if not await _ensure_admin(message):
        return

    stats = await _get_dashboard_stats()
    active_game = stats["active_game"]

    game_text = "No active game."
    if active_game:
        game_text = (
            f"Game #{active_game.id} - State: {active_game.state.upper()} - "
            f"Players: {stats['active_game_player_count']}"
        )

    text = (
        "<b>👮 ADMIN DASHBOARD</b>\n\n"
        f"👥 Users: {stats['users_count']}\n"
        f"💰 Pending Deposits: {stats['pending_deposits']}\n"
        f"🏧 Pending Withdrawals: {stats['pending_withdrawals']}\n"
        f"🎮 {game_text}\n\n"
        "Use the admin menu below to manage the system."
    )
    await message.answer(text, reply_markup=admin_main_menu_keyboard())


@router.message(F.text == "📊 Dashboard")
async def admin_dashboard(message: Message):
    """Show dashboard summary with bot game information."""
    if not await _ensure_admin(message):
        return

    stats = await _get_dashboard_stats()
    active_game = stats["active_game"]
    last_game = stats["last_game"]

    active_text = "None"
    if active_game:
        total_players = stats['active_game_player_count']
        if active_game.has_bots:
            real_players = active_game.real_players_count
            fake_players = total_players - real_players
            active_text = (
                f"#{active_game.id} ({active_game.state.upper()})\n"
                f"   👤 Real: {real_players} | 🤖 Fake: {fake_players} | Total: {total_players}"
            )
        else:
            active_text = (
                f"#{active_game.id} ({active_game.state.upper()}) "
                f"Players: {total_players}"
            )

    last_text = "None"
    if last_game:
        winner_type = "🤖 Bot" if last_game.winner and last_game.winner.telegram_id >= 9000000000 else "👤 Real User"
        winner_name = last_game.winner.first_name if last_game.winner else "No winner"
        
        if last_game.has_bots:
            last_text = (
                f"#{last_game.id} ({last_game.state.upper()})\n"
                f"   Winner: {winner_name} ({winner_type})\n"
                f"   Total Prize: {last_game.prize_amount} Birr\n"
                f"   Real Prize: {last_game.real_prize_amount} Birr (from {last_game.real_players_count} real players)\n"
                f"   🤖 Had Fake Users: Yes"
            )
        else:
            last_text = (
                f"#{last_game.id} ({last_game.state.upper()})\n"
                f"   Winner: {winner_name}\n"
                f"   Prize: {last_game.prize_amount} Birr"
            )

    text = (
        "<b>📊 ADMIN DASHBOARD</b>\n\n"
        f"👥 Total Users: {stats['users_count']}\n"
        f"💰 Pending Deposits: {stats['pending_deposits']}\n"
        f"🏧 Pending Withdrawals: {stats['pending_withdrawals']}\n"
        f"💵 System Revenue: {stats['total_system_revenue']} Birr\n\n"
        f"🎮 Active Game:\n{active_text}\n\n"
        f"🕹 Last Game:\n{last_text}"
    )
    await message.answer(text, reply_markup=admin_main_menu_keyboard(), parse_mode="HTML")


@router.message(F.text == "💰 Deposits")
async def admin_deposits_menu(message: Message):
    """Show summary of pending deposits."""
    if not await _ensure_admin(message):
        return

    pending = await _get_pending_deposits()

    if not pending:
        await message.answer(
            "✅ No pending deposits.\nAll deposit requests have been processed.",
            reply_markup=admin_main_menu_keyboard(),
        )
        return

    lines = ["<b>💰 Pending Deposits (latest)</b>\n"]
    buttons = []
    for tx in pending:
        u = tx.user
        amount_text = f"{tx.amount} Birr" if tx.amount is not None else "Pending"
        lines.append(
            f"#{tx.id} • {u.first_name} (@{u.username or '—'})\n"
            f"Amount: {amount_text} • {tx.created_at:%Y-%m-%d %H:%M}"
        )
        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"Review #{tx.id}", callback_data=f"adm_dep:view:{tx.id}"
                )
            ]
        )

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer("\n".join(lines), reply_markup=keyboard)


@router.message(F.text.regexp(r"^/adm_dep_(\d+)$"))
async def admin_deposit_detail(message: Message):
    """Show detail for a specific pending deposit by ID."""
    if not await _ensure_admin(message):
        return

    try:
        tx_id = int(message.text.split("_")[-1])
    except (TypeError, ValueError):
        await message.answer("❌ Invalid deposit reference.")
        return

    tx = await _get_transaction_or_none(tx_id)
    if not tx or tx.transaction_type != "deposit":
        await message.answer("❌ Deposit not found.")
        return

    user = tx.user
    status = tx.status.upper()
    deposit_detail = getattr(tx, "deposit_detail", None)
    confirmation_text = deposit_detail.payment_proof if deposit_detail else "—"
    amount_text = f"{tx.amount} Birr" if tx.amount is not None else "Pending"

    text = (
        f"<b>💰 Deposit #{tx.id}</b>\n\n"
        f"👤 User: {user.first_name} (@{user.username or '—'})\n"
        f"🆔 Telegram ID: {user.telegram_id}\n"
        f"💵 Amount: {amount_text}\n"
        f"📅 Created: {tx.created_at:%Y-%m-%d %H:%M}\n"
        f"📄 Status: {status}\n\n"
        f"🧾 Confirmation Text:\n{confirmation_text}\n\n"
        "Approve or reject this deposit?\n\n"
        "Use:\n"
        f"/adm_dep_approve_{tx.id}\n"
        f"/adm_dep_reject_{tx.id}"
    )
    await message.answer(text, reply_markup=admin_main_menu_keyboard())


@router.callback_query(F.data.startswith("adm_dep:view:"))
async def admin_deposit_detail_inline(callback: CallbackQuery):
    """Show deposit detail via inline button."""
    if not await _ensure_admin(callback):
        await callback.answer()
        return

    try:
        tx_id = int(callback.data.split(":")[-1])
    except (TypeError, ValueError):
        await callback.answer("Invalid deposit reference", show_alert=True)
        return

    tx = await _get_transaction_or_none(tx_id)
    if not tx or tx.transaction_type != "deposit":
        await callback.answer("Deposit not found", show_alert=True)
        return

    user = tx.user
    status = tx.status.upper()
    deposit_detail = getattr(tx, "deposit_detail", None)
    confirmation_text = deposit_detail.payment_proof if deposit_detail else "—"
    amount_text = f"{tx.amount} Birr" if tx.amount is not None else "Pending"

    text = (
        f"<b>💰 Deposit #{tx.id}</b>\n\n"
        f"👤 User: {user.first_name} (@{user.username or '—'})\n"
        f"🆔 Telegram ID: {user.telegram_id}\n"
        f"💵 Amount: {amount_text}\n"
        f"📅 Created: {tx.created_at:%Y-%m-%d %H:%M}\n"
        f"📄 Status: {status}\n\n"
        f"🧾 Confirmation Text:\n{confirmation_text}\n\n"
        "Approve or reject this deposit?"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Approve",
                    callback_data=f"adm_dep:approve:{tx.id}",
                ),
                InlineKeyboardButton(
                    text="❌ Reject",
                    callback_data=f"adm_dep:reject:{tx.id}",
                ),
            ]
        ]
    )

    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()


@router.message(F.text.regexp(r"^/adm_dep_approve_(\d+)$"))
async def admin_deposit_approve_confirm(message: Message, state: FSMContext):
    """Request verified amount before approving a deposit."""
    if not await _ensure_admin(message):
        return

    try:
        tx_id = int(message.text.split("_")[-1])
    except (TypeError, ValueError):
        await message.answer("❌ Invalid deposit reference.")
        return

    tx = await _get_transaction_or_none(tx_id)
    if not tx or tx.transaction_type != "deposit":
        await message.answer("❌ Deposit not found.")
        return

    user = tx.user
    deposit_detail = getattr(tx, "deposit_detail", None)
    confirmation_text = deposit_detail.payment_proof if deposit_detail else "—"
    await state.update_data(tx_id=tx.id)
    await state.set_state(DepositApprovalStates.waiting_for_amount)
    text = (
        "<b>✅ Approve Deposit</b>\n\n"
        f"User: {user.first_name} (@{user.username or '—'})\n"
        f"Transaction ID: #{tx.id}\n\n"
        f"🧾 Confirmation Text:\n{confirmation_text}\n\n"
        "Please enter the verified deposit amount (in Birr).\n"
        "Send 'cancel' to abort."
    )
    await message.answer(text)


@router.callback_query(F.data.startswith("adm_dep:approve:"))
async def admin_deposit_approve_confirm_inline(callback: CallbackQuery, state: FSMContext):
    """Request verified amount before approving a deposit via inline button."""
    if not await _ensure_admin(callback):
        await callback.answer()
        return

    try:
        tx_id = int(callback.data.split(":")[-1])
    except (TypeError, ValueError):
        await callback.answer("Invalid deposit reference", show_alert=True)
        return

    tx = await _get_transaction_or_none(tx_id)
    if not tx or tx.transaction_type != "deposit":
        await callback.answer("Deposit not found", show_alert=True)
        return

    user = tx.user
    deposit_detail = getattr(tx, "deposit_detail", None)
    confirmation_text = deposit_detail.payment_proof if deposit_detail else "—"
    await state.update_data(tx_id=tx.id)
    await state.set_state(DepositApprovalStates.waiting_for_amount)
    text = (
        "<b>✅ Approve Deposit</b>\n\n"
        f"User: {user.first_name} (@{user.username or '—'})\n"
        f"Transaction ID: #{tx.id}\n\n"
        f"🧾 Confirmation Text:\n{confirmation_text}\n\n"
        "Please enter the verified deposit amount (in Birr)."
    )

    await callback.message.answer(text)
    await callback.answer()


@router.message(F.text.regexp(r"^/adm_dep_approve_yes_(\d+)$"))
async def admin_deposit_approve_execute(message: Message, state: FSMContext):
    """Handle legacy approve command by requesting the verified amount."""
    if not await _ensure_admin(message):
        return

    try:
        tx_id = int(message.text.split("_")[-1])
    except (TypeError, ValueError):
        await message.answer("❌ Invalid deposit reference.")
        return

    await state.update_data(tx_id=tx_id)
    await state.set_state(DepositApprovalStates.waiting_for_amount)
    await message.answer(
        "Please enter the verified deposit amount (in Birr).\n"
        "Send 'cancel' to abort."
    )


@router.callback_query(F.data.startswith("adm_dep:approve_yes:"))
async def admin_deposit_approve_execute_inline(callback: CallbackQuery, state: FSMContext):
    """Handle legacy inline approve by requesting the verified amount."""
    if not await _ensure_admin(callback):
        await callback.answer()
        return

    try:
        tx_id = int(callback.data.split(":")[-1])
    except (TypeError, ValueError):
        await callback.answer("Invalid deposit reference", show_alert=True)
        return

    await state.update_data(tx_id=tx_id)
    await state.set_state(DepositApprovalStates.waiting_for_amount)
    await callback.message.answer(
        "Please enter the verified deposit amount (in Birr).\n"
        "Send 'cancel' to abort."
    )
    await callback.answer()


@router.message(DepositApprovalStates.waiting_for_amount)
async def admin_deposit_amount_submit(message: Message, state: FSMContext):
    """Capture verified amount and request approve/reject confirmation."""
    if not await _ensure_admin(message):
        return

    text = (message.text or "").strip().lower()
    if text in {"cancel", "stop", "exit"}:
        await state.clear()
        await message.answer("✅ Deposit approval cancelled.")
        return

    try:
        amount = Decimal(message.text)
    except (TypeError, InvalidOperation):
        await message.answer("❌ Please enter a valid amount in Birr.")
        return

    if amount <= 0:
        await message.answer("❌ Amount must be greater than 0.")
        return

    if amount < settings.MIN_DEPOSIT:
        await message.answer(
            f"❌ Minimum deposit is {settings.MIN_DEPOSIT} Birr.\n"
            f"Please enter an amount ≥ {settings.MIN_DEPOSIT}."
        )
        return

    data = await state.get_data()
    tx_id = data.get("tx_id")
    if not tx_id:
        await message.answer("❌ Deposit reference missing. Please retry the approval.")
        await state.clear()
        return

    await state.update_data(amount=str(amount))
    await state.set_state(DepositApprovalStates.waiting_for_confirm)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Approve",
                    callback_data=f"adm_dep:confirm_amount:approve:{tx_id}",
                ),
                InlineKeyboardButton(
                    text="❌ Reject",
                    callback_data=f"adm_dep:confirm_amount:reject:{tx_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Cancel",
                    callback_data=f"adm_dep:confirm_amount:cancel:{tx_id}",
                )
            ],
        ]
    )

    await message.answer(
        f"Verified amount recorded: {amount} Birr.\n"
        "Approve or reject this deposit?",
        reply_markup=keyboard,
    )


@router.callback_query(F.data.startswith("adm_dep:confirm_amount:"))
async def admin_deposit_amount_confirm(callback: CallbackQuery, state: FSMContext):
    """Approve or reject a deposit after amount entry."""
    if not await _ensure_admin(callback):
        await callback.answer()
        return

    parts = callback.data.split(":")
    if len(parts) != 4:
        await callback.answer("Invalid action", show_alert=True)
        return

    action = parts[2]
    try:
        tx_id = int(parts[3])
    except (TypeError, ValueError):
        await callback.answer("Invalid deposit reference", show_alert=True)
        return

    data = await state.get_data()
    amount_text = data.get("amount")
    state_tx_id = data.get("tx_id")
    if not amount_text or str(state_tx_id) != str(tx_id):
        await callback.message.answer("❌ Approval context expired. Please re-enter the amount.")
        await state.clear()
        await callback.answer()
        return

    if action == "cancel":
        await state.clear()
        await callback.message.answer("✅ Action cancelled.")
        await callback.answer()
        return

    if action == "reject":
        success, info = await _reject_deposit_atomic(tx_id, callback.from_user.id)
        if not success:
            await callback.message.answer(f"❌ {info}")
            await state.clear()
            await callback.answer()
            return

        tx = await _get_transaction_or_none(tx_id)
        user = tx.user if tx else None

        await callback.message.answer(
            f"✅ Deposit #{tx_id} rejected.",
            reply_markup=admin_main_menu_keyboard(),
        )

        if user:
            try:
                await callback.message.bot.send_message(
                    user.telegram_id,
                    f"❌ Your deposit (Transaction #{tx.id}) has been <b>rejected</b>.\n"
                    "Please contact support if you believe this is an error.",
                )
            except Exception:
                pass

        await send_admin_notification(
            callback.message.bot,
            text=(
                "👮 <b>Admin Action</b>\n\n"
                f"Admin: @{callback.from_user.username or callback.from_user.id}\n"
                f"Action: Rejected deposit #{tx_id}\n"
                f"Time: {timezone.now():%Y-%m-%d %H:%M}"
            ),
        )

        await state.clear()
        await callback.answer()
        return

    if action != "approve":
        await callback.answer("Unknown action", show_alert=True)
        return

    try:
        amount = Decimal(amount_text)
    except (TypeError, InvalidOperation):
        await callback.message.answer("❌ Invalid amount saved. Please re-enter the amount.")
        await state.clear()
        await callback.answer()
        return

    success, info, before, after = await _approve_deposit_atomic(
        tx_id, callback.from_user.id, amount
    )
    if not success:
        await callback.message.answer(f"❌ {info}")
        await state.clear()
        await callback.answer()
        return

    tx = await _get_transaction_or_none(tx_id)
    user = tx.user if tx else None

    reward_result = None
    if tx:
        reward_result = await sync_to_async(try_process_referral_reward_for_deposit)(tx)

    await callback.message.answer(
        f"✅ Deposit #{tx_id} completed.\n"
        f"User: {user.first_name if user else 'Unknown'}\n"
        f"Amount: {tx.amount if tx else '—'} Birr\n"
        f"Balance: {before[0]} → {after[0]} Birr (main)",
        reply_markup=admin_main_menu_keyboard(),
    )

    if user:
        try:
            await callback.message.bot.send_message(
                user.telegram_id,
                f"💰 Your deposit of {tx.amount} Birr (Transaction #{tx.id}) "
                f"has been <b>completed</b>.",
            )
        except Exception:
            pass

    if reward_result and reward_result.get("rewarded"):
        inviter = reward_result["inviter"]
        reward_amount = reward_result["reward_amount"]
        try:
            await callback.message.bot.send_message(
                inviter.telegram_id,
                "🎉 <b>Referral Reward Earned!</b>\n\n"
                "Your invited friend has completed their first qualifying deposit.\n\n"
                f"Reward: +{reward_amount} bonus credits\n\n"
                "Added to your bonus balance.",
            )
        except Exception:
            pass

    await send_admin_notification(
        callback.message.bot,
        text=(
            "👮 <b>Admin Action</b>\n\n"
            f"Admin: @{callback.from_user.username or callback.from_user.id}\n"
            f"Action: Completed deposit #{tx_id}\n"
            f"User: @{user.username or user.telegram_id if user else 'Unknown'}\n"
            f"Amount: {tx.amount if tx else '—'} Birr\n"
            f"Time: {timezone.now():%Y-%m-%d %H:%M}"
        ),
    )

    await state.clear()
    await callback.answer()


@sync_to_async
def _admin_invalidate_referral(referral_id: int, reason: str):
    from users.models import Referral, ReferralEvent

    try:
        referral = Referral.objects.select_related("inviter", "referred_user").get(id=referral_id)
    except Referral.DoesNotExist:
        return False, "Referral not found", None

    if referral.status == Referral.STATUS_REWARDED:
        return False, "Cannot invalidate rewarded referral", referral

    referral.status = Referral.STATUS_INVALID
    referral.invalid_reason = reason or "MANUAL_INVALIDATION"
    referral.save(update_fields=["status", "invalid_reason", "updated_at"])
    ReferralEvent.objects.create(
        referral=referral,
        event_type=ReferralEvent.EVENT_INVALIDATED,
        metadata={"reason": referral.invalid_reason, "source": "admin"},
    )
    return True, "Referral invalidated", referral


@sync_to_async
def _admin_manual_referral_reward(referral_id: int, amount: Decimal):
    from users.models import Referral, ReferralEvent
    from django.db import transaction as db_transaction

    with db_transaction.atomic():
        try:
            referral = Referral.objects.select_for_update().select_related("inviter").get(id=referral_id)
        except Referral.DoesNotExist:
            return False, "Referral not found", None

        if referral.status == Referral.STATUS_REWARDED:
            return False, "Referral already rewarded", referral

        inviter_wallet = Wallet.objects.select_for_update().get(user=referral.inviter)
        inviter_wallet.bonus_balance += amount
        inviter_wallet.save(update_fields=["bonus_balance", "updated_at"])

        referral.status = referral.STATUS_REWARDED
        referral.reward_amount = amount
        referral.rewarded_at = timezone.now()
        if not referral.qualified_at:
            referral.qualified_at = timezone.now()
        referral.save(update_fields=["status", "reward_amount", "rewarded_at", "qualified_at", "updated_at"])

        tx = Transaction.objects.create(
            user=referral.inviter,
            transaction_type="referral_bonus",
            amount=amount,
            status="approved",
            reference=f"referral:{referral.id}",
            description=f"Manual referral bonus for referral #{referral.id}",
        )
        ReferralEvent.objects.create(
            referral=referral,
            event_type=ReferralEvent.EVENT_REWARDED,
            metadata={"source": "admin", "reward_tx_id": tx.id, "reward_amount": str(amount)},
        )

        return True, "Referral rewarded manually", referral


@router.message(Command("referral_stats"))
async def admin_referral_stats(message: Message):
    if not await _ensure_admin(message):
        return

    overview = await sync_to_async(get_referral_overview)()
    top = overview["top_inviters"]
    if top:
        top_text = "\n".join(
            [f"{idx + 1}. {u.first_name} (@{u.username or '—'}) — {u.rewarded_count}" for idx, u in enumerate(top)]
        )
    else:
        top_text = "No rewarded inviters yet"

    text = (
        "<b>📊 Referral Analytics</b>\n\n"
        f"Total referrals: {overview['total']}\n"
        f"Pending referrals: {overview['pending']}\n"
        f"Qualified referrals: {overview['qualified']}\n"
        f"Rewarded referrals: {overview['rewarded']}\n"
        f"Invalid referrals: {overview['invalid']}\n"
        f"Rewards distributed: {overview['rewards_distributed']} credits\n\n"
        f"<b>🏆 Top Inviters</b>\n{top_text}"
    )
    await message.answer(text, reply_markup=admin_main_menu_keyboard())


@router.message(F.text.regexp(r"^/referral_invalidate_(\d+)$"))
async def admin_referral_invalidate(message: Message):
    if not await _ensure_admin(message):
        return

    try:
        referral_id = int(message.text.split("_")[-1])
    except (TypeError, ValueError):
        await message.answer("❌ Invalid referral reference")
        return

    success, info, _ = await _admin_invalidate_referral(referral_id, "MANUAL_INVALIDATION")
    if not success:
        await message.answer(f"❌ {info}")
        return
    await message.answer(f"✅ {info} (#{referral_id})", reply_markup=admin_main_menu_keyboard())


@router.message(F.text.regexp(r"^/referral_reward_(\d+)_(\d+(?:\.\d{1,2})?)$"))
async def admin_referral_manual_reward(message: Message):
    if not await _ensure_admin(message):
        return

    import re

    match = re.match(r"^/referral_reward_(\d+)_(\d+(?:\.\d{1,2})?)$", message.text or "")
    if not match:
        await message.answer("❌ Invalid command format")
        return

    referral_id = int(match.group(1))
    amount = Decimal(match.group(2))
    success, info, _ = await _admin_manual_referral_reward(referral_id, amount)
    if not success:
        await message.answer(f"❌ {info}")
        return
    await message.answer(f"✅ {info} (#{referral_id}, +{amount})", reply_markup=admin_main_menu_keyboard())


@router.message(F.text.regexp(r"^/adm_dep_reject_(\d+)$"))
async def admin_deposit_reject_execute(message: Message):
    """Reject a deposit with confirmation."""
    if not await _ensure_admin(message):
        return

    admin_telegram_id = message.from_user.id
    try:
        tx_id = int(message.text.split("_")[-1])
    except (TypeError, ValueError):
        await message.answer("❌ Invalid deposit reference.")
        return

    success, info = await _reject_deposit_atomic(tx_id, admin_telegram_id)
    if not success:
        await message.answer(f"❌ {info}")
        return

    tx = await _get_transaction_or_none(tx_id)
    user = tx.user if tx else None

    await message.answer(
        f"✅ Deposit #{tx_id} rejected.",
        reply_markup=admin_main_menu_keyboard(),
    )

    if user:
        try:
            await message.bot.send_message(
                user.telegram_id,
                f"❌ Your deposit (Transaction #{tx.id}) has been <b>rejected</b>.\n"
                "Please contact support if you believe this is an error.",
            )
        except Exception:
            pass

    await send_admin_notification(
        message.bot,
        text=(
            "👮 <b>Admin Action</b>\n\n"
            f"Admin: @{message.from_user.username or message.from_user.id}\n"
            f"Action: Rejected deposit #{tx_id}\n"
            f"Time: {timezone.now():%Y-%m-%d %H:%M}"
        ),
    )


@router.callback_query(F.data.startswith("adm_dep:reject:"))
async def admin_deposit_reject_execute_inline(callback: CallbackQuery):
    """Reject a deposit via inline button."""
    if not await _ensure_admin(callback):
        await callback.answer()
        return

    admin_telegram_id = callback.from_user.id
    try:
        tx_id = int(callback.data.split(":")[-1])
    except (TypeError, ValueError):
        await callback.answer("Invalid deposit reference", show_alert=True)
        return

    success, info = await _reject_deposit_atomic(tx_id, admin_telegram_id)
    if not success:
        await callback.message.answer(f"❌ {info}")
        await callback.answer()
        return

    tx = await _get_transaction_or_none(tx_id)
    user = tx.user if tx else None

    await callback.message.answer(
        f"✅ Deposit #{tx_id} rejected.",
        reply_markup=admin_main_menu_keyboard(),
    )

    if user:
        try:
            await callback.message.bot.send_message(
                user.telegram_id,
                f"❌ Your deposit (Transaction #{tx.id}) has been <b>rejected</b>.\n"
                "Please contact support if you believe this is an error.",
            )
        except Exception:
            pass

    await send_admin_notification(
        callback.message.bot,
        text=(
            "👮 <b>Admin Action</b>\n\n"
            f"Admin: @{callback.from_user.username or callback.from_user.id}\n"
            f"Action: Rejected deposit #{tx_id}\n"
            f"Time: {timezone.now():%Y-%m-%d %H:%M}"
        ),
    )

    await callback.answer()


@router.callback_query(F.data.startswith("adm_dep:cancel:"))
async def admin_deposit_cancel_inline(callback: CallbackQuery):
    """Cancel an inline deposit action."""
    if not await _ensure_admin(callback):
        await callback.answer()
        return

    await callback.message.answer("✅ Action cancelled.")
    await callback.answer()


@router.message(F.text == "🏧 Withdrawals")
async def admin_withdrawals_menu(message: Message):
    """Show summary of pending withdrawals."""
    if not await _ensure_admin(message):
        return

    pending = await _get_pending_withdrawals()

    if not pending:
        await message.answer(
            "✅ No pending withdrawals.\nAll withdrawal requests have been processed.",
            reply_markup=admin_main_menu_keyboard(),
        )
        return

    lines = ["<b>🏧 Pending Withdrawals (latest)</b>\n"]
    buttons = []
    for tx in pending:
        u = tx.user
        lines.append(
            f"#{tx.id} • {u.first_name} (@{u.username or '—'})\n"
            f"Amount: {tx.amount} • {tx.created_at:%Y-%m-%d %H:%M}"
        )
        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"Review #{tx.id}", callback_data=f"adm_wd:view:{tx.id}"
                )
            ]
        )

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer("\n".join(lines), reply_markup=keyboard)


@router.message(F.text.regexp(r"^/adm_wd_(\d+)$"))
async def admin_withdrawal_detail(message: Message):
    """Show detail for a specific pending withdrawal by ID."""
    if not await _ensure_admin(message):
        return

    try:
        tx_id = int(message.text.split("_")[-1])
    except (TypeError, ValueError):
        await message.answer("❌ Invalid withdrawal reference.")
        return

    tx = await _get_transaction_or_none(tx_id)
    if not tx or tx.transaction_type != "withdrawal":
        await message.answer("❌ Withdrawal not found.")
        return

    user = tx.user
    status = tx.status.upper()

    wallet = user.wallet
    risk_notes = []
    # Simple risk hints
    if tx.amount and tx.amount > 1000:  # example threshold
        risk_notes.append("• Large amount above risk threshold.")
    if wallet.main_balance < tx.amount:
        risk_notes.append("• Withdrawal exceeds current main balance!")

    risk_text = "\n".join(risk_notes) if risk_notes else "No obvious risk flags."

    text = (
        f"<b>🏧 Withdrawal #{tx.id}</b>\n\n"
        f"👤 User: {user.first_name} (@{user.username or '—'})\n"
        f"🆔 Telegram ID: {user.telegram_id}\n"
        f"💵 Amount: {tx.amount} Birr\n"
        f"📅 Created: {tx.created_at:%Y-%m-%d %H:%M}\n"
        f"💰 Main Balance: {wallet.main_balance}\n"
        f"📄 Status: {status}\n\n"
        f"<b>Risk Notes:</b>\n{risk_text}\n\n"
        "Approve only after you have completed the external payment.\n\n"
        "Use:\n"
        f"/adm_wd_approve_{tx.id}\n"
        f"/adm_wd_reject_{tx.id}"
    )
    await message.answer(text, reply_markup=admin_main_menu_keyboard())


@router.callback_query(F.data.startswith("adm_wd:view:"))
async def admin_withdrawal_detail_inline(callback: CallbackQuery):
    """Show withdrawal detail via inline button."""
    if not await _ensure_admin(callback):
        await callback.answer()
        return

    try:
        tx_id = int(callback.data.split(":")[-1])
    except (TypeError, ValueError):
        await callback.answer("Invalid withdrawal reference", show_alert=True)
        return

    tx = await _get_transaction_or_none(tx_id)
    if not tx or tx.transaction_type != "withdrawal":
        await callback.answer("Withdrawal not found", show_alert=True)
        return

    user = tx.user
    status = tx.status.upper()

    wallet = user.wallet
    risk_notes = []
    if tx.amount and tx.amount > 1000:
        risk_notes.append("• Large amount above risk threshold.")
    if wallet.main_balance < tx.amount:
        risk_notes.append("• Withdrawal exceeds current main balance!")

    risk_text = "\n".join(risk_notes) if risk_notes else "No obvious risk flags."

    text = (
        f"<b>🏧 Withdrawal #{tx.id}</b>\n\n"
        f"👤 User: {user.first_name} (@{user.username or '—'})\n"
        f"🆔 Telegram ID: {user.telegram_id}\n"
        f"💵 Amount: {tx.amount} Birr\n"
        f"📅 Created: {tx.created_at:%Y-%m-%d %H:%M}\n"
        f"💰 Main Balance: {wallet.main_balance}\n"
        f"📄 Status: {status}\n\n"
        f"<b>Risk Notes:</b>\n{risk_text}\n\n"
        "Approve only after you have completed the external payment."
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Approve",
                    callback_data=f"adm_wd:approve:{tx.id}",
                ),
                InlineKeyboardButton(
                    text="❌ Reject",
                    callback_data=f"adm_wd:reject:{tx.id}",
                ),
            ]
        ]
    )

    await callback.message.answer(text, reply_markup=keyboard)
    await callback.answer()


@router.message(F.text.regexp(r"^/adm_wd_approve_(\d+)$"))
async def admin_withdrawal_approve_confirm(message: Message):
    """Two-step confirmation for withdrawal approval."""
    if not await _ensure_admin(message):
        return

    try:
        tx_id = int(message.text.split("_")[-1])
    except (TypeError, ValueError):
        await message.answer("❌ Invalid withdrawal reference.")
        return

    tx = await _get_transaction_or_none(tx_id)
    if not tx or tx.transaction_type != "withdrawal":
        await message.answer("❌ Withdrawal not found.")
        return

    user = tx.user
    text = (
        "<b>✅ Approve Withdrawal?</b>\n\n"
        f"User: {user.first_name} (@{user.username or '—'})\n"
        f"Amount: {tx.amount} Birr\n"
        f"Transaction ID: #{tx.id}\n\n"
        "Confirm ONLY after you have paid the user externally.\n\n"
        "Reply with:\n"
        f"/adm_wd_approve_yes_{tx.id} to CONFIRM\n"
        f"/adm_wd_cancel_{tx.id} to cancel"
    )
    await message.answer(text)


@router.callback_query(F.data.startswith("adm_wd:approve:"))
async def admin_withdrawal_approve_confirm_inline(callback: CallbackQuery):
    """Ask for confirmation before approving a withdrawal via inline button."""
    if not await _ensure_admin(callback):
        await callback.answer()
        return

    try:
        tx_id = int(callback.data.split(":")[-1])
    except (TypeError, ValueError):
        await callback.answer("Invalid withdrawal reference", show_alert=True)
        return

    tx = await _get_transaction_or_none(tx_id)
    if not tx or tx.transaction_type != "withdrawal":
        await callback.answer("Withdrawal not found", show_alert=True)
        return

    user = tx.user
    text = (
        "<b>✅ Approve Withdrawal?</b>\n\n"
        f"User: {user.first_name} (@{user.username or '—'})\n"
        f"Amount: {tx.amount} Birr\n"
        f"Transaction ID: #{tx.id}\n\n"
        "Confirm ONLY after you have paid the user externally."
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Yes",
                    callback_data=f"adm_wd:approve_yes:{tx.id}",
                ),
                InlineKeyboardButton(
                    text="❌ Cancel",
                    callback_data=f"adm_wd:cancel:{tx.id}",
                ),
            ]
        ]
    )

    await callback.message.answer(text, reply_markup=keyboard)
    await callback.answer()


@router.message(F.text.regexp(r"^/adm_wd_approve_yes_(\d+)$"))
async def admin_withdrawal_approve_execute(message: Message):
    """Execute atomic withdrawal approval after confirmation."""
    if not await _ensure_admin(message):
        return

    admin_telegram_id = message.from_user.id
    try:
        tx_id = int(message.text.split("_")[-1])
    except (TypeError, ValueError):
        await message.answer("❌ Invalid withdrawal reference.")
        return

    success, info, before, after = await _approve_withdrawal_atomic(
        tx_id, admin_telegram_id
    )
    if not success:
        await message.answer(f"❌ {info}")
        return

    tx = await _get_transaction_or_none(tx_id)
    user = tx.user if tx else None

    await message.answer(
        f"✅ Withdrawal #{tx_id} approved.\n"
        f"User: {user.first_name if user else 'Unknown'}\n"
        f"Amount: {tx.amount if tx else '—'} Birr\n"
        f"Main balance: {before[0]} → {after[0]} Birr",
        reply_markup=admin_main_menu_keyboard(),
    )

    if user:
        try:
            await message.bot.send_message(
                user.telegram_id,
                f"🏧 Your withdrawal of {tx.amount} Birr (Transaction #{tx.id}) "
                f"has been <b>approved</b>.",
            )
        except Exception:
            pass

    await send_admin_notification(
        message.bot,
        text=(
            "👮 <b>Admin Action</b>\n\n"
            f"Admin: @{message.from_user.username or message.from_user.id}\n"
            f"Action: Approved withdrawal #{tx_id}\n"
            f"User: @{user.username or user.telegram_id if user else 'Unknown'}\n"
            f"Amount: {tx.amount if tx else '—'} Birr\n"
            f"Time: {timezone.now():%Y-%m-%d %H:%M}"
        ),
    )


@router.callback_query(F.data.startswith("adm_wd:approve_yes:"))
async def admin_withdrawal_approve_execute_inline(callback: CallbackQuery):
    """Execute atomic withdrawal approval after inline confirmation."""
    if not await _ensure_admin(callback):
        await callback.answer()
        return

    admin_telegram_id = callback.from_user.id
    try:
        tx_id = int(callback.data.split(":")[-1])
    except (TypeError, ValueError):
        await callback.answer("Invalid withdrawal reference", show_alert=True)
        return

    success, info, before, after = await _approve_withdrawal_atomic(
        tx_id, admin_telegram_id
    )
    if not success:
        await callback.message.answer(f"❌ {info}")
        await callback.answer()
        return

    tx = await _get_transaction_or_none(tx_id)
    user = tx.user if tx else None

    await callback.message.edit_text(
        f"✅ Withdrawal #{tx_id} approved.\n"
        f"User: {user.first_name if user else 'Unknown'}\n"
        f"Amount: {tx.amount if tx else '—'} Birr\n"
        f"Main balance: {before[0]} → {after[0]} Birr",
    )
    await callback.message.answer(
        "Admin menu:",
        reply_markup=admin_main_menu_keyboard(),
    )

    if user:
        try:
            await callback.message.bot.send_message(
                user.telegram_id,
                f"🏧 Your withdrawal of {tx.amount} Birr (Transaction #{tx.id}) "
                f"has been <b>approved</b>.",
            )
        except Exception:
            pass

    await send_admin_notification(
        callback.message.bot,
        text=(
            "👮 <b>Admin Action</b>\n\n"
            f"Admin: @{callback.from_user.username or callback.from_user.id}\n"
            f"Action: Approved withdrawal #{tx_id}\n"
            f"User: @{user.username or user.telegram_id if user else 'Unknown'}\n"
            f"Amount: {tx.amount if tx else '—'} Birr\n"
            f"Time: {timezone.now():%Y-%m-%d %H:%M}"
        ),
    )

    await callback.answer()


@router.message(F.text.regexp(r"^/adm_wd_reject_(\d+)$"))
async def admin_withdrawal_reject_execute(message: Message):
    """Reject a withdrawal request."""
    if not await _ensure_admin(message):
        return

    admin_telegram_id = message.from_user.id
    try:
        tx_id = int(message.text.split("_")[-1])
    except (TypeError, ValueError):
        await message.answer("❌ Invalid withdrawal reference.")
        return

    success, info = await _reject_withdrawal_atomic(tx_id, admin_telegram_id)
    if not success:
        await message.answer(f"❌ {info}")
        return

    tx = await _get_transaction_or_none(tx_id)
    user = tx.user if tx else None

    await message.answer(
        f"✅ Withdrawal #{tx_id} rejected.",
        reply_markup=admin_main_menu_keyboard(),
    )

    if user:
        try:
            await message.bot.send_message(
                user.telegram_id,
                f"❌ Your withdrawal request (Transaction #{tx.id}) "
                f"has been <b>rejected</b>.\n"
                "Please contact support if you believe this is an error.",
            )
        except Exception:
            pass

    await send_admin_notification(
        message.bot,
        text=(
            "👮 <b>Admin Action</b>\n\n"
            f"Admin: @{message.from_user.username or message.from_user.id}\n"
            f"Action: Rejected withdrawal #{tx_id}\n"
            f"Time: {timezone.now():%Y-%m-%d %H:%M}"
        ),
    )


@router.callback_query(F.data.startswith("adm_wd:reject:"))
async def admin_withdrawal_reject_execute_inline(callback: CallbackQuery):
    """Reject a withdrawal via inline button."""
    if not await _ensure_admin(callback):
        await callback.answer()
        return

    admin_telegram_id = callback.from_user.id
    try:
        tx_id = int(callback.data.split(":")[-1])
    except (TypeError, ValueError):
        await callback.answer("Invalid withdrawal reference", show_alert=True)
        return

    success, info = await _reject_withdrawal_atomic(tx_id, admin_telegram_id)
    if not success:
        await callback.message.answer(f"❌ {info}")
        await callback.answer()
        return

    tx = await _get_transaction_or_none(tx_id)
    user = tx.user if tx else None

    await callback.message.edit_text(
        f"✅ Withdrawal #{tx_id} rejected.",
    )
    await callback.message.answer(
        "Admin menu:",
        reply_markup=admin_main_menu_keyboard(),
    )

    if user:
        try:
            await callback.message.bot.send_message(
                user.telegram_id,
                f"❌ Your withdrawal request (Transaction #{tx.id}) "
                "has been <b>rejected</b>.\n"
                "Please contact support if you believe this is an error.",
            )
        except Exception:
            pass

    await send_admin_notification(
        callback.message.bot,
        text=(
            "👮 <b>Admin Action</b>\n\n"
            f"Admin: @{callback.from_user.username or callback.from_user.id}\n"
            f"Action: Rejected withdrawal #{tx_id}\n"
            f"Time: {timezone.now():%Y-%m-%d %H:%M}"
        ),
    )

    await callback.answer()


@router.callback_query(F.data.startswith("adm_wd:cancel:"))
async def admin_withdrawal_cancel_inline(callback: CallbackQuery):
    """Cancel an inline withdrawal action."""
    if not await _ensure_admin(callback):
        await callback.answer()
        return

    await callback.message.answer("✅ Action cancelled.")
    await callback.answer()


@router.message(F.text == "🎮 Game Management")
async def admin_game_management(message: Message):
    """Basic game monitoring for admins."""
    if not await _ensure_admin(message):
        return

    active = await sync_to_async(
        lambda: Game.objects.filter(state__in=["waiting", "playing"]).first()
    )()
    if not active:
        await message.answer(
            "🎮 No active game.\nUse the web/admin tools to create one.",
            reply_markup=admin_main_menu_keyboard(),
        )
        return

    players = await sync_to_async(lambda g: g.cards.count())(active)
    text = (
        f"<b>🎮 Game Management</b>\n\n"
        f"Game ID: #{active.id}\n"
        f"State: {active.state.upper()}\n"
        f"Players: {players}\n"
        f"Prize (current): {active.prize_amount}\n"
        f"Created: {active.created_at:%Y-%m-%d %H:%M}\n\n"
        "Emergency controls (pause/resume/force-finish/new game) "
        "can be added here and integrated with the game engine."
    )
    await message.answer(text, reply_markup=admin_main_menu_keyboard())


@router.message(F.text == "💼 System Balance")
async def admin_system_balance(message: Message):
    """Show system balance overview with inline cash in/out actions."""
    if not await _ensure_admin(message):
        return

    data = await _get_system_balance_overview()
    await message.answer(
        _format_system_balance_text(data),
        reply_markup=system_balance_action_keyboard(),
    )


@router.callback_query(F.data == "sysbal:refresh")
async def admin_system_balance_refresh(callback: CallbackQuery):
    """Refresh the system balance overview from inline action."""
    if not await _ensure_admin(callback):
        await callback.answer()
        return

    data = await _get_system_balance_overview()
    await callback.message.answer(
        _format_system_balance_text(data),
        reply_markup=system_balance_action_keyboard(),
    )
    await callback.answer("Updated")


@router.callback_query(F.data.in_({"sysbal:cash_in", "sysbal:cash_out"}))
async def admin_system_balance_action_start(callback: CallbackQuery, state: FSMContext):
    """Start cash in/out flow by asking for amount."""
    if not await _ensure_admin(callback):
        await state.clear()
        await callback.answer()
        return

    action = callback.data.split(":", 1)[-1]
    await state.update_data(system_balance_action=action)

    action_text = "Cash In (subtract from balance)" if action == "cash_in" else "Cash Out (add to balance)"
    await callback.message.answer(
        f"<b>{action_text}</b>\n\nEnter amount in Birr:"
    )
    await state.set_state(SystemBalanceAdjustStates.waiting_for_amount)
    await callback.answer()


@router.message(SystemBalanceAdjustStates.waiting_for_amount)
async def admin_system_balance_amount(message: Message, state: FSMContext):
    """Capture amount for system balance cash in/out."""
    if not await _ensure_admin(message):
        await state.clear()
        return

    try:
        amount = Decimal((message.text or "").strip())
    except (InvalidOperation, AttributeError):
        await message.answer("❌ Please enter a valid numeric amount.")
        return

    if amount <= Decimal("0"):
        await message.answer("❌ Amount must be greater than 0.")
        return

    await state.update_data(system_balance_amount=amount)
    await message.answer("Please enter reason/description for this action:")
    await state.set_state(SystemBalanceAdjustStates.waiting_for_reason)


@router.message(SystemBalanceAdjustStates.waiting_for_reason)
async def admin_system_balance_reason(message: Message, state: FSMContext):
    """Apply cash in/out to system balance and log to ledger."""
    if not await _ensure_admin(message):
        await state.clear()
        return

    data = await state.get_data()
    action = data.get("system_balance_action")
    amount = data.get("system_balance_amount")
    reason = (message.text or "").strip()

    if not action or not amount:
        await message.answer("❌ Missing action data. Please start again from System Balance menu.")
        await state.clear()
        return

    if not reason:
        await message.answer("❌ Reason is required.")
        return

    success, info, entry = await _adjust_system_balance_atomic(
        action,
        amount,
        reason,
        message.from_user.id,
    )

    if not success:
        await message.answer(f"❌ {info}", reply_markup=admin_main_menu_keyboard())
        await state.clear()
        return

    action_label = "Cash In" if action == "cash_in" else "Cash Out"
    await message.answer(
        f"✅ {action_label} completed.\n"
        f"Entry ID: #{entry.id}\n"
        f"Direction: {entry.direction}\n"
        f"Amount: {entry.amount} Birr\n"
        f"Balance: {entry.balance_before} → {entry.balance_after} Birr\n"
        f"Reason: {reason}",
        reply_markup=admin_main_menu_keyboard(),
    )

    await send_admin_notification(
        message.bot,
        text=(
            "👮 <b>System Balance Adjustment</b>\n\n"
            f"Admin: @{message.from_user.username or message.from_user.id}\n"
            f"Action: {action_label}\n"
            f"Amount: {entry.amount} Birr\n"
            f"Direction: {entry.direction}\n"
            f"Balance: {entry.balance_before} → {entry.balance_after} Birr\n"
            f"Reason: {reason}\n"
            f"Time: {timezone.now():%Y-%m-%d %H:%M}"
        ),
    )

    await state.clear()


@router.message(F.text == "📜 Transaction Logs")
async def admin_transaction_logs(message: Message):
    """Show last few transactions for quick audit."""
    if not await _ensure_admin(message):
        return

    @sync_to_async
    def _get_latest_transactions(limit: int = 10):
        return list(
            Transaction.objects.select_related("user")
            .order_by("-created_at")[:limit]
        )

    txs = await _get_latest_transactions()
    if not txs:
        await message.answer(
            "No transactions found.", reply_markup=admin_main_menu_keyboard()
        )
        return

    lines = ["<b>📜 Latest Transactions</b>\n"]
    for tx in txs:
        lines.append(
            f"#{tx.id} • {tx.transaction_type} • {tx.amount} Birr • {tx.status}\n"
            f"User: {tx.user.first_name} (@{tx.user.username or '—'}) • "
            f"{tx.created_at:%Y-%m-%d %H:%M}\n"
        )

    await message.answer("\n".join(lines), reply_markup=admin_main_menu_keyboard())


@router.message(F.text == "📢 Announcement")
async def admin_announcement_start(message: Message, state: FSMContext):
    """Start announcement flow for broadcasting a message to all users."""
    if not await _ensure_admin(message):
        return

    await message.answer(
        "<b>📢 Announcement</b>\n\n"
        "Send the message you want to broadcast to all active users.\n"
        "Type <b>cancel</b> to abort."
    )
    await state.set_state(AnnouncementStates.waiting_for_message)


@router.message(AnnouncementStates.waiting_for_message)
async def admin_announcement_broadcast(message: Message, state: FSMContext):
    """Capture announcement text and ask for confirmation."""
    if not await _ensure_admin(message):
        await state.clear()
        return

    announcement_text = (message.text or "").strip()
    if not announcement_text:
        await message.answer("❌ Announcement message cannot be empty.")
        return

    if announcement_text.lower() == "cancel":
        await message.answer(
            "✅ Announcement cancelled.",
            reply_markup=admin_main_menu_keyboard(),
        )
        await state.clear()
        return

    await state.update_data(announcement_text=announcement_text)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Send Announcement",
                    callback_data="adm_announce:send",
                ),
                InlineKeyboardButton(
                    text="❌ Cancel",
                    callback_data="adm_announce:cancel",
                ),
            ]
        ]
    )

    await message.answer(
        "<b>📢 Announcement Preview</b>\n\n"
        f"{announcement_text}\n\n"
        "Send this to all active users?",
        reply_markup=keyboard,
    )

    await state.set_state(AnnouncementStates.waiting_for_confirm)


@router.callback_query(F.data == "adm_announce:send")
async def admin_announcement_send(callback: CallbackQuery, state: FSMContext):
    """Broadcast the confirmed announcement to all active users."""
    if not await _ensure_admin(callback):
        await state.clear()
        await callback.answer()
        return

    data = await state.get_data()
    announcement_text = (data.get("announcement_text") or "").strip()
    if not announcement_text:
        await callback.message.answer(
            "❌ No announcement message found. Please start again.",
            reply_markup=admin_main_menu_keyboard(),
        )
        await state.clear()
        await callback.answer()
        return

    users = await _get_active_users_for_notifications()
    if not users:
        await callback.message.answer(
            "❌ No active users found to receive announcement.",
            reply_markup=admin_main_menu_keyboard(),
        )
        await state.clear()
        await callback.answer()
        return

    notification = await _create_announcement_notification(
        callback.from_user.id,
        announcement_text,
        len(users),
    )

    await callback.message.answer(
        f"📤 Sending announcement to {len(users)} users..."
    )

    sent_count = 0
    failed_count = 0

    for user in users:
        try:
            await callback.message.bot.send_message(
                user.telegram_id,
                f"📢 <b>Admin Announcement</b>\n\n{announcement_text}",
            )
            await _create_notification_delivery(
                notification.id,
                user.id,
                "delivered",
            )
            sent_count += 1
        except Exception as error:
            await _create_notification_delivery(
                notification.id,
                user.id,
                "failed",
                str(error)[:500],
            )
            failed_count += 1

    await _finalize_announcement_notification(
        notification.id,
        sent_count,
        failed_count,
    )

    await callback.message.answer(
        "✅ <b>Announcement broadcast completed</b>\n\n"
        f"🆔 Notification ID: #{notification.id}\n"
        f"👥 Total target users: {len(users)}\n"
        f"✅ Delivered: {sent_count}\n"
        f"❌ Failed: {failed_count}",
        reply_markup=admin_main_menu_keyboard(),
    )

    await send_admin_notification(
        callback.message.bot,
        text=(
            "👮 <b>Admin Announcement Sent</b>\n\n"
            f"Admin: @{callback.from_user.username or callback.from_user.id}\n"
            f"Notification ID: #{notification.id}\n"
            f"Delivered: {sent_count}\n"
            f"Failed: {failed_count}\n"
            f"Time: {timezone.now():%Y-%m-%d %H:%M}"
        ),
    )

    await state.clear()
    await callback.answer("Announcement sent")


@router.callback_query(F.data == "adm_announce:cancel")
async def admin_announcement_cancel(callback: CallbackQuery, state: FSMContext):
    """Cancel announcement before broadcasting."""
    if not await _ensure_admin(callback):
        await state.clear()
        await callback.answer()
        return

    await state.clear()
    await callback.message.answer(
        "✅ Announcement cancelled.",
        reply_markup=admin_main_menu_keyboard(),
    )
    await callback.answer("Cancelled")


@router.message(Command("wallet_stats"))
async def admin_wallet_stats(message: Message):
    """Show aggregate financial statistics for admins."""
    if not await _ensure_admin(message):
        return

    stats = await _get_wallet_stats()

    text = (
        "<b>📊 Wallet / Finance Stats</b>\n\n"
        f"💰 Total Deposits (approved): {stats['total_deposits']} Birr\n"
        f"🏧 Total Withdrawals (approved): {stats['total_withdrawals']} Birr\n"
        f"🎁 Total Game Winnings Paid: {stats['total_game_wins']} Birr\n"
        f"📈 Net Revenue: {stats['net_revenue']} Birr\n\n"
        f"⏳ Pending Deposits: {stats['pending_deposits']}\n"
        f"⏳ Pending Withdrawals: {stats['pending_withdrawals']}"
    )
    await message.answer(text, reply_markup=admin_main_menu_keyboard())


@router.message(F.text == "👛 Wallet Management")
async def admin_wallet_management(message: Message, state: FSMContext):
    """Start wallet management flow for a specific user."""
    if not await _ensure_admin(message):
        return

    await message.answer(
        "<b>👛 Wallet Management</b>\n\n"
        "Please enter the user's Telegram ID whose wallet you want to manage:"
    )
    await state.set_state(WalletAdjustStates.waiting_for_user_id)


@router.message(WalletAdjustStates.waiting_for_user_id)
async def admin_wallet_user_id(message: Message, state: FSMContext):
    """Capture and validate target user's Telegram ID."""
    if not await _ensure_admin(message):
        await state.clear()
        return

    try:
        target_telegram_id = int(message.text)
    except ValueError:
        await message.answer("❌ Please enter a valid numeric Telegram ID.")
        return

    wallet = await _get_wallet_by_telegram_id_or_none(target_telegram_id)
    if not wallet:
        await message.answer(
            "❌ Wallet not found for this Telegram ID.\n"
            "Please check the ID and try again, or /admin to cancel."
        )
        return

    await state.update_data(target_telegram_id=target_telegram_id)

    await message.answer(
        f"User: {wallet.user.first_name} (@{wallet.user.username or '—'})\n"
        f"Main Balance: {wallet.main_balance} Birr\n"
        f"Bonus Balance: {wallet.bonus_balance} Birr\n"
        f"Total Balance: {wallet.total_balance} Birr\n\n"
        "Which balance do you want to adjust?",
        reply_markup=wallet_balance_type_keyboard(),
    )
    await state.set_state(WalletAdjustStates.waiting_for_balance_type)


@router.callback_query(F.data.startswith("wallet_balance:"))
async def admin_wallet_balance_type_inline(callback: CallbackQuery, state: FSMContext):
    """Capture balance type via inline buttons."""
    if not await _ensure_admin(callback):
        await state.clear()
        await callback.answer()
        return

    choice = callback.data.split(":", 1)[-1].strip().lower()
    if choice not in {"main", "bonus"}:
        await callback.answer("Invalid option", show_alert=True)
        return

    await state.update_data(balance_type=choice)
    await callback.message.answer(
        "Do you want to <b>add</b> or <b>subtract</b> funds?",
        reply_markup=wallet_direction_keyboard(),
    )
    await state.set_state(WalletAdjustStates.waiting_for_direction)
    await callback.answer()


@router.message(WalletAdjustStates.waiting_for_balance_type)
async def admin_wallet_balance_type(message: Message, state: FSMContext):
    """Capture balance type: main or bonus."""
    if not await _ensure_admin(message):
        await state.clear()
        return

    choice = message.text.strip().lower()
    if choice not in {"main", "bonus"}:
        await message.answer("❌ Please reply with either 'main' or 'bonus'.")
        return

    await state.update_data(balance_type=choice)
    await message.answer(
        "Do you want to <b>add</b> or <b>subtract</b> funds?",
        reply_markup=wallet_direction_keyboard(),
    )
    await state.set_state(WalletAdjustStates.waiting_for_direction)


@router.callback_query(F.data.startswith("wallet_direction:"))
async def admin_wallet_direction_inline(callback: CallbackQuery, state: FSMContext):
    """Capture adjustment direction via inline buttons."""
    if not await _ensure_admin(callback):
        await state.clear()
        await callback.answer()
        return

    direction = callback.data.split(":", 1)[-1].strip().lower()
    if direction not in {"add", "subtract"}:
        await callback.answer("Invalid option", show_alert=True)
        return

    await state.update_data(direction=direction)
    await callback.message.answer("Enter the amount to adjust (in Birr):")
    await state.set_state(WalletAdjustStates.waiting_for_amount)
    await callback.answer()


@router.message(WalletAdjustStates.waiting_for_direction)
async def admin_wallet_direction(message: Message, state: FSMContext):
    """Capture adjustment direction: add or subtract."""
    if not await _ensure_admin(message):
        await state.clear()
        return

    direction = message.text.strip().lower()
    if direction not in {"add", "subtract"}:
        await message.answer("❌ Please reply with 'add' or 'subtract'.")
        return

    await state.update_data(direction=direction)
    await message.answer("Enter the amount to adjust (in Birr):")
    await state.set_state(WalletAdjustStates.waiting_for_amount)


@router.message(WalletAdjustStates.waiting_for_amount)
async def admin_wallet_amount(message: Message, state: FSMContext):
    """Capture and validate adjustment amount."""
    if not await _ensure_admin(message):
        await state.clear()
        return

    try:
        amount = Decimal(message.text.strip())
    except (InvalidOperation, AttributeError):
        await message.answer("❌ Please enter a valid number for the amount.")
        return

    if amount <= Decimal("0"):
        await message.answer("❌ Amount must be greater than 0.")
        return

    await state.update_data(amount=amount)
    await message.answer(
        "Please provide a short reason/description for this adjustment:"
    )
    await state.set_state(WalletAdjustStates.waiting_for_reason)


@router.message(WalletAdjustStates.waiting_for_reason)
async def admin_wallet_reason(message: Message, state: FSMContext):
    """Execute wallet adjustment with provided reason."""
    if not await _ensure_admin(message):
        await state.clear()
        return

    data = await state.get_data()
    target_telegram_id = data.get("target_telegram_id")
    balance_type = data.get("balance_type")
    direction = data.get("direction")
    amount = data.get("amount")
    reason = message.text.strip()

    success, info, before, after, user = await _adjust_wallet_atomic(
        target_telegram_id,
        balance_type,
        direction,
        amount,
        reason,
        message.from_user.id,
    )

    if not success:
        await message.answer(f"❌ {info}", reply_markup=admin_main_menu_keyboard())
        await state.clear()
        return

    await message.answer(
        f"✅ Wallet adjusted successfully.\n\n"
        f"User: {user.first_name} (@{user.username or '—'})\n"
        f"Type: {balance_type} ({direction})\n"
        f"Amount: {amount} Birr\n"
        f"Main: {before[0]} → {after[0]} Birr\n"
        f"Bonus: {before[1]} → {after[1]} Birr\n"
        f"Reason: {reason}",
        reply_markup=admin_main_menu_keyboard(),
    )

    # Optional: notify user about admin adjustment
    try:
        await message.bot.send_message(
            user.telegram_id,
            f"👮 Your wallet was adjusted by an admin.\n\n"
            f"Type: {balance_type} ({direction})\n"
            f"Amount: {amount} Birr\n"
            f"Reason: {reason}",
        )
    except Exception:
        pass

    # Notify all admins for transparency
    await send_admin_notification(
        message.bot,
        text=(
            "👮 <b>Admin Wallet Adjustment</b>\n\n"
            f"Admin: @{message.from_user.username or message.from_user.id}\n"
            f"User: @{user.username or user.telegram_id}\n"
            f"Type: {balance_type} ({direction})\n"
            f"Amount: {amount} Birr\n"
            f"Reason: {reason}\n"
            f"Time: {timezone.now():%Y-%m-%d %H:%M}"
        ),
    )

    await state.clear()


@router.message(F.text == "🏠 User Menu")
async def admin_back_to_user_menu(message: Message):
    """Switch back to normal user menu."""
    # No admin check here – allow anyone to return to user menu safely.
    await message.answer(
        "🏠 Switched back to user menu.",
        reply_markup=main_menu_keyboard(),
    )


@router.message(F.text.in_({"👤 User Management", "⚙️ Settings", "🔍 Search"}))
async def admin_not_implemented(message: Message):
    """Placeholders for future admin features."""
    if not await _ensure_admin(message):
        return

    await message.answer(
        "This admin feature is planned but not implemented yet in the bot UI.\n"
        "Use the Django admin panel for full control.",
        reply_markup=admin_main_menu_keyboard(),
    )


@sync_to_async
def _get_engagement_overview():
    now = timezone.now()
    active_promos = PromoCode.objects.filter(is_active=True, starts_at__lte=now, ends_at__gte=now).count()
    total_promos = PromoCode.objects.count()
    promo_redemptions_today = PromoCodeRedemption.objects.filter(created_at__date=now.date()).count()

    active_events = LiveEvent.objects.filter(is_active=True, starts_at__lte=now, ends_at__gte=now).count()
    upcoming_events = LiveEvent.objects.filter(is_active=True, starts_at__gt=now).count()

    active_missions = MissionTemplate.objects.filter(is_active=True).count()
    daily_missions = MissionTemplate.objects.filter(is_active=True, period=MissionTemplate.PERIOD_DAILY).count()
    weekly_missions = MissionTemplate.objects.filter(is_active=True, period=MissionTemplate.PERIOD_WEEKLY).count()

    current_season = Season.get_current()
    policy = RewardSafetyPolicy.get_active()

    return {
        'active_promos': active_promos,
        'total_promos': total_promos,
        'promo_redemptions_today': promo_redemptions_today,
        'active_events': active_events,
        'upcoming_events': upcoming_events,
        'active_missions': active_missions,
        'daily_missions': daily_missions,
        'weekly_missions': weekly_missions,
        'current_season': current_season,
        'policy': policy,
    }


@router.message(F.text == "🚀 Engagement Management")
async def admin_engagement_management(message: Message):
    if not await _ensure_admin(message):
        return

    await _send_engagement_overview(message)


async def _send_engagement_overview(message_or_callback):
    overview = await _get_engagement_overview()
    season = overview['current_season']
    policy = overview['policy']

    text = (
        "<b>🚀 Engagement Management</b>\n\n"
        f"🎟 Active Promos: {overview['active_promos']} / {overview['total_promos']}\n"
        f"✅ Promo Redemptions Today: {overview['promo_redemptions_today']}\n"
        f"🎉 Active Live Events: {overview['active_events']}\n"
        f"⏭ Upcoming Live Events: {overview['upcoming_events']}\n"
        f"🎯 Active Missions: {overview['active_missions']} (Daily: {overview['daily_missions']}, Weekly: {overview['weekly_missions']})\n"
        f"🏆 Current Season: {season.name if season else 'None'}\n\n"
        "<b>Reward Safety Policy</b>\n"
        f"• Daily Cap: {policy.daily_reward_cap} Birr\n"
        f"• Cooldown: {policy.min_seconds_between_rewards}s\n"
        f"• Hourly Limit: {policy.max_reward_redemptions_per_hour}\n\n"
        "Use the buttons below to manage engagement features."
    )

    if isinstance(message_or_callback, CallbackQuery):
        await message_or_callback.message.answer(text, reply_markup=engagement_main_keyboard())
    else:
        await message_or_callback.answer(text, reply_markup=engagement_main_keyboard())


@router.callback_query(F.data.in_({"eng:open", "eng:refresh"}))
async def admin_engagement_open(callback: CallbackQuery):
    if not await _ensure_admin(callback):
        await callback.answer()
        return

    await _send_engagement_overview(callback)
    await callback.answer("Updated")


@router.callback_query(F.data == "eng:promo:list")
async def admin_engagement_promo_list_inline(callback: CallbackQuery):
    if not await _ensure_admin(callback):
        await callback.answer()
        return

    now = timezone.now()
    promos = await sync_to_async(lambda: list(PromoCode.objects.order_by('-created_at')[:10]))()
    if not promos:
        await callback.message.answer("No promo codes found.", reply_markup=engagement_main_keyboard())
        await callback.answer()
        return

    lines = ["<b>🎟 Promo Codes</b>"]
    buttons = []
    for promo in promos:
        redemptions = await sync_to_async(lambda p=promo: PromoCodeRedemption.objects.filter(promo_code=p).count())()
        state = "🟢 LIVE" if (promo.is_active and promo.starts_at <= now <= promo.ends_at) else ("🟡 ACTIVE" if promo.is_active else "🔴 OFF")
        frontend_state = "🌐 FRONTEND" if promo.is_visible_in_frontend else "🙈 HIDDEN"
        lines.append(
            f"#{promo.id} {promo.code} [{promo.tier}] {state} {frontend_state}\n"
            f"Reward: {promo.reward_amount} -> {promo.reward_balance}\n"
            f"Used: {redemptions}/{promo.max_redemptions if promo.max_redemptions > 0 else '∞'}"
        )
        if promo.is_active:
            buttons.append([InlineKeyboardButton(text=f"Disable {promo.code}", callback_data=f"eng:promo:disable:{promo.id}")])
        buttons.append([InlineKeyboardButton(text=f"Toggle Frontend {promo.code}", callback_data=f"eng:promo:frontend-toggle:{promo.id}")])

    buttons.append([InlineKeyboardButton(text="⬅ Back", callback_data="eng:open")])
    await callback.message.answer(
        "\n\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("eng:promo:disable:"))
async def admin_engagement_promo_disable_inline(callback: CallbackQuery):
    if not await _ensure_admin(callback):
        await callback.answer()
        return

    try:
        promo_id = int(callback.data.split(":")[-1])
    except (TypeError, ValueError):
        await callback.answer("Invalid promo", show_alert=True)
        return

    @sync_to_async
    def _disable():
        promo = PromoCode.objects.filter(id=promo_id).first()
        if not promo:
            return None
        promo.is_active = False
        promo.save(update_fields=['is_active', 'updated_at'])
        return promo

    promo = await _disable()
    if not promo:
        await callback.answer("Promo not found", show_alert=True)
        return

    await callback.message.answer(f"✅ Promo {promo.code} disabled.", reply_markup=engagement_main_keyboard())
    await callback.answer("Disabled")


@router.callback_query(F.data.startswith("eng:promo:frontend-toggle:"))
async def admin_engagement_promo_frontend_toggle_inline(callback: CallbackQuery):
    if not await _ensure_admin(callback):
        await callback.answer()
        return

    try:
        promo_id = int(callback.data.split(":")[-1])
    except (TypeError, ValueError):
        await callback.answer("Invalid promo", show_alert=True)
        return

    @sync_to_async
    def _toggle():
        promo = PromoCode.objects.filter(id=promo_id).first()
        if not promo:
            return None
        promo.is_visible_in_frontend = not promo.is_visible_in_frontend
        promo.save(update_fields=['is_visible_in_frontend', 'updated_at'])
        return promo

    promo = await _toggle()
    if not promo:
        await callback.answer("Promo not found", show_alert=True)
        return

    state = "visible" if promo.is_visible_in_frontend else "hidden"
    await callback.message.answer(
        f"✅ Promo {promo.code} is now {state} in frontend.",
        reply_markup=engagement_main_keyboard(),
    )
    await callback.answer("Updated")


@router.callback_query(F.data == "eng:promo:create")
async def admin_engagement_promo_create_inline_start(callback: CallbackQuery, state: FSMContext):
    if not await _ensure_admin(callback):
        await state.clear()
        await callback.answer()
        return
    await state.set_state(PromoCreateStates.waiting_for_code)
    await callback.message.answer("Enter promo code (e.g. FLASH100):")
    await callback.answer()


@router.callback_query(F.data.startswith("eng:promo:tier:"))
async def admin_engagement_promo_create_inline_tier(callback: CallbackQuery, state: FSMContext):
    tier = callback.data.split(":")[-1]
    allowed = {PromoCode.TIER_COMMON, PromoCode.TIER_RARE, PromoCode.TIER_LEGENDARY}
    if tier not in allowed:
        await callback.answer("Invalid tier", show_alert=True)
        return
    await state.update_data(tier=tier)
    await state.set_state(PromoCreateStates.waiting_for_amount)
    await callback.message.answer("Enter reward amount in Birr:")
    await callback.answer()


@router.callback_query(F.data.startswith("eng:promo:balance:"))
async def admin_engagement_promo_create_inline_balance(callback: CallbackQuery, state: FSMContext):
    balance = callback.data.split(":")[-1]
    allowed = {PromoCode.BALANCE_BONUS, PromoCode.BALANCE_MAIN, PromoCode.BALANCE_WINNINGS}
    if balance not in allowed:
        await callback.answer("Invalid balance", show_alert=True)
        return
    await state.update_data(balance=balance)
    await state.set_state(PromoCreateStates.waiting_for_start_minutes)
    await callback.message.answer("Start in how many minutes from now? (0 for immediate)")
    await callback.answer()


@router.callback_query(F.data == "eng:event:list")
async def admin_engagement_event_list_inline(callback: CallbackQuery):
    if not await _ensure_admin(callback):
        await callback.answer()
        return

    now = timezone.now()
    events = await sync_to_async(lambda: list(LiveEvent.objects.order_by('-starts_at')[:10]))()
    if not events:
        await callback.message.answer("No live events found.", reply_markup=engagement_main_keyboard())
        await callback.answer()
        return

    lines = ["<b>🎉 Live Events</b>"]
    buttons = []
    for event in events:
        state = "🟢 LIVE" if (event.is_active and event.starts_at <= now <= event.ends_at) else ("🟡 ACTIVE" if event.is_active else "🔴 OFF")
        lines.append(
            f"#{event.id} {event.name} [{event.event_type}] {state}\n"
            f"Multiplier: {event.bonus_multiplier}x\n"
            f"Window: {event.starts_at:%Y-%m-%d %H:%M} -> {event.ends_at:%Y-%m-%d %H:%M}"
        )
        if event.is_active:
            buttons.append([InlineKeyboardButton(text=f"Disable {event.name}", callback_data=f"eng:event:disable:{event.id}")])

    buttons.append([InlineKeyboardButton(text="⬅ Back", callback_data="eng:open")])
    await callback.message.answer(
        "\n\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("eng:event:disable:"))
async def admin_engagement_event_disable_inline(callback: CallbackQuery):
    if not await _ensure_admin(callback):
        await callback.answer()
        return

    try:
        event_id = int(callback.data.split(":")[-1])
    except (TypeError, ValueError):
        await callback.answer("Invalid event", show_alert=True)
        return

    @sync_to_async
    def _disable():
        event = LiveEvent.objects.filter(id=event_id).first()
        if not event:
            return None
        event.is_active = False
        event.save(update_fields=['is_active', 'updated_at'])
        return event

    event = await _disable()
    if not event:
        await callback.answer("Event not found", show_alert=True)
        return

    await callback.message.answer(f"✅ Event '{event.name}' disabled.", reply_markup=engagement_main_keyboard())
    await callback.answer("Disabled")


@router.callback_query(F.data == "eng:event:create")
async def admin_engagement_event_create_inline_start(callback: CallbackQuery, state: FSMContext):
    if not await _ensure_admin(callback):
        await state.clear()
        await callback.answer()
        return
    await state.set_state(EventCreateStates.waiting_for_name)
    await callback.message.answer("Enter event name:")
    await callback.answer()


@router.callback_query(F.data.startswith("eng:event:type:"))
async def admin_engagement_event_create_inline_type(callback: CallbackQuery, state: FSMContext):
    event_type = callback.data.split(":")[-1]
    allowed = {LiveEvent.TYPE_HAPPY_HOUR, LiveEvent.TYPE_FLASH_PROMO, LiveEvent.TYPE_DOUBLE_REWARD}
    if event_type not in allowed:
        await callback.answer("Invalid type", show_alert=True)
        return
    await state.update_data(event_type=event_type)
    await state.set_state(EventCreateStates.waiting_for_multiplier)
    await callback.message.answer("Enter reward multiplier (e.g. 1.00, 1.50, 2.00)")
    await callback.answer()


@router.callback_query(F.data == "eng:mission:list")
async def admin_engagement_mission_list_inline(callback: CallbackQuery):
    if not await _ensure_admin(callback):
        await callback.answer()
        return

    missions = await sync_to_async(lambda: list(MissionTemplate.objects.order_by('sort_order', 'id')[:20]))()
    if not missions:
        await callback.message.answer("No missions found.", reply_markup=engagement_main_keyboard())
        await callback.answer()
        return

    lines = ["<b>🎯 Missions</b>"]
    buttons = []
    for mission in missions:
        state = "🟢 ON" if mission.is_active else "🔴 OFF"
        lines.append(
            f"#{mission.id} {mission.title} {state}\n"
            f"Type: {mission.mission_type} | Period: {mission.period}\n"
            f"Target: {mission.target_value} | Reward: {mission.reward_amount} -> {mission.reward_balance}"
        )
        buttons.append([InlineKeyboardButton(text=f"Toggle {mission.id}", callback_data=f"eng:mission:toggle:{mission.id}")])

    buttons.append([InlineKeyboardButton(text="⬅ Back", callback_data="eng:open")])
    await callback.message.answer(
        "\n\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("eng:mission:toggle:"))
async def admin_engagement_mission_toggle_inline(callback: CallbackQuery):
    if not await _ensure_admin(callback):
        await callback.answer()
        return

    try:
        mission_id = int(callback.data.split(":")[-1])
    except (TypeError, ValueError):
        await callback.answer("Invalid mission", show_alert=True)
        return

    @sync_to_async
    def _toggle():
        mission = MissionTemplate.objects.filter(id=mission_id).first()
        if not mission:
            return None
        mission.is_active = not mission.is_active
        mission.save(update_fields=['is_active', 'updated_at'])
        return mission

    mission = await _toggle()
    if not mission:
        await callback.answer("Mission not found", show_alert=True)
        return

    await callback.message.answer(
        f"✅ Mission '{mission.title}' is now {'active' if mission.is_active else 'disabled'}.",
        reply_markup=engagement_main_keyboard(),
    )
    await callback.answer("Toggled")


@router.callback_query(F.data == "eng:season:list")
async def admin_engagement_season_list_inline(callback: CallbackQuery):
    if not await _ensure_admin(callback):
        await callback.answer()
        return

    seasons = await sync_to_async(lambda: list(Season.objects.order_by('-starts_at')[:10]))()
    if not seasons:
        await callback.message.answer("No seasons found.", reply_markup=engagement_main_keyboard())
        await callback.answer()
        return

    now = timezone.now()
    lines = ["<b>🏆 Seasons</b>"]
    buttons = [[InlineKeyboardButton(text="➕ Create Season", callback_data="eng:season:create")]]
    for season in seasons:
        if season.is_active and season.starts_at <= now <= season.ends_at:
            status = "🟢 CURRENT"
        elif season.is_active:
            status = "🟡 ACTIVE"
        else:
            status = "🔴 OFF"
        lines.append(
            f"#{season.id} {season.name} {status}\n"
            f"Window: {season.starts_at:%Y-%m-%d} -> {season.ends_at:%Y-%m-%d}\n"
            f"Rewards: {season.top_1_reward}/{season.top_2_reward}/{season.top_3_reward} + {season.participation_reward}"
        )
        buttons.append([InlineKeyboardButton(text=f"Activate {season.id}", callback_data=f"eng:season:activate:{season.id}")])

    buttons.append([InlineKeyboardButton(text="⬅ Back", callback_data="eng:open")])
    await callback.message.answer(
        "\n\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    await callback.answer()


@router.callback_query(F.data == "eng:season:create")
async def admin_engagement_season_create_inline_start(callback: CallbackQuery, state: FSMContext):
    if not await _ensure_admin(callback):
        await state.clear()
        await callback.answer()
        return
    await state.set_state(SeasonCreateStates.waiting_for_name)
    await callback.message.answer("Enter season name:")
    await callback.answer()


@router.callback_query(F.data.startswith("eng:season:activate:"))
async def admin_engagement_season_activate_inline(callback: CallbackQuery):
    if not await _ensure_admin(callback):
        await callback.answer()
        return

    try:
        season_id = int(callback.data.split(":")[-1])
    except (TypeError, ValueError):
        await callback.answer("Invalid season", show_alert=True)
        return

    @sync_to_async
    def _activate():
        target = Season.objects.filter(id=season_id).first()
        if not target:
            return None
        Season.objects.exclude(id=target.id).update(is_active=False)
        target.is_active = True
        target.save(update_fields=['is_active', 'updated_at'])
        return target

    season = await _activate()
    if not season:
        await callback.answer("Season not found", show_alert=True)
        return

    await callback.message.answer(f"✅ Season '{season.name}' activated.", reply_markup=engagement_main_keyboard())
    await callback.answer("Activated")


@router.callback_query(F.data == "eng:policy:show")
async def admin_engagement_policy_show_inline(callback: CallbackQuery):
    if not await _ensure_admin(callback):
        await callback.answer()
        return

    policy = await sync_to_async(RewardSafetyPolicy.get_active)()
    await callback.message.answer(
        "<b>🛡 Reward Safety Policy</b>\n\n"
        f"Daily Cap: {policy.daily_reward_cap} Birr\n"
        f"Cooldown: {policy.min_seconds_between_rewards} seconds\n"
        f"Hourly Limit: {policy.max_reward_redemptions_per_hour}",
        reply_markup=engagement_main_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "eng:policy:set")
async def admin_engagement_policy_set_inline_start(callback: CallbackQuery, state: FSMContext):
    if not await _ensure_admin(callback):
        await state.clear()
        await callback.answer()
        return
    await state.set_state(RewardPolicyStates.waiting_for_daily_cap)
    await callback.message.answer("Enter new daily reward cap (Birr):")
    await callback.answer()


@router.message(Command("eng_promo_list"))
async def admin_eng_promo_list(message: Message):
    if not await _ensure_admin(message):
        return

    @sync_to_async
    def _get_rows():
        now = timezone.now()
        rows = []
        promos = PromoCode.objects.order_by('-created_at')[:15]
        for promo in promos:
            rows.append({
                'id': promo.id,
                'code': promo.code,
                'tier': promo.tier,
                'amount': promo.reward_amount,
                'balance': promo.reward_balance,
                'live': promo.is_active and promo.starts_at <= now <= promo.ends_at,
                'is_active': promo.is_active,
                'is_visible_in_frontend': promo.is_visible_in_frontend,
                'redemptions': PromoCodeRedemption.objects.filter(promo_code=promo).count(),
                'max_redemptions': promo.max_redemptions,
                'ends_at': promo.ends_at,
            })
        return rows

    rows = await _get_rows()
    if not rows:
        await message.answer("No promo codes found.", reply_markup=admin_main_menu_keyboard())
        return

    lines = ["<b>🎟 Promo Codes (latest 15)</b>"]
    for row in rows:
        live_mark = "🟢 LIVE" if row['live'] else ("🟡 ACTIVE" if row['is_active'] else "🔴 OFF")
        frontend_mark = "🌐 FRONTEND" if row['is_visible_in_frontend'] else "🙈 HIDDEN"
        lines.append(
            f"#{row['id']} {row['code']} [{row['tier']}] {live_mark} {frontend_mark}\n"
            f"Reward: {row['amount']} -> {row['balance']}\n"
            f"Redeemed: {row['redemptions']}/{row['max_redemptions'] if row['max_redemptions'] > 0 else '∞'}\n"
            f"Ends: {row['ends_at']:%Y-%m-%d %H:%M}\n"
            f"Disable: /eng_promo_disable_{row['id']}\n"
            f"Frontend Toggle: /eng_promo_frontend_toggle_{row['id']}"
        )
    await message.answer("\n\n".join(lines), reply_markup=admin_main_menu_keyboard())


@router.message(F.text.regexp(r"^/eng_promo_disable_(\d+)$"))
async def admin_eng_promo_disable(message: Message):
    if not await _ensure_admin(message):
        return

    try:
        promo_id = int(message.text.split("_")[-1])
    except (TypeError, ValueError):
        await message.answer("❌ Invalid promo reference.")
        return

    @sync_to_async
    def _disable():
        promo = PromoCode.objects.filter(id=promo_id).first()
        if not promo:
            return False, None
        promo.is_active = False
        promo.save(update_fields=['is_active', 'updated_at'])
        return True, promo

    ok, promo = await _disable()
    if not ok:
        await message.answer("❌ Promo not found.", reply_markup=admin_main_menu_keyboard())
        return

    await message.answer(
        f"✅ Promo {promo.code} disabled.",
        reply_markup=admin_main_menu_keyboard(),
    )


@router.message(F.text.regexp(r"^/eng_promo_frontend_toggle_(\d+)$"))
async def admin_eng_promo_frontend_toggle(message: Message):
    if not await _ensure_admin(message):
        return

    try:
        promo_id = int(message.text.split("_")[-1])
    except (TypeError, ValueError):
        await message.answer("❌ Invalid promo reference.")
        return

    @sync_to_async
    def _toggle():
        promo = PromoCode.objects.filter(id=promo_id).first()
        if not promo:
            return False, None
        promo.is_visible_in_frontend = not promo.is_visible_in_frontend
        promo.save(update_fields=['is_visible_in_frontend', 'updated_at'])
        return True, promo

    ok, promo = await _toggle()
    if not ok:
        await message.answer("❌ Promo not found.", reply_markup=admin_main_menu_keyboard())
        return

    state = "visible" if promo.is_visible_in_frontend else "hidden"
    await message.answer(
        f"✅ Promo {promo.code} is now {state} in frontend.",
        reply_markup=admin_main_menu_keyboard(),
    )


@router.message(Command("eng_promo_create"))
async def admin_eng_promo_create_start(message: Message, state: FSMContext):
    if not await _ensure_admin(message):
        return
    await state.set_state(PromoCreateStates.waiting_for_code)
    await message.answer("Enter promo code (e.g. FLASH100):")


@router.message(PromoCreateStates.waiting_for_code)
async def admin_eng_promo_create_code(message: Message, state: FSMContext):
    code = (message.text or '').strip().upper()
    if not code or len(code) < 4:
        await message.answer("❌ Promo code must be at least 4 characters.")
        return
    await state.update_data(code=code)
    await state.set_state(PromoCreateStates.waiting_for_tier)
    await message.answer(
        "Select promo tier:",
        reply_markup=engagement_promo_tier_keyboard(),
    )


@router.message(PromoCreateStates.waiting_for_tier)
async def admin_eng_promo_create_tier(message: Message, state: FSMContext):
    tier = (message.text or '').strip().lower()
    if tier not in {PromoCode.TIER_COMMON, PromoCode.TIER_RARE, PromoCode.TIER_LEGENDARY}:
        await message.answer("❌ Tier must be common, rare, or legendary.")
        return
    await state.update_data(tier=tier)
    await state.set_state(PromoCreateStates.waiting_for_amount)
    await message.answer("Enter reward amount in Birr:")


@router.message(PromoCreateStates.waiting_for_amount)
async def admin_eng_promo_create_amount(message: Message, state: FSMContext):
    try:
        amount = Decimal((message.text or '').strip())
    except (InvalidOperation, AttributeError):
        await message.answer("❌ Invalid amount.")
        return
    if amount <= 0:
        await message.answer("❌ Amount must be > 0.")
        return
    await state.update_data(amount=str(amount))
    await state.set_state(PromoCreateStates.waiting_for_balance)
    await message.answer(
        "Select balance target:",
        reply_markup=engagement_balance_target_keyboard(),
    )


@router.message(PromoCreateStates.waiting_for_balance)
async def admin_eng_promo_create_balance(message: Message, state: FSMContext):
    balance = (message.text or '').strip().lower()
    if balance not in {PromoCode.BALANCE_BONUS, PromoCode.BALANCE_MAIN, PromoCode.BALANCE_WINNINGS}:
        await message.answer("❌ Balance must be bonus, main, or winnings.")
        return
    await state.update_data(balance=balance)
    await state.set_state(PromoCreateStates.waiting_for_start_minutes)
    await message.answer("Start in how many minutes from now? (0 for immediate)")


@router.message(PromoCreateStates.waiting_for_start_minutes)
async def admin_eng_promo_create_start_minutes(message: Message, state: FSMContext):
    try:
        minutes = int((message.text or '').strip())
    except (TypeError, ValueError):
        await message.answer("❌ Please enter a whole number.")
        return
    if minutes < 0:
        await message.answer("❌ Start minutes cannot be negative.")
        return
    await state.update_data(start_minutes=minutes)
    await state.set_state(PromoCreateStates.waiting_for_duration_minutes)
    await message.answer("Duration in minutes?")


@router.message(PromoCreateStates.waiting_for_duration_minutes)
async def admin_eng_promo_create_duration_minutes(message: Message, state: FSMContext):
    try:
        minutes = int((message.text or '').strip())
    except (TypeError, ValueError):
        await message.answer("❌ Please enter a whole number.")
        return
    if minutes <= 0:
        await message.answer("❌ Duration must be > 0.")
        return
    await state.update_data(duration_minutes=minutes)
    await state.set_state(PromoCreateStates.waiting_for_max_redemptions)
    await message.answer("Max redemptions globally? (0 for unlimited)")


@router.message(PromoCreateStates.waiting_for_max_redemptions)
async def admin_eng_promo_create_max_redemptions(message: Message, state: FSMContext):
    try:
        max_redemptions = int((message.text or '').strip())
    except (TypeError, ValueError):
        await message.answer("❌ Please enter a whole number.")
        return
    if max_redemptions < 0:
        await message.answer("❌ Max redemptions cannot be negative.")
        return
    await state.update_data(max_redemptions=max_redemptions)
    await state.set_state(PromoCreateStates.waiting_for_per_user_limit)
    await message.answer("Per-user redemption limit? (usually 1)")


@router.message(PromoCreateStates.waiting_for_per_user_limit)
async def admin_eng_promo_create_per_user_limit(message: Message, state: FSMContext):
    try:
        per_user_limit = int((message.text or '').strip())
    except (TypeError, ValueError):
        await message.answer("❌ Please enter a whole number.")
        return
    if per_user_limit <= 0:
        await message.answer("❌ Per-user limit must be > 0.")
        return

    await state.update_data(per_user_limit=per_user_limit)
    await state.set_state(PromoCreateStates.waiting_for_frontend_visibility)
    await message.answer(
        "Should this promo be visible in frontend promo list?",
        reply_markup=engagement_frontend_visibility_keyboard(),
    )


@router.callback_query(F.data.startswith("eng:promo:frontend:"))
async def admin_eng_promo_create_frontend_visibility(callback: CallbackQuery, state: FSMContext):
    value = callback.data.split(":")[-1]
    if value not in {"show", "hide"}:
        await callback.answer("Invalid option", show_alert=True)
        return

    data = await state.get_data()
    if not data:
        await callback.answer("Promo draft expired. Start again.", show_alert=True)
        await state.clear()
        return

    per_user_limit = int(data.get('per_user_limit', 1))
    is_visible_in_frontend = (value == "show")
    now = timezone.now()
    starts_at = now + timedelta(minutes=int(data['start_minutes']))
    ends_at = starts_at + timedelta(minutes=int(data['duration_minutes']))

    @sync_to_async
    def _create_promo():
        if PromoCode.objects.filter(code=data['code']).exists():
            return None
        return PromoCode.objects.create(
            code=data['code'],
            tier=data['tier'],
            reward_amount=Decimal(data['amount']),
            reward_balance=data['balance'],
            starts_at=starts_at,
            ends_at=ends_at,
            max_redemptions=int(data['max_redemptions']),
            per_user_limit=per_user_limit,
            is_active=True,
            is_visible_in_frontend=is_visible_in_frontend,
        )

    promo = await _create_promo()
    if not promo:
        await message.answer("❌ Promo code already exists.")
        await state.clear()
        return

    await message.answer(
        f"✅ Promo created: {promo.code}\n"
        f"Tier: {promo.tier}\n"
        f"Reward: {promo.reward_amount} -> {promo.reward_balance}\n"
        f"Window: {promo.starts_at:%Y-%m-%d %H:%M} to {promo.ends_at:%Y-%m-%d %H:%M}\n"
        f"Limits: global={promo.max_redemptions if promo.max_redemptions > 0 else '∞'}, per-user={promo.per_user_limit}\n"
        f"Frontend: {'Visible' if promo.is_visible_in_frontend else 'Hidden'}",
        reply_markup=admin_main_menu_keyboard(),
    )
    await callback.answer("Promo created")
    await state.clear()


@router.message(Command("eng_event_list"))
async def admin_eng_event_list(message: Message):
    if not await _ensure_admin(message):
        return

    @sync_to_async
    def _rows():
        now = timezone.now()
        rows = []
        for event in LiveEvent.objects.order_by('-starts_at')[:15]:
            rows.append({
                'id': event.id,
                'name': event.name,
                'event_type': event.event_type,
                'multiplier': event.bonus_multiplier,
                'state': 'LIVE' if (event.is_active and event.starts_at <= now <= event.ends_at) else ('UPCOMING' if event.is_active and event.starts_at > now else ('ACTIVE' if event.is_active else 'OFF')),
                'starts_at': event.starts_at,
                'ends_at': event.ends_at,
            })
        return rows

    rows = await _rows()
    if not rows:
        await message.answer("No live events found.", reply_markup=admin_main_menu_keyboard())
        return

    lines = ["<b>🎉 Live Events (latest 15)</b>"]
    for row in rows:
        lines.append(
            f"#{row['id']} {row['name']} [{row['event_type']}] {row['state']}\n"
            f"Multiplier: {row['multiplier']}x\n"
            f"Window: {row['starts_at']:%Y-%m-%d %H:%M} -> {row['ends_at']:%Y-%m-%d %H:%M}\n"
            f"Disable: /eng_event_disable_{row['id']}"
        )
    await message.answer("\n\n".join(lines), reply_markup=admin_main_menu_keyboard())


@router.message(F.text.regexp(r"^/eng_event_disable_(\d+)$"))
async def admin_eng_event_disable(message: Message):
    if not await _ensure_admin(message):
        return

    try:
        event_id = int(message.text.split("_")[-1])
    except (TypeError, ValueError):
        await message.answer("❌ Invalid event reference.")
        return

    @sync_to_async
    def _disable():
        event = LiveEvent.objects.filter(id=event_id).first()
        if not event:
            return False, None
        event.is_active = False
        event.save(update_fields=['is_active', 'updated_at'])
        return True, event

    ok, event = await _disable()
    if not ok:
        await message.answer("❌ Event not found.", reply_markup=admin_main_menu_keyboard())
        return

    await message.answer(f"✅ Event '{event.name}' disabled.", reply_markup=admin_main_menu_keyboard())


@router.message(Command("eng_event_create"))
async def admin_eng_event_create_start(message: Message, state: FSMContext):
    if not await _ensure_admin(message):
        return
    await state.set_state(EventCreateStates.waiting_for_name)
    await message.answer("Enter event name:")


@router.message(EventCreateStates.waiting_for_name)
async def admin_eng_event_create_name(message: Message, state: FSMContext):
    name = (message.text or '').strip()
    if not name:
        await message.answer("❌ Event name is required.")
        return
    await state.update_data(name=name)
    await state.set_state(EventCreateStates.waiting_for_type)
    await message.answer(
        "Select event type:",
        reply_markup=engagement_event_type_keyboard(),
    )


@router.message(EventCreateStates.waiting_for_type)
async def admin_eng_event_create_type(message: Message, state: FSMContext):
    event_type = (message.text or '').strip().lower()
    allowed = {LiveEvent.TYPE_HAPPY_HOUR, LiveEvent.TYPE_FLASH_PROMO, LiveEvent.TYPE_DOUBLE_REWARD}
    if event_type not in allowed:
        await message.answer("❌ Invalid event type.")
        return
    await state.update_data(event_type=event_type)
    await state.set_state(EventCreateStates.waiting_for_multiplier)
    await message.answer("Enter reward multiplier (e.g. 1.00, 1.50, 2.00)")


@router.message(EventCreateStates.waiting_for_multiplier)
async def admin_eng_event_create_multiplier(message: Message, state: FSMContext):
    try:
        multiplier = Decimal((message.text or '').strip())
    except (InvalidOperation, AttributeError):
        await message.answer("❌ Invalid multiplier.")
        return
    if multiplier < Decimal('1.00'):
        await message.answer("❌ Multiplier must be >= 1.00.")
        return
    await state.update_data(multiplier=str(multiplier))
    await state.set_state(EventCreateStates.waiting_for_start_minutes)
    await message.answer("Start in how many minutes from now? (0 for immediate)")


@router.message(EventCreateStates.waiting_for_start_minutes)
async def admin_eng_event_create_start_minutes(message: Message, state: FSMContext):
    try:
        minutes = int((message.text or '').strip())
    except (TypeError, ValueError):
        await message.answer("❌ Please enter a whole number.")
        return
    if minutes < 0:
        await message.answer("❌ Start minutes cannot be negative.")
        return
    await state.update_data(start_minutes=minutes)
    await state.set_state(EventCreateStates.waiting_for_duration_minutes)
    await message.answer("Duration in minutes?")


@router.message(EventCreateStates.waiting_for_duration_minutes)
async def admin_eng_event_create_duration_minutes(message: Message, state: FSMContext):
    try:
        minutes = int((message.text or '').strip())
    except (TypeError, ValueError):
        await message.answer("❌ Please enter a whole number.")
        return
    if minutes <= 0:
        await message.answer("❌ Duration must be > 0.")
        return

    data = await state.get_data()
    starts_at = timezone.now() + timedelta(minutes=int(data['start_minutes']))
    ends_at = starts_at + timedelta(minutes=minutes)

    @sync_to_async
    def _create_event():
        return LiveEvent.objects.create(
            name=data['name'],
            event_type=data['event_type'],
            starts_at=starts_at,
            ends_at=ends_at,
            bonus_multiplier=Decimal(data['multiplier']),
            is_active=True,
            auto_announce=True,
        )

    event = await _create_event()
    await message.answer(
        f"✅ Live event created: {event.name}\n"
        f"Type: {event.event_type}\n"
        f"Multiplier: {event.bonus_multiplier}x\n"
        f"Window: {event.starts_at:%Y-%m-%d %H:%M} -> {event.ends_at:%Y-%m-%d %H:%M}",
        reply_markup=admin_main_menu_keyboard(),
    )
    await state.clear()


@router.message(Command("eng_mission_list"))
async def admin_eng_mission_list(message: Message):
    if not await _ensure_admin(message):
        return

    @sync_to_async
    def _rows():
        return list(MissionTemplate.objects.order_by('sort_order', 'id')[:30])

    missions = await _rows()
    if not missions:
        await message.answer("No missions found.", reply_markup=admin_main_menu_keyboard())
        return

    lines = ["<b>🎯 Missions</b>"]
    for mission in missions:
        state = "🟢 ON" if mission.is_active else "🔴 OFF"
        lines.append(
            f"#{mission.id} {mission.title} {state}\n"
            f"Key: {mission.key} | Type: {mission.mission_type} | Period: {mission.period}\n"
            f"Target: {mission.target_value} | Reward: {mission.reward_amount} -> {mission.reward_balance}\n"
            f"Toggle: /eng_mission_toggle_{mission.id}"
        )
    await message.answer("\n\n".join(lines), reply_markup=admin_main_menu_keyboard())


@router.message(F.text.regexp(r"^/eng_mission_toggle_(\d+)$"))
async def admin_eng_mission_toggle(message: Message):
    if not await _ensure_admin(message):
        return

    try:
        mission_id = int(message.text.split("_")[-1])
    except (TypeError, ValueError):
        await message.answer("❌ Invalid mission reference.")
        return

    @sync_to_async
    def _toggle():
        mission = MissionTemplate.objects.filter(id=mission_id).first()
        if not mission:
            return None
        mission.is_active = not mission.is_active
        mission.save(update_fields=['is_active', 'updated_at'])
        return mission

    mission = await _toggle()
    if not mission:
        await message.answer("❌ Mission not found.", reply_markup=admin_main_menu_keyboard())
        return

    await message.answer(
        f"✅ Mission '{mission.title}' is now {'active' if mission.is_active else 'disabled'}.",
        reply_markup=admin_main_menu_keyboard(),
    )


@router.message(Command("eng_season_list"))
async def admin_eng_season_list(message: Message):
    if not await _ensure_admin(message):
        return

    @sync_to_async
    def _rows():
        return list(Season.objects.order_by('-starts_at')[:12])

    seasons = await _rows()
    if not seasons:
        await message.answer("No seasons found.", reply_markup=admin_main_menu_keyboard())
        return

    lines = ["<b>🏆 Seasons</b>"]
    now = timezone.now()
    for season in seasons:
        if season.is_active and season.starts_at <= now <= season.ends_at:
            status = "🟢 CURRENT"
        elif season.is_active:
            status = "🟡 ACTIVE"
        else:
            status = "🔴 OFF"
        lines.append(
            f"#{season.id} {season.name} {status}\n"
            f"Window: {season.starts_at:%Y-%m-%d} -> {season.ends_at:%Y-%m-%d}\n"
            f"Rewards: 1st={season.top_1_reward}, 2nd={season.top_2_reward}, 3rd={season.top_3_reward}, participation={season.participation_reward}\n"
            f"Activate: /eng_season_activate_{season.id}"
        )
    await message.answer("\n\n".join(lines), reply_markup=admin_main_menu_keyboard())


@router.message(F.text.regexp(r"^/eng_season_activate_(\d+)$"))
async def admin_eng_season_activate(message: Message):
    if not await _ensure_admin(message):
        return

    try:
        season_id = int(message.text.split("_")[-1])
    except (TypeError, ValueError):
        await message.answer("❌ Invalid season reference.")
        return

    @sync_to_async
    def _activate():
        target = Season.objects.filter(id=season_id).first()
        if not target:
            return None
        Season.objects.exclude(id=target.id).update(is_active=False)
        target.is_active = True
        target.save(update_fields=['is_active', 'updated_at'])
        return target

    season = await _activate()
    if not season:
        await message.answer("❌ Season not found.", reply_markup=admin_main_menu_keyboard())
        return

    await message.answer(
        f"✅ Season '{season.name}' activated.",
        reply_markup=admin_main_menu_keyboard(),
    )


@router.message(Command("eng_season_create"))
async def admin_eng_season_create_start(message: Message, state: FSMContext):
    if not await _ensure_admin(message):
        return
    await state.set_state(SeasonCreateStates.waiting_for_name)
    await message.answer("Enter season name:")


@router.message(SeasonCreateStates.waiting_for_name)
async def admin_eng_season_create_name(message: Message, state: FSMContext):
    name = (message.text or '').strip()
    if not name:
        await message.answer("❌ Season name is required.")
        return
    await state.update_data(name=name)
    await state.set_state(SeasonCreateStates.waiting_for_days)
    await message.answer("Season duration in days?")


@router.message(SeasonCreateStates.waiting_for_days)
async def admin_eng_season_create_days(message: Message, state: FSMContext):
    try:
        days = int((message.text or '').strip())
    except (TypeError, ValueError):
        await message.answer("❌ Please enter a whole number.")
        return
    if days <= 0:
        await message.answer("❌ Duration must be > 0 days.")
        return
    await state.update_data(days=days)
    await state.set_state(SeasonCreateStates.waiting_for_top1)
    await message.answer("Top 1 reward amount?")


@router.message(SeasonCreateStates.waiting_for_top1)
async def admin_eng_season_create_top1(message: Message, state: FSMContext):
    try:
        amount = Decimal((message.text or '').strip())
    except (InvalidOperation, AttributeError):
        await message.answer("❌ Invalid amount.")
        return
    if amount < 0:
        await message.answer("❌ Amount cannot be negative.")
        return
    await state.update_data(top1=str(amount))
    await state.set_state(SeasonCreateStates.waiting_for_top2)
    await message.answer("Top 2 reward amount?")


@router.message(SeasonCreateStates.waiting_for_top2)
async def admin_eng_season_create_top2(message: Message, state: FSMContext):
    try:
        amount = Decimal((message.text or '').strip())
    except (InvalidOperation, AttributeError):
        await message.answer("❌ Invalid amount.")
        return
    if amount < 0:
        await message.answer("❌ Amount cannot be negative.")
        return
    await state.update_data(top2=str(amount))
    await state.set_state(SeasonCreateStates.waiting_for_top3)
    await message.answer("Top 3 reward amount?")


@router.message(SeasonCreateStates.waiting_for_top3)
async def admin_eng_season_create_top3(message: Message, state: FSMContext):
    try:
        amount = Decimal((message.text or '').strip())
    except (InvalidOperation, AttributeError):
        await message.answer("❌ Invalid amount.")
        return
    if amount < 0:
        await message.answer("❌ Amount cannot be negative.")
        return
    await state.update_data(top3=str(amount))
    await state.set_state(SeasonCreateStates.waiting_for_participation)
    await message.answer("Participation reward amount?")


@router.message(SeasonCreateStates.waiting_for_participation)
async def admin_eng_season_create_participation(message: Message, state: FSMContext):
    try:
        amount = Decimal((message.text or '').strip())
    except (InvalidOperation, AttributeError):
        await message.answer("❌ Invalid amount.")
        return
    if amount < 0:
        await message.answer("❌ Amount cannot be negative.")
        return

    data = await state.get_data()
    starts_at = timezone.now()
    ends_at = starts_at + timedelta(days=int(data['days']))

    @sync_to_async
    def _create():
        return Season.objects.create(
            name=data['name'],
            starts_at=starts_at,
            ends_at=ends_at,
            is_active=False,
            top_1_reward=Decimal(data['top1']),
            top_2_reward=Decimal(data['top2']),
            top_3_reward=Decimal(data['top3']),
            participation_reward=amount,
        )

    season = await _create()
    await message.answer(
        f"✅ Season created: {season.name}\n"
        f"Window: {season.starts_at:%Y-%m-%d %H:%M} -> {season.ends_at:%Y-%m-%d %H:%M}\n"
        f"Use /eng_season_activate_{season.id} to activate it.",
        reply_markup=admin_main_menu_keyboard(),
    )
    await state.clear()


@router.message(Command("eng_policy_show"))
async def admin_eng_policy_show(message: Message):
    if not await _ensure_admin(message):
        return

    @sync_to_async
    def _get_policy():
        return RewardSafetyPolicy.get_active()

    policy = await _get_policy()
    await message.answer(
        "<b>🛡 Reward Safety Policy</b>\n\n"
        f"Daily Cap: {policy.daily_reward_cap} Birr\n"
        f"Cooldown: {policy.min_seconds_between_rewards} seconds\n"
        f"Hourly Redemptions Limit: {policy.max_reward_redemptions_per_hour}\n\n"
        "Use /eng_policy_set to update values.",
        reply_markup=admin_main_menu_keyboard(),
    )


@router.message(Command("eng_policy_set"))
async def admin_eng_policy_set_start(message: Message, state: FSMContext):
    if not await _ensure_admin(message):
        return
    await state.set_state(RewardPolicyStates.waiting_for_daily_cap)
    await message.answer("Enter new daily reward cap (Birr):")


@router.message(RewardPolicyStates.waiting_for_daily_cap)
async def admin_eng_policy_set_daily_cap(message: Message, state: FSMContext):
    try:
        cap = Decimal((message.text or '').strip())
    except (InvalidOperation, AttributeError):
        await message.answer("❌ Invalid amount.")
        return
    if cap <= 0:
        await message.answer("❌ Daily cap must be > 0.")
        return
    await state.update_data(daily_cap=str(cap))
    await state.set_state(RewardPolicyStates.waiting_for_cooldown_seconds)
    await message.answer("Enter cooldown in seconds:")


@router.message(RewardPolicyStates.waiting_for_cooldown_seconds)
async def admin_eng_policy_set_cooldown(message: Message, state: FSMContext):
    try:
        cooldown = int((message.text or '').strip())
    except (TypeError, ValueError):
        await message.answer("❌ Please enter a whole number.")
        return
    if cooldown < 0:
        await message.answer("❌ Cooldown cannot be negative.")
        return
    await state.update_data(cooldown=cooldown)
    await state.set_state(RewardPolicyStates.waiting_for_hourly_limit)
    await message.answer("Enter hourly redemption limit:")


@router.message(RewardPolicyStates.waiting_for_hourly_limit)
async def admin_eng_policy_set_hourly_limit(message: Message, state: FSMContext):
    try:
        hourly_limit = int((message.text or '').strip())
    except (TypeError, ValueError):
        await message.answer("❌ Please enter a whole number.")
        return
    if hourly_limit <= 0:
        await message.answer("❌ Hourly limit must be > 0.")
        return

    data = await state.get_data()

    @sync_to_async
    def _save_policy():
        policy = RewardSafetyPolicy.get_active()
        policy.daily_reward_cap = Decimal(data['daily_cap'])
        policy.min_seconds_between_rewards = int(data['cooldown'])
        policy.max_reward_redemptions_per_hour = hourly_limit
        policy.save(update_fields=['daily_reward_cap', 'min_seconds_between_rewards', 'max_reward_redemptions_per_hour', 'updated_at'])
        return policy

    policy = await _save_policy()
    await message.answer(
        "✅ Reward safety policy updated.\n"
        f"Daily Cap: {policy.daily_reward_cap} Birr\n"
        f"Cooldown: {policy.min_seconds_between_rewards}s\n"
        f"Hourly Limit: {policy.max_reward_redemptions_per_hour}",
        reply_markup=admin_main_menu_keyboard(),
    )
    await state.clear()

