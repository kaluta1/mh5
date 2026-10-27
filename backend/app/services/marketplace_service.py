"""Marketplace (MyHigh5 as agent) with an EXTERNAL authorised custodian holding buyer funds.

Pricing: buyer_total = seller_base + 20% markup; the markup is MyHigh5 website revenue and the
seller base is never touched by fees or commissions.

MyHigh5 never holds these funds. Internally it tracks order state, mirrors the custodian's
confirmed events and books only what it is entitled to:
  FUNDS_HELD      Dr 1220 custodian clearing  / Cr 2121 seller payable (base) + Cr 2114 deferred markup
  RELEASED        Dr 2121 / Cr 1220 (custodian paid the seller) ; Dr 2114 / Cr 4007 markup revenue
                  + direct commission on the markup for the buyer's sponsor
  MARKUP_SETTLED  Dr 1001 / Cr 1220 (custodian remitted MyHigh5's markup)
  REFUNDED        exact reversal of the FUNDS_HELD entry (only before release)

State changes that move money happen only on custodian confirmations, which are idempotent
by the provider's event id. No provider is selected yet: the default custodian refuses to act.

Acceptance (client requirements 2026-10-28): only the authenticated BUYER accepts, deliberately,
acknowledging the current policy text; the server records the time and a unique reference. Nothing
else accepts: not a seller's "delivered", a courier, a deadline or an administrator. Acceptance then
asks the custodian to settle; a failed or timed-out request is recorded for retry and never undoes the
acceptance, and nobody is "paid" until the custodian confirms RELEASED. The seller hands over only
after verifying the acceptance on their dashboard. Ordinary marketplace disputes are retired: support
can still refund an order before release (non-handover, payment failure, duplicate charge, fraud,
seller unable to supply, a legal remedy); historical disputes stay readable.
"""
from __future__ import annotations

import secrets
from datetime import datetime
from decimal import Decimal
from typing import Optional, Protocol

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.business_model import MarketDispute, MarketOrder, MarketOrderEvent
from app.services.financial_integrity import FinancialIntegrityError, money, positive_money
from app.services.new_model_ledger import (
    Line,
    PostingType,
    SourceType,
    find_entry,
    idempotency_key,
    post_entry,
    reverse_entry,
)
from app.services.new_model_reference_data import MARKETPLACE_MARKUP_RATE, MARKETPLACE_PRODUCT_CODE, NEW_MODEL_VERSION
from app.services.new_model_revenue import accrue_direct_commission, compute_breakdown, get_policy, record_recognition

PAYMENT_PENDING = "PAYMENT_PENDING"
FUNDS_HELD = "FUNDS_HELD"
FULFILLED = "FULFILLED"
BUYER_CONFIRMED = "BUYER_CONFIRMED"
RELEASE_PENDING = "RELEASE_PENDING"
RELEASED = "RELEASED"
DISPUTED = "DISPUTED"
REFUND_PENDING = "REFUND_PENDING"
REFUNDED = "REFUNDED"
CANCELLED = "CANCELLED"

# The acceptance/policy text the buyer acknowledges when accepting (bump when the wording changes).
ACCEPTANCE_POLICY_VERSION = "MARKET-ACCEPTANCE-2026-10-28"
# Why support may refund an order before release (no ordinary dispute process any more).
SUPPORT_REFUND_REASONS = ("NON_HANDOVER", "PAYMENT_FAILURE", "DUPLICATE_CHARGE", "FRAUD", "SELLER_UNABLE_TO_SUPPLY",
                          "LEGAL_REMEDY")
DISPUTES_RETIRED = ("Marketplace disputes are no longer available. For a payment problem, a duplicate charge, "
                    "suspected fraud or an order that was not handed over, contact MyHigh5 support.")
AWAITING_ACCEPTANCE = "Awaiting buyer confirmation. Do not release the product or final service deliverables."
ACCEPTANCE_VERIFIED = "Buyer confirmation verified. Release the product or final service deliverables."
_ACCEPTED = (BUYER_CONFIRMED, RELEASE_PENDING, RELEASED)

_TRANSITIONS = {
    PAYMENT_PENDING: {FUNDS_HELD, CANCELLED},
    # paid: the buyer may accept once the product is in front of them (FUNDS_HELD) or after a service
    # was performed (FULFILLED); support may refund before release
    FUNDS_HELD: {FULFILLED, BUYER_CONFIRMED, REFUND_PENDING},
    FULFILLED: {BUYER_CONFIRMED, REFUND_PENDING},
    BUYER_CONFIRMED: {RELEASE_PENDING},
    RELEASE_PENDING: {RELEASED},
    DISPUTED: {BUYER_CONFIRMED, REFUND_PENDING},          # historical only: no new dispute is opened
    REFUND_PENDING: {REFUNDED},
    RELEASED: set(),
    REFUNDED: set(),
    CANCELLED: set(),
}


