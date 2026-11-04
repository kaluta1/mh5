"""Advertising API: slot decisions and beacons (public), advertiser campaigns (members), advertising
earnings (members) and administration (manage_advertising permission; changes also need the current
password)."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api import deps
from app.core.client_ip import client_ip
from app.core.rate_limit import _is_rate_limited
from app.models.advertising_v2 import (AdvAdsenseBucket, AdvAdsenseImport, AdvAdsenseMonth, AdvAllocation,
                                       AdvAnnualAdsPayment, AdvCampaign, AdvCreative, AdvEntryOrigin,
                                       AdvImpressionEvent)
from app.models.user import User
from app.services import ad_attribution, ad_campaigns as camp, ad_delivery, ad_revenue_sharing as sharing
from app.services import payment_config
from app.services.financial_integrity import FinancialIntegrityError

public_router = APIRouter()
member_router = APIRouter()
admin_router = APIRouter()


def _err(exc: camp.AdError):
    return HTTPException(status_code=exc.status, detail={"code": exc.code, "message": exc.message})


# ---------------------------------------------------------------- public: decide + beacon

class DecideRequest(BaseModel):
    page_type: Literal["CONTEST_LISTING", "CONTEST_ENTRY", "FEED", "POST", "DISCOVERY", "PROFILE", "MARKETPLACE"]
    slot_kind: Literal["SIDEBAR", "IN_FEED", "IN_CONTENT"]
    slot_key: str = Field(min_length=1, max_length=80)
    contestant_id: Optional[int] = None


class EventRequest(BaseModel):
    decision_id: str = Field(min_length=36, max_length=36)
    event_id: str = Field(min_length=36, max_length=36)
    # CLICK is never a beacon: it is recorded only by the MyHigh5 click redirect (GET /ads/click/{id}).
    event_type: Literal["SERVED", "VIEWABLE", "VIDEO_2S", "VIDEO_VIEW"]
    visible_ms: Optional[int] = Field(default=None, ge=0, le=3_600_000)
    visible_ratio: Optional[float] = Field(default=None, ge=0, le=1)
    page_visible: Optional[bool] = None
    played_ms: Optional[int] = Field(default=None, ge=0, le=3_600_000)


def _viewer(request: Request, user: Optional[User]) -> str:
    return ad_delivery.viewer_hash(user.id if user else None, client_ip(request), request.headers.get("user-agent"))


@public_router.post("/decide")
def decide(body: DecideRequest, request: Request, response: Response, db: Session = Depends(deps.get_db),
           current_user: Optional[User] = Depends(deps.get_current_active_user_optional)):
    response.headers["Cache-Control"] = "private, no-store"
    if ad_delivery.is_bot(request.headers.get("user-agent")):
        return {"fill": False, "reason": "NO_FILL"}
    if _is_rate_limited(f"ad-decide:{client_ip(request)}", 120, 60):
        return {"fill": False, "reason": "RATE_LIMITED"}
    from app.services.interaction_safety import ad_eligibility

    elig = ad_eligibility(db, current_user)
    allowed = {k for k in ("myhigh5_ads", "adsense") if elig.get(k)}
    if not allowed:
        return {"fill": False, "reason": "NOT_ELIGIBLE"}
    country = (request.headers.get("cf-ipcountry") or request.headers.get("x-country") or "").strip()[:2] or None
    result = ad_delivery.decide(db, page_type=body.page_type, slot_kind=body.slot_kind, slot_key=body.slot_key,
                                contestant_id=body.contestant_id, viewer=_viewer(request, current_user),
                                country=country, allowed_sources=allowed,
                                viewer_user_id=current_user.id if current_user else None)
    db.commit()
    camp.send_pending(db)
    return result


@public_router.post("/events")
def events(body: EventRequest, request: Request, response: Response, db: Session = Depends(deps.get_db),
           current_user: Optional[User] = Depends(deps.get_current_active_user_optional)):
    response.headers["Cache-Control"] = "private, no-store"
    if _is_rate_limited(f"ad-events:{client_ip(request)}", 240, 60):
        return {"status": "RATE_LIMITED"}
    status = ad_delivery.record_event(db, decision_id=body.decision_id, event_id=body.event_id,
                                      event_type=body.event_type, visible_ms=body.visible_ms,
                                      visible_ratio=body.visible_ratio, page_visible=body.page_visible,
                                      user_agent=request.headers.get("user-agent"),
                                      viewer=_viewer(request, current_user), played_ms=body.played_ms)
    db.commit()
    camp.send_pending(db)
    return {"status": status}


@public_router.get("/click/{decision_id}")
def click(decision_id: str, request: Request, db: Session = Depends(deps.get_db),
          current_user: Optional[User] = Depends(deps.get_current_active_user_optional)):
    """Count a click on a MyHigh5 ad, then send the browser to the creative's REVIEWED destination. The
    target is never taken from the request (no open redirect) and is validated again here. An unknown
    decision, or one that is not a MyHigh5 ad, answers 404 and redirects nowhere. Billing happens later,
    in validation (one click per decision, not a bot, not the advertiser, not within 1 s of serving)."""
    import uuid as _uuid

    from fastapi.responses import RedirectResponse

    from app.models.advertising_v2 import AdvCreative, AdvServeDecision
    from app.services.advertising_integrity import AdvertisingIntegrityError, normalize_destination_url

    try:
        _uuid.UUID(decision_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=404, detail="Not found") from None
    decision = db.query(AdvServeDecision).filter(AdvServeDecision.id == decision_id).first()
    creative = (db.query(AdvCreative).filter(AdvCreative.id == decision.creative_id).first()
                if decision is not None and decision.source == "MYHIGH5" and decision.creative_id else None)
    if creative is None or creative.review_status != "APPROVED":
        raise HTTPException(status_code=404, detail="Not found")
    try:
        target = normalize_destination_url(creative.destination_url)
    except AdvertisingIntegrityError:
        raise HTTPException(status_code=404, detail="Not found") from None
    if not _is_rate_limited(f"ad-click:{client_ip(request)}", 60, 60):
        ad_delivery.record_event(db, decision_id=decision_id, event_id=str(_uuid.uuid4()), event_type="CLICK",
                                 visible_ms=None, visible_ratio=None, page_visible=None,
                                 user_agent=request.headers.get("user-agent"), viewer=_viewer(request, current_user),
                                 action="CTA_CLICK", allow_click=True)
        db.commit()
    return RedirectResponse(target, status_code=302, headers={"Cache-Control": "private, no-store",
                                                              "Referrer-Policy": "strict-origin-when-cross-origin"})


@public_router.get("/config")
def public_config(response: Response, db: Session = Depends(deps.get_db)):
    """Placement limits shown to the frontend (no prices)."""
    response.headers["Cache-Control"] = "public, max-age=60"
    cfg = camp.get_settings(db)
    db.rollback()
    camp.discard_pending(db)
    return {"in_feed_every": 5, "max_in_feed_per_page": 5, "sponsored_label": "Sponsored",
            "campaigns_live": bool(cfg.campaigns_enabled and camp.pricing_state(cfg) == "CONFIGURED")}


# ---------------------------------------------------------------- advertiser (member)

class CampaignCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    # Standard CPM (the default) keeps its fields; Daily City derives budget and dates from the booked days.
    budget: Optional[Decimal] = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    daily_cap: Optional[Decimal] = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    start_at: Optional[datetime] = None
    end_at: Optional[datetime] = None
    placements: List[Literal["SIDEBAR", "IN_FEED", "IN_CONTENT"]]
    countries: List[str] = []
    page_types: List[str] = []
    package: str = Field(default="cpm", max_length=20)
    unit_rate: Optional[Decimal] = Field(default=None, gt=0, max_digits=18, decimal_places=6)
    city_id: Optional[int] = None
    booked_days: List[date] = []


class CampaignUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=160)
    budget: Optional[Decimal] = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    daily_cap: Optional[Decimal] = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    start_at: Optional[datetime] = None
    end_at: Optional[datetime] = None
    placements: Optional[List[Literal["SIDEBAR", "IN_FEED", "IN_CONTENT"]]] = None
    countries: Optional[List[str]] = None
    page_types: Optional[List[str]] = None


class CreativeCreate(BaseModel):
    headline: str = Field(min_length=1, max_length=90)
    body: Optional[str] = Field(default=None, max_length=240)
    image_url: Optional[str] = Field(default=None, max_length=500)
    destination_url: str = Field(min_length=1, max_length=500)


def _own_campaign(db: Session, user: User, campaign_id: int, lock: bool = False) -> AdvCampaign:
    q = db.query(AdvCampaign).filter(AdvCampaign.id == campaign_id, AdvCampaign.advertiser_user_id == user.id)
    row = (q.with_for_update() if lock else q).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return row


@member_router.get("/advertiser/overview")
def advertiser_overview(db: Session = Depends(deps.get_db), user: User = Depends(deps.get_current_active_user)):
    cfg = camp.get_settings(db)
    campaigns = (db.query(AdvCampaign).filter(AdvCampaign.advertiser_user_id == user.id)
                 .order_by(AdvCampaign.id.desc()).all())
    reports = [camp.campaign_report(db, c) for c in campaigns]
    in_campaigns = sum((Decimal(r["remaining_budget"]) for r in reports
                        if r["status"] not in ("COMPLETED", "REJECTED")), Decimal("0.00"))
    packages = camp.packages(db)
    db.rollback()
    camp.discard_pending(db)
    return {"pricing_state": camp.pricing_state(cfg), "currency": "USD", "packages": packages,
            "cpm_rate_usd": str(cfg.cpm_rate_usd) if cfg.cpm_rate_usd is not None else None,
            "min_campaign_budget_usd": str(cfg.min_campaign_budget_usd) if cfg.min_campaign_budget_usd else None,
            "campaigns_enabled": bool(cfg.campaigns_enabled), "funding_enabled": bool(cfg.funding_enabled),
            "available_credit": str(camp.credit_balance(db, user.id)), "credit_in_campaigns": str(in_campaigns),
            "refund_policy": "Unspent credit stays available for new campaigns. Refunds follow a policy "
                             "that is not published yet; none are issued automatically.",
            "campaigns": reports}


@member_router.post("/advertiser/campaigns")
def create_campaign(body: CampaignCreate, db: Session = Depends(deps.get_db),
                    user: User = Depends(deps.get_current_active_user)):
    try:
        c = camp.create_campaign(db, user, name=body.name, budget=body.budget, daily_cap=body.daily_cap,
                                 start_at=body.start_at.replace(tzinfo=None) if body.start_at else None,
                                 end_at=body.end_at.replace(tzinfo=None) if body.end_at else None,
                                 placements=list(body.placements),
                                 targeting={"countries": body.countries, "page_types": body.page_types},
                                 package=body.package, unit_rate=body.unit_rate,
                                 bookings={"city_id": body.city_id, "days": body.booked_days}
                                 if body.city_id or body.booked_days else None)
    except camp.AdError as exc:
        db.rollback()
        camp.discard_pending(db)
        raise _err(exc) from None
    db.commit()
    camp.send_pending(db)
    return camp.campaign_report(db, c)


@member_router.get("/packages")
def advertising_packages(db: Session = Depends(deps.get_db), user: User = Depends(deps.get_current_active_user)):
    out = camp.packages(db)
    db.rollback()
    camp.discard_pending(db)
    return {"packages": out}


@member_router.get("/estimate")
def advertising_estimate(budget: Decimal, db: Session = Depends(deps.get_db),
                         user: User = Depends(deps.get_current_active_user)):
    """Theoretical allowance only (budget / CPM x 1,000): never a delivery promise."""
    cfg = camp.get_settings(db)
    db.rollback()
    camp.discard_pending(db)
    if budget <= 0 or budget > Decimal("1000000"):
        raise HTTPException(status_code=400, detail="Enter a positive budget")
    minimum = cfg.min_campaign_budget_usd
    return {"budget": str(budget.quantize(Decimal("0.01"))), "currency": "USD",
            "cpm_rate_usd": str(cfg.cpm_rate_usd) if cfg.cpm_rate_usd is not None else None,
            "estimated_impressions": camp.estimated_impressions(budget, cfg.cpm_rate_usd),
            "below_minimum": bool(minimum is not None and budget < minimum),
            "minimum_budget_usd": str(minimum) if minimum is not None else None,
            "note": "Estimated maximum of billable (valid, viewable) impressions; delivery is not guaranteed."}


@member_router.patch("/advertiser/campaigns/{campaign_id}")
def update_campaign(campaign_id: int, body: CampaignUpdate, db: Session = Depends(deps.get_db),
                    user: User = Depends(deps.get_current_active_user)):
    c = _own_campaign(db, user, campaign_id, lock=True)
    changes = body.model_dump(exclude_unset=True)
    for key in ("start_at", "end_at"):
        if changes.get(key) is not None:
            changes[key] = changes[key].replace(tzinfo=None)
    try:
        camp.update_campaign(db, user, c, changes)
    except camp.AdError as exc:
        db.rollback()
        camp.discard_pending(db)
        raise _err(exc) from None
    db.commit()
    camp.send_pending(db)
    return camp.campaign_report(db, c)


@member_router.post("/advertiser/campaigns/{campaign_id}/creatives/{creative_id}/image")
async def upload_creative_image(campaign_id: int, creative_id: int, request: Request, file: UploadFile = File(...),
                                db: Session = Depends(deps.get_db), user: User = Depends(deps.get_current_active_user)):
    """Upload the creative's image into the existing media storage (signature, MIME, extension and pixel checks,
    metadata stripped), then the advertising limits (format, 2 MB, 100-4000 px). Owner only."""
    from app.core.storage import store_media, validate_media_content

    if _is_rate_limited(f"ad-image:{user.id}", 20, 3600):
        raise HTTPException(status_code=429, detail="Too many uploads; try again later")
    c = _own_campaign(db, user, campaign_id)
    if c.status not in ("DRAFT", "CHANGES_REQUESTED", "PENDING_REVIEW", "PAUSED", "ACTIVE"):
        raise HTTPException(status_code=409, detail={"code": "CAMPAIGN_CLOSED", "message": "The campaign is closed"})
    cr = db.query(AdvCreative).filter(AdvCreative.id == creative_id, AdvCreative.campaign_id == c.id).first()
    if cr is None:
        raise HTTPException(status_code=404, detail="Creative not found")
    content = await file.read(camp.CREATIVE_IMAGE_MAX_BYTES + 1)
    try:
        meta = validate_media_content(file.filename or "", file.content_type or "", content)
        camp.check_creative_image(meta)
    except camp.AdError as exc:
        raise _err(exc) from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "INVALID_IMAGE", "message": str(exc)}) from None
    await file.seek(0)
    stored = await store_media(file, user.id)
    camp.attach_image(db, cr, stored, actor_id=user.id)
    db.commit()
    camp.send_pending(db)
    return camp.creative_payload(cr)


@member_router.post("/advertiser/campaigns/{campaign_id}/creatives")
def add_creative(campaign_id: int, body: CreativeCreate, db: Session = Depends(deps.get_db),
                 user: User = Depends(deps.get_current_active_user)):
    c = _own_campaign(db, user, campaign_id)
    try:
        cr = camp.add_creative(db, c, headline=body.headline, body=body.body, image_url=body.image_url,
                               destination_url=body.destination_url)
    except camp.AdError as exc:
        db.rollback()
        camp.discard_pending(db)
        raise _err(exc) from None
    db.commit()
    camp.send_pending(db)
    return {"id": cr.id, "review_status": cr.review_status}


@member_router.post("/advertiser/campaigns/{campaign_id}/{action}")
def campaign_action(campaign_id: int, action: Literal["submit", "pause", "resume", "complete", "cancel"],
                    db: Session = Depends(deps.get_db), user: User = Depends(deps.get_current_active_user)):
    c = _own_campaign(db, user, campaign_id, lock=True)
    try:
        if action == "submit":
            camp.submit_campaign(db, user, c)
        elif action in ("pause", "resume"):
            camp.set_paused(db, user, c, paused=action == "pause")
        elif action == "cancel":
            camp.cancel_campaign(db, user, c)
        else:
            camp.complete_campaign(db, c, reason="ADVERTISER_STOPPED", actor_id=user.id)
    except camp.AdError as exc:
        db.rollback()
        camp.discard_pending(db)
        raise _err(exc) from None
    db.commit()
    camp.send_pending(db)
    return camp.campaign_report(db, c)


# ---------------------------------------------------------------- earnings (member)

@member_router.get("/earnings/summary")
def earnings_summary(db: Session = Depends(deps.get_db), user: User = Depends(deps.get_current_active_user)):
    out = sharing.member_summary(db, user.id)
    db.rollback()
    camp.discard_pending(db)
    return out


@member_router.get("/earnings/missed")
def earnings_missed(skip: int = 0, limit: int = 20, db: Session = Depends(deps.get_db),
                    user: User = Depends(deps.get_current_active_user)):
    """The member's own missed advertising shares (creative and sponsor). Never payable."""
    from app.models.missed_earning import CATEGORY_AD_CREATIVE, CATEGORY_AD_SPONSOR
    from app.services import missed_earnings

    out = missed_earnings.member_page(db, user.id, categories=(CATEGORY_AD_CREATIVE, CATEGORY_AD_SPONSOR),
                                      skip=max(0, skip), limit=min(max(1, limit), 100))
    db.rollback()
    camp.discard_pending(db)
    return out


