import asyncio
import os
import sys
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode

try:
    from aiogram.client.default import DefaultBotProperties
    def _make_bot(token):
        return Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
except ImportError:
    def _make_bot(token):
        return Bot(token=token, parse_mode=ParseMode.HTML)

from bot.handlers import user_handlers, game_handlers, wallet_handlers, admin_handlers

BOT_TOKEN = os.getenv('BOT_TOKEN')

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN not found in environment variables")


async def main():
    bot = _make_bot(BOT_TOKEN)
    dp = Dispatcher()

    dp.include_router(user_handlers.router)
    dp.include_router(game_handlers.router)
    dp.include_router(wallet_handlers.router)
    dp.include_router(admin_handlers.router)

    print("Bot started successfully!", flush=True)
    await dp.start_polling(bot)


if __name__ == '__main__':
    # When run directly, setup Django first
    BASE_DIR = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(BASE_DIR))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bingo_project.settings')
    import django
    django.setup()
    asyncio.run(main())
