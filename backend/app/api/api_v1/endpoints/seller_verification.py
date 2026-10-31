"""Marketplace seller registration (member), seller verification review (admin) and signed provider
callbacks. Separate from member KYC; see app.services.seller_verification.

Member routes are closed while MARKETPLACE_ENABLED is off. Admin routes need an administrator AND the
explicit review_seller_verification permission (or a Super Admin), checked here on every route.
"""
from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.api_v1.endpoints.marketplace import _require_marketplace
from app.api.deps import get_current_user, get_db
from app.models.accounting import AuditTrail
from app.models.seller_verification import (
    SellerApplication,
    SellerClassificationReview,
    SellerDocument,
    SellerJurisdictionRule,
)
from app.models.user import User
from app.services import payment_config
from app.services import seller_verification as sv
from app.services import seller_verification_providers as prov
from app.services import seller_verification_rules as rules

router = APIRouter()
admin_router = APIRouter()

PERMISSION_REVIEW = "review_seller_verification"


def _run(db: Session, fn):
    try:
        result = fn()
        db.commit()
        return result
    except LookupError:
        db.rollback()
        raise HTTPException(status_code=404, detail="Not found") from None
    except (sv.SellerError, rules.RuleError) as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc


# ---------------------------------------------------------------- member

class LicenceIn(BaseModel):
    type: str = Field(max_length=120)
    authority: str = Field(max_length=160)
    number: str = Field(max_length=80)
    expires_on: Optional[date] = None


class PersonIn(BaseModel):
    full_name: Optional[str] = Field(None, max_length=200)
    role: Optional[str] = Field(None, max_length=120)


class OwnerIn(BaseModel):
    full_name: str = Field(max_length=200)
    percent: str = Field(max_length=10)


class ApplicationIn(BaseModel):
    seller_category: Literal["PRIVATE", "SOLE_TRADER", "ORGANISATION"]
    business_structure: Optional[str] = Field(None, max_length=30)
    legal_name: Optional[str] = Field(None, max_length=200)
    trading_name: Optional[str] = Field(None, max_length=160)
    residence_country: Optional[str] = Field(None, max_length=2)
    establishment_country: Optional[str] = Field(None, max_length=2)
    establishment_subdivision: Optional[str] = Field(None, max_length=20)
    customer_markets: Optional[list[str]] = Field(None, max_length=60)
    business_address: Optional[str] = Field(None, max_length=1000)
    contact_phone: Optional[str] = Field(None, max_length=30)
    product_categories: Optional[list[str]] = Field(None, max_length=20)
    products_description: Optional[str] = Field(None, max_length=2000)
    commercial_indicators: Optional[dict[str, bool]] = None
    registration_authority: Optional[str] = Field(None, max_length=160)
    registration_number: Optional[str] = Field(None, max_length=60)
    exemption_basis: Optional[str] = Field(None, max_length=2000)
    tax_registered: Optional[bool] = None
    tax_identifier: Optional[str] = Field(None, max_length=40)
    licences: Optional[list[LicenceIn]] = Field(None, max_length=20)
    representative: Optional[PersonIn] = None
    ownership: Optional[list[OwnerIn]] = Field(None, max_length=25)


class SubmitIn(BaseModel):
    declaration_version: str = Field(max_length=40)
    accept_declaration: bool


class AppealIn(BaseModel):
    text: str = Field(min_length=20, max_length=3000)


def _payload(body: ApplicationIn) -> dict:
    data = body.model_dump(exclude_unset=True, mode="json")
    if "tax_identifier" in data and data["tax_identifier"] is None:
        data.pop("tax_identifier")                    # leaving the field empty keeps the stored identifier
    return data


