"""DSM membership reconciliation and sponsor restoration (Prompt 6).

Source of evidence: legacy_import.dsm_members, written once by the authorised DSM import of 2026-10-26 (one row
per DSM member: the DSM id, the MyHigh5 account it was matched to or created as - by exact normalised e-mail
only -, the DSM sponsor and the MyHigh5 account that sponsor resolved to). Names are never used to match.
The table exists only where the import ran (production); elsewhere every function reports SOURCE_MISSING.

Classification of every DSM row (read-only):
  VERIFIED_EXISTING_RELATIONSHIP  the member's current sponsor is the DSM sponsor's account
  VERIFIED_MATCH                  matched/created account, the DSM record had no sponsor
  SAFE_RESTORATION_CANDIDATE      the member has NO sponsor now, the DSM sponsor resolved to an active account,
                                  linking it would create no cycle and is not self
  CONFLICTING_SPONSOR             the member has another sponsor now (it is never replaced)
  AMBIGUOUS_MATCH                 the import could not match the e-mail to exactly one account
  INACTIVE_MEMBERSHIP             the account is deleted, inactive or retired
  MISSING_SOURCE_EVIDENCE         the DSM sponsor is absent from the export or never resolved
  REQUIRES_MANUAL_REVIEW          anything else (e.g. the sponsor's account is unavailable or a cycle)

Restoration (write, administrator-approved, one member at a time): re-checks the candidate inside the
transaction (row locks), writes users.sponsor_id only WHERE it is still NULL, sponsor_source 'DSM_RESTORE'
(never counted for the 40% qualification, which counts PERSONAL_REFERRAL/JOIN_CODE only), keeps a
dsm_sponsor_restorations row and an audit record. No commission, missed earning or any other financial record
is created or recalculated: future events only follow the restored sponsor.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

CLASSES = ("VERIFIED_EXISTING_RELATIONSHIP", "VERIFIED_MATCH", "SAFE_RESTORATION_CANDIDATE", "CONFLICTING_SPONSOR",
           "AMBIGUOUS_MATCH", "INACTIVE_MEMBERSHIP", "MISSING_SOURCE_EVIDENCE", "REQUIRES_MANUAL_REVIEW")
RESTORE_SOURCE = "DSM_RESTORE"


class DsmError(Exception):
    def __init__(self, code: str, message: str, status: int = 409):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def source_available(db: Session) -> bool:
    if db.get_bind().dialect.name != "postgresql":
        return False
    return db.execute(text("SELECT to_regclass('legacy_import.dsm_members')")).scalar() is not None


_ROWS_SQL = """
SELECT m.dsm_id, m.import_status, m.sponsor_status, m.mh5_user_id, m.dsm_sponsor_dsm_id,
       m.resolved_sponsor_mh5_id, m.dsm_joined_at,
       u.sponsor_id AS current_sponsor, u.is_active AS active, u.is_deleted AS deleted,
       (SELECT 1 FROM account_retirements r WHERE r.user_id = m.mh5_user_id LIMIT 1) IS NOT NULL AS retired,
       s.is_active AS sponsor_active, s.is_deleted AS sponsor_deleted
