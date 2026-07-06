#!/usr/bin/env bash
# Rebuild and restart MyHigh5 Next.js frontend on VPS (port 3000).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FRONTEND="$ROOT/frontend"
PORT="${MH5_FRONTEND_PORT:-3000}"

echo "==> rebuild mh5 frontend (port ${PORT})"
cd "$FRONTEND"

port_pids() {
  local pids=""
  if command -v ss >/dev/null 2>&1; then
    pids="$(
      ss -ltnp "sport = :$PORT" 2>/dev/null \
        | sed -nE 's/.*pid=([0-9]+).*/\1/p' \
        | sort -u \
        | tr '\n' ' '
    )"
  fi
  if [ -z "$pids" ] && command -v lsof >/dev/null 2>&1; then
    pids="$(lsof -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null | tr '\n' ' ' || true)"
  fi
  echo "$pids"
}

kill_frontend_listeners() {
  local pid
  for pid in $(port_pids); do
    [ -n "$pid" ] && kill -9 "$pid" 2>/dev/null || true
  done
  if command -v fuser >/dev/null 2>&1; then
    fuser -k "${PORT}/tcp" >/dev/null 2>&1 || true
  fi
  pkill -9 -f "next-server" 2>/dev/null || true
  pkill -9 -f "next start.*-p ${PORT}" 2>/dev/null || true
  pkill -9 -f "next start.*-p${PORT}" 2>/dev/null || true
}

wait_for_port_free() {
  local attempt=0
  while [ -n "$(port_pids)" ]; do
    attempt=$((attempt + 1))
    if [ "$attempt" -gt 15 ]; then
      echo "    ERROR: port ${PORT} still in use after cleanup:"
      ss -ltnp "sport = :$PORT" 2>/dev/null || true
      exit 1
    fi
    echo "    waiting for port ${PORT} to free (attempt ${attempt})..."
    kill_frontend_listeners
    sleep 1
  done
}

wait_for_http() {
  local url="$1"
  local max_attempts="${2:-45}"
  local attempt=0
  local code=""
  while [ "$attempt" -lt "$max_attempts" ]; do
    attempt=$((attempt + 1))
    code="$(curl -sS -o /dev/null -w '%{http_code}' --connect-timeout 3 --max-time 10 "$url" 2>/dev/null || echo 000)"
    if [ "$code" = "200" ] || [ "$code" = "301" ] || [ "$code" = "302" ] || [ "$code" = "307" ] || [ "$code" = "308" ]; then
      echo "    HTTP ${code} from ${url} (attempt ${attempt})"
      return 0
    fi
    if [ "$attempt" -eq 1 ] || [ $((attempt % 5)) -eq 0 ]; then
      echo "    waiting for ${url} (attempt ${attempt}/${max_attempts}, last HTTP ${code})..."
    fi
    sleep 2
  done
  echo "    ERROR: ${url} not ready after ${max_attempts} attempts (last HTTP ${code})" >&2
  return 1
}

stop_frontend_pm2() {
  if ! command -v pm2 >/dev/null 2>&1; then
    return 0
  fi
  echo "    stopping pm2 frontend processes"
  pm2 stop mh5-frontend myhigh5-web myhigh5-frontend mh5-web >/dev/null 2>&1 || true
  pm2 delete mh5-frontend myhigh5-web myhigh5-frontend mh5-web >/dev/null 2>&1 || true
  pm2 save >/dev/null 2>&1 || true
}

verify_next_build() {
  local missing=0
  for f in \
    .next/BUILD_ID \
    .next/prerender-manifest.json \
    .next/routes-manifest.json \
    .next/server/pages-manifest.json; do
    if [ ! -f "$f" ]; then
      echo "    ERROR: build incomplete — missing $f" >&2
      missing=1
    fi
  done
  [ "$missing" -eq 0 ]
}

