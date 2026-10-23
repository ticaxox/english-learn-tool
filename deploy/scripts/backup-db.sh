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

BACKUP_DIR="${BACKUP_DIR:-$ROOT/deploy/backups}"
if [[ "$BACKUP_DIR" != /* ]]; then
  BACKUP_DIR="$ROOT/$BACKUP_DIR"
fi
install -d -m 0700 "$BACKUP_DIR"
umask 077

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
output="$BACKUP_DIR/postgres-$timestamp.dump"
partial="$output.partial"
trap 'rm -f "$partial"' EXIT

"${COMPOSE[@]}" config --quiet
"${COMPOSE[@]}" exec -T postgres pg_dump \
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
chmod 0600 "$output"
trap - EXIT
sha256sum "$output" > "$output.sha256"
chmod 0600 "$output.sha256"

if [[ "${ENABLE_BACKUP_RETENTION:-0}" == "1" ]]; then
  retention_days="${BACKUP_RETENTION_DAYS:-7}"
  if [[ ! "$retention_days" =~ ^[1-9][0-9]*$ ]]; then
    echo "BACKUP_RETENTION_DAYS must be a positive integer" >&2
    exit 2
  fi
  find "$BACKUP_DIR" -maxdepth 1 -type f \
    \( -name 'postgres-*.dump' -o -name 'postgres-*.dump.sha256' \) \
    -mtime "+$retention_days" -delete
fi

echo "$output"