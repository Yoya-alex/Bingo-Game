"""Helper utilities for admin checks and admin-related data access."""

from asgiref.sync import sync_to_async
from django.conf import settings

from users.models import User


def _is_admin_sync(telegram_id: int) -> bool:
    """
    Synchronous helper to determine if a given telegram_id has admin rights.

    A user is considered admin if:
    - Their telegram_id is listed in settings.ADMIN_IDS, OR
    - The corresponding User record has is_admin=True.
    """
    # Check static ADMIN_IDS list first
    if telegram_id in getattr(settings, "ADMIN_IDS", []):
        return True

    try:
        user = User.objects.get(telegram_id=telegram_id)
    except User.DoesNotExist:
        return False

    return bool(user.is_admin)


@sync_to_async
def is_admin(telegram_id: int) -> bool:
    """
    Async wrapper around _is_admin_sync for use in Aiogram handlers.
    """
    return _is_admin_sync(telegram_id)


@sync_to_async
def get_admin_user(telegram_id: int):
    """
    Return the corresponding User model instance for this telegram_id if it exists,
    regardless of admin status. Returns None if not found.
    """
    try:
        return User.objects.get(telegram_id=telegram_id)
    except User.DoesNotExist:
        return None

