#!/usr/bin/env bash
# Deploy backend on VPS after git pull. Run ON THE SERVER from repo root.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

echo "==> git pull"
git pull origin main

echo "==> backend deps"
cd backend
if [ -d .venv ]; then
  source .venv/bin/activate
elif [ -d venv ]; then
  source venv/bin/activate
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
echo "==> health check"
curl -sf "http://127.0.0.1:8001/health" || curl -sf "http://127.0.0.1:8000/health" || true
echo
echo "Expected: curl $BASE/api/v1/build-info shows nomination-roster-fix-5a0110a"
