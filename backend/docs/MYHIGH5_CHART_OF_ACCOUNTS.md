# MyHigh5 Chart of Accounts (Singapore-oriented)

This document maps MyHigh5 payment flows to ledger accounts seeded by `app/scripts/init_coa.py`.  
Posting logic should use these codes (or resolve by stable `account_code`) so the CoA stays scalable.

## Distribution reference (business rules)

| Flow | Key splits (of gross or stated base) |
|------|--------------------------------------|
| Annual $10 | L1 10%; L2–L10 1% each; pool 10%; Shufti $2; remainder **platform revenue** |
| Founding $100 | L1 10%; L2–L10 1% each; pool 10%; remainder **platform revenue** |
| Ad share (participant page) | Member 40%; L1 5%; L2–L10 1% each; pool 10%; remainder **platform** |
| Ad share (nominator page) | Member 10%; L1 2.5%; L2–L10 1% each; pool 10%; remainder **platform** |
| Club subscription (charge = base × 1.2) | Base → **2120** payable to owner; markup → defer **2112**, recognise **4006** over term; from markup: L1 10%, L2–L10 1% each, pool 10%, remainder **4003/4006** per policy |
| Missing sponsor levels | Treated as **platform revenue** (4003/4004 as applicable) |
| Cashout | Min threshold $100 to request; fee 1% min $20 max $1,000 → **4005** |

## Account codes (summary)

| Code | Name | Typical use |
|------|------|-------------|
| 1001 | Platform Wallet | Cash / settlement in transit |
| 2001 / 2002 | Commissions Payable L1 / L2–10 | Accrued affiliate commissions |
| 2003 | Service Fees Payable (KYC) | Shufti and similar |
| 2100 | User Funds Payable | Member wallet balances |
| 2104 | Founding Members Pool Payable | Pool accrual |
| 2110–2112 | Deferred revenue (annual / founding / club markup) | Accrual / IFRS 15-style release |
| 2120 | Club Owner Subscription Payable | Agent: pass-through to club owner |
| 2130 | Member Ad Revenue Share Payable | Participant / nominator earned share |
| 2200 | GST Payable | Singapore GST when registered |
| 4001–4002 | KYC / Membership Revenue | Recognised fee income |
| 4003 | Platform Revenue (Net) | Residual after splits |
| 4004 | Ad Revenue - Platform Retained | Platform share after ad splits |
| 4005 | Cashout Fee Revenue | Payout fees |
| 4006 | Club Platform Service Fee Revenue | Markup portion of club subs |
| 5001–5003 | Commission / KYC / member share expense | P&L mirror of accruals where used |

## Notes

- **Accrual**: recognise income when earned and obligations when incurred; keep an immutable journal trail in the application ledger.
- **Agent model (clubs)**: base subscription is liability **2120**, not platform revenue.
- **Corrections**: only via reversing or approved correction entries (maker-checker), not edits to posted lines.
