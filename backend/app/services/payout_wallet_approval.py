"""Administrator approval of member payout wallets (owner rule 2026-10-18).

Every wallet a member sets, and every later change of address, is submitted
for approval (cashout_service._apply_wallet calls submit). Nothing is paid to a
wallet until an authorised administrator approved exactly that address on that
network:

  PENDING     submitted, waiting for a decision        -> never paid
  APPROVED    an administrator approved it              -> may be paid
  REJECTED    an administrator rejected it              -> never paid
  SUPERSEDED  the member submitted another wallet since -> history only

A decision needs the process_cashouts permission (or a Super Admin), the
administrator's current password, and is never taken on one's own wallet (the
database refuses it as well). It is taken once, on the wallet that is still the
member's current one, and is audited. A payout records the approval it was
bound to (affiliate_cashout_requests.wallet_approval_id), so the address it was
sent to is always the one that was approved.

The security hold that follows a wallet change (payment_config.wallet_hold_hours)
is NOT replaced by the approval: both apply. See the implementation report.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.accounting import AuditTrail
from app.models.affiliate import PayoutWalletApproval
from app.models.user import User
from app.services import payment_config

PENDING, APPROVED, REJECTED, SUPERSEDED = "PENDING", "APPROVED", "REJECTED", "SUPERSEDED"
APPROVE, REJECT = "APPROVE", "REJECT"
NOTE_MIN_LENGTH = 10
AUDIT_SUBMITTED = "PAYOUT_WALLET_SUBMITTED"
AUDIT_APPROVED = "PAYOUT_WALLET_APPROVED"
AUDIT_REJECTED = "PAYOUT_WALLET_REJECTED"


class WalletApprovalError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _same(left: Optional[str], right: Optional[str]) -> bool:
    left, right = str(left or "").strip(), str(right or "").strip()
    if left.lower().startswith("0x") and right.lower().startswith("0x"):
        return left.lower() == right.lower()        # EVM addresses differ only by checksum case
    return bool(left) and left == right


def current(db: Session, user_id: int) -> Optional[PayoutWalletApproval]:
    """The approval row of the member's current wallet submission, if any."""
    return (db.query(PayoutWalletApproval)
            .filter(PayoutWalletApproval.user_id == user_id, PayoutWalletApproval.status != SUPERSEDED)
            .order_by(PayoutWalletApproval.id.desc()).first())


def approved_for(db: Session, user: User) -> Optional[PayoutWalletApproval]:
    """The APPROVED row that matches the wallet on the account now, or None."""
    row = current(db, user.id)
    if (row is None or row.status != APPROVED or not _same(row.address, user.usdt_wallet_address)
            or str(row.currency or "") != str(user.payout_currency or "")):
        return None
    return row


def submit(db: Session, locked: User, *, address: str, currency: str, method: str, wallet_change_id: Optional[int],
           ip: Optional[str], now: datetime) -> PayoutWalletApproval:
    """Record a new wallet submission (PENDING); every earlier open row of the member
    is superseded. The caller holds the member row lock. No commit."""
    (db.query(PayoutWalletApproval)
     .filter(PayoutWalletApproval.user_id == locked.id, PayoutWalletApproval.status != SUPERSEDED)
     .update({PayoutWalletApproval.status: SUPERSEDED, PayoutWalletApproval.superseded_at: now},
             synchronize_session=False))
    row = PayoutWalletApproval(user_id=locked.id, address=address, currency=currency, status=PENDING,
                               wallet_change_id=wallet_change_id, submitted_at=now, verification_method=method,
                               ip_address=ip)
    db.add(row)
    db.flush()
    db.add(AuditTrail(table_name="payout_wallet_approvals", record_id=row.id, action=AUDIT_SUBMITTED,
                      user_id=locked.id, ip_address=ip, timestamp=now, old_values=None,
                      new_values={"currency": currency, "wallet": _mask(address), "verified_by": method}))
    return row


