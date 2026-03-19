from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramForbiddenError
from django.conf import settings
from asgiref.sync import sync_to_async
from urllib.parse import quote_plus
from typing import Optional

from users.models import User
from wallet.models import Wallet, Transaction
from bot.keyboards import main_menu_keyboard, admin_main_menu_keyboard
from bot.utils.db_helpers import get_or_create_user, create_wallet, save_model
from bot.utils.admin_helpers import is_admin
from bot.utils.referral_service import register_referral_for_new_user, get_user_referral_stats

router = Router()


def _normalize_bot_username(raw_value: Optional[str]) -> str:
    if not raw_value:
        return ""
    value = raw_value.strip()
    value = value.replace("https://t.me/", "").replace("http://t.me/", "")
    if value.startswith("@"):
        value = value[1:]
    return value.strip("/")


async def _resolve_bot_username(message: Message) -> str:
    runtime_username = _normalize_bot_username(getattr(message.bot, "username", None))
    if runtime_username:
        return runtime_username

    try:
        me = await message.bot.get_me()
        api_username = _normalize_bot_username(getattr(me, "username", None))
        if api_username:
            return api_username
    except Exception:
        pass

    configured = _normalize_bot_username(getattr(settings, "BOT_USERNAME", ""))
    if configured:
        return configured

    return "ethio_bingo_game_bot"


@router.message(CommandStart())
async def cmd_start(message: Message):
    """Handle /start command - Auto registration"""
    telegram_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name or "User"
    
    start_payload = None
    if message.text and len(message.text.split(maxsplit=1)) > 1:
        start_payload = message.text.split(maxsplit=1)[1].strip()

    # Check if user exists
    user, created = await get_or_create_user(telegram_id, username, first_name)
    
    if created:
        referral = await sync_to_async(register_referral_for_new_user)(user, start_payload)

        # Create wallet
        wallet = await create_wallet(user)
        
        # Give welcome bonus
        wallet.bonus_balance = settings.WELCOME_BONUS
        await save_model(wallet)
        
        # Log bonus transaction
        transaction = Transaction(
            user=user,
            transaction_type='bonus',
            amount=settings.WELCOME_BONUS,
            status='approved',
            description='Welcome bonus'
        )
        await save_model(transaction)

        referral_text = ""
        if referral and referral.status == 'PENDING':
            referral_text = (
                "\n\n🎯 Referral tracked successfully!\n"
                "Your inviter will receive bonus when you complete your first qualifying deposit."
            )
        
        welcome_text = (
            f"🎉 <b>Welcome to Bingo Bot, {first_name}!</b>\n\n"
            f"✅ Registration successful!\n"
            f"🎁 You received {settings.WELCOME_BONUS} Birr welcome bonus!\n\n"
            f"💡 Use your bonus to play your first Bingo game.\n"
            f"Note: Bonus money can only be used for playing, not for withdrawal.\n\n"
            f"Ready to play? Click 🎮 Play Bingo!"
            f"{referral_text}"
        )
    else:
        welcome_text = (
            f"👋 <b>Welcome back, {first_name}!</b>\n\n"
            f"Ready to play Bingo? Choose an option below:"
        )

    # If user is an admin, show admin menu by default (can switch back to user menu).
    try:
        if await is_admin(telegram_id):
            await message.answer(welcome_text, reply_markup=admin_main_menu_keyboard())
        else:
            await message.answer(welcome_text, reply_markup=main_menu_keyboard())
    except TelegramForbiddenError:
        # User has blocked the bot; avoid crashing the update handler.
        return


@router.message(F.text == "📜 Rules")
async def show_rules(message: Message):
    """Show game rules"""
    rules_text = (
        "<b>📜 BINGO GAME RULES</b>\n\n"
        "<b>How to Play:</b>\n"
        "1️⃣ Select a card (1-400) from the waiting screen\n"
        "2️⃣ Each card costs 10 Birr\n"
        "3️⃣ Wait for the game to start (25 seconds countdown)\n"
        f"4️⃣ Numbers will be called randomly (1-{settings.BINGO_NUMBER_MAX})\n"
        "5️⃣ Mark numbers on your 5×5 grid\n"
        "6️⃣ Complete a line (horizontal, vertical, or diagonal)\n"
        "7️⃣ Click BINGO button to claim your win!\n\n"
        "<b>💰 Wallet Rules:</b>\n"
        "• Minimum deposit: 10 Birr\n"
        "• Bonus money: Play only, cannot withdraw\n"
        "• Main balance: Can be withdrawn anytime\n\n"
        "<b>🎯 Winning:</b>\n"
        "• First player to complete a valid line wins\n"
        "• Prize is credited to your main balance\n"
        "• Invalid claims will be rejected\n\n"
        "Good luck! 🍀"
    )
    await message.answer(rules_text, reply_markup=main_menu_keyboard())


@router.message(F.text == "🆘 Support")
async def show_support(message: Message):
    """Show support information"""
    support_text = (
        "<b>🆘 SUPPORT</b>\n\n"
        "Need help? Contact us:\n\n"
        "📧 Email: support@bingobot.com\n"
        "💬 Telegram: @BingoSupport\n\n"
        "We're here to help! 😊"
    )
    await message.answer(support_text, reply_markup=main_menu_keyboard())


@router.message(F.text == "👥 My Invites")
async def my_invites(message: Message):
    """Show referral link and referral stats."""
    user = await sync_to_async(User.objects.filter(telegram_id=message.from_user.id).first)()
    if not user:
        await message.answer("❌ Please start the bot first with /start")
        return

    bot_username = await _resolve_bot_username(message)
    invite_link = f"https://t.me/{bot_username}?start=ref_{quote_plus(user.invite_code)}"
    share_text = (
        "🎯 Play Bingo and Win!\n\n"
        "Join the game using my invite link and start winning.\n\n"
        f"👇 Tap to join:\n{invite_link}\n\n"
        "You will also receive a welcome bonus!"
    )
    share_url = (
        f"https://t.me/share/url?url={quote_plus(invite_link)}"
        f"&text={quote_plus(share_text)}"
    )
    stats = await sync_to_async(get_user_referral_stats)(user)
    welcome_bonus = getattr(settings, "WELCOME_BONUS", 0)

    text = (
        "<b>📊 Referral Statistics</b>\n\n"
        f"🔗 Your Invite Link:\n{invite_link}\n\n"
        f"👥 Total Invited Users: {stats['total']}\n"
        f"✅ Qualified Referrals: {stats['qualified']}\n"
        f"⏳ Pending Referrals: {stats['pending']}\n"
        f"🎁 Total Bonus Earned: {stats['total_bonus']} credits\n\n"
        "<b>🎯 Play Bingo and Win!</b>\n\n"
        "Join the game using my invite link and start winning.\n\n"
        "👇 Tap to join:\n"
        f"<a href=\"{invite_link}\">{invite_link}</a>\n\n"
        "If Telegram opens the chat first, press the <b>START</b> button once.\n\n"
        f"You will also receive a welcome bonus of {welcome_bonus}!"
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📤 Forward Invite Link",
                    url=share_url,
                )
            ]
        ]
    )
    await message.answer(text, reply_markup=keyboard)
