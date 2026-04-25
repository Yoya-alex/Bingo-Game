from django.core.management.base import BaseCommand
from wallet.models import Wallet


class Command(BaseCommand):
    help = 'Reset all users winning balance to 0'

    def add_arguments(self, parser):
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='Confirm the reset operation',
        )

    def handle(self, *args, **options):
        if not options['confirm']:
            count = Wallet.objects.exclude(winnings_balance=0).count()
            self.stdout.write(
                self.style.WARNING(
                    f'⚠️  This will reset winning balance to 0 for {count} users.\n'
                    f'Run with --confirm flag to proceed:\n'
                    f'python manage.py reset_winnings --confirm'
                )
            )
            return

        # Get all wallets with non-zero winnings
        wallets = Wallet.objects.exclude(winnings_balance=0)
        count = wallets.count()
        total_amount = sum(w.winnings_balance for w in wallets)

        if count == 0:
            self.stdout.write(self.style.SUCCESS('✅ No users with winning balance to reset.'))
            return

        # Reset all winnings to 0
        wallets.update(winnings_balance=0)

        self.stdout.write(
            self.style.SUCCESS(
                f'✅ Successfully reset winning balance for {count} users.\n'
                f'Total amount reset: {total_amount} Birr'
            )
        )
