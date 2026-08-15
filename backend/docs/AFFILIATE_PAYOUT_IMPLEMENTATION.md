# MH5 Affiliate Commissions & NOWPayments Payout

Implementation reference for auto-payout, wallet configuration, and manual withdrawal.

## Commission rules

| Product | Price | L1 | L2–L10 |
|---------|-------|----|--------|
| KYC | $10 | 10% ($1) | 1% each ($0.10) |
| MFM / Founding | $100 | 10% ($10) | 1% each ($1) |
| Annual membership | $50 | 10% ($5) | 1% each ($0.50) |

Founding pool (2104 → 2105) remains a **monthly admin batch**, separate from instant affiliate payout.

## Commission status flow (Policy B)

```
Referral payment validated
        │
        ▼
 Sponsor has payout wallet?
   No ──► PENDING (until wallet saved)
   Yes ─► APPROVED
        │
        ▼
 NOWPayments payout configured?
   No ──► stays APPROVED (manual withdraw available)
   Yes ─► auto-payout ─► PAID
```

- **PENDING**: no wallet on file
- **APPROVED**: accrued, ready for auto or manual payout
- **PAID**: sent via NOWPayments (reference stored in `payout_reference`)

## Environment variables

Add to `backend/.env` (see `.env.vps.example`):

```env
NOWPAYMENTS_PAYOUT_API_KEY=
NOWPAYMENTS_EMAIL=
NOWPAYMENTS_PASSWORD=
NOWPAYMENTS_PAYOUT_TOTP_SECRET=
```

Existing pay-in vars (`NOWPAYMENTS_API_KEY`, etc.) are unchanged.

**NOWPayments dashboard (same as SmartBlogger):**

1. Enable **Payout API**
2. Enable **Authenticator app 2FA** on payouts (**not email 2FA**)
3. Copy the TOTP secret shown once into `NOWPAYMENTS_PAYOUT_TOTP_SECRET`
4. Set dashboard login as `NOWPAYMENTS_EMAIL` / `NOWPAYMENTS_PASSWORD`

Payouts will not send until all four are set. Check: `GET /api/v1/admin/affiliate/payout-status`

## Database migration

```bash
cd backend && alembic upgrade head
```

Revision `r2s3t4u5v6w7` adds:

- `users.usdt_wallet_address`, `users.payout_currency`
- `affiliate_commissions.payout_reference`
- `affiliate_cashout_requests` audit table

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/users/me/wallet` | Payout wallet config |
| PATCH | `/api/v1/users/me/wallet` | Save wallet; pays pending commissions |
| GET | `/api/v1/wallet/balance` | PAID = available; PENDING+APPROVED = pending |
| GET | `/api/v1/wallet/withdraw/preview` | Fee preview (min $100) |
| POST | `/api/v1/wallet/withdraw` | Manual batch withdrawal |
| POST | `/api/v1/admin/affiliate/retry-payouts` | Retry stuck APPROVED payouts |

## Manual withdrawal

- Minimum: **$100**
- Fee: **1%** (min $20, max $1,000) via `cashout_fee_and_net()`
- Marks commissions PAID (FIFO) and creates one `AffiliateCashoutRequest` row

## Supported payout currencies

- `usdtbsc` — BEP20 (default)
- `usdterc20` — ERC20
- `usdttrc20` — TRC20

Validation: `app/services/wallet_validation.py`

## Critical NOWPayments notes

1. **Never send `extra_id` on BEP20 USDT payouts** — causes silent REJECTED status.
2. Payout flow: POST `/payout` → POST `/payout/{id}/verify` with TOTP.
3. JWT cached ~4.5 minutes (`nowpayments_service.py`).

## Frontend

- **Settings → Wallet tab** (`/dashboard/settings?tab=wallet`): save payout address + network
- **Wallet page**: banner if no wallet; Withdraw dialog for manual batch
- **Payment dialog**: crypto currency picker from `/api/v1/payments/currencies`
- **Commissions page**: filter/badge for `approved` status

## Deploy checklist

1. Set payout env vars on VPS
2. `alembic upgrade head`
3. Restart backend: `bash scripts/restart_mh5_backend.sh`
4. Rebuild frontend: `npm run build && pm2 restart mh5-frontend`
5. Test: save wallet → trigger commission → verify PAID + `payout_reference`

## Admin retry

If auto-payout fails transiently, commissions stay APPROVED:

```bash
curl -X POST "https://api.myhigh5.com/api/v1/admin/affiliate/retry-payouts" \
  -H "Authorization: Bearer <admin_token>"
```

Optional: `?user_id=123&limit=50`
