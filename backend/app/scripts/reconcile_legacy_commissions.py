#!/usr/bin/env python3
"""Historical (pre NEW_V2) commissions: report, and the reviewed corrections.

Nothing here decides whether a historical commission is honoured or cancelled:
that is an administrator's recorded decision (commission_payout_reviews, made
through Admin > Cashouts > commission reviews). Until it exists, every
historical commission stays HELD from payout (commission_payout_hold).

Commands (each a DRY RUN by default: computed in a transaction, rolled back,
before/after printed; --apply commits and requires --actor-id, the approving
administrator, who is named in one audit_trails row per correction):

  report                       read-only: every historical commission with its
                               facts (journal posted?, payment recorded by an
                               administrator?, did its referral link come from
                               the admin "fallback sponsor" assignment of
                               2026-04-22 (commit acd90ff)?), and the ledger
                               vs subledger figures.
  fix-duplicate-journal        reverse every commission journal of a deposit
                               posted more than once (keeps the first), with a
                               linked compensating entry.
  post-missing-accruals        post the commission expense/liability of open
                               historical commissions whose deposit has no
                               commission journal (Dr 5001 / Cr 2001 level 1,
                               Cr 2002 levels 2-10), one entry per deposit.
                               With --apply, every deposit must be named
                               (--deposit) with the amount the owner approved
                               (--expect DEPOSIT=AMOUNT); the deposit and its
                               commissions are locked and re-validated in the
                               same transaction, and ANY invalid source or
                               mismatch refuses the whole batch.
  execute-cancellations        carry out recorded CANCEL decisions: the row
                               becomes CANCELLED and, where its accrual is in
                               the ledger, a compensating entry is posted.

    python -m app.scripts.reconcile_legacy_commissions report
    python -m app.scripts.reconcile_legacy_commissions fix-duplicate-journal --deposit 102 [--apply --actor-id N]
    python -m app.scripts.reconcile_legacy_commissions post-missing-accruals [--deposit N ...]
    python -m app.scripts.reconcile_legacy_commissions post-missing-accruals --deposit N --expect N=1.20 ... --apply --actor-id N
    python -m app.scripts.reconcile_legacy_commissions execute-cancellations [--apply --actor-id N]

Corrections never run concurrently: each takes one transaction-scoped
advisory lock (PostgreSQL) and re-reads what it corrects after the lock, so a
second run waits and then finds the work done. Every correction is
idempotent (structured idempotency keys, unique in the database).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.accounting import AuditTrail, JournalEntry
from app.models.affiliate import AffiliateCommission, AffiliateTree, CommissionStatus
from app.models.financial_controls import CommissionPayoutReview
from app.models.payment import Deposit, DepositStatus
from app.models.user import User
from app.services import ledger_snapshot
from app.services.commission_payout_hold import historical_clause
from app.services.financial_reversal import is_reversed_deposit
from app.services.financial_integrity import money
from app.services.new_model_ledger import Line, PostingType, SourceType, is_new_model, is_reversed, post_entry, reverse_entry

LEGACY_FIX_SOURCE = "LEGACY_COMMISSIONS"
ACCRUAL_POSTING = "COMMISSION_ACCRUAL_CORRECTION"
FALLBACK_WINDOW = (datetime(2026, 4, 22), datetime(2026, 9, 10, 23, 59, 59))   # acd90ff .. a7a35f8
OPEN = (CommissionStatus.PENDING, CommissionStatus.APPROVED)
LOCK_NAME = "mh5_legacy_commission_corrections"
AUDIT_ACCRUAL = "LEGACY_COMMISSION_ACCRUAL_POSTED"
AUDIT_DUPLICATE = "LEGACY_COMMISSION_DUPLICATE_REVERSED"


class CorrectionRefused(Exception):
    """Nothing was posted: the source data is not what the correction expects."""


def _serialize(db: Session) -> None:
    """One correction at a time (PostgreSQL); released by the caller's commit or rollback."""
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:n))"), {"n": LOCK_NAME})


