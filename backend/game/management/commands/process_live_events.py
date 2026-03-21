from django.core.management.base import BaseCommand
from django.utils import timezone

from game.models import LiveEvent
from notifications.models import Notification


class Command(BaseCommand):
    help = 'Process live events lifecycle and queue admin announcements.'

    def handle(self, *args, **options):
        now = timezone.now()

        started_events = LiveEvent.objects.filter(
            is_active=True,
            starts_at__lte=now,
            ends_at__gte=now,
            auto_announce=True,
            announced_at__isnull=True,
        )

        started_count = 0
        for event in started_events:
            Notification.objects.create(
                notification_type='admin_announcement',
                title=f'Live Event Started: {event.name}',
                message=(
                    f"{event.name}\n"
                    f"Type: {event.event_type}\n"
                    f"Bonus Multiplier: {event.bonus_multiplier}x\n"
                    f"Ends at: {event.ends_at.isoformat()}"
                ),
                status='draft',
            )
            event.announced_at = now
            event.save(update_fields=['announced_at', 'updated_at'])
            started_count += 1

        expired_events = LiveEvent.objects.filter(
            is_active=True,
            ends_at__lt=now,
        )

        expired_count = expired_events.count()
        expired_events.update(is_active=False, updated_at=now)

        self.stdout.write(
            self.style.SUCCESS(
                f'Processed live events. started={started_count}, expired={expired_count}'
            )
        )
