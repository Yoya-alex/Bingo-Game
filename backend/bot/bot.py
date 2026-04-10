import asyncio
import os
import socket
import sys
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramNetworkError
from aiogram.client.session.aiohttp import AiohttpSession

try:
    from aiogram.client.default import DefaultBotProperties
    def _make_bot(token, session=None):
        return Bot(
            token=token,
            session=session,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
except ImportError:
    def _make_bot(token, session=None):
        return Bot(token=token, session=session, parse_mode=ParseMode.HTML)

from bot.handlers import user_handlers, game_handlers, wallet_handlers, admin_handlers

BOT_TOKEN = os.getenv('BOT_TOKEN')
TELEGRAM_API_TIMEOUT = int(os.getenv('TELEGRAM_API_TIMEOUT', '60'))
TELEGRAM_RETRY_DELAY = int(os.getenv('TELEGRAM_RETRY_DELAY', '5'))

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN not found in environment variables")


async def main():
    # Use a longer HTTP timeout for unstable/slow VPS routes to Telegram API.
    session = AiohttpSession(timeout=TELEGRAM_API_TIMEOUT)
    # aiogram<3.8 does not expose connector kwargs on AiohttpSession.__init__,
    # so force IPv4 through connector init dict used when creating ClientSession.
    session._connector_init["family"] = socket.AF_INET
    bot = _make_bot(BOT_TOKEN, session=session)
    dp = Dispatcher()

    dp.include_router(user_handlers.router)
    dp.include_router(game_handlers.router)
    dp.include_router(wallet_handlers.router)
    dp.include_router(admin_handlers.router)

    print(
        f"Bot started successfully! timeout={TELEGRAM_API_TIMEOUT}s retry_delay={TELEGRAM_RETRY_DELAY}s",
        flush=True,
    )
    try:
        while True:
            try:
                await dp.start_polling(bot)
                break
            except TelegramNetworkError as exc:
                print(
                    f"[WARN] Telegram network error: {exc}. Retrying in {TELEGRAM_RETRY_DELAY}s...",
                    flush=True,
                )
                await asyncio.sleep(TELEGRAM_RETRY_DELAY)
    finally:
        await bot.session.close()


if __name__ == '__main__':
    # When run directly, setup Django first
    BASE_DIR = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(BASE_DIR))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bingo_project.settings')
    import django
    django.setup()
    asyncio.run(main())
