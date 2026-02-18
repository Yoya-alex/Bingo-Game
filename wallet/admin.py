from django.contrib import admin
from django.utils import timezone
from .models import Wallet, Transaction, Deposit, Withdrawal


@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ['user', 'main_balance', 'bonus_balance', 'total_balance', 'updated_at']
    search_fields = ['user__first_name', 'user__username', 'user__telegram_id']
    readonly_fields = ['created_at', 'updated_at']
    
    actions = ['add_main_balance', 'add_bonus_balance']
    
    def add_main_balance(self, request, queryset):
        """Add balance to main balance"""
        from django.contrib import messages
        
        # You can customize the amount here
        amount = 100  # Add 100 Birr
        
        for wallet in queryset:
            wallet.main_balance += amount
            wallet.save()
            
            # Log transaction
            Transaction.objects.create(
                user=wallet.user,
                transaction_type='deposit',
                amount=amount,
                status='approved',
                description=f'Manual balance addition by admin'
            )
        
        self.message_user(
            request, 
            f"Added {amount} Birr to {queryset.count()} wallet(s)",
            messages.SUCCESS
        )
    add_main_balance.short_description = "Add 100 Birr to Main Balance"
    
    def add_bonus_balance(self, request, queryset):
        """Add balance to bonus balance"""
        from django.contrib import messages
        
        amount = 50  # Add 50 Birr bonus
        
        for wallet in queryset:
            wallet.bonus_balance += amount
            wallet.save()
            
            # Log transaction
            Transaction.objects.create(
                user=wallet.user,
                transaction_type='bonus',
                amount=amount,
                status='approved',
                description=f'Manual bonus addition by admin'
            )
        
        self.message_user(
            request, 
            f"Added {amount} Birr bonus to {queryset.count()} wallet(s)",
            messages.SUCCESS
        )
    add_bonus_balance.short_description = "Add 50 Birr to Bonus Balance"


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'transaction_type', 'amount', 'status', 'created_at']
    list_filter = ['transaction_type', 'status', 'created_at']
    search_fields = ['user__first_name', 'user__username', 'description']
    readonly_fields = ['created_at']
    
    actions = ['approve_transactions', 'reject_transactions']
    
    def approve_transactions(self, request, queryset):
        for transaction in queryset.filter(status='pending'):
            if transaction.transaction_type == 'deposit':
                if transaction.amount is None:
                    continue
                transaction.status = 'completed'
            else:
                transaction.status = 'approved'
            transaction.processed_at = timezone.now()
            transaction.processed_by = None  # You can link to admin user if needed
            transaction.save()
            
            # Update wallet based on transaction type
            wallet = transaction.user.wallet
            if transaction.transaction_type == 'deposit':
                wallet.main_balance += transaction.amount
                wallet.save()
            elif transaction.transaction_type == 'withdrawal':
                # Already deducted, just mark as processed
                pass
        
        self.message_user(request, f"{queryset.count()} transactions approved")
    approve_transactions.short_description = "Approve selected transactions"
    
    def reject_transactions(self, request, queryset):
        for transaction in queryset.filter(status='pending'):
            transaction.status = 'rejected'
            transaction.processed_at = timezone.now()
            transaction.save()
            
            # Refund if withdrawal
            if transaction.transaction_type == 'withdrawal':
                wallet = transaction.user.wallet
                wallet.main_balance += transaction.amount
                wallet.save()
        
        self.message_user(request, f"{queryset.count()} transactions rejected")
    reject_transactions.short_description = "Reject selected transactions"


@admin.register(Deposit)
class DepositAdmin(admin.ModelAdmin):
    list_display = ['transaction', 'payment_method', 'get_status', 'get_amount']
    list_filter = ['payment_method', 'transaction__status']
    
    def get_status(self, obj):
        return obj.transaction.status
    get_status.short_description = 'Status'
    
    def get_amount(self, obj):
        return obj.transaction.amount
    get_amount.short_description = 'Amount'


@admin.register(Withdrawal)
class WithdrawalAdmin(admin.ModelAdmin):
    list_display = ['transaction', 'payment_method', 'account_info', 'get_status', 'get_amount']
    list_filter = ['payment_method', 'transaction__status']
    
    def get_status(self, obj):
        return obj.transaction.status
    get_status.short_description = 'Status'
    
    def get_amount(self, obj):
        return obj.transaction.amount
    get_amount.short_description = 'Amount'
