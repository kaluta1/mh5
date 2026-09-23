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
"""
from __future__ import annotations

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

_TRANSITIONS = {
    PAYMENT_PENDING: {FUNDS_HELD, CANCELLED},
    FUNDS_HELD: {FULFILLED, DISPUTED, REFUND_PENDING},
    FULFILLED: {BUYER_CONFIRMED, DISPUTED},
    BUYER_CONFIRMED: {RELEASE_PENDING},
    RELEASE_PENDING: {RELEASED},
    DISPUTED: {RELEASE_PENDING, REFUND_PENDING},
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


def create_order(db: Session, *, buyer_user_id: int, item_type: str, item_id: int) -> MarketOrder:
    seller_id, seller_base = _resolve_item(db, item_type, item_id)
    if seller_id == int(buyer_user_id):
        raise MarketplaceError("You cannot buy your own item")
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


def confirm_receipt(db: Session, order: MarketOrder, *, buyer_user_id: int) -> None:
    """Buyer confirmation requests release from the custodian (unless a dispute is open)."""
    if int(buyer_user_id) != int(order.buyer_user_id):
        raise MarketplaceError("Only the buyer can confirm receipt")
    if _open_dispute(db, order):
        raise MarketplaceError("An open dispute blocks release")
    _transition(db, order, BUYER_CONFIRMED, actor_user_id=buyer_user_id, actor_role="BUYER")
    order.confirmed_at = datetime.utcnow()
    _transition(db, order, RELEASE_PENDING, actor_user_id=None, actor_role="SYSTEM", note="Release requested from custodian")
    get_custodian().request_release(order)


def open_dispute(db: Session, order: MarketOrder, *, user_id: int, reason: str) -> MarketDispute:
    if int(user_id) not in (int(order.buyer_user_id), int(order.seller_user_id)):
        raise MarketplaceError("Only the buyer or seller can open a dispute")
    if not (reason or "").strip():
        raise MarketplaceError("A dispute needs a reason")
    role = "BUYER" if int(user_id) == int(order.buyer_user_id) else "SELLER"
    _transition(db, order, DISPUTED, actor_user_id=user_id, actor_role=role, note=reason[:500])
    dispute = MarketDispute(order_id=order.id, opened_by_user_id=user_id, reason=reason.strip(), status="OPEN")
    db.add(dispute)
    db.flush()
    return dispute


def resolve_dispute(db: Session, order: MarketOrder, *, admin_user_id: int, outcome: str, note: str) -> MarketDispute:
    dispute = _open_dispute(db, order)
    if dispute is None or order.state != DISPUTED:
        raise MarketplaceError("No open dispute on this order")
    if outcome not in ("RELEASE", "REFUND"):
        raise MarketplaceError("outcome must be RELEASE or REFUND")
    dispute.status = "RESOLVED_RELEASE" if outcome == "RELEASE" else "RESOLVED_REFUND"
    dispute.resolution_note = note
    dispute.resolved_by_user_id = admin_user_id
    dispute.resolved_at = datetime.utcnow()
    target = RELEASE_PENDING if outcome == "RELEASE" else REFUND_PENDING
    _transition(db, order, target, actor_user_id=admin_user_id, actor_role="ADMIN", note=note)
    custodian = get_custodian()
    (custodian.request_release if outcome == "RELEASE" else custodian.request_refund)(order)
    return dispute


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
