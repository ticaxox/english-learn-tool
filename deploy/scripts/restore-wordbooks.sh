#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
# shellcheck source=lib-compose.sh
. "$ROOT/deploy/scripts/lib-compose.sh"

if [[ $# -ne 2 ]]; then
  echo "usage: restore-wordbooks.sh <wordbooks-*.tar.gz> <english-learn-wordbook-restore-*>" >&2
  exit 2
fi
archive="$1"
target_volume="$2"
[[ -f "$archive" ]] || { echo "Missing archive: $archive" >&2; exit 2; }
[[ "$target_volume" =~ ^english-learn-wordbook-restore-[0-9a-z-]+$ ]] \
  || { echo "Restore volume must use the disposable english-learn-wordbook-restore-* prefix" >&2; exit 2; }
if docker volume inspect "$target_volume" >/dev/null 2>&1; then
  echo "Refusing to overwrite existing volume: $target_volume" >&2
  exit 1
fi

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
"${COMPOSE[@]}" config --quiet
: "${API_IMAGE:?API_IMAGE is required for wordbook restore}"
tar -tzf "$archive" >/dev/null
docker volume create "$target_volume" >/dev/null

cleanup_on_error() {
  docker volume rm "$target_volume" >/dev/null 2>&1 || true
}
trap cleanup_on_error ERR

# Narrow maintenance helper: no network, read-only rootfs, only ownership-related caps.
docker run --rm -i --network none --read-only --tmpfs /tmp \
  --user 0:0 --cap-drop ALL \
  --cap-add CHOWN --cap-add DAC_OVERRIDE --cap-add FOWNER \
  --security-opt no-new-privileges:true \
  -v "$target_volume:/restore-target" \
  "$API_IMAGE" \
  tar --numeric-owner --same-owner -xzf - -C /restore-target < "$archive"

docker run --rm --network none --read-only \
  --user 10001:10001 --cap-drop ALL \
  --security-opt no-new-privileges:true \
  -v "$target_volume:/restore-target:ro" \
  "$API_IMAGE" python -c '
from pathlib import Path
root = Path("/restore-target")
stat = root.stat()
if stat.st_uid != 10001 or stat.st_gid != 10001:
    raise SystemExit(f"unexpected restore volume owner: {stat.st_uid}:{stat.st_gid}")
if stat.st_mode & 0o777 != 0o750:
    raise SystemExit(f"unexpected restore volume mode: {stat.st_mode & 0o777:o}")
'

trap - ERR
echo "Restored $archive to disposable volume $target_volume"