@member_router.get("/earnings/lines")
def earnings_lines(db: Session = Depends(deps.get_db), user: User = Depends(deps.get_current_active_user)):
    return {"lines": sharing.member_lines(db, user.id)}


# ---------------------------------------------------------------- administration

def require_ad_admin(current_user: User = Depends(deps.get_current_active_user)) -> User:
    if not payment_config.has_permission(current_user, camp.PERMISSION_MANAGE):
        raise HTTPException(status_code=403, detail="The manage_advertising permission is required.")
    return current_user


def _reauth(actor: User, password: Optional[str]) -> None:
    try:
        payment_config.require_reauth(actor, password)
    except payment_config.PaymentConfigError as exc:
        raise HTTPException(status_code=403, detail={"code": exc.code, "message": str(exc)}) from None


class SettingsChange(BaseModel):
    changes: dict
    current_password: str = Field(default="", max_length=256)


class ReviewBody(BaseModel):
    approve: bool
    note: str = Field(default="", max_length=500)


class NoteBody(BaseModel):
    note: str = Field(min_length=3, max_length=500)


class ScanBody(BaseModel):
    limit: int = Field(default=500, ge=1, le=2000)
    current_password: str = Field(default="", max_length=256)


class OriginBody(BaseModel):
    origin_kind: Literal["PERSONAL_SUBMISSION", "NOMINATION"]
    note: str = Field(min_length=3, max_length=300)
    current_password: str = Field(default="", max_length=256)


