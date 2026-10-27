#!/usr/bin/env python3
"""Place pre-existing members WITHOUT a sponsor under the first qualified Referral Pool member.

Owner rule (Shafi Abeid, 2026-10-26): members who joined before the new assignment system and have
no sponsor go under ``mlenzi123``; anyone who already has a sponsor keeps it. One run, one time.

Who is changed (all of it, checked again row by row under a lock at write time):
  * ``users.sponsor_id IS NULL``, registered before ``--registered-before``;
  * active, not deleted, a plain member (no admin flag, role 'user' or none);
  * not the founder, and not in the founder's own sponsor chain (no cycle);
  * not touched by the DSM import in any way: no legacy_import.dsm_members row for the account and no
    DSM row whose e-mail matches it case-insensitively (the unresolved identities stay as they are).

Every change sets sponsor_id = founder, sponsor_source FOUNDER_ASSIGNED, sponsor_assigned_at = now,
through an UPDATE that only matches while the sponsor is still NULL, and writes one audit_trails row
SPONSOR_ASSIGNED_FOUNDER with the previous values, the new sponsor, the reason, the run and the
approving administrator. No commission, ledger, KYC or pool row is written.

The founder must be active and hold at least one eligible ACTIVE unit (the pool's own rule), or
nothing is changed.

DRY RUN BY DEFAULT: a read-only transaction that writes nothing and lists every eligible and excluded
account with its reason (founder, upline, inactive, staff, DSM, after cut-off, risk review, ambiguous e-mail,
likely test account, already waiting for a pool sponsor). --apply needs --actor-id and --expect-count (the dry run's count). --only-ids limits
the change to accounts the owner reviewed (test, probe and doubtful accounts are left out by not listing them).

    python -m app.scripts.assign_founder_sponsor --founder mlenzi123 --registered-before 2026-10-26T12:00:00
        [--only-ids 1,2] [--apply --actor-id N --expect-count N --run-id ID]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from typing import List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.accounting import AuditTrail
from app.models.business_model import ReferralPoolUnit
from app.models.user import User

SOURCE = "FOUNDER_ASSIGNED"
AUDIT_ACTION = "SPONSOR_ASSIGNED_FOUNDER"
REASON = ("Owner rule 2026-10-26: a member who joined before the new assignment system without a "
          "sponsor is placed under the first qualified Referral Pool member")


class Refused(Exception):
    pass


def founder_check(db: Session, username: str) -> User:
    from app.services import referral_pool_units as units

    founder = db.query(User).filter(User.username == username).first()
    if founder is None:
        raise Refused(f"no account with username {username!r}")
    if not founder.is_active or founder.is_deleted:
        raise Refused(f"{username} is not an active account")
    if not units.member_eligibility(db, founder).eligible:
        raise Refused(f"{username} is not an eligible pool holder: {units.member_eligibility(db, founder).reason}")
    active = db.query(ReferralPoolUnit).filter(ReferralPoolUnit.user_id == founder.id,
                                               ReferralPoolUnit.status == units.ACTIVE).count()
    if active < 1:
        raise Refused(f"{username} holds no ACTIVE Referral Pool unit")
    return founder


def upline(db: Session, user_id: int) -> List[int]:
    rows = db.execute(text(
        "WITH RECURSIVE u(id, sponsor_id) AS (SELECT id, sponsor_id FROM users WHERE id = :u "
        "UNION SELECT x.id, x.sponsor_id FROM users x JOIN u ON x.id = u.sponsor_id) SELECT id FROM u"),
        {"u": user_id})
    return [r[0] for r in rows]


def _dsm_table(db: Session) -> bool:
    return db.execute(text("SELECT to_regclass('legacy_import.dsm_members')")).scalar() is not None


def _table(db: Session, name: str) -> bool:
    return db.execute(text("SELECT to_regclass(:n)"), {"n": name}).scalar() is not None


# Accounts that look like tests or throwaways (username or e-mail): never assigned automatically.
# PostgreSQL regex, case-insensitive (~*).
TEST_ACCOUNT_RE = (r"(^|[._+-])(test|tests|testing|probe|demo|dummy|fake|qa)([0-9._+-]|@|$)"
                   r"|@(example\.(com|org|net)|mailinator\.com|yopmail\.com|guerrillamail\.com|tempmail\.[a-z]+)$"
                   r"|\.(test|invalid|example|localhost)$")

# Order matters: the FIRST reason that applies is the one reported.
OUTCOMES = ("FOUNDER", "FOUNDER_UPLINE", "INACTIVE_OR_DELETED", "STAFF_ACCOUNT", "DSM_IMPORT_OR_UNRESOLVED",
            "REGISTERED_AFTER_CUTOFF", "RISK_REVIEW", "AMBIGUOUS_EMAIL", "LIKELY_TEST", "POOL_WAITING", "ASSIGNED")


def classify(db: Session, founder: User, registered_before: datetime) -> List[tuple]:
    """(id, username, created_at, outcome) for every member WITHOUT a sponsor, by the first rule that
    excludes them ('ASSIGNED' when none does). Read-only."""
    dsm = ("WHEN EXISTS (SELECT 1 FROM legacy_import.dsm_members m WHERE m.mh5_user_id = u.id "
           "OR m.email_norm = lower(trim(u.email))) THEN 'DSM_IMPORT_OR_UNRESOLVED' ") if _dsm_table(db) else ""
    risk = ("WHEN EXISTS (SELECT 1 FROM referral_pool_risk_reviews v WHERE v.user_id = u.id AND v.blocking "
            "AND v.status IN ('OPEN','CONFIRMED')) THEN 'RISK_REVIEW' ") if _table(db, "referral_pool_risk_reviews") else ""
    pending = ("WHEN EXISTS (SELECT 1 FROM referral_pool_pending p WHERE p.referred_user_id = u.id "
               "AND p.status = 'WAITING') THEN 'POOL_WAITING' ") if _table(db, "referral_pool_pending") else ""
    q = ("SELECT u.id, u.username, u.created_at, CASE WHEN u.id = :f THEN 'FOUNDER' "
         "WHEN u.id = ANY(:up) THEN 'FOUNDER_UPLINE' "
         "WHEN NOT u.is_active OR coalesce(u.is_deleted, false) THEN 'INACTIVE_OR_DELETED' "
         "WHEN u.is_admin OR (u.role_id IS NOT NULL AND coalesce(r.name, '') <> 'user') THEN 'STAFF_ACCOUNT' "
         + dsm +
         "WHEN u.created_at >= :before THEN 'REGISTERED_AFTER_CUTOFF' "
         + risk +
         "WHEN EXISTS (SELECT 1 FROM users o WHERE o.id <> u.id AND lower(trim(o.email)) = lower(trim(u.email))) "
         "THEN 'AMBIGUOUS_EMAIL' "
         "WHEN coalesce(u.username, '') ~* :testre OR coalesce(u.email, '') ~* :testre THEN 'LIKELY_TEST' "
         + pending +
         "ELSE 'ASSIGNED' END AS k "
         "FROM users u LEFT JOIN roles r ON r.id = u.role_id WHERE u.sponsor_id IS NULL ORDER BY u.id")
    return [tuple(r) for r in db.execute(text(q), {"f": founder.id, "up": upline(db, founder.id),
                                                   "before": registered_before, "testre": TEST_ACCOUNT_RE})]


def candidates(db: Session, founder: User, registered_before: datetime) -> List[int]:
    return [r[0] for r in classify(db, founder, registered_before) if r[3] == "ASSIGNED"]


def excluded_summary(db: Session, founder: User, registered_before: datetime) -> dict:
    """What stays without a sponsor, and why (counts only): for the report."""
    counts: dict = {}
    for _id, _name, _at, k in classify(db, founder, registered_before):
        counts[k] = counts.get(k, 0) + 1
    return counts


def run(db: Session, username: str, registered_before: datetime, *, run_id: str, actor_id: Optional[int] = None,
        now: Optional[datetime] = None, only_ids: Optional[List[int]] = None, apply: bool = True) -> dict:
    """apply=False is the dry run: it reads only (no lock, no UPDATE, no audit row) and reports what
    WOULD change. apply=True writes; the caller commits."""
    now = now or datetime.utcnow()
    founder = founder_check(db, username)
    rows = classify(db, founder, registered_before)
    summary: dict = {}
    for _id, _name, _at, k in rows:
        summary[k] = summary.get(k, 0) + 1
    ids = [r[0] for r in rows if r[3] == "ASSIGNED"]
    eligible = list(ids)
    detail = [{"id": i, "username": n, "registered": at.date().isoformat() if at else None}
              for i, n, at, k in rows if k == "ASSIGNED"]
    excluded = {k: [i for i, _n, _a, kk in rows if kk == k] for k in OUTCOMES if k != "ASSIGNED"}
    if only_ids is not None:                                 # the owner-reviewed accounts only (every rule still applies)
        ids = [i for i in ids if i in set(only_ids)]
    changed, skipped = [], []
    founder_chain = set(upline(db, founder.id))              # the founder included
    for user_id in ids:
        if not apply:
            changed.append(user_id)
            continue
        user = db.query(User).filter(User.id == user_id).with_for_update().populate_existing().one()
        if user.sponsor_id is not None or user.id in founder_chain:
            skipped.append(user_id)
            continue
        old = {"sponsor_id": None, "sponsor_source": user.sponsor_source,
               "sponsor_assigned_at": user.sponsor_assigned_at.isoformat() if user.sponsor_assigned_at else None}
        n = db.execute(text("UPDATE users SET sponsor_id = :s, sponsor_source = :src, sponsor_assigned_at = :t "
                            "WHERE id = :u AND sponsor_id IS NULL"),
                       {"s": founder.id, "src": SOURCE, "t": now, "u": user_id}).rowcount
        if n != 1:
            skipped.append(user_id)
            continue
        db.add(AuditTrail(table_name="users", record_id=user_id, action=AUDIT_ACTION, user_id=actor_id, timestamp=now,
                          old_values=old, new_values={"sponsor_id": founder.id, "sponsor_source": SOURCE,
                                                      "sponsor_assigned_at": now.isoformat(), "reason": REASON,
                                                      "run_id": run_id}))
        changed.append(user_id)
    if apply:
        db.flush()
    return {"founder": {"id": founder.id, "username": founder.username}, "registered_before": registered_before,
            "run_id": run_id, "applied": apply, "sponsorless_by_outcome": summary, "eligible_by_rules": eligible,
            "eligible_detail": detail, "excluded_ids": {k: v for k, v in excluded.items() if v},
            "not_selected": [i for i in eligible if i not in ids], "assigned": len(changed), "assigned_ids": changed,
            "skipped_at_write": skipped}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--founder", required=True)
    parser.add_argument("--registered-before", required=True, type=datetime.fromisoformat)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--actor-id", type=int, default=None)
    parser.add_argument("--expect-count", type=int, default=None)
    parser.add_argument("--only-ids", default=None, help="comma-separated account ids reviewed by the owner")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    if args.apply and (not args.actor_id or args.expect_count is None):
        print("--apply needs --actor-id and --expect-count")
        return 2
    run_id = args.run_id or f"FOUNDER-SPONSOR-{datetime.utcnow():%Y%m%dT%H%M%SZ}"

    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        try:
            only = [int(x) for x in args.only_ids.split(",")] if args.only_ids else None
            if not args.apply:                               # the dry run cannot write, even by mistake
                db.execute(text("SET TRANSACTION READ ONLY"))
            result = run(db, args.founder, args.registered_before, run_id=run_id, actor_id=args.actor_id,
                         only_ids=only, apply=args.apply)
        except Refused as exc:
            db.rollback()
            print(json.dumps({"refused": str(exc), "changed": False}))
            return 2
        if args.apply and result["assigned"] != args.expect_count:
            db.rollback()
            print(json.dumps({"refused": f"{result['assigned']} would change, expected {args.expect_count}",
                              "changed": False}))
            return 2
        db.commit() if args.apply else db.rollback()
        print(json.dumps({"mode": "APPLIED" if args.apply else "DRY RUN (rolled back)", **result}, indent=1,
                         default=str))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
