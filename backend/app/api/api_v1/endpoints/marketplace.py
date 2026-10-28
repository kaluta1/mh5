"""Member marketplace: listings (physical products, services, digital products), the seller's file
upload and the buyer's download of a paid digital order.

Orders, acceptance and settlement live with the business-model routes (/marketplace/orders...).
Everything here is closed while MARKETPLACE_ENABLED is off.
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Literal, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.config import settings
from app.db import session as session_module
from app.models.business_model import MarketListing, MarketOrder
from app.models.user import User
from app.services import marketplace_listings as ml
from app.services import marketplace_service
from app.services.financial_eligibility import FinancialEligibilityHold, http_error

logger = logging.getLogger(__name__)
router = APIRouter()


def _require_marketplace() -> None:
    if not settings.MARKETPLACE_ENABLED:
        raise HTTPException(status_code=503, detail="The marketplace is not open yet")


class ListingIn(BaseModel):
    kind: Literal["PHYSICAL", "SERVICE", "DIGITAL"]
    title: str = Field(max_length=160)
    description: str = Field(max_length=5000)
    price_usd: Decimal
    quantity_available: Optional[int] = None
    handover_details: Optional[str] = Field(None, max_length=2000)
    warranty_available: bool = False
    warranty_terms: Optional[str] = Field(None, max_length=2000)
    insurance_available: bool = False
    insurance_terms: Optional[str] = Field(None, max_length=2000)


class ListingPatch(BaseModel):
    kind: Optional[Literal["PHYSICAL", "SERVICE", "DIGITAL"]] = None
    title: Optional[str] = Field(None, max_length=160)
    description: Optional[str] = Field(None, max_length=5000)
    price_usd: Optional[Decimal] = None
    quantity_available: Optional[int] = None
    handover_details: Optional[str] = Field(None, max_length=2000)
    warranty_available: Optional[bool] = None
    warranty_terms: Optional[str] = Field(None, max_length=2000)
    insurance_available: Optional[bool] = None
    insurance_terms: Optional[str] = Field(None, max_length=2000)


def _listing_out(listing: MarketListing, *, owner: bool = False) -> dict:
    base, markup, total = marketplace_service.price_for_seller_base(listing.price_usd)
    out = {
        "id": listing.id, "kind": listing.kind, "title": listing.title, "description": listing.description,
        "seller_user_id": listing.seller_user_id, "buyer_price_usd": str(total),
        "quantity_available": listing.quantity_available, "available": ml.is_buyable(listing),
        "handover_details": listing.handover_details,
        "warranty_available": bool(listing.warranty_available), "insurance_available": bool(listing.insurance_available),
        "disclosures": ml.disclosures(listing),
        "has_file": bool(listing.file_storage_key),
        "published_at": listing.published_at.isoformat() + "Z" if listing.published_at else None,
    }
    if owner:
        out.update({
            "status": listing.status, "seller_price_usd": str(base), "markup_usd": str(markup),
            "warranty_terms": listing.warranty_terms, "insurance_terms": listing.insurance_terms,
            "file_name": listing.file_name, "file_size": listing.file_size,
        })
    return out


def _run(db: Session, fn):
    try:
        result = fn()
        db.commit()
        return result
    except LookupError:
        db.rollback()
        raise HTTPException(status_code=404, detail="Listing not found") from None
    except ml.ListingError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except FinancialEligibilityHold as exc:  # Phase 10: generic body, no reason codes
        db.rollback()
        raise http_error(exc) from None


@router.get("/marketplace/status")
def marketplace_status():
    """Whether the marketplace is open and whether checkout (a payment custodian) is available."""
    custodian = marketplace_service.get_custodian()
    return {"enabled": bool(settings.MARKETPLACE_ENABLED),
            "checkout_available": bool(settings.MARKETPLACE_ENABLED) and not isinstance(
                custodian, marketplace_service.UnconfiguredCustodian),
            "acceptance_policy_version": marketplace_service.ACCEPTANCE_POLICY_VERSION}


@router.get("/marketplace/listings")
def browse_listings(kind: Optional[Literal["PHYSICAL", "SERVICE", "DIGITAL"]] = None,
                    q: Optional[str] = Query(None, max_length=80), page: int = Query(1, ge=1, le=500),
                    db: Session = Depends(get_db)):
    _require_marketplace()
    query = db.query(MarketListing).filter(MarketListing.status == ml.PUBLISHED)
    if kind:
        query = query.filter(MarketListing.kind == kind)
    if q and q.strip():
        like = f"%{q.strip()}%"
        query = query.filter(or_(MarketListing.title.ilike(like), MarketListing.description.ilike(like)))
    rows = query.order_by(MarketListing.published_at.desc(), MarketListing.id.desc()).offset((page - 1) * 24).limit(24).all()
    return [_listing_out(r) for r in rows]


@router.get("/marketplace/my-listings")
def my_listings(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require_marketplace()
    rows = db.query(MarketListing).filter(MarketListing.seller_user_id == current_user.id) \
        .order_by(MarketListing.id.desc()).limit(200).all()
    return [_listing_out(r, owner=True) for r in rows]


@router.get("/marketplace/listings/{listing_id}")
def listing_detail(listing_id: int, db: Session = Depends(get_db)):
    """A published listing (anyone). Sellers see their own drafts through /marketplace/my-listings."""
    _require_marketplace()
    listing = db.query(MarketListing).filter(MarketListing.id == listing_id).first()
    if listing is None or listing.status != ml.PUBLISHED:
        raise HTTPException(status_code=404, detail="Listing not found")
    return _listing_out(listing)


@router.post("/marketplace/listings", status_code=status.HTTP_201_CREATED)
def create_listing(body: ListingIn, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require_marketplace()
    listing = _run(db, lambda: ml.create_listing(db, seller_user_id=current_user.id, data=body.model_dump()))
    return _listing_out(listing, owner=True)


@router.patch("/marketplace/listings/{listing_id}")
def update_listing(listing_id: int, body: ListingPatch, db: Session = Depends(get_db),
                   current_user: User = Depends(get_current_user)):
    _require_marketplace()
    data = body.model_dump(exclude_unset=True)
    listing = _run(db, lambda: ml.update_listing(db, ml.get_own(db, listing_id, current_user.id, lock=True),
                                                 seller_user_id=current_user.id, data=data))
    return _listing_out(listing, owner=True)


@router.post("/marketplace/listings/{listing_id}/{action}")
def listing_action(listing_id: int, action: Literal["publish", "unpublish"], db: Session = Depends(get_db),
                   current_user: User = Depends(get_current_user)):
    _require_marketplace()
    fn = ml.publish if action == "publish" else ml.unpublish
    listing = _run(db, lambda: fn(db, ml.get_own(db, listing_id, current_user.id, lock=True),
                                  seller_user_id=current_user.id))
    return _listing_out(listing, owner=True)


@router.put("/marketplace/listings/{listing_id}/file")
def upload_listing_file(listing_id: int, file: UploadFile = File(...), db: Session = Depends(get_db),
                        current_user: User = Depends(get_current_user)):
    """The seller's digital file (PDF, EPUB or ZIP, 50 MB at most), kept in private storage."""
    _require_marketplace()
    listing = _run(db, lambda: ml.store_file(db, ml.get_own(db, listing_id, current_user.id, lock=True),
                                             seller_user_id=current_user.id, filename=file.filename or "",
                                             stream=file.file))
    return _listing_out(listing, owner=True)


