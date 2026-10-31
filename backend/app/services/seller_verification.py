"""Marketplace seller registration and verification.

Separate from member KYC: it reuses an APPROVED member KYC as the identity check and never charges a
fee, changes KYC, commissions, the Referral Pool, payouts or settlement.

What approval means: permission to sell on MyHigh5. It is never government business registration, tax
registration, incorporation or a product licence. Public labels say only what MyHigh5 checked.

Application states: DRAFT -> SUBMITTED -> CHECKS_IN_PROGRESS -> (ACTION_REQUIRED | MANUAL_REVIEW_REQUIRED
| APPROVED); a person may then APPROVE, REJECT or ask for corrections; an approved seller may be
RESTRICTED or asked to REVERIFY. A change after approval is a new application (the approval stands
until the new one is decided). Automatic approval happens only when every required check PASSED from
verified evidence and nothing needs a person; a provider failure or timeout never approves.

Enforcement (publishing, relisting, editing a live listing, new orders) applies only while
MARKETPLACE_SELLER_VERIFICATION_ENABLED is on. Drafts are always allowed. Existing orders, refunds,
downloads, balances and records are never touched.
"""
from __future__ import annotations

import base64
import hashlib
import os
import secrets
from datetime import date, datetime, timedelta
from decimal import ROUND_DOWN, Decimal
from typing import BinaryIO, Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.seller_verification import (
    SellerApplication,
    SellerApplicationEvent,
    SellerClassificationReview,
    SellerDocument,
    SellerFxRate,
    SellerProfile,
    SellerProviderEvent,
    SellerVerificationCheck,
)
from app.services import seller_verification_providers as prov
from app.services import seller_verification_rules as rules

DRAFT, SUBMITTED, CHECKS_IN_PROGRESS = "DRAFT", "SUBMITTED", "CHECKS_IN_PROGRESS"
ACTION_REQUIRED, MANUAL_REVIEW_REQUIRED = "ACTION_REQUIRED", "MANUAL_REVIEW_REQUIRED"
APPROVED, REJECTED, RESTRICTED = "APPROVED", "REJECTED", "RESTRICTED"
REVERIFICATION_REQUIRED, SUPERSEDED, NONE = "REVERIFICATION_REQUIRED", "SUPERSEDED", "NONE"
EDITABLE_STATUSES = (DRAFT, ACTION_REQUIRED)
OPEN_STATUSES = (DRAFT, SUBMITTED, CHECKS_IN_PROGRESS, ACTION_REQUIRED, MANUAL_REVIEW_REQUIRED)

PRIVATE, SOLE_TRADER, ORGANISATION = "PRIVATE", "SOLE_TRADER", "ORGANISATION"
CATEGORIES = (PRIVATE, SOLE_TRADER, ORGANISATION)
SOLE_TRADER_STRUCTURES = ("REGISTERED", "EXEMPT")
ORGANISATION_STRUCTURES = ("COMPANY", "PARTNERSHIP", "LLP", "ORGANISATION", "OTHER")
COMMERCIAL_INDICATORS = ("sells_new_stock", "buys_for_resale", "manufactures_for_sale", "regular_paid_services",
                         "regular_digital_products")
DOC_TYPES = ("REGISTRATION_CERTIFICATE", "EXEMPTION_EVIDENCE", "LICENCE", "AUTHORITY_LETTER", "OWNERSHIP", "ADDRESS",
             "OTHER")
DECLARATION_VERSION = "SELLER-DECLARATION-2026-10-31"
DECLARATION_TEXT = ("I declare that the information I have given is true and complete, that I will keep it up to "
                    "date, and that I understand MyHigh5 seller approval is permission to sell on MyHigh5 only. It is "
                    "not a government registration, tax registration or licence.")

LABEL_PRIVATE = "Private Seller"
LABEL_BUSINESS = "Business Seller — Checks Completed"
LABEL_EXEMPT = "Sole Trader — Registration Exemption Recorded"

MAX_PROVIDER_ATTEMPTS = 3
EXPIRY_REMINDER_DAYS = 30
BENEFICIARY_CHANGE_GRACE_DAYS = 14
DOCUMENT_RETENTION_DAYS = 730
MAX_DOCUMENT_BYTES = 10 * 1024 * 1024
DOCUMENT_TYPES = {".pdf": "application/pdf", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}

# Reasons the SELLER can fix (shown to them) and reasons only a PERSON can resolve (never shown).
SELLER_FIXABLE = {
    "MEMBER_KYC_NOT_APPROVED": "Complete your MyHigh5 member identity verification first (no extra fee).",
    "PAYOUT_DESTINATION_MISSING": "Add your payout destination in your account settings (confirmed with your password).",
    "EXEMPTION_EVIDENCE_MISSING": "Upload evidence supporting your registration exemption.",
    "LICENCE_DOCUMENT_MISSING": "Upload a copy of each licence you listed.",
}

# Fields whose change after approval needs reassessment.
MATERIAL_FIELDS = ("seller_category", "business_structure", "legal_name", "trading_name", "residence_country",
                   "establishment_country", "establishment_subdivision", "representative", "product_categories",
                   "registration_authority", "registration_number", "licences", "ownership", "exemption_basis")


class SellerError(ValueError):
    pass


class SellerNotEligible(Exception):
    """Selling (publishing, relisting, live edits, new orders) needs an approved seller."""

    code = "SELLER_NOT_APPROVED"
    message = ("Seller registration must be approved before you can publish. Your listing is kept as a draft. "
               "Open Marketplace > Seller registration.")


def enforcement_on() -> bool:
    return bool(settings.MARKETPLACE_SELLER_VERIFICATION_ENABLED)


# ---------------------------------------------------------------- profile / eligibility

def get_profile(db: Session, user_id: int, *, create: bool = False, lock: bool = False) -> Optional[SellerProfile]:
    q = db.query(SellerProfile).filter(SellerProfile.user_id == user_id)
    profile = (q.with_for_update() if lock else q).first()
    if profile is None and create:
        profile = SellerProfile(user_id=user_id, status=NONE)
        db.add(profile)
        db.flush()
    return profile


def profile_can_sell(profile: Optional[SellerProfile], now: Optional[datetime] = None) -> bool:
    if profile is None:
        return False
    if profile.status == APPROVED:
        return True
    now = now or datetime.utcnow()
    return profile.status == REVERIFICATION_REQUIRED and profile.reverify_due_at is not None and profile.reverify_due_at > now


def can_sell(db: Session, user_id: int) -> bool:
    """Seller eligibility. Always True while enforcement is off (behaviour unchanged)."""
    if not enforcement_on():
        return True
    return profile_can_sell(get_profile(db, user_id))


def require_can_sell(db: Session, user_id: int) -> None:
    if not can_sell(db, user_id):
        raise SellerNotEligible()


