# Premium Clubs, Memberships & Digital Marketplace Repair Report

Audit date: 2026-09-09  
Project: `kalutafoundation`  
Implementation status: **PARTIAL — safe dormant state retained; not ready to activate or deploy**

No production data or schema was changed. No migration, payment, payout, refund,
email request, external fulfillment, service restart, or deployment was run.

## 1. Club architecture

The principal club-shaped persistence model is:

`fan_clubs` → `club_admins`, `club_memberships`, `club_content` → comments/likes,
plus `club_wallets` → `club_transactions` → `transaction_approvals`.

`users.id` owns clubs, administers clubs, and identifies members. The only
registered runtime exposure is authenticated search (`/api/v1/search` and
`/api/v1/search/clubs`). The draft club router imports a nonexistent
`app.crud.crud_clubs` module and is intentionally not registered.

Generic Prompt 6 payments know a `club_membership` product type, and generic
commission/accounting code knows that product code. There is no durable key
from a deposit to a specific club, plan/period, membership, or club owner.

## 2. Club active/legacy systems

| Subsystem | Classification | Evidence |
|---|---|---|
| `fan_clubs` family | CANONICAL CANDIDATE / UNFINISHED | Imported ORM metadata and active search use it; all production rows are zero. |
| Club search | ACTIVE, READ-ONLY | Router is registered. Private and inactive rows are now filtered out. |
| `endpoints/clubs.py` | UNFINISHED / DISABLED | Not registered and depends on absent CRUD. |
| `models/club.py` (`club`, `club_members`, join requests/private groups) | LEGACY | Separate generation; not the model used by search/current imported club family. |
| Hard-coded `/clubs` cards | DEMO / NON-AUTHORITATIVE | No API or production records back the cards. Transactional controls are now disabled and the page identifies itself as preview-only. |
| `club_wallets` | LEGACY/PARTIAL STORED BALANCE | Not Prompt 6's canonical ledger and has no production rows. |

There is therefore no active transactional club system to call canonical.
`fan_clubs` is the best persistence candidate, but activation requires the
schema and workflow work listed below.

## 3. Club business model

Evidence supports paid monthly/annual fan clubs, owner-managed content,
optional approval, public/private visibility, and multi-admin approvals. The
database product catalog contains an active fixed `club_membership` product at
USD 4.99 for 30 days. Separately, each `fan_clubs` row can have a
`premium_fee` and annual discount.

The fee policy is contradictory:

- accounting/formula code uses a 20% platform markup over a club-selected base;
- public contact copy says 10% markup;
- product catalog fixes the charge at USD 4.99;
- commission rules say 1.67% direct/0.17% indirect, while product fields say
  10%/1% and other public copy says 20%/2%.

No rate was invented or silently selected. Product activation remains blocked
until the owner selects one authoritative policy and price source.

## 4. Membership lifecycle

The stored enum only supports `ACTIVE`, `SUSPENDED`, `EXPIRED`, and
`CANCELLED`; it has no pending-payment or refunded state. The new shared
integrity helper explicitly permits safe transitions and rejects terminal-state
reactivation. A membership cannot safely be created as active on checkout with
the present schema, so the transactional router remains disabled.

Required target workflow: durable server-priced payment intent → confirmed
provider payment processed by Prompt 6 → atomic membership activation with a
unique payment link. This workflow is documented, not falsely implemented.

## 5. Membership entitlement

`membership_is_entitled` now defines the fail-closed rule: payment must be
authoritatively confirmed and not refunded; club and membership IDs must match;
both must be active; and the current UTC instant must be inside the stored
membership interval. Client flags alone never grant access.

Existing club content has no active endpoint. A durable payment/refund link is
still required before this helper can be connected to live access control.

## 6. Club authorization

The disabled draft router generally derives owner/member IDs from the current
user, but its DTOs and missing CRUD prevent reliable end-to-end enforcement.
`require_owner` provides a centralized fail-closed ownership primitive and has
IDOR regression coverage. Public search no longer reveals private, suspended,
or closed clubs. Owner/admin/member permission matrices still require a real
service implementation and audit-event model before router activation.

## 7. Club payment flow

Prompt 6's canonical deposit validation is the only acceptable payment path.
Client price validation now reuses the Prompt 6 Decimal and authoritative-term
validators. The current generic `club_membership` validation can create
commissions and a journal, but does not identify a club or create a membership.
It must not be treated as a complete club payment.

Production: zero club-membership deposits and zero club-membership affiliate
commissions were found.

