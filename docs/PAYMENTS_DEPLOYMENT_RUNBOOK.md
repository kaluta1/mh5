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
| 4 | `c7d8e9f0a1b2` | `b6c7d8e9f0a1` | beneficiary-paid network fee (section 12): 7 columns on `payment_settings` (every default fails closed), 9 nullable columns on `affiliate_cashout_requests`, `cashout_fee_consents` |
| 5 | `d8e9f0a1b2c3` | `c7d8e9f0a1b2` | payout fee safety (section 13): 5 columns on `payment_settings` (no margin, gate of 0, not suspended), 4 nullable columns on `affiliate_cashout_requests` |
| 6 | `e9f0a1b2c3d4` | `d8e9f0a1b2c3` | review of a flagged payout (section 14): 4 nullable columns on `affiliate_cashout_requests` (all NULL: an existing flagged payout counts as not reviewed) and one check constraint |

All six are additive, idempotent and run in one transaction each. They read
and change no commission, deposit, cashout or journal row. `e9f0a1b2c3d4` is
the single head. The downgrade of `c7d8e9f0a1b2` refuses to run once a
member's acceptance or a beneficiary-paid payout has been recorded; the
downgrade of `d8e9f0a1b2c3` refuses while payouts are suspended or once a fee
reconciliation has been recorded; the downgrade of `e9f0a1b2c3d4` refuses once
a review has been recorded.

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
    `alembic upgrade b6c7d8e9f0a1`, then `alembic upgrade c7d8e9f0a1b2`, then
    `alembic upgrade d8e9f0a1b2c3`.
    `alembic current` must print `d8e9f0a1b2c3 (head)`, and
    `SELECT account_code, account_name, is_active FROM chart_of_accounts WHERE account_code = '5005';`
    must return one active row, and
    `SELECT count(*) FROM cashout_fee_consents;` must return 0.
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
- `Admin > Finance & Payments > Crypto Cashout`: "Provider fee behaviour" reads
  UNVERIFIED, both member fee limits read 0, "Network fee limits approved" is
  off. "Safety margin on the fee estimate" is empty and "Payouts allowed
  without a verified actual fee" reads 0. No suspension card is shown.
  Reconciliation states "No crypto payout can be created". Leave all of them
  as they are (sections 12.5 and 13.6).

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

**Superseded on 2026-10-11 by section 12: the owner decided that the network
fee is paid by the beneficiary.** What follows is kept as the record of what
account 5005 and its posting are. They remain in the code for a payout written
under the retired COMPANY_PAYS policy only (there is none in production); the
engine no longer creates such a payout and an ordinary payout never touches
5005.

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

## 12. Network fee paid by the beneficiary (Phase 3.2, implemented, not deployed)

Owner decision (2026-10-11): the network fee of a crypto payout is paid by the
beneficiary, who receives the payout net of it; the provider takes the fee out
of the amount (`DEDUCTED_BY_PROVIDER`); members accept the fee terms and a
maximum fee before automatic payouts.

### 12.1 How a payout works

1. The engine asks the provider for the fee of THIS payout, for its own amount.
2. That estimate is checked against the lowest limit that applies to the
   member (12.3). Above it: nothing is reserved or sent; the balance stays.
3. The WHOLE commission amount is handed to the provider. The application
   never subtracts the fee itself, so the fee is taken once. One function
   (`cashout_service.amount_to_send`) decides the amount and refuses every
   provider fee behaviour other than `DEDUCTED_BY_PROVIDER`.
4. When the provider reports the payout finished, the cashout is completed and
   its entry posted (12.2). The actual fee and the amount received are recorded
   on the cashout when they are known (12.4).

### 12.2 Accounting

One entry per completed payout, unchanged from before:

    Dr 2001 Commissions payable      gross
        Cr 1001 USDT Treasury (BSC)  gross

The whole amount left the treasury and the whole liability to the member is
settled; the fee is a cost the member bears out of their own proceeds. It is
neither income nor an expense of MyHigh5: no line, no entry, and account 5005
is not used. Gross, amount sent, fee estimate, actual fee and amount received
are kept on the cashout at eight decimal places (`amount_sent`,
`network_fee_estimate`, `network_fee_actual`, `net_received`), so the cent
ledger needs no rounding entry.