def eligible_sellers_filter(column):
    """SQL condition on a seller user-id column: True for sellers allowed to sell now."""
    now = datetime.utcnow()
    from sqlalchemy import select

    allowed = select(SellerProfile.user_id).where(or_(
        SellerProfile.status == APPROVED,
        and_(SellerProfile.status == REVERIFICATION_REQUIRED, SellerProfile.reverify_due_at > now)))
    return column.in_(allowed)


def public_label(profile: Optional[SellerProfile]) -> Optional[str]:
    return profile.public_label if profile_can_sell(profile) else None


def _label_for(app: SellerApplication) -> str:
    if app.seller_category == PRIVATE:
        return LABEL_PRIVATE
    if app.seller_category == SOLE_TRADER and app.business_structure == "EXEMPT":
        return LABEL_EXEMPT
    return LABEL_BUSINESS


def _beneficiary_fingerprint(db: Session, user_id: int) -> Optional[str]:
    from app.models.user import User

    user = db.query(User).filter(User.id == user_id).first()
    wallet = (getattr(user, "usdt_wallet_address", None) or "").strip().lower() if user else ""
    return hashlib.sha256(f"seller-beneficiary:{wallet}".encode()).hexdigest() if wallet else None


# ---------------------------------------------------------------- history / notifications

def _event(db: Session, app: SellerApplication, to_status: str, *, actor_user_id: Optional[int], actor_role: str,
           reason: Optional[str] = None, seller_message: Optional[str] = None, changes: Optional[dict] = None) -> None:
    db.add(SellerApplicationEvent(application_id=app.id, from_status=app.status, to_status=to_status,
                                  actor_user_id=actor_user_id, actor_role=actor_role, reason=reason,
                                  seller_message=seller_message, changes=changes))
    app.status = to_status
    db.flush()


def _notify(db: Session, user_id: int, title: str, message: str) -> None:
    """In-app notification. Never carries internal review reasons or fraud indicators."""
    from app.models.notification import Notification, NotificationType

    db.add(Notification(user_id=user_id, type=NotificationType.SYSTEM, title=title[:255], message=message))
    db.flush()


_STATUS_MESSAGES = {
    CHECKS_IN_PROGRESS: ("Seller registration: checks in progress", "Your seller registration was received. Some "
                         "checks are still in progress; we will tell you when they are finished."),
    MANUAL_REVIEW_REQUIRED: ("Seller registration: under review", "Your seller registration is being reviewed by the "
                             "MyHigh5 team. You can keep preparing draft listings."),
    APPROVED: ("Seller registration approved", "You can now publish listings on the MyHigh5 Marketplace. MyHigh5 "
               "approval is permission to sell on MyHigh5 only; it is not a government registration or licence."),
}


# ---------------------------------------------------------------- application (seller)

def _clean(value, field: str, *, high: int, required: bool = False) -> Optional[str]:
    value = (value or "").strip() if isinstance(value, str) or value is None else str(value).strip()
    if not value:
        if required:
            raise SellerError(f"{field} is required")
        return None
    if len(value) > high:
        raise SellerError(f"{field} must be at most {high} characters")
    return value


def _country(value, field: str) -> Optional[str]:
    value = (value or "").strip().upper()
    if not value:
        return None
    if len(value) != 2 or not value.isalpha():
        raise SellerError(f"{field} must be a two-letter country code")
    return value


def _encrypt_text(value: str) -> str:
    return base64.b64encode(_seal(value.encode())).decode()


def _apply_fields(app: SellerApplication, data: dict) -> None:
    category = data.get("seller_category", app.seller_category)
    if category not in CATEGORIES:
        raise SellerError(f"seller_category must be one of {', '.join(CATEGORIES)}")
    app.seller_category = category
    if "business_structure" in data:
        structure = (data.get("business_structure") or "").strip().upper() or None
        allowed = {SOLE_TRADER: SOLE_TRADER_STRUCTURES, ORGANISATION: ORGANISATION_STRUCTURES}.get(category, ())
        if structure and structure not in allowed:
            raise SellerError(f"business_structure must be one of {', '.join(allowed) or 'none for a private seller'}")
        app.business_structure = structure
    if category == PRIVATE:
        app.business_structure = None
    texts = {"legal_name": 200, "trading_name": 160, "business_address": 1000, "contact_phone": 30,
             "products_description": 2000, "registration_authority": 160, "registration_number": 60,
             "exemption_basis": 2000, "establishment_subdivision": 20}
    for field, high in texts.items():
        if field in data:
            setattr(app, field, _clean(data[field], field, high=high))
    for field in ("residence_country", "establishment_country"):
        if field in data:
            setattr(app, field, _country(data[field], field))
    if "customer_markets" in data:
        app.customer_markets = sorted({_country(c, "customer_markets") for c in (data["customer_markets"] or []) if c})
    if "product_categories" in data:
        cats = sorted({str(c).upper() for c in (data["product_categories"] or [])})
        bad = [c for c in cats if c not in rules.PRODUCT_CATEGORIES]
        if bad:
            raise SellerError(f"Unknown product category: {bad[0]}")
        app.product_categories = cats
    if "commercial_indicators" in data:
        app.commercial_indicators = {k: bool((data["commercial_indicators"] or {}).get(k)) for k in COMMERCIAL_INDICATORS}
    if "tax_registered" in data:
        app.tax_registered = None if data["tax_registered"] is None else bool(data["tax_registered"])
    if "tax_identifier" in data:
        tax_id = _clean(data["tax_identifier"], "tax_identifier", high=40)
        if tax_id:
            app.tax_identifier_encrypted, app.tax_identifier_last4 = _encrypt_text(tax_id), tax_id[-4:]
        else:
            app.tax_identifier_encrypted = app.tax_identifier_last4 = None
    if "licences" in data:
        licences = []
        for item in (data["licences"] or [])[:20]:
            expires = item.get("expires_on") or None
            if expires:
                try:
                    expires = date.fromisoformat(str(expires)).isoformat()
                except ValueError:
                    raise SellerError("licences.expires_on must be a date (YYYY-MM-DD)") from None
            licences.append({"type": _clean(item.get("type"), "licences.type", high=120, required=True),
                             "authority": _clean(item.get("authority"), "licences.authority", high=160, required=True),
                             "number": _clean(item.get("number"), "licences.number", high=80, required=True),
                             "expires_on": expires})
        app.licences = licences
    if "representative" in data:
        rep = data["representative"] or {}
        app.representative = {"full_name": _clean(rep.get("full_name"), "representative.full_name", high=200),
                              "role": _clean(rep.get("role"), "representative.role", high=120)} if rep else None
    if "ownership" in data:
        owners = []
        for item in (data["ownership"] or [])[:25]:
            try:
                pct = Decimal(str(item.get("percent")))
            except Exception:  # noqa: BLE001
                raise SellerError("ownership.percent must be a number") from None
            if not (Decimal("0") < pct <= Decimal("100")):
                raise SellerError("ownership.percent must be above 0 and at most 100")
            owners.append({"full_name": _clean(item.get("full_name"), "ownership.full_name", high=200, required=True),
                           "percent": str(pct)})
        app.ownership = owners


