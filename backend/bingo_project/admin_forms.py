from django import forms
from django.conf import settings
from django.contrib.admin.forms import AdminAuthenticationForm


class TokenAdminAuthenticationForm(AdminAuthenticationForm):
    """Django admin login form with optional token verification."""

    admin_login_token = forms.CharField(
        required=False,
        label="Admin Token",
        widget=forms.PasswordInput(render_value=False, attrs={"autocomplete": "off"}),
        help_text="Required when ADMIN_LOGIN_TOKEN is configured.",
    )

    error_messages = {
        **AdminAuthenticationForm.error_messages,
        "invalid_token": "Invalid admin token.",
    }

    def clean(self):
        cleaned_data = super().clean()

        expected_token = (getattr(settings, "ADMIN_LOGIN_TOKEN", "") or "").strip()
        if not expected_token:
            return cleaned_data

        provided_token = (cleaned_data.get("admin_login_token") or "").strip()
        if provided_token != expected_token:
            raise forms.ValidationError(
                self.error_messages["invalid_token"],
                code="invalid_token",
            )

        return cleaned_data
