# MyHigh5 — Complete Chart of Accounts & Distribution Model (Singapore-oriented)

This document is the **authoritative business + accounting map** for MyHigh5.  
Implementation: CoA seed `app/scripts/init_coa.py`, posting `app/services/payment_accounting.py`, **pure math** `app/accounting/distribution_formulas.py`, frontend helpers `frontend/lib/accounting/coa.ts`.

---

## 1. Principles

| Principle | Application |
|-----------|-------------|
| **Accrual basis** | Recognise revenue when earned and liabilities when incurred; align with Singapore expectations for true and fair financial statements. |
| **Immutable ledger** | Posted journal lines are not edited; corrections via **reversal or delta journals** with **maker–checker** approval. |
| **Agent model (clubs)** | The platform collects subscription cash; **base subscription** is a **payable to the club owner**, not platform revenue. Only the **20% markup** is platform economic margin (then split per policy). |
| **Missing affiliate levels** | Amounts that would have gone to unfilled sponsor levels are **website / platform revenue** (see §5). |
| **Nomination contests** | Geographic voting rules in the product may treat nomination as **country-level**; this doc focuses on **money flows** and CoA codes. |
| **Minimum cashout** | **$100** minimum before a member may request withdrawal (policy); see §7. |

---

## 2. Full chart of accounts (seeded codes)

### 2.1 Assets (1000)

| Code | Name | Notes |
|------|------|--------|
| 1000 | Assets | Header |
| 1001 | Platform Wallet | Cash / PSP balance in platform control |
| 1200 | Accounts Receivable | Optional: ad network accruals if any |

### 2.2 Liabilities (2000)

| Code | Name | Notes |
|------|------|--------|
| 2000 | Liabilities | Header |
| 2001 | Commissions Payable — Level 1 | Affiliate L1 |
| 2002 | Commissions Payable — Levels 2–10 | Affiliate L2–L10 |
| 2003 | Service Fees Payable (KYC) | e.g. Shufti |
| 2100 | User Funds Payable | Member wallet balances |
| 2104 | Founding Members Pool Payable | Contractual pool accrual |
| 2110 | Deferred Revenue — Annual Membership | Time-based release (policy) |
| 2111 | Deferred Revenue — Founding Membership | Alternative: immediate recognition per legal terms |
| 2112 | Deferred Platform Fee — Club Subscriptions | Markup portion deferred over subscription term |
| 2120 | Club Owner Subscription Payable (Agent) | Pass-through to club owner |
| 2130 | Member Ad Revenue Share Payable | Participant / nominator earned share |
| 2200 | GST Payable (Singapore) | When registered |

### 2.3 Equity (3000)

| Code | Name |
|------|------|
| 3000 | Equity |
| 3001 | Retained Earnings |

### 2.4 Revenue (4000)

| Code | Name | Typical use |
|------|------|-------------|
| 4000 | Revenue | Header |
| 4001 | KYC Revenue | KYC verification product |
| 4002 | Membership Revenue | Annual / founding membership recognition |
| 4003 | Platform Revenue (Net) | Residual platform share after splits |
| 4004 | Ad Revenue — Platform Retained | Platform share after ad splits |
| 4005 | Cashout Fee Revenue | Fee on member withdrawals |
| 4006 | Club Platform Service Fee Revenue | Recognised from **markup** on club subs |

### 2.5 Expenses (5000)

| Code | Name |
|------|------|
| 5000 | Expenses |
| 5001 | Commission Expense | Mirror of affiliate accruals (when expensed) |
| 5002 | KYC Provider Expense | Provider cost |
| 5003 | Ad Revenue Share to Members (Expense) | Optional P&L mirror |

---

## 3. Distribution rules (summary)

All **percentage** shares below are **of gross** (membership fee or ad revenue) unless stated otherwise.

### 3.1 Annual membership fee (e.g. $10)

| Recipient | Rule |
|-----------|------|
| Level 1 sponsor | 10% of gross |
| Levels 2–10 | 1% of gross **each** (filled levels only; missing → platform) |
| Founding Members pool | 10% of gross → **2104** |
| Shufti (KYC provider) | **$2** fixed from this product (when applicable) |
| Website revenue | **Remainder** → **4003** (via **4002** recognition net of accruals in posting logic) |

### 3.2 Founding Membership fee (e.g. $100)

| Recipient | Rule |
|-----------|------|
| Level 1 sponsor | 10% |
| Levels 2–10 | 1% each |
| Founding Members pool | 10% |
| Website revenue | Remainder |

### 3.3 Ad revenue — **participant** page (gross = ad revenue on that page)

| Recipient | Rule |
|-----------|------|
| Participant (content owner) | 40% |
| Level 1 sponsor | 5% |
| Levels 2–10 | 1% each |
| Founding Members pool | 10% |
| Website revenue | Remainder |

### 3.4 Ad revenue — **nominator** page

| Recipient | Rule |
|-----------|------|
| Nominator | 10% |
| Level 1 sponsor | 2.5% |
| Levels 2–10 | 1% each |
| Founding Members pool | 10% |
| Website revenue | Remainder |

### 3.5 Club membership subscription (20% markup)

Club owners set **paid membership clubs** with a **base subscription price** and billing cadence (**monthly**, **quarterly**, **semi-annual**, or **annual**). The member’s charge is **base × 1.2** (20% platform markup on top of the owner’s price).

Let **base** = club owner’s list price for one billing period. Customer pays **base × 1.2**.

