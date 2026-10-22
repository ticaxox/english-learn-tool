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

compose=(docker compose --env-file "$ENV_FILE" -f "$ROOT/docker-compose.yml" -f "$ROOT/deploy/compose.prod.yml")
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
