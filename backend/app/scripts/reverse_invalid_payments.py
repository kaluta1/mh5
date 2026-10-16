#!/usr/bin/env python3
"""Reverse payments that were recorded as received but never arrived.

For each named deposit, in ONE transaction for the whole batch:
  * refuses unless it is a NEW_V2 deposit, VALIDATED, recorded by an
    administrator (validated_by set), carries no provider payment id, is not
    already reversed, and none of its commissions is PAID or reserved for a
    payout;
  * reverses its own journals, revenue recognition and commission with the
    existing structured reversal (new_model_payments.reverse_new_model_deposit):
    every original entry stays and gets one linked compensating entry; the
    commission becomes CANCELLED;
  * sets the deposit FAILED (no entitlement remains) and appends an
    immutable reversal marker to its notes;
  * writes one audit_trails row INVALID_PAYMENT_REVERSED with the complete
    pre-state (deposit, commissions, journal and revenue rows) and the
    reversal entries.

DRY RUN BY DEFAULT: everything is computed inside a transaction that is then
rolled back, and the before/after reconciliation is printed. --apply commits
and requires --actor-id (the approving administrator, recorded in the audit row).
Idempotent: a deposit already carrying the marker is reported and skipped.

    python -m app.scripts.reverse_invalid_payments --deposit 101 --deposit 102 \\
        --case CASE-REF --evidence-ref "approval reference" [--apply --actor-id N]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from typing import List, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.accounting import AuditTrail, JournalEntry
from app.models.affiliate import AffiliateCommission, CommissionStatus
from app.models.business_model import RevenueRecognition
from app.models.payment import Deposit, DepositStatus
from app.services import ledger_snapshot
from app.services.financial_integrity import money
from app.services.financial_reversal import INVALID_PAYMENT_REVERSAL_MARKER, is_reversed_deposit
from app.services.new_model_ledger import SourceType, is_new_model

AUDIT_ACTION = "INVALID_PAYMENT_REVERSED"


class ReversalRefused(Exception):
    pass


def _commissions(db: Session, deposit_id: int) -> List[AffiliateCommission]:
    return (db.query(AffiliateCommission)
            .filter(or_(AffiliateCommission.deposit_id == deposit_id,
                        (AffiliateCommission.source_type == SourceType.DEPOSIT)
                        & (AffiliateCommission.source_id == deposit_id)))
            .order_by(AffiliateCommission.id).with_for_update().all())


def _journals(db: Session, deposit_id: int, commission_ids: List[int]) -> List[JournalEntry]:
    q = db.query(JournalEntry).filter(
        or_((JournalEntry.source_type == SourceType.DEPOSIT) & (JournalEntry.source_id == deposit_id),
            (JournalEntry.source_type == SourceType.COMMISSION) & (JournalEntry.source_id.in_(commission_ids or [-1]))))
    return q.order_by(JournalEntry.id).all()


def check(db: Session, deposit: Optional[Deposit], deposit_id: int) -> Optional[str]:
    """Why this deposit must not be reversed by this tool (None when it may)."""
    if deposit is None:
        return f"deposit {deposit_id} does not exist"
    if not is_new_model(deposit.business_model_version):
        return f"deposit {deposit_id} is not a NEW_V2 deposit (legacy deposits need a separate procedure)"
    if deposit.status != DepositStatus.VALIDATED:
        return f"deposit {deposit_id} is {deposit.status.value}, not validated"
    if (deposit.external_payment_id or "").strip():
        return f"deposit {deposit_id} has a provider payment id: use the provider refund path, not this tool"
    if deposit.validated_by is None:
        return f"deposit {deposit_id} was not recorded by an administrator"
    for c in _commissions(db, deposit.id):
        if c.status == CommissionStatus.PAID:
            return f"commission {c.id} of deposit {deposit_id} is PAID: needs a clawback decision, not this tool"
        if c.payout_reference:
            return f"commission {c.id} of deposit {deposit_id} is reserved for a payout: reconcile the payout first"
    return None


def reverse(db: Session, deposit_ids: List[int], *, case: str, evidence_ref: str,
            actor_id: Optional[int] = None, now: Optional[datetime] = None) -> dict:
    """Reverse every listed deposit in the caller's transaction (no commit). Raises ReversalRefused
    (nothing changed) if any deposit fails the checks."""
    from app.services.new_model_payments import reverse_new_model_deposit

    now = now or datetime.utcnow()
    case = " ".join((case or "").split())
    evidence_ref = " ".join((evidence_ref or "").split())
    if len(case) < 4 or len(evidence_ref) < 6:
        raise ReversalRefused("--case (4+ chars) and --evidence-ref (6+ chars) are required")
    locked, skipped = [], []
    for deposit_id in deposit_ids:
        deposit = (db.query(Deposit).filter(Deposit.id == deposit_id)
                   .with_for_update().populate_existing().first())
        if deposit is not None and INVALID_PAYMENT_REVERSAL_MARKER in str(deposit.admin_notes or ""):
            skipped.append(deposit_id)                      # already reversed by this tool: idempotent
            continue
        if deposit is not None and is_reversed_deposit(deposit):
            raise ReversalRefused(f"deposit {deposit_id} was already reversed as a provider refund")
        reason = check(db, deposit, deposit_id)
        if reason:
            raise ReversalRefused(reason)
        locked.append(deposit)
    results = []
    for deposit in locked:
        commissions = _commissions(db, deposit.id)
        journals = _journals(db, deposit.id, [c.id for c in commissions])
        recognitions = (db.query(RevenueRecognition)
                        .filter(RevenueRecognition.source_type == SourceType.DEPOSIT,
                                RevenueRecognition.source_id == deposit.id).order_by(RevenueRecognition.id).all())
        before = {
            "deposit": {"id": deposit.id, "user_id": deposit.user_id, "product_type_id": deposit.product_type_id,
                        "amount": str(money(deposit.amount)), "currency": deposit.currency,
                        "status": deposit.status.value, "order_id": deposit.order_id,
                        "business_model_version": deposit.business_model_version,
                        "validated_by": deposit.validated_by,
                        "validated_at": deposit.validated_at.isoformat() if deposit.validated_at else None,
                        "is_used": bool(deposit.is_used), "admin_notes": deposit.admin_notes},
            "commissions": [{"id": c.id, "user_id": c.user_id, "amount": str(money(c.commission_amount)),
                             "status": c.status.value, "level": c.level} for c in commissions],
            "journal_entry_ids": [j.id for j in journals],
            "revenue_recognition_ids": [r.id for r in recognitions],
        }
        known_entries = {j.id for j in db.query(JournalEntry.id).all()}
        reverse_new_model_deposit(db, deposit, reason=f"Invalid payment reversal ({case})")
        deposit.status = DepositStatus.FAILED
        deposit.admin_notes = (f"{deposit.admin_notes or ''}\n{INVALID_PAYMENT_REVERSAL_MARKER} at {now.isoformat()}Z; "
                               f"case {case}; evidence {evidence_ref}").strip()
        db.flush()
        new_entries = sorted({j.id for j in db.query(JournalEntry.id).all()} - known_entries)
        db.add(AuditTrail(table_name="deposits", record_id=deposit.id, action=AUDIT_ACTION, user_id=actor_id,
                          timestamp=now, old_values=before,
                          new_values={"status": "failed", "case": case, "evidence_reference": evidence_ref,
                                      "reversal_journal_entry_ids": new_entries,
                                      "commissions_cancelled": [c.id for c in commissions]}))
        db.flush()
        results.append({"deposit_id": deposit.id, "reversal_entries": new_entries,
                        "commissions_cancelled": [c.id for c in commissions]})
    return {"reversed": results, "already_reversed": skipped}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--deposit", type=int, action="append", required=True)
    parser.add_argument("--case", required=True)
    parser.add_argument("--evidence-ref", required=True)
    parser.add_argument("--actor-id", type=int, default=None,
                        help="the approving administrator's id (audit; required with --apply)")
    parser.add_argument("--apply", action="store_true", help="commit (default: dry run, rolled back)")
    args = parser.parse_args(argv)
    if args.apply and not args.actor_id:
        print("--apply needs --actor-id (the approving administrator)")
        return 2

    from app.db.session import SessionLocal
    from app.scripts.load_exposed_password_fingerprints import _database_label

    db = SessionLocal()
    try:
        before = ledger_snapshot.snapshot(db)
        try:
            result = reverse(db, args.deposit, case=args.case, evidence_ref=args.evidence_ref, actor_id=args.actor_id)
        except ReversalRefused as exc:
            db.rollback()
            print(json.dumps({"database": _database_label(), "refused": str(exc), "changed": False}))
            return 2
        after = ledger_snapshot.snapshot(db)
        if args.apply:
            db.commit()
        else:
            db.rollback()
        print(json.dumps({"database": _database_label(), "mode": "APPLIED" if args.apply else "DRY RUN (rolled back)",
                          **result, "before": before, "after": after,
                          "changes": ledger_snapshot.diff(before, after)}, indent=2, default=str))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
