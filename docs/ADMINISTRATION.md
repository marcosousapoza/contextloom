# Administration Guide

## Deployment Overview

The supported deployment is one rootless Podman pod containing ContextLoom and PostgreSQL.
HTTP is published only on `127.0.0.1:8000`; PostgreSQL is not published to the host. The
named volume `contextloom-postgres-data` contains the database and survives ordinary pod
replacement.

Requirements:

- Podman 5 or newer using cgroup v2
- OpenSSL for generating the Django secret
- TCP port 8000 available on host loopback
- Caddy or another TLS reverse proxy for public access

Use release-tagged manifests rather than `main`. Download a local copy when configuration
must differ from the localhost defaults:

```console
mkdir -p ~/contextloom
curl --fail --location --output ~/contextloom/contextloom.yml \
  https://raw.githubusercontent.com/marcosousapoza/contextloom/v1.0.0/deploy/contextloom.yml
```

Create the required Podman secret as the same user that will run the pod:

```console
podman secret exists contextloom-secret-key || (key="$(openssl rand -hex 32)" && printf 'apiVersion: v1\nkind: Secret\nmetadata:\n  name: contextloom-secret-key\nstringData:\n  CONTEXTLOOM_SECRET_KEY: %s\n' "$key" | podman secret create contextloom-secret-key -)
```

Edit `~/contextloom/contextloom.yml` before first startup, then deploy it:

```console
podman kube play --replace ~/contextloom/contextloom.yml
curl --fail http://127.0.0.1:8000/health
curl --fail http://127.0.0.1:8000/ready
```

The application waits for PostgreSQL, applies migrations, creates the initial administrator
if it does not exist, and starts Uvicorn. Sign in as `admin` with password `admin` and replace
that password immediately.

## Public HTTPS Setup

For a single public origin such as `https://contextloom.example.com`, keep the host port bound
to `127.0.0.1` and configure the application container environment as follows:

```yaml
        - name: CONTEXTLOOM_PUBLIC_URL
          value: "https://contextloom.example.com"
        - name: CONTEXTLOOM_ALLOWED_HOSTS
          value: "contextloom.example.com,localhost,127.0.0.1"
        - name: CONTEXTLOOM_CSRF_TRUSTED_ORIGINS
          value: "https://contextloom.example.com"
        - name: CONTEXTLOOM_SECURE_COOKIES
          value: "true"
        - name: CONTEXTLOOM_MCP_ALLOWED_HOSTS
          value: "contextloom.example.com,localhost,localhost:*,127.0.0.1,127.0.0.1:*"
        - name: CONTEXTLOOM_MCP_ALLOWED_ORIGINS
          value: "https://contextloom.example.com"
        - name: CONTEXTLOOM_FORWARDED_ALLOW_IPS
          value: "127.0.0.1"
```

Retaining local values in `CONTEXTLOOM_ALLOWED_HOSTS` allows local health checks. For Caddy
running as a system service on the same machine, a minimal Caddyfile is:

```caddyfile
contextloom.example.com {
    reverse_proxy 127.0.0.1:8000
}
```

Caddy preserves `Host`, forwards `Authorization`, and supplies `X-Forwarded-Proto` by
default. Validate local readiness before troubleshooting the proxy:

```console
curl --fail http://127.0.0.1:8000/ready
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

Allow public TCP ports 80 and 443 through the firewall. Do not publish ports 8000 or 5432.
If Caddy runs in a container or on another machine, its connection cannot use host loopback;
change the binding, firewall access to the proxy only, and set
`CONTEXTLOOM_FORWARDED_ALLOW_IPS` to the proxy's actual trusted address.

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

## Rootless Systemd

`restartPolicy: Always` handles container exits but does not attach a direct
`podman kube play` deployment to host startup. To construct a rootless Quadlet, first place
the versioned manifest in the user Quadlet directory:

```console
mkdir -p ~/.config/containers/systemd
curl --fail --location --output ~/.config/containers/systemd/contextloom.yml \
  https://raw.githubusercontent.com/marcosousapoza/contextloom/v1.0.0/deploy/contextloom.yml
```

Create `~/.config/containers/systemd/contextloom.kube` with:

```ini
[Unit]
Description=ContextLoom

[Kube]
Yaml=contextloom.yml
SetWorkingDirectory=yaml
ExitCodePropagation=any

[Service]
Restart=on-failure
RestartSec=10
TimeoutStartSec=900

