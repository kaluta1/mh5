"""Member marketplace listings: physical products, services and digital products (e-books).

A listing's price is the SELLER BASE; the buyer pays it plus the marketplace markup (see
marketplace_service). Listings are created as drafts, published and unpublished by their seller only.

Disclosures: warranty and insurance coverage are claimed only when the seller gives their terms;
otherwise the listing says plainly that none is offered. Statutory consumer rights are never excluded.

Digital files are kept in private storage under a random key (never a public URL) and are served only
to the seller and to buyers of a paid order (see the download route).
"""
from __future__ import annotations

import hashlib
import os
import secrets
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import BinaryIO, Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.business_model import MarketListing

PHYSICAL, SERVICE, DIGITAL = "PHYSICAL", "SERVICE", "DIGITAL"
KINDS = (PHYSICAL, SERVICE, DIGITAL)
DRAFT, PUBLISHED, UNPUBLISHED = "DRAFT", "PUBLISHED", "UNPUBLISHED"

MIN_PRICE, MAX_PRICE = Decimal("1.00"), Decimal("100000.00")
MAX_FILE_BYTES = 50 * 1024 * 1024
FILE_TYPES = {".pdf": "application/pdf", ".epub": "application/epub+zip", ".zip": "application/zip"}

WARRANTY_NONE = "No warranty is offered by the seller."
INSURANCE_NONE = "No insurance is offered with this item."
CONSUMER_RIGHTS = ("Your statutory consumer rights are not affected. MyHigh5 support can still refund an order "
                   "that was not handed over, a duplicate charge, a payment failure or a fraudulent sale.")

EDITABLE = ("kind", "title", "description", "price_usd", "quantity_available", "handover_details",
            "warranty_available", "warranty_terms", "insurance_available", "insurance_terms")


class ListingError(ValueError):
    pass


def _text(value, field: str, *, low: int, high: int, required: bool = True) -> Optional[str]:
    value = (value or "").strip()
    if not value:
        if required:
            raise ListingError(f"{field} is required")
        return None
    if not (low <= len(value) <= high):
        raise ListingError(f"{field} must be {low} to {high} characters")
    return value


def _price(value) -> Decimal:
    try:
        price = Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError):
        raise ListingError("price_usd must be an amount in USD") from None
    if not (MIN_PRICE <= price <= MAX_PRICE):
        raise ListingError(f"price_usd must be between {MIN_PRICE} and {MAX_PRICE}")
    return price


def _apply(listing: MarketListing, data: dict) -> None:
    unknown = set(data) - set(EDITABLE)
    if unknown:
        raise ListingError(f"Unknown field: {sorted(unknown)[0]}")
    merged = {f: getattr(listing, f) for f in EDITABLE}
    merged.update(data)
    kind = merged["kind"]
    if kind not in KINDS:
        raise ListingError(f"kind must be one of {', '.join(KINDS)}")
    if listing.id and listing.kind and kind != listing.kind and listing.status != DRAFT:
        raise ListingError("The kind of a published listing cannot change")
    quantity = merged["quantity_available"]
    if kind == PHYSICAL:
        if quantity is not None and (not isinstance(quantity, int) or isinstance(quantity, bool) or quantity < 0):
            raise ListingError("quantity_available must be a whole number of units, 0 or more")
    elif quantity is not None:
        raise ListingError("Only a physical product has a quantity")
    for flag, terms, label in (("warranty_available", "warranty_terms", "warranty"),
                               ("insurance_available", "insurance_terms", "insurance")):
        merged[flag] = bool(merged[flag])
        merged[terms] = _text(merged[terms], f"{label}_terms", low=10, high=2000, required=merged[flag])
        if not merged[flag]:
            merged[terms] = None                         # coverage is never described when not offered
    listing.kind = kind
    listing.title = _text(merged["title"], "title", low=3, high=160)
    listing.description = _text(merged["description"], "description", low=10, high=5000)
    listing.price_usd = _price(merged["price_usd"])
    listing.quantity_available = quantity
    listing.handover_details = _text(merged["handover_details"], "handover_details", low=5, high=2000, required=False)
    for f in ("warranty_available", "warranty_terms", "insurance_available", "insurance_terms"):
        setattr(listing, f, merged[f])


def _own(listing: Optional[MarketListing], seller_user_id: int) -> MarketListing:
    if listing is None or int(listing.seller_user_id) != int(seller_user_id):
        raise LookupError("Listing not found")
    return listing


def get_own(db: Session, listing_id: int, seller_user_id: int, *, lock: bool = False) -> MarketListing:
    q = db.query(MarketListing).filter(MarketListing.id == listing_id)
    return _own((q.with_for_update() if lock else q).first(), seller_user_id)


def create_listing(db: Session, *, seller_user_id: int, data: dict) -> MarketListing:
    listing = MarketListing(seller_user_id=seller_user_id, status=DRAFT, warranty_available=False,
                            insurance_available=False, quantity_available=None, handover_details=None,
                            warranty_terms=None, insurance_terms=None, kind=None, title=None, description=None,
                            price_usd=None)
    _apply(listing, data)
    db.add(listing)
    db.flush()
    return listing


