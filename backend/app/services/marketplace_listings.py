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
# Prompt 7: SUSPENDED is set and lifted by an administrator only; ARCHIVED is the seller's final retirement.
SUSPENDED, ARCHIVED = "SUSPENDED", "ARCHIVED"
CONDITIONS = ("NEW", "USED", "REFURBISHED")

MIN_PRICE, MAX_PRICE = Decimal("1.00"), Decimal("100000.00")
MAX_FILE_BYTES = 50 * 1024 * 1024
FILE_TYPES = {".pdf": "application/pdf", ".epub": "application/epub+zip", ".zip": "application/zip"}

WARRANTY_NONE = "No warranty is offered by the seller."
INSURANCE_NONE = "No insurance is offered with this item."
CONSUMER_RIGHTS = ("Your statutory consumer rights are not affected. MyHigh5 support can still refund an order "
                   "that was not handed over, a duplicate charge, a payment failure or a fraudulent sale.")

EDITABLE = ("kind", "title", "description", "price_usd", "quantity_available", "handover_details",
            "warranty_available", "warranty_terms", "insurance_available", "insurance_terms", "category",
            "item_condition")


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
    if listing.status in (SUSPENDED, ARCHIVED):
        raise ListingError(f"A {listing.status.lower()} listing cannot be edited")
    merged = {f: getattr(listing, f) for f in EDITABLE}
    merged.update(data)
    kind = merged["kind"]
    if kind not in KINDS:
        raise ListingError(f"kind must be one of {', '.join(KINDS)}")
    category = (merged["category"] or "").strip().upper() or None
    if category is not None and category not in _categories():
        raise ListingError("category must be one of the marketplace product categories")
    condition = (merged["item_condition"] or "").strip().upper() or None
    if condition is not None and (kind != PHYSICAL or condition not in CONDITIONS):
        raise ListingError(f"item_condition applies to physical products only and must be one of {', '.join(CONDITIONS)}")
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
    listing.category, listing.item_condition = category, condition


def _categories() -> tuple:
    from app.services.seller_verification_rules import PRODUCT_CATEGORIES

    return PRODUCT_CATEGORIES


def record_event(db: Session, listing: MarketListing, *, action: str, from_status: Optional[str],
                 actor_user_id: Optional[int], actor_role: str, reason: Optional[str] = None) -> None:
    """Append-only listing history (seller status changes and administrator moderation)."""
    from app.models.business_model import MarketListingEvent

    db.add(MarketListingEvent(listing_id=listing.id, from_status=from_status, to_status=listing.status, action=action,
                              actor_user_id=actor_user_id, actor_role=actor_role,
                              reason=reason[:1000] if reason else None))
    db.flush()


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
                            price_usd=None, category=None, item_condition=None)
    _apply(listing, data)
    db.add(listing)
    db.flush()
    record_event(db, listing, action="CREATED", from_status=None, actor_user_id=seller_user_id, actor_role="SELLER")
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
    if listing.status == SUSPENDED:
        raise ListingError("This listing was suspended by MyHigh5 and cannot be published. Please contact support.")
    if listing.status == ARCHIVED:
        raise ListingError("An archived listing cannot be published again; create a new listing")
    if listing.kind == DIGITAL and not listing.file_storage_key:
        raise ListingError("Upload the digital file before publishing")
    if listing.kind in (PHYSICAL, SERVICE) and not listing.handover_details:
        raise ListingError("Describe how the product or service is handed over before publishing")
    if content_safety.detect_text_harm(f"{listing.title}\n{listing.description}", possibly_minor=False):
        raise ListingError("This listing cannot be published as written. Please contact MyHigh5 support.")
    # Publishing and relisting need an approved seller while seller verification is enforced.
    seller_verification.require_can_sell(db, listing.seller_user_id)
    # A regulated category is sold only by a seller whose approved registration declared it (and so was
    # reviewed by a person). Checked only while seller verification is enforced.
    seller_verification.require_category_allowed(db, listing.seller_user_id, listing.category)
    # The seller will receive value: the same eligibility as any seller payout (Phase 10).
    seller = db.query(User).filter(User.id == listing.seller_user_id).first()
    fe.require(db, seller, fe.FinancialOperation.WITHDRAWAL, subject={"market_listing_id": int(listing.id)})
    if listing.status != PUBLISHED:
        before = listing.status
        listing.status = PUBLISHED
        listing.published_at = datetime.utcnow()
        record_event(db, listing, action="PUBLISHED", from_status=before, actor_user_id=seller_user_id,
                     actor_role="SELLER")
    db.flush()
    return listing


