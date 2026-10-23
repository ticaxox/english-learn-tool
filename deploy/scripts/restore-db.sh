#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
# shellcheck source=lib-compose.sh
. "$ROOT/deploy/scripts/lib-compose.sh"

if [[ $# -ne 2 ]]; then
  echo "usage: restore-db.sh <postgres-*.dump> <english_learn_restore_*>" >&2
  exit 2
fi
archive="$1"
target_db="$2"
[[ -f "$archive" ]] || { echo "Missing backup archive: $archive" >&2; exit 2; }
[[ "$target_db" =~ ^english_learn_restore_[a-z0-9_]+$ ]] \
  || { echo "Target database must use the disposable english_learn_restore_* prefix" >&2; exit 2; }

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
[[ "$target_db" != "${POSTGRES_DB:-english_learn}" ]] \
  || { echo "Refusing to restore over the primary database" >&2; exit 2; }

psql_admin=("${COMPOSE[@]}" exec -T postgres psql -U "${POSTGRES_USER:-english_learn}" -d postgres -v ON_ERROR_STOP=1)
exists="$("${psql_admin[@]}" -Atc "SELECT 1 FROM pg_database WHERE datname = '$target_db'")"
if [[ -n "$exists" ]]; then
  if [[ "${DROP_RESTORE_DB:-0}" != "1" ]]; then
    echo "Restore database already exists: $target_db (set DROP_RESTORE_DB=1 to recreate the disposable target)" >&2
    exit 1
  fi
  "${psql_admin[@]}" -c "DROP DATABASE \"$target_db\" WITH (FORCE);" >/dev/null
fi
"${psql_admin[@]}" -c "CREATE DATABASE \"$target_db\";" >/dev/null
"${COMPOSE[@]}" exec -T postgres pg_restore \
  -U "${POSTGRES_USER:-english_learn}" \
  -d "$target_db" \
  --no-owner \
  --no-privileges < "$archive"
echo "Restored database backup to disposable database $target_db"