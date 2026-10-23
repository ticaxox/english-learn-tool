#!/usr/bin/env bash
# Shared Compose profile resolution for deployment scripts.
configure_compose() {
  local root="$1"
  local env_file="$2"
  local profile="${DEPLOYMENT_PROFILE:-local}"
  local files=(-f "$root/docker-compose.yml")

  case "$profile" in
    local)
      ;;
    local-lightweight)
      files+=(-f "$root/deploy/compose.lightweight.yml")
      ;;
    production)
      files+=(-f "$root/deploy/compose.prod.yml")
      ;;
    lightweight)
      files+=(-f "$root/deploy/compose.prod.yml" -f "$root/deploy/compose.lightweight.yml")
      ;;
    *)
      echo "Unsupported DEPLOYMENT_PROFILE: $profile" >&2
      return 2
      ;;
  esac

  if [[ "${ENABLE_DEMO_TUNNEL:-0}" == "1" ]]; then
    files+=(-f "$root/deploy/compose.tunnel.yml")
  fi
  # shellcheck disable=SC2034
  COMPOSE=(docker compose --env-file "$env_file" "${files[@]}")
}

load_release_env() {
  if [[ -n "${RELEASE_ENV_FILE:-}" ]]; then
    [[ -f "$RELEASE_ENV_FILE" ]] || {
      echo "Missing release environment: $RELEASE_ENV_FILE" >&2
      return 2
    }
    set -a
    # shellcheck disable=SC1090
    . "$RELEASE_ENV_FILE"
    set +a
  fi
}