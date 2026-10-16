#!/usr/bin/env python3
"""Remove ONE sponsor link that closes a referral cycle (owner-approved account only).

The account must currently have exactly the expected sponsor and must sit on a
cycle (its sponsor chain returns to it). Its sponsor_id is set to NULL: the
account becomes the root of its tree again. Nothing else changes: no other
account, no affiliate_tree row (kept as history), no commission. One
audit_trails row SPONSOR_CORRECTED records the old link, whether it carried
the admin 'fallback sponsor' fingerprint (commit acd90ff), the evidence
reference and the approving administrator.

DRY RUN BY DEFAULT (rolled back); --apply commits and requires --actor-id. Idempotent: an account that
no longer has the expected sponsor is reported and left alone.

    python -m app.scripts.correct_sponsor_cycle --account ID --expect-sponsor ID \\
        --evidence-ref "owner approval ref" [--apply --actor-id N]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.accounting import AuditTrail
from app.models.user import User

AUDIT_ACTION = "SPONSOR_CORRECTED"


class CorrectionRefused(Exception):
    pass


def chain(db: Session, user_id: int, limit: int = 1000) -> List[int]:
    """The account followed by its sponsors until the root or the first repeat."""
    out, current = [user_id], db.get(User, user_id)
    while current is not None and current.sponsor_id is not None and len(out) < limit:
        nxt = int(current.sponsor_id)
        out.append(nxt)
        if nxt in out[:-1]:
            break
        current = db.get(User, nxt)
    return out


def on_cycle(db: Session, user_id: int) -> bool:
    path = chain(db, user_id)
    return len(path) > 1 and path[-1] == user_id


def correct(db: Session, account_id: int, expect_sponsor: int, *, evidence_ref: str,
            actor_id: Optional[int] = None, now: Optional[datetime] = None) -> dict:
    from app.scripts.reconcile_legacy_commissions import fallback_link

    now = now or datetime.utcnow()
    evidence_ref = " ".join((evidence_ref or "").split())
    if len(evidence_ref) < 6:
        raise CorrectionRefused("--evidence-ref (6+ characters) is required")
    user = db.query(User).filter(User.id == account_id).with_for_update().populate_existing().first()
    if user is None:
        raise CorrectionRefused(f"account {account_id} does not exist")
    if user.sponsor_id is None:
        return {"account_id": account_id, "status": "already_root", "chain": chain(db, account_id)}
    if int(user.sponsor_id) != int(expect_sponsor):
        raise CorrectionRefused(f"account {account_id} is sponsored by {user.sponsor_id}, not {expect_sponsor}: "
                                "nothing changed")
    before_chain = chain(db, account_id)
    if not on_cycle(db, account_id):
        raise CorrectionRefused(f"account {account_id} is not on a referral cycle ({before_chain}): nothing changed")
    fingerprint = fallback_link(db, account_id)
    old = {"sponsor_id": user.sponsor_id, "sponsor_source": user.sponsor_source,
           "sponsor_assigned_at": user.sponsor_assigned_at.isoformat() if user.sponsor_assigned_at else None,
           "chain": before_chain, "admin_fallback_fingerprint": fingerprint}
    user.sponsor_id = None
    db.flush()
    after_chain = chain(db, account_id)
    db.add(AuditTrail(table_name="users", record_id=account_id, action=AUDIT_ACTION, user_id=actor_id, timestamp=now,
                      old_values=old, new_values={"sponsor_id": None, "evidence_reference": evidence_ref,
                                                  "reason": "Removes the sponsor link that closed a referral cycle"}))
    db.flush()
    return {"account_id": account_id, "status": "corrected", "removed_sponsor": expect_sponsor,
            "admin_fallback_fingerprint": fingerprint, "chain_before": before_chain, "chain_after": after_chain,
            "cycle_remaining": on_cycle(db, account_id)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--account", type=int, required=True)
    parser.add_argument("--expect-sponsor", type=int, required=True)
    parser.add_argument("--evidence-ref", required=True)
    parser.add_argument("--actor-id", type=int, default=None, help="the approving administrator (required with --apply)")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    if args.apply and not args.actor_id:
        print("--apply needs --actor-id (the approving administrator)")
        return 2

    from app.db.session import SessionLocal
    from app.scripts.load_exposed_password_fingerprints import _database_label

    db = SessionLocal()
    try:
        try:
            result = correct(db, args.account, args.expect_sponsor, evidence_ref=args.evidence_ref,
                             actor_id=args.actor_id)
        except CorrectionRefused as exc:
            db.rollback()
            print(json.dumps({"database": _database_label(), "refused": str(exc), "changed": False}))
            return 2
        if args.apply:
            db.commit()
        else:
            db.rollback()
        print(json.dumps({"database": _database_label(), "mode": "APPLIED" if args.apply else "DRY RUN (rolled back)",
                          **result}, indent=2, default=str))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