class FinalizeBody(BaseModel):
    period: str = Field(pattern=r"^\d{4}-\d{2}$")
    source: Literal["MYHIGH5", "ADSENSE"]
    current_password: str = Field(default="", max_length=256)


class AdsenseMonthBody(BaseModel):
    period: str = Field(pattern=r"^\d{4}-\d{2}$")
    finalized_total: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    evidence_note: str = Field(min_length=3, max_length=500)
    current_password: str = Field(default="", max_length=256)


class ImportBody(BaseModel):
    start: date
    end: date


class ReverseBody(BaseModel):
    event_ids: List[int] = Field(min_length=1, max_length=5000)
    reason: str = Field(min_length=3, max_length=200)
    current_password: str = Field(default="", max_length=256)


class HeldSponsorBody(BaseModel):
    note: str = Field(min_length=3, max_length=300)
    current_password: str = Field(default="", max_length=256)


@admin_router.get("/overview")
def admin_overview(db: Session = Depends(deps.get_db), admin: User = Depends(require_ad_admin)):
    from sqlalchemy import func

    cfg = camp.get_settings(db)
    status_counts = dict(db.query(AdvCampaign.status, func.count(AdvCampaign.id)).group_by(AdvCampaign.status).all())
    events = dict(db.query(AdvImpressionEvent.validation_status, func.count(AdvImpressionEvent.id))
                  .group_by(AdvImpressionEvent.validation_status).all())
    allocations = [{"status": s, "count": int(n), "amount": str(a or 0)} for s, n, a in
                   db.query(AdvAllocation.status, func.count(AdvAllocation.id), func.sum(AdvAllocation.amount))
                   .group_by(AdvAllocation.status).all()]
    reviews = db.query(func.count(AdvEntryOrigin.id)).filter(AdvEntryOrigin.status == "REVIEW").scalar()
    annual = dict(db.query(AdvAnnualAdsPayment.buyer_match, func.count(AdvAnnualAdsPayment.id))
                  .group_by(AdvAnnualAdsPayment.buyer_match).all())
    from app.core.config import settings as app_settings

    out = {"settings": camp.settings_payload(cfg), "packages": camp.packages(db),
           "approved_policy": {"cpm_rate_usd": str(camp.APPROVED_CPM_USD),
                               "min_campaign_budget_usd": str(camp.APPROVED_MIN_BUDGET_USD)},
           "origins": ad_attribution.origin_overview(db),
           "campaigns": status_counts, "impression_events": events,
           "allocations": allocations, "origins_under_review": int(reviews or 0),
           "adsense": {"credentials_missing": sharing.missing_adsense_credentials(),
                       "imports": [{"id": i.id, "status": i.status, "rows": i.rows, "detail": i.detail,
                                    "period_start": str(i.period_start), "period_end": str(i.period_end)}
                                   for i in db.query(AdvAdsenseImport).order_by(AdvAdsenseImport.id.desc()).limit(10)],
                       "months": [{"id": m.id, "period": m.period, "finalized_total": str(m.finalized_total),
                                   "estimated_total": str(m.estimated_total)}
                                  for m in db.query(AdvAdsenseMonth).order_by(AdvAdsenseMonth.period.desc()).limit(12)]},
           "annual_ads": {"enabled": bool(getattr(app_settings, "ANNUALADS_ENABLED", False)),
                          "payments_by_buyer_match": annual,
                          "sponsor_commission": "PENDING_POLICY (gross vs net base not approved)"}}
    db.rollback()
    camp.discard_pending(db)
    return out


