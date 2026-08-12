# Development Guide

## Architecture

ContextLoom is a Django modular monolith:

- `contextloom.config` contains settings, URL routing, health endpoints, and ASGI startup.
- `contextloom.accounts` owns users, authentication, login throttling, Admin configuration,
  and personal access tokens.
- `contextloom.knowledge` owns categories, memories, archives, forms, shared services, and
  import/export.
- `contextloom.mcp_integration` embeds the MCP SDK's Streamable HTTP ASGI application.

Web views and MCP tools call the same owner-aware service functions. Synchronous Django ORM
work is moved out of async MCP handlers with `sync_to_async`; worker-thread connections are
closed after every operation.

## Environment

Install Python 3.12 and uv, then synchronize exactly from `uv.lock`:

```console
uv sync --locked --all-extras
```

Start PostgreSQL locally and set:

```console
export CONTEXTLOOM_DATABASE_URL=postgresql://contextloom:contextloom@127.0.0.1/contextloom
export CONTEXTLOOM_SECRET_KEY=development-only-change-me
```

Run migrations and the ASGI server:

```console
uv run contextloom migrate
uv run contextloom serve
```

The standard `uv run python manage.py <command>` interface remains available.

`uv run contextloom create-admin` defaults to `admin` / `admin` for the zero-input deployment
flow and marks that password as temporary. Use explicit command arguments for other local
administrators. Assigned passwords must always be replaced on first login.

Public registration is intentionally absent. New accounts must be created through Django
Admin so every assigned initial password is subject to the first-login replacement flow.

## Quality Gate

Before opening a pull request, run:

```console
uv lock --check
uv run ruff format --check .
uv run ruff check .
uv run python manage.py check
uv run python manage.py makemigrations --check --dry-run
uv run pytest -q
uv run python -m build
```

Tests intentionally require PostgreSQL; SQLite is not a supported substitute. To build the
production image locally, run:

```console
podman build --tag localhost/contextloom:dev --file Containerfile .
```

The container workflow validates multi-architecture builds on pull requests and publishes
images from `main` and version tags to GitHub Container Registry.

## Migrations

Define model changes in the relevant app and generate migrations with:

```console
uv run python manage.py makemigrations
```

Review generated SQL-sensitive behavior against PostgreSQL. Never edit an already released
migration unless the project explicitly decides to reset unreleased history.

## Tests

- Use Django's test client for browser behavior and CSRF checks.
- Assert owner scoping whenever adding a read or mutation path.
- Add import fixtures that validate the complete payload before calling `apply_import`.
- MCP tests must cover bearer authentication and required scopes.
- Transaction and concurrency tests use `pytest.mark.django_db(transaction=True)`.

## Dependencies

Edit `pyproject.toml`, then regenerate and inspect the lockfile:

```console
uv lock
uv sync --all-extras
```

Do not introduce repository layers, background services, or frontend frameworks without a
demonstrated requirement.
