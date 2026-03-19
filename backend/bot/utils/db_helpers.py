"""Database helper functions for async operations"""
from asgiref.sync import sync_to_async
from users.models import User
from wallet.models import Wallet


@sync_to_async
def get_user_by_telegram_id(telegram_id):
    """Get user by telegram ID"""
    try:
        return User.objects.get(telegram_id=telegram_id)
    except User.DoesNotExist:
        return None


@sync_to_async
def get_or_create_user(telegram_id, username, first_name):
    """Get or create user"""
    return User.objects.get_or_create(
        telegram_id=telegram_id,
        defaults={
            'username': username,
            'first_name': first_name
        }
    )


@sync_to_async
def get_user_wallet(user):
    """Get user's wallet"""
    return user.wallet


@sync_to_async
def create_wallet(user):
    """Create wallet for user"""
    return Wallet.objects.create(user=user)


@sync_to_async
def save_model(instance):
    """Save any model instance"""
    instance.save()
    return instance
