"""
Quick start script for Bingo Bot
Run this after setting up your BOT_TOKEN in .env or environment variables
"""
import os
import sys
from pathlib import Path

# Add project to path
BASE_DIR = Path(__file__).resolve().parent
sys.path.append(str(BASE_DIR))

# Load .env file if it exists (local development)
from dotenv import load_dotenv
env_path = BASE_DIR / '.env'
if env_path.exists():
    load_dotenv(env_path)

# Check if BOT_TOKEN is set
BOT_TOKEN = os.getenv('BOT_TOKEN')
if not BOT_TOKEN or BOT_TOKEN == 'YOUR_BOT_TOKEN_HERE':
    print("❌ BOT_TOKEN not configured!")
    print("Please set BOT_TOKEN in your environment variables or .env file")
    sys.exit(1)

print("✅ Configuration OK")
print("🚀 Starting Bingo Bot...")
print("\nPress Ctrl+C to stop\n")

# Start bot
from bot.bot import main
import asyncio

try:
    asyncio.run(main())
except KeyboardInterrupt:
    print("\n\n👋 Bot stopped")
