"""Member emails of the individual automatic USDT payouts (owner rule 2026-10-18).

  AFFILIATE.COMMISSION_EARNED   commission earned, no approved payout wallet yet
  PAYOUT.WALLET_SUBMITTED       wallet submitted for administrator approval
  PAYOUT.WALLET_APPROVED        wallet approved
  PAYOUT.WALLET_REJECTED        wallet rejected (with the reason)
  PAYOUT.COMPLETED              payout finished at the provider (only then)
  PAYOUT.FAILED                 payout failed (not paid) or delayed (outcome open)

Every email goes through the email outbox (queued, retried, idempotent by key)
and is queued only AFTER the financial change it describes is committed. Every
function here never raises: an email never changes money.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.models.affiliate import AffiliateCashoutRequest, AffiliateCommission, CommissionStatus
from app.models.user import User

logger = logging.getLogger(__name__)

# Commissions older than this when the sweep first sees them are not announced
# (e.g. rows that existed before this feature).
NOTICE_WINDOW = timedelta(days=30)
WALLET_PATH = "/dashboard/wallet"


def _enqueue(db: Session, event, user: Optional[User], key: str, context: dict) -> bool:
    if user is None or not user.email or not user.is_active:
        return False
    try:
        from app.services.email import email_service

        delivery = email_service.enqueue(db, event=event, recipient=user.email, idempotency_key=key,
                                         user_id=user.id, context=context)
        return delivery is not None
    except Exception:  # noqa: BLE001
        logger.exception("Payout email %s could not be queued", key)
        db.rollback()
        return False


def _money(value) -> str:
    return f"{float(value or 0):.2f}"


def wallet_submitted(db: Session, user: User, approval_id: int) -> bool:
    from app.models.affiliate import PayoutWalletApproval
    from app.services.cashout_service import mask_address, network_label
    from app.services.email_events import EmailEvent

    row = db.query(PayoutWalletApproval).filter(PayoutWalletApproval.id == approval_id).first()
    if row is None:
        return False
    return _enqueue(db, EmailEvent.PAYOUT_WALLET_SUBMITTED, user, f"payout-wallet-submitted:{row.id}",
                    {"wallet": mask_address(row.address), "network": network_label(row.currency)})


def wallet_decided(db: Session, approval_id: int) -> bool:
    from app.models.affiliate import PayoutWalletApproval
    from app.services import payout_wallet_approval as approvals
    from app.services.cashout_service import mask_address, network_label
    from app.services.email_events import EmailEvent

    row = db.query(PayoutWalletApproval).filter(PayoutWalletApproval.id == approval_id).first()
    if row is None or row.status not in (approvals.APPROVED, approvals.REJECTED):
        return False
    user = db.query(User).filter(User.id == row.user_id).first()
    approved = row.status == approvals.APPROVED
    return _enqueue(db, EmailEvent.PAYOUT_WALLET_APPROVED if approved else EmailEvent.PAYOUT_WALLET_REJECTED,
                    user, f"payout-wallet-{'approved' if approved else 'rejected'}:{row.id}",
                    {"wallet": mask_address(row.address), "network": network_label(row.currency),
                     "reason": None if approved else (row.decision_note or "")})


def payout_outcome(db: Session, cashout_id: int, kind: str) -> bool:
    """kind: COMPLETED (paid, after the provider reported it finished), FAILED
    (confirmed not paid; the commission is available again) or DELAYED (outcome
    not final yet; nothing is retried until it is known)."""
    from app.services import payment_config
    from app.services.email_events import EmailEvent

    cashout = db.query(AffiliateCashoutRequest).filter(AffiliateCashoutRequest.id == cashout_id).first()
    if cashout is None:
        return False
    if kind == "COMPLETED" and cashout.status != "completed":
        return False                                # never announce a payment that is not settled
    user = db.query(User).filter(User.id == cashout.user_id).first()
    asset = payment_config.SUPPORTED_PAYOUT_CURRENCIES.get(str(cashout.payout_currency or ""), {})
    explorer = (asset.get("explorer_tx") + cashout.tx_hash) if (cashout.tx_hash and asset.get("explorer_tx")) else None
    context = {"kind": kind, "amount": _money(cashout.gross_amount),
               "received": (f"{cashout.net_received:.6f}".rstrip("0").rstrip(".")
                            if cashout.net_received is not None else None),
               "commission_id": cashout.commission_id, "tx_hash": cashout.tx_hash, "explorer_url": explorer}
    event = EmailEvent.PAYOUT_COMPLETED if kind == "COMPLETED" else EmailEvent.PAYOUT_FAILED
    return _enqueue(db, event, user, f"payout-{kind.lower()}:{cashout.id}", context)


def sweep(db: Session, *, now: Optional[datetime] = None, limit: int = 500) -> int:
    """Email members who earned commissions that wait for an approved payout wallet.
    Each commission is announced once (affiliate_commissions.wallet_notice_at); all
    of a member's new ones go in one email. Members whose wallet is waiting for
    approval or already approved get nothing here (their dashboard shows it).
    Returns the number of emails queued."""
    from app.services import cashout_service as cs
    from app.services.commission_payout_hold import payable_clause
    from app.services.email_events import EmailEvent

    now = now or datetime.utcnow()
    rows = (db.query(AffiliateCommission)
            .filter(AffiliateCommission.business_model_version == "NEW_V2",
                    AffiliateCommission.status.in_((CommissionStatus.APPROVED, CommissionStatus.PENDING)),
                    AffiliateCommission.payout_reference.is_(None),
                    AffiliateCommission.wallet_notice_at.is_(None),
                    AffiliateCommission.transaction_date >= now - NOTICE_WINDOW,
                    payable_clause())
            .order_by(AffiliateCommission.id.asc()).limit(limit).all())
    by_user = defaultdict(list)
    for row in rows:
        by_user[int(row.user_id)].append(row)
    db.rollback()
    queued = 0
    for user_id, commissions in by_user.items():
        user = db.query(User).filter(User.id == user_id).first()
        if user is None:
            continue
        state = cs.wallet_state(user, now)
        if state.status in (cs.WALLET_PENDING_APPROVAL, cs.WALLET_ON_HOLD, cs.WALLET_VERIFIED):
            db.rollback()
            continue                                # a wallet is on its way: no "set up a wallet" email
        from app.core.public_urls import public_site_base

        total = sum(float(c.commission_amount or 0) for c in commissions)
        ids = [int(c.id) for c in commissions]
        context = {"count": len(ids), "total": f"{total:.2f}", "rejected": state.status == cs.WALLET_REJECTED,
                   "wallet_url": f"{public_site_base()}{WALLET_PATH}"}
        db.rollback()
        if not _enqueue(db, EmailEvent.AFFILIATE_COMMISSION_EARNED, user,
                        f"commission-wallet-missing:{user_id}:{ids[0]}", context):
            continue
        (db.query(AffiliateCommission).filter(AffiliateCommission.id.in_(ids),
                                              AffiliateCommission.wallet_notice_at.is_(None))
         .update({AffiliateCommission.wallet_notice_at: now}, synchronize_session=False))
        db.commit()
        queued += 1
    return queued