## 8. Club hold/escrow model

No canonical club hold or escrow model exists. `club_wallets` contains stored
balance totals; `club_transactions` contains approvals, but neither is tied to
Prompt 6 journal entries or payout intents. All production values and row
counts are zero. These balances must not become spendable or authoritative.

## 9. Club payout

No functional club payout service exists. The draft endpoint would pass a raw
dictionary into missing CRUD and does not use the Prompt 6 payout saga. It
remains unreachable. Before activation, payouts require a committed intent,
Prompt 6 provider idempotency, an available-funds reservation, a club-benefit
source key, retry-safe result recording, and journal linkage.

## 10. Club refunds

Prompt 6 supports generic deposit reversals, accounting reversals, and
commission reversal. The current club schema cannot identify the affected
membership or revoke it, and it cannot determine whether owner funds were
held/paid. Club refunds therefore fail closed/manual review until durable source
links exist. Financial history must be preserved through compensating entries.

## 11. Club affiliate commissions

Code and production configuration confirm that club membership is intended to
be commissionable with at most 10 sponsor levels. Prompt 6's canonical
commission service must be reused. No commission was generated in this prompt.
Activation is blocked by the conflicting rates and missing club/payment source
identity. Production contains zero related commissions.

## 12. Marketplace architecture

The only marketplace-shaped persistence is the dormant DSP generation:

`dsp_wallets` → `dsp_transactions`; `dsp_exchange_rates`;
`digital_products` → `digital_purchases`; and `product_reviews`.

`DigitalPurchase` is simultaneously a purchase record and download token. It
is not a sufficient order/entitlement model: there is no lifecycle status,
currency/network identity, order/deposit/provider reference, refund/reversal,
hold/release, seller payout, delivery state, or ledger link.

## 13. Marketplace active/legacy systems

| Subsystem | Classification | Evidence |
|---|---|---|
| `digital_products` / `digital_purchases` / reviews | UNFINISHED CANONICAL CANDIDATE | ORM-imported, zero production rows, no registered API. |
| DSP wallets/transactions/exchange rates | PARTIAL / LEGACY FINANCIAL SYSTEM | Stored balances conflict with Prompt 6 source-of-truth requirements; only one exchange-rate row exists. |
| `endpoints/dsp.py` | UNFINISHED / DISABLED | Not registered and imports absent `crud_dsp`. |
| `/dashboard/shop` | UNFINISHED | Navigation references it, but no Next.js route exists. |
| Marketing/FAQ shop claims | DOCUMENTATION ONLY | They do not represent a working order or fulfillment system. |

There is no active marketplace system. The dormant model is not safe to expose.

## 14. Seller model

Products have `seller_id` and draft update code checks it, but no seller entity,
store, onboarding state, moderation state, payout account, or eligibility model
exists. The draft create endpoint only checks identity/address verification.
Central ownership checks were added, but seller onboarding and administrator
approval requirements remain a product decision and schema blocker.

## 15. Product model

The model supports one unspecified digital-file product type with title,
description, free-text category, three price fields (DSP/CAD/USD), currency,
file URL/type/size, preview, and counters. There is no inventory model; evidence
suggests unlimited digital goods. There are no supported service, license,
course, subscription, cart, tax, or third-party fulfillment implementations.

Server price validation is centralized and rejects a mismatched client amount.
The active `shop_purchase` product catalog price is USD 0.00, which the Prompt 6
positive-price validator correctly rejects. Variable-order pricing needs a
server-created order line model rather than relaxing that guard.

## 16. Product/media security

The model stores `file_url` directly and the draft seller DTO accepts it. It has
no private object key, Prompt 4 ownership record, signature/MIME verification,
or safe replacement/deletion lifecycle. A paid file could be publicly reachable
or seller-supplied. The router remains disabled. A future implementation must
reuse Prompt 4 upload validation and private storage; arbitrary seller URLs
cannot be accepted as paid assets.

## 17. Order/checkout

There is no cart or canonical order entity. The draft purchase endpoint accepts
only a product ID and method, but its CRUD implementation does not exist.
Prompt 6 payment intent cannot support the zero-priced variable `shop_purchase`
without a durable server-calculated order. No checkout was activated.

## 18. Order lifecycle

`DigitalPurchase` has no status at all, so unpaid, paid, delivered, completed,
cancelled, disputed, and refunded cannot be distinguished. Counters and a token
must not be interpreted as proof of payment. A real lifecycle and validated
transitions are **required for correctness**.

## 19. Seller earnings