@admin_router.put("/settings")
def admin_settings(body: SettingsChange, db: Session = Depends(deps.get_db), admin: User = Depends(require_ad_admin)):
    _reauth(admin, body.current_password)
    try:
        row = camp.update_settings(db, admin, body.changes)
    except camp.AdError as exc:
        db.rollback()
        camp.discard_pending(db)
        raise _err(exc) from None
    db.commit()
    camp.send_pending(db)
    return camp.settings_payload(row)


@admin_router.get("/campaigns")
def admin_campaigns(db: Session = Depends(deps.get_db), admin: User = Depends(require_ad_admin)):
    rows = db.query(AdvCampaign).order_by(AdvCampaign.id.desc()).limit(200).all()
    out = []
    for c in rows:
        r = camp.campaign_report(db, c)
        r["advertiser_user_id"] = c.advertiser_user_id
        r["creatives"] = [{"id": cr.id, "headline": cr.headline, "body": cr.body, "image_url": cr.image_url,
                           "destination_url": cr.destination_url, "review_status": cr.review_status}
                          for cr in db.query(AdvCreative).filter(AdvCreative.campaign_id == c.id).all()]
        out.append(r)
    return {"campaigns": out}


@admin_router.post("/creatives/{creative_id}/review")
def admin_review_creative(creative_id: int, body: ReviewBody, db: Session = Depends(deps.get_db),
                          admin: User = Depends(require_ad_admin)):
    cr = db.query(AdvCreative).filter(AdvCreative.id == creative_id).first()
    if cr is None:
        raise HTTPException(status_code=404, detail="Creative not found")
    try:
        camp.review_creative(db, admin, cr, approve=body.approve, note=body.note)
    except camp.AdError as exc:
        db.rollback()
        camp.discard_pending(db)
        raise _err(exc) from None
    db.commit()
    camp.send_pending(db)
    return {"id": cr.id, "review_status": cr.review_status}


