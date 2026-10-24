"""Multi-Unit Referral Pool: second-account safeguards (P6).

Signals come only from data the platform already holds; nothing new about a person is
collected. A review stores a SHA-256 of the normalized signal and the ids of the accounts
involved, never the name, birth date, address, wallet or IP itself.

  DUPLICATE_KYC_IDENTITY  two accounts whose APPROVED verifications carry the same verified
                          first name, last name and date of birth. BLOCKING pending review: the
                          accounts can neither buy units, hold active units, nor receive a pool
                          sponsor until an administrator clears it.
  SHARED_PAYOUT_WALLET    the same payout wallet on several accounts. Recorded, never blocking.
  SHARED_LOGIN_IP         a login IP shared with another account. Recorded, never blocking.

The database itself refuses a blocking review for any signal but a duplicate identity: a
shared wallet, device or IP alone never bans anyone.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime
from typing import Iterable, List, Optional

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.models.business_model import ReferralPoolRiskReview
from app.models.user import User

logger = logging.getLogger(__name__)

DUPLICATE_IDENTITY, SHARED_WALLET, SHARED_IP = "DUPLICATE_KYC_IDENTITY", "SHARED_PAYOUT_WALLET", "SHARED_LOGIN_IP"
OPEN, CLEARED, CONFIRMED = "OPEN", "CLEARED", "CONFIRMED"
AUDIT_DECISION = "REFERRAL_POOL_RISK_REVIEW_DECIDED"
_MAX_RELATED = 50


class RiskError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _digest(*parts) -> str:
    return hashlib.sha256("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()


def is_blocked(db: Session, user_id: int) -> bool:
    """An open or confirmed duplicate-identity review stands against this account."""
    return db.query(ReferralPoolRiskReview.id).filter(
        ReferralPoolRiskReview.user_id == user_id, ReferralPoolRiskReview.blocking.is_(True),
        ReferralPoolRiskReview.status.in_((OPEN, CONFIRMED))).first() is not None


def _record(db: Session, user_ids: Iterable[int], signal: str, evidence: str, *, blocking: bool,
            now: datetime) -> List[int]:
    """One review per account involved (idempotent per account, signal and evidence). A review
    already decided is left as decided."""
    ids = sorted(set(int(u) for u in user_ids))
    created = []
    for uid in ids:
        related = ",".join(str(o) for o in ids if o != uid)[:2000]
        row = db.execute(text(
            "INSERT INTO referral_pool_risk_reviews (user_id, signal, evidence_hash, related_user_ids, blocking, status, "
            "created_at, updated_at) VALUES (:u, :s, :e, :r, :b, 'OPEN', :t, :t) "
            "ON CONFLICT (user_id, signal, evidence_hash) DO NOTHING RETURNING id"),
            {"u": uid, "s": signal, "e": evidence, "r": related, "b": blocking, "t": now}).scalar()
        if row is not None:
            created.append(row)
    if created:
        logger.warning("Referral Pool risk signal %s recorded for %s account(s)", signal, len(created))
    return created


# ---------------------------------------------------------------- scans

def scan_identity(db: Session, user_id: int, *, now: Optional[datetime] = None) -> List[int]:
    """Another account with the same APPROVED verified identity? Both get a blocking review."""
    from app.crud import crud_kyc
    from app.models.kyc import KYCStatus, KYCVerification

    now = now or datetime.utcnow()
    mine = crud_kyc.kyc_verification.get_by_user(db, user_id=user_id)
    if (mine is None or mine.status != KYCStatus.APPROVED or not mine.verified_first_name
            or not mine.verified_last_name or mine.verified_date_of_birth is None):
        return []
    first = mine.verified_first_name.strip().lower()
    last = mine.verified_last_name.strip().lower()
    born = mine.verified_date_of_birth.date()
    others = [u for (u,) in db.query(KYCVerification.user_id).filter(
        KYCVerification.status == KYCStatus.APPROVED, KYCVerification.user_id != user_id,
        func.lower(func.trim(KYCVerification.verified_first_name)) == first,
        func.lower(func.trim(KYCVerification.verified_last_name)) == last,
        func.date(KYCVerification.verified_date_of_birth) == born).distinct().limit(_MAX_RELATED)]
    if not others:
        return []
    return _record(db, [user_id, *others], DUPLICATE_IDENTITY, _digest("identity", first, last, born),
                   blocking=True, now=now)


def scan_wallets(db: Session, user_id: int, *, now: Optional[datetime] = None) -> List[int]:
    """The account's payout wallet(s) on other accounts: recorded for review, not blocking."""
    from app.models.affiliate import PayoutWalletApproval

    now = now or datetime.utcnow()
    own = {a.strip().lower() for (a,) in db.query(PayoutWalletApproval.address).filter(
        PayoutWalletApproval.user_id == user_id, PayoutWalletApproval.status.in_(("PENDING", "APPROVED")))
        if a and a.strip()}
    profile = db.query(User.usdt_wallet_address).filter(User.id == user_id).scalar()
    if profile and profile.strip():
        own.add(profile.strip().lower())
    created = []
    for address in sorted(own):
        others = {u for (u,) in db.query(PayoutWalletApproval.user_id).filter(
            func.lower(func.trim(PayoutWalletApproval.address)) == address, PayoutWalletApproval.user_id != user_id,
            PayoutWalletApproval.status.in_(("PENDING", "APPROVED"))).limit(_MAX_RELATED)}
        others |= {u for (u,) in db.query(User.id).filter(
            func.lower(func.trim(User.usdt_wallet_address)) == address, User.id != user_id).limit(_MAX_RELATED)}
        if others:
            created += _record(db, [user_id, *others], SHARED_WALLET, _digest("wallet", address), blocking=False, now=now)
    return created


