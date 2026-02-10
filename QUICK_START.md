# 🚀 Quick Start Guide

## Get Your Bot Running in 5 Minutes

### Step 1: Get Your Bot Token (2 minutes)

1. Open Telegram
2. Search for `@BotFather`
3. Send `/newbot`
4. Choose a name: `My Bingo Bot`
5. Choose a username: `my_bingo_bot` (must end with 'bot')
6. Copy the token (looks like: `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`)

### Step 2: Configure the Bot (1 minute)

1. Open `.env` file in this project
2. Replace `YOUR_BOT_TOKEN_HERE` with your actual token:
   ```
   BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
   ```
3. Save the file

### Step 3: Start the Bot (2 minutes)

```bash
# Install dependencies (first time only)
pip install -r requirements.txt

# Start the bot
python start_bot.py
```

You should see:
```
✅ Configuration OK
🚀 Starting Bingo Bot...
Bot started successfully!
```

### Step 4: Test It!

1. Open Telegram
2. Search for your bot username
3. Click Start
4. You should receive a welcome message with 10 Birr bonus!

## 🎮 What You Can Test Now

### User Commands
- `/start` - Register and get welcome bonus
- `💰 Balance` - Check your balance
- `📜 Rules` - Read game rules
- `🆘 Support` - Get support info
- `🎮 Play Bingo` - Join a game (select a card)

### Admin Panel
```bash
# Create admin user
python manage.py createsuperuser

# Start Django server
python manage.py runserver
```

Visit: http://localhost:8000/admin

## ⚠️ Known Limitations

The bot is **60% complete**. What works:
- ✅ User registration
- ✅ Balance management
- ✅ Deposit requests
- ✅ Withdrawal requests
- ✅ Card selection
- ✅ Bingo grid generation

What doesn't work yet:
- ❌ Countdown timer
- ❌ Auto game start
- ❌ Number calling
- ❌ Real-time updates
- ❌ Game loop

## 🔧 Troubleshooting

### "BOT_TOKEN not configured"
- Make sure you edited `.env` file
- Make sure you saved the file
- Make sure the token has no spaces

### "Module not found"
```bash
pip install -r requirements.txt
```

### "Database error"
```bash
python manage.py migrate
```

### Bot doesn't respond
- Check if bot is running
- Check if token is correct
- Try `/start` command

## 📚 Next Steps

Once you've tested the basic features, check out:
- `PROJECT_STATUS.md` - See what's complete and what's missing
- `SETUP_GUIDE.md` - Detailed setup and architecture
- `README.md` - Project overview

## 🎯 Ready to Continue Development?

The next critical feature to implement is **game automation**:
1. Countdown timer (25 seconds)
2. Auto game start
3. Number calling system
4. Broadcasting to all players

See `PROJECT_STATUS.md` for detailed next steps.

## 💬 Questions?

Check the documentation files:
- `SETUP_GUIDE.md` - Technical details
- `PROJECT_STATUS.md` - Development roadmap
- `README.md` - Project overview

Happy coding! 🎉