class MarketplaceError(ValueError):
    pass


class CustodianNotConfigured(MarketplaceError):
    pass


# ---------------------------------------------------------------- custodian boundary

class CustodianProvider(Protocol):
    name: str

    def create_hold(self, order: MarketOrder) -> dict: ...

    def request_release(self, order: MarketOrder) -> None: ...

    def request_refund(self, order: MarketOrder) -> None: ...


class UnconfiguredCustodian:
    """Placeholder until an authorised custodian is contracted. It never moves money."""

    name = "UNCONFIGURED"

    def _refuse(self, *_a, **_k):
        raise CustodianNotConfigured("No authorised custodian is configured; marketplace funds cannot be handled yet")

    create_hold = request_release = request_refund = _refuse


_PROVIDERS: dict[str, CustodianProvider] = {}


def register_custodian(provider: CustodianProvider) -> None:
    _PROVIDERS[provider.name] = provider


def get_custodian() -> CustodianProvider:
    name = (getattr(settings, "MARKETPLACE_CUSTODIAN", "") or "").strip()
    return _PROVIDERS.get(name) or UnconfiguredCustodian()


# ---------------------------------------------------------------- pricing / orders

def price_for_seller_base(seller_base) -> tuple[Decimal, Decimal, Decimal]:
    base = positive_money(seller_base)
    markup = money(base * MARKETPLACE_MARKUP_RATE)
    return base, markup, money(base + markup)


def _resolve_item(db: Session, item_type: str, item_id: int) -> tuple[int, Decimal]:
    """(seller_user_id, seller_base) from server-side records only."""
    if item_type == "digital_product":
        from app.models.dsp import DigitalProduct

        item = db.query(DigitalProduct).filter(DigitalProduct.id == item_id).first()
        if item is None or not item.is_active or item.price_usd is None:
            raise MarketplaceError("Product is not available for sale")
        return int(item.seller_id), money(item.price_usd)
    if item_type == "club_subscription":
        from app.models.clubs import ClubStatus, FanClub

        club = db.query(FanClub).filter(FanClub.id == item_id).first()
        if club is None or club.status != ClubStatus.ACTIVE or not club.premium_fee:
            raise MarketplaceError("Club subscription is not available")
        return int(club.owner_id), money(club.premium_fee)
    raise MarketplaceError("Unsupported marketplace item type")


def _event(db: Session, order: MarketOrder, to_state: str, *, actor_user_id: Optional[int], actor_role: str,
           external_event_id: Optional[str] = None, note: Optional[str] = None) -> None:
    db.add(MarketOrderEvent(order_id=order.id, from_state=order.state, to_state=to_state, actor_user_id=actor_user_id,
                            actor_role=actor_role, external_event_id=external_event_id, note=note))
    order.state = to_state
    db.flush()


def _transition(db: Session, order: MarketOrder, to_state: str, **kw) -> None:
    if to_state not in _TRANSITIONS.get(order.state, set()):
        raise MarketplaceError(f"Order {order.id} cannot move from {order.state} to {to_state}")
    _event(db, order, to_state, **kw)


def _open_dispute(db: Session, order: MarketOrder) -> Optional[MarketDispute]:
    return db.query(MarketDispute).filter(MarketDispute.order_id == order.id, MarketDispute.status == "OPEN").first()


def _require_financial(db: Session, user_id: int, operation, subject: dict) -> None:
    """Child/Teen Safety Phase 10 central gate (raises FinancialEligibilityHold)."""
    from app.models.user import User
    from app.services import financial_eligibility as fe

    fe.require(db, db.query(User).filter(User.id == user_id).first(), operation, subject=subject)


def _require_seller_release(db: Session, order: MarketOrder) -> None:
    from app.services.financial_eligibility import FinancialOperation

    _require_financial(db, order.seller_user_id, FinancialOperation.WITHDRAWAL, {"market_order_id": int(order.id)})