def _audit(db: Session, *, action: str, entry_id: int, actor_id: Optional[int], now: datetime, values: dict) -> None:
    db.add(AuditTrail(table_name="journal_entries", record_id=entry_id, action=action, user_id=actor_id,
                      timestamp=now, new_values=values))


def _mentions(description: str, deposit_id: int) -> bool:
    return re.search(rf"Deposit #{int(deposit_id)}(?!\d)", description or "") is not None


def commission_journals(db: Session, deposit_id: int) -> List[JournalEntry]:
    """Commission journals of a historical deposit: the legacy '(Commissions)' entries and this tool's
    corrections. Reversal entries are excluded."""
    rows = (db.query(JournalEntry)
            .filter(JournalEntry.reverses_entry_id.is_(None),
                    (JournalEntry.description.like(f"%Deposit #{int(deposit_id)}%(Commissions)%"))
                    | ((JournalEntry.source_type == LEGACY_FIX_SOURCE) & (JournalEntry.source_id == deposit_id)
                       & (JournalEntry.posting_type == ACCRUAL_POSTING)))
            .order_by(JournalEntry.id).all())
    return [r for r in rows if r.source_type == LEGACY_FIX_SOURCE or _mentions(r.description, deposit_id)]


def fallback_link(db: Session, user_id: int) -> Optional[dict]:
    """The user's sponsor link was written by the admin 'fallback sponsor' code (acd90ff): an
    affiliate_tree row at level 1 with no path, written after registration inside the window."""
    user = db.get(User, user_id)
    tree = db.query(AffiliateTree).filter(AffiliateTree.user_id == user_id).first()
    if user is None or tree is None or tree.path is not None or int(tree.level or 0) != 1 or tree.join_date is None:
        return None
    if not (FALLBACK_WINDOW[0] <= tree.join_date <= FALLBACK_WINDOW[1]):
        return None
    if user.created_at and tree.join_date <= user.created_at + timedelta(hours=1):
        return None
    return {"user_id": user_id, "sponsor_id": tree.sponsor_id, "assigned_at": tree.join_date.isoformat()}


def chain_links(db: Session, payer_id: int, level: int) -> List[int]:
    """The users whose sponsor link a level-N commission of this payer used: payer, s1, ..., s(N-1)."""
    out, current = [], payer_id
    for _ in range(max(level, 1)):
        out.append(current)
        user = db.get(User, current)
        if user is None or user.sponsor_id is None:
            break
        current = int(user.sponsor_id)
    return out[:level]


def report(db: Session) -> dict:
    rows = (db.query(AffiliateCommission).filter(historical_clause())
            .order_by(AffiliateCommission.deposit_id, AffiliateCommission.level, AffiliateCommission.id).all())
    reviews = {r.commission_id: r for r in db.query(CommissionPayoutReview).all()}
    items, per_deposit = [], defaultdict(list)
    for c in rows:
        deposit = db.get(Deposit, c.deposit_id) if c.deposit_id else None
        links = chain_links(db, c.source_user_id, c.level)
        fallback = [f for f in (fallback_link(db, u) for u in links) if f]
        used_fallback = [f for f in fallback if c.transaction_date and f["assigned_at"] <= c.transaction_date.isoformat()]
        journals = commission_journals(db, c.deposit_id) if c.deposit_id else []
        review = reviews.get(c.id)
        flags = []
        if used_fallback:
            flags.append("REFERRAL_LINK_FROM_ADMIN_FALLBACK")
        if deposit is not None and deposit.validated_by is not None:
            flags.append("PAYMENT_RECORDED_BY_ADMINISTRATOR")
        if c.level > 1:
            flags.append("RETIRED_MULTI_LEVEL")
        item = {"commission_id": c.id, "deposit_id": c.deposit_id, "payer_id": c.source_user_id,
                "beneficiary_id": c.user_id, "level": c.level, "type": c.commission_type.value,
                "amount": str(money(c.commission_amount)), "status": c.status.value,
                "date": c.transaction_date.date().isoformat() if c.transaction_date else None,
                "journal_entries": [j.id for j in journals], "flags": flags, "fallback_links_used": used_fallback,
                "review": ({"decision": review.decision, "executed_at": review.executed_at.isoformat()
                            if review.executed_at else None} if review else None)}
        items.append(item)
        per_deposit[c.deposit_id].append(item)
    open_items = [i for i in items if i["status"] in ("PENDING", "APPROVED")]
    flagged = [i for i in open_items if "REFERRAL_LINK_FROM_ADMIN_FALLBACK" in i["flags"]]
    return {
        "historical_commissions": items,
        "deposits_without_commission_journal": sorted(d for d, its in per_deposit.items()
                                                      if d and not its[0]["journal_entries"]),
        "deposits_with_duplicate_commission_journal": sorted(d for d, its in per_deposit.items()
                                                             if d and len(its[0]["journal_entries"]) > 1),
        "open_total": str(sum((Decimal(i["amount"]) for i in open_items), Decimal("0.00"))),
        "open_flagged_fallback_total": str(sum((Decimal(i["amount"]) for i in flagged), Decimal("0.00"))),
        "open_flagged_fallback_ids": [i["commission_id"] for i in flagged],
        "ledger": ledger_snapshot.snapshot(db)["ledger_vs_subledger"],
    }