FROM legacy_import.dsm_members m
LEFT JOIN users u ON u.id = m.mh5_user_id
LEFT JOIN users s ON s.id = m.resolved_sponsor_mh5_id
ORDER BY m.dsm_id
"""


def _parents(db: Session) -> dict:
    return {int(i): (int(s) if s is not None else None)
            for i, s in db.execute(text("SELECT id, sponsor_id FROM users WHERE sponsor_id IS NOT NULL"))}


def _creates_cycle(parents: dict, user_id: int, sponsor_id: int) -> bool:
    seen, cur = set(), sponsor_id
    for _ in range(10000):
        if cur is None:
            return False
        if cur == user_id:
            return True
        if cur in seen:
            return True
        seen.add(cur)
        cur = parents.get(cur)
    return True


def classify_row(r, parents: dict) -> tuple:
    """(class, reason) for one DSM row (mapping-like)."""
    status = r["import_status"]
    if status not in ("CREATED", "MATCHED_EXISTING") or r["mh5_user_id"] is None:
        if str(status).startswith("REVIEW"):
            return "AMBIGUOUS_MATCH", status
        return "MISSING_SOURCE_EVIDENCE", status
    if r["deleted"] or r["active"] is False or r["retired"]:
        return "INACTIVE_MEMBERSHIP", "account deleted, inactive or retired"
    target = r["resolved_sponsor_mh5_id"]
    current = r["current_sponsor"]
    if r["dsm_sponsor_dsm_id"] is None:
        if str(r["sponsor_status"] or "") == "SPONSOR_NOT_IN_SOURCE":
            return "MISSING_SOURCE_EVIDENCE", "DSM sponsor not in the export"
        return "VERIFIED_MATCH", "no DSM sponsor"
    if target is None:
        return "MISSING_SOURCE_EVIDENCE", f"DSM sponsor not resolved ({r['sponsor_status']})"
    if current is not None and int(current) == int(target):
        return "VERIFIED_EXISTING_RELATIONSHIP", "current sponsor equals the DSM sponsor"
    if current is not None:
        return "CONFLICTING_SPONSOR", "another sponsor now (kept)"
    if r["sponsor_deleted"] or r["sponsor_active"] is False:
        return "REQUIRES_MANUAL_REVIEW", "DSM sponsor's account unavailable"
    if int(target) == int(r["mh5_user_id"]) or _creates_cycle(parents, int(r["mh5_user_id"]), int(target)):
        return "REQUIRES_MANUAL_REVIEW", "self or cycle"
    return "SAFE_RESTORATION_CANDIDATE", "no sponsor now; DSM sponsor resolved and active"


def report(db: Session, *, sample: int = 50) -> dict:
    """Counts per class, samples per class (ids only, no personal data), restorations applied."""
    if not source_available(db):
        return {"read_only": True, "source": "SOURCE_MISSING", "counts": {}, "samples": {}}
    parents = _parents(db)
    counts = {c: 0 for c in CLASSES}
    samples: dict = {c: [] for c in CLASSES}
    pool = {"dsm_accounts": 0, "kyc_approved": 0}
    approved = {int(u) for (u,) in db.execute(text(
        "SELECT user_id FROM kyc_verifications WHERE lower(status::text) = 'approved'"))}
    for r in db.execute(text(_ROWS_SQL)).mappings():
        cls, reason = classify_row(r, parents)
        counts[cls] += 1
        if len(samples[cls]) < sample:
            samples[cls].append({"dsm_id": r["dsm_id"], "user_id": r["mh5_user_id"], "current_sponsor_id": r["current_sponsor"],
                                 "dsm_sponsor_user_id": r["resolved_sponsor_mh5_id"], "reason": reason})
        if r["mh5_user_id"] is not None:
            pool["dsm_accounts"] += 1
            pool["kyc_approved"] += int(int(r["mh5_user_id"]) in approved)
    restorations = db.execute(text("SELECT status, count(*) FROM dsm_sponsor_restorations GROUP BY status")).all() \
        if db.execute(text("SELECT to_regclass('public.dsm_sponsor_restorations')")).scalar() else []
    return {"read_only": True, "source": "legacy_import.dsm_members", "counts": counts, "samples": samples,
            "referral_pool_eligibility": {**pool, "note": "DSM membership alone never makes a member eligible: "
                                          "approved MyHigh5 KYC is required; no unit is granted from DSM history."},
            "restorations": {str(k): int(v) for k, v in restorations}}


def candidates(db: Session, *, limit: int = 200) -> list:
    if not source_available(db):
        return []
    parents = _parents(db)
    out = []
    for r in db.execute(text(_ROWS_SQL)).mappings():
        cls, reason = classify_row(r, parents)
        if cls == "SAFE_RESTORATION_CANDIDATE":
            out.append({"dsm_id": r["dsm_id"], "user_id": r["mh5_user_id"], "dsm_sponsor_user_id": r["resolved_sponsor_mh5_id"],
                        "dsm_joined_at": str(r["dsm_joined_at"]) if r["dsm_joined_at"] else None, "reason": reason})
            if len(out) >= limit:
                break
    return out


def restore(db: Session, actor, *, user_id: int, note: str, now: Optional[datetime] = None) -> dict:
    """Apply ONE approved restoration (caller checks the permission and password, and commits)."""
    from app.models.accounting import AuditTrail
    from app.models.dsm_restoration import DsmSponsorRestoration
    from app.models.user import User

    if not source_available(db):
        raise DsmError("SOURCE_MISSING", "The DSM import record is not available here.", 404)
    if len((note or "").strip()) < 5:
        raise DsmError("NOTE_REQUIRED", "Give the evidence or reason for the restoration.", 400)
    if db.query(DsmSponsorRestoration.id).filter(DsmSponsorRestoration.user_id == user_id).first():
        raise DsmError("ALREADY_DECIDED", "A restoration was already recorded for this member.")
    user = db.query(User).filter(User.id == user_id).with_for_update().first()
    if user is None:
        raise DsmError("NOT_FOUND", "Member not found.", 404)
    row = db.execute(text(_ROWS_SQL.replace("ORDER BY m.dsm_id", "WHERE m.mh5_user_id = :u ORDER BY m.dsm_id")),
                     {"u": user_id}).mappings().all()
    if len(row) != 1:
        raise DsmError("AMBIGUOUS_SOURCE", "The member does not map to exactly one DSM record.")
    r = row[0]
    sponsor = db.query(User).filter(User.id == r["resolved_sponsor_mh5_id"]).with_for_update().first() \
        if r["resolved_sponsor_mh5_id"] else None
    cls, reason = classify_row(r, _parents(db))
    if cls != "SAFE_RESTORATION_CANDIDATE" or sponsor is None:
        raise DsmError("NOT_A_CANDIDATE", f"Not a safe restoration candidate now: {cls} ({reason}).")
    now = now or datetime.utcnow()
    changed = db.execute(text("UPDATE users SET sponsor_id = :s, sponsor_source = :src, sponsor_assigned_at = :ts "
                              "WHERE id = :u AND sponsor_id IS NULL AND id <> :s"),
                         {"s": sponsor.id, "src": RESTORE_SOURCE, "ts": now, "u": user.id}).rowcount
    if changed != 1:
        raise DsmError("CHANGED", "The member's sponsor changed meanwhile; nothing was written.")
    evidence = {"dsm_id": r["dsm_id"], "import_status": r["import_status"], "sponsor_status": r["sponsor_status"],
                "dsm_sponsor_dsm_id": r["dsm_sponsor_dsm_id"], "resolved_sponsor_mh5_id": sponsor.id,
                "source": "legacy_import.dsm_members (DSM export 2026-10-20)"}
    db.add(DsmSponsorRestoration(user_id=user.id, dsm_id=int(r["dsm_id"]), previous_sponsor_id=None,
                                 restored_sponsor_id=sponsor.id, status="APPLIED", evidence=evidence,
                                 note=note.strip()[:300], approved_by_user_id=actor.id, applied_at=now))
    db.add(AuditTrail(table_name="users", record_id=user.id, action="DSM_SPONSOR_RESTORED",
                      old_values={"sponsor_id": None}, new_values={"sponsor_id": sponsor.id, "source": RESTORE_SOURCE,
                                                                   **evidence, "note": note.strip()[:300]},
                      user_id=actor.id))
    db.flush()
    return {"user_id": user.id, "sponsor_id": sponsor.id, "dsm_id": r["dsm_id"], "status": "APPLIED"}
