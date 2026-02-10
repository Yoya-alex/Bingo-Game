# Game Engine Guide

## Overview
The game engine automatically manages the game lifecycle:
- **Auto-starts games** when countdown reaches 0 (25 seconds after creation)
- **Calls numbers** every 3 seconds during gameplay
- **Validates BINGO** claims from players
- **Awards prizes** to winners

## How It Works

### 1. Game States
```
NO_GAME → WAITING (25s) → PLAYING → FINISHED → (new WAITING)
```

### 2. Waiting State (Lobby)
- Game created with state='waiting'
- Players select cards (1-80)
- Countdown starts at 25 seconds
- When countdown = 0, game auto-starts

### 3. Playing State
- Numbers called every 3 seconds (1-75)
- Players mark their cards
- Players can click BINGO to claim win
- System validates winning patterns

### 4. Finished State
- Winner announced
- Prize credited to wallet
- New game created automatically

## Running the System

### Option 1: All-in-One (Recommended)
```bash
python start_game_system.py
```
This starts:
- Django web server (port 8000)
- Game engine (background)
- Telegram bot

### Option 2: Manual (Separate Terminals)

**Terminal 1 - Django:**
```bash
python manage.py runserver
```

**Terminal 2 - Game Engine:**
```bash
python manage.py run_game_engine
```

**Terminal 3 - Bot:**
```bash
python start_bot.py
```

## Testing

### Test Game Flow
```bash
python test_game_flow.py
```

### Manual Testing
1. Open: http://localhost:8000/game/lobby/5217880016/
2. Select a card
3. Wait for countdown to reach 0
4. Game should auto-start
5. Numbers will be called every 3 seconds
6. Click BINGO when you have a winning pattern

## Game Engine Features

### Auto-Start Games
- Monitors games in 'waiting' state
- Checks if 25 seconds elapsed since creation
- Automatically changes state to 'playing'

### Number Calling
- Calls numbers every 3 seconds
- Random selection from 1-75
- No duplicates
- Stops at 75 numbers

### BINGO Validation
- Checks horizontal lines (5 rows)
- Checks vertical lines (5 columns)
- Checks diagonals (2 diagonals)
- Center cell is FREE (auto-marked)

### Prize Distribution
- Prize = Total Players × Card Price (10 Birr)
- Automatically credited to winner's wallet
- Transaction logged

## API Endpoints

### Get Game Status
```
GET /game/api/game-status/<game_id>/
```
Returns:
- game_id
- state
- countdown (seconds remaining)
- total_players
- called_numbers
- winner
- prize_amount

### Select Card
```
POST /game/api/select-card/
Body: {telegram_id, card_number}
```

### Claim BINGO
```
POST /game/api/claim-bingo/
Body: {telegram_id, game_id}
```

## Troubleshooting

### Game Not Starting
- Check if game engine is running
- Verify game age: `python test_game_flow.py`
- Check Django logs

### Numbers Not Being Called
- Ensure game state is 'playing'
- Check game engine output
- Verify started_at timestamp

### BINGO Not Validating
- Check if all numbers in pattern are called
- Verify grid generation
- Check game state

## Configuration

### Card Price
Edit `bingo_project/settings.py`:
```python
CARD_PRICE = 10  # Birr
```

### Countdown Duration
Edit `game/management/commands/run_game_engine.py`:
```python
if time_elapsed >= 25:  # Change 25 to desired seconds
```

### Number Call Interval
Edit `game/management/commands/run_game_engine.py`:
```python
expected_calls = int(time_since_start / 3)  # Change 3 to desired seconds
```

## Architecture

```
┌─────────────────┐
│  Telegram Bot   │ ← Users interact
└────────┬────────┘
         │
         ↓
┌─────────────────┐
│  Django Server  │ ← Web interface
└────────┬────────┘
         │
         ↓
┌─────────────────┐
│  Game Engine    │ ← Auto-manages games
└────────┬────────┘
         │
         ↓
┌─────────────────┐
│    Database     │ ← SQLite
└─────────────────┘
```

## Next Steps

1. ✅ Auto-start games (DONE)
2. ✅ Auto-call numbers (DONE)
3. ✅ BINGO validation (DONE)
4. ✅ Prize distribution (DONE)
5. 🔄 Broadcast to all players (Future)
6. 🔄 Multiple game rooms (Future)
7. 🔄 Jackpot mode (Future)
