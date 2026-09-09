# Affiliate, Commission & Financial Accounting Repair Report

Date: 2026-09-09  
Scope: Prompt 6 only; repository audit, implementation, mocked-provider tests, and low-impact production reads  
Status: **PARTIAL**  
Production deployment/data/schema changes: **none**

Prompt 6 repaired the active payment, affiliate commission, payout, refund, wallet-display, and journal-posting paths. It remains PARTIAL because production contains an unmapped five-row `wallets` balance domain totaling USD 2,441.00, the commission subledger exceeds commission-payable journal balances by USD 2.00, and several required payout/webhook/refund integrity fields and constraints cannot be introduced while Alembic history is divergent. No discrepancy was auto-corrected.

## 1. Financial architecture

The registered financial routes are:

- `/api/v1/payments`: NOWPayments checkout, status, synchronization, and invoices.
- `/api/v1/webhooks/nowpayments`: signed payment/refund IPN finalization.
- `/api/v1/webhooks/sponsor-payment`: signed AnnualAds sponsor-payment posting.
- `/api/v1/wallet`: the current user's derived commission balance, history, preview, and withdrawal.
- `/api/v1/users/me/wallet`: payout-address registration.
- `/api/v1/affiliates`: sponsor tree, commissions, and summaries.
- `/api/v1/admin`: globally admin-protected payment grants, reports, and payout controls.
- `/api/v1/fmr`: founding membership point views.

Accounting, club, and DSP endpoint modules exist but are not registered in the active API router. Their models/tables are therefore inventory domains, not active public financial APIs. The production inventory found 44 finance-related tables, including deposits, payment methods/products, commissions/rules, two wallet table names, journals, FMP ledgers, cashouts, DSP/club/ad domains, invoices, revenue tables, and referral tables.

## 2. Accounting source of truth

There is no safe single source of truth across every historical domain.

| Domain | Classification | Current source |
|---|---|---|
| Active purchase/payment | AUTHORITATIVE | `product_types` for price/currency; `deposits` for order/provider/payment state |
| Affiliate accrual | AUTHORITATIVE subledger | `affiliate_commissions`, keyed to `deposit_id` |
| Posted accounting | AUTHORITATIVE for covered events | `journal_entries` + `journal_lines`; true debit/credit entries |
| Affiliate wallet API | DERIVED | grouped sums of `affiliate_commissions`; no mutable balance field |
| Founding membership points | AUTHORITATIVE ledger / derived cache | `member_fmp_ledger`; `member_fmp_balances` is a cached total |
| Payout workflow | PARTIAL | `affiliate_cashout_requests` plus commission reservations/references |
| Singular `wallet` | LEGACY/UNUSED | ORM-mapped but zero production rows |
| Plural `wallets` | UNKNOWN/LEGACY | unmapped by the current ORM; five rows and USD 2,441.00 |
| `transactions` | LEGACY/UNUSED | zero production rows |
| DSP/club/ad/invoice/revenue domains | DORMANT/PARTIAL | tables/models exist; most production counts are zero and routers are inactive |

Journal entries are double-entry for supported posting flows, not a complete universal ledger for every balance-like table. Transactions are not authoritative.

## 3. Wallet model

The active affiliate wallet is now centralized in `financial_balances.get_commission_balance()`. It derives:

- available: APPROVED and unreserved commissions;
- pending: PENDING commissions;
- reserved: APPROVED commissions attached to a payout intent;
- paid lifetime: PAID commissions;
- earned lifetime: all non-cancelled commissions.

The previous API incorrectly counted PAID historical commissions as available. That overspend risk is repaired. All active withdrawals reserve commission rows through the payout service; the endpoint does not mutate `wallet.balance`.

Production nevertheless has a separate plural `wallets` table with five USD rows, USD 2,441.00 balance, and USD 0.00 frozen balance. The current ORM maps singular `wallet`, which is empty. Provenance and ownership semantics of the plural table must be established before any migration or balance claim.

## 4. Transaction model

`deposits` are durable payment/order records. Production contains 69:

- 35 expired totaling USD 880.00;
- 27 pending totaling USD 324.00;
- 7 validated totaling USD 61.00.

