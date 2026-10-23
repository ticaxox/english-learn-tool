#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
# shellcheck source=lib-compose.sh
. "$ROOT/deploy/scripts/lib-compose.sh"

ENV_FILE="${ENV_FILE:-$ROOT/.env}"
EVIDENCE_FILE="${EVIDENCE_FILE:-$ROOT/deploy/backups/wordbook-storage-evidence.json}"
WAIT_TIMEOUT="${WAIT_TIMEOUT:-300}"
STORAGE_DIR="/app/var/wordbooks"
APP_SERVICES=(api worker scheduler)
STARTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

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
BASE_URL="http://127.0.0.1:${EDGE_PORT:-8080}"
COMMIT_SHA="${COMMIT_SHA:-$(git rev-parse HEAD 2>/dev/null || printf unknown)}"
COMPOSE_PROJECT="${COMPOSE_PROJECT_NAME:-unknown}"
RUN_STAMP="$(date -u +%Y%m%dT%H%M%SZ)-$$-${RANDOM}"
RUN_HEX="$(printf '%s' "$RUN_STAMP" | sha256sum | cut -c1-32)"
API_FILE="preview-${RUN_HEX}.txt"
WORKER_FILE="export-${RUN_HEX}.txt"
MARKER_FILE="wordbook-${RUN_HEX}.txt"
API_TOKEN="api-$(printf 'api:%s' "$RUN_STAMP" | sha256sum | cut -d' ' -f1)"
WORKER_TOKEN="worker-$(printf 'worker:%s' "$RUN_STAMP" | sha256sum | cut -d' ' -f1)"
MARKER_TOKEN="marker-$(printf 'marker:%s' "$RUN_STAMP" | sha256sum | cut -d' ' -f1)"
MARKER_APPEND="-append-$(printf 'append:%s' "$RUN_STAMP" | sha256sum | cut -d' ' -f1)"
MARKER_BYTES="${MARKER_TOKEN}${MARKER_APPEND}"
MARKER_SHA256="$(printf '%s' "$MARKER_BYTES" | sha256sum | cut -d' ' -f1)"
declare -A SERVICE_UID=()
declare -A SERVICE_GID=()
declare -A SERVICE_SOURCE=()
STATIC_PROBES=()
TMP_RESPONSE="$(mktemp)"

die() {
  echo "ERROR: $*" >&2
  exit 1
}

container_id() {
  "${COMPOSE[@]}" ps -q "$1" | head -n 1
}

service_python() {
  local service="$1"
  local code="$2"
  shift 2
  "${COMPOSE[@]}" exec -T "$service" python -c "$code" "$@"
}

delete_test_files() {
  local service
  for service in "${APP_SERVICES[@]}"; do
    service_python "$service" \
      'from pathlib import Path
import sys
root = Path(sys.argv[1])
for key in sys.argv[2:]:
    path = root / key
    if path.is_file() or path.is_symlink():
        path.unlink()
' "$STORAGE_DIR" "$API_FILE" "$WORKER_FILE" "$MARKER_FILE"
  done
}

cleanup_on_exit() {
  delete_test_files >/dev/null 2>&1 || true
  rm -f "$TMP_RESPONSE"
}

trap cleanup_on_exit EXIT

assert_files_absent() {
  local service="$1"
  service_python "$service" \
    'from pathlib import Path
import sys
root = Path(sys.argv[1])
if any((root / key).exists() for key in sys.argv[2:]):
    raise SystemExit("one or more smoke-test files remain")
' "$STORAGE_DIR" "$API_FILE" "$WORKER_FILE" "$MARKER_FILE"
}

for service in "${APP_SERVICES[@]}"; do
  container="$(container_id "$service")"
  [[ -n "$container" ]] || die "$service has no running container"

  SERVICE_UID["$service"]="$(
    "${COMPOSE[@]}" exec -T "$service" id -u | tr -d '\r'
  )"
  SERVICE_GID["$service"]="$(
    "${COMPOSE[@]}" exec -T "$service" id -g | tr -d '\r'
  )"
  [[ "${SERVICE_UID[$service]}" == "10001" ]] \
    || die "$service runs as UID ${SERVICE_UID[$service]}, expected 10001"
  [[ "${SERVICE_GID[$service]}" == "10001" ]] \
    || die "$service runs as GID ${SERVICE_GID[$service]}, expected 10001"

  storage_env="$(
    "${COMPOSE[@]}" exec -T "$service" printenv WORDBOOK_STORAGE_DIR | tr -d '\r'
  )"
  [[ "$storage_env" == "$STORAGE_DIR" ]] \
    || die "$service has WORDBOOK_STORAGE_DIR=$storage_env"

  directory_metadata="$(
    service_python "$service" \
      'import os
