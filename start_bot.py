"""
Quick start script for Bingo Bot
Run this after setting up your BOT_TOKEN in .env
"""
import os
import sys
from pathlib import Path

# Add project to path
BASE_DIR = Path(__file__).resolve().parent
sys.path.append(str(BASE_DIR))

# Check if .env exists
if not os.path.exists('.env'):
    print("❌ .env file not found!")
    print("Please create .env file and add your BOT_TOKEN")
    print("\nExample:")
    print("BOT_TOKEN=your_bot_token_here")
    sys.exit(1)

# Check if BOT_TOKEN is set
from dotenv import load_dotenv
load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
if not BOT_TOKEN or BOT_TOKEN == 'YOUR_BOT_TOKEN_HERE':
    print("❌ BOT_TOKEN not configured!")
    print("Please edit .env file and add your actual bot token")
    print("\nGet your token from @BotFather on Telegram")
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