def unpublish(db: Session, listing: MarketListing, *, seller_user_id: int) -> MarketListing:
    """Stops new orders; existing orders (and paid buyers' downloads) are unaffected."""
    _own(listing, seller_user_id)
    if listing.status == PUBLISHED:
        listing.status = UNPUBLISHED
        record_event(db, listing, action="UNPUBLISHED", from_status=PUBLISHED, actor_user_id=seller_user_id,
                     actor_role="SELLER")
    db.flush()
    return listing


def archive(db: Session, listing: MarketListing, *, seller_user_id: int) -> MarketListing:
    """The seller retires a listing for good (stops new orders; existing orders and downloads unaffected).
    A suspended listing stays with MyHigh5 support."""
    _own(listing, seller_user_id)
    if listing.status == SUSPENDED:
        raise ListingError("This listing was suspended by MyHigh5; contact support")
    if listing.status != ARCHIVED:
        before = listing.status
        listing.status = ARCHIVED
        record_event(db, listing, action="ARCHIVED", from_status=before, actor_user_id=seller_user_id,
                     actor_role="SELLER")
    db.flush()
    return listing


MODERATION_ACTIONS = ("suspend", "restore")


def moderate(db: Session, listing: MarketListing, *, admin_user_id: int, action: str, reason: str,
             seller_message: Optional[str] = None) -> MarketListing:
    """An administrator suspends a listing (any state but archived) or lifts a suspension. A lifted listing
    returns UNPUBLISHED: the seller publishes it again, which re-runs every publishing check. Nothing is
    ever published by an administrator. Existing orders are never touched."""
    if action not in MODERATION_ACTIONS:
        raise ListingError("Unknown moderation action")
    reason = (reason or "").strip()
    if len(reason) < 5:
        raise ListingError("Record a reason (at least 5 characters)")
    if int(listing.seller_user_id) == int(admin_user_id):
        raise ListingError("An administrator cannot moderate their own listing")
    before = listing.status
    if action == "suspend":
        if before == SUSPENDED:
            raise ListingError("This listing is already suspended")
        if before == ARCHIVED:
            raise ListingError("An archived listing is not offered; nothing to suspend")
        message = (seller_message or "").strip()
        if len(message) < 5:
            raise ListingError("A message for the seller is required (at least 5 characters)")
        listing.status, listing.moderation_note = SUSPENDED, message[:500]
        _notify(db, listing.seller_user_id, "Marketplace listing suspended",
                f'Your listing "{listing.title}" was suspended by MyHigh5: {message[:500]} '
                "Existing orders are not affected.")
    else:
        if before != SUSPENDED:
            raise ListingError("Only a suspended listing can be restored")
        listing.status, listing.moderation_note = UNPUBLISHED, None
        _notify(db, listing.seller_user_id, "Marketplace listing restored",
                f'Your listing "{listing.title}" may be published again from your dashboard.')
    record_event(db, listing, action=action.upper(), from_status=before, actor_user_id=admin_user_id,
                 actor_role="ADMIN", reason=reason)
    db.flush()
    return listing


def _notify(db: Session, user_id: int, title: str, message: str) -> None:
    from app.models.notification import Notification, NotificationType

    db.add(Notification(user_id=user_id, type=NotificationType.SYSTEM, title=title[:255], message=message[:2000]))
    db.flush()


def history(db: Session, listing: MarketListing) -> list:
    from app.models.business_model import MarketListingEvent

    rows = (db.query(MarketListingEvent).filter(MarketListingEvent.listing_id == listing.id)
            .order_by(MarketListingEvent.id).all())
    return [{"action": e.action, "from": e.from_status, "to": e.to_status, "by": e.actor_role,
             "at": e.created_at.isoformat() + "Z" if e.created_at else None} for e in rows]


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
        "category": listing.category, "item_condition": listing.item_condition,
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


# ---------------------------------------------------------------- listing images (Prompt 7)

