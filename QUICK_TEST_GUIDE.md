# Quick Test Guide - Ethio Bingo

## Current System Status ✅

All systems are running:
- ✅ Django Server (Process 17) - http://localhost:8000
- ✅ Telegram Bot (Process 13)
- ✅ Game Engine (Process 18) - Auto-starting games & calling numbers

## Test the Game Flow

### Step 1: Open Lobby
Open in your browser:
```
http://localhost:8000/game/lobby/5217880016/
```

You should see:
- Purple gradient background
- Top bar with: Countdown | Wallet | Stake | Game N°
- 80 cards in 8-column grid
- Orange cards = taken, White cards = available

### Step 2: Select a Card
1. Click any white (available) card
2. Confirm the selection
3. You'll be redirected to the play screen

### Step 3: Wait for Game Start
- The lobby shows a countdown (25 seconds)
- When countdown reaches 0, game auto-starts
- You'll be redirected to the play screen automatically

### Step 4: Play the Game
On the play screen you'll see:
- Your 5×5 Bingo grid (center is FREE)
- Game status (WAITING → PLAYING → FINISHED)
- Called numbers (updated every 3 seconds)
- BINGO button (click when you have a winning pattern)

### Step 5: Win!
- Numbers are called every 3 seconds
- Your grid auto-marks called numbers
- When you have a line (horizontal, vertical, or diagonal), click BINGO
- System validates and awards prize if valid

## Winning Patterns

Valid BINGO patterns:
- ✅ Any horizontal row (5 in a row)
- ✅ Any vertical column (5 in a column)
- ✅ Diagonal top-left to bottom-right
- ✅ Diagonal top-right to bottom-left

Remember: Center cell is FREE (automatically marked)

## Check Game Status

Run this anytime to see current game state:
```bash
python test_game_flow.py
```

## Browser Cache Issue Fix

If you still see the old page:
1. Press Ctrl + Shift + Delete
2. Clear "Cached images and files"
3. Close browser completely
4. Reopen and try again

Or try:
- Different browser (Firefox, Edge, Chrome)
- Incognito/Private mode
- Add `?v=2` to URL: `http://localhost:8000/game/lobby/5217880016/?v=2`

## Troubleshooting

### Countdown not syncing?
- Check if game engine is running: `python test_game_flow.py`
- Restart game engine if needed

### Numbers not being called?
- Game must be in 'playing' state
- Check game engine output
- Verify at least one player has selected a card

### BINGO not validating?
- Make sure all numbers in your pattern are called
- Check that game is still in 'playing' state
- Try refreshing the page

## Admin Panel

Access admin at: http://localhost:8000/admin/
- Username: `admin`
- Password: `admin123`

You can:
- View all games
- See player cards
- Check transactions
- Manually adjust balances

## Test User Info

- Telegram ID: `5217880016`
- Name: Yoni
- Lobby URL: http://localhost:8000/game/lobby/5217880016/

## Next Game

After a game finishes:
- Winner is announced
- Prize is credited automatically
- New game is created
- Countdown starts again (25 seconds)
- Players can select new cards

## Stop All Services

To stop everything:
1. Press Ctrl+C in each terminal
2. Or use the process manager to stop processes 13, 17, 18

## Restart Everything

```bash
# Stop current processes first, then:
python start_game_system.py
```

This starts all three services in one command.