def create_order(db: Session, *, buyer_user_id: int, item_type: str, item_id: int) -> MarketOrder:
    from app.services.financial_eligibility import FinancialOperation

    seller_id, seller_base = _resolve_item(db, item_type, item_id)
    if seller_id == int(buyer_user_id):
        raise MarketplaceError("You cannot buy your own item")
    # Phase 10: the buyer pays and the seller will receive value off-platform.
    _require_financial(db, buyer_user_id, FinancialOperation.PAYMENT, {"market_item_type": item_type})
    _require_financial(db, seller_id, FinancialOperation.WITHDRAWAL, {"market_item_type": item_type})
    base, markup, total = price_for_seller_base(seller_base)
    order = MarketOrder(
        buyer_user_id=buyer_user_id, seller_user_id=seller_id, item_type=item_type, item_id=item_id, currency="USD",
        seller_base_amount=base, markup_rate=MARKETPLACE_MARKUP_RATE, markup_amount=markup, buyer_total_amount=total,
        state=PAYMENT_PENDING, custodian_provider=get_custodian().name, business_model_version=NEW_MODEL_VERSION,
    )
    db.add(order)
    db.flush()
    db.add(MarketOrderEvent(order_id=order.id, from_state=None, to_state=PAYMENT_PENDING, actor_user_id=buyer_user_id,
                            actor_role="BUYER", note="Order created"))
    db.flush()
    return order


def cancel_unpaid(db: Session, order: MarketOrder, *, actor_user_id: int) -> None:
    if int(actor_user_id) != int(order.buyer_user_id):
        raise MarketplaceError("Only the buyer can cancel an unpaid order")
    _transition(db, order, CANCELLED, actor_user_id=actor_user_id, actor_role="BUYER")


def mark_fulfilled(db: Session, order: MarketOrder, *, seller_user_id: int, note: Optional[str] = None) -> None:
    if int(seller_user_id) != int(order.seller_user_id):
        raise MarketplaceError("Only the seller can mark the order delivered")
    _transition(db, order, FULFILLED, actor_user_id=seller_user_id, actor_role="SELLER", note=note)
    order.fulfilled_at = datetime.utcnow()


def confirm_receipt(db: Session, order: MarketOrder, *, buyer_user_id: int,
                    policy_version: Optional[str] = None) -> str:
    """The buyer's final acceptance. Buyer only, deliberate (the current policy text acknowledged),
    once: a repeated request returns the same reference and changes nothing. The caller holds the
    order row lock. Settlement is then requested; its failure is kept for retry, not raised."""
    if int(buyer_user_id) != int(order.buyer_user_id):
        raise MarketplaceError("Only the buyer can confirm this order")
    if order.state in _ACCEPTED and order.acceptance_reference:
        return order.acceptance_reference                    # idempotent: already accepted
    if order.state not in (FUNDS_HELD, FULFILLED, DISPUTED):
        raise MarketplaceError("This order cannot be confirmed now")
    if policy_version != ACCEPTANCE_POLICY_VERSION:
        raise MarketplaceError("Read and acknowledge the current acceptance terms before confirming")
    if _open_dispute(db, order):
        raise MarketplaceError("An open dispute blocks release")
    _require_seller_release(db, order)  # Phase 10: CURRENT seller state before any release
    now = datetime.utcnow()
    order.acceptance_reference = f"ACC-{order.id}-{secrets.token_hex(5).upper()}"
    order.acceptance_policy_version = policy_version
    order.confirmed_at = now
    _transition(db, order, BUYER_CONFIRMED, actor_user_id=buyer_user_id, actor_role="BUYER",
                note=f"Buyer acceptance {order.acceptance_reference} ({policy_version})")
    _transition(db, order, RELEASE_PENDING, actor_user_id=None, actor_role="SYSTEM", note="Settlement requested")
    request_settlement(db, order)
    return order.acceptance_reference


def request_settlement(db: Session, order: MarketOrder) -> bool:
    """Ask the custodian to settle an accepted order (idempotent at the custodian by order). A failure
    (no custodian, timeout, provider error) is recorded and retried later; the acceptance stands and
    no money is booked here: RELEASED is booked only on the custodian's confirmation."""
    if order.state != RELEASE_PENDING:
        raise MarketplaceError("Only an accepted order awaiting settlement can be settled")
    order.release_requested_at = datetime.utcnow()
    try:
        get_custodian().request_release(order)
    except Exception as exc:  # noqa: BLE001 - recorded for retry, never undoes the acceptance
        order.release_request_error = f"{type(exc).__name__}: {exc}"[:200]
        db.flush()
        return False
    order.release_request_error = None
    db.flush()
    return True


