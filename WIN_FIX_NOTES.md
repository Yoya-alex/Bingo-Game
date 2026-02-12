# Win Database Update Fix

## Problem
The database wasn't updating when users won the game because:

1. The `claim_bingo_api` function required the game to be in `'playing'` state
2. Games only transition from `'waiting'` to `'playing'` when the game engine is running
3. Without the game engine running, games stayed in `'waiting'` state forever
4. Win claims were rejected with "Game is not active" error

## Solution
Updated the win validation logic to:

1. Auto-transition games from `'waiting'` to `'playing'` when a BINGO is claimed
2. Allow wins to be claimed in both `'waiting'` and `'playing'` states
3. Only reject claims if the game is already `'finished'`

## Changes Made

### File: `game/views.py`
- Modified `claim_bingo_api()` function
- Added auto-transition logic before win validation
- Changed state check to allow both 'waiting' and 'playing' states
- Reordered operations to save card winner status correctly

### File: `bot/handlers/game_handlers.py`
- Implemented full BINGO claim handler (was placeholder)
- Added win validation logic
- Added auto-transition in `mark_winner_and_distribute_prize()`
- Added proper error handling and user feedback

## Testing
Run `python test_win_fix.py` to verify:
- ✅ Game state transitions correctly
- ✅ Winner is marked in database
- ✅ Prize is calculated correctly
- ✅ Wallet balance is updated
- ✅ Transaction is logged
- ✅ Card winner status is set

## How It Works Now

1. User clicks "BINGO" button
2. System checks if game is finished (reject if yes)
3. If game is still in 'waiting', auto-transition to 'playing'
4. Validate the BINGO pattern
5. If valid:
   - Mark game as finished
   - Set winner
   - Calculate and save prize
   - Mark card as winner
   - Credit wallet
   - Log transaction
6. Return success/failure to user

## Notes
- The game engine (`run_game_engine.py`) is still useful for automatic number calling
- But wins can now be validated even without the game engine running
- This makes testing and manual gameplay much easier