@admin_router.post("/campaigns/{campaign_id}/review")
def admin_review_campaign(campaign_id: int, body: ReviewBody, db: Session = Depends(deps.get_db),
                          admin: User = Depends(require_ad_admin)):
    c = db.query(AdvCampaign).filter(AdvCampaign.id == campaign_id).first()
    if c is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    try:
        camp.review_campaign(db, admin, c, approve=body.approve, note=body.note)
    except camp.AdError as exc:
        db.rollback()
        camp.discard_pending(db)
        raise _err(exc) from None
    db.commit()
    camp.send_pending(db)
    return camp.campaign_report(db, c)


@admin_router.post("/campaigns/{campaign_id}/pause")
def admin_pause_campaign(campaign_id: int, db: Session = Depends(deps.get_db), admin: User = Depends(require_ad_admin)):
    c = db.query(AdvCampaign).filter(AdvCampaign.id == campaign_id).first()
    if c is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    try:
        camp.set_paused(db, admin, c, paused=True)
    except camp.AdError as exc:
        db.rollback()
        camp.discard_pending(db)
        raise _err(exc) from None
    db.commit()
    camp.send_pending(db)
    return camp.campaign_report(db, c)


@admin_router.post("/campaigns/{campaign_id}/resume")
def admin_resume_campaign(campaign_id: int, db: Session = Depends(deps.get_db), admin: User = Depends(require_ad_admin)):
    c = db.query(AdvCampaign).filter(AdvCampaign.id == campaign_id).first()
    if c is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    try:
        camp.set_paused(db, admin, c, paused=False)
    except camp.AdError as exc:
        db.rollback()
        camp.discard_pending(db)
        raise _err(exc) from None
    db.commit()
    camp.send_pending(db)
    return camp.campaign_report(db, c)


