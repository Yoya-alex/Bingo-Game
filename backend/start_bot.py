"""
Start script for Bingo Bot - Render production
"""
import os
import sys
import traceback
from pathlib import Path

# Add project to path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

# Load .env file if it exists (local development only)
try:
    from dotenv import load_dotenv
    env_path = BASE_DIR / '.env'
    if env_path.exists():
        load_dotenv(env_path)
        print("Loaded .env file", flush=True)

    django_env = os.getenv('DJANGO_ENV', '').strip().lower()
    dev_env_path = BASE_DIR / '.env.development'
    if django_env in {'dev', 'development', 'local'} and dev_env_path.exists():
        load_dotenv(dev_env_path, override=True)
        print("Loaded .env.development file", flush=True)
except Exception as e:
    print(f"dotenv load skipped: {e}", flush=True)

# Check BOT_TOKEN early
BOT_TOKEN = os.getenv('BOT_TOKEN', '').strip()
if not BOT_TOKEN or BOT_TOKEN == 'YOUR_BOT_TOKEN_HERE':
    print("❌ BOT_TOKEN not set in environment variables!", flush=True)
    sys.exit(1)

print(f"✅ BOT_TOKEN found (starts with: {BOT_TOKEN[:8]}...)", flush=True)

# Setup Django before any imports
try:
    print("Setting up Django...", flush=True)
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bingo_project.settings')
    import django
    django.setup()
    print("✅ Django setup OK", flush=True)
except Exception as e:
    print(f"❌ Django setup failed: {e}", flush=True)
    traceback.print_exc()
    sys.exit(1)

# Import bot
try:
    print("Importing bot module...", flush=True)
    from bot.bot import main
    from aiogram.exceptions import TelegramUnauthorizedError
    print("✅ Bot module imported OK", flush=True)
except Exception as e:
    print(f"❌ Bot import failed: {e}", flush=True)
    traceback.print_exc()
    sys.exit(1)

# Run bot
import asyncio
print("🚀 Starting Bingo Bot...", flush=True)
try:
    asyncio.run(main())
except TelegramUnauthorizedError:
    print("❌ Telegram rejected BOT_TOKEN (Unauthorized).", flush=True)
    print("   Action: Create a new token in @BotFather and update backend/.env", flush=True)
    sys.exit(1)
except KeyboardInterrupt:
    print("👋 Bot stopped", flush=True)
except Exception as e:
    print(f"❌ Bot crashed: {e}", flush=True)
    traceback.print_exc()
    sys.exit(1)
