# 👨‍💼 Admin Guide - Managing User Balances

## 🚀 Quick Start

### Step 1: Create Admin Account (First Time Only)

```bash
python manage.py createsuperuser
```

Enter:
- Username: `admin`
- Email: (press Enter to skip)
- Password: (your password)
- Password confirmation: (same password)

### Step 2: Start Django Server

```bash
python manage.py runserver
```

### Step 3: Access Admin Panel

Open browser: **http://localhost:8000/admin**

Login with your admin credentials.

---

## 💰 How to Manually Increase User Balance

### Method 1: Using Quick Actions (Recommended)

1. **Go to Admin Panel:** http://localhost:8000/admin
2. **Click "Wallets"** in the left menu
3. **Find the user** (search by name or telegram ID)
4. **Select the checkbox** next to the user's wallet
5. **Choose action** from dropdown:
   - "Add 100 Birr to Main Balance"
   - "Add 50 Birr to Bonus Balance"
6. **Click "Go"**
7. ✅ Done! Balance updated instantly!

### Method 2: Edit Wallet Directly

1. **Go to Admin Panel:** http://localhost:8000/admin
2. **Click "Wallets"**
3. **Click on the user's wallet**
4. **Edit the balance fields:**
   - Main balance: Enter new amount
   - Bonus balance: Enter new amount
5. **Click "Save"**
6. ✅ Done!

### Method 3: Approve Pending Deposits

1. **Go to Admin Panel:** http://localhost:8000/admin
2. **Click "Transactions"**
3. **Filter by:** Status = Pending, Type = Deposit
4. **Select the transactions** to approve
5. **Choose action:** "Approve selected transactions"
6. **Click "Go"**
7. ✅ Balance credited automatically!

---

## 📊 Admin Panel Features

### Users Section
- View all registered users
- See telegram IDs
- Check registration dates
- Mark users as admin

### Wallets Section
- View all user balances
- See main + bonus balance
- Quick actions to add balance
- Search by user name

### Transactions Section
- View all transactions
- Filter by type (deposit, withdrawal, game, bonus)
- Filter by status (pending, approved, rejected)
- Approve/reject deposits
- Approve/reject withdrawals

### Games Section
- View all games
- See player counts
- Check game states
- View winners

### Bingo Cards Section
- See all cards
- Check which users have which cards
- View card numbers

---

## 🎯 Common Admin Tasks

### Task 1: Give User Test Money

**Quick Way:**
1. Go to Wallets
2. Find user
3. Select checkbox
4. Action: "Add 100 Birr to Main Balance"
5. Click Go

**Manual Way:**
1. Go to Wallets
2. Click on user's wallet
3. Change main_balance to desired amount (e.g., 1000)
4. Click Save

### Task 2: Approve Deposit

1. Go to Transactions
2. Filter: Status = Pending, Type = Deposit
3. Select transaction
4. Action: "Approve selected transactions"
5. Click Go
6. User's balance updated automatically!

### Task 3: Approve Withdrawal

1. Go to Transactions
2. Filter: Status = Pending, Type = Withdrawal
3. Select transaction
4. Action: "Approve selected transactions"
5. Click Go
6. Process payment manually to user

### Task 4: View Game Details

1. Go to Games
2. Click on a game
3. See:
   - Game state
   - Player count
   - Winner
   - Prize amount
   - Called numbers

### Task 5: Check User's Cards

1. Go to Bingo Cards
2. Search for user name
3. See all their cards
4. Check card numbers

---

## 🔧 Customizing Balance Amounts

Want to change the quick action amounts?

Edit `wallet/admin.py`:

```python
def add_main_balance(self, request, queryset):
    amount = 100  # Change this to any amount you want
    # ... rest of code
```

Then restart Django server:
```bash
# Stop server (Ctrl+C)
python manage.py runserver
```

---

## 💡 Pro Tips

### Tip 1: Search Users Quickly
In Wallets section, use the search box:
- Search by first name
- Search by username
- Search by telegram ID

### Tip 2: Filter Transactions
Use the right sidebar filters:
- By transaction type
- By status
- By date

### Tip 3: Bulk Operations
Select multiple wallets/transactions and apply actions to all at once!

### Tip 4: View User Details
Click on a user's name to see:
- All their transactions
- Their wallet
- Their game history

---

## 🐛 Troubleshooting

### Issue: Can't login to admin
**Solution:** Create superuser again
```bash
python manage.py createsuperuser
```

### Issue: Changes not showing
**Solution:** Refresh the page (F5)

### Issue: Balance not updating in bot
**Solution:** User needs to click "💰 Balance" button in bot to see updated balance

### Issue: Admin panel looks broken
**Solution:** Make sure Django server is running
```bash
python manage.py runserver
```

---

## 📱 Quick Reference

### Admin URLs:
- **Main:** http://localhost:8000/admin
- **Users:** http://localhost:8000/admin/users/user/
- **Wallets:** http://localhost:8000/admin/wallet/wallet/
- **Transactions:** http://localhost:8000/admin/wallet/transaction/
- **Games:** http://localhost:8000/admin/game/game/

### Quick Actions:
- **Add 100 Birr:** Select wallet → Action → "Add 100 Birr to Main Balance"
- **Add 50 Bonus:** Select wallet → Action → "Add 50 Birr to Bonus Balance"
- **Approve Deposit:** Select transaction → Action → "Approve selected transactions"
- **Reject Withdrawal:** Select transaction → Action → "Reject selected transactions"

---

## 🎓 Step-by-Step Example

### Example: Give User 500 Birr for Testing

1. Open browser: http://localhost:8000/admin
2. Login with admin credentials
3. Click "Wallets" in left menu
4. Find user (search by name)
5. Click on their wallet
6. Change "Main balance" to 500
7. Click "Save" button at bottom
8. ✅ Done! User now has 500 Birr

### Example: Approve a Deposit

1. Open browser: http://localhost:8000/admin
2. Click "Transactions"
3. Click "Pending" filter on right
4. Click "Deposit" filter on right
5. Check the box next to the deposit
6. Select "Approve selected transactions" from dropdown
7. Click "Go"
8. ✅ Done! Balance credited to user

---

## 🎉 That's It!

You can now:
- ✅ Add balance to any user
- ✅ Approve deposits
- ✅ Approve withdrawals
- ✅ View all game data
- ✅ Manage users

**Most common task:** Add balance for testing
**Fastest way:** Wallets → Select user → Action: "Add 100 Birr" → Go

---

**Need help? Check the Django admin documentation or ask!** 👨‍💼
