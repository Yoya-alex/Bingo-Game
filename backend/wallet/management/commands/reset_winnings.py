from django.core.management.base import BaseCommand
from wallet.models import Wallet, Transaction
from users.models import User


class Command(BaseCommand):
    help = 'Reset winning balance to 0 for users with completed deposits'

    def add_arguments(self, parser):
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='Confirm the reset operation',
        )

    def handle(self, *args, **options):
        # Get users who have completed deposits
        users_with_completed_deposits = User.objects.filter(
            transactions__transaction_type='deposit',
            transactions__status='completed'
        ).distinct()

        # Get wallets for these users with non-zero winnings
        wallets = Wallet.objects.filter(
            user__in=users_with_completed_deposits
        ).exclude(winnings_balance=0)

        count = wallets.count()
        total_amount = sum(w.winnings_balance for w in wallets)

        if not options['confirm']:
            self.stdout.write(
                self.style.WARNING(
                    f'⚠️  This will reset winning balance to 0 for {count} users with completed deposits.\n'
                    f'Total amount to be reset: {total_amount} Birr\n'
                    f'Run with --confirm flag to proceed:\n'
                    f'python manage.py reset_winnings_completed_deposits --confirm'
                )
            )
            return

        if count == 0:
            self.stdout.write(self.style.SUCCESS('✅ No users with winning balance and completed deposits to reset.'))
            return

        # Reset all winnings to 0
        wallets.update(winnings_balance=0)

        self.stdout.write(
            self.style.SUCCESS(
                f'✅ Successfully reset winning balance for {count} users with completed deposits.\n'
                f'Total amount reset: {total_amount} Birr'
            )
        )