[Install]
WantedBy=default.target
```

Reload and start the generated service:

```console
systemctl --user daemon-reload
systemctl --user start contextloom.service
```

The `[Install]` section starts it with the user systemd `default.target`; generated Quadlet
services are not enabled with `systemctl enable`. To start before login and remain running
after logout, an administrator must enable lingering once with
`sudo loginctl enable-linger "$USER"`. Stop any directly played `contextloom` pod before
starting the service to avoid a name and port conflict.

Manage and inspect the generated service with:

```console
systemctl --user status contextloom.service
systemctl --user restart contextloom.service
journalctl --user-unit contextloom.service --follow
```

Stopping the Quadlet removes the pod but preserves the database volume and Podman secret.

## Configuration

Configuration is read when the application container starts. Edit the `env` list under the
`contextloom` container in the local manifest, then recreate the pod or restart the Quadlet.
`deploy/contextloom.env.example` is a reference only; `podman kube play` does not load it.
Comma-separated settings should not contain shell quoting inside the YAML value.

### Required And Runtime

| Variable | Default | Purpose |
| --- | --- | --- |
| `CONTEXTLOOM_DATABASE_URL` | required | Django PostgreSQL connection URL. The release manifest connects to PostgreSQL over pod loopback. |
| `CONTEXTLOOM_SECRET_KEY` | required | Django signing key and PAT-hash salt. The release manifest obtains it from `contextloom-secret-key`. |
| `CONTEXTLOOM_HOST` | `0.0.0.0` | Address Uvicorn listens on inside the container. Usually leave unchanged. |
| `CONTEXTLOOM_PORT` | `8000` | Uvicorn container port. Changing it also requires changing manifest ports and probes. |
| `CONTEXTLOOM_BASE_DIR` | current directory | Base for runtime paths such as static storage. Normally leave unchanged in the image. |
| `CONTEXTLOOM_DEBUG` | `false` | Enables Django debug behavior. Never enable on a public deployment. |
| `CONTEXTLOOM_LOG_LEVEL` | `INFO` | Root Python log level, for example `DEBUG`, `INFO`, `WARNING`, or `ERROR`. |

`CONTEXTLOOM_DATABASE_URL` and `CONTEXTLOOM_SECRET_KEY` are deliberately absent from the
non-secret example file because the manifest supplies them separately. Do not commit secret
values or pass them directly in a public manifest.

### Public URL And Trust

| Variable | Default | Purpose |
| --- | --- | --- |
| `CONTEXTLOOM_PUBLIC_URL` | `http://localhost:8000` | One canonical external origin. Used to advertise MCP URLs; omit the trailing slash. |
| `CONTEXTLOOM_ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated HTTP hostnames Django accepts. Values do not include schemes or paths. |
| `CONTEXTLOOM_CSRF_TRUSTED_ORIGINS` | empty | Comma-separated origins allowed to submit protected browser requests. Values include `https://`. |
| `CONTEXTLOOM_SECURE_COOKIES` | `false` | Marks session and CSRF cookies HTTPS-only. Set to `true` for public HTTPS. |
| `CONTEXTLOOM_FORWARDED_ALLOW_IPS` | `127.0.0.1` | Comma-separated proxy addresses Uvicorn trusts to set forwarded headers. This is a trust boundary, not a client allowlist. |
| `CONTEXTLOOM_MCP_ALLOWED_HOSTS` | local hosts | Comma-separated MCP host allowlist used for DNS-rebinding protection. Wildcard ports use forms such as `localhost:*`. |
| `CONTEXTLOOM_MCP_ALLOWED_ORIGINS` | local HTTP origins | Comma-separated origins accepted by the MCP transport, primarily relevant to browser-based clients. |

A host is `contextloom.example.com`; an origin is
`https://contextloom.example.com`. `CONTEXTLOOM_PUBLIC_URL` is singular, while allowlists may
contain multiple comma-separated values. Do not use `*` for public trust settings merely to
avoid configuration errors.

### Authentication And Startup

| Variable | Default | Purpose |
| --- | --- | --- |
| `CONTEXTLOOM_LOGIN_ATTEMPTS` | `5` | Failed login attempts allowed within the throttle window. |
| `CONTEXTLOOM_LOGIN_WINDOW_SECONDS` | `300` | Login-throttle window in seconds. |
| `CONTEXTLOOM_DATABASE_WAIT_ATTEMPTS` | `30` | Database connection attempts made by `contextloom start`. Must be positive. |
| `CONTEXTLOOM_DATABASE_WAIT_SECONDS` | `2` | Delay between database connection attempts. Must be non-negative. |

The default startup wait is approximately 60 seconds. Increase it on slow storage or hosts
where PostgreSQL initialization regularly takes longer. Migration errors are not retried and
cause startup to fail visibly.

### Import And Export Limits

| Variable | Default | Purpose |
| --- | --- | --- |
| `CONTEXTLOOM_EXPORT_SPOOL_LIMIT` | `2000000` | Bytes retained in memory before an export spool moves to temporary storage. |
| `CONTEXTLOOM_IMPORT_MAX_BYTES` | `10000000` | Maximum uploaded archive size in bytes. |
| `CONTEXTLOOM_IMPORT_MAX_EXPANDED_BYTES` | `25000000` | Maximum total uncompressed archive size. Protects against expansion bombs. |
| `CONTEXTLOOM_IMPORT_MAX_ROWS` | `50000` | Maximum combined imported records. |
| `CONTEXTLOOM_IMPORT_MAX_FIELD_LENGTH` | `1000000` | Maximum characters accepted in one imported text field. |
| `CONTEXTLOOM_IMPORT_MAX_DEPTH` | `50` | Maximum imported category nesting depth. |

Raise these limits only after considering memory, temporary-storage, request-duration, and
denial-of-service impact. The manifest provides writable temporary storage at `/tmp` because
the application root filesystem is read-only.

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