import stat
import sys
value = os.stat(sys.argv[1])
print(
    f"{value.st_uid}:{value.st_gid}:"
    f"{stat.S_IMODE(value.st_mode):04o}:"
    f"{str(stat.S_ISDIR(value.st_mode)).lower()}"
)
' "$STORAGE_DIR"
  )"
  [[ "$directory_metadata" == "10001:10001:0750:true" ]] \
    || die "$service storage metadata is $directory_metadata, expected 10001:10001:0750:true"

  mount_record="$(
    docker inspect --format \
      '{{range .Mounts}}{{if eq .Destination "/app/var/wordbooks"}}{{.Type}}|{{.Name}}|{{.Destination}}|{{.RW}}{{end}}{{end}}' \
      "$container"
  )"
  [[ "$mount_record" =~ ^volume\|([^|]+)\|/app/var/wordbooks\|true$ ]] \
    || die "$service has an unexpected wordbook mount: $mount_record"
  mount_source="${BASH_REMATCH[1]}"
  SERVICE_SOURCE["$service"]="$mount_source"
  if [[ -n "${SERVICE_SOURCE[api]:-}" ]]; then
    [[ "$mount_source" == "${SERVICE_SOURCE[api]}" ]] \
      || die "wordbook volume sources differ across application services"
  fi

  readonly_rootfs="$(docker inspect --format '{{.HostConfig.ReadonlyRootfs}}' "$container")"
  cap_drop="$(docker inspect --format '{{json .HostConfig.CapDrop}}' "$container")"
  security_opt="$(docker inspect --format '{{json .HostConfig.SecurityOpt}}' "$container")"
  port_bindings="$(docker inspect --format '{{json .HostConfig.PortBindings}}' "$container")"
  [[ "$readonly_rootfs" == "true" ]] || die "$service root filesystem is writable"
  [[ "$cap_drop" == *'"ALL"'* ]] || die "$service does not drop all capabilities"
  [[ "$security_opt" == *'no-new-privileges:true'* ]] \
    || die "$service does not enable no-new-privileges"
  [[ "$port_bindings" == "{}" || "$port_bindings" == "null" ]] \
    || die "$service publishes a host port"

  if service_python "$service" \
    'from pathlib import Path
import sys
Path(sys.argv[1]).write_text("unexpected-write", encoding="utf-8")
' "/app/.wordbook-storage-probe-$RUN_HEX"; then
    die "$service can write outside the wordbook volume"
  fi
done

[[ "${SERVICE_SOURCE[api]}" == "${SERVICE_SOURCE[worker]}" ]] \
  || die "api and worker do not share the same wordbook volume"
[[ "${SERVICE_SOURCE[api]}" == "${SERVICE_SOURCE[scheduler]}" ]] \
  || die "api and scheduler do not share the same wordbook volume"
SHARED_VOLUME_SOURCE="${SERVICE_SOURCE[api]}"

service_python api \
  'from pathlib import Path
import os
import sys
path = Path(sys.argv[1]) / sys.argv[2]
descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(descriptor, "wb") as handle:
    handle.write(sys.argv[3].encode())
if (path.stat().st_mode & 0o777) != 0o600:
    raise SystemExit("storage file mode is not 0600")
' "$STORAGE_DIR" "$API_FILE" "$API_TOKEN"

service_python worker \
  'from pathlib import Path
import os
import sys
root = Path(sys.argv[1])
if (root / sys.argv[2]).read_bytes() != sys.argv[4].encode():
    raise SystemExit("worker could not read the API file")
path = root / sys.argv[3]
descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(descriptor, "wb") as handle:
    handle.write(sys.argv[5].encode())
' "$STORAGE_DIR" "$API_FILE" "$WORKER_FILE" "$API_TOKEN" "$WORKER_TOKEN"

service_python scheduler \
  'from pathlib import Path
import os
import sys
root = Path(sys.argv[1])
if (root / sys.argv[2]).read_bytes() != sys.argv[4].encode():
    raise SystemExit("scheduler could not read the worker file")
path = root / sys.argv[3]
descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(descriptor, "wb") as handle:
    handle.write(sys.argv[5].encode())
with path.open("ab") as handle:
    handle.write(sys.argv[6].encode())
if path.read_bytes() != (sys.argv[5] + sys.argv[6]).encode():
    raise SystemExit("scheduler append verification failed")
(root / sys.argv[2]).unlink()
if (root / sys.argv[2]).exists():
    raise SystemExit("scheduler did not delete the worker file")
' "$STORAGE_DIR" "$WORKER_FILE" "$MARKER_FILE" "$WORKER_TOKEN" "$MARKER_TOKEN" "$MARKER_APPEND"

for service in "${APP_SERVICES[@]}"; do
  service_python "$service" \
    'from pathlib import Path
import sys
if (Path(sys.argv[1]) / sys.argv[2]).exists():
    raise SystemExit("scheduler deletion is not visible in this service")
' "$STORAGE_DIR" "$WORKER_FILE"
done

"${COMPOSE[@]}" restart api worker scheduler
"${COMPOSE[@]}" up -d --wait --wait-timeout "$WAIT_TIMEOUT" api worker scheduler

for service in "${APP_SERVICES[@]}"; do
  service_python "$service" \
    'from pathlib import Path
import sys
if (Path(sys.argv[1]) / sys.argv[2]).read_bytes() != sys.argv[3].encode():
    raise SystemExit("persisted marker content changed after restart")
