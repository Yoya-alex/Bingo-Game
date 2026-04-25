from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from asgiref.sync import sync_to_async
from django.conf import settings

from users.models import User
from wallet.models import Wallet, Transaction, Deposit, Withdrawal
from bot.keyboards import main_menu_keyboard, deposit_keyboard, withdrawal_keyboard, payment_method_keyboard
from bot.utils.notification_service import send_admin_notification
from bot.utils.receipt_verifier import verify_receipt
from bot.utils.i18n import is_menu_text, normalize_language, tr
from game.business_rules import get_business_rules

router = Router()


class DepositStates(StatesGroup):
    waiting_for_confirmation = State()


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


@sync_to_async
def get_telebirr_details():
    rules = get_business_rules()
    return {
        'number': rules.telebirr_receiving_phone_number,
        'name': getattr(rules, 'telebirr_receiving_account_name', 'Bingo Bot'),
    }


@sync_to_async
def get_minimum_withdrawal_amount():
    return float(get_business_rules().minimum_withdrawable_balance)


@sync_to_async
def _reject_transaction(transaction_id: int, extracted_text: str):
    from wallet.models import Transaction, Deposit
    t = Transaction.objects.get(id=transaction_id)
    t.status = "rejected"
    t.save()
    try:
        d = t.deposit_detail
        d.extracted_text = extracted_text
        d.save()
    except Exception:
        pass


@router.message(lambda message: is_menu_text(message.text, 'menu_balance'))
async def show_balance(message: Message):
    """Show user balance"""
    user = await get_user_with_wallet(message.from_user.id)
    
    if not user:
        await message.answer(tr('en', 'please_start'))
        return
    
    wallet = user.wallet
    language = normalize_language(user.language)
    balance_text = tr(
        language,
        'wallet_balance_text',
        main_balance=wallet.main_balance,
        winnings_balance=wallet.winnings_balance,
        bonus_balance=wallet.bonus_balance,
        total_balance=wallet.total_balance,
    )
    
    await message.answer(balance_text, reply_markup=main_menu_keyboard(language))


@router.message(lambda message: is_menu_text(message.text, 'menu_deposit'))
async def deposit_menu(message: Message):
    """Show deposit menu"""
    from asgiref.sync import sync_to_async
    get_rules = sync_to_async(get_business_rules)
    rules = await get_rules()
    telebirr_number = rules.telebirr_receiving_phone_number
    telebirr_name = rules.telebirr_receiving_account_name
    
    user = await get_user_with_wallet(message.from_user.id)
    if not user:
        await message.answer(tr('en', 'please_start'))
        return
    language = normalize_language(user.language)
    
    deposit_text = tr(
        language,
        'wallet_deposit_text',
        telebirr_number=telebirr_number,
        telebirr_name=telebirr_name,
        min_deposit=settings.MIN_DEPOSIT,
    )
    
    await message.answer(deposit_text, reply_markup=deposit_keyboard(), parse_mode="HTML")


@router.callback_query(F.data == "submit_deposit")
async def submit_deposit_start(callback: CallbackQuery, state: FSMContext):
    """Start deposit submission process"""
    user = await get_user_with_wallet(callback.from_user.id)
    language = normalize_language(getattr(user, 'language', None))
    await callback.message.answer(
        tr(language, 'wallet_confirmation_prompt')
    )
    await state.set_state(DepositStates.waiting_for_confirmation)
    await callback.answer()


@router.message(DepositStates.waiting_for_confirmation, F.text)
async def process_deposit_confirmation(message: Message, state: FSMContext):
    """Process deposit confirmation — manual admin verification."""
    user = await get_user_with_wallet(message.from_user.id)

    if not user:
        await message.answer(tr('en', 'please_start'))
        await state.clear()
        return

    confirmation_text = (message.text or "").strip()
    if not confirmation_text:
        await message.answer(tr(normalize_language(user.language), 'wallet_confirmation_required'))
        return

    # Create a pending transaction
    transaction = await create_transaction(
        user, 'deposit', None, 'pending', 'Deposit pending admin verification'
    )
    await create_deposit(transaction, confirmation_text, 'Telebirr')

    language = normalize_language(user.language)
    
    await message.answer(
        f"✅ <b>Deposit Submitted</b>\n\n"
        f"Your receipt has been received.\n"
        f"An admin will verify and approve it shortly.\n\n"
        f"<b>Transaction ID:</b> #{transaction.id}\n"
        f"<b>Status:</b> Pending Review",
        reply_markup=main_menu_keyboard(language),
        parse_mode="HTML"
    )

    # Notify admins about new deposit
    try:
        await send_admin_notification(
            message.bot,
            text=(
                "🔔 <b>New Deposit Submission</b>\n\n"
                f"User: {user.first_name} (@{user.username or '—'})\n"
                f"Receipt/Link: {confirmation_text}\n"
                f"Transaction ID: #{transaction.id}\n\n"
                "Please verify and approve/reject in admin panel."
            ),
        )
    except Exception:
        pass

    await state.clear()


