import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create a Django superuser during deploy when env vars are provided."

    @staticmethod
    def _get_first_env(*names: str) -> str:
        for name in names:
            value = os.getenv(name, "").strip()
            if value:
                return value
        return ""

    def handle(self, *args, **options):
        username = self._get_first_env("DJANGO_SUPERUSER_USERNAME", "ADMIN_USERNAME", "SUPERUSER_USERNAME")
        email = self._get_first_env("DJANGO_SUPERUSER_EMAIL", "ADMIN_EMAIL", "SUPERUSER_EMAIL")
        password = self._get_first_env("DJANGO_SUPERUSER_PASSWORD", "ADMIN_PASSWORD", "SUPERUSER_PASSWORD")

        if not username or not email or not password:
            self.stdout.write(
                self.style.WARNING(
                    "Skipping superuser creation: set DJANGO_SUPERUSER_USERNAME, "
                    "DJANGO_SUPERUSER_EMAIL, and DJANGO_SUPERUSER_PASSWORD "
                    "(or ADMIN_USERNAME, ADMIN_EMAIL, ADMIN_PASSWORD)."
                )
            )
            return

        User = get_user_model()
        user = User.objects.filter(username=username).first()

        if user:
            changed = False
            if email and user.email != email:
                user.email = email
                changed = True
            if password and not user.check_password(password):
                user.set_password(password)
                changed = True
            if not user.is_staff:
                user.is_staff = True
                changed = True
            if not user.is_superuser:
                user.is_superuser = True
                changed = True
            if changed:
                user.save()
                self.stdout.write(self.style.SUCCESS(f"Superuser '{username}' updated from environment."))
            else:
                self.stdout.write(self.style.SUCCESS(f"Superuser '{username}' already exists."))
            return

        User.objects.create_superuser(username=username, email=email, password=password)
        self.stdout.write(self.style.SUCCESS(f"Created superuser '{username}'."))