Nothing is posted for a payout that is pending, failed, rejected or of unknown
outcome; its commissions stay reserved or return to the balance as before.

This is an accounting DESIGN, not a confirmed requirement of the Singapore
standards. For Mr. Abeid or a Singapore-qualified accountant: (a) direct
settlement without a clearing account; (b) carrying USDT at 1 USDT = 1 USD
with no re-measurement; (c) the treasury account being credited when the
provider reports the payout finished, not when it is sent; (d) any GST or
Payment Services Act consequence.

### 12.3 Limits and the member's acceptance

- Two configurable limits: a share of the payout and an amount per payout. 0
  means "not set". When both are set the lower one applies. **Both ship as 0:
  no value is a decided policy.** No payout is created while neither is set.
- The limits, the provider fee behaviour and the terms version are approved in
  a SEPARATE change ("Network fee limits approved", typed phrase). Any later
  change to one of them withdraws the approval.
- A member accepts the terms exactly as shown (version and limits). A
  different version or limit is refused. One acceptance is in force per member
  (unique index). It ends when the member withdraws it, when the terms version
  is raised, or after the configured lifetime (0 = no expiry by time).
- The member's limit for a payout is the LOWEST of: the limits they accepted
  and the limits in force now. The company's own "maximum network fee share"
  still applies on top.
- A payout is never sent when the member would receive nothing, or less than
  "Minimum amount received".

### 12.4 The actual fee and what stops payouts

The provider documents neither the values of `fee_paid_by` nor the unit of
`fee`. So the actual fee is recorded automatically only when the reported
payer value is one that was confirmed with the provider and set in
`NOWPAYMENTS_FEE_PAID_BY_RECEIVER_VALUES`. Otherwise the payout is listed under
Reconciliation (`MEMBER_FEE_NOT_RECORDED`) and an administrator with
`process_cashouts` records the fee from the provider's statement, stating where
the provider took it from.

Each of these is listed as critical, SUSPENDS all payouts (section 13.4), sets
the provider fee behaviour back to UNVERIFIED and withdraws the approval, so
that NO further payout is created until a person has looked:

| Flag | Meaning |
|---|---|
| `PROVIDER_FEE_MODE_MISMATCH` | the provider charged its fee to the MyHigh5 balance instead of the payout. The member received the whole amount. The fee is recorded, NOT posted: the treasury account is overstated by it until accounting books it, with the owner's approval (the only case 5005 could apply to) |
| `PROVIDER_AMOUNT_MISMATCH` | the provider reports a larger amount than it was asked to send |
| `FEE_CAP_EXCEEDED` | the fee the provider took is above the member's limit. Nothing more is taken from the member; whether MyHigh5 makes up the difference is the owner's decision |

### 12.5 Activation (NOT part of the deployment; each step needs the owner)

Deploying this code changes nothing for members: every default fails closed.
Before a single payout can be created, in this order:

1. Confirm with the provider, in writing or by a sandbox payout: that the
   account's "withdrawal fee paid by" setting is Receiver and applies to API
   payouts; that a finished payout reports `fee` and `fee_paid_by`, their
   exact values and the unit of `fee`; whether `amount` is the amount requested
   or received; whether the minimum payout applies before or after the fee.
2. The owner decides the member fee limits. Set them; set "Provider fee
   behaviour" to DEDUCTED_BY_PROVIDER (typed phrase).
3. The owner approves the configured values; an administrator records it
   ("Network fee limits approved", typed phrase).
4. Set `NOWPAYMENTS_FEE_PAID_BY_RECEIVER_VALUES` and
   `NOWPAYMENTS_FEE_PAID_BY_COMPANY_VALUES` to the confirmed values.
5. Members accept the terms in their wallet page.
6. Only then the existing switches for automatic payouts (server switch,
   connection test, typed phrase), which also refuse while steps 2 and 3 are
   not done.

A settings row saved before this migration keeps its stored policy. If it
reads COMPANY_PAYS no payout is created (`FEE_POLICY_NOT_BENEFICIARY_PAID`)
until an administrator sets MEMBER_PAYS. Production has no settings row yet.

## 13. Payout fee safety (Phase 3.3 Stage A, implemented, not deployed)