No non-positive deposit, validated-without-timestamp deposit, missing order/provider reference, or duplicate non-null provider payment ID was found. `deposits.order_id` has a production unique constraint. The legacy `transactions` and `user_transactions` tables contain zero rows.

## 5. Journal/ledger model

Production has 38 journal entries and 90 journal lines. Read-only reconciliation found:

- zero unbalanced headers;
- zero unbalanced line sets;
- zero header/line total mismatches;
- USD 0.00 total line imbalance.

The posting service now rejects empty journals, negative line amounts, a line containing both debit and credit, and any debit/credit imbalance. Amounts are normalized to cent-scale `Decimal` before persistence. The journal is proper double-entry where it is used, but coverage is incomplete: the commission payable accounts carry USD 36.00 against USD 38.00 of outstanding commissions.

## 6. Affiliate architecture

The canonical live parent relation is `users.sponsor_id`. `affiliate_tree` is a legacy/materialized representation used by some display and FMP code. Production has zero `affiliate_tree` rows, so it cannot be the live hierarchy source. The repair synchronizes `users.sponsor_id` when joining through the affiliate endpoint and prevents silent sponsor mutation from admin GET requests.

## 7. Sponsor hierarchy

Traversal is deterministic, capped, and cycle-safe:

- maximum commission depth is 10;
- the payer and every visited sponsor are tracked;
- self-referral, reassignment, descendant cycles, missing sponsors, inactive sponsors, and deleted sponsors fail closed or are skipped according to the operation;
- malformed history terminates without recursion loops.

Production read-only results: zero self-referrals, zero missing sponsors, zero cycles, zero paths over the safety depth, and zero affiliate-tree/user sponsor mismatches.

## 8. Commission rules

Active calculation uses the server-side `commission_rules` row for the deposit's server-selected product. Production has nine active rules. Most fixed-price products use 10% at level 1 and 1% at levels 2-10; the existing club and shop rules retain their configured rates. The service caps a database rule at ten levels even if malformed configuration requests more.

The commission basis is the authoritative `product_types.price` stored on the deposit. Client amount, recipient, rate, and beneficiary cannot set the commission basis. The unused legacy reference-based commission creator is disabled fail-closed. The stale KYC display configuration was corrected from USD 1.00 to the production USD 10.00 price.

## 9. Commission lifecycle

Existing states are preserved: PENDING, APPROVED, PAID, CANCELLED.

- PENDING: accrued for a beneficiary without a configured payout target.
- APPROVED: withdrawable unless it has an internal payout-intent reservation.
- PAID: only after the provider returns a durable payout reference and final posting commits.
- CANCELLED: source payment was reversed; the historical row is retained.

An external request being initiated no longer marks a commission PAID. Uncertain payout outcomes remain APPROVED but reserved, with cashout status `unknown`, and require reconciliation.

## 10. Commission idempotency

Application code checks `(deposit_id, recipient user)` before accrual. More importantly, production already has the partial unique index `uq_affiliate_commissions_deposit_user` on `(deposit_id, user_id) WHERE deposit_id IS NOT NULL`, despite the reported Alembic revision. No duplicate commission source was found.

Webhook finalization also locks the deposit row. This serializes duplicate payment confirmations before commission creation. The database index remains the final concurrent enforcement.

## 11. Payment workflow

Checkout now follows this boundary:

1. load active product and authoritative USD price;
2. reject any submitted amount/currency mismatch;
3. create and commit a local pending deposit/order intent;
4. call NOWPayments with bounded timeouts and no open database transaction;
5. lock the deposit and store the provider result.

An `Idempotency-Key` produces a stable order ID scoped to the user. `deposits.order_id` uniqueness prevents double-click/retry duplicate orders. The frontend reuses one key throughout a dialog attempt. Multi-recipient and third-party purchases are disabled until the schema can distinguish payer, beneficiary, and order items.

Validated deposits are the durable entitlement record. Product `validity_days` now sets `expires_at`; transient unmapped `User.is_founding_member` attributes were removed from the workflow.

## 12. NOWPayments integration

