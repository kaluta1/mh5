"""Multi-Unit Referral Pool: the life of a $100 unit (P3). No revenue, commission or allocation here.

A purchase of N units (one deposit) becomes exactly N rows in referral_pool_units once its
payment is VALIDATED and matches the purchase to the cent. A unit is a participation weight:
assignments never consume it. It leaves the pool only by refund (terminal), revocation
(terminal) or suspension (eligibility lost; restored when eligibility returns, from the next
round on: restoring never creates a slot in a round that is already open).

Eligibility of a unit holder: a usable account, a confirmed adult (the central age policy, no
open age or child-safety review) and an APPROVED KYC verification. Evaluated fail-closed.

Locking. Every writer here takes the pool mutex (the referral_pool_config row, FOR UPDATE)
before any pool row, then the OPEN round, then the purchase, then units in id order, then
slots. A caller may already hold a deposit or user row lock (payment confirmation, refund);
allocation (P4) must take the referred member's row BEFORE the mutex, so the order is always
deposit -> user -> pool mutex -> round -> purchase -> units -> slots, and no KYC verification
lock is ever taken. Nothing here commits: the caller's transaction decides.

Switches: referral_pool_config.multiunit_sales_enabled gates purchases and activation from the
payment path; with it off (the default) the payment path is exactly what it was before.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Iterable, List, Optional, Sequence, Tuple

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.business_model import (
    ReferralPoolConfig,
    ReferralPoolPurchase,
    ReferralPoolRound,
    ReferralPoolRoundSlot,
    ReferralPoolUnit,
)
from app.models.payment import Deposit, DepositStatus, ProductType
from app.models.user import User

logger = logging.getLogger(__name__)

UNIT_PRICE = Decimal("100.00")
# Owner rule (Shafi Abeid, 2026-10-26): at most this many DISTINCT members take part. A member limit,
# not a unit limit: a member already in the pool may always buy more units.
MAX_POOL_MEMBERS = 10000
PRODUCT_CODE = "referral_pool_entry"
_CENT = Decimal("0.01")

# unit statuses
PENDING, ACTIVE, SUSPENDED, REFUNDED, REVOKED = "PENDING", "ACTIVE", "SUSPENDED", "REFUNDED", "REVOKED"
ENDED = (REFUNDED, REVOKED)
HELD = (PENDING, ACTIVE, SUSPENDED)            # counted against a member's holding limit
# purchase statuses
P_PENDING, P_PAID, P_PARTIAL, P_REFUNDED = "PENDING_PAYMENT", "PAID", "PARTIALLY_REFUNDED", "REFUNDED"
P_CANCELLED, P_HELD = "CANCELLED", "HELD_FOR_REVIEW"

ELIGIBILITY = "ELIGIBILITY:"                   # status_reason prefix of an eligibility suspension
ADMIN = "ADMIN:"                               # status_reason prefix of an administrator's action


class UnitsError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Eligibility:
    eligible: bool
    reason: Optional[str] = None


def money(value) -> Decimal:
    return Decimal(str(value)).quantize(_CENT)


# ---------------------------------------------------------------- locks and configuration

def lock_pool(db: Session) -> ReferralPoolConfig:
    """The pool mutex: the configuration row, locked until the caller's commit."""
    cfg = (db.query(ReferralPoolConfig).order_by(ReferralPoolConfig.id.asc())
           .with_for_update().populate_existing().first())
    if cfg is None:
        raise UnitsError("NOT_CONFIGURED", "The Referral Pool is not configured.")
    return cfg


def _open_round(db: Session) -> Optional[ReferralPoolRound]:
    return (db.query(ReferralPoolRound).filter(ReferralPoolRound.status == "OPEN")
            .with_for_update().populate_existing().first())


def _units_for_update(db: Session, ids: Iterable[int]) -> List[ReferralPoolUnit]:
    ids = sorted(set(int(i) for i in ids))
    if not ids:
        return []
    return (db.query(ReferralPoolUnit).filter(ReferralPoolUnit.id.in_(ids))
            .order_by(ReferralPoolUnit.id).with_for_update().populate_existing().all())


# ---------------------------------------------------------------- eligibility

def member_eligibility(db: Session, user: Optional[User]) -> Eligibility:
    """May this member hold active units now? Never raises; fails closed."""
    try:
        return _member_eligibility(db, user)
    except Exception as exc:  # noqa: BLE001 - never fail open
        logger.warning("Referral Pool eligibility evaluation failed: %s", type(exc).__name__)
        return Eligibility(False, "EVALUATION_FAILED")


