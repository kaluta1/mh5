#!/usr/bin/env bash
# Quick check: is nomination fix deployed on production?
set -euo pipefail
BASE="${1:-https://myhigh5.com/api/v1}"
echo "==> build-info"
curl -sf "${BASE%/}/build-info" | python3 -m json.tool || {
  echo "FAIL: /build-info not found — backend not updated yet (git pull + restart on VPS)"
  exit 1
}
echo "==> nomination verify round 21 contest 7"
python3 "$(dirname "$0")/../backend/scripts/verify_nomination_vote_levels.py" \
  --base-url "$BASE" --round-id 21 --contest-id 7
