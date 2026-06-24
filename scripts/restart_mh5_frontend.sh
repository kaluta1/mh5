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
node --max-old-space-size=4096 node_modules/next/dist/bin/next build

if command -v pm2 >/dev/null 2>&1; then
  # Avoid serving mixed Next builds: remove old/errored PM2 entries and any
  # unmanaged process still listening on the frontend port.
  pm2 delete mh5-frontend myhigh5-web myhigh5-frontend mh5-web >/dev/null 2>&1 || true
  if command -v lsof >/dev/null 2>&1; then
    while IFS= read -r pid; do
      [ -n "$pid" ] && kill "$pid" >/dev/null 2>&1 || true
    done < <(lsof -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null || true)
  elif command -v fuser >/dev/null 2>&1; then
    fuser -k "${PORT}/tcp" >/dev/null 2>&1 || true
  elif command -v ss >/dev/null 2>&1; then
    while IFS= read -r pid; do
      [ -n "$pid" ] && kill "$pid" >/dev/null 2>&1 || true
    done < <(
      ss -ltnp "sport = :$PORT" 2>/dev/null \
        | sed -nE 's/.*pid=([0-9]+).*/\1/p' \
        | sort -u
    )
  fi

  cd "$FRONTEND"
  PORT="$PORT" pm2 start npm --name mh5-frontend -- run start:vps
  pm2 save 2>/dev/null || true
  sleep 3
  pm2 status mh5-frontend
  exit 0
fi

echo "    WARN: pm2 not installed; run manually: cd frontend && npm run start:vps"
exit 1