- HMAC-SHA512 IPN verification remains mandatory.
- Provider `order_id`, `payment_id`, authoritative price, and price currency are bound to the local deposit before mutation.
- Production must explicitly define `NOWPAYMENTS_SANDBOX=true|false`; omission now fails startup.
- Pay-in, status, authentication, payout, and verification calls have explicit connect/read/write/pool timeout profiles.
- Payout TOTP remains internal; the admin endpoint that exposed the current second-factor code now returns 410.
- Tests mock every provider action. No live payment, payout, verification, or refund call was made.

Residual safe-failure case: if provider payment creation succeeds but its response is lost before the external ID is stored, the committed local intent blocks a duplicate provider call and requires manual provider reconciliation.

## 13. Withdrawal workflow

Withdrawal validation now enforces positive Decimal amounts, minimum USD 100, server-calculated fee, available balance, configured wallet, address/network validation, and payout readiness. A user can act only on commissions owned by their authenticated user ID.

Because commissions are indivisible rows in the current schema, a withdrawal must equal an exact FIFO sum of whole commission rows. A request that cuts through the last row is explicitly rejected before provider I/O. This repairs the prior bug that marked excessive commissions paid during a partial withdrawal.

## 14. Payout workflow

The new durable saga is:

1. lock the user and eligible commission rows;
2. create a cashout intent and reserve the exact rows;
3. commit the intent;
4. commit state `processing`;
5. call/verify the provider without an open database transaction;
6. re-lock intent and reserved rows;
7. mark only those rows PAID, record provider reference, post the balanced cashout journal, and commit.

A provider error or timeout produces `unknown`; funds remain reserved and the intent is never blindly retried. New payouts are blocked while that user's unresolved intent exists.

## 15. Refund workflow

A signed provider `refunded` event now reaches the reversal service even when the deposit was previously VALIDATED. The service locks the deposit and source commissions, rejects a race with an unresolved payout, marks the entitlement deposit failed, cancels rather than deletes commissions, reverses founding points, and writes compensating accounting.

Duplicate refund delivery is a no-op after the durable refund marker/reversal entry. Full refunds are supported. Partial refunds are explicitly rejected for manual reconciliation because the schema has no refund amount/allocation model.

## 16. Reversal strategy

Original history is immutable. Each original deposit journal line is mirrored debit-for-credit in a refund reversal journal. For a commission already paid externally, the original commission is cancelled and a separate accounts-receivable entry records debt from the affiliate; its payout reference and paid date are retained. For unpaid commissions, cancelling plus reversal removes the payable. FMP uses a negative `FOUNDING_JOIN_REVERSAL` ledger row rather than deleting the accrual.

## 17. Concurrency model

- payment webhook/scheduler: deposit `FOR UPDATE` plus unique commission source index;
- purchase creation: unique order ID plus deterministic idempotency key;
- withdrawal: user lock plus commission row locks and durable reservation;
- refund versus payout: locked commissions and unresolved-intent rejection;
- AnnualAds: PostgreSQL transaction advisory lock by transaction hash;
- journal/FMP: existing event/idempotency uniqueness where present.

True concurrent PostgreSQL write tests were not run against production. The two opt-in live-PostgreSQL tests remain skipped, so row-lock behavior is source-verified and production-constraint-verified rather than destructively exercised.

## 18. Money precision

Active financial calculations use `Decimal`, explicit cent quantization, and ROUND_HALF_UP. ORM persistence uses NUMERIC/DECIMAL. NaN/non-finite values, zero/negative movements, unbalanced journals, and invalid fee/net relationships are rejected. Conversion to JSON/provider numeric values occurs only at external serialization boundaries. Dormant legacy models retain `Mapped[float]` annotations over NUMERIC columns and should be normalized before those domains are activated.

## 19. Currency/asset handling

Server price currency is currently USD only. Payout settlement is fail-closed to USDT on BSC because the live cash account is specifically the BSC treasury. Unknown network labels no longer silently become BSC. ERC20/TRC20 registration/payout is disabled until separate ledger accounts, custody reconciliation, and network-specific constraints exist. AnnualAds likewise requires USDT BSC and verifies net equals gross minus fee.

## 20. Webhook security

