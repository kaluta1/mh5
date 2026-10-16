# Phase 1 — Financial reconciliation (method)

Sanitized: production record ids and amounts are kept in the private operations
archive, not in this repository.

## Goal

After Phase 1 the commission ledger matches the commission subledger:

| Ledger account | Must equal |
|---|---|
| 2001 direct commissions payable | open (PENDING + APPROVED) level-1 commissions |
| 2002 indirect commissions payable | open historical level 2–10 commissions |
| 5001 commission expense | commissions earned and not cancelled |

## Steps, in order (each a dry run first, then `--apply`, then a re-run that must write nothing)

1. **Reverse administrator-recorded payments that never arrived**
   (`reverse_invalid_payments`). Each original journal, revenue recognition
   and commission accrual gets one linked compensating entry; the commission is
   cancelled; the deposit becomes FAILED with an immutable marker. Cash,
   revenue, deferred revenue, commission liability and expense all fall by
   exactly the reversed amounts.
2. **Historical ledger corrections** (`reconcile_legacy_commissions`):
   * `fix-duplicate-journal`: a commission journal posted twice for one
     payment is reversed once (the first is kept);
   * `post-missing-accruals`: historical commissions whose accrual was never
     posted get one correction entry per payment (Dr 5001 / Cr 2001 level 1 /
     Cr 2002 levels 2–10).
   These release, cancel or pay nothing. With `--apply` the exact deposits
   and their approved amounts must be named; the source is re-validated under
   row locks in the same transaction and any mismatch refuses the batch.
3. **Sponsor-cycle correction** (`correct_sponsor_cycle`): no financial effect.

After step 2 the three equalities above hold. Every historical commission
remains **held** until a recorded review decision.

## Out of scope for Phase 1

* Recognition of historical KYC revenue still deferred for payments whose
  verification step never ran (separate decision).
* Any payout. Payouts stay disabled.

## Verification

* Arithmetic from read-only production figures: done (private archive).
* Same logic on synthetic data, SQLite and PostgreSQL: see
  `PHASE1_TEST_RESULTS.md`.
* Same steps on a restored copy of production, before/after compared:
  **pending** (see `PHASE1_PRODUCTION_RUNBOOK.md`, rehearsal).
