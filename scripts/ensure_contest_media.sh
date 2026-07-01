#!/usr/bin/env bash
# Ensure media storage dir exists and sync contest images from S3 when configured.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND="$ROOT/backend"
# shellcheck disable=SC1091
source "$ROOT/scripts/load_backend_env.sh" "$ROOT"

MEDIA_ROOT="${LOCAL_STORAGE_PATH:-/var/lib/myhigh5/media}"
mkdir -p "$MEDIA_ROOT"
echo "==> media root: $MEDIA_ROOT"

if grep -qE '^AWS_ACCESS_KEY_ID=.+' "$BACKEND/.env" 2>/dev/null && \
   grep -qE '^AWS_S3_BUCKET=.+' "$BACKEND/.env" 2>/dev/null; then
  echo "==> syncing uploads from S3..."
  cd "$BACKEND"
  if [ -f .venv/bin/activate ]; then
    # shellcheck disable=SC1091
    source .venv/bin/activate
  fi
  export PYTHONPATH=.
  python scripts/sync_media_from_s3.py --prefix uploads/
else
  echo "    skip S3 sync (AWS_* not set in backend/.env)"
  echo "    If images are missing, add S3 credentials or copy files into $MEDIA_ROOT"
fi

echo "==> sample contest image check"
SAMPLE="$MEDIA_ROOT/9/cb15b76a-d384-444f-99d6-8527d198f166.jpg"
if [ -f "$SAMPLE" ]; then
  echo "    OK $SAMPLE exists"
else
  echo "    WARN missing $SAMPLE"
fi
