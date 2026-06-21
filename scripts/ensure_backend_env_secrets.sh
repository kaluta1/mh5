#!/usr/bin/env bash
# Ensure backend/.env has secrets required when ENVIRONMENT=production.
# Generates missing keys once — never overwrites existing values.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${ROOT}/backend/.env"

if [ ! -f "$ENV_FILE" ]; then
  echo "ERROR: $ENV_FILE not found" >&2
  exit 1
fi

get_env() {
  local key="$1"
  grep -E "^${key}=" "$ENV_FILE" 2>/dev/null | tail -1 | cut -d= -f2- | sed 's/^["'\''"]//;s/["'\''"]$//' || true
}

set_env_if_missing() {
  local key="$1"
  local value="$2"
  if [ -n "$(get_env "$key")" ]; then
    return 0
  fi
  echo "${key}=${value}" >> "$ENV_FILE"
  echo "    added ${key} to backend/.env"
}

rand_hex() {
  python3 -c "import secrets; print(secrets.token_hex($1))"
}

echo "==> ensure backend/.env secrets"

# SECRET_KEY (JWT) — min 32 chars
SK="$(get_env SECRET_KEY)"
if [ -z "$SK" ] || [ "${#SK}" -lt 32 ]; then
  set_env_if_missing "SECRET_KEY" "$(rand_hex 32)"
fi

set_env_if_missing "MASTER_ENCRYPTION_KEY" "$(rand_hex 32)"
set_env_if_missing "ENCRYPTION_KEY_DERIVATION_SALT" "$(rand_hex 16)"

if ! grep -qE '^ENVIRONMENT=' "$ENV_FILE"; then
  echo "ENVIRONMENT=production" >> "$ENV_FILE"
  echo "    added ENVIRONMENT=production"
fi

echo "    OK required secrets present in backend/.env"
