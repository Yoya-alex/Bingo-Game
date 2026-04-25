import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('game', '0018_businessrulesettings_rejoin_start_delay_minutes_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='businessrulesettings',
            name='winner_announcement_seconds',
            field=models.PositiveIntegerField(
                default=3,
                help_text='How long the winner announcement modal stays visible before redirecting users.',
                validators=[
                    django.core.validators.MinValueValidator(1),
                    django.core.validators.MaxValueValidator(120),
                ],
            ),
        ),
    ]
