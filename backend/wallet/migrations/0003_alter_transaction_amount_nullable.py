from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("wallet", "0002_alter_transaction_transaction_type"),
    ]

    operations = [
        migrations.AlterField(
            model_name="transaction",
            name="amount",
            field=models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True),
        ),
    ]
