#!/usr/bin/env bash
# Emergency restore when myhigh5.com shows ERR_CONNECTION_RESET.
# Run ON THE VPS as root: bash scripts/vps_recover.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "=== MyHigh5 emergency recover ==="
echo "    repo: $ROOT"
echo "    time: $(date -Iseconds)"

echo ""
echo "=== resources ==="
free -h 2>/dev/null || true
df -h / /var 2>/dev/null | tail -3 || true

echo ""
echo "=== nginx ==="
if command -v nginx >/dev/null 2>&1; then
  if ! nginx -t 2>&1; then
    echo "    ERROR: nginx config invalid — fix /etc/nginx/sites-enabled/ before reload"
  fi
  systemctl enable nginx 2>/dev/null || true
  systemctl restart nginx
  systemctl is-active nginx && echo "    nginx: active" || echo "    nginx: FAILED"
else
  echo "    WARN: nginx not installed"
fi

echo ""
echo "=== backend (systemd :8001) ==="
bash "$ROOT/scripts/restart_mh5_backend.sh" || {
  echo "    backend restart failed — see: journalctl -u myhigh5-backend -n 50 --no-pager"
}

echo ""
echo "=== frontend (pm2 :3000) — full rebuild ==="
bash "$ROOT/scripts/restart_mh5_frontend.sh" || {
  echo "    frontend rebuild failed — see pm2 logs mh5-frontend"
  exit 1
}
pm2 status 2>/dev/null || true

echo ""
echo "=== local smoke tests ==="
for label_port in "backend:8001/api/v1/build-info" "frontend:3000/"; do
  label="${label_port%%:*}"
  path_port="${label_port#*:}"
  port="${path_port%%/*}"
  path="/${path_port#*/}"
  code="$(curl -sS -o /dev/null -w '%{http_code}' --connect-timeout 5 "http://127.0.0.1:${port}${path}" 2>/dev/null || echo 000)"
  echo "    ${label} http://127.0.0.1:${port}${path} → HTTP ${code}"
done

echo ""
echo "=== public HTTPS ==="
PUBLIC="$(curl -sf --connect-timeout 15 "https://myhigh5.com/api/v1/build-info" 2>/dev/null || echo FAIL)"
echo "    https://myhigh5.com/api/v1/build-info → ${PUBLIC}"

if [ "$PUBLIC" = "FAIL" ]; then
  echo ""
  echo "Still down. Check:"
  echo "  journalctl -u nginx -n 40 --no-pager"
  echo "  journalctl -u myhigh5-backend -n 40 --no-pager"
  echo "  pm2 logs mh5-frontend --lines 40"
  echo "  ss -ltnp | grep -E ':80|:443|:3000|:8001'"
  exit 1
fi

echo ""
echo "=== recover OK ==="