def fix_duplicate_journal(db: Session, deposit_ids: List[int], *, actor_id: Optional[int] = None,
                          now: Optional[datetime] = None) -> dict:
    now = now or datetime.utcnow()
    _serialize(db)
    done = []
    for deposit_id in deposit_ids:
        journals = [j for j in commission_journals(db, deposit_id) if j.source_type != LEGACY_FIX_SOURCE]
        for duplicate in journals[1:]:
            if is_reversed(db, duplicate):
                continue
            entry = reverse_entry(db, duplicate, reason=f"duplicate commission journal of Deposit #{deposit_id} "
                                                       f"(first posted as {journals[0].entry_number})")
            _audit(db, action=AUDIT_DUPLICATE, entry_id=entry.id, actor_id=actor_id, now=now,
                   values={"deposit_id": deposit_id, "duplicate_entry_id": duplicate.id, "kept_entry_id": journals[0].id,
                           "amount": str(money(duplicate.total_debit))})
            done.append({"deposit_id": deposit_id, "duplicate_entry_id": duplicate.id, "reversal_entry_id": entry.id})
    db.flush()
    return {"reversed_duplicates": done}


def _validated_rows(db: Session, deposit_id: int) -> List[AffiliateCommission]:
    """Lock the deposit and ALL its commissions, re-read them, and return the open historical rows
    to accrue. Raises CorrectionRefused if anything is not a valid historical source."""
    deposit = db.query(Deposit).filter(Deposit.id == deposit_id).with_for_update().populate_existing().first()
    if deposit is None:
        raise CorrectionRefused(f"deposit {deposit_id} does not exist")
    if is_new_model(deposit.business_model_version):
        raise CorrectionRefused(f"deposit {deposit_id} is a NEW_V2 payment, not historical")
    if deposit.status != DepositStatus.VALIDATED or is_reversed_deposit(deposit):
        raise CorrectionRefused(f"deposit {deposit_id} is not a validated, unreversed payment")
    rows = (db.query(AffiliateCommission).filter(AffiliateCommission.deposit_id == deposit_id)
            .order_by(AffiliateCommission.id).with_for_update().populate_existing().all())
    open_rows, levels, beneficiaries = [], set(), set()
    for r in rows:
        if r.status == CommissionStatus.CANCELLED:
            continue
        if is_new_model(r.business_model_version):
            raise CorrectionRefused(f"deposit {deposit_id} carries a NEW_V2 commission (#{r.id})")
        if r.status not in OPEN or r.payout_reference:
            raise CorrectionRefused(f"commission #{r.id} of deposit {deposit_id} is {r.status.value} or reserved")
        if int(r.source_user_id) != int(deposit.user_id):
            raise CorrectionRefused(f"commission #{r.id} was not generated by the payer of deposit {deposit_id}")
        if money(r.commission_amount) <= 0 or not 1 <= int(r.level) <= 10:
            raise CorrectionRefused(f"commission #{r.id} has an invalid amount or level")
        if r.level in levels or r.user_id in beneficiaries:
            raise CorrectionRefused(f"deposit {deposit_id} has two commissions for one level or beneficiary")
        levels.add(r.level)
        beneficiaries.add(r.user_id)
        open_rows.append(r)
    if not open_rows:
        raise CorrectionRefused(f"deposit {deposit_id} has no open historical commission")
    return open_rows


