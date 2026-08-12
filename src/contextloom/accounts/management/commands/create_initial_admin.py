from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create the initial administrator, requiring a password change on first login."

    def add_arguments(self, parser):
        parser.add_argument("--username", default="admin")
        parser.add_argument("--email", default="admin@localhost.invalid")
        parser.add_argument("--password", default="admin")

    def handle(self, *args, **options):
        user_model = get_user_model()
        if user_model.objects.filter(username=options["username"]).exists():
            self.stdout.write("Administrator already exists; no changes made.")
            return
        user = user_model.objects.create_superuser(
            username=options["username"],
            email=options["email"],
            password=options["password"],
        )
        user.password_change_required = True
        user.save(update_fields=["password_change_required"])
        self.stdout.write(
            self.style.SUCCESS(
                f"Initial administrator created. Sign in as {options['username']} with the "
                "assigned password and change it immediately."
            )
        )
