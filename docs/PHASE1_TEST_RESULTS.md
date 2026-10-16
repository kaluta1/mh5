# Phase 1 — Test results

Run 2026-10-16 on the uncommitted Phase 1 working tree (base `09bd435`).
All data synthetic. PostgreSQL tests use disposable local databases
(loopback only, random names, dropped afterwards).

## Summary

| Suite | Result | Notes |
|---|---|---|
| Backend unit (`tests/unit`, SQLite) | **2855 passed, 10 failed** | the 10 are pre-existing, see below |
| Backend other (`tests/` without unit; PostgreSQL ones skipped) | **116 passed**, 141 skipped | skips = PostgreSQL-only tests, run below |
| Backend PostgreSQL (`RUN_POSTGRES_TESTS=1 -m postgres tests/integration`) | **139 passed, 0 failed** | includes the Phase 1 file (29/29) |
| Phase 1 unit (`test_phase1_financial_controls.py`) | **23/23** | |
| Phase 1 PostgreSQL (`test_phase1_financial_controls_postgres.py`) | **29/29** | |
| Frontend (vitest) | **532/532** | |
| Frontend type check (`tsc --noEmit`) | clean | |
| Frontend production build (`next build`) | OK | |
| Real alembic CLI from production revision | OK | `e6f7a8b9c0d1` → head → `e6f7a8b9c0d1` → head → −1 → head |

## Rehearsal on a restored production copy

Disposable local database, every integration disabled, production not
contacted. Migrations up/down/up changed no existing row; every correction
script was run as a dry run, applied, and re-run (re-runs wrote nothing). All
29 checks passed and every reconciled figure equalled the approved plan
(ledger = subledger for direct payable, indirect payable and commission
expense; all journals balanced; historical commissions still held; payouts
off). Details and figures are in the private operations archive.

### Side effects of the corrections

A first check of "rows created during the run" in the email, notification and
KYC tables compared naive-UTC timestamps with a local-time clock and is
therefore **inconclusive**; it is not counted as a pass. It was replaced by a
census of every table (row count, highest primary key, full-content checksum)
before and after all four corrections on a restored copy: only the expected
financial, audit and referral tables changed; email, notification, KYC,
settings, cashout, review and referral-tree tables were identical.

## Pre-existing failures (not Phase 1)

`tests/unit/test_email5_immutable_content.py`, 10 tests. The identical set
fails on a clean checkout of `09bd435` (verified in a separate worktree) and
has been the known baseline since earlier releases. Not touched by Phase 1.

`tests/test_accounting_flow.py` (2 tests) is skipped in both runs (it needs a
live database outside the integration harness); previously recorded as stale
(asserts a retired posting). Unchanged by Phase 1.

A full alembic run from an empty database stops at an old revision
(`kyc_verifications.verification_url` already present); pre-existing and
unrelated. Phase 1 migrations are proven from the production revision instead.

## Phase 1 regressions found and fixed during testing

| Found | Fix |
|---|---|
| Sponsor-cycle trigger race: two concurrent changes (A under B, B under A) both passed and created a cycle. Proven by a PostgreSQL test that fails without the fix. | Trigger takes a transaction-scoped advisory lock; the walk then sees the other change. |
| Hold and CHECK treated only `business_model_version IS NULL` as historical; the codebase rule is "anything but NEW_V2" (`LEGACY_V1` can be stamped). | One `historical_clause()` (`COALESCE(version,'') <> 'NEW_V2'`) used by the hold, reviews and reconciliation; CHECK uses the same rule. |
| 3 older tests inserted rows the new guards forbid (self-sponsor; NEW_V2 at level > 1). | Rewritten to assert the database refuses them; their application-level assertions kept. |
| PostgreSQL payment fixtures used unstamped commissions (now held) and the chain test stopped at the previous head. | Fixtures stamped NEW_V2 (as the SQLite fixtures); chain test extended to `b7d9f1a3c5e7`. |

No security or financial assertion was weakened.

## What the Phase 1 tests prove

**Payout hold** — NULL and `LEGACY_V1` commissions are excluded from cashout
reservation, the crypto engine, the older payout service, PENDING promotion
and the available balance (SQLite and PostgreSQL); a RELEASE makes exactly one
row payable; CANCEL keeps it held; decisions need permission + password +
reason, are final, never on one's own commission; concurrent decisions on one
commission record exactly one.

**Maker-checker** — record credits nothing; same administrator, the member,
an earner, missing evidence or a wrong password are refused and audited;
double confirmation → `ALREADY_DECIDED`; two checkers at once → one credit,
one commission, journals posted once; confirm vs cancel at once → exactly one
consistent outcome (3 runs); provider validation in between → superseded,
nothing credited twice; reversed deposit cannot be confirmed.

**Guards and migrations** — chain is additive (no existing row changed),
repeatable and reversible on production-shaped data (missing source index,
historical sponsor loop, multi-level history); the guard migration stops on
each kind of violating row and creates nothing; downgrade refuses to drop a
table holding decisions; trigger refuses cycles and self-sponsorship, ignores
an unrelated historical loop, allows registrations under it, allows the
planned correction and refuses putting the link back.

**Historical accrual correction** — serialised by an advisory lock; four
concurrent runs post each entry exactly once; a commission changed by another
transaction while the correction waits is re-read and the batch refused; seven
kinds of invalid source data and three kinds of approved-amount mismatch
refuse the whole batch; re-runs write nothing; one audit row per entry; the
command line refuses `--apply` without the approving administrator, the
deposits or the approved amounts.

**Manual-payment queue** — only administrators holding the payment
permission can view it (others get 403, audited); maker-checker and the
earner rule unchanged at the API.

**Commission policy** — 20% standard and 40% for a qualified sponsor's
ad-slot purchases, direct sponsor only; both are level-1 rows accepted by the
guards and payable; the same row above level 1 is refused; a live payment
pays 20% at level 1 even to a qualified sponsor.

**Scripts** — invalid-payment reversal dry run changes nothing, apply reverses exactly,
re-run is a no-op, refusals for anything it must not touch; historical
corrections bring ledger to subledger; cancellations only after a recorded
decision; cycle correction removes only the named link.