def post_missing_accruals(db: Session, deposit_ids: Optional[List[int]] = None, *,
                          expected: Optional[Dict[int, Decimal]] = None, actor_id: Optional[int] = None,
                          now: Optional[datetime] = None) -> dict:
    """Post the missing accrual of each named (or, when none is named, each found) historical deposit.
    All or nothing: one refused deposit refuses the batch (CorrectionRefused; the caller rolls back)."""
    now = now or datetime.utcnow()
    _serialize(db)
    if not deposit_ids:
        deposit_ids = sorted({int(d) for (d,) in db.query(AffiliateCommission.deposit_id).filter(
            historical_clause(), AffiliateCommission.status.in_(OPEN), AffiliateCommission.deposit_id.isnot(None)
        ).distinct().all()})
    targets = sorted({int(d) for d in deposit_ids})
    if expected is not None and set(expected) != set(targets):
        raise CorrectionRefused("the approved amounts must name exactly the deposits being corrected")
    posted, already = [], []
    for deposit_id in targets:
        rows = _validated_rows(db, deposit_id)
        if commission_journals(db, deposit_id):
            already.append(deposit_id)                 # posted before (by the legacy flow or an earlier run)
            continue
        direct = sum((money(r.commission_amount) for r in rows if r.level == 1), Decimal("0.00"))
        indirect = sum((money(r.commission_amount) for r in rows if r.level != 1), Decimal("0.00"))
        total = money(direct + indirect)
        if expected is not None and money(expected[deposit_id]) != total:
            raise CorrectionRefused(f"deposit {deposit_id}: accrual {total} differs from the approved "
                                    f"{money(expected[deposit_id])}")
        lines = [Line("5001", debit=total, description="Historical commission expense (correction)")]
        if direct:
            lines.append(Line("2001", credit=direct, description="Historical direct commissions payable"))
        if indirect:
            lines.append(Line("2002", credit=indirect, description="Historical indirect commissions payable"))
        entry = post_entry(db, source_type=LEGACY_FIX_SOURCE, source_id=deposit_id, posting_type=ACCRUAL_POSTING,
                           lines=lines, description=f"Legacy commission accrual correction - Deposit #{deposit_id} "
                                                    f"(commissions {', '.join(str(r.id) for r in rows)})")
        _audit(db, action=AUDIT_ACCRUAL, entry_id=entry.id, actor_id=actor_id, now=now,
               values={"deposit_id": deposit_id, "commission_ids": [r.id for r in rows], "amount": str(total),
                       "direct": str(direct), "indirect": str(indirect)})
        posted.append({"deposit_id": deposit_id, "entry_id": entry.id, "commission_ids": [r.id for r in rows],
                       "amount": str(total)})
    db.flush()
    return {"accruals_posted": posted, "already_posted": already}