**These controls do not guarantee the actual network fee of any payout, and
in particular not of the first one.** The member's limit is checked against
the provider's ESTIMATE. The provider decides the actual fee when it sends, and
it is known only afterwards. What follows keeps the exposure small and makes a
problem stop payouts; it cannot prevent the first payout's fee from being
higher than the limit.

### 13.1 What the member is told

The wallet page and the acceptance text now say: the member pays the network
fee; the provider deducts it; the member receives the remaining amount; the fee
shown before a payout is an estimate; the limit is checked against that
estimate (with a safety margin) and is NOT a limit on the actual fee, which may
differ and can be higher. Nothing reads "up to" a limit any more.

No acceptance record is invalidated by this: nothing was deployed with the
earlier wording, the terms version stays 1 and no acceptance exists in
production. If an acceptance had been collected under the earlier wording,
raising "Network fee terms version" would be the way to ask for it again.

### 13.2 Recording gate (a temporary hold, not a suspension)

No FURTHER payout is created while more payouts than "Payouts allowed without
a verified actual fee" are outstanding. Outstanding means: reserved, at the
provider or of unknown outcome, or completed without a VERIFIED actual fee.
The default is 0: one payout at a time, each verified before the next. It
does not block the first payout: with nothing outstanding one payout goes.

**Nothing is wrong while the gate holds payouts back.** The fee of an earlier
payout is simply not verified yet. Nothing is stored, nothing is audited as a
problem, the provider fee behaviour and the approval stay as they are, and the
gate lifts BY ITSELF as soon as the fee is verified. No reactivation exists
for it and none is needed. The engine reports `FEE_RECONCILIATION_PENDING`;
Reconciliation shows the figures under "temporary hold".

- A missing actual fee is never taken to be zero. A payout that is still at
  the provider is not a reconciled one. A completed beneficiary-paid payout
  with no reconciliation recorded (including any written before this
  migration) counts as NOT reconciled.
- A payout's fee counts as verified in exactly two ways, and either one
  releases the gate automatically when the number allows:
  1. `PROVIDER_VERIFIED`: the provider reported the fee, a payer value that was
     confirmed with it (`NOWPAYMENTS_FEE_PAID_BY_RECEIVER_VALUES`), and an
     amount that agrees with the confirmed meaning of `amount`
     (`NOWPAYMENTS_PAYOUT_AMOUNT_MEANS` = REQUESTED or RECEIVED). All three
     variables are empty by default, so by default nothing the provider
     reports verifies anything.
  2. `ADMIN_VERIFIED`: an administrator with `process_cashouts` records the
     fee, where the provider took it from, the evidence (provider statement,
     blockchain explorer or provider support; "other" never verifies) and the
     amount the member received, and that amount equals the payout less the
     fee. The record is audited with the evidence and the administrator.
- A figure entered WITHOUT that is kept as `ADMIN_UNVERIFIED` (or
  `PROVIDER_UNVERIFIED`), is listed under Reconciliation
  (`MEMBER_FEE_NOT_VERIFIED`) and does not count: the gate keeps holding. It
  may be replaced once, by a verified figure; a verified figure is never
  changed.
- Workers are serialised for this check (they lock the settings row before
  reserving), so several workers, a batch, a retry or a manual engine run
  cannot send more than the gate allows. Tested on PostgreSQL with concurrent
  workers.

### 13.3 Safety margin on the estimate

"Safety margin on the fee estimate" raises the provider's estimate before it
is compared with the member's limit: adjusted = estimate x (1 + margin / 100),
in exact decimal arithmetic, rounded up at eight decimal places. The adjusted
estimate is also what the minimum amount received, the company's own fee limit
and the provider balance check use.

- **It is empty by default and no value is a decided policy.** While it is
  empty no payout is created (`FEE_SAFETY_MARGIN_NOT_SET`) and the limits
  cannot be approved. 0 is a valid value only once the owner has decided it.
- Range 0 to 500, at most three decimal places. Changing it, or the gate
  number, withdraws the approval of the fee settings.
- It changes what is CHECKED, never what is sent: the whole amount is still
  handed to the provider and the fee is still taken once, by the provider.
- Three figures are kept apart on every payout: the provider's estimate, the
  adjusted estimate (with the margin used), and the actual fee.