MAX_IMAGES = 8
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000          # decompression-bomb guard
MAX_IMAGE_SIDE = 2000                  # stored images are scaled down to this
IMAGE_FORMATS = {"JPEG": ("image/jpeg", "JPEG"), "PNG": ("image/png", "PNG"), "WEBP": ("image/webp", "WEBP")}


def _image_dir() -> str:
    path = os.path.join(_storage_dir(), "images")
    os.makedirs(path, mode=0o700, exist_ok=True)
    return path


def images(db: Session, listing: MarketListing) -> list:
    from app.models.business_model import MarketListingImage

    return (db.query(MarketListingImage).filter(MarketListingImage.listing_id == listing.id)
            .order_by(MarketListingImage.position, MarketListingImage.id).all())


def add_image(db: Session, listing: MarketListing, *, seller_user_id: int, stream: BinaryIO):
    """Validate by CONTENT (never the file name or the browser's type), then re-encode: the stored image
    has no metadata (location, camera) and cannot carry a script or a second file."""
    import io

    from PIL import Image, UnidentifiedImageError

    from app.models.business_model import MarketListingImage

    _own(listing, seller_user_id)
    if listing.status in (SUSPENDED, ARCHIVED):
        raise ListingError(f"A {listing.status.lower()} listing cannot be changed")
    if len(images(db, listing)) >= MAX_IMAGES:
        raise ListingError(f"A listing has at most {MAX_IMAGES} images")
    raw = stream.read(MAX_IMAGE_BYTES + 1)
    if len(raw) > MAX_IMAGE_BYTES:
        raise ListingError("The image is larger than 5 MB")
    if not raw:
        raise ListingError("The image is empty")
    try:
        with Image.open(io.BytesIO(raw)) as probe:
            fmt = probe.format
            if fmt not in IMAGE_FORMATS:
                raise ListingError("The image must be a JPEG, PNG or WebP picture")
            if probe.width * probe.height > MAX_IMAGE_PIXELS:
                raise ListingError("The image has too many pixels")
            probe.verify()
        with Image.open(io.BytesIO(raw)) as img:
            img.load()
            img = img.convert("RGBA" if fmt in ("PNG", "WEBP") and img.mode in ("RGBA", "LA", "P") else "RGB")
            img.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
            out = io.BytesIO()
            img.save(out, IMAGE_FORMATS[fmt][1], **({"quality": 85} if fmt in ("JPEG", "WEBP") else {}))
            width, height = img.size
    except ListingError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise ListingError("The file is not a valid JPEG, PNG or WebP picture") from None
    data = out.getvalue()
    key = secrets.token_hex(20)
    with open(os.path.join(_image_dir(), key), "xb") as f:
        f.write(data)
    position = max([i.position for i in images(db, listing)] or [-1]) + 1
    image = MarketListingImage(listing_id=listing.id, storage_key=key, content_type=IMAGE_FORMATS[fmt][0], width=width,
                               height=height, size=len(data), sha256=hashlib.sha256(data).hexdigest(), position=position)
    db.add(image)
    db.flush()
    return image


def remove_image(db: Session, listing: MarketListing, *, seller_user_id: int, image_id: int) -> None:
    from app.models.business_model import MarketListingImage

    _own(listing, seller_user_id)
    if listing.status in (SUSPENDED, ARCHIVED):
        raise ListingError(f"A {listing.status.lower()} listing cannot be changed")
    image = (db.query(MarketListingImage)
             .filter(MarketListingImage.id == image_id, MarketListingImage.listing_id == listing.id).first())
    if image is None:
        raise LookupError("Image not found")
    key = image.storage_key
    db.delete(image)
    db.flush()
    path = os.path.join(_image_dir(), key)
    if os.path.isfile(path):          # the row is gone; a file left behind is reported by reconciliation
        os.remove(path)


def image_path(image) -> str:
    path = os.path.join(_image_dir(), image.storage_key)
    if not os.path.isfile(path):
        raise LookupError("No image")
    return path


def publicly_visible(db: Session, listing: Optional[MarketListing]) -> bool:
    """What a buyer may see: a published listing of a seller allowed to sell now."""
    from app.services import seller_verification

    return listing is not None and listing.status == PUBLISHED and seller_verification.can_sell(db, listing.seller_user_id)