@router.message(lambda message: is_menu_text(message.text, 'menu_withdraw'))
async def withdrawal_menu(message: Message):
    """Show withdrawal menu"""
    user = await get_user_with_wallet(message.from_user.id)

    if not user:
        await message.answer(tr('en', 'please_start'))
        return
    
    wallet = user.wallet
    language = normalize_language(user.language)
    minimum_withdrawal = await get_minimum_withdrawal_amount()
    
    # Check minimum withdrawal amount - only winnings can be withdrawn
    if float(wallet.winnings_balance) < minimum_withdrawal:
        await message.answer(
            tr(
                language,
                'wallet_withdraw_insufficient',
                winnings_balance=wallet.winnings_balance,
                main_balance=wallet.main_balance,
                bonus_balance=wallet.bonus_balance,
                minimum_withdrawal=minimum_withdrawal,
            ),
            reply_markup=main_menu_keyboard(language),
            parse_mode="HTML"
        )
        return
    
    withdrawal_text = tr(
        language,
        'wallet_withdraw_menu',
        winnings_balance=wallet.winnings_balance,
        main_balance=wallet.main_balance,
        bonus_balance=wallet.bonus_balance,
        minimum_withdrawal=minimum_withdrawal,
    )
    
    await message.answer(withdrawal_text, reply_markup=withdrawal_keyboard(), parse_mode="HTML")


@router.callback_query(F.data == "request_withdrawal")
async def request_withdrawal_start(callback: CallbackQuery, state: FSMContext):
    """Start withdrawal request process"""
    user = await get_user_with_wallet(callback.from_user.id)
    language = normalize_language(getattr(user, 'language', None))
    minimum_withdrawal = await get_minimum_withdrawal_amount()
    await callback.message.answer(
        tr(language, 'wallet_withdraw_request_prompt', minimum_withdrawal=minimum_withdrawal)
    )
    await state.set_state(WithdrawalStates.waiting_for_amount)
    await callback.answer()


@router.message(WithdrawalStates.waiting_for_amount)
async def process_withdrawal_amount(message: Message, state: FSMContext):
    """Process withdrawal amount"""
    try:
        amount = float(message.text)
        user = await get_user_with_wallet(message.from_user.id)
        minimum_withdrawal = await get_minimum_withdrawal_amount()
        
        if not user:
            await message.answer(tr('en', 'please_start'))
            await state.clear()
            return
        
        wallet = user.wallet
        language = normalize_language(user.language)
        
        if amount <= 0:
            await message.answer(tr(language, 'wallet_amount_gt_zero'))
            return

        if amount < minimum_withdrawal:
            await message.answer(tr(language, 'wallet_min_withdraw', minimum_withdrawal=minimum_withdrawal))
            return
        
        if amount > wallet.winnings_balance:
            await message.answer(tr(language, 'wallet_insufficient_winnings', winnings_balance=wallet.winnings_balance))
            return
        
        await state.update_data(amount=amount)
        await message.answer(
            tr(language, 'wallet_select_method'),
            reply_markup=payment_method_keyboard(),
            parse_mode="HTML"
        )
        await state.set_state(WithdrawalStates.waiting_for_method)
        
    except ValueError:
        await message.answer(tr('en', 'wallet_enter_valid_number'))


@router.message(WithdrawalStates.waiting_for_method)
async def process_withdrawal_method(message: Message, state: FSMContext):
    """Process withdrawal payment method"""
    user = await get_user_with_wallet(message.from_user.id)
    language = normalize_language(getattr(user, 'language', None))
    await state.update_data(payment_method=message.text)
    await message.answer(
        tr(language, 'wallet_account_prompt')
    )
    await state.set_state(WithdrawalStates.waiting_for_account)


@router.callback_query(F.data.startswith("payment_method:"), WithdrawalStates.waiting_for_method)
async def process_payment_method_callback(callback: CallbackQuery, state: FSMContext):
    """Handle payment method button selection"""
    user = await get_user_with_wallet(callback.from_user.id)
    language = normalize_language(getattr(user, 'language', None))
    method = callback.data.split(":")[1]
    
    if method == "cbe":
        payment_method = "CBE (Commercial Bank of Ethiopia)"
        prompt = tr(language, 'wallet_cbe_prompt')
    else:  # telebirr
        payment_method = "Telebirr"
        prompt = tr(language, 'wallet_telebirr_prompt')
    
    await state.update_data(payment_method=payment_method)
    await callback.message.answer(prompt, parse_mode="HTML")
    await state.set_state(WithdrawalStates.waiting_for_account)
    await callback.answer()


@router.message(WithdrawalStates.waiting_for_account)
async def process_withdrawal_account(message: Message, state: FSMContext):
    """Complete withdrawal request"""
    user = await get_user_with_wallet(message.from_user.id)
    
    if not user:
        await message.answer(tr('en', 'please_start'))
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
        tr(
            normalize_language(user.language),
            'wallet_withdraw_submitted',
            amount=data['amount'],
            payment_method=data['payment_method'],
            account=message.text,
            transaction_id=transaction.id,
        ),
        reply_markup=main_menu_keyboard(normalize_language(user.language))
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
    user = await get_user_with_wallet(callback.from_user.id)
    language = normalize_language(getattr(user, 'language', None))
    await callback.message.answer(
        tr(language, 'main_menu_title'),
        reply_markup=main_menu_keyboard(language)
    )
    await callback.answer()
