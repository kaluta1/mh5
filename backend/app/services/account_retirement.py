"""Retiring a member account so its email address and username can be registered again.

Nothing is deleted. The account row stays, so every record that points at it (audit trail, DSM
import mapping, sponsor, age and terms evidence, email history) keeps its meaning. What changes:

  * the email address and username are replaced by placeholders (the originals are kept in
    account_retirements), so both can be used by a new registration;
  * the account is deactivated and soft-deleted, its security version is raised (every session
    ends) and every unused one-time link is revoked: it cannot sign in or recover a password.

A later registration with the same address becomes the retired account's SUCCESSOR, linked
explicitly (account_retirements.successor_user_id) inside the registration transaction. That link
carries exactly one thing: the historical DSM classification (dsm_predecessor), so a member who was
excluded from the Referral Pool as a DSM member stays excluded. The successor inherits no sponsor,
wallet, KYC, commission or other state.

Refused for administrators and for any account holding money, KYC, Referral Pool units,
marketplace orders or listings, or members it sponsors: retiring those needs a separate decision.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import or_, text
from sqlalchemy.orm import Session

from app.models.account_retirement import AccountRetirement
from app.models.accounting import AuditTrail
from app.models.affiliate import AffiliateCashoutRequest, AffiliateCommission
from app.models.auth_security import TOKEN_PURPOSES
from app.models.business_model import MarketListing, MarketOrder, ReferralPoolUnit
from app.models.kyc import KYCVerification
from app.models.payment import Deposit
from app.models.user import User
from app.services import admin_security, auth_tokens
from app.services.auth_security import normalize_email

AUDIT_ACCOUNT_RETIRED = "ACCOUNT_RETIRED"
AUDIT_SUCCESSOR_LINKED = "ACCOUNT_SUCCESSOR_LINKED"
RETIRED_EMAIL_DOMAIN = "retired.myhigh5.com"


class RetirementRefused(Exception):
    pass


def placeholder_email(user_id: int) -> str:
    return f"retired-{int(user_id)}@{RETIRED_EMAIL_DOMAIN}"


def placeholder_username(user_id: int) -> str:
    return f"retired_{int(user_id)}"


def blockers(db: Session, user: User) -> dict:
    """Records that make retirement a separate decision (count > 0 blocks)."""
    uid = int(user.id)
    found = {
        "commissions": db.query(AffiliateCommission).filter(
            or_(AffiliateCommission.user_id == uid, AffiliateCommission.source_user_id == uid)).count(),
        "deposits": db.query(Deposit).filter(Deposit.user_id == uid).count(),
        "cashouts": db.query(AffiliateCashoutRequest).filter(AffiliateCashoutRequest.user_id == uid).count(),
        "kyc": db.query(KYCVerification).filter(KYCVerification.user_id == uid).count(),
        "pool_units": db.query(ReferralPoolUnit).filter(ReferralPoolUnit.user_id == uid).count(),
        "market_orders": db.query(MarketOrder).filter(
            or_(MarketOrder.buyer_user_id == uid, MarketOrder.seller_user_id == uid)).count(),
        "market_listings": db.query(MarketListing).filter(MarketListing.seller_user_id == uid).count(),
        "sponsored_members": db.query(User).filter(User.sponsor_id == uid).count(),
    }
    return {name: n for name, n in found.items() if n}


def retire(db: Session, user_id: int, email: str, *, reason: str, actor_id: Optional[int] = None,
           now: Optional[datetime] = None) -> AccountRetirement:
    """Retire the account that has BOTH this id and this address. No commit."""
    now = now or datetime.utcnow()
    user = db.query(User).filter(User.id == int(user_id)).with_for_update().one_or_none()
    if user is None or normalize_email(user.email) != normalize_email(email):
        raise RetirementRefused("the user id and the email address do not designate the same account")
    if db.query(AccountRetirement).filter(AccountRetirement.user_id == user.id).first() is not None:
        raise RetirementRefused("the account is already retired")
    if admin_security.is_administrator(user) or admin_security.role_is_privileged(user.role):
        raise RetirementRefused("an administrator account cannot be retired")
    blocking = blockers(db, user)
    if blocking:
        raise RetirementRefused(f"the account holds records that need a separate decision: {blocking}")

    row = AccountRetirement(user_id=user.id, original_email=user.email, original_email_norm=normalize_email(user.email),
                            original_username=user.username, reason=reason[:300], retired_by=actor_id, retired_at=now)
    db.add(row)
    user.email = placeholder_email(user.id)
    user.username = placeholder_username(user.id)
    user.is_active = False
    user.is_deleted = True
    user.security_version = int(user.security_version or 0) + 1      # every session ends
    revoked = sum(auth_tokens.revoke(db, user.id, purpose, now=now) for purpose in TOKEN_PURPOSES)
    db.add(AuditTrail(table_name="users", record_id=user.id, action=AUDIT_ACCOUNT_RETIRED,
                      old_values={"is_active": True, "is_deleted": False},
                      new_values={"is_active": False, "is_deleted": True, "links_revoked": revoked,
                                  "reason": reason[:300]},
                      user_id=actor_id, timestamp=now))
    db.flush()
    return row


def link_successor(db: Session, new_user: User, *, now: Optional[datetime] = None) -> Optional[AccountRetirement]:
    """Inside the registration transaction: a new account whose address belonged to a retired
    account becomes its successor (the most recent unclaimed retirement). No commit."""
    norm = normalize_email(new_user.email)
    row = (db.query(AccountRetirement)
           .filter(AccountRetirement.original_email_norm == norm, AccountRetirement.successor_user_id.is_(None))
           .order_by(AccountRetirement.retired_at.desc(), AccountRetirement.id.desc())
           .with_for_update().first())
    if row is None:
        return None
    now = now or datetime.utcnow()
    row.successor_user_id = new_user.id
    row.successor_linked_at = now
    db.add(AuditTrail(table_name="account_retirements", record_id=row.id, action=AUDIT_SUCCESSOR_LINKED,
                      old_values=None, new_values={"retired_user_id": row.user_id, "successor_user_id": new_user.id},
                      user_id=None, timestamp=now))
    return row


def dsm_predecessor(db: Session, user_id: int) -> bool:
    """Is this account the successor of a retired account that came from (or was matched by)
    the DSM member import? (PostgreSQL only: legacy_import.dsm_members exists only there.)"""
    if db.get_bind().dialect.name != "postgresql" or db.execute(
            text("SELECT to_regclass('legacy_import.dsm_members')")).scalar() is None:
        return False
    return db.execute(text(
        "SELECT 1 FROM account_retirements r JOIN legacy_import.dsm_members m ON m.mh5_user_id = r.user_id "
        "WHERE r.successor_user_id = :u LIMIT 1"), {"u": int(user_id)}).first() is not None
