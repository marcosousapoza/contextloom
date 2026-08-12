import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Create the initial administrator from arguments or environment variables."

    def add_arguments(self, parser):
        parser.add_argument("--username", default=os.getenv("CONTEXTLOOM_ADMIN_USERNAME"))
        parser.add_argument("--email", default=os.getenv("CONTEXTLOOM_ADMIN_EMAIL"))
        parser.add_argument("--password", default=os.getenv("CONTEXTLOOM_ADMIN_PASSWORD"))

    def handle(self, *args, **options):
        missing = [name for name in ("username", "email", "password") if not options[name]]
        if missing:
            raise CommandError(f"Missing administrator values: {', '.join(missing)}")
        user_model = get_user_model()
        if user_model.objects.filter(username=options["username"]).exists():
            self.stdout.write("Administrator already exists; no changes made.")
            return
        user_model.objects.create_superuser(
            username=options["username"],
            email=options["email"],
            password=options["password"],
        )
        self.stdout.write(self.style.SUCCESS("Initial administrator created."))