def _member_eligibility(db: Session, user: Optional[User]) -> Eligibility:
    from app.core.child_safety import AgeReviewStatus, AgeTier
    from app.crud import crud_kyc
    from app.models.age_safety import UserAgeProfile
    from app.models.kyc import KYCStatus
    from app.services.age_policy_engine import AgeAndContestPolicyEngine, utc_today
    from app.services.financial_eligibility import open_child_safety_escalation

    if user is None or not user.is_active or user.is_deleted:
        return Eligibility(False, "ACCOUNT_UNAVAILABLE")
    from app.services.referral_pool_risk import is_blocked

    if is_blocked(db, user.id):
        return Eligibility(False, "RISK_REVIEW")      # a duplicate verified identity, pending review
    profile = db.query(UserAgeProfile).filter(UserAgeProfile.user_id == user.id).first()
    if profile is not None and (profile.review_status or AgeReviewStatus.NONE.value) != AgeReviewStatus.NONE.value:
        return Eligibility(False, "AGE_REVIEW_PENDING")
    if open_child_safety_escalation(db, user.id):
        return Eligibility(False, "CHILD_SAFETY_REVIEW")
    ctx = AgeAndContestPolicyEngine(db).context_for_user(user, utc_today(), profile)
    adult = ctx.age_known and ctx.age_tier == AgeTier.ADULT_18_PLUS and (not ctx.policy.found or ctx.legal_adult)
    if not adult:
        return Eligibility(False, "ADULT_REQUIRED")
    verification = crud_kyc.kyc_verification.get_by_user(db, user_id=user.id)
    if verification is None or verification.status != KYCStatus.APPROVED or not user.identity_verified:
        return Eligibility(False, "KYC_REQUIRED")
    return Eligibility(True)


# ---------------------------------------------------------------- purchase (checkout side; sales switch)

def create_purchase(db: Session, *, user: User, deposit: Deposit, quantity: int) -> ReferralPoolPurchase:
    """Record that `deposit` buys `quantity` units. Refused unless sales are switched on and the
    purchaser is eligible now. Idempotent per deposit (the same quantity returns the same row)."""
    cfg = lock_pool(db)
    if not cfg.multiunit_sales_enabled:
        raise UnitsError("SALES_DISABLED", "Referral Pool sales are not open.")
    if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 1:
        raise UnitsError("INVALID_QUANTITY", "Buy at least one unit.")
    if cfg.max_units_per_purchase is not None and quantity > cfg.max_units_per_purchase:
        raise UnitsError("PURCHASE_LIMIT", f"At most {cfg.max_units_per_purchase} units can be bought at once.")
    eligibility = member_eligibility(db, user)
    if not eligibility.eligible:
        raise UnitsError("NOT_ELIGIBLE", "Only KYC-approved adult members can buy Referral Pool units.")
    _check_deposit(db, deposit, user_id=user.id, total=UNIT_PRICE * quantity, paid=False)
    _check_holding_limits(db, cfg, user.id, quantity)
    _check_membership_cap(db, user.id)

    existing = db.query(ReferralPoolPurchase).filter(ReferralPoolPurchase.deposit_id == deposit.id).first()
    if existing is not None:
        if existing.user_id != user.id or existing.quantity != quantity:
            raise UnitsError("PURCHASE_CONFLICT", "This payment already records a different purchase.")
        return existing
    row = ReferralPoolPurchase(user_id=user.id, deposit_id=deposit.id, quantity=quantity, unit_price=UNIT_PRICE,
                               total_amount=UNIT_PRICE * quantity, currency="USD", status=P_PENDING)
    savepoint = db.begin_nested()
    try:
        db.add(row)
        db.flush()
        savepoint.commit()
    except IntegrityError:
        savepoint.rollback()
        raise UnitsError("PURCHASE_CONFLICT", "This payment already records a purchase.") from None
    return row


def _check_deposit(db: Session, deposit: Deposit, *, user_id: int, total: Decimal, paid: bool) -> None:
    product = db.query(ProductType).filter(ProductType.id == deposit.product_type_id).first()
    if product is None or product.code != PRODUCT_CODE:
        raise UnitsError("WRONG_PRODUCT", "This payment is not a Referral Pool purchase.")
    if int(deposit.user_id) != int(user_id):
        raise UnitsError("WRONG_MEMBER", "This payment belongs to another member.")
    if (deposit.currency or "").upper() != "USD" or money(deposit.amount) != money(total):
        raise UnitsError("AMOUNT_MISMATCH", "The payment amount does not match the units bought.")
    if paid and deposit.status != DepositStatus.VALIDATED:
        raise UnitsError("NOT_PAID", "The payment is not confirmed.")


