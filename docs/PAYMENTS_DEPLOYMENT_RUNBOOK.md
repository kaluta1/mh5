# Payments: deployment runbook (dual cashout, Finance & Payments, NOWPayments)

Prepared 2026-10-10. This is a plan. Nothing in it has been executed on
production. Automatic crypto payouts and USD settlement stay OFF throughout.

Commits covered (oldest first): `7e53af1`, `e8d4fa0`, `9e170b0`, `8dbdd11`, and
the Phase 3 hardening commit that contains this file. Deploy the newest one.

Production today runs `d208c1d` with Alembic revision `e2f3a4b5c6d7`.

## 1. Migration chain

| Order | Revision | Revises | What it adds |
|---|---|---|---|
| 1 | `f3a4b5c6d7e8` | `e2f3a4b5c6d7` | 3 columns on `users`, 9 on `affiliate_cashout_requests`, two unique indexes, `payout_wallet_changes` |
| 2 | `a5b6c7d8e9f0` | `f3a4b5c6d7e8` | `payment_settings`, `payment_credentials`, `payment_config_audit`, `payout_wallet_verifications`, `payment_webhook_stats`, 3 + 1 columns, two permissions held by nobody |

| 3 | `b6c7d8e9f0a1` | `a5b6c7d8e9f0` | one row in `chart_of_accounts`: 5005 Crypto payout network fees (paid by MyHigh5), under 5000 |

All three are additive, idempotent and run in one transaction each. They read
and change no commission, deposit, cashout or journal row. `b6c7d8e9f0a1` is
the single head.

Verified on a disposable local PostgreSQL 16 database with production-like
rows: upgrade from `e2f3a4b5c6d7`, a second upgrade, downgrade, upgrade again;
every existing row identical before and after; the resulting schema equal to
the one the models expect (`tests/integration/test_payments_postgres.py`).

## 2. Pre-migration checks (read-only SQL)

Run on production BEFORE the upgrade. Each must return what is stated.

```sql
-- 2.1 The expected starting revision. Expect exactly: e2f3a4b5c6d7
SELECT version_num FROM alembic_version;

-- 2.2 The upgrade refuses to continue if this returns a row. Expect: no rows.
SELECT user_id, count(*) FROM affiliate_cashout_requests
WHERE status IN ('requested', 'processing', 'unknown')
GROUP BY user_id HAVING count(*) > 1;

-- 2.3 The upgrade refuses to continue if this returns a row. Expect: no rows.
SELECT payout_reference, count(*) FROM affiliate_cashout_requests
WHERE payout_reference IS NOT NULL
GROUP BY payout_reference HAVING count(*) > 1;

-- 2.4 Nothing from this release exists yet. Expect: all NULL.
SELECT to_regclass('public.payment_settings'), to_regclass('public.payment_credentials'),
       to_regclass('public.payout_wallet_changes'), to_regclass('public.payout_wallet_verifications');

-- 2.5 The permission tables the second migration writes to exist. Expect: both not NULL.
SELECT to_regclass('public.permissions'), to_regclass('public.role_permissions');

-- 2.6 Baseline to compare after the upgrade (save the output).
SELECT status::text, count(*), coalesce(sum(commission_amount), 0) FROM affiliate_commissions GROUP BY 1 ORDER BY 1;
SELECT status, count(*), coalesce(sum(gross_amount), 0) FROM affiliate_cashout_requests GROUP BY 1 ORDER BY 1;
SELECT count(*) AS members_with_wallet FROM users WHERE coalesce(usdt_wallet_address, '') <> '';
SELECT count(*) AS journals, coalesce(sum(total_debit), 0), coalesce(sum(total_credit), 0) FROM journal_entries;
```

If 2.2 or 2.3 returns rows: stop. Nothing may be deleted to make the data
fit; the rows have to be reconciled by hand first. (The upgrade itself also
stops with a clear message and changes nothing in that case.)

## 3. `PAYMENT_SETTINGS_ENCRYPTION_KEY`

What it protects: provider credentials stored through the Admin Panel, and the
USD payout destination details members enter. It is NOT needed for credentials
that stay in the server environment (the default source).

Rules:
- At least 32 characters, generated for this purpose only, never reused from
  `SECRET_KEY` or any other secret, never stored in the database, never
  committed, never pasted into chat, a ticket or an email.
- Production, staging and local each have their own key.

Setting it (on the server, by the person who holds server access):
1. Generate it directly into the environment file so it never appears on a
   screen or in shell history, for example:
   `printf 'PAYMENT_SETTINGS_ENCRYPTION_KEY=%s\n' "$(openssl rand -base64 48)" >> /path/to/backend/.env`
