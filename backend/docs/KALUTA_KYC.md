# Kaluta KYC (default provider)

MyHigh5 uses **Kaluta KYC** for identity verification. **Shufti Pro** remains in the codebase as a legacy provider (`KYC_PROVIDER=shufti_pro`).

## Environment variables

```env
KYC_PROVIDER=kaluta
KALUTA_API_KEY=klt_...
KALUTA_WEBHOOK_SECRET=whsec_...   # from Kaluta Dashboard → Webhooks
```

Optional overrides:

```env
KALUTA_WEBHOOK_URL=https://api.myhigh5.com/api/v1/kyc/webhook/kaluta
KALUTA_REDIRECT_URL=https://myhigh5.com/dashboard/kyc
```

Defaults are derived from `BACKEND_PUBLIC_URL` and `FRONTEND_URL`.

## Flow

1. User pays $10 KYC fee (NOWPayments) — unchanged.
2. `POST /api/v1/kyc/initiate` creates a Kaluta session server-side (API key never exposed to browser).
3. Frontend opens `KalutaKYC.open({ url: verification_url })` via `embed.js`.
4. Kaluta webhook `POST /api/v1/kyc/webhook/kaluta` updates verification status.
5. User completes MH5 proof-of-address step unless Kaluta PoA is enabled and passed in-session.

## Kaluta dashboard setup

1. Add webhook endpoint: `{BACKEND_PUBLIC_URL}/api/v1/kyc/webhook/kaluta`
2. Subscribe to: `session.approved`, `session.verified`, `session.rejected`, `session.expired`
3. Copy webhook signing secret → `KALUTA_WEBHOOK_SECRET`

## Debug

`GET /api/v1/kyc/deployment/kaluta-urls` (authenticated) — shows webhook/redirect URLs without secrets.

## Legacy Shufti Pro

Set `KYC_PROVIDER=shufti_pro` and configure `SHUFTI_CLIENT_ID`, `SHUFTI_SECRET_KEY`. Webhook: `/api/v1/kyc/webhook/shufti-pro`.

Code: `backend/app/services/shufti_pro.py` (unchanged, aside from dispatch layer).