Seller earnings are a numeric field on `DigitalPurchase`, with no pending,
held, available, paid, or reversed state and no canonical journal source. The
new split helper derives exact Decimal amounts from an explicit server-owned
rate and preserves gross = platform + seller, but it does not mutate balances.
Seller earnings must be posted and derived via Prompt 6 ledger services.

## 20. Platform fees

The model comment states 20%, but no authoritative marketplace pricing rule or
versioned order snapshot exists. Production commission configuration also
conflicts with public copy. The helper intentionally requires the server fee
rate as input instead of embedding a commercial policy. Tax/VAT and payment-fee
allocation are unsupported.

## 21. Marketplace hold/escrow

No order-linked hold exists. `dsp_wallets.frozen_balance` is a generic stored
field with no reservation identity, release event, journal link, or concurrency
version. It is not accepted as canonical escrow. Disputed/refundable seller
funds cannot safely become withdrawable until a hold/release state model exists.

## 22. Digital delivery

`purchase_allows_download` requires the authenticated buyer, matching product,
active product, authoritative payment confirmation, non-refunded payment, and a
remaining download allowance. This closes the intended authorization rule at
the service boundary. It is not wired to a route because the schema cannot
prove payment/refund state.

## 23. Download security

A token alone is insufficient. Tests cover wrong-buyer IDOR, unconfirmed
payment, refund revocation, product activity, product identity, and exhausted
download counts. The current direct `file_url` design cannot guarantee private
delivery or bounded signed URLs and is a required activation blocker.

## 24. Seller payout

No seller earning ledger or seller payout flow exists. DSP withdrawals/transfers
are draft stored-balance operations in missing CRUD, not Prompt 6 payouts. They
remain unreachable. A future seller payout must reserve only available,
non-disputed journal-derived earnings and reuse Prompt 6 payout intents and
idempotency.

## 25. Refund/disputes

No marketplace refund or dispute state exists. Generic Prompt 6 refund cannot
identify a purchase, entitlement, seller earning, or platform split. Full and
partial refunds therefore fail closed/manual review. Partial refunds must remain
unsupported until proportional allocation rules and source-linked compensating
entries are defined. No dispute platform was invented.

## 26. Affiliate integration

`shop_purchase` is configured as commissionable for up to 10 levels, but there
are zero related commissions and no order/payment artifacts. The canonical
Prompt 6 commission and reversal services are the only permitted integration.
The rate contradiction and missing order source key block activation and
duplicate-proof commission generation.

## 27. Admin controls

There are no registered club or marketplace admin routers for approval,
moderation, refunds, disputes, or payouts. The generic admin user-deletion path
knows about club memberships but is not an operational club console. Required
future controls need role checks, reason, actor, timestamp, immutable source,
valid transition checks, and canonical financial service calls. State-changing
GET operations must not be introduced.

## 28. Production read-only audit

The audit ran against `neondb` inside `SET TRANSACTION READ ONLY`, with an 8s
statement timeout and 1s lock timeout, and always rolled back.

| Domain item | Production result |
|---|---:|
| Fan clubs / admins / memberships | 0 / 0 / 0 |
| Club wallets / transactions / approvals | 0 / 0 / 0 |
| Club content / comments / likes | 0 / 0 / 0 |
| Club-membership deposits / affiliate commissions | 0 / 0 |
| Digital products / purchases / reviews | 0 / 0 / 0 |
| DSP wallets / transactions | 0 / 0 |
| DSP exchange rates | 1 |
| Shop-purchase deposits / affiliate commissions | 0 / 0 |
| Domain journal entries | 0 |
| Payout batches / items (global tables matched by inventory) | 0 / 0 |

All anomaly counts over domain rows are zero because the operational tables are
empty: no orphans, duplicate active memberships, duplicate entitlements,
negative amounts, split mismatches, excess downloads, self-reviews, duplicate
references, or public product file URLs were present.

## 29. Financial reconciliation

Club totals reconcile at zero: memberships, deposits, commissions, wallets,
transactions, approvals, and journal entries all contain no domain activity.
Marketplace totals reconcile at zero: gross purchases, platform fee, seller
earnings, deposits, commissions, DSP balances/transactions, and journal entries
all contain no domain activity. This is a zero-activity reconciliation, not
evidence that the incomplete designs are accounting-safe.

Prompt 6's unresolved plural `wallets` USD 2,441.00 and approximately USD 2.00
commission/payable gap were excluded, as required, and were not changed.

## 30. Concurrency

