# ContextLoom

ContextLoom is a self-hosted, multi-user application for organizing and retrieving
categorized knowledge. It combines a restrained server-rendered web interface with an
MCP Streamable HTTP endpoint, PostgreSQL persistence, and Django's account and Admin
facilities.

Documentation:

- [User guide](docs/USER_GUIDE.md)
- [Administration guide](docs/ADMINISTRATION.md)
- [Development guide](docs/DEVELOPMENT.md)
- [Upgrade notes](UPGRADING.md)
- [Security policy](SECURITY.md)

## Requirements

- Rootless Podman 5 or newer for deployment
- `openssl` for deployment-secret generation
- Python 3.12 and [uv](https://docs.astral.sh/uv/) for development
- PostgreSQL 14 or newer for development and testing

No reverse proxy is included. ContextLoom serves plain HTTP on port 8000 by default;
production operators should place their own TLS-terminating reverse proxy in front of it.

## Podman Deployment

Create a unique Django secret in Podman's secret store. This command preserves an existing
secret, so it is safe to run again:

```console
podman secret exists contextloom-secret-key || (key="$(openssl rand -hex 32)" && printf 'apiVersion: v1\nkind: Secret\nmetadata:\n  name: contextloom-secret-key\nstringData:\n  CONTEXTLOOM_SECRET_KEY: %s\n' "$key" | podman secret create contextloom-secret-key -)
```

Then deploy directly from the public manifest:

```console
podman kube play --replace https://raw.githubusercontent.com/marcosousapoza/contextloom/v0.2.1/deploy/contextloom.yml
```

Podman stores the serialized Kubernetes Secret separately from the image and source tree.
The manifest resolves its `CONTEXTLOOM_SECRET_KEY` key through `secretKeyRef`; no plaintext
secret file is created by ContextLoom. Back up the Podman secret store according to your
host's secret-driver policy because losing or replacing this value invalidates browser
sessions and personal access tokens.

Unlike `podman run --secret type=env`, kube `secretKeyRef` expansion places the resolved value
in the container configuration, where a host operator can view it with `podman inspect`. Use
the same access controls for Podman administration as for the secret store itself.

The application waits for PostgreSQL, applies migrations, idempotently creates the initial
administrator, and then starts the server. The persistent volume claim is created by the
same manifest.

Sign in at <http://localhost:8000> with username `admin` and password `admin`. ContextLoom
immediately requires replacing that password before any other page or Admin function can be
used. Port 8000 binds to localhost by default; do not expose the initial credentials to an
untrusted network.

For a checked-out manifest, the equivalent deployment command is:

```console
podman kube play --replace deploy/contextloom.yml
```

The release manifest pulls `ghcr.io/marcosousapoza/contextloom:0.2.1`. The same release image
is also published as `0.2` and `latest`; exact versions are preferable for reproducible
deployments. The public package can be pulled anonymously.

Use a version-tagged manifest URL rather than `main`. Development on `main` may include a
future manifest that is incompatible with the latest released image.

Open <http://localhost:8000>. PostgreSQL shares the pod network but has no host-published
port. Its named volume, `contextloom-postgres-data`, survives pod recreation.

To create an administrator later:

```console
podman exec \
  contextloom-contextloom contextloom create-admin \
  --username another-admin \
  --email another-admin@example.com \
  --password 'an-assigned-password'
```

The account must replace the assigned password after signing in.

## Database Authentication

PostgreSQL is unpublished and accepts trusted connections only from within the pod network by
default. This removes a credential that would otherwise be automatically generated and
available to the application container anyway. Never publish PostgreSQL port 5432.

Operators who require password authentication can replace `POSTGRES_HOST_AUTH_METHOD=trust`
with `POSTGRES_PASSWORD` and include that password in `CONTEXTLOOM_DATABASE_URL` in
`deploy/contextloom.yml`. Apply this choice before PostgreSQL initializes a new data volume;
authentication settings are persisted with the database cluster.

## Reverse Proxy

Set `CONTEXTLOOM_PUBLIC_URL`, `CONTEXTLOOM_ALLOWED_HOSTS`,
`CONTEXTLOOM_CSRF_TRUSTED_ORIGINS`, `CONTEXTLOOM_MCP_ALLOWED_HOSTS`, and
`CONTEXTLOOM_MCP_ALLOWED_ORIGINS` to the public HTTPS origin. Set
`CONTEXTLOOM_SECURE_COOKIES=true`. The proxy can connect to `127.0.0.1:8000` and must
preserve `Host`, set `X-Forwarded-Proto: https`, pass the `Authorization` header, support
long-lived HTTP responses, and proxy `/mcp` without changing its path. Restrict trusted
forwarded-header sources with `CONTEXTLOOM_FORWARDED_ALLOW_IPS`.

## MCP

In **Settings**, create a personal access token with the minimum required category and
memory scopes. Configure an MCP client for Streamable HTTP:

```json
{
  "url": "https://contextloom.example.com/mcp",
  "headers": {"Authorization": "Bearer clm_value-shown-once"}
}
```

Tokens are hashed at rest, shown once, independently revocable, optionally expiring, and
never authenticated through browser cookies. Disabled accounts cannot use their tokens.

The `edit_category` tool changes only the supplied `name` or `description`. Supply
`parent_id` to move the category and its subtree below another owned category, or set
`move_to_root` to `true` to make it top-level. The `edit_memory` tool similarly changes only
the supplied `content` or `priority`; supply `category_id` to move it. These tools require
the existing `categories:write` and `memories:write` scopes, respectively. Calls with no
changes are rejected.

## Data Portability

**Settings > Export my data** downloads a versioned ZIP containing `manifest.json` and
UTF-8 CSV files for categories, memories, and complete archives. Credentials and account
roles are excluded. **Import** validates an upload and shows a dry-run summary before any
write. Merge adds records and suffixes colliding category names; replace requires typing
`replace` and atomically replaces only the signed-in user's knowledge.

This format is portability, not disaster recovery.

## Upgrades

1. Read `UPGRADING.md` and release notes.
2. Back up PostgreSQL.
3. Pin or select the new image or manifest version.
4. Recreate the pod; `contextloom start` applies migrations before serving requests.
5. Check `/health`, `/ready`, login, and an MCP request.

The `contextloom migrate` command remains available for development and maintenance. The
production `contextloom start` command runs migrations automatically for the single-instance
Podman deployment.

## PostgreSQL Backup

The system administrator is responsible for PostgreSQL backup, retention, encryption,
testing, and disaster recovery. For a concise logical backup reference:

```console
pg_dump --format=custom --file=contextloom.dump "$CONTEXTLOOM_DATABASE_URL"
pg_restore --clean --if-exists --dbname="$CONTEXTLOOM_DATABASE_URL" contextloom.dump
```

Stop application writes before a destructive restore and follow PostgreSQL's documentation.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `CONTEXTLOOM_DATABASE_URL` | required | PostgreSQL URL |
| `CONTEXTLOOM_SECRET_KEY` | required | Django and token-hash secret; supplied by Podman in deployment |
| `CONTEXTLOOM_DATABASE_WAIT_ATTEMPTS` | `30` | Production startup connection attempts |
| `CONTEXTLOOM_DATABASE_WAIT_SECONDS` | `2` | Seconds between startup connection attempts |
| `CONTEXTLOOM_HOST` / `CONTEXTLOOM_PORT` | `0.0.0.0` / `8000` | ASGI listener |
| `CONTEXTLOOM_PUBLIC_URL` | `http://localhost:8000` | Canonical MCP URL |
| `CONTEXTLOOM_ALLOWED_HOSTS` | local hosts | Django host allowlist |
| `CONTEXTLOOM_CSRF_TRUSTED_ORIGINS` | empty | Trusted form origins |
| `CONTEXTLOOM_SECURE_COOKIES` | `false` | Require HTTPS cookies |
| `CONTEXTLOOM_MCP_ALLOWED_HOSTS` | local hosts | MCP DNS-rebinding allowlist |
| `CONTEXTLOOM_MCP_ALLOWED_ORIGINS` | local origins | MCP origin allowlist |
| `CONTEXTLOOM_LOG_LEVEL` | `INFO` | stdout/stderr logging level |
| `CONTEXTLOOM_FORWARDED_ALLOW_IPS` | `127.0.0.1` | Trusted proxy addresses |

Non-secret deployment settings are summarized in `deploy/contextloom.env.example` and the
Django settings module.

## Development

Use uv for all dependency and environment management:

```console
uv sync --all-extras
CONTEXTLOOM_SECRET_KEY=development-only \
CONTEXTLOOM_DATABASE_URL=postgresql://contextloom:contextloom@localhost/contextloom \
uv run contextloom migrate
uv run contextloom serve
```

Standard `uv run python manage.py <command>` remains available. Verification commands:

```console
uv run ruff format --check .
uv run ruff check .
uv run pytest
uv run python -m build
podman build -t localhost/contextloom:0.2.1 .
```

GitHub Actions builds the `Containerfile` for `linux/amd64` and `linux/arm64` on pull
requests without publishing. Pushes to `main` run the normal CI workflow but do not build or
publish a container. A matching `vX.Y.Z` Git tag publishes the same image as `X.Y.Z`, `X.Y`,
and `latest`.

## License

ContextLoom is licensed under the GNU Affero General Public License v3.0 or later.
