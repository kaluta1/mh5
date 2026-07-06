#!/usr/bin/env bash
# Ensure backend/.env has secrets required when ENVIRONMENT=production.
# Generates missing keys once; fixes localhost public URLs on VPS deploy.
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

set_env_replace() {
  local key="$1"
  local value="$2"
  if grep -qE "^${key}=" "$ENV_FILE"; then
    sed -i.bak "s|^${key}=.*|${key}=${value}|" "$ENV_FILE"
  else
    echo "${key}=${value}" >> "$ENV_FILE"
  fi
  echo "    set ${key}=${value}"
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

ENV_VAL="$(get_env ENVIRONMENT)"
if echo "$ENV_VAL" | grep -qiE '^(dev|development|local)$'; then
  set_env_replace "ENVIRONMENT" "production"
fi

if ! grep -qE '^FRONTEND_URL=' "$ENV_FILE"; then
  echo "FRONTEND_URL=https://myhigh5.com" >> "$ENV_FILE"
  echo "    added FRONTEND_URL=https://myhigh5.com"
fi

if ! grep -qE '^BACKEND_PUBLIC_URL=' "$ENV_FILE"; then
  echo "BACKEND_PUBLIC_URL=https://myhigh5.com" >> "$ENV_FILE"
  echo "    added BACKEND_PUBLIC_URL=https://myhigh5.com"
fi

# Replace loopback public URLs left from local dev copies
for key in FRONTEND_URL BACKEND_PUBLIC_URL NEXT_PUBLIC_API_URL API_BASE_URL; do
  val="$(get_env "$key")"
  if [ -n "$val" ] && echo "$val" | grep -qiE 'localhost|127\.0\.0\.1'; then
    if [ "$key" = "FRONTEND_URL" ] || [ "$key" = "BACKEND_PUBLIC_URL" ] || [ "$key" = "NEXT_PUBLIC_API_URL" ] || [ "$key" = "API_BASE_URL" ]; then
      set_env_replace "$key" "https://myhigh5.com"
    fi
  fi
done

# NOWPayments — must be set manually (cannot auto-generate)
NP_KEY="$(get_env NOWPAYMENTS_API_KEY)"
NP_IPN="$(get_env NOWPAYMENTS_IPN_SECRET)"
if [ -z "$NP_KEY" ] || [ -z "$NP_IPN" ]; then
  echo "    WARN: NOWPAYMENTS_API_KEY and/or NOWPAYMENTS_IPN_SECRET missing in backend/.env"
  echo "          Crypto checkout will return 502 until both are set, then: systemctl restart myhigh5-backend"
else
  echo "    OK NOWPayments keys present"
fi

if ! grep -qE '^NOWPAYMENTS_DEFAULT_PAY_CURRENCY=' "$ENV_FILE"; then
  echo "NOWPAYMENTS_DEFAULT_PAY_CURRENCY=usdttrc20" >> "$ENV_FILE"
  echo "    added NOWPAYMENTS_DEFAULT_PAY_CURRENCY=usdttrc20"
fi

if ! grep -qE '^NOWPAYMENTS_UNDERPAYMENT_TOLERANCE_USD=' "$ENV_FILE"; then
  echo "NOWPAYMENTS_UNDERPAYMENT_TOLERANCE_USD=0.5" >> "$ENV_FILE"
  echo "    added NOWPAYMENTS_UNDERPAYMENT_TOLERANCE_USD=0.5"
fi

echo "    OK required secrets present in backend/.env"
