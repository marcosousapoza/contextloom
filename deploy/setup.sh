#!/bin/sh
set -eu

POD="contextloom"
SECRETS_FILE="deploy/contextloom.secrets.env"

create_secret() {
    name="$1"
    key="$2"
    value="$3"
    encoded="$(printf '%s' "$value" | base64 | tr -d '\n')"
    podman secret rm "$name" >/dev/null 2>&1 || true
    printf 'apiVersion: v1\nkind: Secret\nmetadata:\n  name: %s\ndata:\n  %s: %s\n' \
        "$name" "$key" "$encoded" | podman secret create "$name" - >/dev/null
}

if [ -f "$SECRETS_FILE" ]; then
    . "./$SECRETS_FILE"
else
    CONTEXTLOOM_SECRET_KEY="${CONTEXTLOOM_SECRET_KEY:-$(openssl rand -hex 32)}"
    CONTEXTLOOM_DATABASE_PASSWORD="${CONTEXTLOOM_DATABASE_PASSWORD:-$(openssl rand -hex 24)}"
    umask 077
    printf 'CONTEXTLOOM_SECRET_KEY=%s\nCONTEXTLOOM_DATABASE_PASSWORD=%s\n' \
        "$CONTEXTLOOM_SECRET_KEY" "$CONTEXTLOOM_DATABASE_PASSWORD" >"$SECRETS_FILE"
fi
secret_key="${CONTEXTLOOM_SECRET_KEY}"
database_password="${CONTEXTLOOM_DATABASE_PASSWORD}"
database_url="postgresql://contextloom:${database_password}@127.0.0.1:5432/contextloom"

podman pod rm --force "$POD" >/dev/null 2>&1 || true
create_secret contextloom-secret-key CONTEXTLOOM_SECRET_KEY "$secret_key"
create_secret contextloom-postgres-password POSTGRES_PASSWORD "$database_password"
create_secret contextloom-database-url CONTEXTLOOM_DATABASE_URL "$database_url"
podman volume exists contextloom-postgres-data || podman volume create contextloom-postgres-data >/dev/null
podman play kube deploy/contextloom.yml

printf '%s\n' "Waiting for PostgreSQL..."
attempt=0
until podman exec contextloom-postgres pg_isready -U contextloom -d contextloom >/dev/null 2>&1; do
    attempt=$((attempt + 1))
    if [ "$attempt" -ge 30 ]; then
        printf '%s\n' "PostgreSQL did not become ready. Check: podman pod logs $POD" >&2
        exit 1
    fi
    sleep 2
done

podman exec contextloom-contextloom contextloom migrate
if [ "${CONTEXTLOOM_CREATE_ADMIN:-0}" = "1" ]; then
    : "${CONTEXTLOOM_ADMIN_USERNAME:?Set CONTEXTLOOM_ADMIN_USERNAME}"
    : "${CONTEXTLOOM_ADMIN_EMAIL:?Set CONTEXTLOOM_ADMIN_EMAIL}"
    : "${CONTEXTLOOM_ADMIN_PASSWORD:?Set CONTEXTLOOM_ADMIN_PASSWORD}"
    podman exec \
        --env CONTEXTLOOM_ADMIN_USERNAME \
        --env CONTEXTLOOM_ADMIN_EMAIL \
        --env CONTEXTLOOM_ADMIN_PASSWORD \
        contextloom-contextloom contextloom create-admin
fi
printf '%s\n' "ContextLoom is available at http://localhost:8000"