def _open_application(db: Session, user_id: int, *, lock: bool = False) -> Optional[SellerApplication]:
    q = db.query(SellerApplication).filter(SellerApplication.user_id == user_id,
                                           SellerApplication.status.in_(OPEN_STATUSES))
    return (q.with_for_update() if lock else q).order_by(SellerApplication.id.desc()).first()


def latest_application(db: Session, user_id: int) -> Optional[SellerApplication]:
    return db.query(SellerApplication).filter(SellerApplication.user_id == user_id) \
        .order_by(SellerApplication.id.desc()).first()


def save_draft(db: Session, *, user_id: int, data: dict) -> SellerApplication:
    """Create or update the member's editable application (draft or correction). After an approval a new
    application starts from the approved details; the approval stands until the new one is decided."""
    profile = get_profile(db, user_id, create=True, lock=True)
    app = _open_application(db, user_id, lock=True)
    if app is not None and app.status not in EDITABLE_STATUSES:
        raise SellerError("Your application is being checked and cannot be changed right now")
    if app is None:
        approved = db.get(SellerApplication, profile.approved_application_id) if profile.approved_application_id else None
        if profile.status == RESTRICTED:
            raise SellerError("Selling is restricted on this account. You can appeal the restriction instead.")
        app = SellerApplication(user_id=user_id, status=DRAFT, seller_category=data.get("seller_category") or PRIVATE)
        if approved is not None:
            for field in MATERIAL_FIELDS + ("customer_markets", "business_address", "contact_phone", "products_description",
                                            "commercial_indicators", "tax_registered", "tax_identifier_encrypted",
                                            "tax_identifier_last4"):
                setattr(app, field, getattr(approved, field))
            app.supersedes_application_id = approved.id
        db.add(app)
        db.flush()
        db.add(SellerApplicationEvent(application_id=app.id, from_status=None, to_status=DRAFT, actor_user_id=user_id,
                                      actor_role="SELLER", reason="Application started"))
    _apply_fields(app, data)
    app.declaration_accepted_at = app.declaration_version = None   # any change needs a fresh declaration
    if profile.approved_application_id is None and profile.status in (NONE, DRAFT, REJECTED, ACTION_REQUIRED):
        profile.status = app.status
        profile.seller_category = app.seller_category
    db.flush()
    return app


def missing_fields(app: SellerApplication) -> list[str]:
    """What the seller must provide before submitting (only what applies to their category)."""
    need = ["legal_name", "residence_country"]
    if app.seller_category != PRIVATE:
        need += ["trading_name", "establishment_country", "business_address", "contact_phone", "business_structure",
                 "product_categories"]
        if app.business_structure != "EXEMPT":
            need += ["registration_authority", "registration_number"]
        else:
            need += ["exemption_basis"]
        if app.tax_registered is None:
            need.append("tax_registered")
    if app.seller_category == ORGANISATION:
        need.append("representative")
    missing = [f for f in need if not getattr(app, f)]
    if app.seller_category == ORGANISATION and app.representative and not (app.representative or {}).get("full_name"):
        missing.append("representative")
    if app.tax_registered and not app.tax_identifier_encrypted:
        missing.append("tax_identifier")
    return missing


def submit(db: Session, *, user_id: int, declaration_version: str, accept_declaration: bool) -> SellerApplication:
    app = _open_application(db, user_id, lock=True)
    if app is None or app.status not in EDITABLE_STATUSES:
        raise SellerError("There is no application to submit")
    if not accept_declaration or declaration_version != DECLARATION_VERSION:
        raise SellerError("Please read and accept the current accuracy declaration")
    missing = missing_fields(app)
    if missing:
        raise SellerError(f"Please complete: {', '.join(missing)}")
    app.declaration_version, app.declaration_accepted_at = DECLARATION_VERSION, datetime.utcnow()
    app.submitted_at, app.correction_request = datetime.utcnow(), None
    for row in db.query(SellerVerificationCheck).filter_by(application_id=app.id).all():
        # the details may have changed: every check runs again on the submitted version
        row.status, row.result_code, row.external_reference, row.attempts, row.last_error = (
            prov.PENDING, None, None, 0, None)
    _event(db, app, SUBMITTED, actor_user_id=user_id, actor_role="SELLER", reason="Submitted")
    run_checks(db, app)
    return app


def appeal(db: Session, *, user_id: int, text: str) -> SellerApplication:
    """A rejected application, or a restricted approval, goes back to a person with the seller's appeal."""
    text = _clean(text, "appeal", high=3000, required=True)
    if len(text) < 20:
        raise SellerError("Please explain your appeal in at least 20 characters")
    profile = get_profile(db, user_id, lock=True)
    app = latest_application(db, user_id)
    if profile is not None and profile.status == RESTRICTED and profile.approved_application_id:
        app = db.get(SellerApplication, profile.approved_application_id)
    if app is None or app.status not in (REJECTED, RESTRICTED):
        raise SellerError("Only a rejected application or a selling restriction can be appealed")
    app.appeal_text = text
    app.review_reasons = sorted(set(app.review_reasons or []) | {"APPEAL"})
    _event(db, app, MANUAL_REVIEW_REQUIRED, actor_user_id=user_id, actor_role="SELLER", reason="Appeal submitted")
    _notify(db, user_id, "Seller appeal received", "Your appeal was received and will be reviewed by the MyHigh5 team.")
    return app


# ---------------------------------------------------------------- automated checks and evaluation

def required_checks(app: SellerApplication) -> list[str]:
    checks = [prov.IDENTITY]
    if app.seller_category != PRIVATE:
        checks.append(prov.PAYOUT_BENEFICIARY)
        if app.business_structure != "EXEMPT":
            checks.append(prov.BUSINESS_REGISTRY)
    if app.seller_category == ORGANISATION:
        checks.append(prov.REPRESENTATIVE)
    if app.licences:
        checks.append(prov.LICENCE)
    return checks


def _check_row(db: Session, app: SellerApplication, check_type: str) -> SellerVerificationCheck:
    row = db.query(SellerVerificationCheck).filter_by(application_id=app.id, check_type=check_type).first()
    if row is None:
        provider = prov.provider_for(check_type)
        row = SellerVerificationCheck(application_id=app.id, check_type=check_type, attempts=0,
                                      provider=provider.name if provider else "NONE_CONNECTED", status=prov.PENDING)
        db.add(row)
        db.flush()
    return row