@router.get("/marketplace/seller/status")
def seller_status(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require_marketplace()
    return sv.status_out(db, current_user.id)


@router.put("/marketplace/seller/application")
def save_application(body: ApplicationIn, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Save (or resume) the draft. Nothing is checked or decided until it is submitted."""
    _require_marketplace()
    _run(db, lambda: sv.save_draft(db, user_id=current_user.id, data=_payload(body)))
    return sv.status_out(db, current_user.id)


@router.post("/marketplace/seller/application/submit")
def submit_application(body: SubmitIn, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require_marketplace()
    _run(db, lambda: sv.submit(db, user_id=current_user.id, declaration_version=body.declaration_version,
                               accept_declaration=body.accept_declaration))
    return sv.status_out(db, current_user.id)


@router.post("/marketplace/seller/application/documents", status_code=status.HTTP_201_CREATED)
def upload_document(doc_type: str = Form(...), expires_on: Optional[date] = Form(None), file: UploadFile = File(...),
                    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """A compliance document (PDF, JPG or PNG, 10 MB at most), encrypted in private storage."""
    _require_marketplace()
    _run(db, lambda: sv.store_document(db, user_id=current_user.id, doc_type=doc_type, filename=file.filename or "",
                                       stream=file.file, expires_on=expires_on))
    return sv.status_out(db, current_user.id)


@router.post("/marketplace/seller/appeal")
def appeal(body: AppealIn, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require_marketplace()
    _run(db, lambda: sv.appeal(db, user_id=current_user.id, text=body.text))
    return sv.status_out(db, current_user.id)


@router.post("/marketplace/seller/provider-callback/{provider_name}")
async def provider_callback(provider_name: str, request: Request, db: Session = Depends(get_db)):
    """Signed result from a connected verification provider. Unknown providers and bad signatures are
    refused; a repeated event id is acknowledged without being applied twice."""
    provider = prov.provider_named(provider_name)
    body = await request.body()
    if provider is None or not prov.verify_signature(provider, body, request.headers.get("X-Signature")):
        raise HTTPException(status_code=404, detail="Not found")
    try:
        import json

        payload = json.loads(body or b"{}")
        event_id, reference = str(payload["event_id"])[:160], str(payload["reference"])[:160]
        outcome, result_code = str(payload["outcome"]).upper(), str(payload.get("result_code") or "")
    except (ValueError, KeyError, TypeError):
        raise HTTPException(status_code=422, detail="Malformed callback") from None
    return _run(db, lambda: sv.apply_provider_callback(db, provider_name=provider.name, event_id=event_id,
                                                       reference=reference, outcome=outcome, result_code=result_code))


# ---------------------------------------------------------------- admin

def require_reviewer(current_user: User = Depends(get_current_user)) -> User:
    if not payment_config.has_permission(current_user, PERMISSION_REVIEW):
        raise HTTPException(status_code=403, detail="The review_seller_verification permission is required.")
    return current_user


def _audit(db: Session, *, actor_id: int, table: str, record_id: int, action: str, new: dict) -> None:
    db.add(AuditTrail(table_name=table, record_id=int(record_id), action=action, old_values=None,
                      new_values={k: (v.isoformat() if isinstance(v, date) else v) for k, v in new.items()},
                      user_id=actor_id))


@admin_router.get("/applications")
def admin_applications(status_filter: Optional[str] = Query(None, alias="status"), db: Session = Depends(get_db),
                       reviewer: User = Depends(require_reviewer)):
    q = db.query(SellerApplication)
    if status_filter:
        q = q.filter(SellerApplication.status == status_filter)
    return [{"id": a.id, "user_id": a.user_id, "status": a.status, "seller_category": a.seller_category,
             "business_structure": a.business_structure, "legal_name": a.legal_name, "trading_name": a.trading_name,
             "establishment_country": a.establishment_country, "residence_country": a.residence_country,
             "review_reasons": a.review_reasons or [], "submitted_at": sv._iso(a.submitted_at)}
            for a in q.order_by(SellerApplication.id.desc()).limit(200).all()]


@admin_router.get("/applications/{application_id}")
def admin_application(application_id: int, db: Session = Depends(get_db), reviewer: User = Depends(require_reviewer)):
    app = db.get(SellerApplication, application_id)
    if app is None:
        raise HTTPException(status_code=404, detail="Not found")
    out = sv.application_out(db, app, admin=True)
    out["applicable_rule_details"] = [rules.rule_out(r) for r in rules.applicable_rules(db, app)]
    out["profile"] = sv.status_out(db, app.user_id)["profile"]
    return out


@admin_router.get("/documents/{document_id}")
def admin_document(document_id: int, db: Session = Depends(get_db), reviewer: User = Depends(require_reviewer)):
    """Decrypts one document for a reviewer. Every view is audited; the response is never cached."""
    doc = db.get(SellerDocument, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Not found")
    try:
        data = sv.read_document(doc)
    except (LookupError, sv.SellerError):
        raise HTTPException(status_code=404, detail="Document not available") from None
    _audit(db, actor_id=reviewer.id, table="seller_documents", record_id=doc.id, action="SELLER_DOCUMENT_VIEWED",
           new={"application_id": doc.application_id, "doc_type": doc.doc_type})
    db.commit()
    safe = "".join(c for c in doc.file_name if c.isalnum() or c in "._- ")[:120] or "document"
    return Response(content=data, media_type=doc.content_type, headers={
        "Content-Disposition": f'attachment; filename="{safe}"', "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff"})


class DecisionIn(BaseModel):
    action: Literal["approve", "request_correction", "reject", "restrict", "request_reverification"]
    reason: str = Field(min_length=5, max_length=2000)
    seller_message: Optional[str] = Field(None, max_length=2000)
    grace_days: int = Field(0, ge=0, le=60)


@admin_router.post("/applications/{application_id}/decision")
def admin_decision(application_id: int, body: DecisionIn, db: Session = Depends(get_db),
                   reviewer: User = Depends(require_reviewer)):
    def go():
        app = db.query(SellerApplication).filter(SellerApplication.id == application_id).with_for_update().first()
        if app is None:
            raise LookupError
        before = app.status
        sv.admin_decide(db, app, admin_user_id=reviewer.id, action=body.action, reason=body.reason,
                        seller_message=body.seller_message, grace_days=body.grace_days)
        _audit(db, actor_id=reviewer.id, table="seller_applications", record_id=app.id,
               action=f"SELLER_{body.action.upper()}",
               new={"from": before, "to": app.status, "reason": body.reason, "grace_days": body.grace_days})
        return app
    app = _run(db, go)
    return sv.application_out(db, app, admin=True)


@admin_router.post("/applications/{application_id}/retry-checks")
def admin_retry_checks(application_id: int, db: Session = Depends(get_db), reviewer: User = Depends(require_reviewer)):
    def go():
        app = db.query(SellerApplication).filter(SellerApplication.id == application_id).with_for_update().first()
        if app is None:
            raise LookupError
        sv.run_checks(db, app)
        _audit(db, actor_id=reviewer.id, table="seller_applications", record_id=app.id, action="SELLER_RETRY_CHECKS",
               new={"status": app.status})
        return app
    return sv.application_out(db, _run(db, go), admin=True)


@admin_router.get("/rules")
def admin_rules(db: Session = Depends(get_db), reviewer: User = Depends(require_reviewer)):
    return {"rules": [rules.rule_out(r) for r in db.query(SellerJurisdictionRule)
                      .order_by(SellerJurisdictionRule.jurisdiction, SellerJurisdictionRule.rule_code,
                                SellerJurisdictionRule.version).all()],
            "connected_providers": prov.connected()}


@admin_router.post("/rules/seed-defaults")
def admin_seed_rules(db: Session = Depends(get_db), reviewer: User = Depends(require_reviewer)):
    """Adds the default catalogue where missing (legal rules as DRAFT). Never changes an existing rule."""
    def go():
        added = rules.seed_defaults(db)
        _audit(db, actor_id=reviewer.id, table="seller_jurisdiction_rules", record_id=0, action="SELLER_RULES_SEEDED",
               new={"added": added})
        return added
    return {"added": _run(db, go)}


class RuleActivationIn(BaseModel):
    official_source_url: str = Field(max_length=500)
    last_reviewed_on: date
    effective_from: date
    note: str = Field(min_length=10, max_length=2000)


class RuleRetireIn(BaseModel):
    note: str = Field(min_length=10, max_length=2000)


@admin_router.post("/rules/{rule_id}/activate")
def admin_activate_rule(rule_id: int, body: RuleActivationIn, db: Session = Depends(get_db),
                        reviewer: User = Depends(require_reviewer)):
    def go():
        rule = db.get(SellerJurisdictionRule, rule_id)
        if rule is None:
            raise LookupError
        rules.activate(db, rule, actor_user_id=reviewer.id, official_source_url=body.official_source_url,
                       last_reviewed_on=body.last_reviewed_on, effective_from=body.effective_from, note=body.note)
        _audit(db, actor_id=reviewer.id, table="seller_jurisdiction_rules", record_id=rule.id,
               action="SELLER_RULE_ACTIVATED", new=body.model_dump())
        return rule
    return rules.rule_out(_run(db, go))


@admin_router.post("/rules/{rule_id}/retire")
def admin_retire_rule(rule_id: int, body: RuleRetireIn, db: Session = Depends(get_db),
                      reviewer: User = Depends(require_reviewer)):
    def go():
        rule = db.get(SellerJurisdictionRule, rule_id)
        if rule is None:
            raise LookupError
        rules.retire(db, rule, note=body.note)
        _audit(db, actor_id=reviewer.id, table="seller_jurisdiction_rules", record_id=rule.id,
               action="SELLER_RULE_RETIRED", new=body.model_dump())
        return rule
    return rules.rule_out(_run(db, go))


@admin_router.get("/classification-reviews")
def admin_classification_reviews(open_only: bool = True, db: Session = Depends(get_db),
                                 reviewer: User = Depends(require_reviewer)):
    q = db.query(SellerClassificationReview)
    if open_only:
        q = q.filter(SellerClassificationReview.status == "OPEN")
    return [{"id": r.id, "user_id": r.user_id, "trigger": r.trigger, "status": r.status,
             "qualifying_sales_usd": str(r.qualifying_sales_usd), "qualifying_order_count": r.qualifying_order_count,
             "window_start": sv._iso(r.window_start), "window_end": sv._iso(r.window_end), "detail": r.detail,
             "fx_rates_used": r.fx_rates_used, "resolution": r.resolution, "resolution_note": r.resolution_note}
            for r in q.order_by(SellerClassificationReview.id.desc()).limit(200).all()]


class ClassificationResolveIn(BaseModel):
    resolution: Literal["REMAINS_PRIVATE", "BUSINESS_ONBOARDING_REQUESTED"]
    note: str = Field(min_length=5, max_length=2000)


@admin_router.post("/classification-reviews/{review_id}/resolve")
def admin_resolve_classification(review_id: int, body: ClassificationResolveIn, db: Session = Depends(get_db),
                                 reviewer: User = Depends(require_reviewer)):
    def go():
        review = db.query(SellerClassificationReview).filter_by(id=review_id).with_for_update().first()
        if review is None:
            raise LookupError
        sv.resolve_classification_review(db, review, admin_user_id=reviewer.id, resolution=body.resolution,
                                         note=body.note)
        _audit(db, actor_id=reviewer.id, table="seller_classification_reviews", record_id=review.id,
               action="SELLER_CLASSIFICATION_RESOLVED", new=body.model_dump())
        return review
    review = _run(db, go)
    return {"id": review.id, "status": review.status, "resolution": review.resolution}


@admin_router.post("/monitoring/run")
def admin_run_monitoring(db: Session = Depends(get_db), reviewer: User = Depends(require_reviewer)):
    """Private seller monitoring, expiry/reverification sweep and provider retries. Idempotent; it never
    restricts selling by itself."""
    def go():
        result = {"classification_reviews_opened": sv.run_private_seller_monitoring(db),
                  **sv.run_compliance_sweep(db), "checks_retried": sv.retry_in_progress(db)}
        _audit(db, actor_id=reviewer.id, table="seller_profiles", record_id=0, action="SELLER_MONITORING_RUN",
               new=result)
        return result
    return _run(db, go)


@admin_router.get("/migration-preview")
def admin_migration_preview(db: Session = Depends(get_db), reviewer: User = Depends(require_reviewer)):
    """READ-ONLY preview of existing sellers before enforcement is enabled."""
    return sv.migration_preview(db)
