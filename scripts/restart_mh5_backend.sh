#!/usr/bin/env bash
# Restart MyHigh5 backend on VPS — stop legacy units, run myhigh5-backend on :8001.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND="$ROOT/backend"
PORT="${MH5_BACKEND_PORT:-8001}"
UNIT_SRC="$ROOT/deploy/myhigh5-backend.service"
UNIT_NAME="myhigh5-backend.service"
LEGACY_UNITS=(mh5-api myhigh5-api mh5-backend)

expected_build_id() {
  python3 -c "import re; print(re.search(r'BACKEND_BUILD_ID\s*=\s*\"([^\"]+)\"', open('${BACKEND}/app/core/build_info.py').read()).group(1))"
}

echo "==> ensure backend/.env secrets"
bash "$ROOT/scripts/ensure_backend_env_secrets.sh"

echo "==> restart mh5 backend (port ${PORT})"
EXPECTED="$(expected_build_id)"
echo "    expected build_id: ${EXPECTED}"

# Ensure venv exists and dependencies match requirements.txt (git pull may add new packages)
if [ ! -x "$BACKEND/.venv/bin/uvicorn" ]; then
  echo "    creating .venv..."
  python3 -m venv "$BACKEND/.venv"
fi
echo "    syncing pip dependencies..."
"$BACKEND/.venv/bin/pip" install -q -r "$BACKEND/requirements.txt"

if [ -f "$ROOT/scripts/fix_postgres_ownership.sh" ]; then
  echo "==> fix postgres table ownership (app user must own tables for alembic)"
  if bash "$ROOT/scripts/fix_postgres_ownership.sh"; then
    echo "    OK ownership"
  else
    echo "    WARN ownership fix failed — trying manual migrations as postgres" >&2
  fi
fi

if [ -f "$ROOT/scripts/apply_vps_db_migrations.sh" ]; then
  echo "==> apply idempotent VPS manual migrations (postgres superuser)"
  if bash "$ROOT/scripts/apply_vps_db_migrations.sh"; then
    echo "    OK manual migrations"
  else
    echo "    WARN manual migrations failed — see backend/scripts/neon_manual_migrations.sql" >&2
  fi
fi

# Apply database migrations (the systemd unit runs uvicorn directly and does NOT
# migrate, so prod schema drifts without this). 'heads' handles multiple branches.
VENV_PY="$BACKEND/.venv/bin/python3"
if [ -x "$VENV_PY" ]; then
  echo "==> applying database migrations (alembic upgrade heads)"
  # script_location in alembic.ini is relative to cwd, so run from backend/.
  if ( cd "$BACKEND" && PYTHONPATH="$BACKEND" "$VENV_PY" -m alembic upgrade heads ); then
    echo "    OK migrations applied"
  else
    echo "    WARN alembic upgrade failed — check DB and: cd backend && .venv/bin/python -m alembic upgrade heads" >&2
  fi

  # Safety net: alembic may be stamped past migrations that never actually ran
  # (old start.py could `alembic stamp heads` without applying them). This
  # idempotent check adds any missing KYC/payment columns + enum values.
  echo "==> ensuring KYC/payment schema (idempotent)"
  ( cd "$BACKEND" && PYTHONPATH="$BACKEND" "$VENV_PY" scripts/ensure_kyc_payment_schema.py ) \
    || echo "    WARN schema-ensure failed — run manually: cd backend && .venv/bin/python scripts/ensure_kyc_payment_schema.py" >&2
fi

# Always sync systemd unit from repo (paths may differ from /root/mh5)
if [ -f "$UNIT_SRC" ]; then
  echo "    syncing $UNIT_NAME from deploy/"
  sed "s|/root/mh5|${ROOT}|g" "$UNIT_SRC" > "/etc/systemd/system/$UNIT_NAME"
  systemctl daemon-reload
  systemctl enable "$UNIT_NAME"
fi

# Stop PM2-managed legacy backend (common on this VPS)
if command -v pm2 >/dev/null 2>&1; then
  for name in myhigh5-api mh5-api mh5-backend; do
    if pm2 describe "$name" >/dev/null 2>&1; then
      echo "    stopping pm2 $name (superseded by myhigh5-backend systemd unit)"
      pm2 stop "$name" 2>/dev/null || true
      pm2 delete "$name" 2>/dev/null || true
    fi
  done
  pm2 save 2>/dev/null || true
fi

# Stop legacy systemd services that steal :8001 with old code
for svc in "${LEGACY_UNITS[@]}"; do
  if systemctl is-active --quiet "$svc" 2>/dev/null; then
    echo "    stopping legacy $svc (superseded by myhigh5-backend)"
    systemctl stop "$svc" || true
    systemctl disable "$svc" 2>/dev/null || true
  fi
done

# Free the port — kill any stale uvicorn not managed by our unit
if command -v fuser >/dev/null 2>&1; then
  fuser -k "${PORT}/tcp" 2>/dev/null || true
else
  pkill -f "uvicorn main:app.*--port ${PORT}" 2>/dev/null || true
  pkill -f "uvicorn main:app.*--port ${PORT}" 2>/dev/null || true
fi
sleep 1

echo "    systemctl restart myhigh5-backend"

wait_for_backend() {
  local attempt=0
  local max="${1:-30}"
  while [ "$attempt" -lt "$max" ]; do
    attempt=$((attempt + 1))
    if curl -sf "http://127.0.0.1:${PORT}/api/v1/build-info" >/dev/null 2>&1; then
      echo "    backend ready (attempt ${attempt})"
      return 0
    fi
    if [ "$attempt" -eq 1 ] || [ $((attempt % 5)) -eq 0 ]; then
      echo "    waiting for backend on :${PORT} (attempt ${attempt}/${max})..."
    fi
    sleep 1
  done
  return 1
}

systemctl restart myhigh5-backend
if ! wait_for_backend 45; then
  echo "    WARN backend not healthy after restart" >&2
  systemctl status myhigh5-backend --no-pager -l | tail -20 || true
fi

BUILD_JSON="$(curl -sf "http://127.0.0.1:${PORT}/api/v1/build-info" || echo '{}')"
echo "    local build-info: ${BUILD_JSON}"

if echo "$BUILD_JSON" | grep -q "$EXPECTED"; then
  echo "    OK build_id matches repo"
  exit 0
fi

echo "    WARN build_id mismatch — check: systemctl status myhigh5-backend --no-pager -l"
systemctl status myhigh5-backend --no-pager -l | tail -20 || true
exit 1
