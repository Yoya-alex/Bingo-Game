# 🔄 System Flow Diagrams

## 1. User Registration Flow

```
User clicks /start
       ↓
Check if user exists in DB
       ↓
   ┌───┴───┐
   │       │
  YES     NO
   │       │
   │       └→ Create user record
   │          Create wallet
   │          Give 10 Birr bonus
   │          Log transaction
   │       ↓
   └───┬───┘
       ↓
Show welcome message
Show main menu
```

## 2. Deposit Flow

```
User clicks "➕ Deposit"
       ↓
Show payment instructions
       ↓
User clicks "Submit Proof"
       ↓
User sends photo
       ↓
Create Transaction (pending)
Create Deposit record
       ↓
Admin reviews in Django admin
       ↓
   ┌───┴───┐
   │       │
APPROVE  REJECT
   │       │
   │       └→ Mark as rejected
   │          Notify user
   │       ↓
   └→ Credit main balance
      Mark as approved
      Notify user
```

## 3. Withdrawal Flow

```
User clicks "➖ Withdraw"
       ↓
Show available balance
       ↓
User enters amount
       ↓
Check if sufficient balance
       ↓
   ┌───┴───┐
   │       │
  YES     NO
   │       │
   │       └→ Show error
   │       ↓
   └→ User enters payment method
      User enters account info
       ↓
Create Transaction (pending)
Create Withdrawal record
       ↓
Admin reviews in Django admin
       ↓
   ┌───┴───┐
   │       │
APPROVE  REJECT
   │       │
   │       └→ Refund balance
   │          Mark as rejected
   │          Notify user
   │       ↓
   └→ Process payment
      Mark as approved
      Notify user
```

## 4. Game Flow (Current Implementation)

```
User clicks "🎮 Play Bingo"
       ↓
Check balance >= 10 Birr
       ↓
   ┌───┴───┐
   │       │
  YES     NO
   │       │
   │       └→ Show "Insufficient Balance"
   │       ↓
   └→ Get or create active game
       ↓
   ┌───┴───┐
   │       │
WAITING  PLAYING
   │       │
   │       └→ Check if user has card
   │          ┌───┴───┐
   │          │       │
   │         YES     NO
   │          │       │
   │          │       └→ Show "Wait for next game"
   │          │       ↓
   │          └→ Show playing screen
   │       ↓
   └→ Show available cards
      User selects card
       ↓
Deduct 10 Birr from balance
Generate 5×5 Bingo grid
Create BingoCard record
       ↓
Show waiting screen with grid
```

## 5. Game Flow (Target Implementation)

```
Game Created (state: WAITING)
       ↓
Start 25-second countdown
Broadcast timer to all players
       ↓
Players join and select cards
       ↓
Countdown reaches 0
       ↓
Lock card selection
Change state to PLAYING
       ↓
Start calling numbers (every 3 seconds)
       ↓
┌─────────────────────┐
│  Number Called      │
│  Broadcast to all   │
│  Update all grids   │
└─────────────────────┘
       ↓
Player clicks "BINGO"
       ↓
Validate win pattern
       ↓
   ┌───┴───┐
   │       │
 VALID  INVALID
   │       │
   │       └→ Show "Invalid BINGO"
   │          Continue game
   │       ↓
   └→ Mark as winner
      Calculate prize
      Credit main balance
      Change state to FINISHED
       ↓
Announce winner to all players
       ↓
Wait 5 seconds
       ↓
Create new game (state: WAITING)
Start new countdown
```

## 6. Balance Deduction Priority

```
User needs to pay 10 Birr
       ↓
Check main_balance
       ↓
   ┌───┴───┐
   │       │
>= 10    < 10
   │       │
   │       └→ Deduct from main_balance
   │          Calculate remaining
   │          Deduct remaining from bonus_balance
   │       ↓
   └→ Deduct 10 from main_balance
       ↓
Save wallet
Log transaction
```

## 7. Win Validation Logic

