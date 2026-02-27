from aiogram import Router, F
from decimal import Decimal, InvalidOperation
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
from game.models import Game
from bot.keyboards import (
    admin_main_menu_keyboard,
    main_menu_keyboard,
    wallet_balance_type_keyboard,
    wallet_direction_keyboard,
)
from bot.utils.admin_helpers import is_admin, get_admin_user
from bot.utils.notification_service import send_admin_notification


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

