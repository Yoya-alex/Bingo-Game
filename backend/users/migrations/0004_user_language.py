from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0003_user_last_site_seen_at'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='language',
            field=models.CharField(
                blank=True,
                choices=[('en', 'English'), ('am', 'Amharic'), ('om', 'Oromo')],
                max_length=5,
                null=True,
            ),
        ),
    ]
