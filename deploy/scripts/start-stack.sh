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

compose=(docker compose --env-file "$ENV_FILE" -f "$ROOT/docker-compose.yml")
"${compose[@]}" config --quiet
"${compose[@]}" build --pull
"${compose[@]}" up -d --wait --wait-timeout "$WAIT_TIMEOUT" postgres redis
"${compose[@]}" run --rm migrate
"${compose[@]}" up -d --wait --wait-timeout "$WAIT_TIMEOUT" api worker scheduler frontend reverse-proxy

ENV_FILE="$ENV_FILE" "$ROOT/deploy/scripts/verify-stack.sh"
ENV_FILE="$ENV_FILE" "$ROOT/deploy/scripts/verify-database.sh"