```
User clicks "BINGO"
       ↓
Get user's grid
Get called numbers
       ↓
Check horizontal lines (5 rows)
       ↓
   ┌───┴───┐
   │       │
 FOUND  NOT FOUND
   │       │
   │       └→ Check vertical lines (5 columns)
   │          ┌───┴───┐
   │          │       │
   │        FOUND  NOT FOUND
   │          │       │
   │          │       └→ Check diagonal ↘
   │          │          ┌───┴───┐
   │          │          │       │
   │          │        FOUND  NOT FOUND
   │          │          │       │
   │          │          │       └→ Check diagonal ↙
   │          │          │          ┌───┴───┐
   │          │          │          │       │
   │          │          │        FOUND  NOT FOUND
   │          │          │          │       │
   │          │          │          │       └→ Return FALSE
   │          │          │          │       ↓
   │          │          │          └───────┘
   │          │          │       ↓
   │          │          └───────┘
   │          │       ↓
   │          └───────┘
   │       ↓
   └───────┘
       ↓
Return TRUE + pattern name
```

## 8. Database Relationships

```
User
 ├─→ Wallet (1:1)
 ├─→ Transactions (1:N)
 ├─→ BingoCards (1:N)
 └─→ Won Games (1:N)

Game
 ├─→ BingoCards (1:N)
 └─→ Winner (N:1 to User)

Transaction
 ├─→ User (N:1)
 ├─→ Deposit (1:1, optional)
 └─→ Withdrawal (1:1, optional)

BingoCard
 ├─→ Game (N:1)
 └─→ User (N:1)
```

## 9. State Machine (Game States)

```
     ┌─────────────┐
     │  NO_GAME    │
     └──────┬──────┘
            │ Create game
            ↓
     ┌─────────────┐
     │   WAITING   │ ←─────┐
     └──────┬──────┘       │
            │ Timer = 0    │
            ↓              │
     ┌─────────────┐       │
     │   PLAYING   │       │
     └──────┬──────┘       │
            │ Winner found │
            ↓              │
     ┌─────────────┐       │
     │  FINISHED   │       │
     └──────┬──────┘       │
            │ Create new   │
            └──────────────┘
```

## 10. Message Flow (Broadcasting)

```
Game Event Occurs
       ↓
   ┌───┴───────────────────┐
   │                       │
Countdown    Number Called    Winner
   │              │             │
   ↓              ↓             ↓
Get all      Get all       Get all
players      players       users
   │              │             │
   ↓              ↓             ↓
For each     For each      For each
player       player        user
   │              │             │
   ↓              ↓             ↓
Send         Send          Send
timer        number        winner
update       update        announcement
```

## 11. Admin Workflow

```
Admin logs into Django admin
       ↓
   ┌───┴───────────────────┐
   │                       │
Deposits              Withdrawals
   │                       │
   ↓                       ↓
View pending          View pending
transactions          transactions
   │                       │
   ↓                       ↓
Check proof           Check amount
   │                       │
   ↓                       ↓
Select transaction    Select transaction
   │                       │
   ↓                       ↓
Click "Approve"       Click "Approve"
or "Reject"           or "Reject"
   │                       │
   ↓                       ↓
Balance updated       Payment processed
User notified         User notified
```

## 12. Error Handling Flow

```
User Action
       ↓
Try to execute
       ↓
   ┌───┴───┐
   │       │
SUCCESS  ERROR
   │       │
   │       └→ Catch exception
   │          Log error
   │          ┌───┴───────────────┐
   │          │                   │
   │     User Error        System Error
   │          │                   │
   │          └→ Show friendly    └→ Show generic
   │             error message       error message
   │             (e.g., "Insufficient   (e.g., "Something
   │              balance")              went wrong")
   │          ↓                   ↓
   │          └───────┬───────────┘
   │                  │
   └──────────────────┘
       ↓
Continue operation
```

---

## 🎯 Key Takeaways

1. **User Flow** - Simple and intuitive
2. **Game Flow** - Needs automation (countdown, calling)
3. **Admin Flow** - Manual approval for now
4. **State Machine** - Clear game lifecycle
5. **Broadcasting** - Critical for multiplayer experience

## 🚧 What Needs Implementation

- ❌ Countdown timer broadcasting
- ❌ Automatic number calling
- ❌ Real-time grid updates
- ❌ Winner announcement broadcasting
- ❌ Automatic game loop

These are the **critical missing pieces** that will make the game fully functional!
