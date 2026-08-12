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
    umask 077
    printf 'CONTEXTLOOM_SECRET_KEY=%s\n' "$CONTEXTLOOM_SECRET_KEY" >"$SECRETS_FILE"
fi
secret_key="${CONTEXTLOOM_SECRET_KEY}"

podman pod rm --force "$POD" >/dev/null 2>&1 || true
podman secret rm contextloom-postgres-password contextloom-database-url >/dev/null 2>&1 || true
create_secret contextloom-secret-key CONTEXTLOOM_SECRET_KEY "$secret_key"
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
podman exec contextloom-contextloom contextloom create-admin
printf '%s\n' "ContextLoom is available at http://localhost:8000"
printf '%s\n' "Initial login: admin / admin (password change required)"