2. Confirm it is present without printing it:
   `grep -c '^PAYMENT_SETTINGS_ENCRYPTION_KEY=' /path/to/backend/.env` (expect `1`).
3. Restrict the file: owner-only read (`chmod 600`).

Backup and recovery:
- Store one copy in the organisation's password manager (owner and one
  deputy), and one offline copy (printed or on an encrypted drive) kept with
  the other disaster-recovery material.
- Keep it SEPARATE from database backups: a database backup plus this key is
  everything needed to read the stored credentials.
- The key must survive every deployment. The release procedure must carry the
  existing `.env` forward; a new release must never generate a new key.
- Disaster recovery: restore the database, then put the SAME key back before
  starting the backend. Add "encryption key present" to the recovery checklist.

If the key is lost or changed:
- Credentials stored in the Admin Panel become unreadable (the panel reports
  "cannot be decrypted"); nothing falls back to another secret. Store them
  again through the panel.
- USD destination details already entered by members cannot be read any more;
  those members have to be asked again.
- Commissions, cashouts and the ledger are not affected.

Rotation: there is no re-encryption tool. To rotate, set the new key, then
store every credential again in the Admin Panel. Do it while no USD cashout
with destination details is open.

## 4. Deployment steps (do not start without the go/no-go in section 8)

1. Confirm the exact Git SHA to deploy and that `origin/main` is at it.
2. Confirm the production baseline: release commit and
   `SELECT version_num FROM alembic_version` = `e2f3a4b5c6d7`.
3. Full database backup (`pg_dump`, custom format).
4. Back up the application directory and the backend `.env`.
5. Verify the backups: checksum, `pg_restore --list` succeeds, and a restore
   into a scratch database on the server returns the row counts of 2.6.
6. Set `PAYMENT_SETTINGS_ENCRYPTION_KEY` (section 3) and store its backup.
7. Confirm in the `.env`: `CRYPTO_AUTO_PAYOUT_ENABLED=false`,
   `USD_CASHOUT_SETTLEMENT_ENABLED=false`, `NOWPAYMENTS_SANDBOX` explicitly set.
8. Run the pre-migration checks (section 2).
9. Stop the backend (or put it in maintenance) so no request runs across the
   schema change.
10. `alembic upgrade f3a4b5c6d7e8`, then `alembic upgrade a5b6c7d8e9f0`, then
    `alembic upgrade b6c7d8e9f0a1`. `alembic current` must print
    `b6c7d8e9f0a1 (head)`, and
    `SELECT account_code, account_name, is_active FROM chart_of_accounts WHERE account_code = '5005';`
    must return one active row.
11. Re-run 2.6 and compare with the saved baseline: identical.
12. Deploy the exact tested commit, backend and frontend together (frontend
    built with the production `NEXT_PUBLIC_*` values).
13. Start the backend and the frontend; check the health endpoint, the home
    page and a login.
14. Grant the two permissions to the named administrators only:
    `python -m app.scripts.grant_payment_permissions --email <admin> ` (dry
    run), then the same with `--apply`.
15. Finance & Payments smoke test (section 5).
16. Existing pay-in regression check (section 6).
17. Confirm payouts are disabled (section 7).
18. Reconciliation: Admin > Finance & Payments > Reconciliation shows no
    discrepancy; owed totals equal the 2.6 commission totals.
19. Watch the backend log and nginx for 30 minutes: no 5xx on `/api/v1/payments`,
    `/api/v1/wallet`, `/api/v1/webhooks/nowpayments`, `/api/v1/admin/finance`.

## 5. Finance & Payments smoke test

- An administrator WITHOUT the permission opens the section: pages load, every
  save and the connection test answer 403.
- An administrator WITH `manage_payment_settings`: saving a setting asks for
  the current password; a wrong password is refused; a correct one is saved
  and appears in the configuration history.
- Provider page: no credential value is visible anywhere; statuses read
  Configured / Unverified, never Verified before a connection test.
- Run the connection test once. With the server IP not whitelisted the
  expected result is "IP not whitelisted" for custody: that is the provider
  blocker, not a deployment failure.
- Member side: Settings > Payout wallet asks for the password and sends the
  confirmation email; the wallet shows "on hold" after confirmation.

## 6. Existing pay-in regression check

- Create one real KYC payment as a test member and do NOT pay it: an address
  and amount are shown; the deposit is `pending`.