@admin_router.post("/campaigns/{campaign_id}/request-changes")
def admin_request_changes(campaign_id: int, body: NoteBody, db: Session = Depends(deps.get_db),
                          admin: User = Depends(require_ad_admin)):
    c = db.query(AdvCampaign).filter(AdvCampaign.id == campaign_id).first()
    if c is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    try:
        camp.request_changes(db, admin, c, note=body.note)
    except camp.AdError as exc:
        db.rollback()
        camp.discard_pending(db)
        raise _err(exc) from None
    db.commit()
    camp.send_pending(db)
    return camp.campaign_report(db, c)


@admin_router.get("/reconciliation")
def admin_reconciliation(db: Session = Depends(deps.get_db), admin: User = Depends(require_ad_admin)):
    out = camp.reconciliation(db)
    db.rollback()
    camp.discard_pending(db)
    return out


@admin_router.get("/suspicious")
def admin_suspicious(db: Session = Depends(deps.get_db), admin: User = Depends(require_ad_admin)):
    out = camp.suspicious_activity(db)
    db.rollback()
    camp.discard_pending(db)
    return out


@admin_router.get("/origins")
def admin_origins(skip: int = 0, limit: int = 50, db: Session = Depends(deps.get_db),
                  admin: User = Depends(require_ad_admin)):
    out = {"overview": ad_attribution.origin_overview(db),
           "origins": ad_attribution.review_page(db, skip=skip, limit=limit)}
    db.rollback()
    camp.discard_pending(db)
    return out


