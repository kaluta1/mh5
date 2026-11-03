"""Member marketplace: listings (physical products, services, digital products), the seller's file
upload and the buyer's download of a paid digital order.

Orders, acceptance and settlement live with the business-model routes (/marketplace/orders...).
Everything here is closed while MARKETPLACE_ENABLED is off.
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Literal, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.config import settings
from app.db import session as session_module
from app.models.business_model import MarketListing, MarketListingImage, MarketOrder
from app.models.user import User
from app.services import marketplace_listings as ml
from app.services import marketplace_service
from app.services import seller_verification
from app.services.financial_eligibility import FinancialEligibilityHold, http_error

logger = logging.getLogger(__name__)
router = APIRouter()


# Member-safe (allowlisted in main.MEMBER_SAFE_UNAVAILABLE_CODES), so production shows it as written.
MARKETPLACE_CLOSED = {"code": "MARKETPLACE_CLOSED", "message": "The marketplace is not open yet."}


def _require_marketplace() -> None:
    if not settings.MARKETPLACE_ENABLED:
        raise HTTPException(status_code=503, detail=MARKETPLACE_CLOSED)


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
    category: Optional[str] = Field(None, max_length=40)
    item_condition: Optional[Literal["NEW", "USED", "REFURBISHED"]] = None


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
    category: Optional[str] = Field(None, max_length=40)
    item_condition: Optional[Literal["NEW", "USED", "REFURBISHED"]] = None


def _seller_labels(db: Session, listings) -> dict:
    """Public seller labels (only what MyHigh5 checked; never compliance evidence)."""
    from app.models.seller_verification import SellerProfile

    ids = {int(l.seller_user_id) for l in listings}
    if not ids:
        return {}
    rows = db.query(SellerProfile).filter(SellerProfile.user_id.in_(ids)).all()
    return {p.user_id: seller_verification.public_label(p) for p in rows}


def _image_urls(db: Session, listing: MarketListing, *, owner: bool) -> list:
    prefix = f"/api/v1/marketplace/{'my-listings' if owner else 'listings'}/{listing.id}/images"
    return [{"id": i.id, "url": f"{prefix}/{i.id}", "width": i.width, "height": i.height}
            for i in ml.images(db, listing)]


def _listing_out(listing: MarketListing, *, owner: bool = False, seller_label: Optional[str] = None,
                 db: Optional[Session] = None) -> dict:
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
        "seller_label": seller_label,
        "category": listing.category, "item_condition": listing.item_condition,
        "images": _image_urls(db, listing, owner=owner) if db is not None else [],
    }
    if owner:
        out.update({
            "status": listing.status, "seller_price_usd": str(base), "markup_usd": str(markup),
            "warranty_terms": listing.warranty_terms, "insurance_terms": listing.insurance_terms,
            "file_name": listing.file_name, "file_size": listing.file_size,
            "moderation_note": listing.moderation_note,
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
    except seller_verification.SellerNotEligible as exc:
        db.rollback()
        raise HTTPException(status_code=403, detail={"code": exc.code, "message": exc.message}) from None


@router.get("/marketplace/status")
def marketplace_status():
    """Whether the marketplace is open and whether checkout (a payment custodian) is available."""
    custodian = marketplace_service.get_custodian()
    return {"enabled": bool(settings.MARKETPLACE_ENABLED),
            "checkout_available": bool(settings.MARKETPLACE_ENABLED) and not isinstance(
                custodian, marketplace_service.UnconfiguredCustodian),
            "acceptance_policy_version": marketplace_service.ACCEPTANCE_POLICY_VERSION}


PAGE_SIZE = 24
_SORTS = {
    "newest": (MarketListing.published_at.desc(), MarketListing.id.desc()),
    "price_asc": (MarketListing.price_usd.asc(), MarketListing.id.desc()),
    "price_desc": (MarketListing.price_usd.desc(), MarketListing.id.desc()),
}


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@router.get("/marketplace/categories")
def marketplace_categories():
    """The product categories (the seller-registration vocabulary; regulated ones need a reviewed seller)."""
    from app.services.seller_verification_rules import PRODUCT_CATEGORIES, REGULATED_CATEGORIES

    return [{"code": c, "regulated": c in REGULATED_CATEGORIES} for c in PRODUCT_CATEGORIES]


@router.get("/marketplace/listings")
def browse_listings(response: Response, kind: Optional[Literal["PHYSICAL", "SERVICE", "DIGITAL"]] = None,
                    q: Optional[str] = Query(None, max_length=80), page: int = Query(1, ge=1, le=500),
                    category: Optional[str] = Query(None, max_length=40),
                    sort: Literal["newest", "price_asc", "price_desc"] = "newest",
                    min_price: Optional[Decimal] = Query(None, ge=0, le=1000000),
                    max_price: Optional[Decimal] = Query(None, ge=0, le=1000000),
                    db: Session = Depends(get_db)):
    """Published listings of sellers allowed to sell. Prices are filtered on the BUYER price (seller base +
    markup) the buyer sees. X-Total-Count carries the number of matches."""
    _require_marketplace()
    query = db.query(MarketListing).filter(MarketListing.status == ml.PUBLISHED)
    if seller_verification.enforcement_on():          # listings of sellers not (or no longer) approved are kept, not shown
        query = query.filter(seller_verification.eligible_sellers_filter(MarketListing.seller_user_id))
    if kind:
        query = query.filter(MarketListing.kind == kind)
    if category:
        query = query.filter(MarketListing.category == category.strip().upper())
    factor = 1 + marketplace_service.MARKETPLACE_MARKUP_RATE
    if min_price is not None:
        query = query.filter(MarketListing.price_usd * factor >= min_price)
    if max_price is not None:
        query = query.filter(MarketListing.price_usd * factor <= max_price)
    if q and q.strip():
        like = f"%{_escape_like(q.strip())}%"
        query = query.filter(or_(MarketListing.title.ilike(like, escape="\\"),
                                 MarketListing.description.ilike(like, escape="\\")))
    response.headers["X-Total-Count"] = str(query.count())
    rows = query.order_by(*_SORTS[sort]).offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE).all()
    labels = _seller_labels(db, rows)
    return [_listing_out(r, seller_label=labels.get(r.seller_user_id), db=db) for r in rows]


@router.get("/marketplace/my-listings")
def my_listings(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require_marketplace()
    rows = db.query(MarketListing).filter(MarketListing.seller_user_id == current_user.id) \
        .order_by(MarketListing.id.desc()).limit(200).all()
    return [_listing_out(r, owner=True, db=db) for r in rows]


@router.get("/marketplace/my-listings/{listing_id}/history")
def my_listing_history(listing_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require_marketplace()
    try:
        listing = ml.get_own(db, listing_id, current_user.id)
    except LookupError:
        raise HTTPException(status_code=404, detail="Listing not found") from None
    return ml.history(db, listing)


@router.get("/marketplace/seller/summary")
def seller_sales_summary(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """The seller's own sales (custodian-held / custodian-paid). Never a MyHigh5 balance."""
    _require_marketplace()
    return marketplace_service.seller_summary(db, current_user.id)