def _reserved_units(db: Session, user_id: Optional[int] = None) -> int:
    """Units held (pending, active or suspended) plus units of purchases still being paid (their
    deposit pending or partly paid): what a limit is measured against, so two checkouts at once
    cannot both pass it."""
    held = db.query(ReferralPoolUnit).filter(ReferralPoolUnit.status.in_(HELD))
    paying = (db.query(func.coalesce(func.sum(ReferralPoolPurchase.quantity), 0))
              .join(Deposit, Deposit.id == ReferralPoolPurchase.deposit_id)
              .filter(ReferralPoolPurchase.status == P_PENDING,
                      Deposit.status.in_((DepositStatus.PENDING, DepositStatus.PARTIALLY_PAID))))
    if user_id is not None:
        held = held.filter(ReferralPoolUnit.user_id == user_id)
        paying = paying.filter(ReferralPoolPurchase.user_id == user_id)
    return held.count() + int(paying.scalar() or 0)


def _check_holding_limits(db: Session, cfg: ReferralPoolConfig, user_id: int, adding: int) -> None:
    """Optional administrator limits (NULL = unlimited), measured at checkout under the pool
    mutex. A purchase that passed them keeps its reservation until it is paid or closed."""
    if cfg.max_units_per_member is not None and _reserved_units(db, user_id) + adding > cfg.max_units_per_member:
        raise UnitsError("MEMBER_LIMIT", f"A member can hold at most {cfg.max_units_per_member} units.")
    if cfg.max_active_units is not None and _reserved_units(db) + adding > cfg.max_active_units:
        raise UnitsError("POOL_LIMIT", "The Referral Pool has reached its unit limit.")


def _member_ids(db: Session, user_id: Optional[int] = None):
    """Who takes part (user ids): a held unit (pending, active or suspended), or a purchase still
    being paid, which reserves its seat like it reserves its units."""
    held = db.query(ReferralPoolUnit.user_id.label("user_id")).filter(ReferralPoolUnit.status.in_(HELD))
    paying = (db.query(ReferralPoolPurchase.user_id.label("user_id"))
              .join(Deposit, Deposit.id == ReferralPoolPurchase.deposit_id)
              .filter(ReferralPoolPurchase.status == P_PENDING,
                      Deposit.status.in_((DepositStatus.PENDING, DepositStatus.PARTIALLY_PAID))))
    if user_id is not None:
        held = held.filter(ReferralPoolUnit.user_id == user_id)
        paying = paying.filter(ReferralPoolPurchase.user_id == user_id)
    return held.union(paying)


def pool_member_count(db: Session) -> int:
    return int(_member_ids(db).count())


def is_pool_member(db: Session, user_id: int) -> bool:
    return _member_ids(db, int(user_id)).first() is not None


def _check_membership_cap(db: Session, user_id: int) -> None:
    """MAX_POOL_MEMBERS distinct members, decided at checkout under the pool mutex (the caller holds
    it), so two first purchases at once cannot both take the last seat."""
    if not is_pool_member(db, user_id) and pool_member_count(db) >= MAX_POOL_MEMBERS:
        raise UnitsError("POOL_MEMBERS_FULL",
                         f"The Referral Pool is full ({MAX_POOL_MEMBERS:,} members). Members already in the pool "
                         "can still buy more units.")


def sales_open(db: Session) -> bool:
    cfg = db.query(ReferralPoolConfig).order_by(ReferralPoolConfig.id.asc()).first()
    return bool(cfg is not None and cfg.multiunit_sales_enabled)


# ---------------------------------------------------------------- activation (payment confirmed)

