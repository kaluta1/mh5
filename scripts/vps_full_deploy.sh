#!/usr/bin/env bash
# Full backend deploy on VPS: pull, deps, restart, run migrations, verify.
# Run as root ON THE VPS: bash scripts/vps_full_deploy.sh
set -euo pipefail

EXPECTED_BUILD="nomination-roster-fix-20260621"

find_repo() {
  if [ -f "$(pwd)/backend/main.py" ] && [ -d "$(pwd)/.git" ]; then
    pwd
    return
  fi
  for candidate in \
    /root/mh5 \
    /var/www/mh5 \
    /home/*/mh5 \
    /opt/mh5; do
    if [ -f "$candidate/backend/main.py" ] && [ -d "$candidate/.git" ]; then
      echo "$candidate"
      return
    fi
  done
  local hit
  hit="$(find /root /var/www /home /opt -maxdepth 5 -type f -path '*/mh5/backend/main.py' 2>/dev/null | head -1 || true)"
  if [ -n "$hit" ]; then
    dirname "$(dirname "$hit")"
    return
  fi
  echo "ERROR: mh5 repo not found. cd to repo root and re-run." >&2
  exit 1
}

REPO_ROOT="$(find_repo)"
cd "$REPO_ROOT"
echo "==> repo: $REPO_ROOT"

# Single DATABASE_URL for migrations, verify scripts, and API (backend/.env)
# shellcheck disable=SC1091
source "$REPO_ROOT/scripts/load_backend_env.sh" "$REPO_ROOT"
echo "    DATABASE_URL host: ${DATABASE_URL#*@}"

echo "==> git sync (VPS must match GitHub main exactly)"
git fetch origin main
# Production VPS: discard local commits so deploy matches origin/main
if ! git merge-base --is-ancestor HEAD origin/main 2>/dev/null || \
   ! git merge-base --is-ancestor origin/main HEAD 2>/dev/null; then
  echo "    divergent history — resetting to origin/main"
  git reset --hard origin/main
else
  git pull --ff-only origin main
fi
GIT_SHA="$(git rev-parse --short HEAD)"
echo "    HEAD=$GIT_SHA"

echo "==> backend deps"
cd backend

activate_venv() {
  if [ -f .venv/bin/activate ]; then
    # shellcheck disable=SC1091
    source .venv/bin/activate
    return
  fi
  if [ -f venv/bin/activate ]; then
    # shellcheck disable=SC1091
    source venv/bin/activate
    return
  fi
  echo "    creating .venv (missing or incomplete)"
  rm -rf .venv
  python3 -m venv .venv
  # shellcheck disable=SC1091
  source .venv/bin/activate
}

activate_venv
pip install -q -r requirements.txt

export GIT_SHA

echo "==> restart backend"
bash "$REPO_ROOT/scripts/restart_mh5_backend.sh"

sleep 2

echo "==> local build-info"
OK_LOCAL=0
for port in 8001 8000; do
  if resp="$(curl -sf "http://127.0.0.1:${port}/api/v1/build-info" 2>/dev/null)"; then
    echo "    port $port: $resp"
    OK_LOCAL=1
    break
  fi
done
if [ "$OK_LOCAL" -eq 0 ]; then
  echo "    FAIL: no local /api/v1/build-info on 8001 or 8000"
fi

echo "==> run season migrations (sync + promote)"
cd "$REPO_ROOT/backend"
PYTHONPATH=. python3 -c "
from app.db.session import SessionLocal
from app.services.season_migration import season_migration_service
db = SessionLocal()
try:
    out = season_migration_service.check_and_process_migrations(db)
    print('processed:', out.get('processed', 0))
finally:
    db.close()
"

echo "==> optional: March round regional backfill"
for round_name in "Round March 2026" "Round March 2025"; do
  if PYTHONPATH=. python3 scripts/diagnose_round_regional_migration.py --round-name "$round_name" 2>/dev/null | head -3; then
    PYTHONPATH=. python3 scripts/diagnose_round_regional_migration.py --round-name "$round_name" --apply || true
    break
  fi
done

echo "==> public build-info"
PUBLIC="$(curl -sf "https://myhigh5.com/api/v1/build-info" 2>/dev/null || echo FAIL)"
echo "    $PUBLIC"
if echo "$PUBLIC" | grep -q "$EXPECTED_BUILD"; then
  echo "    OK build_id=$EXPECTED_BUILD"
else
  echo "    FAIL expected build_id=$EXPECTED_BUILD but public API returned: $PUBLIC"
  echo "    Run: bash scripts/restart_mh5_backend.sh && curl -s http://127.0.0.1:8001/api/v1/build-info"
  exit 1
fi

echo "==> nomination verify (auto round — use localhost for heavy /rounds/ list)"
cd "$REPO_ROOT"
LOCAL_API=""
for port in 8001 8000; do
  if curl -sf "http://127.0.0.1:${port}/api/v1/build-info" >/dev/null 2>&1; then
    LOCAL_API="http://127.0.0.1:${port}/api/v1"
    break
  fi
done
if [ -n "$LOCAL_API" ]; then
  python3 backend/scripts/verify_nomination_vote_levels.py \
    --base-url https://myhigh5.com/api/v1 \
    --list-base-url "$LOCAL_API" \
    --contest-id 7 || true
else
  python3 backend/scripts/verify_nomination_vote_levels.py \
    --base-url https://myhigh5.com/api/v1 --contest-id 7 || true
fi

echo "==> done"
