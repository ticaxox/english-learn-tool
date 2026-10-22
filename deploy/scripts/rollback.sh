#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

if [[ $# -ne 1 ]]; then
  echo "usage: rollback.sh <previous-full-sha-or-semver-tag>" >&2
  exit 2
fi

ENV_FILE="${ENV_FILE:-$ROOT/.env}"
WAIT_TIMEOUT="${WAIT_TIMEOUT:-600}"
if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing environment file: $ENV_FILE" >&2
  exit 2
fi

set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a

: "${GHCR_OWNER:?GHCR_OWNER is required}"
target_tag="$1"
if [[ ! "$target_tag" =~ ^[0-9a-f]{40}$ && ! "$target_tag" =~ ^v[0-9]+\.[0-9]+\.[0-9]+([-.][A-Za-z0-9.]+)?$ ]]; then
  echo "Rollback target must be a full 40-character Git SHA or semantic version tag" >&2
  exit 2
fi

export API_IMAGE="ghcr.io/${GHCR_OWNER}/english-learn-api:${target_tag}"
export FRONTEND_IMAGE="ghcr.io/${GHCR_OWNER}/english-learn-frontend:${target_tag}"
export REVERSE_PROXY_IMAGE="ghcr.io/${GHCR_OWNER}/english-learn-reverse-proxy:${target_tag}"

compose=(docker compose --env-file "$ENV_FILE" -f "$ROOT/docker-compose.yml" -f "$ROOT/deploy/compose.prod.yml")
"${compose[@]}" config --quiet
"${compose[@]}" pull api worker scheduler frontend reverse-proxy
"${compose[@]}" up -d --no-build --no-deps --force-recreate --wait --wait-timeout "$WAIT_TIMEOUT" \
  api worker scheduler frontend reverse-proxy

ENV_FILE="$ENV_FILE" "$ROOT/deploy/scripts/verify-stack.sh"

echo "Application containers rolled back to $target_tag."
echo "Database migrations were not reversed. If the restored code is incompatible with the current schema, stop and restore the matching pre-deployment database backup through an approved manual procedure."
