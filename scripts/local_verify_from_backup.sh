#!/usr/bin/env bash
# Restore db-backup and run nomination verify against local backend (optional pre-VPS check).
# Requires: PostgreSQL 17+ client (pg_restore), Python 3.10+, backend/.env with DATABASE_URL
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKUP="${ROOT}/db-backup/mh5-db-backup.sql"
DB_NAME="${MH5_DB_NAME:-mh5_local}"
PORT="${BACKEND_PORT:-8001}"

# Production checks: use DATABASE_URL from backend/.env only.
# Local backup restore: set MH5_USE_LOCAL_RESTORE=1 to point at a restored local DB.
if [ -f "$ROOT/backend/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/backend/.env"
  set +a
  if [ -f "$ROOT/backend/.env.local" ]; then
    set -a
    # shellcheck disable=SC1091
    source "$ROOT/backend/.env.local"
    set +a
  fi
fi
if [ "${MH5_USE_LOCAL_RESTORE:-0}" = "1" ]; then
  export DATABASE_URL="postgresql://$(whoami)@127.0.0.1:5432/${DB_NAME}"
elif [ -z "${DATABASE_URL:-}" ]; then
  echo "ERROR: set DATABASE_URL in backend/.env (or MH5_USE_LOCAL_RESTORE=1 for backup restore)" >&2
  exit 1
fi

if ! command -v pg_restore >/dev/null; then
  echo "Install PostgreSQL 17+ (backup format 1.16 needs pg_restore 17+)"
  exit 1
fi

echo "==> create database ${DB_NAME} (skip if exists)"
createdb "$DB_NAME" 2>/dev/null || true

echo "==> restore backup (may take a few minutes)"
pg_restore -d "$DB_NAME" --no-owner --no-acl "$BACKUP" 2>/dev/null || {
  echo "If restore fails: upgrade pg_restore to 17+ (brew install postgresql@17)"
  exit 1
}

echo "==> start backend on :${PORT} (background)"
cd "$ROOT/backend"
if [ -d .venv ]; then source .venv/bin/activate; fi
pip install -q -r requirements.txt 2>/dev/null || pip install -q fastapi uvicorn sqlalchemy psycopg2-binary python-dotenv python-jose bcrypt 'pydantic[email]' 2>/dev/null
uvicorn main:app --host 127.0.0.1 --port "$PORT" &
PID=$!
sleep 5

echo "==> local build-info"
curl -sf "http://127.0.0.1:${PORT}/api/v1/build-info" | python3 -m json.tool

echo "==> local nomination verify"
python3 "$ROOT/backend/scripts/verify_nomination_vote_levels.py" \
  --base-url "http://127.0.0.1:${PORT}/api/v1" --round-id 21 --contest-id 7

kill "$PID" 2>/dev/null || true
