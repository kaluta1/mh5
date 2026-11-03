"""Marketplace administration (Prompt 7): listing moderation, buyer support requests, overview and the
read-only reconciliation. Mounted under /admin/marketplace behind require_admin; every route also needs an
explicit permission (Super Admins hold every permission):

  * listings (read, moderation): moderate_content; a moderation decision also needs the current password and
    is never taken on one's own listing;
  * requests, overview, reconciliation (read): process_cashouts or moderate_content.

Money actions on orders (support refund, retry settlement, declining a request) live with the business-model
admin routes and need process_cashouts + the current password.
"""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models.accounting import AuditTrail
from app.models.business_model import MarketListing, MarketOrder, MarketOrderRequest
from app.models.user import User
from app.services import admin_security, marketplace_reconciliation, marketplace_service, payment_config
from app.services import marketplace_listings as ml
from app.services import seller_verification

router = APIRouter()

PERMISSION_MODERATE = "moderate_content"


def require_moderator(current_user: User = Depends(get_current_user)) -> User:
    if not payment_config.has_permission(current_user, PERMISSION_MODERATE):
        raise HTTPException(status_code=403, detail="The moderate_content permission is required.")
    return current_user


def require_marketplace_viewer(current_user: User = Depends(get_current_user)) -> User:
    if not (payment_config.has_permission(current_user, PERMISSION_MODERATE)
            or payment_config.has_permission(current_user, payment_config.PERMISSION_PROCESS)):
        raise HTTPException(status_code=403, detail="The moderate_content or process_cashouts permission is required.")
    return current_user


def _listing_admin_out(db: Session, listing: MarketListing, *, detail: bool = False) -> dict:
    base, markup, total = marketplace_service.price_for_seller_base(listing.price_usd)
    profile = seller_verification.get_profile(db, listing.seller_user_id)
    out = {
        "id": listing.id, "seller_user_id": listing.seller_user_id, "kind": listing.kind, "title": listing.title,
        "status": listing.status, "category": listing.category, "item_condition": listing.item_condition,
        "seller_price_usd": str(base), "buyer_price_usd": str(total), "quantity_available": listing.quantity_available,
        "seller_status": profile.status if profile else "NONE",
        "seller_can_sell": seller_verification.can_sell(db, listing.seller_user_id),
        "moderation_note": listing.moderation_note,
        "published_at": listing.published_at.isoformat() + "Z" if listing.published_at else None,
        "image_count": len(ml.images(db, listing)),
    }
    if detail:
        out.update({
            "description": listing.description, "handover_details": listing.handover_details,
            "disclosures": ml.disclosures(listing), "has_file": bool(listing.file_storage_key),
            "history": ml.history(db, listing),
            "orders": int(db.query(func.count(MarketOrder.id)).filter(MarketOrder.item_type == "listing",
                                                                      MarketOrder.item_id == listing.id).scalar() or 0),
        })
    return out


@router.get("/listings")
def admin_listings(status: Optional[Literal["DRAFT", "PUBLISHED", "UNPUBLISHED", "SUSPENDED", "ARCHIVED"]] = None,
                   q: Optional[str] = Query(None, max_length=80), page: int = Query(1, ge=1, le=500),
                   db: Session = Depends(get_db), moderator: User = Depends(require_moderator)):
    query = db.query(MarketListing)
    if status:
        query = query.filter(MarketListing.status == status)
    if q and q.strip():
        like = "%" + q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        query = query.filter(or_(MarketListing.title.ilike(like, escape="\\"),
                                 MarketListing.description.ilike(like, escape="\\")))
    rows = query.order_by(MarketListing.id.desc()).offset((page - 1) * 50).limit(50).all()
    return [_listing_admin_out(db, r) for r in rows]


@router.get("/listings/{listing_id}")
def admin_listing(listing_id: int, db: Session = Depends(get_db), moderator: User = Depends(require_moderator)):
    listing = db.get(MarketListing, listing_id)
    if listing is None:
        raise HTTPException(status_code=404, detail="Listing not found")
    return _listing_admin_out(db, listing, detail=True)


