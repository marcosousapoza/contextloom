import os

import uvicorn
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Run ContextLoom with the production Uvicorn ASGI server."

    def add_arguments(self, parser):
        parser.add_argument("--host", default=os.getenv("CONTEXTLOOM_HOST", "0.0.0.0"))
        parser.add_argument("--port", type=int, default=int(os.getenv("CONTEXTLOOM_PORT", "8000")))

    def handle(self, *args, **options):
        uvicorn.run(
            "contextloom.config.asgi:application",
            host=options["host"],
            port=options["port"],
            proxy_headers=True,
            forwarded_allow_ips=os.getenv("CONTEXTLOOM_FORWARDED_ALLOW_IPS", "127.0.0.1"),
        )
