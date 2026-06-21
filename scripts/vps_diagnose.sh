#!/usr/bin/env bash
# Run ON THE VPS from repo root — shows why nomination fix may not be live.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "=== git ==="
git log -1 --oneline 2>/dev/null || echo "not a git repo?"
echo "expected: 4da2e62 or newer (rounds API restore + nomination-roster-fix-20260621)"

echo ""
echo "=== backend build-info (local) ==="
for port in 8001 8000; do
  if curl -sf "http://127.0.0.1:${port}/api/v1/build-info" 2>/dev/null; then
    echo " (port ${port})"
    break
  else
    echo "port ${port}: no response"
  fi
done

echo ""
echo "=== systemd (prefer myhigh5-backend; legacy mh5-api must be stopped) ==="
for svc in myhigh5-backend mh5-backend mh5-api myhigh5-api; do
  if systemctl is-active --quiet "$svc" 2>/dev/null; then
    echo "--- $svc ---"
    systemctl status "$svc" --no-pager -l | head -12
  fi
done

echo ""
echo "=== public API (via nginx) ==="
curl -sf "https://myhigh5.com/api/v1/build-info" 2>/dev/null || echo "404 = backend NOT updated yet"

echo ""
echo "=== nomination verify ==="
if command -v python3 >/dev/null; then
  python3 backend/scripts/verify_nomination_vote_levels.py \
    --base-url https://myhigh5.com/api/v1 --round-id 21 --contest-id 7 || true
fi
