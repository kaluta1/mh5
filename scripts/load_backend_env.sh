#!/usr/bin/env bash
# Source backend/.env so shell scripts and one-off commands use the same DATABASE_URL as the API.
# Usage: source scripts/load_backend_env.sh [repo_root]

_load_backend_env_impl() {
  local root="${1:-}"
  if [ -z "$root" ]; then
    root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  fi
  local env_file="${root}/backend/.env"
  if [ ! -f "$env_file" ]; then
    echo "ERROR: ${env_file} not found — create it with DATABASE_URL" >&2
    return 1
  fi
  set -a
  # shellcheck disable=SC1090
  source "$env_file"
  set +a
  if [ -f "${root}/backend/.env.local" ] && [ "${ENVIRONMENT:-}" != "production" ]; then
    set -a
    # shellcheck disable=SC1090
    source "${root}/backend/.env.local"
    set +a
  fi
  if [ -z "${DATABASE_URL:-}" ]; then
    echo "ERROR: DATABASE_URL is empty in ${env_file}" >&2
    return 1
  fi
  export REPO_ROOT="$root"
}

if [ "${BASH_SOURCE[0]}" != "${0}" ]; then
  _load_backend_env_impl "${1:-}"
else
  echo "Source this file: source scripts/load_backend_env.sh" >&2
  exit 1
fi
