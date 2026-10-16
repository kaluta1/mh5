# Phase 1 — Financial controls and security changes

Scope: commission payouts, manually recorded payments, referral-tree integrity.
Commission payouts remain **disabled**; nothing here enables them.

## 1. Historical commissions are held from payout

* A commission is **current** only when `business_model_version = 'NEW_V2'`.
  Every other row (NULL or any other stamp, e.g. `LEGACY_V1`) is
  **historical**, using the same rule as `new_model_ledger.is_new_model`.
* A historical commission is excluded from every path that selects money to
  pay: cashout reservation, the crypto payout engine, the older payout
  service, promotion of PENDING rows, and the "available" balance. Members see
  it as *held / under review*. The hold changes no commission row.
* It becomes payable only after an authorised administrator records an
  explicit **RELEASE** decision (`commission_payout_reviews`, one per
  commission, final). A **CANCEL** decision keeps it held; the reconciliation
  procedure carries the cancellation out with a compensating entry.
* A decision needs the `process_cashouts` permission (or Super Admin) and the
  administrator's current password, is refused on one's own commission and on
  rows that are not open, and is audited (`COMMISSION_PAYOUT_REVIEWED`).
* Single code path: `app/services/commission_payout_hold.py`
  (`historical_clause`, `payable_clause`, `held_clause`).

## 2. Manually recorded payments need two administrators (maker-checker)

* **Record** (`POST /admin/users/{id}/grant-payment`): the deposit stays
  PENDING; nothing is credited, posted to the ledger or commissioned.
* **Confirm** (`POST /admin/manual-payments/{id}/confirm`): a **different**
  administrator holding `grant_manual_payments`, with password and an evidence
  reference. Only then is the deposit validated and the normal pipeline run,
  in one transaction.
* The checker is never the maker, never the member, never anyone who earns
  from the payment; the confirmation is refused if any resulting commission
  would go to the maker or the checker.
* **Reject** (checker) / **Cancel** (maker) close the request; a deposit the
  request created becomes FAILED.
* The queue (`GET /admin/manual-payments`, which shows member contact details)
  is visible only to administrators holding `grant_manual_payments` (or a
  Super Admin); any other administrator gets 403 and the refusal is audited.
* Concurrency: request row locked `FOR UPDATE`, one state transition; a second
  decision gets `ALREADY_DECIDED`. Database backstops: one open request per
  member and product (partial unique index), `decided_by <> requested_by`
  (CHECK). Every step and every refusal is audited.
* Administrator text (reason, evidence, note) is written into the deposit's
  notes; text containing a system reversal marker is refused
  (`TEXT_NOT_ALLOWED`), so nobody can make a deposit look reversed.
* Consequence: with a single authorised administrator, no manual payment can
  be completed. This is intended.

## 3. Database guards (migration `b7d9f1a3c5e7`)

| Guard | Rule |
|---|---|
| `ck_users_sponsor_not_self` | nobody sponsors themselves |
| `trg_users_sponsor_no_cycle` | refuses a sponsor change that would close a cycle; walks at most 1,000 ancestors; ignores an existing loop that does not involve the member (never blocks unrelated changes or registrations); serialised by a transaction-scoped advisory lock so two concurrent changes cannot close a cycle together |
| `ck_affiliate_commissions_amount_positive` | commission amount > 0 |
| `ck_affiliate_commissions_level_range` | level 1–10 |
| `ck_affiliate_commissions_new_model_level_one` | a NEW_V2 commission is level 1 (the active program pays direct referrals only) |
| `uq_affiliate_commissions_deposit_user`, `uq_affiliate_commissions_source_user` | one commission per payment / structured source and beneficiary (created if missing) |

The migration checks existing data first and stops, changing nothing, if any
row would violate a guard. Existing referral links are never rewritten by it.

## 4. Referral links are never changed silently

Application paths that write `sponsor_id`: registration (new account only),
join code and `set_sponsor` (both refuse reassignment and cycles via
`affiliate_hierarchy.validate_sponsor_assignment`), and the explicit
correction script below. No update schema accepts `sponsor_id`.

## 5. Correction scripts (dry run by default, idempotent, audited)

| Script | Purpose |
|---|---|
| `app/scripts/reverse_invalid_payments.py` | reverse administrator-recorded payments that never arrived: structured compensating entries, commission cancelled, deposit FAILED with a reversal marker, full pre-state audited (`INVALID_PAYMENT_REVERSED`); refuses anything with a provider id or a paid/reserved commission |
| `app/scripts/reconcile_legacy_commissions.py` | report on historical commissions; reverse duplicated commission journals; post missing historical accruals; execute recorded CANCEL decisions only. Corrections are serialised (advisory lock), re-validate their source under row locks in the same transaction (deposit historical, validated, unreversed; every commission open, unreserved, from the payer, valid level and amount, no duplicate level/beneficiary), refuse the whole batch on any invalid source, and with `--apply` require the exact deposits and approved amounts (`--expect DEPOSIT=AMOUNT`). One audit row per correction |
| `app/scripts/correct_sponsor_cycle.py` | remove one named sponsor link that closes a cycle, only if it still has the expected value; nothing else changes |

All three are dry runs by default; `--apply` requires `--actor-id` (the
approving administrator, recorded in the audit row). None is run
automatically. Production use requires a fresh backup, a rehearsal on a
restored copy and an explicit approval per script.

## 6. Commission policy (unchanged by Phase 1, now guarded)

* Level 1 (direct sponsor) only. No level 2–10 commission is created; the
  database refuses a current (NEW_V2) commission above level 1.
* Standard direct rate: 20%.
* Special direct rate: 40% (replacing, never added to, the 20%) on eligible
  ad-slot purchases for a sponsor who reached 10,000 KYC-verified direct
  referrals within six months of registration
  (`affiliate_rate_policy`). Still a level-1 commission. Other revenue
  categories keep their policy rate.