def activate_purchase_for_deposit(db: Session, deposit: Deposit, *, now: Optional[datetime] = None
                                  ) -> Optional[ReferralPoolPurchase]:
    """A VALIDATED pool deposit creates its N units, once. Returns the purchase (None when the
    deposit records no purchase). Posts nothing to the ledger. A payment that does not match
    its purchase (amount, member, product, limits) is HELD_FOR_REVIEW with no unit."""
    now = now or datetime.utcnow()
    cfg = lock_pool(db)
    purchase = (db.query(ReferralPoolPurchase).filter(ReferralPoolPurchase.deposit_id == deposit.id)
                .with_for_update().populate_existing().first())
    if purchase is None:
        return None
    if purchase.status != P_PENDING:
        return purchase                               # already activated, held, refunded or cancelled
    if purchase.unit_price != UNIT_PRICE or money(purchase.total_amount) != money(UNIT_PRICE * purchase.quantity):
        return _hold(purchase, "PRICE_MISMATCH", now)
    try:
        # The limits were applied (and reserved) at checkout: a limit changed since never holds
        # money the member already paid. What is checked here is the payment itself.
        _check_deposit(db, deposit, user_id=purchase.user_id, total=purchase.total_amount, paid=True)
    except UnitsError as exc:
        if exc.code == "NOT_PAID":
            return purchase                           # not confirmed yet: nothing happens
        return _hold(purchase, exc.code, now)
    from app.services import referral_pool_accounting as accounting

    if not accounting.receipt_ready(db, deposit):
        return purchase                               # the cash is not held in 2100 yet: nothing happens
    # The member cap, once more under the mutex. A seat reserved at checkout always fits here (this
    # purchase no longer counts as "paying"); only a payment that arrives after its reservation
    # lapsed, into a pool that filled meanwhile, is held for review (refund), never a 10,001st member.
    if not is_pool_member(db, purchase.user_id) and pool_member_count(db) >= MAX_POOL_MEMBERS:
        return _hold(purchase, "POOL_MEMBERS_FULL", now)

    holder = db.query(User).filter(User.id == purchase.user_id).first()
    eligibility = member_eligibility(db, holder)
    for index in range(1, purchase.quantity + 1):
        unit = ReferralPoolUnit(user_id=purchase.user_id, purchase_id=purchase.id, unit_index=index, source="PAID",
                                amount=purchase.unit_price, currency=purchase.currency)
        if eligibility.eligible:
            unit.status, unit.activated_at = ACTIVE, now
        else:
            # Paid, but the holder is not eligible right now: the unit waits, it is not lost.
            unit.status, unit.suspended_at, unit.status_reason = SUSPENDED, now, f"{ELIGIBILITY}{eligibility.reason}"
        db.add(unit)
    purchase.status, purchase.paid_at, purchase.units_created_at = P_PAID, now, now
    db.flush()
    # Each ACTIVE unit earns its revenue and commission in this same transaction (once).
    for unit in db.query(ReferralPoolUnit).filter(ReferralPoolUnit.purchase_id == purchase.id,
                                                  ReferralPoolUnit.status == ACTIVE).order_by(ReferralPoolUnit.id):
        accounting.recognize_unit(db, unit)
    return purchase


def _hold(purchase: ReferralPoolPurchase, code: str, now: datetime) -> ReferralPoolPurchase:
    purchase.status = P_HELD
    purchase.paid_at = purchase.paid_at or now
    purchase.notes = f"Held for review: {code}; no unit created"
    logger.warning("Referral Pool purchase %s held for review (%s)", purchase.id, code)
    return purchase


def on_pool_deposit_validated(db: Session, deposit: Deposit) -> Optional[ReferralPoolPurchase]:
    """Payment-path hook (inside the payment confirmation transaction): creates the units of a
    recorded purchase, with their revenue and commission. Never allocates. The sales switch stops
    NEW checkouts only: a purchase made while sales were open is honoured when its payment
    arrives, so a member's money is never left without its units."""
    if not db.query(ReferralPoolPurchase.id).filter(ReferralPoolPurchase.deposit_id == deposit.id).first():
        return None
    return activate_purchase_for_deposit(db, deposit)


def refuse_full_reversal_after_unit_refunds(db: Session, deposit: Deposit) -> None:
    """A full reversal reverses the whole receipt: after a unit's cash was already refunded (signed
    partial refund or an approved manual one) that would pay the same cash out twice. Refused before
    anything is written; the remaining units go through on_provider_refund instead."""
    from app.services.financial_integrity import FinancialIntegrityError

    purchase = db.query(ReferralPoolPurchase).filter(ReferralPoolPurchase.deposit_id == deposit.id).first()
    own = f"deposit-refund:{deposit.id}"                      # this reversal's own units: a replay stays a no-op
    if purchase is not None and db.query(ReferralPoolUnit.id).filter(
            ReferralPoolUnit.purchase_id == purchase.id, ReferralPoolUnit.status == REFUNDED,
            ReferralPoolUnit.refund_reference.is_distinct_from(own)).first():
        raise FinancialIntegrityError(
            f"Deposit {deposit.id} already has refunded Referral Pool units: refund the rest per unit, not by a full reversal")