def run_checks(db: Session, app: SellerApplication) -> SellerApplication:
    """Run (or retry) every required check that is not final, then evaluate. A provider error is a
    transient UNAVAILABLE (retried up to MAX_PROVIDER_ATTEMPTS); it never passes a check."""
    if app.status not in (SUBMITTED, CHECKS_IN_PROGRESS, MANUAL_REVIEW_REQUIRED):
        raise SellerError("Checks run only on a submitted application")
    if app.status == SUBMITTED:
        _event(db, app, CHECKS_IN_PROGRESS, actor_user_id=None, actor_role="SYSTEM")
    for check_type in required_checks(app):
        row = _check_row(db, app, check_type)
        if row.status in (prov.PASSED, prov.FAILED, prov.MANUAL):
            continue
        if row.status == prov.PENDING and row.external_reference:
            continue                                     # awaiting the provider's signed callback
        provider = prov.provider_for(check_type)
        if provider is None:
            row.provider, row.status, row.result_code = "NONE_CONNECTED", prov.UNAVAILABLE, "NO_PROVIDER_CONNECTED"
            continue
        row.provider, row.attempts = provider.name, int(row.attempts or 0) + 1
        try:
            result = provider.run(db, app)
        except Exception as exc:  # noqa: BLE001 - a provider failure is recorded, never treated as a pass
            row.status, row.result_code, row.last_error = prov.UNAVAILABLE, "PROVIDER_ERROR", type(exc).__name__[:200]
            continue
        row.status, row.result_code, row.last_error = result.status, result.result_code, None
        row.external_reference = result.external_reference or row.external_reference
        row.checked_at = datetime.utcnow()
    db.flush()
    return evaluate(db, app)


def retry_in_progress(db: Session) -> int:
    """Retry transient provider failures of applications still in checks (scheduled or by an admin)."""
    count = 0
    for app in db.query(SellerApplication).filter(SellerApplication.status == CHECKS_IN_PROGRESS).all():
        run_checks(db, app)
        count += 1
    return count


def _documents(db: Session, app: SellerApplication) -> list[SellerDocument]:
    return db.query(SellerDocument).filter(SellerDocument.application_id == app.id,
                                           SellerDocument.erased_at.is_(None)).all()


def evaluate(db: Session, app: SellerApplication, *, today: Optional[date] = None) -> SellerApplication:
    today = today or date.today()
    applicable = rules.applicable_rules(db, app, today=today)
    app.applicable_rules = [f"{r.rule_code}@v{r.version}" for r in applicable]
    checks = {c.check_type: c for c in db.query(SellerVerificationCheck).filter_by(application_id=app.id).all()}
    docs = _documents(db, app)
    fix, review, waiting = set(), set(), False

    for check_type in required_checks(app):
        row = checks.get(check_type)
        if row is None or row.status == prov.PENDING:
            waiting = True
        elif row.status == prov.FAILED:
            (fix if row.result_code in SELLER_FIXABLE else review).add(row.result_code or f"{check_type}_FAILED")
        elif row.status == prov.UNAVAILABLE:
            if row.result_code == "NO_PROVIDER_CONNECTED" or int(row.attempts or 0) >= MAX_PROVIDER_ATTEMPTS:
                review.add("PROVIDER_UNAVAILABLE" if row.result_code != "NO_PROVIDER_CONNECTED"
                           else f"{check_type}_NOT_AUTOMATED")
            else:
                waiting = True                               # retried later; truthful pending
        elif row.status == prov.MANUAL:
            review.add(f"{check_type}_MANUAL")

    if app.seller_category == SOLE_TRADER and app.business_structure == "EXEMPT":
        review.add("EXEMPTION_CLAIM")
        if not any(d.doc_type == "EXEMPTION_EVIDENCE" for d in docs):
            fix.add("EXEMPTION_EVIDENCE_MISSING")
    if app.licences and sum(1 for d in docs if d.doc_type == "LICENCE") < len(app.licences):
        fix.add("LICENCE_DOCUMENT_MISSING")
    for lic in app.licences or []:
        if lic.get("expires_on") and date.fromisoformat(lic["expires_on"]) < today:
            review.add("LICENCE_EXPIRED")
    if set(app.product_categories or []) & rules.REGULATED_CATEGORIES:
        review.add("REGULATED_ACTIVITY")
    if app.seller_category == PRIVATE and any((app.commercial_indicators or {}).values()):
        review.add("COMMERCIAL_ACTIVITY_INDICATED")
    if app.ownership:
        total = sum(Decimal(o["percent"]) for o in app.ownership)
        names = [prov.normalise_name(o["full_name"]) for o in app.ownership]
        if total > Decimal("100") or len(set(names)) != len(names):
            review.add("OWNERSHIP_CONFLICT")
    if not rules.establishment_supported(applicable, app):
        review.add("JURISDICTION_NOT_SUPPORTED")
    if app.seller_category != PRIVATE and docs:
        review.add("DOCUMENTS_REQUIRE_REVIEW")           # no document provider: authenticity needs a person
    if app.appeal_text:
        review.add("APPEAL")

    app.review_reasons = sorted(review | fix)
    if fix:
        target, message = ACTION_REQUIRED, " ".join(SELLER_FIXABLE[c] for c in sorted(fix))
        app.correction_request = message
    elif waiting:
        target, message = CHECKS_IN_PROGRESS, None
    elif review:
        target, message = MANUAL_REVIEW_REQUIRED, None
    else:
        target, message = APPROVED, None
    if target == APPROVED:
        _approve(db, app, actor_user_id=None, actor_role="SYSTEM", reason="Every applicable check passed")
        return app
    if target != app.status:
        _event(db, app, target, actor_user_id=None, actor_role="SYSTEM", reason=", ".join(app.review_reasons) or None,
               seller_message=message)
        title, text = _STATUS_MESSAGES.get(target, ("Seller registration: action required", message or ""))
        _notify(db, app.user_id, title, text)
    _sync_open_profile(db, app)
    return app


def _sync_open_profile(db: Session, app: SellerApplication) -> None:
    """Without an approval the profile mirrors the application; with one, the approval stands."""
    profile = get_profile(db, app.user_id, create=True)
    if profile.approved_application_id is None:
        profile.status, profile.seller_category = app.status, app.seller_category
    db.flush()


def _approve(db: Session, app: SellerApplication, *, actor_user_id: Optional[int], actor_role: str, reason: str) -> None:
    profile = get_profile(db, app.user_id, create=True, lock=True)
    previous = profile.approved_application_id
    if previous and previous != app.id:
        old = db.get(SellerApplication, previous)
        if old is not None and old.status in (APPROVED, REVERIFICATION_REQUIRED, RESTRICTED):
            _event(db, old, SUPERSEDED, actor_user_id=actor_user_id, actor_role=actor_role,
                   reason=f"Superseded by application {app.id}")
    app.decided_at, app.decided_by_user_id, app.decision_reason = datetime.utcnow(), actor_user_id, reason
    _event(db, app, APPROVED, actor_user_id=actor_user_id, actor_role=actor_role, reason=reason,
           seller_message=_STATUS_MESSAGES[APPROVED][1])
    profile.status, profile.seller_category = APPROVED, app.seller_category
    profile.public_label, profile.public_trading_name = _label_for(app), app.trading_name if app.seller_category != PRIVATE else None
    profile.approved_application_id, profile.approved_at = app.id, datetime.utcnow()
    profile.restricted_at = profile.reverify_due_at = None
    profile.beneficiary_fingerprint = _beneficiary_fingerprint(db, app.user_id)
    db.flush()
    _notify(db, app.user_id, *_STATUS_MESSAGES[APPROVED])