def scan_login_ips(db: Session, user_id: int, *, now: Optional[datetime] = None) -> List[int]:
    """Login IPs (already logged) shared with other accounts: recorded, never blocking."""
    from app.models.login_log import LoginLog

    now = now or datetime.utcnow()
    ips = {ip for (ip,) in db.query(LoginLog.ip_address).filter(LoginLog.user_id == user_id,
                                                               LoginLog.ip_address.isnot(None)).distinct()}
    created = []
    for ip in sorted(ips):
        others = {u for (u,) in db.query(LoginLog.user_id).filter(LoginLog.ip_address == ip,
                                                                 LoginLog.user_id != user_id)
                  .distinct().limit(_MAX_RELATED)}
        if others:
            created += _record(db, [user_id, *others], SHARED_IP, _digest("ip", ip), blocking=False, now=now)
    return created


def scan_member(db: Session, user_id: int, *, now: Optional[datetime] = None) -> List[int]:
    return scan_identity(db, user_id, now=now) + scan_wallets(db, user_id, now=now) + scan_login_ips(db, user_id, now=now)


# ---------------------------------------------------------------- manual review

def decide(db: Session, actor, review_id: int, decision: str, *, note: str, password: Optional[str],
           ip: Optional[str] = None, now: Optional[datetime] = None) -> ReferralPoolRiskReview:
    """An administrator (manage_kyc_settings + password) clears or confirms a review. Clearing
    the last blocking review lets the member take part again (a RISK_CLEARED pool event re-checks
    their units and queue entry). Commits."""
    from app.models.accounting import AuditTrail
    from app.services import admin_security, payment_config
    from app.services import referral_pool_integration as integration

    now = now or datetime.utcnow()
    if decision not in (CLEARED, CONFIRMED):
        raise RiskError("INVALID_DECISION", "Decide CLEARED or CONFIRMED.")
    if not payment_config.has_permission(actor, admin_security.PERMISSION_MANAGE_KYC):
        raise RiskError("FORBIDDEN", f"The {admin_security.PERMISSION_MANAGE_KYC} permission is required.")
    try:
        payment_config.require_reauth(actor, password)
    except payment_config.PaymentConfigError as exc:
        raise RiskError(exc.code, str(exc)) from None
    note = str(note or "").strip()
    if len(note) < 5:
        raise RiskError("NOTE_REQUIRED", "Explain the decision (at least 5 characters).")
    review = (db.query(ReferralPoolRiskReview).filter(ReferralPoolRiskReview.id == review_id)
              .with_for_update().populate_existing().first())
    if review is None:
        raise RiskError("NOT_FOUND", "Review not found.")
    if review.status == decision:
        db.rollback()
        return review
    old = review.status
    review.status, review.decided_by, review.decided_at, review.decision_note = (
        decision, getattr(actor, "id", None), now, note[:500])
    db.add(AuditTrail(table_name="referral_pool_risk_reviews", record_id=review.id, action=AUDIT_DECISION,
                      user_id=getattr(actor, "id", None), ip_address=(ip or None),
                      old_values={"status": old}, new_values={"status": decision, "signal": review.signal}))
    db.flush()
    if decision == CLEARED and review.blocking and not is_blocked(db, review.user_id):
        integration.record_event(db, user_id=review.user_id, event_type="RISK_CLEARED",
                                 dedupe_key=f"RISK_CLEARED:{review.id}:{now.isoformat()}", now=now)
    db.commit()
    return review
