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

restart_pm2() {
  local name="$1"
  if command -v pm2 >/dev/null 2>&1 && pm2 describe "$name" >/dev/null 2>&1; then
    echo "    pm2 restart $name"
    pm2 restart "$name"
    pm2 save 2>/dev/null || true
    return 0
  fi
  return 1
}

for app in mh5-frontend myhigh5-web myhigh5-frontend mh5-web; do
  if restart_pm2 "$app"; then
    sleep 3
    echo "    OK pm2 app $app restarted"
    exit 0
  fi
done

echo "    no pm2 frontend app found — starting myhigh5-web"
if command -v pm2 >/dev/null 2>&1; then
  cd "$FRONTEND"
  PORT="$PORT" pm2 start npm --name myhigh5-web -- run start:vps
  pm2 save 2>/dev/null || true
  exit 0
fi

echo "    WARN: pm2 not installed; run manually: cd frontend && npm run start:vps"
exit 1