def on_deposit_refunded(db: Session, deposit: Deposit) -> List[ReferralPoolUnit]:
    """Refund-path hook: a full provider refund of a pool deposit ends all its remaining units.
    Any other deposit returns at once, without touching a pool row or lock."""
    if not db.query(ReferralPoolPurchase.id).filter(ReferralPoolPurchase.deposit_id == deposit.id).first():
        return []
    from app.services import referral_pool_accounting as accounting

    refunded = refund_deposit_units(db, deposit.id, reference=f"deposit-refund:{deposit.id}")
    accounting.link_cash_reversal(db, deposit, refunded)   # the cash left with the receipt's reversal
    return refunded


# ---------------------------------------------------------------- slots of an open round

def _void_open_slots(db: Session, units: Sequence[ReferralPoolUnit], reason: str, now: datetime) -> int:
    """The units' OPEN slots in the open round become VOID; FILLED slots (history) stay."""
    if not units:
        return 0
    round_ = _open_round(db)
    if round_ is None:
        return 0
    slots = (db.query(ReferralPoolRoundSlot)
             .filter(ReferralPoolRoundSlot.round_id == round_.id, ReferralPoolRoundSlot.status == "OPEN",
                     ReferralPoolRoundSlot.unit_id.in_([u.id for u in units]))
             .order_by(ReferralPoolRoundSlot.id).with_for_update().all())
    for slot in slots:
        slot.status, slot.voided_at, slot.void_reason = "VOID", now, reason[:60]
    round_.void_slots = int(round_.void_slots or 0) + len(slots)
    if round_.filled_slots + round_.void_slots == round_.total_slots:
        round_.status, round_.completed_at = "COMPLETED", now      # nothing left to fill
    db.flush()
    return len(slots)


# ---------------------------------------------------------------- eligibility changes

def suspend_member_units(db: Session, user_id: int, reason: str, *, now: Optional[datetime] = None,
                         admin: bool = False) -> int:
    """ACTIVE units of the member become SUSPENDED and lose their open slots. Returns how many."""
    now = now or datetime.utcnow()
    lock_pool(db)
    _open_round(db)                                   # round before units: the order of every writer
    ids = [i for (i,) in db.query(ReferralPoolUnit.id).filter(ReferralPoolUnit.user_id == user_id,
                                                              ReferralPoolUnit.status == ACTIVE)]
    units = [u for u in _units_for_update(db, ids) if u.status == ACTIVE]
    for unit in units:
        unit.status, unit.suspended_at = SUSPENDED, now
        unit.status_reason = f"{ADMIN if admin else ELIGIBILITY}{reason}"[:2000]
    _void_open_slots(db, units, "UNIT_SUSPENDED", now)
    db.flush()
    return len(units)


def restore_member_units(db: Session, user_id: int, *, now: Optional[datetime] = None, admin: bool = False) -> int:
    """SUSPENDED units return to ACTIVE when the member is eligible again. Only suspensions of the
    same kind are lifted (eligibility ones automatically, an administrator's only by an
    administrator). No slot is created: the units join the next round."""
    now = now or datetime.utcnow()
    lock_pool(db)
    holder = db.query(User).filter(User.id == user_id).first()
    if not member_eligibility(db, holder).eligible:
        return 0
    prefix = ADMIN if admin else ELIGIBILITY
    ids = [i for (i,) in db.query(ReferralPoolUnit.id).filter(ReferralPoolUnit.user_id == user_id,
                                                              ReferralPoolUnit.status == SUSPENDED)]
    units = [u for u in _units_for_update(db, ids)
             if u.status == SUSPENDED and str(u.status_reason or "").startswith(prefix)]
    from app.services import referral_pool_accounting as accounting

    for unit in units:
        unit.status, unit.suspended_at, unit.status_reason = ACTIVE, None, None
        unit.activated_at = unit.activated_at or now
    db.flush()
    for unit in units:
        accounting.recognize_unit(db, unit)           # a unit paid while its holder was ineligible earns now
    return len(units)


def sync_member_eligibility(db: Session, user_id: int, *, now: Optional[datetime] = None) -> Tuple[int, int]:
    """Bring the member's units in line with their eligibility now: (suspended, restored).
    Meant to run in its own short transaction AFTER a KYC or account change has committed."""
    holder = db.query(User).filter(User.id == user_id).first()
    eligibility = member_eligibility(db, holder)
    if eligibility.eligible:
        return 0, restore_member_units(db, user_id, now=now)
    return suspend_member_units(db, user_id, eligibility.reason or "NOT_ELIGIBLE", now=now), 0


