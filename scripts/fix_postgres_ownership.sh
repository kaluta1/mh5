#!/usr/bin/env bash
# Transfer public schema object ownership to the app DB user (fixes alembic
# "must be owner of table users" on VPS when tables were created as postgres).
#
# Run ON THE VPS as root:
#   bash scripts/fix_postgres_ownership.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${ROOT}/backend/.env"

if [ ! -f "$ENV_FILE" ]; then
  echo "ERROR: missing ${ENV_FILE}" >&2
  exit 1
fi

DB_URL="$(grep -E '^DATABASE_URL=' "$ENV_FILE" | tail -1 | cut -d= -f2- | tr -d '"'"'"'"' || true)"
if [ -z "$DB_URL" ]; then
  echo "ERROR: DATABASE_URL not set in ${ENV_FILE}" >&2
  exit 1
fi

read -r DB_USER DB_NAME DB_HOST DB_PORT <<<"$(
  python3 - <<PY
from urllib.parse import urlparse
u = urlparse("""${DB_URL}""")
print(u.username or "mh5_user", end=" ")
print((u.path or "/mh5db").lstrip("/") or "mh5db", end=" ")
print(u.hostname or "localhost", end=" ")
print(u.port or 5432)
PY
)"

if ! command -v psql >/dev/null 2>&1; then
  echo "ERROR: psql not installed" >&2
  exit 1
fi

if [ "$DB_HOST" != "localhost" ] && [ "$DB_HOST" != "127.0.0.1" ]; then
  echo "ERROR: this script only supports local Postgres (got host ${DB_HOST})" >&2
  exit 1
fi

echo "==> fix postgres ownership for database ${DB_NAME} → role ${DB_USER}"

run_psql() {
  if id postgres >/dev/null 2>&1; then
    sudo -u postgres psql -v ON_ERROR_STOP=1 "$@"
  else
    psql -v ON_ERROR_STOP=1 "$@"
  fi
}

run_psql -d postgres -c "SELECT 1 FROM pg_database WHERE datname = '${DB_NAME}';" | grep -q 1 || {
  echo "ERROR: database ${DB_NAME} not found" >&2
  exit 1
}

run_psql -d postgres <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '${DB_USER}') THEN
    RAISE EXCEPTION 'role ${DB_USER} does not exist';
  END IF;
END \$\$;

ALTER DATABASE ${DB_NAME} OWNER TO ${DB_USER};
SQL

run_psql -d "${DB_NAME}" <<SQL
DO \$\$
DECLARE
  r RECORD;
  kind_sql TEXT;
BEGIN
  FOR r IN
    SELECT c.relkind, c.relname
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public'
      AND c.relkind IN ('r', 'S', 'v', 'm')
  LOOP
    kind_sql := CASE r.relkind
      WHEN 'S' THEN 'SEQUENCE'
      WHEN 'v' THEN 'VIEW'
      WHEN 'm' THEN 'MATERIALIZED VIEW'
      ELSE 'TABLE'
    END;
    EXECUTE format('ALTER %s public.%I OWNER TO ${DB_USER}', kind_sql, r.relname);
  END LOOP;
END \$\$;

DO \$\$
DECLARE r RECORD;
BEGIN
  FOR r IN
    SELECT t.typname
    FROM pg_type t
    JOIN pg_namespace n ON n.oid = t.typnamespace
    WHERE n.nspname = 'public'
      AND t.typtype = 'e'
  LOOP
    EXECUTE format('ALTER TYPE public.%I OWNER TO ${DB_USER}', r.typname);
  END LOOP;
END \$\$;
SQL

echo "    OK ownership updated for ${DB_NAME}.${DB_USER}"
