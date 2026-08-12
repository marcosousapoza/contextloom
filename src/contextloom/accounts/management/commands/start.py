import os
import time

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.utils import OperationalError


class Command(BaseCommand):
    help = "Wait for PostgreSQL, initialize ContextLoom, and run the production server."

    def add_arguments(self, parser):
        parser.add_argument(
            "--database-wait-attempts",
            type=int,
            default=int(os.getenv("CONTEXTLOOM_DATABASE_WAIT_ATTEMPTS", "30")),
        )
        parser.add_argument(
            "--database-wait-seconds",
            type=float,
            default=float(os.getenv("CONTEXTLOOM_DATABASE_WAIT_SECONDS", "2")),
        )

    def handle(self, *args, **options):
        attempts = options["database_wait_attempts"]
        wait_seconds = options["database_wait_seconds"]
        if attempts < 1 or wait_seconds < 0:
            raise CommandError("Database wait attempts must be positive and seconds non-negative.")

        self.stdout.write("Waiting for PostgreSQL...")
        for attempt in range(1, attempts + 1):
            try:
                connection.ensure_connection()
                break
            except OperationalError as error:
                connection.close()
                if attempt == attempts:
                    raise CommandError(
                        f"PostgreSQL did not become ready after {attempts} attempts."
                    ) from error
                time.sleep(wait_seconds)

        call_command("migrate", interactive=False)
        call_command("create_initial_admin")
        call_command("serve")
