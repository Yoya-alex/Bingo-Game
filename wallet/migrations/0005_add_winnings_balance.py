# Generated migration for adding winnings_balance

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('wallet', '0004_alter_transaction_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='wallet',
            name='winnings_balance',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
        ),
    ]
