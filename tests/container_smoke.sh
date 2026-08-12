#!/bin/sh
set -eu

POD=contextloom
VOLUME=contextloom-postgres-data
SECRETS="contextloom-secret-key contextloom-postgres-password contextloom-database-url"

cleanup() {
    podman pod rm --force "$POD" >/dev/null 2>&1 || true
    podman volume rm --force "$VOLUME" >/dev/null 2>&1 || true
    for secret in $SECRETS; do
        podman secret rm "$secret" >/dev/null 2>&1 || true
    done
    rm -f deploy/contextloom.secrets.env
}

wait_for_ready() {
    attempt=0
    until curl --fail --silent http://127.0.0.1:8000/ready >/dev/null 2>&1; do
        attempt=$((attempt + 1))
        if [ "$attempt" -ge 60 ]; then
            podman pod ps || true
            podman logs contextloom-contextloom || true
            podman logs contextloom-postgres || true
            return 1
        fi
        sleep 2
    done
}

trap cleanup EXIT INT TERM
cleanup

CONTEXTLOOM_SECRET_KEY=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef \
CONTEXTLOOM_DATABASE_PASSWORD=0123456789abcdef0123456789abcdef \
CONTEXTLOOM_CREATE_ADMIN=1 \
CONTEXTLOOM_ADMIN_USERNAME=smoke-admin \
CONTEXTLOOM_ADMIN_EMAIL=smoke-admin@example.com \
CONTEXTLOOM_ADMIN_PASSWORD=smoke-test-password-42 \
deploy/setup.sh

wait_for_ready
test "$(curl --fail --silent http://127.0.0.1:8000/health)" = '{"status": "healthy"}'
curl --fail --silent --output /dev/null http://127.0.0.1:8000/static/contextloom.css
test "$(curl --silent --output /dev/null --write-out '%{http_code}' \
    --request POST \
    --header 'Content-Type: application/json' \
    --header 'Accept: application/json, text/event-stream' \
    --data '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"smoke","version":"1"}}}' \
    http://127.0.0.1:8000/mcp)" = 401

test "$(podman inspect contextloom-contextloom --format '{{.Config.User}}')" = "10001:10001"
test "$(podman inspect contextloom-contextloom --format '{{.HostConfig.ReadonlyRootfs}}')" = "true"
test "$(podman port contextloom-postgres)" = ""

podman play kube --down deploy/contextloom.yml
podman play kube deploy/contextloom.yml
wait_for_ready
test "$(podman exec contextloom-contextloom contextloom create-admin \
    --username smoke-admin \
    --email smoke-admin@example.com \
    --password irrelevant)" = "Administrator already exists; no changes made."