NOWPayments requires its HMAC signature and binds signed identity/price fields. AnnualAds requires HMAC-SHA256 over timestamp plus raw body, rejects timestamps outside five minutes, validates event, positive amounts, fee/net equality, transaction hash, and BSC asset. AnnualAds no longer creates chart-of-account rows inside a webhook; missing configuration fails closed.

Both handlers are replay-safe at the application/state level. A canonical provider-event table with unique `(provider,event_id)` remains required for durable forensic replay history and final concurrent enforcement across all providers.

## 21. Financial admin controls

All `/admin` routes have a router-wide admin dependency, and financial handlers also retain explicit checks. Manual grants now derive price/currency from `product_types`; an admin-supplied mismatch is rejected. The deposit records `validated_by`, time, and notes. The TOTP disclosure endpoint is disabled. Admin user-detail GET no longer silently assigns a sponsor.

Remaining governance gap: there is no dedicated immutable admin-financial-action table covering every grant, reversal, hierarchy override, and reconciliation decision.

## 22. Production reconciliation

The tool `backend/scripts/reconcile_financial_production_readonly.py` enforces PostgreSQL, starts a READ ONLY transaction, uses 8-second statement and 1-second lock timeouts, emits no credentials/PII, and always rolls back.

Results:

- journals: 38 headers / 90 lines, all balanced and header-consistent;
- deposits: 69 totaling USD 1,265.00 across expired/pending/validated status groups; no structural anomalies found;
- affiliate commissions: 14 APPROVED rows totaling USD 38.00;
- commission-payable ledger: USD 36.00, aggregate discrepancy USD -2.00;
- deposit 51: one USD 1.00 commission with USD 0.00 payable posting;
- remaining aggregate USD 1.00 difference is not isolated by description-based deposit correlation and requires journal-source investigation;
- singular `wallet`: zero rows;
- plural `wallets`: five USD rows, USD 2,441.00 balance, USD 0.00 frozen;
- cashout requests, FMP ledgers/balances, founding members, transactions, DSP/club financial rows, invoices, and revenue transactions: zero;
- configured user payout wallets: zero.

## 23. Affiliate reconciliation

No duplicate source/recipient commissions, negative commissions, zero commissions, invalid levels, missing commission sources, paid-without-reference rows, paid-date/status mismatches, or recipients outside the sponsor chain were found. All 14 rows are deposit-backed and APPROVED. Production's database-level unique commission index is confirmed.

## 24. Data anomalies

1. **Critical provenance blocker:** five records and USD 2,441.00 exist in unmapped plural `wallets`; active code maps empty singular `wallet` and derives affiliate balances elsewhere.
2. **Accounting blocker:** affiliate commission subledger USD 38.00 versus payable ledger USD 36.00.
3. **Specific missing posting:** deposit 51 has a USD 1.00 commission and no corresponding payable posting.
4. **Schema/history drift:** production contains unique indexes/columns not explained by revision `f3merge01`; repository remains multi-head.
5. **Zero-price active products:** variable-price `ad_credit`, `dsp_topup`, and `shop_purchase` rows cannot use the repaired fixed-price checkout and now fail closed; they need authoritative order-item pricing before activation there.

## 25. Files changed

Prompt 6 changed:

- Backend endpoints: `admin.py`, `affiliate.py`, `payment_webhooks.py`, `payments.py`, `sponsor_annualads.py`, `users.py`, `wallet.py`.
- Backend core/CRUD/schema: `config.py`, `commission_config.py`, `crud_affiliate.py`, `crud_user.py`, `schemas/wallet.py`.
- Backend services: `accounting_service.py`, `affiliate_hierarchy.py`, `commission_distribution.py`, `commission_payout_service.py`, `financial_balances.py`, `financial_integrity.py`, `financial_reversal.py`, `journal_entry_status.py`, `nowpayments_service.py`, `payment_scheduler.py`, `wallet_validation.py`.
- Tool/tests: `reconcile_financial_production_readonly.py`, `test_financial_integrity.py`, `test_financial_payouts.py`, `test_wallet_validation.py`, `test_wallet_flow.py`.
- Frontend: `payment-dialog-v2.tsx`, `settings-wallet-tab.tsx`, `withdraw-dialog.tsx`, `commission-config.ts`, `payment-service.ts`.

