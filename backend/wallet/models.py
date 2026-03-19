from django.db import models
from django.utils import timezone
from users.models import User


class Wallet(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='wallet')
    main_balance = models.DecimalField(max_digits=10, decimal_places=2, default=0)  # Deposit money (cannot withdraw)
    bonus_balance = models.DecimalField(max_digits=10, decimal_places=2, default=0)  # Bonus money
    winnings_balance = models.DecimalField(max_digits=10, decimal_places=2, default=0)  # Prize money (can withdraw)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'wallets'
    
    @property
    def total_balance(self):
        """Total balance for playing games (deposit + bonus + winnings)"""
        return self.main_balance + self.bonus_balance + self.winnings_balance
    
    @property
    def withdrawable_balance(self):
        """Only winnings can be withdrawn"""
        return self.winnings_balance
    
    def __str__(self):
        return f"Wallet of {self.user.first_name} - Total: {self.total_balance}"


class Transaction(models.Model):
    TRANSACTION_TYPES = [
        ('deposit', 'Deposit'),
        ('withdrawal', 'Withdrawal'),
        ('game_entry', 'Game Entry'),
        ('game_win', 'Game Win'),
        ('bonus', 'Bonus'),
        ('referral_bonus', 'Referral Bonus'),
        ('admin_adjustment', 'Admin Adjustment'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('completed', 'Completed'),
        ('rejected', 'Rejected'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='transactions')
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    reference = models.CharField(max_length=100, blank=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    processed_at = models.DateTimeField(null=True, blank=True)
    processed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='processed_transactions')
    
    class Meta:
        db_table = 'transactions'
        ordering = ['-created_at']
    
    def __str__(self):
        amount_text = self.amount if self.amount is not None else "Pending"
        return f"{self.transaction_type} - {amount_text} - {self.status}"


class Deposit(models.Model):
    transaction = models.OneToOneField(Transaction, on_delete=models.CASCADE, related_name='deposit_detail')
    payment_proof = models.TextField()
    payment_method = models.CharField(max_length=100)
    
    class Meta:
        db_table = 'deposits'
    
    def __str__(self):
        return f"Deposit {self.transaction.amount} by {self.transaction.user.first_name}"


class Withdrawal(models.Model):
    transaction = models.OneToOneField(Transaction, on_delete=models.CASCADE, related_name='withdrawal_detail')
    payment_method = models.CharField(max_length=100)
    account_info = models.CharField(max_length=255)
    
    class Meta:
        db_table = 'withdrawals'
    
    def __str__(self):
        return f"Withdrawal {self.transaction.amount} by {self.transaction.user.first_name}"
