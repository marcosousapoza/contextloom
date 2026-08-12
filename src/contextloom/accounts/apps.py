from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "contextloom.accounts"
    verbose_name = "Accounts"

    def ready(self):
        from contextloom.accounts import admin  # noqa: F401