def _file_response(listing: MarketListing, chunks) -> StreamingResponse:
    safe_name = "".join(c for c in (listing.file_name or "download") if c.isalnum() or c in "._- ")[:120] or "download"
    return StreamingResponse(chunks, media_type=listing.file_content_type or "application/octet-stream", headers={
        "Content-Disposition": f'attachment; filename="{safe_name}"', "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff", "Content-Length": str(listing.file_size or 0)})


def _read(path: str):
    with open(path, "rb") as f:
        while chunk := f.read(64 * 1024):
            yield chunk


@router.get("/marketplace/listings/{listing_id}/file")
def seller_file(listing_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """The seller's own copy (checking the upload). Never finalises anything."""
    _require_marketplace()
    try:
        listing = ml.get_own(db, listing_id, current_user.id)
        path = ml.file_path(listing)
    except LookupError:
        raise HTTPException(status_code=404, detail="File not found") from None
    return _file_response(listing, _read(path))


def _finalise_after_complete_download(order_id: int, user_id: int) -> None:
    db = session_module.SessionLocal()
    try:
        order = db.query(MarketOrder).filter(MarketOrder.id == order_id).with_for_update().first()
        marketplace_service.record_digital_download(db, order, buyer_user_id=user_id)
        db.commit()
    except Exception:  # noqa: BLE001 - the file was delivered; the next complete download retries
        db.rollback()
        logger.exception("Marketplace order %s: digital delivery could not be recorded", order_id)
    finally:
        db.close()


@router.get("/marketplace/orders/{order_id}/download")
def buyer_download(order_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """The buyer's download of a paid digital order. Only once the LAST byte has been handed to the
    connection is the delivery recorded (first time: it finalises the purchase and starts settlement).
    An interrupted download records nothing."""
    _require_marketplace()
    order = db.query(MarketOrder).filter(MarketOrder.id == order_id).first()
    if order is None or not marketplace_service.can_download(order, current_user.id):
        raise HTTPException(status_code=404, detail="Download not available")
    listing = db.query(MarketListing).filter(MarketListing.id == order.item_id).first()
    try:
        path = ml.file_path(listing) if listing is not None else ml.file_path(MarketListing())
    except LookupError:
        raise HTTPException(status_code=404, detail="Download not available") from None
    user_id = current_user.id

    def chunks():
        yield from _read(path)
        _finalise_after_complete_download(order_id, user_id)       # reached only after the last chunk

    return _file_response(listing, chunks())
