# Administration Guide

## Accounts

Open `/admin/` with a superuser account. ContextLoom Admin exposes only users and the
account management controls. User categories, memories, archives, sessions, imports, and
token hashes are deliberately absent.

Use `is_active` to enable or disable an account, `is_staff` to permit Admin access, and
`is_superuser` for full administrative privileges. ContextLoom does not define parallel
roles, teams, or organizations.

The production `contextloom start` command creates the first administrator automatically
after applying migrations. It is invoked by `deploy/contextloom.yml`.

Sign in as `admin` with password `admin`. ContextLoom blocks all other browser pages until the
password is replaced. The command is idempotent by username.

Accounts created through Django Admin are also marked for a mandatory password change. The
administrator assigns the initial password in the account creation form; the user signs in
with it once and must replace it before using ContextLoom. Public registration is not
available; administrators are the only account creators.

## Health

- `/health` reports whether the application process is serving requests.
- `/ready` verifies that the application can connect to PostgreSQL.

Use readiness for traffic routing and deployment checks. A healthy but unready instance
must not receive user or MCP traffic.

## PostgreSQL Authentication

The default single-pod deployment uses PostgreSQL trust authentication and does not publish
port 5432. Only containers sharing the pod network namespace can reach that listener. The
application's database compromise boundary is therefore the same with or without an embedded
password, because the application must possess any configured password.

For policy-driven password authentication, edit `deploy/contextloom.yml` before first startup:

1. Replace `POSTGRES_HOST_AUTH_METHOD=trust` with `POSTGRES_PASSWORD` sourced from your secret
   management system.
2. Put the same password in `CONTEXTLOOM_DATABASE_URL`.
3. Keep port 5432 unpublished.

Changing these environment values does not rewrite authentication for an existing PostgreSQL
data volume; follow PostgreSQL's `pg_hba.conf` procedures when converting an existing cluster.

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

ContextLoom stores no deployment secret file. Protect and back up the Podman secret store
according to the configured Podman secret driver. Its default `file` driver keeps secrets in
read-protected host files.

Rotate the secret deliberately with:

```console
(key="$(openssl rand -hex 32)" && printf 'apiVersion: v1\nkind: Secret\nmetadata:\n  name: contextloom-secret-key\nstringData:\n  CONTEXTLOOM_SECRET_KEY: %s\n' "$key" | podman secret create --replace contextloom-secret-key -)
podman kube play --replace https://raw.githubusercontent.com/marcosousapoza/contextloom/v0.1.0/deploy/contextloom.yml
```

Replacing the Podman secret does not alter already-created containers, so pod replacement is
required. Rotating `CONTEXTLOOM_SECRET_KEY` invalidates existing sessions and all personal
access tokens.

After changing deployment secrets, recreate the pod and run `/ready` checks before routing
traffic to it.

## Container Images

Published images are available at `ghcr.io/marcosousapoza/contextloom`. Containers are
published only from `vX.Y.Z` release tags. Each release updates the exact `X.Y.Z` tag, its
`X.Y` series alias, and `latest` to the same image. Production deployments should use the
version-tagged manifest, which pins the exact image, then use `podman kube play --replace` to
apply an update. The target image applies migrations before starting the server.

To publish a release, update the version in `pyproject.toml` and the image tag in
`deploy/contextloom.yml`, merge the tested changes into `main`, then create and push the
matching tag, such as `v0.1.0`. The container workflow rejects malformed tags and tags that
do not match the package or manifest version.

The package is public and deployment hosts can pull it without registry credentials.
