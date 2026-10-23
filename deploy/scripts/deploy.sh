#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
# shellcheck source=lib-compose.sh
. "$ROOT/deploy/scripts/lib-compose.sh"

ENV_FILE="${ENV_FILE:-$ROOT/.env}"
RELEASE_MANIFEST="${RELEASE_MANIFEST:-$ROOT/deploy/releases/release-manifest.json}"
WAIT_TIMEOUT="${WAIT_TIMEOUT:-600}"
MIN_FREE_MEMORY_MB="${MIN_FREE_MEMORY_MB:-128}"
MIN_FREE_DISK_MB="${MIN_FREE_DISK_MB:-2048}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing environment file: $ENV_FILE" >&2
  exit 2
fi
if [[ ! -f "$RELEASE_MANIFEST" ]]; then
  echo "Missing validated release manifest: $RELEASE_MANIFEST" >&2
  exit 2
fi
if grep -Eq '^(POSTGRES_PASSWORD|DATABASE_URL|JWT_SECRET|REFRESH_TOKEN_PEPPER|SECRET_ENCRYPTION_KEY)=.*(replace_with|change_me|example)' "$ENV_FILE"; then
  echo "Refusing deployment with placeholder configuration" >&2
  exit 2
fi

set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a

case "${DEPLOYMENT_PROFILE:-local}" in
  production|lightweight) ;;
  *)
    echo "DEPLOYMENT_PROFILE must be production or lightweight for deploy.sh" >&2
    exit 2
    ;;
esac

edge_port="${EDGE_PORT:-8080}"
if [[ "$edge_port" == "80" || "$edge_port" == "443" || "$edge_port" == "30000" ]]; then
  echo "EDGE_PORT must not occupy the protected existing-service ports (80/443/30000)" >&2
  exit 2
fi
if [[ "${EDGE_BIND_ADDRESS:-127.0.0.1}" != "127.0.0.1" && "${ALLOW_PUBLIC_EDGE:-0}" != "1" ]]; then
  echo "EDGE_BIND_ADDRESS must remain loopback unless ALLOW_PUBLIC_EDGE=1 is explicitly approved" >&2
  exit 2
fi

release_env="$(mktemp)"
trap 'rm -f "$release_env"' EXIT
python3 "$ROOT/deploy/scripts/validate_release_manifest.py" \
  "$RELEASE_MANIFEST" \
  --write-env "$release_env"

set -a
# shellcheck disable=SC1090
. "$release_env"
set +a
export API_IMAGE FRONTEND_IMAGE REVERSE_PROXY_IMAGE POSTGRES_IMAGE REDIS_IMAGE RELEASE_VERSION RELEASE_COMMIT
export RELEASE_ENV_FILE="$release_env"

available_mb="$(awk '/^MemAvailable:/ {print int($2 / 1024)}' /proc/meminfo)"
free_disk_mb="$(df -Pk "$ROOT" | awk 'NR == 2 {print int($4 / 1024)}')"
if [[ "$available_mb" -lt "$MIN_FREE_MEMORY_MB" ]]; then
  echo "Insufficient available memory: ${available_mb} MiB" >&2
  exit 1
fi
if [[ "$free_disk_mb" -lt "$MIN_FREE_DISK_MB" ]]; then
  echo "Insufficient disk space: ${free_disk_mb} MiB" >&2
  exit 1
fi
if [[ "${DEPLOYMENT_PROFILE}" == "lightweight" ]]; then
  memory_budget="${LIGHTWEIGHT_MEMORY_BUDGET_MB:?LIGHTWEIGHT_MEMORY_BUDGET_MB is required}"
  if [[ "$available_mb" -lt $((memory_budget + MIN_FREE_MEMORY_MB)) ]]; then
    echo "Lightweight profile budget (${memory_budget} MiB) plus reserve (${MIN_FREE_MEMORY_MB} MiB) exceeds available memory (${available_mb} MiB)" >&2
    exit 1
  fi
fi

configure_compose "$ROOT" "$ENV_FILE"
"${COMPOSE[@]}" config --quiet

app_services=(api worker scheduler frontend reverse-proxy)
if [[ "${ENABLE_DEMO_TUNNEL:-0}" == "1" ]]; then
  app_services+=(cloudflared)
fi

existing_pg="$("${COMPOSE[@]}" ps -q postgres || true)"
if [[ -n "$existing_pg" ]] && [[ "$(docker inspect --format '{{.State.Running}}' "$existing_pg")" == "true" ]]; then
  echo "Creating pre-migration database backup"
  ENV_FILE="$ENV_FILE" DEPLOYMENT_PROFILE="$DEPLOYMENT_PROFILE" "$ROOT/deploy/scripts/backup-db.sh" >/dev/null
  echo "Backup completed"
else
  echo "No running PostgreSQL container found; treating this as an initial deployment"
fi

"${COMPOSE[@]}" pull
"${COMPOSE[@]}" up -d --wait --wait-timeout "$WAIT_TIMEOUT" postgres redis
"${COMPOSE[@]}" run --rm --no-deps migrate
"${COMPOSE[@]}" up -d --no-build --wait --wait-timeout "$WAIT_TIMEOUT" "${app_services[@]}"

ENV_FILE="$ENV_FILE" DEPLOYMENT_PROFILE="$DEPLOYMENT_PROFILE" "$ROOT/deploy/scripts/verify-stack.sh"
ENV_FILE="$ENV_FILE" DEPLOYMENT_PROFILE="$DEPLOYMENT_PROFILE" "$ROOT/deploy/scripts/verify-database.sh"

if [[ -n "${DEPLOYMENT_RECEIPT_FILE:-}" ]]; then
  python3 "$ROOT/deploy/scripts/write_deployment_receipt.py" \
    --manifest "$RELEASE_MANIFEST" \
    --output "$DEPLOYMENT_RECEIPT_FILE" \
    --profile "$DEPLOYMENT_PROFILE" \
    --edge-bind "${EDGE_BIND_ADDRESS:-127.0.0.1}" \
    --edge-port "$edge_port"
fi

echo "Deployment verified: ${RELEASE_VERSION} (${RELEASE_COMMIT}) with digest-pinned images."