### 13.4 Suspension (persistent, for a confirmed inconsistency only)

Payouts are SUSPENDED, with the reason, the time and the payout stored on the
settings row and an audit event (`PAYOUTS_SUSPENDED`), when a payout shows:

| Reason | When |
|---|---|
| `PROVIDER_FEE_MODE_MISMATCH` | the provider charged its fee to the MyHigh5 balance |
| `PROVIDER_AMOUNT_MISMATCH` | the reported amount is larger than the amount sent, or contradicts the confirmed meaning of `amount` |
| `FEE_CAP_EXCEEDED` | the actual fee is above the member's limit |

Each also sets the provider fee behaviour back to UNVERIFIED and withdraws the
approval. The first finding stays the stored reason.

A fee that is only missing or not verified is NOT in this list. That is the
recording gate (13.2).

While suspended: no payout is reserved or sent, by any worker, the scheduler
or "run engine"; payouts already at the provider are still reconciled;
automatic payouts cannot be switched on. **Restoring the provider fee
behaviour, the approval or any other setting does not lift it. Recording a fee
afterwards, verified or not, does not lift it.**

| | Recording gate (13.2) | Suspension (13.4) |
|---|---|---|
| Cause | an earlier payout's fee is not verified yet | a confirmed inconsistency |
| Stored | nothing | reason, time, payout; audit event |
| Settings | unchanged | fee behaviour to UNVERIFIED, approval withdrawn |
| Ends | by itself, when the fee is verified | only by an administrator's reactivation |

### 13.5 Reactivation by an administrator (after a suspension only)

Admin > Finance & Payments > Crypto Cashout shows the suspension. Lifting it
is a separate act (`POST /admin/finance/payouts/reactivate`), not a setting:

1. Review the payout named on the card in Cashout Transactions.
2. Record its actual fee as verified (13.2). A payout that genuinely does not
   add up stays flagged; decide with the owner what is done about it.
3. Confirm the provider's behaviour with the provider again, set "Provider fee
   behaviour" (typed phrase), then approve the fee settings (typed phrase,
   separate save).
4. Record the review of the flagged payout (section 14.2). Reactivation is
   refused while a flagged payout is not reviewed; the review itself lifts
   nothing.
5. Reactivate: `manage_payment_settings`, the current password, the phrase
   "REACTIVATE CRYPTO PAYOUTS" and a written note of what was reviewed (at
   least 20 characters, kept in the configuration history as
   `PAYOUTS_REACTIVATED`).

It is refused when payouts are not suspended, while a completed payout still
has no verified fee beyond the gate, or while the fee rules are not in force.
It changes no setting, sends nothing and does not switch automatic payouts on.

With every default in place (no confirmed provider values, gate of 0) the
ordinary flow is manual but needs no reactivation: one payout, an
administrator records its fee as verified, the next payout goes. It becomes
fully automatic when the provider's values are confirmed and set (13.6).

### 13.6 Prerequisites and provider dependencies

Migration: `d8e9f0a1b2c3` after `c7d8e9f0a1b2`; no data is rewritten. Nothing
else is needed to deploy; nothing here activates payouts.

Still to be confirmed with the provider before any payout (unchanged from
12.5, plus the last one): that Receiver applies to API payouts; the unit of
`fee`; the values of `fee_paid_by`; whether the minimum applies before or after
the fee; and **what `amount` on a finished payout means**, which decides
`NOWPAYMENTS_PAYOUT_AMOUNT_MEANS`.

Still to be decided by the owner (nothing is assumed): the member fee limits;
the safety margin; the gate number if not 0; whether MyHigh5 compensates a
member for an actual fee above their limit; how a fee the provider charged to
MyHigh5 is booked.

### 13.7 Remaining financial risks

- The actual fee of the first payout, and of any payout, can exceed the
  member's limit. The margin lowers the chance; the gate limits how many
  payouts are exposed before it is noticed; neither prevents it.
- Until the provider's values are confirmed, an excess is noticed only when an
  administrator records the fee. With the gate at 0 that is before the next
  payout; with a higher number, up to that many payouts later.
- An administrator's verified record releases the next payout without a second
  step. A wrong figure recorded as verified (for example a fee that was in
  fact above the limit, entered lower) would therefore let payouts continue.
  The record is audited with its evidence; there is no second-person check.