# ---------------------------------------------------------------- refunds and revocation

def refund_units(db: Session, *, purchase_id: int, reference: str, quantity: Optional[int] = None,
                 unit_ids: Optional[Sequence[int]] = None, now: Optional[datetime] = None,
                 cash_refund: bool = False) -> List[ReferralPoolUnit]:
    """Refund some or all units of one purchase, identified by the provider refund `reference`.
    Idempotent per reference: repeating a refund returns the units it already refunded.
    Each refunded unit gives back exactly what it earned (its revenue and commission); with
    `cash_refund` its cash also leaves 2100 (a verified partial refund). Refunded units are
    terminal; assignments they received stay as they are. Call only for a refund the provider
    has confirmed: a requested or failed refund must not come here."""
    from app.services import referral_pool_accounting as accounting

    now = now or datetime.utcnow()
    reference = str(reference or "").strip()[:120]
    if not reference:
        raise UnitsError("REFERENCE_REQUIRED", "A refund needs its provider reference.")
    lock_pool(db)
    _open_round(db)
    purchase = (db.query(ReferralPoolPurchase).filter(ReferralPoolPurchase.id == purchase_id)
                .with_for_update().populate_existing().first())
    if purchase is None:
        raise UnitsError("NOT_FOUND", "Purchase not found.")
    done = (db.query(ReferralPoolUnit).filter(ReferralPoolUnit.purchase_id == purchase.id,
                                              ReferralPoolUnit.refund_reference == reference)
            .order_by(ReferralPoolUnit.unit_index).all())
    if done:
        return done                                   # this refund was already applied
    open_ids = [i for (i,) in db.query(ReferralPoolUnit.id).filter(ReferralPoolUnit.purchase_id == purchase.id,
                                                                   ReferralPoolUnit.status != REFUNDED)]
    units = _units_for_update(db, open_ids)
    if unit_ids is not None:
        wanted = set(int(i) for i in unit_ids)
        if not wanted <= {u.id for u in units}:
            raise UnitsError("NOT_REFUNDABLE", "A unit named in the refund is not refundable in this purchase.")
        chosen = [u for u in units if u.id in wanted]
    else:
        count = len(units) if quantity is None else int(quantity)
        if count < 1 or count > len(units):
            raise UnitsError("INVALID_QUANTITY", "The refund names more units than remain refundable.")
        chosen = sorted(units, key=lambda u: u.unit_index, reverse=True)[:count]   # last bought first
    for unit in chosen:
        unit.status, unit.refunded_at, unit.ended_at, unit.refund_reference = REFUNDED, now, now, reference
        unit.status_reason = "REFUNDED"
    db.flush()
    for unit in sorted(chosen, key=lambda u: u.id):
        accounting.reverse_unit(db, unit, reason=f"Refund {reference}", cash_refund=cash_refund)
    _void_open_slots(db, chosen, "UNIT_REFUNDED", now)
    purchase.refunded_quantity = int(purchase.refunded_quantity or 0) + len(chosen)
    purchase.status = P_REFUNDED if purchase.refunded_quantity >= purchase.quantity else P_PARTIAL
    db.flush()
    return sorted(chosen, key=lambda u: u.unit_index)


def refund_deposit_units(db: Session, deposit_id: int, *, reference: str,
                         now: Optional[datetime] = None) -> List[ReferralPoolUnit]:
    """A full provider refund of the deposit: every unit not yet refunded."""
    lock_pool(db)
    _open_round(db)
    purchase = (db.query(ReferralPoolPurchase).filter(ReferralPoolPurchase.deposit_id == deposit_id)
                .with_for_update().populate_existing().first())
    if purchase is None:
        return []
    remaining = db.query(ReferralPoolUnit).filter(ReferralPoolUnit.purchase_id == purchase.id,
                                                  ReferralPoolUnit.status != REFUNDED).count()
    if remaining:
        return refund_units(db, purchase_id=purchase.id, reference=reference, now=now)
    if purchase.status in (P_PENDING, P_HELD):
        purchase.status = P_REFUNDED                  # refunded before any unit existed
        db.flush()
    return []


# ---------------------------------------------------------------- refunds the provider confirms

