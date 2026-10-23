#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
# shellcheck source=lib-compose.sh
. "$ROOT/deploy/scripts/lib-compose.sh"

if [[ $# -ne 1 ]]; then
  echo "usage: rollback.sh <previous-release-manifest.json>" >&2
  exit 2
fi

ENV_FILE="${ENV_FILE:-$ROOT/.env}"
WAIT_TIMEOUT="${WAIT_TIMEOUT:-600}"
target_manifest="$1"
if [[ ! -f "$ENV_FILE" || ! -f "$target_manifest" ]]; then
  echo "Missing environment file or rollback manifest" >&2
  exit 2
fi

set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a
case "${DEPLOYMENT_PROFILE:-local}" in
  production|lightweight) ;;
  *)
    echo "DEPLOYMENT_PROFILE must be production or lightweight for rollback.sh" >&2
    exit 2
    ;;
esac

current_manifest="${RELEASE_MANIFEST:-$ROOT/deploy/releases/release-manifest.json}"
release_env="$(mktemp)"
trap 'rm -f "$release_env"' EXIT
python3 "$ROOT/deploy/scripts/validate_release_manifest.py" \
  "$target_manifest" \
  --write-env "$release_env"
set -a
# shellcheck disable=SC1090
. "$release_env"
set +a
export API_IMAGE FRONTEND_IMAGE REVERSE_PROXY_IMAGE POSTGRES_IMAGE REDIS_IMAGE RELEASE_VERSION RELEASE_COMMIT
export RELEASE_ENV_FILE="$release_env"

configure_compose "$ROOT" "$ENV_FILE"
"${COMPOSE[@]}" config --quiet
"${COMPOSE[@]}" pull

database_head="$("${COMPOSE[@]}" exec -T postgres psql \
  -U "${POSTGRES_USER:-english_learn}" \
  -d "${POSTGRES_DB:-english_learn}" \
  -Atc 'SELECT version_num FROM alembic_version ORDER BY version_num' | paste -sd, -)"
if [[ -z "$database_head" ]]; then
  echo "Database has no Alembic revision; refusing application rollback" >&2
  exit 1
fi
target_heads="$("${COMPOSE[@]}" run --rm --no-deps api alembic heads | awk 'NF {print $1}' | sort | paste -sd, -)"
if [[ "$database_head" != "$target_heads" ]]; then
  echo "Rollback blocked: database head (${database_head}) does not match target image heads (${target_heads})" >&2
  echo "Restore the matching pre-deployment database backup through the approved recovery procedure." >&2
  exit 1
fi

app_services=(api worker scheduler frontend reverse-proxy)
if [[ "${ENABLE_DEMO_TUNNEL:-0}" == "1" ]]; then
  app_services+=(cloudflared)
fi

"${COMPOSE[@]}" up -d --no-build --no-deps --force-recreate --wait --wait-timeout "$WAIT_TIMEOUT" \
  "${app_services[@]}"

ENV_FILE="$ENV_FILE" DEPLOYMENT_PROFILE="$DEPLOYMENT_PROFILE" "$ROOT/deploy/scripts/verify-stack.sh"

echo "Application containers rolled back to ${RELEASE_VERSION} (${RELEASE_COMMIT})."
echo "Database migrations were not reversed. Named volumes were preserved."
if [[ -n "${ROLLBACK_RECEIPT_FILE:-}" ]]; then
  python3 "$ROOT/deploy/scripts/write_deployment_receipt.py" \
    --manifest "$target_manifest" \
    --output "$ROLLBACK_RECEIPT_FILE" \
    --profile "$DEPLOYMENT_PROFILE" \
    --edge-bind "${EDGE_BIND_ADDRESS:-127.0.0.1}" \
    --edge-port "${EDGE_PORT:-8080}" \
    --rollback-from "$current_manifest"
fi