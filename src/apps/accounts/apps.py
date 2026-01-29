# src/apps/accounts/apps.py
from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"
    label = "accounts"  # AUTH_USER_MODEL = "accounts.User" と一致させるため明示