def seller_verify_acceptance(db: Session, order: MarketOrder, *, seller_user_id: int) -> datetime:
    """The seller checked the buyer's acceptance (dashboard) and may hand over. Seller only, after a
    buyer acceptance; recorded once."""
    if int(seller_user_id) != int(order.seller_user_id):
        raise MarketplaceError("Only the seller can verify this order")
    if order.state not in _ACCEPTED or not order.acceptance_reference:
        raise MarketplaceError(AWAITING_ACCEPTANCE)
    if order.seller_verified_at is None:
        order.seller_verified_at = datetime.utcnow()
        _event(db, order, order.state, actor_user_id=seller_user_id, actor_role="SELLER",
               note=f"Seller verified buyer acceptance {order.acceptance_reference}")
    return order.seller_verified_at


def handover_status(order: MarketOrder) -> dict:
    """What each side sees: acceptance, handover and settlement, kept separate."""
    accepted = order.state in _ACCEPTED and bool(order.acceptance_reference)
    if order.state == RELEASED:
        settlement = "SETTLED"
    elif order.state == RELEASE_PENDING:
        settlement = "SETTLEMENT_RETRY_NEEDED" if order.release_request_error else "SETTLEMENT_PENDING"
    elif order.state in (REFUND_PENDING, REFUNDED):
        settlement = order.state
    else:
        settlement = "NOT_STARTED"
    fulfilment = {PAYMENT_PENDING: "UNPAID", FUNDS_HELD: "AWAITING_FULFILMENT", FULFILLED: "AWAITING_ACCEPTANCE",
                  DISPUTED: "AWAITING_ACCEPTANCE", CANCELLED: "CANCELLED", REFUND_PENDING: "REFUND_PENDING",
                  REFUNDED: "REFUNDED"}.get(order.state, "ACCEPTED")
    return {
        "acceptance_status": "ACCEPTED" if accepted else "NOT_ACCEPTED",
        "acceptance_reference": order.acceptance_reference if accepted else None,
        "accepted_at": order.confirmed_at.isoformat() + "Z" if accepted and order.confirmed_at else None,
        "seller_verified_at": order.seller_verified_at.isoformat() + "Z" if order.seller_verified_at else None,
        "handover_instruction": ACCEPTANCE_VERIFIED if accepted else AWAITING_ACCEPTANCE,
        "fulfilment_status": fulfilment,
        "settlement_status": settlement,
        "support_reason": order.support_reason,
    }


def open_dispute(db: Session, order: MarketOrder, *, user_id: int, reason: str) -> MarketDispute:
    """Retired (client requirements 2026-10-28). Kept so nothing can open one by mistake."""
    raise MarketplaceError(DISPUTES_RETIRED)


def support_refund(db: Session, order: MarketOrder, *, admin_user_id: int, reason: str, note: str) -> None:
    """Support refunds an order BEFORE release (no buyer acceptance, or a historical dispute). Never a
    release: support cannot accept on the buyer's behalf. Money moves on the custodian's REFUNDED."""
    if reason not in SUPPORT_REFUND_REASONS:
        raise MarketplaceError(f"reason must be one of {', '.join(SUPPORT_REFUND_REASONS)}")
    if not (note or "").strip():
        raise MarketplaceError("A refund needs a note")
    if order.state not in (FUNDS_HELD, FULFILLED, DISPUTED):
        raise MarketplaceError("Only a paid order that was not accepted or released can be refunded by support")
    dispute = _open_dispute(db, order)
    if dispute is not None:                                   # a historical dispute is closed by the refund
        dispute.status = "RESOLVED_REFUND"
        dispute.resolution_note = note
        dispute.resolved_by_user_id = admin_user_id
        dispute.resolved_at = datetime.utcnow()
    order.support_reason = reason
    _transition(db, order, REFUND_PENDING, actor_user_id=admin_user_id, actor_role="ADMIN", note=f"{reason}: {note}"[:500])
    get_custodian().request_refund(order)


# ---------------------------------------------------------------- custodian confirmations (money moves here)