@admin_router.post("/origins/scan")
def admin_scan_origins(body: ScanBody, db: Session = Depends(deps.get_db), admin: User = Depends(require_ad_admin)):
    """Classify active entries from verified evidence; unprovable ones go to review (held). No money moves."""
    from app.models.accounting import AuditTrail

    _reauth(admin, body.current_password)
    out = ad_attribution.scan_origins(db, limit=body.limit)
    db.add(AuditTrail(table_name="adv_entry_origins", record_id=0, action="SCAN", old_values=None, new_values=out,
                      user_id=admin.id))
    db.commit()
    camp.send_pending(db)
    return out


@admin_router.post("/origins/{contestant_id}/resolve")
def admin_resolve_origin(contestant_id: int, body: OriginBody, db: Session = Depends(deps.get_db),
                         admin: User = Depends(require_ad_admin)):
    from app.models.accounting import AuditTrail

    _reauth(admin, body.current_password)
    try:
        row = ad_attribution.resolve_review(db, contestant_id=contestant_id, origin_kind=body.origin_kind,
                                            actor_id=admin.id, note=body.note)
        priced = sharing.apply_origin_resolution(db, contestant_id=contestant_id)
    except ValueError as exc:
        db.rollback()
        camp.discard_pending(db)
        raise HTTPException(status_code=409, detail=str(exc)) from None
    db.add(AuditTrail(table_name="adv_entry_origins", record_id=row.id, action="RESOLVE", old_values={"status": "REVIEW"},
                      new_values={"origin_kind": body.origin_kind, "note": body.note, "lines_priced": priced},
                      user_id=admin.id))
    db.commit()
    camp.send_pending(db)
    return {"contestant_id": contestant_id, "origin_kind": row.origin_kind, "lines_priced": priced}


@admin_router.get("/allocations")
def admin_allocations(period: Optional[str] = None, db: Session = Depends(deps.get_db),
                      admin: User = Depends(require_ad_admin)):
    q = db.query(AdvAllocation)
    if period:
        q = q.filter(AdvAllocation.period == period)
    rows = q.order_by(AdvAllocation.id.desc()).limit(1000).all()
    return {"allocations": [{"id": r.id, "period": r.period, "contestant_id": r.contestant_id, "role": r.role,
                             "source": r.source, "origin_kind": r.origin_kind, "contest_level": r.contest_level,
                             "beneficiary_user_id": r.beneficiary_user_id, "rate": str(r.rate),
                             "base_amount": str(r.base_amount), "amount": str(r.amount), "status": r.status,
                             "version": r.version, "commission_id": r.commission_id} for r in rows]}


@admin_router.get("/estimate")
def admin_estimate(period: str, source: Literal["MYHIGH5", "ADSENSE"], db: Session = Depends(deps.get_db),
                   admin: User = Depends(require_ad_admin)):
    lines = sharing.plan_lines(db, period, source, finalized=False)
    return {"period": period, "source": source, "estimate": True,
            "lines": [{k: (str(v) if isinstance(v, Decimal) else v) for k, v in l.items()} for l in lines]}


