#!/usr/bin/env bash
# Apply idempotent DDL as postgres superuser when the app role cannot ALTER TABLE.
# Safe to re-run. Also stamps alembic_version for wallet/KYC revisions.
#
# Run ON THE VPS as root:
#   bash scripts/apply_vps_db_migrations.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SQL_FILE="${ROOT}/backend/scripts/neon_manual_migrations.sql"

if [ ! -f "$SQL_FILE" ]; then
  echo "ERROR: missing ${SQL_FILE}" >&2
  exit 1
fi

ENV_FILE="${ROOT}/backend/.env"
DB_URL="$(grep -E '^DATABASE_URL=' "$ENV_FILE" | tail -1 | cut -d= -f2- | tr -d '"'"'"'"' || true)"
DB_NAME="$(
  python3 - <<PY
from urllib.parse import urlparse
u = urlparse("""${DB_URL}""")
print((u.path or "/mh5db").lstrip("/") or "mh5db")
PY
)"

echo "==> apply VPS manual migrations on ${DB_NAME}"

if id postgres >/dev/null 2>&1; then
  sudo -u postgres psql -v ON_ERROR_STOP=1 -d "${DB_NAME}" -f "${SQL_FILE}"
else
  psql -v ON_ERROR_STOP=1 -d "${DB_NAME}" -f "${SQL_FILE}"
fi

echo "    OK manual migrations applied"
