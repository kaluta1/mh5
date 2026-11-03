"""Marketplace read-only reconciliation (Prompt 7): sellers, listings, images, orders, custodian references and
the order ledger, against each other. Never writes; never repairs.

Every issue: type, record ids, expected, actual, suggestion, auto_fix_safe (always False: production data is
never repaired by this report) and owner_approval. A fingerprint of the main counts lets two runs be compared.
"""
from __future__ import annotations

import hashlib
import json
import os
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.services.financial_integrity import money

_FUNDED_STATES = ("FUNDS_HELD", "FULFILLED", "BUYER_CONFIRMED", "RELEASE_PENDING", "RELEASED", "DISPUTED",
                  "REFUND_PENDING", "REFUNDED")


def _issue(kind, expected, actual, suggestion, owner=True, **ids) -> dict:
    return {"type": kind, **ids, "expected": str(expected), "actual": str(actual), "suggestion": suggestion,
            "auto_fix_safe": False, "owner_approval": owner}


def _count(db: Session, column) -> dict:
    return {str(k): int(v) for k, v in db.query(column, func.count()).group_by(column).all()}


def _entry_total(entry) -> tuple:
    debit = sum((money(line.debit_amount or 0) for line in entry.lines), Decimal("0"))
    credit = sum((money(line.credit_amount or 0) for line in entry.lines), Decimal("0"))
    return money(debit), money(credit)


