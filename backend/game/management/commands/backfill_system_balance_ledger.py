from django.core.management.base import BaseCommand

from game.models import Game, SystemBalanceLedger


class Command(BaseCommand):
    help = 'Backfill system balance ledger entries for finished games with system_revenue but missing ledger rows.'

    def handle(self, *args, **options):
        candidates = Game.objects.filter(state='finished', system_revenue__gt=0).order_by('id')
        created_count = 0
        skipped_count = 0

        for game in candidates:
            if SystemBalanceLedger.objects.filter(game=game).exists():
                skipped_count += 1
                continue

            event_type = 'game_commission' if game.winner_id else 'game_no_winner'
            idempotency_key = f"game:{game.id}:{'winner_commission' if game.winner_id else 'no_winner'}"

            SystemBalanceLedger.append_entry(
                event_type=event_type,
                direction='credit',
                amount=game.system_revenue,
                game=game,
                description=f'Backfilled settlement for Game #{game.id}.',
                metadata={
                    'winner_id': game.winner_id,
                    'backfilled': True,
                },
                idempotency_key=idempotency_key,
            )
            created_count += 1

        self.stdout.write(self.style.SUCCESS(
            f'Backfill complete. created={created_count}, skipped={skipped_count}, total_candidates={candidates.count()}'
        ))
