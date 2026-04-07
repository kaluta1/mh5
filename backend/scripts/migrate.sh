#!/usr/bin/env bash
# Run Alembic with the project venv (SQLAlchemy 2.x). Do not use system /usr/bin/alembic.
set -euo pipefail
BACKEND_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$BACKEND_DIR"
VENV_PY="${BACKEND_DIR}/.venv/bin/python3"
if [[ ! -x "$VENV_PY" ]]; then
  echo "No project venv at ${BACKEND_DIR}/.venv"
  echo "Create it and install deps:"
  echo "  cd $BACKEND_DIR"
  echo "  python3 -m venv .venv"
  echo "  . .venv/bin/activate"
  echo "  pip install -U pip"
  echo "  pip install -r requirements.txt"
  echo "Then run:"
  echo "  $0 \"\$@\""
  exit 1
fi
exec "$VENV_PY" -m alembic "$@"
