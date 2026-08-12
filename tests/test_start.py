import tomllib
from pathlib import Path
from unittest.mock import call, patch

import pytest
from django.core.management.base import CommandError
from django.db.utils import OperationalError

from contextloom.accounts.management.commands.start import Command


@patch("contextloom.accounts.management.commands.start.time.sleep")
@patch("contextloom.accounts.management.commands.start.call_command")
@patch("contextloom.accounts.management.commands.start.connection")
def test_start_waits_then_initializes_and_serves(connection, call_command, sleep):
    connection.ensure_connection.side_effect = [OperationalError("not ready"), None]

    Command().handle(database_wait_attempts=3, database_wait_seconds=0.25)

    assert connection.ensure_connection.call_count == 2
    connection.close.assert_called_once_with()
    sleep.assert_called_once_with(0.25)
    assert call_command.call_args_list == [
        call("migrate", interactive=False),
        call("create_initial_admin"),
        call("serve"),
    ]


@patch("contextloom.accounts.management.commands.start.time.sleep")
@patch("contextloom.accounts.management.commands.start.call_command")
@patch("contextloom.accounts.management.commands.start.connection")
def test_start_fails_after_bounded_database_wait(connection, call_command, sleep):
    connection.ensure_connection.side_effect = OperationalError("not ready")

    with pytest.raises(CommandError, match="after 2 attempts"):
        Command().handle(database_wait_attempts=2, database_wait_seconds=0)

    assert connection.ensure_connection.call_count == 2
    assert connection.close.call_count == 2
    sleep.assert_called_once_with(0)
    call_command.assert_not_called()


@patch("contextloom.accounts.management.commands.start.time.sleep")
@patch("contextloom.accounts.management.commands.start.call_command")
@patch("contextloom.accounts.management.commands.start.connection")
def test_start_does_not_retry_migration_failures(connection, call_command, sleep):
    call_command.side_effect = RuntimeError("migration failed")

    with pytest.raises(RuntimeError, match="migration failed"):
        Command().handle(database_wait_attempts=3, database_wait_seconds=1)

    connection.ensure_connection.assert_called_once_with()
    sleep.assert_not_called()
    call_command.assert_called_once_with("migrate", interactive=False)


def test_remote_manifest_uses_start_and_external_secret():
    manifest = Path("deploy/contextloom.yml").read_text()
    with Path("pyproject.toml").open("rb") as project_file:
        version = tomllib.load(project_file)["project"]["version"]

    assert 'args: ["start"]' in manifest
    assert f"image: ghcr.io/marcosousapoza/contextloom:{version}" in manifest
    assert "secretKeyRef:" in manifest
    assert "name: contextloom-secret-key" in manifest
    assert "kind: Secret" not in manifest
    assert "httpGet:" in manifest
    assert "apt-get install --yes --no-install-recommends curl" in Path("Containerfile").read_text()


def test_plaintext_secret_file_and_setup_helper_are_absent():
    assert not Path("deploy/setup.sh").exists()
    assert "contextloom.secrets.env" not in Path(".gitignore").read_text()
    assert "CONTEXTLOOM_SECRET_KEY=" not in Path("deploy/contextloom.env.example").read_text()
