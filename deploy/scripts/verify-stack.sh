#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

ENV_FILE="${ENV_FILE:-$ROOT/.env}"
if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing environment file: $ENV_FILE" >&2
  exit 2
fi

set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a

compose=(docker compose --env-file "$ENV_FILE" -f "$ROOT/docker-compose.yml")
BASE_URL="http://127.0.0.1:${EDGE_PORT:-8080}"

for service in postgres redis api worker scheduler frontend reverse-proxy; do
  container_id="$("${compose[@]}" ps -q "$service")"
  if [[ -z "$container_id" ]]; then
    echo "Service $service has no container" >&2
    exit 1
  fi
done

for service in postgres redis api worker scheduler frontend reverse-proxy; do
  container_id="$("${compose[@]}" ps -q "$service")"
  state="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container_id")"
  if [[ "$state" != "healthy" ]]; then
    echo "Service $service is not healthy: $state" >&2
    "${compose[@]}" logs --no-color --tail=80 "$service" >&2 || true
    exit 1
  fi
done

for service in api worker scheduler frontend reverse-proxy; do
  container_id="$("${compose[@]}" ps -q "$service")"
  uid="$(docker compose --env-file "$ENV_FILE" -f "$ROOT/docker-compose.yml" exec -T "$service" id -u | tr -d '\r')"
  if [[ "$uid" == "0" ]]; then
    echo "Service $service is running as root" >&2
    exit 1
  fi
done

curl -fsS "$BASE_URL/healthz" >/dev/null
curl -fsS "$BASE_URL/" >/dev/null
curl -fsS "$BASE_URL/api/v1" >/dev/null
curl -fsS "$BASE_URL/health/live" | python -c 'import json,sys; data=json.load(sys.stdin); assert data["status"] == "ok"'
curl -fsS "$BASE_URL/health/ready" | python -c 'import json,sys; data=json.load(sys.stdin); assert data["status"] == "ready"'

echo "Compose stack is healthy through $BASE_URL"
