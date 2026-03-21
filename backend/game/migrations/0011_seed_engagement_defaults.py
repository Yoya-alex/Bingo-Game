from decimal import Decimal
from datetime import timedelta

from django.db import migrations
from django.utils import timezone


def seed_defaults(apps, schema_editor):
    RewardSafetyPolicy = apps.get_model('game', 'RewardSafetyPolicy')
    MissionTemplate = apps.get_model('game', 'MissionTemplate')
    Season = apps.get_model('game', 'Season')

    RewardSafetyPolicy.objects.get_or_create(
        pk=1,
        defaults={
            'daily_reward_cap': Decimal('500.00'),
            'min_seconds_between_rewards': 20,
            'max_reward_redemptions_per_hour': 20,
        },
    )

    templates = [
        {
            'key': 'daily_play_3',
            'title': 'Play 3 Games',
            'description': 'Join 3 games today.',
            'mission_type': 'play_games',
            'period': 'daily',
            'target_value': 3,
            'reward_amount': Decimal('10.00'),
            'reward_balance': 'bonus',
            'sort_order': 10,
        },
        {
            'key': 'daily_win_1',
            'title': 'Win 1 Game',
            'description': 'Get at least one bingo win today.',
            'mission_type': 'win_games',
            'period': 'daily',
            'target_value': 1,
            'reward_amount': Decimal('20.00'),
            'reward_balance': 'bonus',
            'sort_order': 20,
        },
        {
            'key': 'daily_redeem_1',
            'title': 'Redeem 1 Promo Code',
            'description': 'Redeem one promo code today.',
            'mission_type': 'redeem_promo',
            'period': 'daily',
            'target_value': 1,
            'reward_amount': Decimal('8.00'),
            'reward_balance': 'bonus',
            'sort_order': 30,
        },
        {
            'key': 'weekly_play_15',
            'title': 'Play 15 Games This Week',
            'description': 'Join 15 games in the current week.',
            'mission_type': 'play_games',
            'period': 'weekly',
            'target_value': 15,
            'reward_amount': Decimal('60.00'),
            'reward_balance': 'bonus',
            'sort_order': 100,
        },
        {
            'key': 'weekly_win_5',
            'title': 'Win 5 Games This Week',
            'description': 'Get 5 wins this week.',
            'mission_type': 'win_games',
            'period': 'weekly',
            'target_value': 5,
            'reward_amount': Decimal('100.00'),
            'reward_balance': 'bonus',
            'sort_order': 110,
        },
    ]

    for template in templates:
        MissionTemplate.objects.get_or_create(key=template['key'], defaults=template)

    now = timezone.now()
    current_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    next_month_start = (current_month_start + timedelta(days=32)).replace(day=1)

    Season.objects.get_or_create(
        name=f"Season {current_month_start.strftime('%Y-%m')}",
        defaults={
            'starts_at': current_month_start,
            'ends_at': next_month_start - timedelta(seconds=1),
            'is_active': True,
            'top_1_reward': Decimal('500.00'),
            'top_2_reward': Decimal('300.00'),
            'top_3_reward': Decimal('200.00'),
            'participation_reward': Decimal('20.00'),
        },
    )


def reverse_seed_defaults(apps, schema_editor):
    MissionTemplate = apps.get_model('game', 'MissionTemplate')
    MissionTemplate.objects.filter(
        key__in=['daily_play_3', 'daily_win_1', 'daily_redeem_1', 'weekly_play_15', 'weekly_win_5']
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('game', '0010_liveevent_missiontemplate_promocode_and_more'),
    ]

    operations = [
        migrations.RunPython(seed_defaults, reverse_seed_defaults),
    ]
