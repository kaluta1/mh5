#!/usr/bin/env bash
# Run ON THE VPS from repo root — backend status, logs hints, contest API smoke test.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

EXPECTED_BUILD="$(python3 -c "import re; print(re.search(r'BACKEND_BUILD_ID\s*=\s*\"([^\"]+)\"', open('backend/app/core/build_info.py').read()).group(1))" 2>/dev/null || echo unknown)"

echo "=== MyHigh5 VPS layout ==="
echo "  Backend : systemd myhigh5-backend.service → uvicorn 127.0.0.1:8001"
echo "  Frontend: pm2 mh5-frontend → next start 127.0.0.1:3000"
echo "  nginx   : /api/* → :8001, everything else → :3000"
echo ""
echo "  Backend logs are NOT in pm2. Use:"
echo "    journalctl -u myhigh5-backend -n 80 --no-pager"
echo "    journalctl -u myhigh5-backend -f"
echo "  Frontend logs:"
echo "    pm2 logs mh5-frontend --lines 50"
echo ""

echo "=== git ==="
git log -1 --oneline 2>/dev/null || echo "not a git repo?"
echo "expected build_id in repo: ${EXPECTED_BUILD}"

echo ""
echo "=== backend build-info (localhost) ==="
LOCAL_OK=0
for port in 8001 8000; do
  if resp="$(curl -sf "http://127.0.0.1:${port}/api/v1/build-info" 2>/dev/null)"; then
    echo "port ${port}: ${resp}"
    LOCAL_OK=1
    break
  else
    echo "port ${port}: no response"
  fi
done
if [ "$LOCAL_OK" -eq 0 ]; then
  echo "FAIL: backend not listening on 8001 or 8000"
fi

echo ""
echo "=== systemd backend (myhigh5-backend) ==="
if systemctl list-unit-files myhigh5-backend.service >/dev/null 2>&1; then
  systemctl is-active myhigh5-backend 2>/dev/null && echo "active: yes" || echo "active: NO — run: bash scripts/restart_mh5_backend.sh"
  systemctl status myhigh5-backend --no-pager -l 2>/dev/null | head -15 || true
else
  echo "myhigh5-backend.service not installed — run: bash scripts/restart_mh5_backend.sh"
fi

echo ""
echo "=== legacy services (should be stopped) ==="
for svc in mh5-backend mh5-api myhigh5-api; do
  if systemctl is-active --quiet "$svc" 2>/dev/null; then
    echo "WARN: legacy $svc is still active (old code on :8001?)"
    systemctl status "$svc" --no-pager -l 2>/dev/null | head -6 || true
  fi
done

echo ""
echo "=== pm2 (frontend only) ==="
if command -v pm2 >/dev/null 2>&1; then
  pm2 status 2>/dev/null || true
else
  echo "pm2 not installed"
fi

echo ""
echo "=== nginx /api proxy ==="
if command -v nginx >/dev/null 2>&1; then
  nginx -t 2>&1 | tail -2 || true
  grep -R "proxy_pass.*800" /etc/nginx/sites-enabled/ 2>/dev/null | head -5 || echo "(could not read nginx sites-enabled)"
fi

echo ""
echo "=== public API (https://myhigh5.com/api/v1) ==="
PUBLIC="$(curl -sf "https://myhigh5.com/api/v1/build-info" 2>/dev/null || echo FAIL)"
echo "build-info: ${PUBLIC}"
if echo "$PUBLIC" | grep -q "$EXPECTED_BUILD"; then
  echo "OK public build_id matches repo"
else
  echo "WARN public build_id may be stale — git pull && bash scripts/vps_full_deploy.sh"
fi

echo ""
echo "=== contest 177 nominators (Tanzania, round 21) ==="
URL="https://myhigh5.com/api/v1/contests/177?filterCountry=Tanzania&entryType=nomination&roundId=21&contestLevel=country&country=Tanzania&rosterOnly=true"
CODE="$(curl -sS -o /tmp/mh5-contest177.json -w '%{http_code}' "$URL" || echo 000)"
echo "HTTP ${CODE}"
if [ "$CODE" = "200" ]; then
  python3 -c "import json; d=json.load(open('/tmp/mh5-contest177.json')); print('  contestants:', len(d.get('contestants') or []), '|', d.get('name'))" 2>/dev/null || true
elif [ "$CODE" = "503" ]; then
  echo "  503 Database error — check:"
  echo "    journalctl -u myhigh5-backend -n 100 --no-pager | grep -iE 'database|error|503'"
  echo "    grep DATABASE_URL backend/.env  (Neon URL must be valid)"
fi

echo ""
echo "=== recent backend errors (last 30 lines) ==="
journalctl -u myhigh5-backend -n 30 --no-pager 2>/dev/null | tail -20 || echo "(journalctl unavailable or unit missing)"
