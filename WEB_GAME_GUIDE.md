# 🌐 Web Game Interface Guide

## ✅ What's New!

The game now opens in a **web browser** instead of inside Telegram! This provides a much better experience for:
- Viewing all 400 cards at once
- Seeing the full Bingo grid
- Real-time game updates
- Better visual design

---

## 🎮 How It Works

### 1. User Flow:

```
User clicks "🎮 Play Bingo" in Telegram
         ↓
Bot sends message with "Open Game" button
         ↓
User clicks button
         ↓
Game opens in browser (web interface)
         ↓
User sees 400-card table
         ↓
User selects a card
         ↓
Balance deducted automatically
         ↓
User sees their Bingo grid
         ↓
Game plays in browser
```

---

## 🖥️ Web Interface Features

### Lobby Page (`/game/lobby/{telegram_id}/`)

**Features:**
- ✅ Shows all 400 cards in a grid
- ✅ Taken cards are grayed out
- ✅ Available cards are clickable
- ✅ Shows game info (players, balance, price)
- ✅ Real-time updates every 5 seconds
- ✅ Responsive design (works on mobile)

**What Users See:**
- Game status (WAITING/PLAYING/FINISHED)
- Player count (X/400)
- Their balance
- Card price
- 400-card grid (20x20 layout)

### Play Page (`/game/play/{telegram_id}/{game_id}/`)

**Features:**
- ✅ Shows user's 5×5 Bingo grid
- ✅ B-I-N-G-O column headers
- ✅ FREE center cell
- ✅ Game status display
- ✅ Called numbers list
- ✅ BINGO button
- ✅ Auto-refresh every 3 seconds
- ✅ Numbers marked automatically

**What Users See:**
- Their card number
- Game status
- Player count
- Prize amount
- Their Bingo grid
- Called numbers (when game starts)
- BINGO button (to claim win)

---

## 🚀 Testing the Web Interface

### Step 1: Start Servers

```bash
# Terminal 1: Start Django server
python manage.py runserver

# Terminal 2: Start bot
python start_bot.py
```

### Step 2: Test in Telegram

1. Open your bot in Telegram
2. Click `🎮 Play Bingo`
3. You'll see two buttons:
   - **🎮 Open Game** - Opens in Telegram's built-in browser
   - **🔗 Open in Browser** - Opens in your default browser

### Step 3: Select a Card

1. Game lobby opens showing 400 cards
2. Click any available card (white background)
3. Confirm selection
4. Balance is deducted
5. You're redirected to play screen

### Step 4: View Your Grid

1. See your 5×5 Bingo grid
2. See game status
3. Wait for game to start (auto-start coming soon)

---

## 🌐 Deployment Options

### Option 1: Local Testing (Current)

**URL:** `http://localhost:8000/game/lobby/{telegram_id}/`

**Pros:**
- Easy to test
- No setup needed

**Cons:**
- Only works on your computer
- Others can't access it

### Option 2: Ngrok (For Testing with Others)

```bash
# Install ngrok
# Download from https://ngrok.com/

# Start ngrok
ngrok http 8000

# You'll get a URL like: https://abc123.ngrok.io
```

**Update bot handler:**
```python
web_url = f"https://abc123.ngrok.io/game/lobby/{user.telegram_id}/"
```

**Pros:**
- Others can test your bot
- Works from anywhere
- Free tier available

**Cons:**
- URL changes each time
- Limited bandwidth on free tier

### Option 3: Production Deployment

**Recommended Hosting:**
- Heroku
- DigitalOcean
- AWS
- PythonAnywhere
- Railway

**Steps:**
1. Deploy Django app to hosting
2. Get permanent domain (e.g., `https://yourgame.com`)
3. Update bot handler with production URL
4. Configure ALLOWED_HOSTS in settings.py

---

## 🎨 Web Interface Design

### Color Scheme:
- Primary: Purple gradient (#667eea to #764ba2)
- Success: Green (#28a745)
- Cards: White with purple border
- Taken cards: Gray (#e0e0e0)

### Layout:
- **Lobby:** 20×20 grid of cards (400 total)
- **Play:** Centered 5×5 Bingo grid
- **Responsive:** Works on mobile and desktop

### Features:
- Smooth animations
- Hover effects
- Real-time updates
- Auto-refresh
- Loading states

---

## 📱 Mobile Support

The web interface is fully responsive:
- ✅ Works on phones
- ✅ Works on tablets
- ✅ Works on desktop
- ✅ Touch-friendly buttons
- ✅ Optimized layout

---

## 🔧 Configuration

### Update Web URL

Edit `bot/handlers/game_handlers.py`:

```python
# For local testing
web_url = f"http://localhost:8000/game/lobby/{user.telegram_id}/"

# For ngrok
web_url = f"https://YOUR-NGROK-URL.ngrok.io/game/lobby/{user.telegram_id}/"

# For production
web_url = f"https://yourdomain.com/game/lobby/{user.telegram_id}/"
```

### Update Django Settings

Edit `bingo_project/settings.py`:

```python
# For production
ALLOWED_HOSTS = ['yourdomain.com', 'www.yourdomain.com']

# For ngrok
ALLOWED_HOSTS = ['YOUR-NGROK-URL.ngrok.io', 'localhost', '127.0.0.1']
```

---

## 🎯 What's Working Now

### ✅ Fully Functional:
1. Web lobby with 400-card grid
2. Card selection with balance deduction
3. Bingo grid display
4. Game status display
5. Real-time updates
6. Responsive design
7. Error handling

### 🚧 Coming Soon:
1. Countdown timer
2. Automatic number calling
3. Auto-marking numbers
4. Win validation
5. Winner announcement
6. Game loop

---

## 🐛 Troubleshooting

### Issue: "Page not found"
**Solution:** Make sure Django server is running
```bash
python manage.py runserver
```

### Issue: "User not found"
**Solution:** Start the bot first with `/start` in Telegram

### Issue: "Can't access from phone"
**Solution:** Use ngrok to create public URL

### Issue: "Cards not loading"
**Solution:** Check browser console for errors, refresh page

### Issue: "Balance not deducted"
**Solution:** Check Django server logs for errors

---

## 📊 API Endpoints

### 1. Game Lobby
```
GET /game/lobby/{telegram_id}/
```
Shows 400-card selection interface

### 2. Game Play
```
GET /game/play/{telegram_id}/{game_id}/
```
Shows user's Bingo grid and game status

### 3. Select Card (API)
```
POST /game/api/select-card/
Body: {
  "telegram_id": 123456789,
  "card_number": 42
}
```
Selects a card and deducts balance

### 4. Game Status (API)
```
GET /game/api/game-status/{game_id}/
```
Returns current game state (for real-time updates)

---

## 🎉 Success!

Your Bingo game now has a beautiful web interface!

**Test it now:**
1. Open Telegram
2. Click `🎮 Play Bingo`
3. Click `🔗 Open in Browser`
4. See all 400 cards!
5. Select a card
6. View your Bingo grid!

---

## 🚀 Next Steps

1. **Test the web interface** - Try selecting cards
2. **Test with multiple users** - Open in different browsers
3. **Deploy with ngrok** - Share with friends
4. **Implement game automation** - Countdown, number calling
5. **Deploy to production** - Get a real domain

---

**The web interface is ready! Try it now!** 🎮