def on_provider_refund(db: Session, deposit: Deposit, refunded_total, *, source: str,
                       now: Optional[datetime] = None) -> Optional[List[ReferralPoolUnit]]:
    """A SIGNED provider refund event for a pool deposit: `refunded_total` is the provider's
    cumulative refunded amount (the verifiable evidence). The units it covers and not yet
    refunded are refunded, with their cash, revenue and commission; a replay or an older event
    (a smaller total) changes nothing. Returns None when the deposit has no units (the caller
    keeps its existing handling). Caller holds the deposit row lock."""
    from app.services.financial_integrity import FinancialIntegrityError

    purchase = db.query(ReferralPoolPurchase).filter(ReferralPoolPurchase.deposit_id == deposit.id).first()
    if purchase is None or not db.query(ReferralPoolUnit.id).filter(ReferralPoolUnit.purchase_id == purchase.id).first():
        return None
    total = money(refunded_total)
    if total <= 0 or total % money(purchase.unit_price) != 0 or total > money(purchase.total_amount):
        raise FinancialIntegrityError("A Referral Pool refund must be a whole number of units of this purchase")
    covered = int(total / money(purchase.unit_price))
    lock_pool(db)
    locked = (db.query(ReferralPoolPurchase).filter(ReferralPoolPurchase.id == purchase.id)
              .with_for_update().populate_existing().one())
    already = db.query(ReferralPoolUnit).filter(ReferralPoolUnit.purchase_id == locked.id,
                                                ReferralPoolUnit.status == REFUNDED).count()
    if covered <= already:
        return []                                     # replayed or out-of-order event: nothing new
    return refund_units(db, purchase_id=locked.id, quantity=covered - already, cash_refund=True, now=now,
                        reference=f"{source}-refund:{deposit.id}:{total}")


def purchase_fully_refunded(db: Session, deposit: Deposit) -> bool:
    purchase = db.query(ReferralPoolPurchase).filter(ReferralPoolPurchase.deposit_id == deposit.id).first()
    return purchase is not None and purchase.status == P_REFUNDED


# ---------------------------------------------------------------- refunds the provider cannot confirm

AUDIT_REFUND_PROPOSED = "REFERRAL_POOL_MANUAL_REFUND_PROPOSED"
# References written by the signed-provider and full-reversal paths: never accepted from an administrator,
# so a claim can never look like provider evidence.
RESERVED_REFUND_PREFIXES = ("provider-refund:", "soncopay-refund:", "deposit-refund:")
AUDIT_REFUND_DECIDED = "REFERRAL_POOL_MANUAL_REFUND_DECIDED"


def _finance_actor(actor, password: Optional[str]) -> None:
    from app.services import payment_config

    if not payment_config.has_permission(actor, payment_config.PERMISSION_PROCESS):
        raise UnitsError("FORBIDDEN", f"The {payment_config.PERMISSION_PROCESS} permission is required.")
    try:
        payment_config.require_reauth(actor, password)
    except payment_config.PaymentConfigError as exc:
        raise UnitsError(exc.code, str(exc)) from None


def propose_manual_refund(db: Session, actor, *, purchase_id: int, quantity: int, amount, provider_reference: str,
                          evidence_note: str, password: Optional[str], ip: Optional[str] = None):
    """A controlled exception (owner decision 2026-10-24): a refund the provider sends no signed
    event for. One finance administrator proposes it with the provider's reference and the
    evidence they checked; nothing moves until a DIFFERENT administrator approves it. The
    reference is recorded, never taken as verified by itself. Commits."""
    from app.models.accounting import AuditTrail
    from app.models.business_model import ReferralPoolRefundRecord
    from app.services.financial_reversal import is_reversed_deposit

    _finance_actor(actor, password)
    reference = str(provider_reference or "").strip()[:120]
    note = str(evidence_note or "").strip()
    if not reference:
        raise UnitsError("REFERENCE_REQUIRED", "Enter the provider's refund reference.")
    if reference.lower().startswith(RESERVED_REFUND_PREFIXES):
        raise UnitsError("REFERENCE_RESERVED", "This reference format is reserved for provider-verified refunds.")
    if len(note) < 10:
        raise UnitsError("EVIDENCE_REQUIRED", "Describe the evidence checked at the provider (at least 10 characters).")
    if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 1:
        raise UnitsError("INVALID_QUANTITY", "Refund at least one unit.")
    try:
        amount_d = money(amount)
    except Exception:  # noqa: BLE001 - any unparseable amount
        raise UnitsError("INVALID_AMOUNT", "Enter the refunded amount.") from None
    purchase = db.get(ReferralPoolPurchase, purchase_id)
    if purchase is None:
        raise UnitsError("NOT_FOUND", "Purchase not found.")
    if amount_d != money(purchase.unit_price * quantity):
        raise UnitsError("AMOUNT_MISMATCH", "The refunded amount must be the price of the units refunded.")
    deposit = db.get(Deposit, purchase.deposit_id)
    if deposit is None or deposit.status != DepositStatus.VALIDATED or is_reversed_deposit(deposit):
        raise UnitsError("NOT_REFUNDABLE", "This payment is not a confirmed, unrefunded payment.")
    refundable = db.query(ReferralPoolUnit).filter(ReferralPoolUnit.purchase_id == purchase.id,
                                                   ReferralPoolUnit.status != REFUNDED).count()
    if quantity > refundable:
        raise UnitsError("INVALID_QUANTITY", "The refund names more units than remain refundable.")
    record = ReferralPoolRefundRecord(purchase_id=purchase.id, quantity=quantity, amount=amount_d,
                                      provider_reference=reference, evidence_note=note[:4000], status="PROPOSED",
                                      proposed_by=actor.id)
    savepoint = db.begin_nested()
    try:
        db.add(record)
        db.flush()
        savepoint.commit()
    except IntegrityError:
        savepoint.rollback()
        db.rollback()
        raise UnitsError("REFERENCE_REUSED", "This provider reference is already recorded.") from None
    db.add(AuditTrail(table_name="referral_pool_refund_records", record_id=record.id, action=AUDIT_REFUND_PROPOSED,
                      user_id=actor.id, ip_address=(ip or None),
                      new_values={"purchase_id": purchase.id, "quantity": quantity, "amount": f"{amount_d:.2f}",
                                  "provider_reference": reference}))
    db.commit()
    return record


