#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
# shellcheck source=lib-compose.sh
. "$ROOT/deploy/scripts/lib-compose.sh"

ENV_FILE="${ENV_FILE:-$ROOT/.env}"
if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing environment file: $ENV_FILE" >&2
  exit 2
fi

set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a
load_release_env
configure_compose "$ROOT" "$ENV_FILE"

BASE_URL="${VERIFY_BASE_URL:-http://127.0.0.1:${EDGE_PORT:-8080}}"

for service in postgres redis api worker scheduler frontend reverse-proxy; do
  container_id="$("${COMPOSE[@]}" ps -q "$service")"
  if [[ -z "$container_id" ]]; then
    echo "Service $service has no container" >&2
    exit 1
  fi
done

for service in postgres redis api worker scheduler frontend reverse-proxy; do
  container_id="$("${COMPOSE[@]}" ps -q "$service")"
  state="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container_id")"
  if [[ "$state" != "healthy" ]]; then
    echo "Service $service is not healthy: $state" >&2
    "${COMPOSE[@]}" logs --no-color --tail=80 "$service" >&2 || true
    exit 1
  fi
done

for service in api worker scheduler frontend reverse-proxy; do
  uid="$("${COMPOSE[@]}" exec -T "$service" id -u | tr -d '\r')"
  if [[ "$uid" == "0" ]]; then
    echo "Service $service is running as root" >&2
    exit 1
  fi
done

curl -fsS "$BASE_URL/healthz" >/dev/null
curl -fsS "$BASE_URL/" >/dev/null
curl -fsS "$BASE_URL/api/v1" >/dev/null
curl -fsS "$BASE_URL/health/live" | python3 -c 'import json,sys; data=json.load(sys.stdin); assert data["status"] == "ok"'
curl -fsS "$BASE_URL/health/ready" | python3 -c 'import json,sys; data=json.load(sys.stdin); assert data["status"] == "ready"'

headers_file="$(mktemp)"
trap 'rm -f "$headers_file"' EXIT
curl -sS -D "$headers_file" -o /dev/null "$BASE_URL/" || true
for header in \
  'x-content-type-options: nosniff' \
  'x-frame-options: SAMEORIGIN' \
  'referrer-policy: strict-origin-when-cross-origin' \
  'strict-transport-security: max-age='; do
  grep -Eiq "^${header%%:*}: .*${header#*: }" "$headers_file" \
    || { echo "Missing security header: $header" >&2; exit 1; }
done
grep -Eiq '^content-security-policy: .*default-src .self.*' "$headers_file" \
  || { echo "Missing Content-Security-Policy" >&2; exit 1; }
curl -sS -D "$headers_file" -o /dev/null \
  "$BASE_URL/api/v1/coach/streams/00000000-0000-0000-0000-000000000000" || true
grep -Eiq '^x-accel-buffering: no' "$headers_file" \
  || { echo "SSE route does not disable proxy buffering" >&2; exit 1; }
grep -Eiq '^cache-control: .*no-cache.*no-store' "$headers_file" \
  || { echo "SSE route does not disable response caching" >&2; exit 1; }

echo "Compose stack is healthy through $BASE_URL"