def report(db: Session, *, limit: int = 500, check_files: bool = True) -> dict:
    from app.models.business_model import (MarketListing, MarketListingImage, MarketOrder, MarketOrderRequest)
    from app.models.seller_verification import SellerApplication, SellerProfile
    from app.models.user import User
    from app.services import marketplace_listings as ml
    from app.services.new_model_ledger import PostingType, SourceType, find_entry, idempotency_key, is_reversed
    from app.services.new_model_reference_data import MARKETPLACE_MARKUP_RATE

    issues: list = []
    user_ids = {uid for (uid,) in db.query(User.id).all()}

    # ---- listings and images
    listings = db.query(MarketListing).order_by(MarketListing.id).all()
    for listing in listings:
        if int(listing.seller_user_id) not in user_ids:
            issues.append(_issue("LISTING_SELLER_MISSING", "an existing seller account", listing.seller_user_id,
                                 "Review the listing ownership", listing_id=listing.id))
        if listing.status == ml.PUBLISHED and listing.kind == ml.DIGITAL and not listing.file_storage_key:
            issues.append(_issue("PUBLISHED_DIGITAL_WITHOUT_FILE", "a stored file", None,
                                 "Unpublish until the seller uploads the file", listing_id=listing.id))
        if check_files and listing.file_storage_key:
            try:
                ml.file_path(listing)
            except LookupError:
                issues.append(_issue("DIGITAL_FILE_MISSING", listing.file_storage_key, None,
                                     "Restore the file from backup or ask the seller to upload it again",
                                     listing_id=listing.id))
    listing_ids = {l.id for l in listings}
    images = db.query(MarketListingImage).all()
    for image in images:
        if image.listing_id not in listing_ids:
            issues.append(_issue("ORPHAN_IMAGE_ROW", "an existing listing", image.listing_id, "Review", image_id=image.id))
        elif check_files:
            try:
                ml.image_path(image)
            except LookupError:
                issues.append(_issue("IMAGE_FILE_MISSING", image.storage_key, None, "Ask the seller to upload it again",
                                     owner=False, image_id=image.id, listing_id=image.listing_id))
    orphan_files = 0
    if check_files:
        try:
            image_dir = os.path.join(ml._storage_dir(), "images")
            known = {i.storage_key for i in images}
            orphan_files = sum(1 for name in (os.listdir(image_dir) if os.path.isdir(image_dir) else []) if name not in known)
        except OSError:
            orphan_files = -1
        if orphan_files > 0:
            issues.append(_issue("ORPHAN_IMAGE_FILES", 0, orphan_files,
                                 "Informational: image files without a database row (left by an interrupted upload)",
                                 owner=False))

    # ---- orders
    orders = db.query(MarketOrder).order_by(MarketOrder.id).all()
    pending_by_buyer_item: dict = {}
    for o in orders:
        base, markup, total = money(o.seller_base_amount), money(o.markup_amount), money(o.buyer_total_amount)
        if money(base + markup) != total:
            issues.append(_issue("ORDER_TOTAL_MISMATCH", money(base + markup), total, "Review the order pricing",
                                 order_id=o.id))
        if Decimal(str(o.markup_rate)) == MARKETPLACE_MARKUP_RATE and money(base * MARKETPLACE_MARKUP_RATE) != markup:
            issues.append(_issue("ORDER_MARKUP_MISMATCH", money(base * MARKETPLACE_MARKUP_RATE), markup,
                                 "Review the order pricing", order_id=o.id))
        if o.buyer_user_id == o.seller_user_id:
            issues.append(_issue("ORDER_SELF_PURCHASE", "buyer different from seller", o.buyer_user_id, "Review",
                                 order_id=o.id))
        if o.item_type == "listing" and o.item_id not in listing_ids:
            issues.append(_issue("ORDER_LISTING_MISSING", "an existing listing", o.item_id, "Review", order_id=o.id))
        if o.state == "PAYMENT_PENDING":
            pending_by_buyer_item.setdefault((o.buyer_user_id, o.item_type, o.item_id), []).append(o.id)

        funded = find_entry(db, idempotency_key(SourceType.MARKET_ORDER, o.id, PostingType.CUSTODY_FUNDED))
        released = find_entry(db, idempotency_key(SourceType.MARKET_ORDER, o.id, PostingType.CUSTODY_RELEASED))
        settled = find_entry(db, idempotency_key(SourceType.MARKET_ORDER, o.id, PostingType.MARKUP_SETTLED))
        if o.state in _FUNDED_STATES:
            if not o.custodian_reference:
                issues.append(_issue("FUNDED_WITHOUT_CUSTODIAN_REFERENCE", "a custodian reference", None,
                                     "Obtain the reference from the custodian statement", order_id=o.id))
            if funded is None:
                issues.append(_issue("FUNDED_WITHOUT_LEDGER_ENTRY", "CUSTODY_FUNDED entry", None,
                                     "Review against the custodian statement", order_id=o.id))
            else:
                debit, credit = _entry_total(funded)
                if debit != credit or debit != total:
                    issues.append(_issue("FUNDED_ENTRY_MISMATCH", total, f"{debit}/{credit}", "Review the ledger",
                                         order_id=o.id, journal_entry_id=funded.id))
        elif funded is not None:
            issues.append(_issue("LEDGER_ENTRY_FOR_UNPAID_ORDER", "no CUSTODY_FUNDED entry", funded.id, "Review",
                                 order_id=o.id))
        if o.state == "RELEASED":
            if released is None:
                issues.append(_issue("RELEASED_WITHOUT_LEDGER_ENTRY", "CUSTODY_RELEASED entry", None, "Review",
                                     order_id=o.id))
            else:
                debit, credit = _entry_total(released)
                if debit != credit or debit != total:
                    issues.append(_issue("RELEASED_ENTRY_MISMATCH", total, f"{debit}/{credit}", "Review the ledger",
                                         order_id=o.id, journal_entry_id=released.id))
        elif released is not None:
            issues.append(_issue("RELEASE_ENTRY_FOR_UNRELEASED_ORDER", "no CUSTODY_RELEASED entry", o.state, "Review",
                                 order_id=o.id))
        if (o.markup_settled_at is not None) != (settled is not None):
            issues.append(_issue("MARKUP_SETTLEMENT_MISMATCH", "settled date and ledger entry together",
                                 f"date={o.markup_settled_at is not None} entry={settled is not None}", "Review",
                                 order_id=o.id))
        if o.state == "REFUNDED" and funded is not None and not is_reversed(db, funded):
            issues.append(_issue("REFUND_NOT_REVERSED", "a reversal of CUSTODY_FUNDED", None, "Review the ledger",
                                 order_id=o.id, journal_entry_id=funded.id))
        if o.state != "REFUNDED" and funded is not None and is_reversed(db, funded):
            issues.append(_issue("REVERSED_WITHOUT_REFUND", "REFUNDED state", o.state, "Review", order_id=o.id))
    for (buyer, item_type, item_id), ids in pending_by_buyer_item.items():
        if len(ids) > 1:
            issues.append(_issue("POSSIBLE_DUPLICATE_ORDERS", 1, len(ids),
                                 "Informational: the buyer has several unpaid orders for the same item", owner=False,
                                 order_ids=ids, buyer_user_id=buyer))

    open_requests = db.query(MarketOrderRequest).filter(MarketOrderRequest.status == "OPEN").all()
    states = {o.id: o.state for o in orders}
    for req in open_requests:
        if states.get(req.order_id) not in ("FUNDS_HELD", "FULFILLED"):
            issues.append(_issue("OPEN_REQUEST_ON_CLOSED_ORDER", "FUNDS_HELD or FULFILLED", states.get(req.order_id),
                                 "Resolve the request", owner=False, request_id=req.id, order_id=req.order_id))

    counts = {
        "seller_profiles_by_status": _count(db, SellerProfile.status),
        "seller_applications_by_status": _count(db, SellerApplication.status),
        "listings_by_status": _count(db, MarketListing.status),
        "listings_by_kind": _count(db, MarketListing.kind),
        "listing_images": len(images),
        "orders_by_state": _count(db, MarketOrder.state),
        "open_requests": len(open_requests),
        "buyer_total_by_state": {str(s): str(money(t)) for s, t in db.query(
            MarketOrder.state, func.coalesce(func.sum(MarketOrder.buyer_total_amount), 0)).group_by(MarketOrder.state).all()},
    }
    fingerprint = hashlib.sha256(json.dumps(counts, sort_keys=True, default=str).encode()).hexdigest()[:16]
    return {"read_only": True, "counts": counts, "fingerprint": fingerprint, "issues": issues[:limit],
            "issue_count": len(issues), "ok": not [i for i in issues if i["owner_approval"]]}
