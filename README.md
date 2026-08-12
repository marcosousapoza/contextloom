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
- `openssl` for the setup helper
- Python 3.12 and [uv](https://docs.astral.sh/uv/) for development
- PostgreSQL 14 or newer for development and testing

No reverse proxy is included. ContextLoom serves plain HTTP on port 8000 by default;
production operators should place their own TLS-terminating reverse proxy in front of it.

## Podman Deployment

The helper generates Podman secrets, creates persistent storage, pulls the published image,
starts the pod, and runs migrations. Generated source values are retained in the ignored,
mode-0600 `deploy/contextloom.secrets.env`; protect that file because it is required to
recreate matching secrets:

```console
chmod +x deploy/setup.sh
deploy/setup.sh
```

To create the initial administrator during setup, supply values without writing them to a
file:

```console
CONTEXTLOOM_CREATE_ADMIN=1 \
CONTEXTLOOM_ADMIN_USERNAME=admin \
CONTEXTLOOM_ADMIN_EMAIL=admin@example.com \
CONTEXTLOOM_ADMIN_PASSWORD='use-a-long-random-password' \
deploy/setup.sh
```

After secrets, the image, and storage exist, the deployment itself is always:

```console
podman play kube deploy/contextloom.yml
```

The manifest pulls `ghcr.io/marcosousapoza/contextloom:latest`. Version releases are also
published with semantic-version tags, which are preferable for stable production
deployments. Change the image tag in `deploy/contextloom.yml` to pin a release. After the
first workflow publish, set the package visibility to public in GitHub Packages so hosts can
pull anonymously. Until then, authenticate with `podman login ghcr.io` using a token with
`read:packages`.

Open <http://localhost:8000>. PostgreSQL shares the pod network but has no host-published
port. Its named volume, `contextloom-postgres-data`, survives pod recreation.

To create an administrator later:

```console
podman exec \
  --env CONTEXTLOOM_ADMIN_USERNAME=admin \
  --env CONTEXTLOOM_ADMIN_EMAIL=admin@example.com \
  --env CONTEXTLOOM_ADMIN_PASSWORD='use-a-long-random-password' \
  contextloom-contextloom contextloom create-admin
```

## Reverse Proxy

Set `CONTEXTLOOM_PUBLIC_URL`, `CONTEXTLOOM_ALLOWED_HOSTS`,
`CONTEXTLOOM_CSRF_TRUSTED_ORIGINS`, `CONTEXTLOOM_MCP_ALLOWED_HOSTS`, and
`CONTEXTLOOM_MCP_ALLOWED_ORIGINS` to the public HTTPS origin. Set
`CONTEXTLOOM_SECURE_COOKIES=true`. The proxy must preserve `Host`, set
`X-Forwarded-Proto: https`, pass the `Authorization` header, support long-lived HTTP
responses, and proxy `/mcp` without changing its path. Restrict trusted forwarded-header
sources with `CONTEXTLOOM_FORWARDED_ALLOW_IPS`.

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
3. Build or pull the new image.
4. Run `contextloom migrate` once.
5. Recreate the pod and check `/health` and `/ready`.

Migrations are explicit and are not run automatically when the application starts.

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
| `CONTEXTLOOM_SECRET_KEY` | required | Django and token-hash secret |
| `CONTEXTLOOM_HOST` / `CONTEXTLOOM_PORT` | `0.0.0.0` / `8000` | ASGI listener |
| `CONTEXTLOOM_PUBLIC_URL` | `http://localhost:8000` | Canonical MCP URL |
| `CONTEXTLOOM_ALLOWED_HOSTS` | local hosts | Django host allowlist |
| `CONTEXTLOOM_CSRF_TRUSTED_ORIGINS` | empty | Trusted form origins |
| `CONTEXTLOOM_REGISTRATION_ENABLED` | `false` | Initial registration setting |
| `CONTEXTLOOM_SECURE_COOKIES` | `false` | Require HTTPS cookies |
| `CONTEXTLOOM_MCP_ALLOWED_HOSTS` | local hosts | MCP DNS-rebinding allowlist |
| `CONTEXTLOOM_MCP_ALLOWED_ORIGINS` | local origins | MCP origin allowlist |
| `CONTEXTLOOM_LOG_LEVEL` | `INFO` | stdout/stderr logging level |
| `CONTEXTLOOM_FORWARDED_ALLOW_IPS` | `127.0.0.1` | Trusted proxy addresses |
| `CONTEXTLOOM_ADMIN_*` | empty | Initial-admin command inputs |

Resource-limit settings are documented in `deploy/contextloom.env.example` and the Django
settings module.

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
podman build -t localhost/contextloom:0.1.0 .
```

GitHub Actions builds the `Containerfile` for `linux/amd64` and `linux/arm64`. Pushes to
`main` publish `latest` and commit-SHA tags to GHCR; `v*` Git tags publish semantic-version
tags. Pull requests build without publishing.

## License

ContextLoom is licensed under the GNU Affero General Public License v3.0 or later.