class ModerationIn(BaseModel):
    action: Literal["suspend", "restore"]
    reason: str = Field(min_length=5, max_length=1000)
    seller_message: Optional[str] = Field(None, max_length=500)
    current_password: str = Field(default="", max_length=256)


@router.post("/listings/{listing_id}/moderation")
def admin_moderate_listing(listing_id: int, body: ModerationIn, db: Session = Depends(get_db),
                           moderator: User = Depends(require_moderator)):
    """Suspend a listing (it leaves the marketplace at once; orders are untouched) or lift a suspension (the
    listing returns unpublished; only the seller can publish it). Never publishes, never approves."""
    listing = db.get(MarketListing, listing_id)
    if listing is None:
        raise HTTPException(status_code=404, detail="Listing not found")
    try:
        admin_security.authorize(db, moderator, permission=PERMISSION_MODERATE, password=body.current_password,
                                 target_id=listing.seller_user_id, attempted=f"MARKET_LISTING_{body.action.upper()}")
    except admin_security.AdminSecurityError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": str(exc)}) from None
    listing = db.query(MarketListing).filter(MarketListing.id == listing_id).with_for_update().first()
    before = listing.status
    try:
        ml.moderate(db, listing, admin_user_id=moderator.id, action=body.action, reason=body.reason,
                    seller_message=body.seller_message)
        db.add(AuditTrail(table_name="market_listings", record_id=listing.id, action=f"MARKET_LISTING_{body.action.upper()}",
                          old_values={"status": before}, new_values={"status": listing.status, "reason": body.reason},
                          user_id=moderator.id))
        db.commit()
    except ml.ListingError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from None
    return _listing_admin_out(db, listing, detail=True)


@router.get("/requests")
def admin_order_requests(status: Literal["OPEN", "RESOLVED"] = "OPEN", db: Session = Depends(get_db),
                         viewer: User = Depends(require_marketplace_viewer)):
    rows = (db.query(MarketOrderRequest).filter(MarketOrderRequest.status == status)
            .order_by(MarketOrderRequest.id.desc()).limit(200).all())
    orders = {o.id: o for o in db.query(MarketOrder).filter(MarketOrder.id.in_({r.order_id for r in rows} or {0})).all()}
    out = []
    for r in rows:
        o = orders.get(r.order_id)
        out.append({**marketplace_service.request_out(r), "order_state": o.state if o else None,
                    "buyer_total_amount": str(o.buyer_total_amount) if o else None,
                    "buyer_user_id": r.buyer_user_id, "seller_user_id": o.seller_user_id if o else None})
    return out


@router.get("/overview")
def admin_marketplace_overview(db: Session = Depends(get_db), viewer: User = Depends(require_marketplace_viewer)):
    from app.core.config import settings
    from app.models.seller_verification import SellerApplication, SellerProfile

    def count(column):
        return {str(k): int(v) for k, v in db.query(column, func.count()).group_by(column).all()}

    custodian = marketplace_service.get_custodian()
    return {
        "marketplace_enabled": bool(settings.MARKETPLACE_ENABLED),
        "seller_verification_enforced": seller_verification.enforcement_on(),
        "custodian": custodian.name,
        "checkout_available": bool(settings.MARKETPLACE_ENABLED) and not isinstance(
            custodian, marketplace_service.UnconfiguredCustodian),
        "sellers_by_status": count(SellerProfile.status),
        "applications_by_status": count(SellerApplication.status),
        "listings_by_status": count(MarketListing.status),
        "orders_by_state": count(MarketOrder.state),
        "open_requests": int(db.query(func.count(MarketOrderRequest.id))
                             .filter(MarketOrderRequest.status == "OPEN").scalar() or 0),
    }


@router.get("/reconciliation")
def admin_marketplace_reconciliation(db: Session = Depends(get_db), viewer: User = Depends(require_marketplace_viewer)):
    """Read only: nothing is repaired."""
    return marketplace_reconciliation.report(db)
