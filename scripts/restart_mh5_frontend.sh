#!/usr/bin/env bash
# Rebuild and restart MyHigh5 Next.js frontend on VPS (port 3000).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FRONTEND="$ROOT/frontend"
PORT="${MH5_FRONTEND_PORT:-3000}"

echo "==> rebuild mh5 frontend (port ${PORT})"
cd "$FRONTEND"

rm -rf .next

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

# Bake production public URLs into the client bundle (not localhost).
if [ -f .env.production ]; then
  set -a
  # shellcheck disable=SC1091
  source .env.production
  set +a
  echo "    loaded .env.production (NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL:-unset})"
fi

node --max-old-space-size=4096 node_modules/next/dist/bin/next build

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
  # Orphan next-server children survive npm/pm2 crash loops.
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

if command -v pm2 >/dev/null 2>&1; then
  pm2 delete mh5-frontend myhigh5-web myhigh5-frontend mh5-web >/dev/null 2>&1 || true
  kill_frontend_listeners
  sleep 1
  wait_for_port_free

  cd "$FRONTEND"
  # Start Next directly — npm wrapper + pm2 autorestart causes EADDRINUSE crash loops.
  PORT="$PORT" pm2 start node_modules/next/dist/bin/next \
    --name mh5-frontend \
    --cwd "$FRONTEND" \
    -- start -H 127.0.0.1 -p "$PORT"
  pm2 save 2>/dev/null || true
  sleep 4
  pm2 status mh5-frontend
  echo "    port ${PORT} listeners:"
  ss -ltnp "sport = :$PORT" 2>/dev/null || true
  exit 0
fi

echo "    WARN: pm2 not installed; run manually: cd frontend && npm run start:vps"
exit 1
