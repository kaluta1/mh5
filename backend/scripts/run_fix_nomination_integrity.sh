#!/usr/bin/env bash
# Run fix_nomination_integrity.py with the same Python env as the API.
# Usage (from repo root, e.g. ~/mh5):
#   bash backend/scripts/run_fix_nomination_integrity.sh
#   bash backend/scripts/run_fix_nomination_integrity.sh --apply
#   bash backend/scripts/run_fix_nomination_integrity.sh --apply --overlap

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${BACKEND_DIR}/.." && pwd)"
ARGS=("$@")

run_in_venv() {
  cd "${BACKEND_DIR}"
  if [[ ! -d .venv ]]; then
    echo "Creating backend/.venv ..."
    python3 -m venv .venv
  fi
  # shellcheck disable=SC1091
  source .venv/bin/activate
  pip install -q -r requirements.txt
  exec python scripts/fix_nomination_integrity.py "${ARGS[@]}"
}

run_in_docker() {
  local compose_file="${BACKEND_DIR}/docker-compose.yml"
  local service="app"
  local container=""

  if [[ -f "${compose_file}" ]]; then
    if docker compose -f "${compose_file}" ps --status running --services 2>/dev/null | grep -qx "${service}"; then
      cd "${BACKEND_DIR}"
      exec docker compose exec -T "${service}" python scripts/fix_nomination_integrity.py "${ARGS[@]}"
    fi
  fi

  for name in backend-app mh5-backend-app mh5_app app; do
    if docker ps --format '{{.Names}}' | grep -qx "${name}"; then
      container="${name}"
      break
    fi
  done

  if [[ -n "${container}" ]]; then
    exec docker exec -i "${container}" python scripts/fix_nomination_integrity.py "${ARGS[@]}"
  fi

  return 1
}

if run_in_docker; then
  :
elif [[ -f "${BACKEND_DIR}/.venv/bin/activate" ]]; then
  run_in_venv
else
  echo "No running backend Docker container found and no backend/.venv."
  echo "Start the API container, or create a venv:"
  echo "  cd ${BACKEND_DIR} && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
  exit 1
fi
