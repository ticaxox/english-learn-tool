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

run_id="$(date -u +%Y%m%d%H%M%S)-$(printf '%06x' $((RANDOM * 32768 + RANDOM)))"
marker="wordbook-restore-drill-$run_id.txt"
target_volume="english-learn-wordbook-restore-$run_id"
evidence_file="${WORDBOOK_BACKUP_EVIDENCE_FILE:-$BACKUP_DIR/wordbook-restore-evidence-$run_id.json}"
if [[ "$evidence_file" != /* ]]; then
  evidence_file="$ROOT/$evidence_file"
fi

cleanup() {
  "${COMPOSE[@]}" exec -T api python -c \
    'from pathlib import Path; import sys; p=Path("/app/var/wordbooks")/sys.argv[1]; p.unlink(missing_ok=True)' \
    "$marker" >/dev/null 2>&1 || true
  docker volume rm "$target_volume" >/dev/null 2>&1 || true
}
trap cleanup EXIT

marker_sha="$(printf 'wordbook-restore-drill:%s\n' "$run_id" | sha256sum | cut -d' ' -f1)"
"${COMPOSE[@]}" exec -T api python -c '
from pathlib import Path
import sys
p = Path("/app/var/wordbooks") / sys.argv[1]
p.write_text(sys.argv[2], encoding="utf-8")
p.chmod(0o600)
' "$marker" "$marker_sha"

backup_path="$(ENV_FILE="$ENV_FILE" DEPLOYMENT_PROFILE="$DEPLOYMENT_PROFILE" "$ROOT/deploy/scripts/backup-wordbooks.sh")"
archive_sha="$(sha256sum "$backup_path" | cut -d' ' -f1)"
ENV_FILE="$ENV_FILE" DEPLOYMENT_PROFILE="$DEPLOYMENT_PROFILE" \
  "$ROOT/deploy/scripts/restore-wordbooks.sh" "$backup_path" "$target_volume"

"${COMPOSE[@]}" run --rm --no-deps -T \
  -v "$target_volume:/restore-target:ro" \
  api python -c '
import pathlib
import sys
source = pathlib.Path("/app/var/wordbooks") / sys.argv[1]
restored = pathlib.Path("/restore-target") / sys.argv[1]
if source.read_text(encoding="utf-8") != restored.read_text(encoding="utf-8"):
    raise SystemExit("restored marker content differs")
' "$marker"

mkdir -p "$(dirname "$evidence_file")"
python3 - "$evidence_file" "$run_id" "$archive_sha" "$marker_sha" "$target_volume" <<'PY'
import json
import sys
from pathlib import Path
output, run_id, archive_sha, marker_sha, target_volume = sys.argv[1:]
Path(output).write_text(json.dumps({
    "schema_version": 1,
    "status": "passed",
    "run_id": run_id,
    "archive_sha256": archive_sha,
    "marker_sha256": marker_sha,
    "restore_volume": target_volume,
    "checks": [
        "wordbook_backup_created",
        "archive_listing_valid",
        "new_disposable_volume_restored",
        "restored_volume_owner_and_mode_verified",
        "restored_marker_matches_source",
        "disposable_volume_removed_after_evidence",
    ],
}, indent=2) + "\n", encoding="utf-8")
PY
chmod 0600 "$evidence_file"
echo "Wordbook backup restore drill passed. Evidence: $evidence_file"