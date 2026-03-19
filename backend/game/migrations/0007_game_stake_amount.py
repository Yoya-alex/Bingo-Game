from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('game', '0006_system_balance_tables'),
    ]

    operations = [
        migrations.AddField(
            model_name='game',
            name='stake_amount',
            field=models.IntegerField(db_index=True, default=10),
        ),
    ]