def decide_manual_refund(db: Session, actor, record_id: int, *, approve: bool, note: str, password: Optional[str],
                         ip: Optional[str] = None, now: Optional[datetime] = None):
    """A second finance administrator approves (the units are refunded now, with their money) or
    rejects the proposal. Never the proposer. Commits; a failure (e.g. a commission payout in
    flight) rolls everything back and the proposal stays open."""
    from app.models.accounting import AuditTrail
    from app.models.business_model import ReferralPoolRefundRecord

    now = now or datetime.utcnow()
    _finance_actor(actor, password)
    note = str(note or "").strip()
    if len(note) < 5:
        raise UnitsError("NOTE_REQUIRED", "Explain the decision (at least 5 characters).")
    lock_pool(db)
    record = (db.query(ReferralPoolRefundRecord).filter(ReferralPoolRefundRecord.id == record_id)
              .with_for_update().populate_existing().first())
    if record is None:
        raise UnitsError("NOT_FOUND", "Refund record not found.")
    if record.status != "PROPOSED":
        db.rollback()
        raise UnitsError("ALREADY_DECIDED", "This refund was already decided.")
    if int(record.proposed_by) == int(actor.id):
        db.rollback()
        raise UnitsError("SAME_ADMINISTRATOR", "A refund is approved by a different administrator than its proposer.")
    try:
        if approve:
            done = refund_units(db, purchase_id=record.purchase_id, quantity=record.quantity,
                                reference=record.provider_reference, cash_refund=True, now=now)
            record.executed_unit_ids = ",".join(str(u.id) for u in done)
        record.status = "APPROVED" if approve else "REJECTED"
        record.decided_by, record.decided_at, record.decision_note = actor.id, now, note[:500]
        db.add(AuditTrail(table_name="referral_pool_refund_records", record_id=record.id, action=AUDIT_REFUND_DECIDED,
                          user_id=actor.id, ip_address=(ip or None),
                          old_values={"status": "PROPOSED"},
                          new_values={"status": record.status, "units": record.executed_unit_ids}))
        db.commit()
    except Exception:
        db.rollback()
        raise
    return record


def revoke_unit(db: Session, unit_id: int, reason: str, *, now: Optional[datetime] = None) -> ReferralPoolUnit:
    """An administrator ends a unit (no refund). Terminal."""
    now = now or datetime.utcnow()
    lock_pool(db)
    _open_round(db)
    units = _units_for_update(db, [unit_id])
    if not units:
        raise UnitsError("NOT_FOUND", "Unit not found.")
    unit = units[0]
    if unit.status in ENDED:
        raise UnitsError("ALREADY_ENDED", "This unit has already ended.")
    unit.status, unit.ended_at, unit.status_reason = REVOKED, now, f"{ADMIN}{reason}"[:2000]
    _void_open_slots(db, [unit], "UNIT_REVOKED", now)
    db.flush()
    return unit