def apply_provider_callback(db: Session, *, provider_name: str, event_id: str, reference: str, outcome: str,
                            result_code: str) -> dict:
    """A signature-verified provider result, applied once per (provider, event id)."""
    if outcome not in (prov.PASSED, prov.FAILED):
        raise SellerError("outcome must be PASSED or FAILED")
    if db.query(SellerProviderEvent).filter_by(provider=provider_name, event_id=event_id).first():
        return {"duplicate": True}
    check = db.query(SellerVerificationCheck).filter_by(provider=provider_name, external_reference=reference) \
        .with_for_update().first()
    db.add(SellerProviderEvent(provider=provider_name, event_id=event_id, check_id=check.id if check else None,
                               outcome=outcome))
    db.flush()
    if check is None:
        return {"duplicate": False, "applied": False}
    if check.status == prov.PENDING:
        check.status, check.result_code, check.checked_at = outcome, (result_code or "")[:60] or None, datetime.utcnow()
        db.flush()
        app = db.get(SellerApplication, check.application_id)
        if app is not None and app.status == CHECKS_IN_PROGRESS:
            evaluate(db, app)
    return {"duplicate": False, "applied": True}


# ---------------------------------------------------------------- administration

ADMIN_ACTIONS = ("approve", "request_correction", "reject", "restrict", "request_reverification")
_ADMIN_FROM = {
    "approve": (SUBMITTED, CHECKS_IN_PROGRESS, MANUAL_REVIEW_REQUIRED, RESTRICTED, REVERIFICATION_REQUIRED),
    "request_correction": (SUBMITTED, CHECKS_IN_PROGRESS, MANUAL_REVIEW_REQUIRED),
    "reject": (SUBMITTED, CHECKS_IN_PROGRESS, MANUAL_REVIEW_REQUIRED, ACTION_REQUIRED),
    "restrict": (APPROVED, REVERIFICATION_REQUIRED, MANUAL_REVIEW_REQUIRED),
    "request_reverification": (APPROVED,),
}


def admin_decide(db: Session, app: SellerApplication, *, admin_user_id: int, action: str, reason: str,
                 seller_message: Optional[str] = None, grace_days: int = 0) -> SellerApplication:
    """A person's decision. The internal reason is required and kept for audit; the seller sees only
    seller_message (required where the seller must act or is refused)."""
    if action not in ADMIN_ACTIONS:
        raise SellerError("Unknown action")
    reason = _clean(reason, "reason", high=2000, required=True)
    if len(reason) < 5:
        raise SellerError("Please record a reason (at least 5 characters)")
    seller_message = _clean(seller_message, "seller_message", high=2000)
    if action in ("request_correction", "reject", "restrict", "request_reverification") and not seller_message:
        raise SellerError("A message for the seller is required")
    profile = get_profile(db, app.user_id, create=True, lock=True)
    if action == "restrict" and app.status == MANUAL_REVIEW_REQUIRED and profile.approved_application_id != app.id:
        raise SellerError("Only an approved seller can be restricted")
    if app.status not in _ADMIN_FROM[action]:
        raise SellerError(f"This application is {app.status}; it cannot be changed with '{action}'")

    if action == "approve":
        _approve(db, app, actor_user_id=admin_user_id, actor_role="ADMIN", reason=reason)
        return app
    app.decided_at, app.decided_by_user_id, app.decision_reason = datetime.utcnow(), admin_user_id, reason
    if action == "request_correction":
        app.correction_request = seller_message
        _event(db, app, ACTION_REQUIRED, actor_user_id=admin_user_id, actor_role="ADMIN", reason=reason,
               seller_message=seller_message)
        _sync_open_profile(db, app)
        _notify(db, app.user_id, "Seller registration: correction needed", seller_message)
    elif action == "reject":
        _event(db, app, REJECTED, actor_user_id=admin_user_id, actor_role="ADMIN", reason=reason,
               seller_message=seller_message)
        _sync_open_profile(db, app)
        _notify(db, app.user_id, "Seller registration not approved",
                f"{seller_message} You may appeal from Marketplace > Seller registration.")
    elif action == "restrict":
        _event(db, app, RESTRICTED, actor_user_id=admin_user_id, actor_role="ADMIN", reason=reason,
               seller_message=seller_message)
        profile.status, profile.restricted_at = RESTRICTED, datetime.utcnow()
        _notify(db, app.user_id, "Marketplace selling restricted",
                f"{seller_message} Your existing orders, balances and records are unaffected. You may appeal.")
    else:
        grace = max(0, min(int(grace_days or 0), 60))
        _event(db, app, REVERIFICATION_REQUIRED, actor_user_id=admin_user_id, actor_role="ADMIN", reason=reason,
               seller_message=seller_message)
        profile.status = REVERIFICATION_REQUIRED
        profile.reverify_due_at = datetime.utcnow() + timedelta(days=grace) if grace else None
        _notify(db, app.user_id, "Seller reverification required", seller_message)
    db.flush()
    return app


def resolve_classification_review(db: Session, review: SellerClassificationReview, *, admin_user_id: int,
                                  resolution: str, note: str) -> SellerClassificationReview:
    """REMAINS_PRIVATE | BUSINESS_ONBOARDING_REQUESTED. Business onboarding is a request, never a forced
    incorporation and never an automatic restriction."""
    if review.status != "OPEN":
        raise SellerError("This review is already resolved")
    if resolution not in ("REMAINS_PRIVATE", "BUSINESS_ONBOARDING_REQUESTED"):
        raise SellerError("Unknown resolution")
    note = _clean(note, "note", high=2000, required=True)
    review.status, review.resolution, review.resolution_note = "RESOLVED", resolution, note
    review.resolved_by_user_id, review.resolved_at = admin_user_id, datetime.utcnow()
    if resolution == "BUSINESS_ONBOARDING_REQUESTED":
        _notify(db, review.user_id, "Please register as a business seller",
                "Your recent marketplace activity suggests you may be selling as a business. Please complete "
                "\"Register as a Business Seller\" in Marketplace > Seller registration. A lawful business does not "
                "always need to be an incorporated company: sole traders and registration exemptions are supported.")
    db.flush()
    return review


# ---------------------------------------------------------------- private seller sales monitoring