Runtime safeguards cannot make absent source keys unique. Application helpers
cover deterministic transitions and authorization, while the disabled routers
prevent concurrent financial writes today. Required future database guarantees
include unique payment-to-membership/order links, source-keyed earnings,
entitlements and payouts, plus row-locked/atomic reservations. Refund versus
payout needs an explicit state machine; no SELECT-before-UPDATE wallet flow may
be activated.

## 31. Files changed

Prompt 8 changes:

- `backend/app/api/api_v1/endpoints/search.py`
- `backend/app/models/clubs.py`
- `backend/app/models/dsp.py`
- `backend/app/schemas/clubs.py`
- `backend/app/schemas/dsp.py`
- `backend/app/services/club_marketplace_integrity.py`
- `backend/scripts/analyze_clubs_marketplace_production_readonly.py`
- `backend/tests/unit/test_club_marketplace_integrity.py`
- `frontend/app/clubs/page.tsx`
- `PREMIUM_CLUBS_MARKETPLACE_REPAIR_REPORT.md`

The worktree also contains preserved, unapproved changes from Prompts 2–7.

## 32. Tests

- Prompt 8 focused backend: **9 passed**.
- Full backend: **287 passed, 2 skipped, 0 failed**. Both skips are explicitly
  opt-in PostgreSQL accounting tests; production was not used for write tests.
- Frontend Vitest: **66 passed in 16 files, 0 failed**.
- Next.js production build: **PASS**, compiled and generated 88/88 pages.
- Build configuration skips TypeScript validation and linting; that existing
  limitation is not represented as a typecheck/lint pass.
- No provider was contacted; all financial write paths remained disabled.
- Prompt 2 voting/ranking, Prompt 3 contest context, Prompt 4 category/media,
  Prompt 5 performance, Prompt 6 financial, and Prompt 7 advertising regression
  tests are included in the passing full suite.

## 33. Schema recommendations

No recommendation was applied.

**REQUIRED FOR CORRECTNESS**

1. Club order/plan snapshot with club, member, period, base, markup, currency,
   versioned rule, and unique canonical deposit/payment reference.
2. Unique membership activation source; prevent duplicate active periods for
   the same club/member according to the chosen renewal policy.
3. Pending-payment/refunded membership representation or a separate immutable
   entitlement state/event table.
4. Club hold/release and payout-intent source keys, unique idempotency keys,
   canonical journal references, and currency constraints.
5. Marketplace order/order-line model with authoritative price snapshot,
   currency/asset/network, provider/payment ID, lifecycle, refund total, and
   unique checkout idempotency key.
6. Unique entitlement source keyed by order line/product/buyer and explicit
   active/revoked state.
7. Seller earning records with pending/held/available/paid/reversed lifecycle,
   unique order-line source, and canonical journal/payout references.
8. Unique refund and seller/club payout idempotency keys and compensating-entry
   references.
9. Private media object identity/ownership rather than a public paid-file URL.

**RECOMMENDED**

1. CHECK constraints for nonnegative money, valid intervals, positive download
   limits, valid ratings, valid fee ranges, and gross split equality where the
   database representation permits it.
2. Unique club admin, transaction approval, and product review pairs.
3. Indexes for active public club search, club/member/status/period,
   product/seller/status/category, purchase buyer/product/date, payment source,
   earning state, and payout state. Write cost is modest at current zero scale
   but should be evaluated with the final schema and query plans.
4. Separate product taxonomy and seller/moderation status foreign keys.

**OPTIONAL HARDENING**

- Version/optimistic-lock columns in addition to row locks, bounded signed-link
  audit metadata, and immutable admin action records.

## 34. Remaining risks

Critical remaining blockers are: no operational club or marketplace service;
no payment-to-domain linkage; no order or robust entitlement lifecycle; no
canonical holds/earnings/payouts; public-file design; absent moderation and
seller model; missing idempotency constraints; contradictory price/markup and
commission rules; no partial-refund policy; and divergent Alembic history.

The preview UI still contains demonstration cards and marketing copy, although
it is now explicitly labeled preview-only and all transaction/create controls
are disabled. The one DSP exchange-rate row has no active consumer and was not
treated as authoritative.

## 35. Deployment recommendation

**NO.** Do not deploy Prompt 8 or activate the dormant routers. First reconcile
Alembic, approve a single pricing/commission policy, design the required source
links and state machines, implement them through Prompt 6 services, use private
Prompt 4 media delivery, and run PostgreSQL concurrency/provider-mock tests in
an isolated staging environment.
