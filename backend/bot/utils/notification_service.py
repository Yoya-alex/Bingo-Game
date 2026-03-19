"""Centralized admin and system notification helpers for Telegram."""

from typing import Iterable, Optional

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup
from django.conf import settings


async def _get_admin_chat_ids() -> Iterable[int]:
    """
    Return the list of admin chat IDs that should receive notifications.

    For now we reuse settings.ADMIN_IDS. Later this can be extended to support
    dedicated notification channels or per-admin preferences.
    """
    return getattr(settings, "ADMIN_IDS", [])


async def send_admin_notification(
    bot: Bot,
    text: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
) -> None:
    """
    Broadcast a notification to all configured admins.

    This helper is intentionally fire-and-forget: failures to deliver a
    notification must NOT block business logic.
    """
    admin_ids = await _get_admin_chat_ids()
    for chat_id in admin_ids:
        try:
            await bot.send_message(chat_id, text, reply_markup=reply_markup)
        except Exception:
            # Swallow send errors to keep financial operations safe.
            continue