- Nothing is refunded automatically. A member who bore more than their limit
  is made whole only if the owner decides so, by hand.
- A fee the provider charged to MyHigh5 leaves the treasury account overstated
  until accounting books it.
- "Verified by an administrator" rests on that administrator reading the
  evidence correctly. The same administrator may hold both permissions; there
  is no second-person rule.

### 13.8 Rollback limits

Rolling the code back leaves the new columns in place and unused, which is
safe. But the PREVIOUS code does not know the suspension or the gate: if
payouts were ever enabled, rolling back to it would let them run without
either. Before any rollback, switch automatic payouts off (server switch) and
confirm no payout is at the provider. Do not run the downgrade once a
suspension or a reconciliation is recorded; it refuses, by design.

## 14. Admin workflow and stale configuration (Phase 3.3 Stage B, implemented, not deployed)

Stage B adds no financial rule and no number. It changes how an administrator
sees and works with what Stage A enforces, records the review of a flagged
payout, and closes two ways of acting on values that are no longer in force.
**Nothing here guarantees the actual network fee of a payout** (section 13),
and nothing here activates payouts.

### 14.1 Crypto Cashout page

Admin > Finance & Payments > Crypto Cashout Settings is grouped:

- A. Provider configuration
- B. Network fee estimates and limits
- C. Safety margin and recording gate
- D. Approval and activation
- E. Suspension and reactivation
- Payout limits and schedule (amounts, daily limits, intervals, retries)

Each section is saved on its own, with the password. At the top, "Current
configuration status" (`GET /admin/finance/payout-status`, read-only, the
provider is not asked) lists EVERY reason no payout is created, not only the
first, each with what to do and the section it is resolved in, and shows:
whether the provider fee behaviour is confirmed, whether the limits are
approved, whether a suspension is active, the recording gate, the required
settings that are not set, and whether the provider's reporting values are
confirmed on the server (`NOWPAYMENTS_FEE_PAID_BY_RECEIVER_VALUES`,
`NOWPAYMENTS_FEE_PAID_BY_COMPANY_VALUES`, `NOWPAYMENTS_PAYOUT_AMOUNT_MEANS`).
The temporary hold of the recording gate is marked as temporary; a suspension
is not. The list is built from the same rules the engine applies and is
covered by a test that the engine pays if and only if the list is empty.

`COMPANY_PAYS` and `CHARGED_TO_BALANCE` are shown as not available, with the
reason, and cannot be selected. They remain as values because rows written
before the owner's decision carry them; the server refuses them whatever a
client sends (unchanged from section 12).

### 14.2 Review of a flagged payout