def update_listing(db: Session, listing: MarketListing, *, seller_user_id: int, data: dict) -> MarketListing:
    """Edits apply to new orders only: every order keeps the snapshot its buyer was shown. A live listing
    is edited only by an approved seller (when seller verification is enforced); drafts always."""
    from app.services import seller_verification

    _own(listing, seller_user_id)
    if listing.status == PUBLISHED:
        seller_verification.require_can_sell(db, listing.seller_user_id)
    _apply(listing, data)
    db.flush()
    return listing


def publish(db: Session, listing: MarketListing, *, seller_user_id: int) -> MarketListing:
    from app.models.user import User
    from app.services import content_safety
    from app.services import financial_eligibility as fe
    from app.services import seller_verification

    _own(listing, seller_user_id)
    if listing.kind == DIGITAL and not listing.file_storage_key:
        raise ListingError("Upload the digital file before publishing")
    if listing.kind in (PHYSICAL, SERVICE) and not listing.handover_details:
        raise ListingError("Describe how the product or service is handed over before publishing")
    if content_safety.detect_text_harm(f"{listing.title}\n{listing.description}", possibly_minor=False):
        raise ListingError("This listing cannot be published as written. Please contact MyHigh5 support.")
    # Publishing and relisting need an approved seller while seller verification is enforced.
    seller_verification.require_can_sell(db, listing.seller_user_id)
    # The seller will receive value: the same eligibility as any seller payout (Phase 10).
    seller = db.query(User).filter(User.id == listing.seller_user_id).first()
    fe.require(db, seller, fe.FinancialOperation.WITHDRAWAL, subject={"market_listing_id": int(listing.id)})
    if listing.status != PUBLISHED:
        listing.status = PUBLISHED
        listing.published_at = datetime.utcnow()
    db.flush()
    return listing


def unpublish(db: Session, listing: MarketListing, *, seller_user_id: int) -> MarketListing:
    """Stops new orders; existing orders (and paid buyers' downloads) are unaffected."""
    _own(listing, seller_user_id)
    if listing.status == PUBLISHED:
        listing.status = UNPUBLISHED
    db.flush()
    return listing


def is_buyable(listing: Optional[MarketListing]) -> bool:
    return (listing is not None and listing.status == PUBLISHED
            and (listing.kind != PHYSICAL or listing.quantity_available is None or listing.quantity_available > 0))


def disclosures(listing: MarketListing) -> dict:
    return {
        "warranty": f"Warranty available: {listing.warranty_terms}" if listing.warranty_available else WARRANTY_NONE,
        "insurance": f"Insurance available: {listing.insurance_terms}" if listing.insurance_available else INSURANCE_NONE,
        "consumer_rights": CONSUMER_RIGHTS,
    }


def snapshot(listing: MarketListing) -> dict:
    """What the buyer is shown when ordering, kept on the order."""
    return {
        "listing_id": int(listing.id), "kind": listing.kind, "title": listing.title,
        "price_usd": str(listing.price_usd), "handover_details": listing.handover_details,
        "warranty_available": bool(listing.warranty_available), "insurance_available": bool(listing.insurance_available),
        **disclosures(listing),
    }


# ---------------------------------------------------------------- private file storage

def _storage_dir() -> str:
    path = settings.MARKETPLACE_STORAGE_DIR
    os.makedirs(path, mode=0o700, exist_ok=True)
    return path


def file_path(listing: MarketListing) -> str:
    if not listing.file_storage_key:
        raise LookupError("No file")
    path = os.path.join(_storage_dir(), listing.file_storage_key)
    if not os.path.isfile(path):
        raise LookupError("No file")
    return path


def store_file(db: Session, listing: MarketListing, *, seller_user_id: int, filename: str,
               stream: BinaryIO) -> MarketListing:
    """Store (or replace) a digital listing's file. Type by extension, 50 MB at most."""
    _own(listing, seller_user_id)
    if listing.kind != DIGITAL:
        raise ListingError("Only a digital listing has a file")
    name = os.path.basename((filename or "").replace("\\", "/")).strip()[:200]
    ext = os.path.splitext(name)[1].lower()
    if not name or ext not in FILE_TYPES:
        raise ListingError(f"The file must be one of: {', '.join(sorted(FILE_TYPES))}")
    key = secrets.token_hex(20)
    target = os.path.join(_storage_dir(), key)
    digest, size = hashlib.sha256(), 0
    try:
        with open(target, "xb") as out:
            while chunk := stream.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_FILE_BYTES:
                    raise ListingError("The file is larger than 50 MB")
                digest.update(chunk)
                out.write(chunk)
        if size == 0:
            raise ListingError("The file is empty")
    except BaseException:
        if os.path.exists(target):
            os.remove(target)
        raise
    # A replaced file is left in place (never deleted before the new key is committed).
    listing.file_storage_key, listing.file_name, listing.file_content_type = key, name, FILE_TYPES[ext]
    listing.file_size, listing.file_sha256 = size, digest.hexdigest()
    db.flush()
    return listing