' "$STORAGE_DIR" "$MARKER_FILE" "$MARKER_BYTES"
done

probe_path() {
  local path="$1"
  local status
  local response_sha256
  status="$(curl -sS -o "$TMP_RESPONSE" -w '%{http_code}' "${BASE_URL}${path}" 2>/dev/null || true)"
  [[ -n "$status" ]] || status="000"
  response_sha256="$(sha256sum "$TMP_RESPONSE" | cut -d' ' -f1)"
  [[ "$response_sha256" != "$MARKER_SHA256" ]] \
    || die "reverse proxy exposes the private test marker at $path"
  STATIC_PROBES+=(
    "{\"path\":\"$path\",\"http_status\":\"$status\",\"marker_hash_exposed\":false}"
  )
}

probe_path "/var/wordbooks/$MARKER_FILE"
probe_path "/wordbooks/$MARKER_FILE"
probe_path "/static/wordbooks/$MARKER_FILE"
probe_path "/exports/$MARKER_FILE"
probe_path "/api/var/wordbooks/$MARKER_FILE"

delete_test_files
for service in "${APP_SERVICES[@]}"; do
  assert_files_absent "$service"
done

mkdir -p "$(dirname "$EVIDENCE_FILE")"
IFS=','
STATIC_PROBES_JSON="${STATIC_PROBES[*]}"
unset IFS
FINISHED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

cat > "$EVIDENCE_FILE" <<JSON
{
  "schema_version": 1,
  "status": "passed",
  "started_at_utc": "$STARTED_AT",
  "finished_at_utc": "$FINISHED_AT",
  "commit_sha": "$COMMIT_SHA",
  "compose_project": "$COMPOSE_PROJECT",
  "storage": {
    "target": "$STORAGE_DIR",
    "volume_type": "named",
    "shared_volume_source": "$SHARED_VOLUME_SOURCE",
    "owner_uid": 10001,
    "owner_gid": 10001,
    "mode": "0750",
    "tracked_marker_key": "$MARKER_FILE",
    "tracked_marker_sha256": "$MARKER_SHA256"
  },
  "services": {
    "api": {
      "uid": ${SERVICE_UID[api]},
      "gid": ${SERVICE_GID[api]},
      "storage_path": "$STORAGE_DIR",
      "volume_source": "${SERVICE_SOURCE[api]}",
      "read_only_rootfs": true,
      "cap_drop_all": true,
      "no_new_privileges": true,
      "rootfs_outside_storage_write": "denied"
    },
    "worker": {
      "uid": ${SERVICE_UID[worker]},
      "gid": ${SERVICE_GID[worker]},
      "storage_path": "$STORAGE_DIR",
      "volume_source": "${SERVICE_SOURCE[worker]}",
      "read_only_rootfs": true,
      "cap_drop_all": true,
      "no_new_privileges": true,
      "rootfs_outside_storage_write": "denied"
    },
    "scheduler": {
      "uid": ${SERVICE_UID[scheduler]},
      "gid": ${SERVICE_GID[scheduler]},
      "storage_path": "$STORAGE_DIR",
      "volume_source": "${SERVICE_SOURCE[scheduler]}",
      "read_only_rootfs": true,
      "cap_drop_all": true,
      "no_new_privileges": true,
      "rootfs_outside_storage_write": "denied"
    }
  },
  "checks": [
    {"name": "api_create_read_0600", "status": "passed"},
    {"name": "worker_read_api_and_create", "status": "passed"},
    {"name": "scheduler_read_worker_write_append_marker_delete_worker", "status": "passed"},
    {"name": "delete_visible_across_services", "status": "passed"},
    {"name": "restart_persistence", "status": "passed"},
    {"name": "read_only_rootfs_outside_volume", "status": "passed"},
    {"name": "non_root_uid_gid_10001", "status": "passed"},
    {"name": "directory_owner_and_mode_10001_0750", "status": "passed"},
    {"name": "same_named_volume_source", "status": "passed"},
    {"name": "no_static_reverse_proxy_exposure", "status": "passed"},
    {"name": "smoke_files_removed", "status": "passed"}
  ],
  "commands": [
    "docker compose config --format json",
    "docker compose exec -T <service> python -c <file-operation>",
    "docker compose restart api worker scheduler",
    "docker compose up -d --wait api worker scheduler"
  ],
  "restart_persistence": {
    "before_restart": "marker present in api, worker and scheduler namespace",
    "after_restart": "same marker bytes readable from api, worker and scheduler",
    "worker_file": "deleted by scheduler before restart"
  },
  "static_path_probes": [${STATIC_PROBES_JSON}],
  "cleanup": {
    "test_files_removed": true,
    "down_v_executed": false
  },
  "artifact_policy": "metadata-only; no uploads, exports, tokens or real member data"
}
JSON

python3 -m json.tool "$EVIDENCE_FILE" >/dev/null
echo "Cross-container wordbook storage verification passed."
echo "Evidence: $EVIDENCE_FILE"
