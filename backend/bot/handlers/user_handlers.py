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
from bot.utils.i18n import (
    is_menu_text,
    language_button_rows,
    language_name,
    normalize_language,
    tr,
)
from game.business_rules import get_countdown_seconds

router = Router()


def _language_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=language_button_rows())


async def _send_welcome_by_language(message: Message, user: User, created: bool, referral_text: str = ""):
    language = normalize_language(user.language)
    first_name = user.first_name or "User"
    if created:
        text = tr(
            language,
            'start_first_time',
            first_name=first_name,
            welcome_bonus=settings.WELCOME_BONUS,
            referral_text=referral_text,
        )
    else:
        text = tr(language, 'start_back', first_name=first_name)

    if await is_admin(user.telegram_id):
        await message.answer(text, reply_markup=admin_main_menu_keyboard(language))
    else:
        await message.answer(text, reply_markup=main_menu_keyboard(language))


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
    
    referral_text = ""
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

        if referral and referral.status == 'PENDING':
            referral_text = (
                "\n\n🎯 Referral tracked successfully!\n"
                "Your inviter will receive bonus when you complete your first qualifying deposit."
            )

    # Force language selection for first-time users and users without language.
    if not user.language:
        await message.answer(tr('en', 'lang_prompt'), reply_markup=_language_keyboard())
        return

    # If user is an admin, show admin menu by default (can switch back to user menu).
    try:
        await _send_welcome_by_language(message, user, created=created, referral_text=referral_text)
    except TelegramForbiddenError:
        # User has blocked the bot; avoid crashing the update handler.
        return


@router.callback_query(F.data.startswith("set_lang:"))
async def set_language(callback):
    language = normalize_language(callback.data.split(":", 1)[1])
    user = await sync_to_async(User.objects.filter(telegram_id=callback.from_user.id).first)()
    if not user:
        await callback.answer(tr('en', 'please_start'), show_alert=True)
        return

    user.language = language
    await save_model(user)

    await callback.answer(
        tr(language, 'lang_saved', language_name=language_name(language, language)),
        show_alert=False,
    )
    await callback.message.answer(
        tr(language, 'lang_saved', language_name=language_name(language, language)),
    )
    await _send_welcome_by_language(callback.message, user, created=False)


@router.message(lambda message: is_menu_text(message.text, 'menu_rules'))
async def show_rules(message: Message):
    """Show game rules"""
    countdown_seconds = await sync_to_async(get_countdown_seconds)()
    user = await sync_to_async(User.objects.filter(telegram_id=message.from_user.id).first)()
    language = normalize_language(getattr(user, 'language', None))
    rules_text = tr(
        language,
        'rules_text',
        countdown_seconds=countdown_seconds,
        bingo_max=settings.BINGO_NUMBER_MAX,
    )
    await message.answer(rules_text, reply_markup=main_menu_keyboard(language))


@router.message(lambda message: is_menu_text(message.text, 'menu_support'))
async def show_support(message: Message):
    """Show support information"""
    user = await sync_to_async(User.objects.filter(telegram_id=message.from_user.id).first)()
    language = normalize_language(getattr(user, 'language', None))
    support_text = tr(language, 'support_text')
    await message.answer(support_text, reply_markup=main_menu_keyboard(language))


@router.message(lambda message: is_menu_text(message.text, 'menu_invites'))
async def my_invites(message: Message):
    """Show referral link and referral stats."""
    user = await sync_to_async(User.objects.filter(telegram_id=message.from_user.id).first)()
    if not user:
        await message.answer(tr('en', 'please_start'))
        return

    language = normalize_language(user.language)

    bot_username = await _resolve_bot_username(message)
    invite_link = f"https://t.me/{bot_username}?start=ref_{quote_plus(user.invite_code)}"
    share_text = tr(language, 'invite_share_text', invite_link=invite_link)
    share_url = (
        f"https://t.me/share/url?url={quote_plus(invite_link)}"
        f"&text={quote_plus(share_text)}"
    )
    stats = await sync_to_async(get_user_referral_stats)(user)
    welcome_bonus = getattr(settings, "WELCOME_BONUS", 0)

    text = tr(
        language,
        'invite_card_text',
        invite_link=invite_link,
        total=stats['total'],
        qualified=stats['qualified'],
        pending=stats['pending'],
        total_bonus=stats['total_bonus'],
        welcome_bonus=welcome_bonus,
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=tr(language, 'invite_forward_btn'),
                    url=share_url,
                )
            ]
        ]
    )
    await message.answer(text, reply_markup=keyboard)


@router.message(lambda message: is_menu_text(message.text, 'menu_language'))
async def language_menu(message: Message):
    user = await sync_to_async(User.objects.filter(telegram_id=message.from_user.id).first)()
    language = normalize_language(getattr(user, 'language', None))
    await message.answer(tr(language, 'lang_prompt'), reply_markup=_language_keyboard())
