import asyncio
import os
import sys
import django
from pathlib import Path

# Setup Django
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bingo_project.settings')
django.setup()

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties   # pyright: ignore[reportMissingImports]
from aiogram.enums import ParseMode
from dotenv import load_dotenv

from bot.handlers import user_handlers, game_handlers, wallet_handlers, admin_handlers

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN not found in environment variables")


async def main():
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    
    # Register routers
    dp.include_router(user_handlers.router)
    dp.include_router(game_handlers.router)
    dp.include_router(wallet_handlers.router)
    dp.include_router(admin_handlers.router)
    
    print("Bot started successfully!")
    await dp.start_polling(bot)


if __name__ == '__main__':
    asyncio.run(main())
