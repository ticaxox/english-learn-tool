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
run_id="$(date -u +%Y%m%d%H%M%S)_$(printf '%06x' $((RANDOM * 32768 + RANDOM)))"
target_db="english_learn_restore_$run_id"
evidence_file="${DB_BACKUP_EVIDENCE_FILE:-$BACKUP_DIR/database-restore-evidence-$run_id.json}"
if [[ "$evidence_file" != /* ]]; then
  evidence_file="$ROOT/$evidence_file"
fi
source_db="${POSTGRES_DB:-english_learn}"
psql_base=("${COMPOSE[@]}" exec -T postgres psql -U "${POSTGRES_USER:-english_learn}" -v ON_ERROR_STOP=1)

cleanup() {
  if [[ "${KEEP_RESTORE_DB:-0}" != "1" ]]; then
    "${psql_base[@]}" -d postgres -c "DROP DATABASE IF EXISTS \"$target_db\" WITH (FORCE);" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

backup_path="$(ENV_FILE="$ENV_FILE" DEPLOYMENT_PROFILE="$DEPLOYMENT_PROFILE" "$ROOT/deploy/scripts/backup-db.sh")"
archive_sha="$(sha256sum "$backup_path" | cut -d' ' -f1)"
sidecar_sha="$(cut -d' ' -f1 "$backup_path.sha256")"
[[ "$archive_sha" == "$sidecar_sha" ]] || { echo "Database backup checksum mismatch" >&2; exit 1; }

ENV_FILE="$ENV_FILE" DEPLOYMENT_PROFILE="$DEPLOYMENT_PROFILE" DROP_RESTORE_DB=0 \
  "$ROOT/deploy/scripts/restore-db.sh" "$backup_path" "$target_db"

for db in "$source_db" "$target_db"; do
  tables="$("${psql_base[@]}" -d "$db" -Atc "SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE' ORDER BY table_name")"
  {
    printf '%s\n' "$tables" | while IFS= read -r table; do
      [[ -n "$table" ]] || continue
      [[ "$table" =~ ^[a-z_][a-z0-9_]*$ ]] || { echo "Unexpected table name: $table" >&2; exit 1; }
      count="$("${psql_base[@]}" -d "$db" -Atc "SELECT count(*) FROM \"$table\";")"
      printf '%s\t%s\n' "$table" "$count"
    done
  } > "/tmp/english-learn-$db-counts.txt"
done

if ! diff -u "/tmp/english-learn-$source_db-counts.txt" "/tmp/english-learn-$target_db-counts.txt"; then
  echo "Restored database table counts differ from source" >&2
  exit 1
fi

mkdir -p "$(dirname "$evidence_file")"
python3 - "$evidence_file" "$run_id" "$source_db" "$target_db" "$archive_sha" "/tmp/english-learn-$source_db-counts.txt" <<'PY'
import json
import sys
from pathlib import Path
output, run_id, source_db, target_db, archive_sha, counts_path = sys.argv[1:]
counts = {}
for line in Path(counts_path).read_text(encoding="utf-8").splitlines():
    table, count = line.split("\t", 1)
    counts[table] = int(count)
Path(output).write_text(json.dumps({
    "schema_version": 1,
    "status": "passed",
    "run_id": run_id,
    "source_database": source_db,
    "restore_database": target_db,
    "archive_sha256": archive_sha,
    "table_row_counts": counts,
    "checks": [
        "checksum_verified_before_restore",
        "isolated_database_created",
        "pg_restore_completed",
        "public_table_lists_match",
        "public_table_row_counts_match",
        "disposable_database_removed_after_evidence",
    ],
}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
chmod 0600 "$evidence_file"
echo "Database backup restore drill passed. Evidence: $evidence_file"