from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message
from django.conf import settings
from asgiref.sync import sync_to_async

from users.models import User
from wallet.models import Wallet, Transaction
from bot.keyboards import main_menu_keyboard
from bot.utils.db_helpers import get_or_create_user, create_wallet, save_model

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message):
    """Handle /start command - Auto registration"""
    telegram_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name or "User"
    
    # Check if user exists
    user, created = await get_or_create_user(telegram_id, username, first_name)
    
    if created:
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
        
        welcome_text = (
            f"🎉 <b>Welcome to Bingo Bot, {first_name}!</b>\n\n"
            f"✅ Registration successful!\n"
            f"🎁 You received {settings.WELCOME_BONUS} Birr welcome bonus!\n\n"
            f"💡 Use your bonus to play your first Bingo game.\n"
            f"Note: Bonus money can only be used for playing, not for withdrawal.\n\n"
            f"Ready to play? Click 🎮 Play Bingo!"
        )
    else:
        welcome_text = (
            f"👋 <b>Welcome back, {first_name}!</b>\n\n"
            f"Ready to play Bingo? Choose an option below:"
        )
    
    await message.answer(welcome_text, reply_markup=main_menu_keyboard())


@router.message(F.text == "📜 Rules")
async def show_rules(message: Message):
    """Show game rules"""
    rules_text = (
        "<b>📜 BINGO GAME RULES</b>\n\n"
        "<b>How to Play:</b>\n"
        "1️⃣ Select a card (1-400) from the waiting screen\n"
        "2️⃣ Each card costs 10 Birr\n"
        "3️⃣ Wait for the game to start (25 seconds countdown)\n"
        "4️⃣ Numbers will be called randomly (1-75)\n"
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
