# 🎮 Telegram Bingo Game Bot

A real-time multiplayer Bingo game system built on Telegram with wallet management, 400-card entry system, and automated game cycles.

## 📊 Project Status: 60% Complete

✅ **Working:** User registration, wallet system, card selection, win validation, admin panel  
🚧 **In Progress:** Game automation (countdown, number calling, broadcasting)

## 🚀 Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Get bot token from @BotFather on Telegram

# 3. Update .env file with your token
BOT_TOKEN=your_token_here

# 4. Run migrations
python manage.py migrate

# 5. Start bot
python start_bot.py
```

**📖 Read `START_HERE.md` for detailed instructions!**

## ✨ Features

### ✅ Implemented
- Automatic user registration with welcome bonus
- Dual wallet system (main + bonus balance)
- Deposit requests with photo proof
- Withdrawal requests with approval flow
- 400-card Bingo game system
- 5×5 grid generation (1-75 numbers)
- Win validation (horizontal, vertical, diagonal)
- Prize distribution
- Django admin panel

### 🚧 Coming Soon
- Countdown timer (25 seconds)
- Automatic game start
- Real-time number calling
- Broadcasting to all players
- Automatic game loop

## 🛠️ Tech Stack

- **Backend:** Django 4.2.7
- **Bot:** Aiogram 3.3.0
- **Database:** SQLite (PostgreSQL ready)
- **Cache:** Redis (for future features)
- **Language:** Python 3.9+

## 📚 Documentation

| File | Purpose |
|------|---------|
| **START_HERE.md** | 👈 Read this first! |
| **QUICK_START.md** | 5-minute setup guide |
| **TODO.md** | Task checklist |
| **PROJECT_STATUS.md** | Development roadmap |
| **SETUP_GUIDE.md** | Architecture details |
| **SYSTEM_FLOW.md** | Flow diagrams |
| **IMPLEMENTATION_SUMMARY.md** | Complete overview |

## 🎯 Next Steps

1. Read `START_HERE.md`
2. Get your bot running
3. Test current features
4. Implement game automation (see `TODO.md`)

## 📞 Support

Check the documentation files for help. All questions are answered there!

---

**Ready to build? Start with `START_HERE.md`! 🚀**
