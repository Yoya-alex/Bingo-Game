from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('game', '0007_game_stake_amount'),
    ]

    operations = [
        migrations.CreateModel(
            name='StakeLobbyLock',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('stake_amount', models.IntegerField(unique=True)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
            ],
            options={
                'db_table': 'stake_lobby_lock',
            },
        ),
    ]