A completed beneficiary-paid payout that did not add up carries a flag
(`PROVIDER_FEE_MODE_MISMATCH`, `PROVIDER_AMOUNT_MISMATCH`, `FEE_CAP_EXCEEDED`).
Admin > Finance & Payments > Reconciliation & Audit Logs > "Flagged Payout
Review" lists them (`GET /admin/cashouts/fee-exceptions`) with: why it was
flagged, what was expected (amount handed over, the estimate, the estimate with
the margin, the member's limit, what the member was expected to receive), what
happened (actual fee, amount received, how far above the estimate and the
limit), the evidence and the reconciliation state, what the provider reported
when the flag was raised, and the history of the payout's fee from the audit
trail.

An administrator records a review with `POST /admin/cashouts/{id}/fee-review`:

- needs the `process_cashouts` permission and the current password;
- needs a written note of what was checked and found (20 to 500 characters);
- is stored on the cashout (`fee_review_flag`, `fee_review_note`,
  `fee_reviewed_by`, `fee_reviewed_at`) and in the audit trail as
  `CASHOUT_FEE_EXCEPTION_REVIEWED` with the administrator, the time, the
  address and the state of the payout at that moment;
- is recorded once per flag. The same review sent again changes nothing; a
  different note or another administrator is refused (`ALREADY_REVIEWED`). If
  the payout is later flagged for something else, the earlier review no longer
  covers it, it is pending again, and both reviews stay in the audit trail.

**A review is a record and nothing else.** It does not clear the flag. It does
not verify the payout's actual fee: the recording gate still counts the payout
until its fee is verified (13.2). It does not lift a suspension: only the
reactivation of 13.5 does. It allows no payout. It changes no amount, no
commission and no journal entry.

One thing changed in 13.5: **reactivation is now also refused while a flagged
payout has not been reviewed.** The order is therefore: verify the actual fee,
restore and approve the settings, review the flagged payout, then reactivate.
The reactivation itself is unchanged (permission, password, phrase, note).

The existing `reviewed_by` / `reviewed_at` columns are not reused: they record
who cancelled, settled or resolved the cashout itself.

### 14.3 A cycle never pays under values that are no longer in force

Before Stage B a payout cycle read the configuration once and checked every
payout of that cycle against it. A change that withdrew the approval was
caught, but a limit that was changed AND approved again while the cycle was
running, or a change to a setting that needs no approval (the maximum single
payout, the daily limits), was not: the payout could still be reserved and
sent under the earlier values.

Now the cycle compares the configuration version it read with the one in
force, under the lock on the settings row:

1. immediately before a payout is reserved: if the version differs, nothing is
   reserved (`CONFIGURATION_CHANGED`);
2. again immediately before the payout is handed to the provider: if it
   differs, the reservation is released (the cashout is closed as cancelled
   with `CONFIGURATION_CHANGED`, the commissions are available again) and the
   provider is not called. It does not count as a failed attempt of the
   member's.

Either way the cycle stops; the next cycle starts from the configuration in
force. Because the second check holds the settings lock until the payout is
marked as handed over, a change is either seen by it or waits until after it:
it cannot fall in between. The version a payout was reserved under is written
to its `CASHOUT_RESERVED` audit record (`settings_version`). A suspension that
arrives during a cycle is still reported as `PAYOUTS_SUSPENDED`.

### 14.4 Nobody approves values they were not shown

`PUT /admin/finance/settings` accepts `expected_version`, the configuration
version the page was showing; the Admin Panel always sends it. If the
configuration has changed since, nothing is stored (`STALE_CONFIGURATION`,
"reload and review"). A change that approves or switches something on (the
approval of the fee settings, the confirmation of the provider fee behaviour,
automatic payouts, USD settlement) is refused without it (`VERSION_REQUIRED`).
Before this, administrator A could approve limits that administrator B had
changed after A loaded the page.

### 14.5 An action is decided on the row as it is under the lock

Found while testing Stage B on PostgreSQL, in code that was already there:
the administrator actions on a cashout (record a fee, settle, resolve, cancel)
locked the row but kept the values of the copy loaded before the lock. Two
administrators with the same cashout open could therefore both pass a check
that only one of them should pass; for example a fee already recorded as
VERIFIED could be replaced by a second verified figure. Each of these actions,
and the new review, now re-reads the row under the lock. Nothing was deployed
with this, and no payout was ever created, so no stored record is affected.

The same pattern exists for the member's own row in the member-facing calls
(change the payout wallet, choose the cashout method, request a USD cashout,
accept the fee terms). It was NOT changed in Stage B (outside its scope); the
database's unique rules and the existing tests cover the money-moving cases.
It should be reviewed before payouts are activated.

### 14.6 Deployment and rollback

Migration: `e9f0a1b2c3d4` after `d8e9f0a1b2c3`; four nullable columns and one
check constraint; no row is rewritten. The frontend and the backend must be
deployed together: the new page needs `payout-status`, `fee-exceptions` and
`crypto_sections`, and the backend refuses an approval without
`expected_version`, which only the new page sends.

Rolling the code back leaves the columns in place and unused, which is safe.
The previous code does not have the version checks of 14.3 and 14.4. Do not
run the downgrade once a review is recorded; it refuses, by design.

### 14.7 Still open

For the owner (nothing is assumed, and Stage B decided none of them): the
member fee limits; the safety margin; the gate number; whether MyHigh5
compensates a member for a fee above their limit; how a fee charged to MyHigh5
is booked; whether an approval, a verified fee record, a review or a
reactivation needs a second person. Today one administrator who holds both
permissions can do all four; Stage B did not introduce a two-person rule.

With the provider (unchanged from 13.6): that Receiver applies to API payouts;
the unit of `fee`; the values of `fee_paid_by`; what `amount` means; whether
the minimum applies before or after the fee.
