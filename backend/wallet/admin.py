from django.contrib import admin, messages
from django.utils import timezone
from django.urls import path
from django.http import HttpResponseRedirect
from .models import Wallet, Transaction, Deposit, Withdrawal


@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ['user', 'main_balance', 'bonus_balance', 'winnings_balance', 'total_balance', 'updated_at']
    search_fields = ['user__first_name', 'user__username', 'user__telegram_id']
    readonly_fields = ['created_at', 'updated_at']
    
    actions = ['add_main_balance', 'add_bonus_balance']
    
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('reset-all-winnings/', self.admin_site.admin_view(self.reset_all_winnings), name='reset_all_winnings'),
        ]
        return custom_urls + urls
    
    def reset_all_winnings(self, request):
        """Reset all winning balances except for users with completed deposits"""
        # Get users with completed deposits
        users_with_completed_deposits = set(
            Transaction.objects.filter(
                transaction_type='deposit',
                status='completed'
            ).values_list('user_id', flat=True)
        )
        
        # Get all wallets to reset (exclude those with completed deposits)
        wallets_to_reset = Wallet.objects.exclude(
            user_id__in=users_with_completed_deposits
        ).exclude(winnings_balance=0)
        
        total_reset = sum(w.winnings_balance for w in wallets_to_reset)
        count = wallets_to_reset.count()
        
        if count == 0:
            self.message_user(request, "No wallets with winning balance to reset.", messages.WARNING)
        else:
            # Reset winning balance to 0
            wallets_to_reset.update(winnings_balance=0)
            self.message_user(
                request,
                f"✅ Reset winning balance to 0 for {count} user(s). Total amount reset: {total_reset} Birr",
                messages.SUCCESS
            )
        
        return HttpResponseRedirect(request.META.get('HTTP_REFERER', '/admin/wallet/wallet/'))
    
    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        
        # Calculate stats
        users_with_completed_deposits = set(
            Transaction.objects.filter(
                transaction_type='deposit',
                status='completed'
            ).values_list('user_id', flat=True)
        )
        
        wallets_to_reset = Wallet.objects.exclude(
            user_id__in=users_with_completed_deposits
        ).exclude(winnings_balance=0)
        
        total_reset = sum(w.winnings_balance for w in wallets_to_reset)
        count = wallets_to_reset.count()
        
        extra_context['reset_winnings_count'] = count
        extra_context['reset_winnings_total'] = total_reset
        extra_context['reset_winnings_url'] = 'admin:reset_all_winnings'
        
        return super().changelist_view(request, extra_context=extra_context)
    
    def add_main_balance(self, request, queryset):
        """Add balance to main balance"""
        
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
    list_display = ['id', 'user', 'transaction_type', 'amount', 'status', 'reference', 'created_at']
    list_filter = ['transaction_type', 'status', 'created_at']
    search_fields = ['user__first_name', 'user__username', 'description']
    readonly_fields = ['created_at']
    
    actions = ['approve_transactions', 'reject_transactions', 'reset_winnings_except_selected']
    
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
    
    def reset_winnings_except_selected(self, request, queryset):
        """Reset winning balance to 0 for users WITHOUT the selected completed deposits"""
        # Get only completed deposits from selection
        completed_deposits = queryset.filter(
            transaction_type='deposit',
            status='completed'
        )
        
        if not completed_deposits.exists():
            self.message_user(
                request,
                "❌ Please select completed deposits first.",
                messages.ERROR
            )
            return
        
        # Get users with selected completed deposits
        users_with_selected_deposits = set(completed_deposits.values_list('user_id', flat=True))
        
        # Get all wallets to reset (exclude those with selected completed deposits)
        wallets_to_reset = Wallet.objects.exclude(
            user_id__in=users_with_selected_deposits
        ).exclude(winnings_balance=0)
        
        total_reset = sum(w.winnings_balance for w in wallets_to_reset)
        count = wallets_to_reset.count()
        
        if count == 0:
            self.message_user(
                request,
                "No wallets with winning balance to reset.",
                messages.WARNING
            )
            return
        
        # Reset winning balance to 0
        wallets_to_reset.update(winnings_balance=0)
        
        self.message_user(
            request,
            f"✅ Reset winning balance to 0 for {count} user(s). Total amount reset: {total_reset} Birr\n"
            f"Users with selected completed deposits were excluded.",
            messages.SUCCESS
        )
    reset_winnings_except_selected.short_description = "🔄 Reset Winning Balance to 0 (Except Selected Deposits)"


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