COMPLETED_STATES = ("BUYER_CONFIRMED", "RELEASE_PENDING", "RELEASED")
# Seller sales only: KYC fees, subscriptions (club_subscription) and Referral Pool units are never MarketOrders
# of these types.
QUALIFYING_ITEM_TYPES = ("listing", "digital_product")
WINDOW_DAYS = 365
COMMERCIAL_STOCK_QUANTITY = 5
COMMERCIAL_REGULAR_LISTINGS = 3


def review_thresholds() -> tuple[Decimal, int]:
    return Decimal(settings.SELLER_PRIVATE_REVIEW_SALES_USD).quantize(Decimal("0.01")), int(
        settings.SELLER_PRIVATE_REVIEW_ORDER_COUNT)


def usd_rate(db: Session, currency: str, on: date) -> Optional[tuple[Decimal, str]]:
    if (currency or "USD").upper() == "USD":
        return Decimal("1"), "USD"
    row = db.query(SellerFxRate).filter(SellerFxRate.currency == currency.upper(), SellerFxRate.as_of <= on) \
        .order_by(SellerFxRate.as_of.desc()).first()
    return (Decimal(row.usd_per_unit), f"{row.currency}@{row.as_of.isoformat()}:{row.source}") if row else None


def rolling_sales(db: Session, user_id: int, *, now: Optional[datetime] = None) -> dict:
    """Completed paid seller sales in the rolling 12 months: one order = one transaction; the amount is the
    seller's item price (seller base, excluding MyHigh5's markup), converted to USD with a recorded rate.
    Cancelled, unpaid and refunded orders never count. (MyHigh5 marketplace refunds are whole-order; there is
    no partial refund to adjust today.)"""
    from app.models.business_model import MarketOrder

    now = now or datetime.utcnow()
    start = now - timedelta(days=WINDOW_DAYS)
    orders = db.query(MarketOrder).filter(
        MarketOrder.seller_user_id == user_id, MarketOrder.item_type.in_(QUALIFYING_ITEM_TYPES),
        MarketOrder.state.in_(COMPLETED_STATES), MarketOrder.refunded_at.is_(None),
        MarketOrder.confirmed_at.isnot(None), MarketOrder.confirmed_at > start, MarketOrder.confirmed_at <= now).all()
    total, count, rates, unconverted = Decimal("0.00"), 0, {}, []
    for o in orders:
        rate = usd_rate(db, o.currency, o.confirmed_at.date())
        if rate is None:
            unconverted.append(o.id)
            continue
        total += (Decimal(o.seller_base_amount) * rate[0]).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
        count += 1
        rates[o.currency] = rate[1]
    return {"window_start": start, "window_end": now, "sales_usd": total, "order_count": count, "fx_rates": rates,
            "unconverted_order_ids": unconverted}


def _commercial_signals(db: Session, user_id: int) -> list[str]:
    from app.models.business_model import MarketListing

    listings = db.query(MarketListing).filter(MarketListing.seller_user_id == user_id,
                                              MarketListing.status == "PUBLISHED").all()
    signals = []
    if any(l.kind == "PHYSICAL" and (l.quantity_available or 0) >= COMMERCIAL_STOCK_QUANTITY for l in listings):
        signals.append("STOCK_QUANTITY")
    if sum(1 for l in listings if l.kind == "SERVICE") >= COMMERCIAL_REGULAR_LISTINGS:
        signals.append("REGULAR_PAID_SERVICES")
    if sum(1 for l in listings if l.kind == "DIGITAL") >= COMMERCIAL_REGULAR_LISTINGS:
        signals.append("REGULAR_DIGITAL_PRODUCTS")
    return signals