def decide(db: Session, admin: User, approval_id: int, *, decision: str, note: Optional[str],
           password: Optional[str], ip: Optional[str] = None, now: Optional[datetime] = None) -> PayoutWalletApproval:
    """Approve or reject one PENDING wallet. Commits."""
    now = now or datetime.utcnow()
    decision = str(decision or "").strip().upper()
    if decision not in (APPROVE, REJECT):
        raise WalletApprovalError("INVALID_DECISION", "The decision is APPROVE or REJECT.")
    note = " ".join(str(note or "").split())
    if decision == REJECT and len(note) < NOTE_MIN_LENGTH:
        raise WalletApprovalError("REASON_REQUIRED", f"Say why (at least {NOTE_MIN_LENGTH} characters).")
    if not payment_config.has_permission(admin, payment_config.PERMISSION_PROCESS):
        raise WalletApprovalError("FORBIDDEN", f"The {payment_config.PERMISSION_PROCESS} permission is required.")
    try:
        payment_config.require_reauth(admin, password)
    except payment_config.PaymentConfigError as exc:
        raise WalletApprovalError(exc.code, str(exc)) from None

    row = (db.query(PayoutWalletApproval).filter(PayoutWalletApproval.id == approval_id)
           .with_for_update().populate_existing().first())
    if row is None:
        db.rollback()
        raise WalletApprovalError("NOT_FOUND", "Wallet submission not found.")
    if int(row.user_id) == int(getattr(admin, "id", 0) or 0):
        db.rollback()
        raise WalletApprovalError("SELF_ACTION_FORBIDDEN", "Nobody approves their own payout wallet.")
    if row.status != PENDING:
        db.rollback()
        raise WalletApprovalError("ALREADY_DECIDED", "This wallet is not waiting for a decision.")
    member = db.query(User).filter(User.id == row.user_id).with_for_update().populate_existing().one()
    if not _same(member.usdt_wallet_address, row.address) or str(member.payout_currency or "") != row.currency:
        db.rollback()
        raise WalletApprovalError("WALLET_CHANGED", "The member's wallet changed since this submission.")
    row.status = APPROVED if decision == APPROVE else REJECTED
    row.decided_by, row.decided_at, row.decision_note = admin.id, now, (note[:500] or None)
    if row.status == APPROVED and not member.cashout_method:
        # Setting a crypto wallet is the member's choice of automatic crypto payouts.
        member.cashout_method = "CRYPTO"
        member.cashout_method_changed_at = now
    db.add(AuditTrail(table_name="payout_wallet_approvals", record_id=row.id,
                      action=AUDIT_APPROVED if row.status == APPROVED else AUDIT_REJECTED, user_id=admin.id,
                      ip_address=ip, timestamp=now, old_values={"status": PENDING},
                      new_values={"status": row.status, "member_id": int(row.user_id), "wallet": _mask(row.address),
                                  "currency": row.currency, "note": note[:300] or None}))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise WalletApprovalError("SELF_ACTION_FORBIDDEN", "Nobody approves their own payout wallet.") from None
    db.refresh(row)
    # After the decision is committed: tell the member, and pay their available
    # commissions now (each its own payout) when the wallet was approved.
    from app.services import payout_notifications
    from app.services.cashout_engine import request_cycle

    payout_notifications.wallet_decided(db, row.id)
    if row.status == APPROVED:
        request_cycle()
    db.refresh(row)
    return row


def _mask(address: Optional[str]) -> Optional[str]:
    text = (address or "").strip()
    if not text:
        return None
    return text if len(text) < 12 else f"{text[:6]}...{text[-4:]}"


def view(row: PayoutWalletApproval, *, full_address: bool = False) -> dict:
    return {"id": row.id, "user_id": row.user_id, "status": row.status, "currency": row.currency,
            "address": row.address if full_address else _mask(row.address),
            "submitted_at": row.submitted_at.isoformat() if row.submitted_at else None,
            "verification_method": row.verification_method,
            "decided_by": row.decided_by, "decided_at": row.decided_at.isoformat() if row.decided_at else None,
            "decision_note": row.decision_note,
            "superseded_at": row.superseded_at.isoformat() if row.superseded_at else None}


def listing(db: Session, *, status: Optional[str] = None, user_id: Optional[int] = None, skip: int = 0,
            limit: int = 50) -> dict:
    """Administrators' queue (status=PENDING) and history. Full addresses: the
    approving administrator must compare them, and whitelist them at the provider."""
    query = db.query(PayoutWalletApproval)
    if status:
        query = query.filter(PayoutWalletApproval.status == status)
    if user_id:
        query = query.filter(PayoutWalletApproval.user_id == user_id)
    total = query.count()
    rows = query.order_by(PayoutWalletApproval.id.desc()).offset(skip).limit(limit).all()
    members = {u.id: u for u in db.query(User).filter(User.id.in_({r.user_id for r in rows} or {0})).all()}
    out = []
    for row in rows:
        item = view(row, full_address=True)
        member = members.get(row.user_id)
        item["username"] = getattr(member, "username", None)
        out.append(item)
    return {"total": total, "items": out}
