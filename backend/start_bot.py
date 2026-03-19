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
except KeyboardInterrupt:
    print("👋 Bot stopped", flush=True)
except Exception as e:
    print(f"❌ Bot crashed: {e}", flush=True)
    traceback.print_exc()
    sys.exit(1)
