from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from asgiref.sync import sync_to_async
from django.conf import settings

from users.models import User
from wallet.models import Wallet, Transaction, Deposit, Withdrawal
from bot.keyboards import main_menu_keyboard, deposit_keyboard, withdrawal_keyboard
from bot.utils.notification_service import send_admin_notification

router = Router()


class DepositStates(StatesGroup):
    waiting_for_amount = State()
    waiting_for_proof = State()


class WithdrawalStates(StatesGroup):
    waiting_for_amount = State()
    waiting_for_method = State()
    waiting_for_account = State()


@sync_to_async
def get_user_with_wallet(telegram_id):
    try:
        user = User.objects.select_related('wallet').get(telegram_id=telegram_id)
        return user
    except User.DoesNotExist:
        return None


@sync_to_async
def create_transaction(user, trans_type, amount, status, description):
    return Transaction.objects.create(
        user=user,
        transaction_type=trans_type,
        amount=amount,
        status=status,
        description=description
    )


@sync_to_async
def create_deposit(transaction, proof, method):
    return Deposit.objects.create(
        transaction=transaction,
        payment_proof=proof,
        payment_method=method
    )


@sync_to_async
def create_withdrawal(transaction, method, account):
    return Withdrawal.objects.create(
        transaction=transaction,
        payment_method=method,
        account_info=account
    )


@router.message(F.text == "💰 Balance")
async def show_balance(message: Message):
    """Show user balance"""
    user = await get_user_with_wallet(message.from_user.id)
    
    if not user:
        await message.answer("❌ Please start the bot first with /start")
        return
    
    wallet = user.wallet
    balance_text = (
        f"<b>💰 YOUR BALANCE</b>\n\n"
        f"💵 Main Balance: {wallet.main_balance} Birr\n"
        f"🎁 Bonus Balance: {wallet.bonus_balance} Birr\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"💎 Total Balance: {wallet.total_balance} Birr\n\n"
        f"<i>Note: Bonus balance can only be used for playing</i>"
    )
    
    await message.answer(balance_text, reply_markup=main_menu_keyboard())


@router.message(F.text == "➕ Deposit")
async def deposit_menu(message: Message):
    """Show deposit menu"""
    deposit_text = (
        "<b>➕ DEPOSIT</b>\n\n"
        "To deposit money:\n\n"
        "1️⃣ Transfer money to:\n"
        "   <b>Bank:</b> Commercial Bank of Ethiopia\n"
        "   <b>Account:</b> 1000123456789\n"
        "   <b>Name:</b> Bingo Bot\n\n"
        "2️⃣ Take a screenshot of the transaction\n"
        "3️⃣ Click 'Submit Deposit Proof' below\n\n"
        f"<i>Minimum deposit: {settings.MIN_DEPOSIT} Birr</i>"
    )
    
    await message.answer(deposit_text, reply_markup=deposit_keyboard())


@router.callback_query(F.data == "submit_deposit")
async def submit_deposit_start(callback: CallbackQuery, state: FSMContext):
    """Start deposit submission process"""
    await callback.message.answer(
        "📤 <b>Deposit Amount</b>\n\n"
        "Please enter the amount you deposited (in Birr):"
    )
    await state.set_state(DepositStates.waiting_for_amount)
    await callback.answer()


@router.message(DepositStates.waiting_for_amount)
async def process_deposit_amount(message: Message, state: FSMContext):
    """Capture and validate deposit amount before proof."""
    try:
        amount = float(message.text)
    except ValueError:
        await message.answer("❌ Please enter a valid number for the amount.")
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

    await state.update_data(amount=amount)
    await message.answer(
        "📤 <b>Submit Deposit Proof</b>\n\n"
        "Now send a screenshot or photo of your transaction receipt."
    )
    await state.set_state(DepositStates.waiting_for_proof)


@router.message(DepositStates.waiting_for_proof, F.photo)
async def process_deposit_proof(message: Message, state: FSMContext):
    """Process deposit proof submission"""
    user = await get_user_with_wallet(message.from_user.id)
    
    if not user:
        await message.answer("❌ Please start the bot first with /start")
        await state.clear()
        return
    
    # Get photo file_id
    photo_file_id = message.photo[-1].file_id
    data = await state.get_data()
    amount = data.get("amount", 0)
    
    # Create transaction with pending status and provided amount
    transaction = await create_transaction(
        user,
        'deposit',
        amount,
        'pending',
        'Deposit pending verification',
    )
    
    # Create deposit detail
    await create_deposit(transaction, photo_file_id, 'Bank Transfer')
    
    await message.answer(
        "✅ <b>Deposit submitted!</b>\n\n"
        f"Amount: {amount} Birr\n"
        "Your deposit is pending admin verification.\n"
        "You'll be notified once it's approved.\n\n"
        f"Transaction ID: #{transaction.id}",
        reply_markup=main_menu_keyboard(),
    )

    # Notify admins about new deposit request
    try:
        await send_admin_notification(
            message.bot,
            text=(
                "🔔 <b>New Deposit Request</b>\n\n"
                f"User: {user.first_name} (@{user.username or '—'})\n"
                f"Amount: {amount} Birr\n"
                f"Transaction ID: #{transaction.id}"
            ),
        )
    except Exception:
        # Notification failures must not affect core flow
        pass

    await state.clear()