def apply_custodian_event(db: Session, order: MarketOrder, *, event_type: str, external_event_id: str,
                          custodian_reference: Optional[str] = None) -> bool:
    """Apply a custodian-confirmed event once. Returns False when the event was already applied."""
    if not (external_event_id or "").strip():
        raise MarketplaceError("Custodian event id is required")
    if db.query(MarketOrderEvent.id).filter(MarketOrderEvent.external_event_id == external_event_id).first():
        return False
    now = datetime.utcnow()
    if event_type == "FUNDED":
        _transition(db, order, FUNDS_HELD, actor_user_id=None, actor_role="CUSTODIAN", external_event_id=external_event_id)
        order.funded_at = now
        if custodian_reference:
            order.custodian_reference = custodian_reference
        post_entry(
            db, source_type=SourceType.MARKET_ORDER, source_id=order.id, posting_type=PostingType.CUSTODY_FUNDED,
            lines=[Line("1220", debit=order.buyer_total_amount, description="Buyer funds held by external custodian"),
                   Line("2121", credit=order.seller_base_amount, description="Seller base payable (held by custodian)"),
                   Line("2114", credit=order.markup_amount, description="Deferred marketplace markup")],
            description=f"Marketplace order {order.id} funded at custodian",
        )
    elif event_type == "RELEASED":
        if _open_dispute(db, order):
            raise MarketplaceError("An open dispute blocks release")
        _transition(db, order, RELEASED, actor_user_id=None, actor_role="CUSTODIAN", external_event_id=external_event_id)
        order.released_at = now
        breakdown = compute_breakdown(get_policy(db, MARKETPLACE_PRODUCT_CODE), order.buyer_total_amount,
                                      seller_base=order.seller_base_amount)
        if breakdown.website_revenue != money(order.markup_amount):
            raise FinancialIntegrityError("Marketplace policy must treat exactly the markup as website revenue")
        entry = post_entry(
            db, source_type=SourceType.MARKET_ORDER, source_id=order.id, posting_type=PostingType.CUSTODY_RELEASED,
            lines=[Line("2121", debit=order.seller_base_amount, description="Seller paid by custodian"),
                   Line("1220", credit=order.seller_base_amount, description="Custodian released seller base"),
                   Line("2114", debit=order.markup_amount, description="Release deferred markup"),
                   Line("4007", credit=order.markup_amount, description="Marketplace markup revenue")],
            description=f"Marketplace order {order.id} released to seller",
        )
        record_recognition(db, source_type=SourceType.MARKET_ORDER, source_id=order.id, user_id=order.buyer_user_id,
                           breakdown=breakdown, journal_entry_id=entry.id)
        accrue_direct_commission(db, source_type=SourceType.MARKET_ORDER, source_id=order.id,
                                 payer_user_id=order.buyer_user_id, breakdown=breakdown)
    elif event_type == "MARKUP_SETTLED":
        if order.state != RELEASED or order.markup_settled_at is not None:
            raise MarketplaceError("Markup can only be settled once, after release")
        _event(db, order, RELEASED, actor_user_id=None, actor_role="CUSTODIAN", external_event_id=external_event_id,
               note="Markup remitted to MyHigh5")
        order.markup_settled_at = now
        post_entry(
            db, source_type=SourceType.MARKET_ORDER, source_id=order.id, posting_type=PostingType.MARKUP_SETTLED,
            lines=[Line("1001", debit=order.markup_amount, description="Markup received from custodian"),
                   Line("1220", credit=order.markup_amount, description="Custodian clearing settled")],
            description=f"Marketplace order {order.id} markup settled",
        )
    elif event_type == "REFUNDED":
        _transition(db, order, REFUNDED, actor_user_id=None, actor_role="CUSTODIAN", external_event_id=external_event_id)
        order.refunded_at = now
        funded = find_entry(db, idempotency_key(SourceType.MARKET_ORDER, order.id, PostingType.CUSTODY_FUNDED))
        if funded is not None:
            reverse_entry(db, funded, reason="Custodian refunded buyer")
    else:
        raise MarketplaceError("Unknown custodian event type")
    db.flush()
    return True


def reconciliation(db: Session) -> dict:
    """Internal custody mirror by state; compare with the custodian's statement."""
    from sqlalchemy import func

    rows = db.query(MarketOrder.state, func.count(MarketOrder.id), func.coalesce(func.sum(MarketOrder.buyer_total_amount), 0),
                    func.coalesce(func.sum(MarketOrder.markup_amount), 0)).group_by(MarketOrder.state).all()
    held = [r for r in rows if r[0] in (FUNDS_HELD, FULFILLED, BUYER_CONFIRMED, RELEASE_PENDING, DISPUTED, REFUND_PENDING)]
    unsettled_markup = (
        db.query(func.coalesce(func.sum(MarketOrder.markup_amount), 0))
        .filter(MarketOrder.state == RELEASED, MarketOrder.markup_settled_at.is_(None)).scalar()
    )
    return {
        "by_state": [{"state": s, "orders": int(c), "buyer_total": money(t), "markup": money(m)} for s, c, t, m in rows],
        "funds_held_at_custodian": money(sum((money(r[2]) for r in held), Decimal("0"))),
        "markup_released_not_yet_remitted": money(unsettled_markup or 0),
        "custodian": get_custodian().name,
    }