def monitor_private_seller(db: Session, user_id: int, *, now: Optional[datetime] = None) -> Optional[SellerClassificationReview]:
    """Open at most one classification review at a time. Idempotent: the key names the seller, trigger,
    year and threshold multiple, so re-running never duplicates. It never restricts selling."""
    if db.query(SellerClassificationReview).filter_by(user_id=user_id, status="OPEN").first():
        return None
    now = now or datetime.utcnow()
    usd_limit, count_limit = review_thresholds()
    sales = rolling_sales(db, user_id, now=now)
    candidates = []
    if sales["sales_usd"] >= usd_limit:
        candidates.append(("SALES_AMOUNT", int(sales["sales_usd"] // usd_limit), {}))
    if sales["order_count"] >= count_limit:
        candidates.append(("ORDER_COUNT", sales["order_count"] // count_limit, {}))
    for signal in _commercial_signals(db, user_id):
        candidates.append(("COMMERCIAL_INDICATOR", signal, {"signal": signal}))
    for trigger, level, detail in candidates:
        key = f"{user_id}:{trigger}:{now.year}:{level}"
        if db.query(SellerClassificationReview).filter_by(idempotency_key=key).first():
            continue
        review = SellerClassificationReview(
            user_id=user_id, trigger=trigger, idempotency_key=key, window_start=sales["window_start"],
            window_end=sales["window_end"], qualifying_sales_usd=sales["sales_usd"],
            qualifying_order_count=sales["order_count"], fx_rates_used=sales["fx_rates"],
            detail={**detail, "unconverted_order_ids": sales["unconverted_order_ids"],
                    "thresholds": {"sales_usd": str(usd_limit), "order_count": count_limit},
                    "note": "Internal MyHigh5 review trigger, not a statutory registration threshold."},
            status="OPEN")
        db.add(review)
        db.flush()
        return review
    return None


def run_private_seller_monitoring(db: Session, *, now: Optional[datetime] = None) -> int:
    opened = 0
    for (user_id,) in db.query(SellerProfile.user_id).filter(SellerProfile.seller_category == PRIVATE).all():
        if monitor_private_seller(db, user_id, now=now) is not None:
            opened += 1
    return opened


# ---------------------------------------------------------------- continuing compliance

def _already(db: Session, app: SellerApplication, key: str) -> bool:
    return db.query(SellerApplicationEvent).filter_by(application_id=app.id, reason=key).first() is not None


def run_compliance_sweep(db: Session, *, today: Optional[date] = None) -> dict:
    """Expiry reminders, reverification on expired evidence or a changed payout destination, and retention
    of documents from rejected or superseded applications. Idempotent (each step is recorded once)."""
    today = today or date.today()
    out = {"reminders": 0, "reverification": 0, "erased": 0}
    for profile in db.query(SellerProfile).filter(SellerProfile.status == APPROVED).all():
        app = db.get(SellerApplication, profile.approved_application_id) if profile.approved_application_id else None
        if app is None:
            continue
        expiries = [(f"DOC:{d.id}", d.expires_on) for d in _documents(db, app) if d.expires_on]
        expiries += [(f"LIC:{i}", date.fromisoformat(l["expires_on"])) for i, l in enumerate(app.licences or [])
                     if l.get("expires_on")]
        expired = [k for k, d in expiries if d < today]
        if expired:
            _event(db, app, REVERIFICATION_REQUIRED, actor_user_id=None, actor_role="SYSTEM",
                   reason=f"EXPIRED:{','.join(expired)}", seller_message="A licence or document on file has expired.")
            profile.status, profile.reverify_due_at = REVERIFICATION_REQUIRED, None
            _notify(db, app.user_id, "Seller reverification required",
                    "A licence or document on file has expired. Please update your seller registration.")
            out["reverification"] += 1
            continue
        for key, expires in expiries:
            if expires - today <= timedelta(days=EXPIRY_REMINDER_DAYS):
                marker = f"EXPIRY_REMINDER:{key}:{expires.isoformat()}"
                if not _already(db, app, marker):
                    db.add(SellerApplicationEvent(application_id=app.id, from_status=app.status, to_status=app.status,
                                                  actor_role="SYSTEM", reason=marker))
                    _notify(db, app.user_id, "A seller document expires soon",
                            f"A licence or document on your seller registration expires on {expires.isoformat()}. "
                            "Please upload a renewed copy.")
                    out["reminders"] += 1
        if app.seller_category != PRIVATE and profile.beneficiary_fingerprint and \
                _beneficiary_fingerprint(db, profile.user_id) != profile.beneficiary_fingerprint:
            _event(db, app, REVERIFICATION_REQUIRED, actor_user_id=None, actor_role="SYSTEM",
                   reason="PAYOUT_BENEFICIARY_CHANGED", seller_message="Your payout destination changed.")
            profile.status = REVERIFICATION_REQUIRED
            profile.reverify_due_at = datetime.utcnow() + timedelta(days=BENEFICIARY_CHANGE_GRACE_DAYS)
            _notify(db, app.user_id, "Seller reverification required",
                    f"Your payout destination changed. Please confirm your seller registration within "
                    f"{BENEFICIARY_CHANGE_GRACE_DAYS} days to keep selling.")
            out["reverification"] += 1
    cutoff = datetime.utcnow() - timedelta(days=DOCUMENT_RETENTION_DAYS)
    stale = db.query(SellerDocument).join(SellerApplication, SellerApplication.id == SellerDocument.application_id) \
        .filter(SellerDocument.erased_at.is_(None), SellerApplication.status.in_((REJECTED, SUPERSEDED)),
                SellerApplication.decided_at < cutoff).all()
    for doc in stale:
        erase_document(db, doc)
        out["erased"] += 1
    db.flush()
    return out


# ---------------------------------------------------------------- private encrypted documents

def _key() -> bytes:
    secret = settings.SELLER_DOCUMENT_ENCRYPTION_KEY
    if not secret or len(secret) < 32:
        raise SellerError("Secure storage for seller documents is not available yet. Please try again later.")
    return hashlib.sha256(f"myhigh5-seller-documents:{secret}".encode()).digest()


def _seal(data: bytes) -> bytes:
    nonce = os.urandom(12)
    return nonce + AESGCM(_key()).encrypt(nonce, data, b"seller-v1")


def _open(blob: bytes) -> bytes:
    return AESGCM(_key()).decrypt(blob[:12], blob[12:], b"seller-v1")


def _storage_dir() -> str:
    path = settings.SELLER_DOCUMENT_STORAGE_DIR
    os.makedirs(path, mode=0o700, exist_ok=True)
    return path


def store_document(db: Session, *, user_id: int, doc_type: str, filename: str, stream: BinaryIO,
                   expires_on: Optional[date] = None) -> SellerDocument:
    app = _open_application(db, user_id, lock=True)
    if app is None or app.status not in EDITABLE_STATUSES:
        raise SellerError("Documents can be added only to a draft or to an application that needs a correction")
    if doc_type not in DOC_TYPES:
        raise SellerError(f"doc_type must be one of {', '.join(DOC_TYPES)}")
    name = os.path.basename((filename or "").replace("\\", "/")).strip()[:200]
    ext = os.path.splitext(name)[1].lower()
    if not name or ext not in DOCUMENT_TYPES:
        raise SellerError(f"The file must be one of: {', '.join(sorted(DOCUMENT_TYPES))}")
    data = stream.read(MAX_DOCUMENT_BYTES + 1)
    if len(data) > MAX_DOCUMENT_BYTES:
        raise SellerError("The file is larger than 10 MB")
    if not data:
        raise SellerError("The file is empty")
    sealed = _seal(data)
    key = secrets.token_hex(20)
    with open(os.path.join(_storage_dir(), key), "xb") as out:
        out.write(sealed)
    doc = SellerDocument(application_id=app.id, doc_type=doc_type, storage_key=key, file_name=name,
                         content_type=DOCUMENT_TYPES[ext], size=len(data), sha256=hashlib.sha256(data).hexdigest(),
                         expires_on=expires_on, uploaded_by_user_id=user_id)
    db.add(doc)
    db.flush()
    return doc


def read_document(doc: SellerDocument) -> bytes:
    if doc.erased_at is not None:
        raise LookupError("Document erased")
    path = os.path.join(_storage_dir(), doc.storage_key)
    if not os.path.isfile(path):
        raise LookupError("Document missing")
    with open(path, "rb") as f:
        return _open(f.read())


def erase_document(db: Session, doc: SellerDocument) -> None:
    path = os.path.join(_storage_dir(), doc.storage_key)
    if os.path.isfile(path):
        os.remove(path)
    doc.erased_at = datetime.utcnow()
    db.flush()


# ---------------------------------------------------------------- read models

def application_out(db: Session, app: SellerApplication, *, admin: bool = False) -> dict:
    """The seller's view (and, with admin=True, the reviewer's). Internal review reasons, check details and
    decision reasons are admin-only; the tax identifier is never returned in full."""
    out = {
        "id": app.id, "status": app.status, "seller_category": app.seller_category,
        "business_structure": app.business_structure, "legal_name": app.legal_name, "trading_name": app.trading_name,
        "residence_country": app.residence_country, "establishment_country": app.establishment_country,
        "establishment_subdivision": app.establishment_subdivision, "customer_markets": app.customer_markets or [],
        "business_address": app.business_address, "contact_phone": app.contact_phone,
        "product_categories": app.product_categories or [], "products_description": app.products_description,
        "commercial_indicators": app.commercial_indicators or {},
        "registration_authority": app.registration_authority, "registration_number": app.registration_number,
        "exemption_basis": app.exemption_basis, "tax_registered": app.tax_registered,
        "tax_identifier_masked": f"****{app.tax_identifier_last4}" if app.tax_identifier_last4 else None,
        "licences": app.licences or [], "representative": app.representative, "ownership": app.ownership or [],
        "declaration_accepted_at": _iso(app.declaration_accepted_at), "submitted_at": _iso(app.submitted_at),
        "decided_at": _iso(app.decided_at), "correction_request": app.correction_request,
        "missing_fields": missing_fields(app) if app.status in EDITABLE_STATUSES else [],
        "documents": [{"id": d.id, "doc_type": d.doc_type, "file_name": d.file_name, "size": d.size,
                       "expires_on": d.expires_on.isoformat() if d.expires_on else None} for d in _documents(db, app)],
        "history": [{"to_status": e.to_status, "at": _iso(e.created_at), "message": e.seller_message}
                    for e in _events(db, app) if e.seller_message or e.actor_role != "SYSTEM"],
    }
    if admin:
        out.update({
            "user_id": app.user_id, "applicable_rules": app.applicable_rules or [], "review_reasons": app.review_reasons or [],
            "decision_reason": app.decision_reason, "decided_by_user_id": app.decided_by_user_id,
            "appeal_text": app.appeal_text, "supersedes_application_id": app.supersedes_application_id,
            "checks": [{"check_type": c.check_type, "provider": c.provider, "status": c.status,
                        "result_code": c.result_code, "attempts": c.attempts, "last_error": c.last_error,
                        "external_reference": c.external_reference, "checked_at": _iso(c.checked_at)}
                       for c in db.query(SellerVerificationCheck).filter_by(application_id=app.id).all()],
            "events": [{"from_status": e.from_status, "to_status": e.to_status, "actor_role": e.actor_role,
                        "actor_user_id": e.actor_user_id, "reason": e.reason, "seller_message": e.seller_message,
                        "at": _iso(e.created_at)} for e in _events(db, app)],
            "previous_applications": [{"id": a.id, "status": a.status, "decided_at": _iso(a.decided_at),
                                       "decision_reason": a.decision_reason}
                                      for a in db.query(SellerApplication).filter(SellerApplication.user_id == app.user_id,
                                                                                  SellerApplication.id != app.id)
                                      .order_by(SellerApplication.id.desc()).limit(20).all()],
        })
    else:
        out["review_status_message"] = {
            CHECKS_IN_PROGRESS: "Checks are in progress.",
            MANUAL_REVIEW_REQUIRED: "Your application is with the MyHigh5 review team.",
        }.get(app.status)
    return out


def _events(db: Session, app: SellerApplication) -> list[SellerApplicationEvent]:
    return db.query(SellerApplicationEvent).filter_by(application_id=app.id).order_by(SellerApplicationEvent.id).all()


def _iso(value) -> Optional[str]:
    return value.isoformat() + "Z" if value else None


def status_out(db: Session, user_id: int) -> dict:
    profile = get_profile(db, user_id)
    app = _open_application(db, user_id) or latest_application(db, user_id)
    return {
        "enforcement_enabled": enforcement_on(),
        "profile": {"status": profile.status if profile else NONE,
                    "seller_category": profile.seller_category if profile else None,
                    "public_label": public_label(profile),
                    "reverify_due_at": _iso(profile.reverify_due_at) if profile else None},
        "can_sell": profile_can_sell(profile) if enforcement_on() else True,
        "application": application_out(db, app) if app else None,
        "declaration": {"version": DECLARATION_VERSION, "text": DECLARATION_TEXT},
        "product_categories": list(rules.PRODUCT_CATEGORIES),
        "regulated_categories": sorted(rules.REGULATED_CATEGORIES),
        "private_review_thresholds": {"sales_usd": str(review_thresholds()[0]), "order_count": review_thresholds()[1],
                                      "note": "Internal MyHigh5 review triggers, not legal registration thresholds."},
    }


def migration_preview(db: Session) -> dict:
    """READ-ONLY: what enabling enforcement would mean for existing sellers. Changes nothing."""
    from app.models.business_model import MarketListing, MarketOrder
    from app.models.dsp import DigitalProduct
    from app.models.kyc import KYCStatus, KYCVerification
    from app.models.user import User

    seller_ids = {r for (r,) in db.query(MarketListing.seller_user_id).distinct().all()}
    seller_ids |= {r for (r,) in db.query(DigitalProduct.seller_id).filter(DigitalProduct.is_active.is_(True)).distinct().all()}
    seller_ids |= {r for (r,) in db.query(MarketOrder.seller_user_id)
                   .filter(MarketOrder.item_type.in_(QUALIFYING_ITEM_TYPES)).distinct().all()}
    usd_limit, count_limit = review_thresholds()
    terminal = ("RELEASED", "REFUNDED", "CANCELLED")
    rows = []
    for uid in sorted(seller_ids):
        user = db.get(User, uid)
        profile = get_profile(db, uid)
        kyc = db.query(KYCVerification).filter(KYCVerification.user_id == uid).order_by(KYCVerification.id.desc()).first()
        published = db.query(MarketListing).filter_by(seller_user_id=uid, status="PUBLISHED").count()
        dsp_active = db.query(DigitalProduct).filter(DigitalProduct.seller_id == uid, DigitalProduct.is_active.is_(True)).count()
        open_orders = db.query(MarketOrder).filter(MarketOrder.seller_user_id == uid,
                                                   MarketOrder.state.notin_(terminal)).count()
        sales = rolling_sales(db, uid)
        signals = _commercial_signals(db, uid)
        business_like = sales["sales_usd"] >= usd_limit or sales["order_count"] >= count_limit or bool(signals)
        missing = []
        if kyc is None or kyc.status != KYCStatus.APPROVED:
            missing.append("MEMBER_KYC_APPROVED")
        if not profile or profile.status == NONE:
            missing.append("SELLER_APPLICATION")
        if business_like and not (user and user.payout_wallet_verified_at):
            missing.append("PAYOUT_DESTINATION_CONFIRMED")
        approved = profile_can_sell(profile)
        rows.append({
            "user_id": uid, "account_active": bool(user and user.is_active and not getattr(user, "is_deleted", False)),
            "seller_status": profile.status if profile else NONE,
            "proposed_category": (profile.seller_category if profile and profile.seller_category
                                  else ("BUSINESS_REVIEW" if business_like else PRIVATE)),
            "published_listings": published, "active_digital_products": dsp_active,
            "rolling_sales_usd": str(sales["sales_usd"]), "rolling_order_count": sales["order_count"],
            "commercial_signals": signals, "missing": missing,
            "requires_manual_review": business_like or bool(signals),
            "proposed_restriction": None if approved else (
                "When enforcement is enabled: new publishing and new orders paused until approved; "
                "existing listings kept, not deleted" if (published or dsp_active) else "None (nothing published)"),
            "open_orders_protected": open_orders,
        })
    return {
        "read_only": True, "enforcement_enabled": enforcement_on(), "existing_seller_count": len(rows),
        "already_approved": sum(1 for r in rows if r["seller_status"] == APPROVED),
        "requiring_manual_review": sum(1 for r in rows if r["requires_manual_review"]),
        "would_be_paused": sum(1 for r in rows if r["proposed_restriction"] and r["proposed_restriction"].startswith("When")),
        "open_orders_protected": sum(r["open_orders_protected"] for r in rows),
        "note": "No seller is approved, suspended or changed by this preview. Existing orders, refunds, downloads, "
                "balances and records continue unchanged when enforcement is enabled.",
        "sellers": rows,
    }