The worktree also contains preserved, unapproved Prompt 2-5 changes; they are not attributed to Prompt 6 here.

## 26. Tests

Final verification:

- Python compile check using a temporary pycache: PASS.
- Backend: **257 passed, 2 skipped**. Skips are opt-in live-PostgreSQL accounting tests; zero failures.
- Frontend Vitest: **64 passed, 0 failed** across 15 files.
- Next.js production build: PASS; compiled and generated **88/88** static pages.
- Provider calls in tests: mocked; no real side effects.

New coverage includes server price tampering, order idempotency, provider identity binding, fivefold webhook replay, AnnualAds signature/replay, ten-level/cycle/reassignment safety, exact withdrawal reservation, insufficient funds, payout timeout/unknown recovery, duplicate payout replay, balanced payout journals, full/duplicate/partial refund behavior, paid-commission receivable, FMP reversal, Decimal precision, and asset/network rejection.

The complete suites include the Prompt 2 ranking, Prompt 3 context, Prompt 4 category/media, and Prompt 5 performance guards; all pass.

## 27. Schema recommendations

**REQUIRED FOR CORRECTNESS** (documented only; not applied):

1. Reconcile Alembic history and adopt the already-present unique commission and journal indexes into canonical migration history.
2. Add unique non-null `deposits.external_payment_id` and a provider/event table unique on `(provider,event_id)`.
3. Add explicit unique cashout `idempotency_key`, unique provider payout reference, constrained payout status, and a cashout-to-commission reservation/junction table.
4. Add first-class refund/reversal records with provider event, original deposit, amount, currency, state, and journal/reversal references.
5. Decide and migrate one canonical wallet model with `(owner,currency,asset,network)` uniqueness; preserve and provenance-audit all five plural-wallet rows first.
6. Add currency/asset/network and typed source references to financial journals; use existing journal event/idempotency columns instead of description matching.
7. Add explicit commission reversal/debt linkage and state transition metadata.
8. Add payer/order/order-item/beneficiary records before re-enabling third-party or variable-price checkout.

**RECOMMENDED:** sponsor self-check constraint; constrained commission levels/rates/non-negative amounts; payout/refund transition audit table; indexes on provider IDs, commission reservation/status/user, deposit status/product/user, and journal source lookup.

**OPTIONAL HARDENING:** optimistic wallet version only if a mutable wallet is intentionally activated; separate custody accounts per blockchain network; archival partitions after material scale growth.

Write cost is small at current volumes, but uniqueness/foreign-key indexes increase every financial insert. Their correctness benefit outweighs that cost. No index or migration was applied.

## 28. Remaining financial risks

- USD 2,441.00 in the plural wallet domain has unknown provenance relative to the active application.
- USD 2.00 commission-payable gap requires reviewed, explicit reconciliation; deposit 51 explains USD 1.00.
- Payout/webhook/refund schema support is incomplete even though application workflows now fail safely.
- A provider-created payment whose response is lost remains a manual-reconciliation intent; a provider payout with uncertain response remains reserved/unknown by design.
- Full refunds are automatic; partial refunds are rejected, not allocated.
- Arbitrary partial commission-row withdrawals are rejected until allocations are modeled.
- No live PostgreSQL concurrency write test was run; production row-lock and unique-index behavior was not stress-tested.
- Dormant DSP, club, plural-wallet, ad-credit, invoice, and revenue-share systems are not unified under the active ledger and must remain inactive until separately reconciled.
- Some dormant/reporting schemas expose numeric values as JSON floats; active calculations and persistence are Decimal/NUMERIC.
- Alembic topology is still divergent and production contains schema artifacts beyond its recorded revision.

## 29. Deployment recommendation

**NO.** Do not deploy Prompts 2-6 together yet. First reconcile Alembic history, establish provenance and business ownership of the five plural-wallet balances, resolve the USD 2.00 commission-payable difference with reviewed compensating entries (never edits/deletes), add the required payout/webhook/refund constraints, and execute the concurrency/provider-contract suite in an isolated PostgreSQL staging environment with mocked NOWPayments.

No code was deployed, no production service was restarted, no Alembic command ran, no production row changed, and no real financial provider side effect occurred.
