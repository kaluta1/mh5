#!/usr/bin/env bash
# Apply MH5 NOWPayments pay-in keys to backend/.env (VPS).
# Payouts still need dashboard email/password + Authenticator TOTP secret.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${ROOT}/backend/.env"

# MH5 production NOWPayments account (pay-in)
NP_API_KEY="${NOWPAYMENTS_API_KEY_OVERRIDE:-MVMSTBP-17K4MDK-NX6FDFQ-2Q9DSEF}"
NP_IPN_SECRET="${NOWPAYMENTS_IPN_SECRET_OVERRIDE:-6p+2u0dV0MxkO9j+PirVQaEKz+O50x85}"

if [ ! -f "$ENV_FILE" ]; then
  echo "ERROR: $ENV_FILE not found" >&2
  exit 1
fi

set_env_replace() {
  local key="$1"
  local value="$2"
  python3 - "$ENV_FILE" "$key" "$value" <<'PY'
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
key = sys.argv[2]
value = sys.argv[3]
text = path.read_text(encoding="utf-8") if path.exists() else ""
lines = text.splitlines()
out = []
found = False
for line in lines:
    if line.startswith(f"{key}="):
        out.append(f"{key}={value}")
        found = True
    else:
        out.append(line)
if not found:
    if out and out[-1] != "":
        out.append("")
    out.append(f"{key}={value}")
path.write_text("\n".join(out) + "\n", encoding="utf-8")
PY
  echo "    set ${key}"
}

echo "==> apply NOWPayments MH5 pay-in keys"
set_env_replace "NOWPAYMENTS_API_KEY" "$NP_API_KEY"
set_env_replace "NOWPAYMENTS_IPN_SECRET" "$NP_IPN_SECRET"
set_env_replace "NOWPAYMENTS_SANDBOX" "false"

# Same account: use pay-in key for payouts unless a dedicated payout key is already set
current_payout="$(grep -E '^NOWPAYMENTS_PAYOUT_API_KEY=' "$ENV_FILE" 2>/dev/null | tail -1 | cut -d= -f2- || true)"
if [ -z "$current_payout" ]; then
  set_env_replace "NOWPAYMENTS_PAYOUT_API_KEY" "$NP_API_KEY"
  echo "    NOWPAYMENTS_PAYOUT_API_KEY defaulted to pay-in API key"
fi

echo ""
echo "Pay-in keys updated. Affiliate payouts still need (same as SmartBlogger):"
echo "  NOWPAYMENTS_EMAIL=...          # NOWPayments dashboard login"
echo "  NOWPAYMENTS_PASSWORD=...       # NOWPayments dashboard password"
echo "  NOWPAYMENTS_PAYOUT_TOTP_SECRET=...  # Authenticator 2FA secret (not email 2FA)"
echo ""
echo "Then: bash scripts/restart_mh5_backend.sh"