@router.message(F.text == "➖ Withdraw")
async def withdrawal_menu(message: Message):
    """Show withdrawal menu"""
    user = await get_user_with_wallet(message.from_user.id)
    
    if not user:
        await message.answer("❌ Please start the bot first with /start")
        return
    
    wallet = user.wallet
    withdrawal_text = (
        f"<b>➖ WITHDRAWAL</b>\n\n"
        f"💵 Available for withdrawal: {wallet.main_balance} Birr\n\n"
        f"<i>Note: Only main balance can be withdrawn.\n"
        f"Bonus balance cannot be withdrawn.</i>\n\n"
        f"Click below to request withdrawal:"
    )
    
    await message.answer(withdrawal_text, reply_markup=withdrawal_keyboard())


@router.callback_query(F.data == "request_withdrawal")
async def request_withdrawal_start(callback: CallbackQuery, state: FSMContext):
    """Start withdrawal request process"""
    await callback.message.answer(
        "💸 <b>Withdrawal Request</b>\n\n"
        "Please enter the amount you want to withdraw (in Birr):"
    )
    await state.set_state(WithdrawalStates.waiting_for_amount)
    await callback.answer()


@router.message(WithdrawalStates.waiting_for_amount)
async def process_withdrawal_amount(message: Message, state: FSMContext):
    """Process withdrawal amount"""
    try:
        amount = float(message.text)
        user = await get_user_with_wallet(message.from_user.id)
        
        if not user:
            await message.answer("❌ Please start the bot first with /start")
            await state.clear()
            return
        
        wallet = user.wallet
        
        if amount <= 0:
            await message.answer("❌ Amount must be greater than 0")
            return
        
        if amount > wallet.main_balance:
            await message.answer(
                f"❌ Insufficient balance!\n"
                f"Available: {wallet.main_balance} Birr"
            )
            return
        
        await state.update_data(amount=amount)
        await message.answer(
            "📱 <b>Payment Method</b>\n\n"
            "Please enter your payment method:\n"
            "(e.g., Bank Transfer, Mobile Money, etc.)"
        )
        await state.set_state(WithdrawalStates.waiting_for_method)
        
    except ValueError:
        await message.answer("❌ Please enter a valid number")


@router.message(WithdrawalStates.waiting_for_method)
async def process_withdrawal_method(message: Message, state: FSMContext):
    """Process withdrawal payment method"""
    await state.update_data(payment_method=message.text)
    await message.answer(
        "🏦 <b>Account Information</b>\n\n"
        "Please enter your account number or phone number:"
    )
    await state.set_state(WithdrawalStates.waiting_for_account)


@router.message(WithdrawalStates.waiting_for_account)
async def process_withdrawal_account(message: Message, state: FSMContext):
    """Complete withdrawal request"""
    user = await get_user_with_wallet(message.from_user.id)
    
    if not user:
        await message.answer("❌ Please start the bot first with /start")
        await state.clear()
        return
    
    data = await state.get_data()
    
    # Create transaction
    transaction = await create_transaction(
        user, 'withdrawal', data['amount'], 'pending', 'Withdrawal pending approval'
    )
    
    # Create withdrawal detail
    await create_withdrawal(transaction, data['payment_method'], message.text)
    
    await message.answer(
        "✅ <b>Withdrawal request submitted!</b>\n\n"
        f"Amount: {data['amount']} Birr\n"
        f"Method: {data['payment_method']}\n"
        f"Account: {message.text}\n\n"
        "Your request is pending admin approval.\n"
        f"Transaction ID: #{transaction.id}",
        reply_markup=main_menu_keyboard()
    )

    # Notify admins about new withdrawal request
    try:
        await send_admin_notification(
            message.bot,
            text=(
                "🔔 <b>New Withdrawal Request</b>\n\n"
                f"User: {user.first_name} (@{user.username or '—'})\n"
                f"Amount: {data['amount']} Birr\n"
                f"Transaction ID: #{transaction.id}"
            ),
        )
    except Exception:
        pass

    await state.clear()


@router.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: CallbackQuery, state: FSMContext):
    """Return to main menu"""
    await state.clear()
    await callback.message.answer(
        "🏠 Main Menu",
        reply_markup=main_menu_keyboard()
    )
    await callback.answer()
