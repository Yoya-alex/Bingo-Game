from django.db import models
from django.utils import timezone


class User(models.Model):
    telegram_id = models.BigIntegerField(unique=True, db_index=True)
    username = models.CharField(max_length=255, null=True, blank=True)
    first_name = models.CharField(max_length=255)
    registration_date = models.DateTimeField(default=timezone.now)
    is_active = models.BooleanField(default=True)
    is_admin = models.BooleanField(default=False)
    
    class Meta:
        db_table = 'users'
        ordering = ['-registration_date']
    
    def __str__(self):
        return f"{self.first_name} (@{self.username})"