@admin_router.post("/finalize")
def admin_finalize(body: FinalizeBody, db: Session = Depends(deps.get_db), admin: User = Depends(require_ad_admin)):
    _reauth(admin, body.current_password)
    try:
        out = sharing.finalize_period(db, period=body.period, source=body.source, actor_id=admin.id)
    except camp.AdError as exc:
        db.rollback()
        camp.discard_pending(db)
        raise _err(exc) from None
    except FinancialIntegrityError as exc:
        db.rollback()
        camp.discard_pending(db)
        raise HTTPException(status_code=409, detail=str(exc)) from None
    db.commit()
    camp.send_pending(db)
    return out


@admin_router.post("/allocations/{line_id}/release-held-sponsor")
def admin_release_held_sponsor(line_id: int, body: HeldSponsorBody, db: Session = Depends(deps.get_db),
                               admin: User = Depends(require_ad_admin)):
    _reauth(admin, body.current_password)
    try:
        line = sharing.release_held_sponsor(db, line_id=line_id, actor_id=admin.id, note=body.note)
    except camp.AdError as exc:
        db.rollback()
        camp.discard_pending(db)
        raise _err(exc) from None
    db.commit()
    camp.send_pending(db)
    return {"id": line.id, "status": line.status, "beneficiary_user_id": line.beneficiary_user_id}


@admin_router.post("/adsense/import")
def admin_adsense_import(body: ImportBody, db: Session = Depends(deps.get_db), admin: User = Depends(require_ad_admin)):
    if body.end < body.start or (body.end - body.start).days > 62:
        raise HTTPException(status_code=400, detail="Choose a range of at most 62 days")
    run = sharing.import_adsense(db, start=body.start, end=body.end, actor_id=admin.id)
    db.commit()
    camp.send_pending(db)
    return {"id": run.id, "status": run.status, "rows": run.rows, "detail": run.detail}


@admin_router.post("/adsense/months")
def admin_adsense_month(body: AdsenseMonthBody, db: Session = Depends(deps.get_db),
                        admin: User = Depends(require_ad_admin)):
    _reauth(admin, body.current_password)
    try:
        month = sharing.record_finalized_month(db, period=body.period, finalized_total=body.finalized_total,
                                               actor_id=admin.id, evidence_note=body.evidence_note)
    except camp.AdError as exc:
        db.rollback()
        camp.discard_pending(db)
        raise _err(exc) from None
    db.commit()
    camp.send_pending(db)
    return {"id": month.id, "period": month.period, "finalized_total": str(month.finalized_total),
            "estimated_total": str(month.estimated_total)}


@admin_router.get("/adsense/buckets")
def admin_adsense_buckets(period: str, db: Session = Depends(deps.get_db), admin: User = Depends(require_ad_admin)):
    start, end = sharing.period_bounds(period)
    rows = db.query(AdvAdsenseBucket).filter(AdvAdsenseBucket.day >= start, AdvAdsenseBucket.day < end).all()
    return {"buckets": [{"day": str(b.day), "ad_unit": b.ad_unit, "currency": b.currency, "status": b.status,
                         "estimated": str(b.estimated_earnings),
                         "finalized": str(b.finalized_earnings) if b.finalized_earnings is not None else None}
                        for b in rows]}


@admin_router.post("/invalid-activity")
def admin_reverse_invalid(body: ReverseBody, db: Session = Depends(deps.get_db), admin: User = Depends(require_ad_admin)):
    _reauth(admin, body.current_password)
    try:
        out = ad_delivery.reverse_invalid_activity(db, event_ids=body.event_ids, reason=body.reason, actor_id=admin.id)
        adjusted = []
        for period in out["periods"]:
            for source in ("MYHIGH5", "ADSENSE"):
                res = sharing.adjust_after_reversal(db, period=period, source=source, reason=body.reason,
                                                    actor_id=admin.id)
                adjusted.append({"period": period, "source": source, **res})
        out["allocations"] = adjusted
    except camp.AdError as exc:
        db.rollback()
        camp.discard_pending(db)
        raise _err(exc) from None
    except FinancialIntegrityError as exc:
        db.rollback()
        camp.discard_pending(db)
        raise HTTPException(status_code=409, detail=str(exc)) from None
    db.commit()
    camp.send_pending(db)
    return out
