import os
import sys


def main() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "contextloom.config.settings")
    from django.core.management import execute_from_command_line

    aliases = {
        "migrate": ["migrate"],
        "create-admin": ["create_initial_admin"],
        "start": ["start"],
        "serve": ["serve"],
    }
    if len(sys.argv) < 2 or sys.argv[1] not in aliases:
        options = ", ".join(aliases)
        raise SystemExit(f"Usage: contextloom <{options}> [arguments]")
    execute_from_command_line([sys.argv[0], *aliases[sys.argv[1]], *sys.argv[2:]])