- The invoice page and "check status" answer without error.
- After one hour the poller marks it expired (it now asks the provider first).
- If a real small payment is authorised by the owner: pay it and confirm the
  callback is accepted (Callback / IPN card: "Accepted" increases). This is the
  first proof that the IPN secret matches.

## 7. Payouts-disabled verification

- `Admin > Finance & Payments`: server switch "automatic crypto payouts" off,
  effective state off, "USD settlement" off.
- Backend log shows "Cashout scheduler started (server master switch: False)".
- `POST /admin/cashouts/run` (with `process_cashouts`) answers
  `{"enabled": false, ...}`.
- `affiliate_cashout_requests` has no new row.

## 8. Go / no-go

GO only if every line is true:
- [ ] The SHA to deploy is the one whose tests were run and reported.
- [ ] Database backup taken, verified by a scratch restore, copied off the server.
- [ ] `.env` and application backup taken.
- [ ] Encryption key set, backed up in two places, not in any chat or ticket.
- [ ] Pre-migration checks 2.1 to 2.5 return the expected results.
- [ ] Both money switches are `false` in the environment.
- [ ] A named person is watching logs for the first 30 minutes.
- [ ] The rollback steps below have been read by the person deploying.

NO-GO if any of: a pre-migration check fails; no verified backup; the
encryption key is not backed up; the starting revision is not `e2f3a4b5c6d7`.

## 9. Rollback

Criteria: the backend does not start; 5xx on payment creation, the callback or
login that is not explained within 15 minutes; any commission, cashout or
journal total differs from the 2.6 baseline; a payout row appears.

Preferred, in this order:
1. **Roll back the code only** to the previous release and restart. The
   schema changes are additive, so the previous code runs on the new schema:
   it does not know the new columns and tables and ignores them. Leave the
   migrations in place.
2. Only if a migration itself failed: it ran in a transaction and left
   nothing behind. Fix the cause and repeat; there is nothing to undo.
3. **Do not run `alembic downgrade` on production as a routine step.** It drops
   the wallet-change history, the configuration and its audit history, the
   stored credentials and pending wallet confirmations. It is acceptable only
   immediately after the upgrade, before the new code has served any request,
   and only after confirming those tables are empty:
   `SELECT (SELECT count(*) FROM payout_wallet_changes), (SELECT count(*) FROM payment_credentials), (SELECT count(*) FROM payment_config_audit);`
4. **Restoring the database backup is the last resort.** It discards every
   write since the backup (registrations, votes, payments). Use it only for
   data corruption, with the site in maintenance, and reconcile payments made
   in the gap against the provider dashboard afterwards.

## 10. Staging verification plan (not executed)

Environment: a separate host or container set; its own PostgreSQL database
restored from a scrubbed copy or built empty; its own `SECRET_KEY` and its own
`PAYMENT_SETTINGS_ENCRYPTION_KEY`; no production secret of any kind;
`NOWPAYMENTS_SANDBOX=true` with sandbox credentials, or no provider
credentials at all; both money switches `false`; outbound email pointed at a
test inbox.

1. Deploy the candidate commit; run both migrations; `alembic current` = head.
2. Run the backend suite on staging's PostgreSQL:
   `RUN_POSTGRES_TESTS=1 POSTGRES_ADMIN_URL=<staging admin URL on localhost> pytest -m postgres tests/integration`.
3. Create synthetic users (a sponsor, two members) and synthetic commissions.
4. Admin permissions: without, with `manage_payment_settings`, with
   `process_cashouts`; confirm each can do only what it should.
5. Payment configuration UI: change each group, wrong password refused,
   history recorded, credentials write-only, blank field keeps the value.
6. Wallet verification: change, email link, expiry, reuse refused, hold.
7. Cashout lifecycle with the provider mocked or sandboxed: USD request,
   cancel, settlement refused while disabled; crypto engine off = no row.
8. Reconciliation page: owed totals equal the synthetic commissions.
9. Frontend smoke: wallet page, cashout panel, admin Finance & Payments.
10. Health checks and logs clean for one hour.

Only with separate authorisation, on staging with sandbox credentials: one
sandbox payment end to end (proves the IPN secret and signature), and one
sandbox payout (proves login, second factor, status shape and the unique
reference).

## 11. Network fee accounting and the open proposal

### 11.1 Company-paid crypto network fee (approved 2026-10-10, implemented, not deployed)

A completed crypto cashout posts its own balanced entry: Dr 2001 commissions
payable (gross) / Cr 1001 (what the member received). When MyHigh5 bears the
network fee (policy COMPANY_PAYS) the provider takes that fee from the same
balance, and a SECOND entry records it:

    Dr 5005 Crypto payout network fees (paid by MyHigh5)
        Cr 1001 USDT Treasury (BSC)

