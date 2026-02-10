# 🧪 Testing Guide - What Works Now

## ✅ Current Features (Ready to Test!)

### 1. User Registration
**Test:** Send `/start` to the bot

**Expected Result:**
- Welcome message appears
- 10 Birr bonus credited
- Main menu keyboard shows

**Status:** ✅ Working

---

### 2. Balance Check
**Test:** Click `💰 Balance` button

**Expected Result:**
- Shows Main Balance: 0 Birr
- Shows Bonus Balance: 10 Birr
- Shows Total Balance: 10 Birr

**Status:** ✅ Working

---

### 3. Game Rules
**Test:** Click `📜 Rules` button

**Expected Result:**
- Shows complete game rules
- Explains how to play
- Explains wallet rules
- Explains winning conditions

**Status:** ✅ Working

---

### 4. Support Info
**Test:** Click `🆘 Support` button

**Expected Result:**
- Shows support contact information

**Status:** ✅ Working

---

### 5. Deposit Request
**Test:** 
1. Click `➕ Deposit`
2. Click "Submit Deposit Proof"
3. Send a photo

**Expected Result:**
- Shows bank account details
- Accepts photo upload
- Creates pending transaction
- Shows transaction ID

**Status:** ✅ Working

---

### 6. Withdrawal Request
**Test:**
1. Click `➖ Withdraw`
2. Click "Request Withdrawal"
3. Enter amount (e.g., 5)
4. Enter payment method (e.g., Bank Transfer)
5. Enter account number

**Expected Result:**
- Shows available balance
- Validates amount
- Collects payment details
- Creates pending withdrawal
- Shows transaction ID

**Status:** ✅ Working

---

### 7. Play Bingo - Card Selection
**Test:**
1. Click `🎮 Play Bingo`
2. Click a card number (1-40)

**Expected Result:**
- Shows game info
- Shows available cards
- Deducts 10 Birr from balance
- Shows your Bingo grid (5×5)
- Shows card number
- Shows player count

**Status:** ✅ Working

---

## 🎮 Game Flow Test

### Complete Game Test Scenario:

1. **Start Bot**
   ```
   /start
   ```
   ✅ Get 10 Birr bonus

2. **Check Balance**
   ```
   Click: 💰 Balance
   ```
   ✅ See 10 Birr bonus balance

3. **Join Game**
   ```
   Click: 🎮 Play Bingo
   ```
   ✅ See game lobby

4. **Select Card**
   ```
   Click: Any number (1-40)
   ```
   ✅ Balance deducted (10 Birr)
   ✅ See your Bingo grid
   ✅ Card number assigned

5. **View Grid**
   - ✅ 5×5 grid displayed
   - ✅ Numbers in correct ranges:
     - B column: 1-15
     - I column: 16-30
     - N column: 31-45
     - G column: 46-60
     - O column: 61-75
   - ✅ Center cell shows 🆓 (FREE)

---

## 🚧 Features Not Yet Working

### ❌ Countdown Timer
- Games don't start automatically after 25 seconds
- No timer display

### ❌ Number Calling
- Numbers aren't called during game
- No real-time updates

### ❌ Auto Marking
- Numbers aren't marked automatically
- Players can't mark numbers manually

### ❌ Win Detection
- BINGO button doesn't validate wins yet
- No winner announcement

### ❌ Game Loop
- Games don't cycle automatically
- No automatic new game creation

---

## 🎯 Test with Multiple Users

To fully test the multiplayer aspect:

1. **User 1:** Start bot, join game, select card #1
2. **User 2:** Start bot, join same game, select card #2
3. **User 3:** Start bot, join same game, select card #3

**Expected:**
- All users see same game ID
- Each user gets unique card
- Player count increases
- Each user sees their own grid

---

## 🐛 Known Issues

### Issue 1: Balance Shows 0 After Card Selection
**Status:** This is correct behavior
- Bonus balance was used to buy card
- Check balance again to confirm

### Issue 2: Game Doesn't Start
**Status:** Expected - auto-start not implemented yet
- Games stay in "WAITING" state
- Manual start needed (admin feature coming)

### Issue 3: Can't Play Multiple Rounds
**Status:** Expected - game loop not implemented
- Only one game at a time
- Need to manually create new game in admin

---

## 📊 Admin Panel Testing

### Setup Admin:
```bash
python manage.py createsuperuser
python manage.py runserver
```

Visit: http://localhost:8000/admin

### Test Admin Features:

1. **View Users**
   - See all registered users
   - Check telegram IDs
   - View registration dates

2. **View Wallets**
   - See all user balances
   - Check main vs bonus balance

3. **Approve Deposits**
   - Find pending deposits
   - Select transaction
   - Click "Approve selected transactions"
   - Balance updates automatically

4. **Approve Withdrawals**
   - Find pending withdrawals
   - Select transaction
   - Click "Approve selected transactions"
   - Process payment manually

5. **View Games**
   - See all games
   - Check player counts
   - View game states

6. **View Bingo Cards**
   - See all cards
   - Check which users have which cards
   - View card numbers

---

## ✅ Success Criteria

Your bot is working correctly if:

- [x] Users can register and get bonus
- [x] Users can check balance
- [x] Users can submit deposits
- [x] Users can request withdrawals
- [x] Users can select bingo cards
- [x] Balance is deducted correctly
- [x] Bingo grids are generated
- [x] Admin can approve transactions
- [x] Multiple users can join same game

---

## 🚀 Next Development Steps

After testing current features, implement:

1. **Countdown Timer** (2-3 hours)
   - 25-second countdown
   - Broadcast to all players
   - Auto-start game

2. **Number Calling** (2-3 hours)
   - Call numbers every 3 seconds
   - Broadcast to all players
   - Update grids

3. **Win Detection** (1-2 hours)
   - Validate BINGO claims
   - Announce winner
   - Distribute prize

4. **Game Loop** (1 hour)
   - Auto-create new game
   - Reset countdown
   - Continue cycle

---

## 💡 Testing Tips

1. **Use Multiple Accounts**
   - Test with 2-3 Telegram accounts
   - Verify multiplayer features

2. **Check Database**
   - Use Django admin
   - Verify data is saved correctly

3. **Monitor Bot Logs**
   - Watch console output
   - Check for errors

4. **Test Edge Cases**
   - Try with 0 balance
   - Try selecting same card twice
   - Try joining full game

5. **Test Admin Actions**
   - Approve/reject deposits
   - Approve/reject withdrawals
   - Check balance updates

---

## 📞 Need Help?

If something doesn't work:

1. Check bot is running: Look for "Bot started successfully!"
2. Check for errors in console
3. Verify database migrations: `python manage.py migrate`
4. Restart bot if needed
5. Check TODO.md for known limitations

---

**Happy Testing! 🎉**

Report any bugs or issues you find!
