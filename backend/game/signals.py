from decimal import Decimal

from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Game, SystemBalanceLedger


@receiver(post_save, sender=Game)
def ensure_system_balance_ledger_for_finished_game(sender, instance, **kwargs):
    if instance.state != 'finished':
        return

    revenue = Decimal(str(instance.system_revenue or 0))
    if revenue <= 0:
        return

    if SystemBalanceLedger.objects.filter(game=instance).exists():
        return

    event_type = 'game_commission' if instance.winner_id else 'game_no_winner'
    idempotency_key = f'game:{instance.id}:{"winner_commission" if instance.winner_id else "no_winner"}'

    SystemBalanceLedger.append_entry(
        event_type=event_type,
        direction='credit',
        amount=revenue,
        game=instance,
        description=f'Automatic settlement sync for finished Game #{instance.id}.',
        metadata={
            'winner_id': instance.winner_id,
            'auto_synced': True,
        },
        idempotency_key=idempotency_key,
    )
