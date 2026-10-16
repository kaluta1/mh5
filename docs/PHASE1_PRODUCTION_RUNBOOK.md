# Phase 1 — Production runbook (sanitized)

Hosts, database names and record ids are in the private operations archive.
Every step that touches production needs an explicit owner go-ahead for that
step. Commission payouts stay disabled throughout.

## Migrations

`e6f7a8b9c0d1` → `f9b1c3d5e7a9` (manual_payment_confirmations, empty)
→ `a8c0e2f4b6d8` (commission_payout_reviews, empty)
→ `b7d9f1a3c5e7` (CHECKs, unique indexes, sponsor-cycle trigger).

All additive. The guard migration checks existing data first and stops,
changing nothing, on any violation. Downgrade removes the trigger and CHECKs and
refuses to drop a table that already holds records.

## A. Rehearsal (before any production change)

1. Read-only identification of the production database and its revision.
2. Fresh `pg_dump -Fc` on the server into a new mode-700 backup directory,
   with SHA-256 checksums.
3. Copy the dump to the operator's machine (private, git-excluded folder);
   verify the checksum.
4. Restore into a disposable local database (`--no-owner --no-privileges`).
5. Set `DATABASE_URL` explicitly to that local database and assert host and
   name before running anything (the local `.env` points elsewhere).
6. `alembic upgrade head`, `downgrade e6f7a8b9c0d1`, `upgrade head`.
7. Run the scripts in order (see `PHASE1_FINANCIAL_RECONCILIATION.md`): dry
   run, `--apply --actor-id N` (accruals also `--deposit`/`--expect` for each
   deposit), re-run (must be a no-op). Save every output.
8. Pass criteria: ledger equals subledger; all journals balance; re-runs wrote
   nothing; historical commissions still held; no PAID commission, no cashout;
   only the named sponsor link changed.
9. Drop the local rehearsal database. The encrypted backup and its
   passphrase are kept; deleting them needs a separate owner approval.

## B. Production (after rehearsal PASS; every stage separately approved)

1. Fresh backup immediately before.
2. Upload the new release without activating it; the current release keeps
   serving.
3. `alembic upgrade head` while the current release still serves (the new
   code needs the new tables; the current code is unaffected by them).
4. Switch traffic to the new release. Smoke checks: health, admin login, held
   balances shown as "under review", manual-payment queue visible only to
   permission holders and empty, empty review table, payouts off.
5. Corrections, one approval each: dry run → owner reviews the output →
   `--apply --actor-id N` → re-run must do nothing → verification. The
   accrual correction also needs each `--deposit` with its approved
   `--expect DEPOSIT=AMOUNT`.
6. Post-checks as in A.8.

## Rollback

* Code: previous release.
* Schema: `alembic downgrade e6f7a8b9c0d1`.
* Data: the scripts only add compensating entries and audit rows; full undo
  is a restore of the pre-change backup (owner decision).

## Operational consequences

* A second authorised administrator is needed to complete any manual payment.
* Members with historical balances see them as held.