Create a logical backup from the default pod without publishing PostgreSQL:

```console
podman exec contextloom-postgres \
  pg_dump --username=contextloom --dbname=contextloom --format=custom \
  > contextloom.dump
```

Test backups on a separate database before relying on them. User exports are portability
archives and do not contain accounts, credentials, sessions, tokens, permissions, or complete
infrastructure state.

For a restore, stop the application container so no writes occur, restore into PostgreSQL,
then start the application again:

```console
podman stop contextloom-contextloom
podman exec -i contextloom-postgres \
  pg_restore --clean --if-exists --username=contextloom --dbname=contextloom \
  < contextloom.dump
podman start contextloom-contextloom
curl --fail http://127.0.0.1:8000/ready
```

Test the exact procedure for the PostgreSQL version and backup strategy in use. A destructive
restore should never be the first time a backup is tested.

## Upgrades

Before an upgrade, read `UPGRADING.md` and the target release notes, then create and verify a
PostgreSQL backup. Download the new exact-version manifest, reapply any local configuration,
and review the resulting diff before replacing the pod:

```console
curl --fail --location --output ~/contextloom/contextloom.yml.new \
  https://raw.githubusercontent.com/marcosousapoza/contextloom/v1.0.0/deploy/contextloom.yml
diff --unified ~/contextloom/contextloom.yml ~/contextloom/contextloom.yml.new
podman kube play --replace ~/contextloom/contextloom.yml
curl --fail http://127.0.0.1:8000/health
curl --fail http://127.0.0.1:8000/ready
```

The command above intentionally deploys `contextloom.yml`, not `.new`. Transfer the reviewed
release changes into the configured manifest first. ContextLoom applies database migrations
before it serves traffic. Do not run an older application image after a migration unless the
release notes explicitly document rollback support.

## Operations And Troubleshooting

Useful direct-Podman commands:

```console
podman pod ps
podman ps --all --pod
podman logs contextloom-contextloom
podman logs contextloom-postgres
podman inspect contextloom-contextloom --format '{{json .State.Health}}'
```

`podman ps` shows the application, PostgreSQL, an infra container for the shared pod network,
and, under Quadlet, a service container. These are containers belonging to one pod, not four
independent ContextLoom installations.

Interpret common failures as follows:

| Symptom | Likely cause | Check |
| --- | --- | --- |
| Caddy returns `502` with connection refused | Application is stopped or restarting | Local `/health`, application logs, container health |
| Health output says `curl: not found` | Running the affected `0.1.0` image | Upgrade to `0.1.1` or temporarily remove application probe blocks |
| Django returns `DisallowedHost` | Public hostname missing from `CONTEXTLOOM_ALLOWED_HOSTS` | Manifest environment and request host |
| Browser forms return CSRF 403 | Public HTTPS origin is not trusted or forwarded scheme is wrong | CSRF origins, Caddy headers, trusted proxy address |
| Login loops only over HTTPS | Cookie or forwarded-proto configuration is inconsistent | Secure cookies and `CONTEXTLOOM_FORWARDED_ALLOW_IPS` |
| MCP rejects host or origin | MCP allowlists do not contain the public values | MCP host and origin variables |
| PostgreSQL never becomes ready | Initialization, permissions, storage, or authentication failure | PostgreSQL logs and volume ownership |

Internet scanners routinely request paths such as `/.env`, `/graphql`, or `/info.php` after a
hostname becomes public. ContextLoom should return 404 for unknown paths. Scanner traffic is
not itself evidence of compromise; investigate unexpected successful responses, crashes, or
authentication events.

## Removal

Stop a direct deployment while preserving data:

```console
podman kube down ~/contextloom/contextloom.yml
```

Completely delete the default deployment, including PostgreSQL data and its secret:

```console
podman kube down --force ~/contextloom/contextloom.yml
podman secret rm contextloom-secret-key
```

The `--force` option removes volumes declared by the manifest, including
`contextloom-postgres-data`; it cannot be undone without a tested backup. `kube down` does not
remove the Podman secret, so that is deleted separately. Container images remain in local
image storage and may be removed with `podman image rm`.

## Secret Rotation

ContextLoom stores no deployment secret file. Protect and back up the Podman secret store
according to the configured Podman secret driver. Its default `file` driver keeps secrets in
read-protected host files. Podman resolves kube `secretKeyRef` values into the container
configuration, so a host administrator can retrieve the key with `podman inspect`. Protect
Podman administration with the same controls as the secret store.

Rotate the secret deliberately with:

```console
(key="$(openssl rand -hex 32)" && printf 'apiVersion: v1\nkind: Secret\nmetadata:\n  name: contextloom-secret-key\nstringData:\n  CONTEXTLOOM_SECRET_KEY: %s\n' "$key" | podman secret create --replace contextloom-secret-key -)
podman kube play --replace ~/contextloom/contextloom.yml
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
matching tag, such as `v1.0.0`. The container workflow rejects malformed tags and tags that
do not match the package or manifest version.

The package is public and deployment hosts can pull it without registry credentials.