def execute_cancellations(db: Session, *, actor_id: Optional[int] = None, now: Optional[datetime] = None) -> dict:
    now = now or datetime.utcnow()
    _serialize(db)
    done = []
    reviews = (db.query(CommissionPayoutReview)
               .filter(CommissionPayoutReview.decision == "CANCEL", CommissionPayoutReview.executed_at.is_(None))
               .order_by(CommissionPayoutReview.id).with_for_update().all())
    for review in reviews:
        c = (db.query(AffiliateCommission).filter(AffiliateCommission.id == review.commission_id)
             .with_for_update().populate_existing().one())
        if is_new_model(c.business_model_version) or c.status not in OPEN or c.payout_reference:
            done.append({"commission_id": c.id, "skipped": f"not an open, unreserved historical row ({c.status.value})"})
            continue
        entry_id = None
        if c.deposit_id and commission_journals(db, int(c.deposit_id)):
            amount = money(c.commission_amount)
            entry = post_entry(db, source_type=SourceType.COMMISSION, source_id=c.id, posting_type=PostingType.REVERSAL,
                               key_suffix="legacy-cancel",
                               lines=[Line("2001" if c.level == 1 else "2002", debit=amount,
                                           description="Cancelled historical commission"),
                                      Line("5001", credit=amount, description="Cancelled historical commission")],
                               description=f"Cancellation of historical commission #{c.id} after review "
                                           f"(Deposit #{c.deposit_id})")
            entry_id = entry.id
        old_status = c.status.value
        c.status = CommissionStatus.CANCELLED
        review.executed_at = now
        db.add(AuditTrail(table_name="affiliate_commissions", record_id=c.id, action="COMMISSION_CANCELLED_AFTER_REVIEW",
                          user_id=actor_id, timestamp=now, old_values={"status": old_status},
                          new_values={"status": "CANCELLED", "review_id": review.id, "reason": review.reason[:300],
                                      "compensating_entry_id": entry_id}))
        done.append({"commission_id": c.id, "compensating_entry_id": entry_id})
    db.flush()
    return {"cancellations": done}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("command", choices=["report", "fix-duplicate-journal", "post-missing-accruals",
                                            "execute-cancellations"])
    parser.add_argument("--deposit", type=int, action="append")
    parser.add_argument("--expect", action="append", default=[], metavar="DEPOSIT=AMOUNT",
                        help="post-missing-accruals: the approved accrual of a deposit (required with --apply)")
    parser.add_argument("--actor-id", type=int, default=None, help="the approving administrator (required with --apply)")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    try:
        expected = ({int(k): Decimal(v) for k, v in (item.split("=", 1) for item in args.expect)}
                    if args.expect else None)
    except (ValueError, ArithmeticError):
        print("--expect takes DEPOSIT=AMOUNT, e.g. --expect 115=1.20")
        return 2
    if args.apply and args.command != "report":
        if not args.actor_id:
            print("--apply needs --actor-id (the approving administrator)")
            return 2
        if args.command == "post-missing-accruals" and (not args.deposit or expected is None):
            print("post-missing-accruals --apply needs every --deposit and its approved --expect DEPOSIT=AMOUNT")
            return 2

    from app.db.session import SessionLocal
    from app.scripts.load_exposed_password_fingerprints import _database_label

    db = SessionLocal()
    try:
        if args.command == "report":
            print(json.dumps({"database": _database_label(), **report(db)}, indent=2, default=str))
            db.rollback()
            return 0
        before = ledger_snapshot.snapshot(db)
        if args.command == "fix-duplicate-journal":
            if not args.deposit:
                print("--deposit is required")
                return 2
            result = fix_duplicate_journal(db, args.deposit, actor_id=args.actor_id)
        elif args.command == "post-missing-accruals":
            try:
                result = post_missing_accruals(db, args.deposit, expected=expected, actor_id=args.actor_id)
            except CorrectionRefused as exc:
                db.rollback()
                print(json.dumps({"database": _database_label(), "refused": str(exc), "changed": False}))
                return 2
        else:
            result = execute_cancellations(db, actor_id=args.actor_id)
        after = ledger_snapshot.snapshot(db)
        if args.apply:
            db.commit()
        else:
            db.rollback()
        print(json.dumps({"database": _database_label(), "mode": "APPLIED" if args.apply else "DRY RUN (rolled back)",
                          **result, "changes": ledger_snapshot.diff(before, after),
                          "ledger_after": after["ledger_vs_subledger"]}, indent=2, default=str))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
