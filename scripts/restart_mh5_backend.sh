#!/usr/bin/env bash
# Restart MyHigh5 backend on VPS — systemd first, then manual uvicorn on :8001.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND="$ROOT/backend"
PORT="${MH5_BACKEND_PORT:-8001}"
UNIT_SRC="$ROOT/deploy/myhigh5-backend.service"
UNIT_NAME="myhigh5-backend.service"

echo "==> restart mh5 backend (port ${PORT})"

# Ensure venv exists
if [ ! -x "$BACKEND/.venv/bin/uvicorn" ]; then
  echo "    creating .venv..."
  python3 -m venv "$BACKEND/.venv"
  # shellcheck disable=SC1091
  source "$BACKEND/.venv/bin/activate"
  pip install -q -r "$BACKEND/requirements.txt"
fi

# Install systemd unit if missing (path must match repo on this host)
if [ -f "$UNIT_SRC" ] && [ ! -f "/etc/systemd/system/$UNIT_NAME" ]; then
  echo "    installing $UNIT_NAME from deploy/"
  sed "s|/root/mh5|${ROOT}|g" "$UNIT_SRC" > "/etc/systemd/system/$UNIT_NAME"
  systemctl daemon-reload
  systemctl enable "$UNIT_NAME"
fi

for svc in myhigh5-backend mh5-backend myhigh5-api mh5-api; do
  if systemctl list-unit-files "${svc}.service" 2>/dev/null | grep -q "${svc}.service"; then
    echo "    systemctl restart $svc"
    systemctl restart "$svc"
    sleep 3
    if curl -sf "http://127.0.0.1:${PORT}/api/v1/build-info" >/dev/null 2>&1; then
      curl -sf "http://127.0.0.1:${PORT}/api/v1/build-info"
      echo ""
      exit 0
    fi
  fi
done

# Fallback: kill stale uvicorn on this port and start fresh
echo "    no healthy systemd unit — restarting uvicorn on :${PORT}"
pkill -f "uvicorn main:app.*--port ${PORT}" 2>/dev/null || true
pkill -f "uvicorn main:app.*--port ${PORT}" 2>/dev/null || true
sleep 1

# shellcheck disable=SC1091
source "$ROOT/scripts/load_backend_env.sh" "$ROOT"
export ENVIRONMENT="${ENVIRONMENT:-production}"
export PYTHONPATH="$BACKEND"
export GIT_SHA="$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo unknown)"

nohup "$BACKEND/.venv/bin/uvicorn" main:app \
  --host 127.0.0.1 \
  --port "$PORT" \
  --workers 1 \
  --timeout-keep-alive 30 \
  >> /var/log/myhigh5-backend.log 2>&1 &

sleep 4
if curl -sf "http://127.0.0.1:${PORT}/api/v1/build-info"; then
  echo ""
  echo "    OK backend listening on :${PORT}"
else
  echo "    FAIL: backend did not start — tail /var/log/myhigh5-backend.log"
  tail -30 /var/log/myhigh5-backend.log 2>/dev/null || true
  exit 1
fi
