#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

ENV_FILE="${ENV_FILE:-$ROOT/.env}"
WAIT_TIMEOUT="${WAIT_TIMEOUT:-300}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing environment file: $ENV_FILE" >&2
  echo "Copy .env.example to .env and replace placeholders before deployment." >&2
  exit 2
fi

if [[ "${ALLOW_INSECURE_EXAMPLE_ENV:-0}" != "1" ]] \
  && grep -Eq '^(POSTGRES_PASSWORD|JWT_SECRET|REFRESH_TOKEN_PEPPER|SECRET_ENCRYPTION_KEY)=.*(replace_with|change_me|example)' "$ENV_FILE"; then
  echo "Refusing to start with placeholder secrets. Replace them or set ALLOW_INSECURE_EXAMPLE_ENV=1 for disposable CI." >&2
  exit 2
fi

set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a
case "${DEPLOYMENT_PROFILE:-local}" in
  local)
    files=(-f "$ROOT/docker-compose.yml")
    ;;
  local-lightweight)
    files=(-f "$ROOT/docker-compose.yml" -f "$ROOT/deploy/compose.lightweight.yml")
    ;;
  *)
    echo "start-stack.sh supports only local and local-lightweight profiles" >&2
    exit 2
    ;;
esac
if [[ "${ENABLE_DEMO_TUNNEL:-0}" == "1" ]]; then
  files+=(-f "$ROOT/deploy/compose.tunnel.yml")
fi
compose=(docker compose --env-file "$ENV_FILE" "${files[@]}")

"${compose[@]}" config --quiet
"${compose[@]}" build --pull
"${compose[@]}" up -d --wait --wait-timeout "$WAIT_TIMEOUT" postgres redis
"${compose[@]}" run --rm migrate
app_services=(api worker scheduler frontend reverse-proxy)
if [[ "${ENABLE_DEMO_TUNNEL:-0}" == "1" ]]; then
  app_services+=(cloudflared)
fi

"${compose[@]}" up -d --wait --wait-timeout "$WAIT_TIMEOUT" "${app_services[@]}"

ENV_FILE="$ENV_FILE" DEPLOYMENT_PROFILE="$DEPLOYMENT_PROFILE" "$ROOT/deploy/scripts/verify-stack.sh"
ENV_FILE="$ENV_FILE" DEPLOYMENT_PROFILE="$DEPLOYMENT_PROFILE" "$ROOT/deploy/scripts/verify-database.sh"