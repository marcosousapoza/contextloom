# Administration Guide

## Accounts

Open `/admin/` with a superuser account. ContextLoom Admin exposes only users and the
application registration setting. User categories, memories, archives, sessions, imports,
and token hashes are deliberately absent.

Use `is_active` to enable or disable an account, `is_staff` to permit Admin access, and
`is_superuser` for full administrative privileges. ContextLoom does not define parallel
roles, teams, or organizations.

Create the first administrator with:

```console
CONTEXTLOOM_ADMIN_USERNAME=admin \
CONTEXTLOOM_ADMIN_EMAIL=admin@example.com \
CONTEXTLOOM_ADMIN_PASSWORD='a-long-random-password' \
contextloom create-admin
```

The command is idempotent by username.

## Registration

Registration is disabled by default. Change **Application settings** in Admin to enable or
disable it. The database setting takes precedence over the initial environment default.

## Health

- `/health` reports whether the application process is serving requests.
- `/ready` verifies that the application can connect to PostgreSQL.

Use readiness for traffic routing and deployment checks. A healthy but unready instance
must not receive user or MCP traffic.

## Backups

ContextLoom does not manage infrastructure backups. The administrator is responsible for
PostgreSQL backup scheduling, encryption, off-site storage, retention, and restore tests.

```console
pg_dump --format=custom --file=contextloom.dump "$CONTEXTLOOM_DATABASE_URL"
pg_restore --clean --if-exists --dbname="$CONTEXTLOOM_DATABASE_URL" contextloom.dump
```

User exports are portability archives and do not contain accounts, credentials, sessions,
tokens, permissions, or complete infrastructure state.

## Secret Rotation

Protect `deploy/contextloom.secrets.env` with the same care as database credentials. Losing
it prevents the helper from recreating matching Podman secrets. Rotating
`CONTEXTLOOM_SECRET_KEY` invalidates existing sessions and all personal access tokens.

After changing deployment secrets, recreate the pod and run `/ready` checks before routing
traffic to it.

## Container Images

Published images are available at `ghcr.io/marcosousapoza/contextloom`. The `latest` tag
tracks `main`; semantic-version tags identify releases and commit-SHA tags identify exact
builds. Production deployments should pin a semantic-version or SHA tag in
`deploy/contextloom.yml`, then use `podman play kube --replace deploy/contextloom.yml` to
apply the update before running migrations with the target image.

GitHub Container Registry creates a new package as private by default. A repository owner
must change the package visibility to public once if anonymous deployment pulls are desired.
For a private package, run `podman login ghcr.io` with a personal access token carrying the
`read:packages` scope on each deployment host.