Why 1001: it is the account pay-ins are debited to and payouts are credited
from; it stands for the USDT (BSC) balance held at the provider. The fee
leaves that same balance.

Rules built in:
- Only an ACTUAL fee is posted. The estimate taken when the payout was created
  is never posted.
- Automatic posting happens only when the provider reports the fee on the
  finished payout AND reports that it came from the merchant balance. The
  provider does not document the values of its `fee_paid_by` field, so none is
  assumed: automatic posting is OFF until those values are confirmed with the
  provider and set in `NOWPAYMENTS_FEE_PAID_BY_COMPANY_VALUES`.
- Until then (and whenever the provider reports nothing) the payout is listed
  under Reconciliation as "fee not recorded yet", and an administrator with
  `process_cashouts` records it from the provider's statement in Cashout
  Transactions (0 = the provider charged none).
- Once per cashout. Nothing for a failed, rejected, unknown or member-paid
  payout. A missing or inactive account refuses the posting; the payout itself
  is still completed.

Currency and precision:
- The payout currency is USDT, which this ledger carries at 1 USDT = 1 USD (as
  the payout amount itself is). No conversion is applied; a payout in any other
  kind of currency is refused by the posting and needs a manual entry.
- The ledger stores cents. A fee is rounded half-up to the cent and the exact
  reported figure is kept in the audit trail; a fee under half a cent is
  recorded as "none" and posts no entry. Reconciliation shows the exact total
  next to the ledger total and the difference rounding left out, so the books
  can be agreed with the provider's statement; that difference is not posted.
- A completed payout whose fee is not recorded is listed under Discrepancies
  (warning `NETWORK_FEE_NOT_RECORDED`): the report never shows it as clean.
- The chart-of-accounts seed (`init_coa.py`, run by `start.py` and by the admin "ensure chart of accounts" action) creates 5005 only
  if it is missing; like the migration, it never renames or redescribes an
  account 5005 that already exists. No other account's seeding changed.
- The 1 USDT = 1 USD basis is written into each fee's audit record. It is the
  ledger's existing convention, not a market valuation: nothing re-measures
  account 1001 and nothing posts to 7110.

Not verified with the provider (do this on staging or with its support before
switching automatic posting on): that a finished payout reports its fee, the
unit of that fee, and the `fee_paid_by` values.

Known limit, outside this change: a correction of a fee already recorded is a
manual reversing journal entry by accounting; the application records one fee
per cashout. Provider fees on PAY-INS (the provider settles slightly less than
the invoice price) are not booked anywhere and are not part of this change.

### 11.2 Unique provider payment id on `deposits` (awaiting approval, NOT implemented)

`deposits.external_payment_id` has no unique rule. Only NOWPayments writes it
and the table has no provider column, so the proposed rule is on the id alone:

```sql
-- Read-only check first. Expect: no rows.
-- (Run on production 2026-10-10 in a read-only transaction: no rows; 157
-- deposits = 110 without an id, 0 empty, 41 numeric, 6 in another format.)
SELECT external_payment_id, count(*), array_agg(id ORDER BY id)
FROM deposits
WHERE external_payment_id IS NOT NULL AND external_payment_id <> ''
GROUP BY external_payment_id HAVING count(*) > 1;

-- Shape of the legacy values (how many never reached a provider).
SELECT count(*) FILTER (WHERE external_payment_id IS NULL)  AS null_ids,
       count(*) FILTER (WHERE external_payment_id = '')     AS empty_ids,
       count(*) FILTER (WHERE external_payment_id ~ '^[0-9]+$') AS numeric_ids,
       count(*) FILTER (WHERE external_payment_id <> '' AND external_payment_id !~ '^[0-9]+$') AS other_ids
FROM deposits;

-- The rule (a later migration, only after the first query returns no rows).
CREATE UNIQUE INDEX uq_deposits_external_payment_id ON deposits (external_payment_id)
WHERE external_payment_id IS NOT NULL AND external_payment_id <> '';
```

NULL and empty values (legacy rows that never had a provider payment) are
left out of the rule. If the check returns rows they are reconciled by hand;
no row is deleted or rewritten by a migration. If a second payment provider
is ever added, the table first needs a provider column and the rule becomes
(provider, id).

Until the rule exists the application refuses the two cases it would
prevent: a new payment is never given an id another deposit holds, and a
callback that matches more than one deposit by payment id credits neither.