# Stop serving BEFORE deleting .next — prevents ENOENT + EADDRINUSE crash loops.
echo "==> stop old frontend (free :${PORT})"
stop_frontend_pm2
kill_frontend_listeners
sleep 1
wait_for_port_free

fix_maintenance_env() {
  local f="$1"
  [ -f "$f" ] || return 0
  if grep -qE '^(IS_MAINTENANCE_MODE|MAINTENANCE_MODE)=' "$f" 2>/dev/null; then
    local tmp
    tmp="$(mktemp)"
    sed -E 's/^(IS_MAINTENANCE_MODE|MAINTENANCE_MODE)=.*/\1=false/' "$f" > "$tmp"
    mv "$tmp" "$f"
    echo "    forced maintenance flags off in $f"
  fi
}
fix_maintenance_env .env.local
fix_maintenance_env .env

install_deps() {
  if [ -f package-lock.json ]; then
    if npm ci --no-audit --no-fund; then
      return 0
    fi
    echo "    WARN: npm ci failed (lockfile/npm version mismatch) — falling back to npm install"
    rm -rf node_modules
  fi
  npm install --no-audit --no-fund
}

install_deps

export NODE_ENV=production
export NEXT_TELEMETRY_DISABLED=1
export MAINTENANCE_MODE=false
export IS_MAINTENANCE_MODE=false

if [ -f .env.production ]; then
  set -a
  # shellcheck disable=SC1091
  source .env.production
  set +a
  echo "    loaded .env.production (NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL:-unset})"
fi

if [ "${NEXT_PUBLIC_API_URL:-}" != "https://myhigh5.com" ] && [ "${NEXT_PUBLIC_API_URL:-}" != "https://myhigh5.com/" ]; then
  echo "    ERROR: NEXT_PUBLIC_API_URL must be https://myhigh5.com for VPS (got: ${NEXT_PUBLIC_API_URL:-unset})" >&2
  exit 1
fi

echo "==> next build (keep .next.bak until success)"
if [ -d .next ]; then
  rm -rf .next.bak
  mv .next .next.bak
fi
rm -rf .next

if ! node --max-old-space-size=4096 node_modules/next/dist/bin/next build; then
  echo "    ERROR: next build failed — restoring previous .next if available" >&2
  rm -rf .next
  if [ -d .next.bak ]; then
    mv .next.bak .next
    echo "    restored .next.bak"
  fi
  exit 1
fi

if ! verify_next_build; then
  echo "    ERROR: build artifacts missing — restoring previous .next if available" >&2
  rm -rf .next
  if [ -d .next.bak ]; then
    mv .next.bak .next
    echo "    restored .next.bak"
  fi
  exit 1
fi

rm -rf .next.bak
echo "    build OK (.next/prerender-manifest.json present)"

if command -v pm2 >/dev/null 2>&1; then
  wait_for_port_free
  cd "$FRONTEND"
  PORT="$PORT" pm2 start node_modules/next/dist/bin/next \
    --name mh5-frontend \
    --cwd "$FRONTEND" \
    --max-restarts 5 \
    --time \
    -- start -H 127.0.0.1 -p "$PORT"
  pm2 save 2>/dev/null || true

  if ! wait_for_http "http://127.0.0.1:${PORT}/" 45; then
    echo "    pm2 status:" >&2
    pm2 status mh5-frontend 2>/dev/null || true
    echo "    port ${PORT} listeners:" >&2
    ss -ltnp "sport = :$PORT" 2>/dev/null || true
    echo "    recent logs:" >&2
    pm2 logs mh5-frontend --lines 40 --nostream 2>/dev/null || true
    exit 1
  fi

  pm2 status mh5-frontend
  echo "    port ${PORT} listeners:"
  ss -ltnp "sport = :$PORT" 2>/dev/null || true
  exit 0
fi

echo "    WARN: pm2 not installed; run manually: cd frontend && npm run start:vps"
exit 1
