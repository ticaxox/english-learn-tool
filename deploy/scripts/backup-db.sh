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

BACKUP_DIR="${BACKUP_DIR:-$ROOT/deploy/backups}"
if [[ "$BACKUP_DIR" != /* ]]; then
  BACKUP_DIR="$ROOT/$BACKUP_DIR"
fi
mkdir -p "$BACKUP_DIR"
umask 077

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
output="$BACKUP_DIR/postgres-$timestamp.dump"
partial="$output.partial"
trap 'rm -f "$partial"' EXIT

if [[ -n "${GHCR_OWNER:-}" && -n "${IMAGE_TAG:-}" ]]; then
  export API_IMAGE="${API_IMAGE:-ghcr.io/${GHCR_OWNER}/english-learn-api:${IMAGE_TAG}}"
  export FRONTEND_IMAGE="${FRONTEND_IMAGE:-ghcr.io/${GHCR_OWNER}/english-learn-frontend:${IMAGE_TAG}}"
  export REVERSE_PROXY_IMAGE="${REVERSE_PROXY_IMAGE:-ghcr.io/${GHCR_OWNER}/english-learn-reverse-proxy:${IMAGE_TAG}}"
else
  : "${API_IMAGE:?API_IMAGE is required when GHCR_OWNER and IMAGE_TAG are unavailable}"
  : "${FRONTEND_IMAGE:?FRONTEND_IMAGE is required when GHCR_OWNER and IMAGE_TAG are unavailable}"
  : "${REVERSE_PROXY_IMAGE:?REVERSE_PROXY_IMAGE is required when GHCR_OWNER and IMAGE_TAG are unavailable}"
fi

compose=(docker compose --env-file "$ENV_FILE" -f "$ROOT/docker-compose.yml" -f "$ROOT/deploy/compose.prod.yml")
"${compose[@]}" config --quiet
"${compose[@]}" exec -T postgres pg_dump \
  -U "${POSTGRES_USER:-english_learn}" \
  -d "${POSTGRES_DB:-english_learn}" \
  --format=custom \
  --no-owner \
  --no-privileges > "$partial"

if [[ ! -s "$partial" ]]; then
  echo "Database backup is empty" >&2
  exit 1
fi

mv "$partial" "$output"
trap - EXIT
echo "$output"