@router.get("/marketplace/listings/{listing_id}")
def listing_detail(listing_id: int, db: Session = Depends(get_db)):
    """A published listing (anyone). Sellers see their own drafts through /marketplace/my-listings."""
    _require_marketplace()
    listing = db.query(MarketListing).filter(MarketListing.id == listing_id).first()
    if not ml.publicly_visible(db, listing):
        raise HTTPException(status_code=404, detail="Listing not found")
    return _listing_out(listing, seller_label=_seller_labels(db, [listing]).get(listing.seller_user_id), db=db)


@router.post("/marketplace/listings", status_code=status.HTTP_201_CREATED)
def create_listing(body: ListingIn, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require_marketplace()
    listing = _run(db, lambda: ml.create_listing(db, seller_user_id=current_user.id, data=body.model_dump()))
    return _listing_out(listing, owner=True, db=db)


@router.patch("/marketplace/listings/{listing_id}")
def update_listing(listing_id: int, body: ListingPatch, db: Session = Depends(get_db),
                   current_user: User = Depends(get_current_user)):
    _require_marketplace()
    data = body.model_dump(exclude_unset=True)
    listing = _run(db, lambda: ml.update_listing(db, ml.get_own(db, listing_id, current_user.id, lock=True),
                                                 seller_user_id=current_user.id, data=data))
    return _listing_out(listing, owner=True, db=db)


@router.put("/marketplace/listings/{listing_id}/file")
def upload_listing_file(listing_id: int, file: UploadFile = File(...), db: Session = Depends(get_db),
                        current_user: User = Depends(get_current_user)):
    """The seller's digital file (PDF, EPUB or ZIP, 50 MB at most), kept in private storage."""
    _require_marketplace()
    listing = _run(db, lambda: ml.store_file(db, ml.get_own(db, listing_id, current_user.id, lock=True),
                                             seller_user_id=current_user.id, filename=file.filename or "",
                                             stream=file.file))
    return _listing_out(listing, owner=True, db=db)


@router.post("/marketplace/listings/{listing_id}/images", status_code=status.HTTP_201_CREATED)
def upload_listing_image(listing_id: int, file: UploadFile = File(...), db: Session = Depends(get_db),
                         current_user: User = Depends(get_current_user)):
    """A listing photo (JPEG, PNG or WebP, 5 MB at most, 8 per listing). Checked by content and re-encoded."""
    _require_marketplace()
    _run(db, lambda: ml.add_image(db, ml.get_own(db, listing_id, current_user.id, lock=True),
                                  seller_user_id=current_user.id, stream=file.file))
    return _listing_out(ml.get_own(db, listing_id, current_user.id), owner=True, db=db)


@router.delete("/marketplace/listings/{listing_id}/images/{image_id}")
def delete_listing_image(listing_id: int, image_id: int, db: Session = Depends(get_db),
                         current_user: User = Depends(get_current_user)):
    _require_marketplace()
    _run(db, lambda: ml.remove_image(db, ml.get_own(db, listing_id, current_user.id, lock=True),
                                     seller_user_id=current_user.id, image_id=image_id))
    return _listing_out(ml.get_own(db, listing_id, current_user.id), owner=True, db=db)


def _image_response(db: Session, listing_id: int, image_id: int) -> FileResponse:
    image = (db.query(MarketListingImage)
             .filter(MarketListingImage.id == image_id, MarketListingImage.listing_id == listing_id).first())
    try:
        path = ml.image_path(image) if image is not None else None
    except LookupError:
        path = None
    if path is None:
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(path, media_type=image.content_type, headers={
        "Cache-Control": "public, max-age=300", "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'none'"})


@router.get("/marketplace/listings/{listing_id}/images/{image_id}")
def public_listing_image(listing_id: int, image_id: int, db: Session = Depends(get_db)):
    """A photo of a listing a buyer may see (published, seller allowed to sell). Anything else: 404."""
    _require_marketplace()
    if not ml.publicly_visible(db, db.query(MarketListing).filter(MarketListing.id == listing_id).first()):
        raise HTTPException(status_code=404, detail="Image not found")
    return _image_response(db, listing_id, image_id)


@router.get("/marketplace/my-listings/{listing_id}/images/{image_id}")
def own_listing_image(listing_id: int, image_id: int, db: Session = Depends(get_db),
                      current_user: User = Depends(get_current_user)):
    _require_marketplace()
    try:
        ml.get_own(db, listing_id, current_user.id)
    except LookupError:
        raise HTTPException(status_code=404, detail="Image not found") from None
    response = _image_response(db, listing_id, image_id)
    response.headers["Cache-Control"] = "private, no-store"
    return response


# ---------------------------------------------------------------- payment custodian webhook (Prompt 7)

@router.post("/marketplace/custodian/webhook/{provider_name}")
async def custodian_webhook(provider_name: str, request: Request, db: Session = Depends(get_db)):
    """Signed deliveries from the CONFIGURED payment custodian only (none is configured: 503). The provider
    adapter verifies the signature; events are applied once each. No body content is logged."""
    body = await request.body()
    if len(body) > 256 * 1024:
        raise HTTPException(status_code=413, detail="Payload too large")
    try:
        result = marketplace_service.handle_custodian_webhook(db, provider_name=provider_name,
                                                              headers=dict(request.headers), body=body)
        db.commit()
    except marketplace_service.CustodianSignatureInvalid:
        db.rollback()
        raise HTTPException(status_code=401, detail="Invalid signature") from None
    except marketplace_service.CustodianNotConfigured:
        db.rollback()
        raise HTTPException(status_code=503, detail="Payment custodian not configured") from None
    return result


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


# Registered last: "{action}" must not capture /images and other fixed sub-paths.
@router.post("/marketplace/listings/{listing_id}/{action}")
def listing_action(listing_id: int, action: Literal["publish", "unpublish", "archive"], db: Session = Depends(get_db),
                   current_user: User = Depends(get_current_user)):
    _require_marketplace()
    fn = {"publish": ml.publish, "unpublish": ml.unpublish, "archive": ml.archive}[action]
    listing = _run(db, lambda: fn(db, ml.get_own(db, listing_id, current_user.id, lock=True),
                                  seller_user_id=current_user.id))
    return _listing_out(listing, owner=True, db=db)
