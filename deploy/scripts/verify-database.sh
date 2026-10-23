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

mapfile -t expected_heads < <("${COMPOSE[@]}" exec -T api alembic heads | awk 'NF {print $1}' | sort)
mapfile -t current_heads < <("${COMPOSE[@]}" exec -T api alembic current | awk 'NF {print $1}' | sort)

if [[ "${#expected_heads[@]}" -eq 0 ]]; then
  echo "No Alembic head was reported" >&2
  exit 1
fi

if [[ "$(printf '%s\n' "${expected_heads[@]}")" != "$(printf '%s\n' "${current_heads[@]}")" ]]; then
  echo "Database revision does not match Alembic head" >&2
  printf 'expected: %s\n' "${expected_heads[*]}" >&2
  printf 'current:  %s\n' "${current_heads[*]}" >&2
  exit 1
fi

metadata_table="$("${COMPOSE[@]}" exec -T postgres psql \
  -U "${POSTGRES_USER:-english_learn}" \
  -d "${POSTGRES_DB:-english_learn}" \
  -v ON_ERROR_STOP=1 \
  -tAc "SELECT to_regclass('public.system_metadata') IS NOT NULL;" | tr -d '\r' | xargs)"

if [[ "$metadata_table" != "t" ]]; then
  echo "Baseline system_metadata table is absent after migration" >&2
  exit 1
fi

echo "Alembic head and baseline schema verified: ${current_heads[*]}"