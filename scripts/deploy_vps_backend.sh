#!/usr/bin/env bash
# Deploy backend on VPS after git pull. Run ON THE SERVER from repo root.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

# shellcheck disable=SC1091
source "$REPO_ROOT/scripts/load_backend_env.sh" "$REPO_ROOT"

echo "==> git pull"
git pull origin main

echo "==> backend deps"
cd backend
if [ -f .venv/bin/activate ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
elif [ -f venv/bin/activate ]; then
  # shellcheck disable=SC1091
  source venv/bin/activate
else
  rm -rf .venv
  python3 -m venv .venv
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi
pip install -r requirements.txt

export GIT_SHA="$(git -C "$REPO_ROOT" rev-parse --short HEAD)"
echo "==> GIT_SHA=$GIT_SHA"

echo "==> restart backend (adjust service name if needed)"
if systemctl is-active --quiet myhigh5-backend 2>/dev/null; then
  sudo systemctl restart myhigh5-backend
elif systemctl is-active --quiet mh5-backend 2>/dev/null; then
  sudo systemctl restart mh5-backend
else
  echo "No systemd unit found. Restart uvicorn/docker manually."
  echo "Example: uvicorn main:app --host 0.0.0.0 --port 8001"
fi

sleep 3
echo "==> run season migrations"
cd "$REPO_ROOT/backend"
PYTHONPATH=. python3 -c "
from app.db.session import SessionLocal
from app.services.season_migration import season_migration_service
db = SessionLocal()
try:
    print(season_migration_service.check_and_process_migrations(db))
finally:
    db.close()
"

echo "==> health / build-info"
for port in 8001 8000; do
  curl -sf "http://127.0.0.1:${port}/api/v1/build-info" && echo " (port ${port})" && break
done || curl -sf "http://127.0.0.1:8001/health" || curl -sf "http://127.0.0.1:8000/health" || true
echo
echo "Expected build_id: rounds-list-perf-fix-20260615"
curl -sf "https://myhigh5.com/api/v1/build-info" | python3 -m json.tool 2>/dev/null || echo "Public /build-info not ready yet"
