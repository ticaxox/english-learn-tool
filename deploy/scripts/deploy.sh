#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

ENV_FILE="${ENV_FILE:-$ROOT/.env}"
WAIT_TIMEOUT="${WAIT_TIMEOUT:-600}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing environment file: $ENV_FILE" >&2
  exit 2
fi
if grep -Eq '^(GHCR_OWNER|IMAGE_TAG|POSTGRES_PASSWORD|DATABASE_URL|JWT_SECRET|REFRESH_TOKEN_PEPPER|SECRET_ENCRYPTION_KEY)=.*(replace_with|change_me|example)' "$ENV_FILE"; then
  echo "Refusing deployment with placeholder configuration" >&2
  exit 2
fi

set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a

: "${GHCR_OWNER:?GHCR_OWNER is required}"
: "${IMAGE_TAG:?IMAGE_TAG is required}"

if [[ ! "$IMAGE_TAG" =~ ^[0-9a-f]{40}$ && ! "$IMAGE_TAG" =~ ^v[0-9]+\.[0-9]+\.[0-9]+([-.][A-Za-z0-9.]+)?$ ]]; then
  echo "IMAGE_TAG must be a full 40-character Git SHA or semantic version tag" >&2
  exit 2
fi

export API_IMAGE="ghcr.io/${GHCR_OWNER}/english-learn-api:${IMAGE_TAG}"
export FRONTEND_IMAGE="ghcr.io/${GHCR_OWNER}/english-learn-frontend:${IMAGE_TAG}"
export REVERSE_PROXY_IMAGE="ghcr.io/${GHCR_OWNER}/english-learn-reverse-proxy:${IMAGE_TAG}"

compose=(docker compose --env-file "$ENV_FILE" -f "$ROOT/docker-compose.yml" -f "$ROOT/deploy/compose.prod.yml")
"${compose[@]}" config --quiet

existing_pg="$("${compose[@]}" ps -q postgres || true)"
if [[ -n "$existing_pg" ]] && [[ "$(docker inspect --format '{{.State.Running}}' "$existing_pg")" == "true" ]]; then
  echo "Creating pre-migration database backup"
  ENV_FILE="$ENV_FILE" "$ROOT/deploy/scripts/backup-db.sh" >/dev/null
  echo "Backup completed"
else
  echo "No running PostgreSQL container found; treating this as an initial deployment"
fi

"${compose[@]}" pull
"${compose[@]}" up -d --wait --wait-timeout "$WAIT_TIMEOUT" postgres redis
"${compose[@]}" run --rm migrate
"${compose[@]}" up -d --no-build --wait --wait-timeout "$WAIT_TIMEOUT" api worker scheduler frontend reverse-proxy

ENV_FILE="$ENV_FILE" "$ROOT/deploy/scripts/verify-stack.sh"
ENV_FILE="$ENV_FILE" "$ROOT/deploy/scripts/verify-database.sh"