| Bucket | Accounting |
|--------|--------------|
| **Base** | Liability **2120** (payable to club owner — agent), not platform revenue |
| **Markup (20%)** | Platform margin: split **only from markup**: L1 sponsor of the payer **10%** of markup; levels **2–10** **1% each** of markup (filled levels only; missing slots accrue to platform per §1); **10%** of markup to **Founding Members pool (2104)**; **remainder** of markup to platform revenue **4003** / **4006** per recognition policy and **2112** deferral over the subscription term |

Automated **daily** (or periodic) **release** of deferred amounts (base vs markup) should follow the club’s subscription term and settlement buffer (e.g. T+7) — implement as scheduled journals, not manual edits.

### 3.6 Cashout fee (on withdrawal)

- Fee = **1%** of requested amount  
- **Minimum** fee **$20**, **maximum** **$1,000**  
- Recognise fee as **4005**; pay **net** to member; debit member payable **2100**

---

## 4. Worked examples (all sponsors L2–10 present)

Amounts rounded to **$0.01**. Code: `distribution_formulas.py` / `frontend/lib/accounting/coa.ts`.

### 4.1 Annual membership **$10.00**

| Line | Amount |
|------|--------|
| Level 1 | $1.00 |
| Levels 2–10 (9 × 1%) | $0.90 |
| Founding pool | $1.00 |
| Shufti | $2.00 |
| **Platform net** | **$5.10** |
| **Check** | $1.00 + $0.90 + $1.00 + $2.00 + $5.10 = **$10.00** |

### 4.2 Founding membership **$100.00**

| Line | Amount |
|------|--------|
| Level 1 | $10.00 |
| Levels 2–10 | $9.00 |
| Founding pool | $10.00 |
| **Platform net** | **$71.00** |

### 4.3 Ad revenue **$100** — participant page

| Line | Amount |
|------|--------|
| Participant | $40.00 |
| Level 1 | $5.00 |
| Levels 2–10 | $9.00 |
| Founding pool | $10.00 |
| **Platform net** | **$36.00** |

### 4.4 Ad revenue **$100** — nominator page

| Line | Amount |
|------|--------|
| Nominator | $10.00 |
| Level 1 | $2.50 |
| Levels 2–10 | $9.00 |
| Founding pool | $10.00 |
| **Platform net** | **$68.50** |

### 4.5 Club subscription — base **$100** (charge **$120**)

| Line | Amount |
|------|--------|
| To club owner (2120) | $100.00 |
| Markup | $20.00 |
| From **markup** — Level 1 | $2.00 |
| From **markup** — L2–10 | $1.80 |
| From **markup** — pool | $2.00 |
| From **markup** — platform net | **$14.20** |

### 4.6 Cashout fee examples

| Request | 1% | Fee (after min/max) | Net to member |
|---------|-----|---------------------|---------------|
| $100 | $1.00 | **$20** | $80 |
| $5,000 | $50 | $50 | $4,950 |
| $200,000 | $2,000 | **$1,000** (cap) | $199,000 |

---

## 5. Missing sponsor levels

- **Level 1 missing:** the **10%** intended for L1 accrues to **platform revenue** (same for each product line).  
- **Levels 2–10:** only **filled** slots receive 1% each; **unfilled** portions stay with **platform**.

The helper functions take `levels_2_to_10_filled` in **Python** (`0–9`) and the same in **TypeScript** helpers.

---

## 6. Financial statement mapping

| Statement | CoA usage |
|-----------|-----------|
| **Balance sheet** | **1001** assets; **2001–2200** payables & deferred; **2100** member balances; **3001** equity |
| **Income statement** | **4001–4006** revenue; **5001–5003** expenses |
| **Trial balance / GL** | All posted accounts with period filters |

Reporting cadence (daily / weekly / monthly / quarterly / semi-annual / annual) is a **reporting layer** on the same immutable journals: filter `entry_date` (and fiscal period once **accounting periods** are enforced in app).

---

## 7. Operational controls (recommended)

- **Maker–checker** on corrections and high-risk payouts.  
- **Period lock** before close (no new posts to closed periods without override).  
- **Audit trail** on all financial mutations.  
- **$100** minimum cashout: enforce in **workflow** before creating payable settlement.

---

## 8. Code references

### DB model notes

- `chart_of_accounts.balance` (migration `002_add_myfav_models`) is the denormalized cached amount; **authoritative** balances are computed from `journal_lines` via `AccountingService.get_balance`.
- `journal_entries` / `journal_lines` are created by migration `a7f3e2d1c4b8_accounting_align_coa_and_journal_tables` if missing.
- `ChartOfAccounts` uses `SQLEnum(..., native_enum=False)` so Postgres legacy ENUMs or VARCHAR both work.

| Artifact | Path |
|----------|------|
| CoA seed | `app/scripts/init_coa.py` |
| Payment posting | `app/services/payment_accounting.py` |
| Distribution math | `app/accounting/distribution_formulas.py` |
| Tests | `tests/test_distribution_formulas.py` |
| Frontend CoA + calculators | `frontend/lib/accounting/coa.ts` |
| Admin UI (read-only views) | `frontend/components/admin/admin-accounting.tsx` |

---

## 9. Open policy items (legal / tax)

- Final **Founding Membership** revenue recognition (immediate vs deferred) vs membership agreement.  
- **GST** registration threshold and **400x/2200** mapping when applicable.  
- **Club** refund and chargeback policy vs agent terms (affects **2120** and deferred release).  

These do not change the **CoA structure**; they change **timing** and **journal templates**.
