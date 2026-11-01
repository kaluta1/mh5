"""Advertising API: slot decisions and beacons (public), advertiser campaigns (members), advertising
earnings (members) and administration (manage_advertising permission; changes also need the current
password)."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
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
    event_type: Literal["SERVED", "VIEWABLE"]
    visible_ms: Optional[int] = Field(default=None, ge=0, le=3_600_000)
    visible_ratio: Optional[float] = Field(default=None, ge=0, le=1)
    page_visible: Optional[bool] = None


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
                                country=country, allowed_sources=allowed)
    db.commit()
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
                                      viewer=_viewer(request, current_user))
    db.commit()
    return {"status": status}


@public_router.get("/config")
def public_config(response: Response, db: Session = Depends(deps.get_db)):
    """Placement limits shown to the frontend (no prices)."""
    response.headers["Cache-Control"] = "public, max-age=60"
    cfg = camp.get_settings(db)
    db.rollback()
    return {"in_feed_every": 5, "max_in_feed_per_page": 5, "sponsored_label": "Sponsored",
            "campaigns_live": bool(cfg.campaigns_enabled and camp.pricing_state(cfg) == "CONFIGURED")}


# ---------------------------------------------------------------- advertiser (member)

class CampaignCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    budget: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    daily_cap: Optional[Decimal] = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    start_at: datetime
    end_at: datetime
    placements: List[Literal["SIDEBAR", "IN_FEED", "IN_CONTENT"]]
    countries: List[str] = []
    page_types: List[str] = []


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
    db.rollback()
    return {"pricing_state": camp.pricing_state(cfg), "currency": "USD",
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
                                 start_at=body.start_at.replace(tzinfo=None), end_at=body.end_at.replace(tzinfo=None),
                                 placements=list(body.placements),
                                 targeting={"countries": body.countries, "page_types": body.page_types})
    except camp.AdError as exc:
        db.rollback()
        raise _err(exc) from None
    db.commit()
    return camp.campaign_report(db, c)


@member_router.post("/advertiser/campaigns/{campaign_id}/creatives")
def add_creative(campaign_id: int, body: CreativeCreate, db: Session = Depends(deps.get_db),
                 user: User = Depends(deps.get_current_active_user)):
    c = _own_campaign(db, user, campaign_id)
    try:
        cr = camp.add_creative(db, c, headline=body.headline, body=body.body, image_url=body.image_url,
                               destination_url=body.destination_url)
    except camp.AdError as exc:
        db.rollback()
        raise _err(exc) from None
    db.commit()
    return {"id": cr.id, "review_status": cr.review_status}


@member_router.post("/advertiser/campaigns/{campaign_id}/{action}")
def campaign_action(campaign_id: int, action: Literal["submit", "pause", "resume", "complete"],
                    db: Session = Depends(deps.get_db), user: User = Depends(deps.get_current_active_user)):
    c = _own_campaign(db, user, campaign_id, lock=True)
    try:
        if action == "submit":
            camp.submit_campaign(db, user, c)
        elif action in ("pause", "resume"):
            camp.set_paused(db, user, c, paused=action == "pause")
        else:
            camp.complete_campaign(db, c, reason="ADVERTISER_STOPPED", actor_id=user.id)
    except camp.AdError as exc:
        db.rollback()
        raise _err(exc) from None
    db.commit()
    return camp.campaign_report(db, c)


# ---------------------------------------------------------------- earnings (member)

@member_router.get("/earnings/summary")
def earnings_summary(db: Session = Depends(deps.get_db), user: User = Depends(deps.get_current_active_user)):
    out = sharing.member_summary(db, user.id)
    db.rollback()
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

    out = {"settings": camp.settings_payload(cfg), "campaigns": status_counts, "impression_events": events,
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
    return out


@admin_router.put("/settings")
def admin_settings(body: SettingsChange, db: Session = Depends(deps.get_db), admin: User = Depends(require_ad_admin)):
    _reauth(admin, body.current_password)
    try:
        row = camp.update_settings(db, admin, body.changes)
    except camp.AdError as exc:
        db.rollback()
        raise _err(exc) from None
    db.commit()
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
        raise _err(exc) from None
    db.commit()
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
        raise _err(exc) from None
    db.commit()
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
        raise _err(exc) from None
    db.commit()
    return camp.campaign_report(db, c)


@admin_router.get("/origins")
def admin_origins(db: Session = Depends(deps.get_db), admin: User = Depends(require_ad_admin)):
    rows = db.query(AdvEntryOrigin).filter(AdvEntryOrigin.status == "REVIEW").order_by(AdvEntryOrigin.id.asc()).limit(500).all()
    return {"origins": [{"contestant_id": r.contestant_id, "evidence": r.evidence} for r in rows]}


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
        raise HTTPException(status_code=409, detail=str(exc)) from None
    db.add(AuditTrail(table_name="adv_entry_origins", record_id=row.id, action="RESOLVE", old_values={"status": "REVIEW"},
                      new_values={"origin_kind": body.origin_kind, "note": body.note, "lines_priced": priced},
                      user_id=admin.id))
    db.commit()
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
        raise _err(exc) from None
    except FinancialIntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from None
    db.commit()
    return out


@admin_router.post("/allocations/{line_id}/release-held-sponsor")
def admin_release_held_sponsor(line_id: int, body: HeldSponsorBody, db: Session = Depends(deps.get_db),
                               admin: User = Depends(require_ad_admin)):
    _reauth(admin, body.current_password)
    try:
        line = sharing.release_held_sponsor(db, line_id=line_id, actor_id=admin.id, note=body.note)
    except camp.AdError as exc:
        db.rollback()
        raise _err(exc) from None
    db.commit()
    return {"id": line.id, "status": line.status, "beneficiary_user_id": line.beneficiary_user_id}


@admin_router.post("/adsense/import")
def admin_adsense_import(body: ImportBody, db: Session = Depends(deps.get_db), admin: User = Depends(require_ad_admin)):
    if body.end < body.start or (body.end - body.start).days > 62:
        raise HTTPException(status_code=400, detail="Choose a range of at most 62 days")
    run = sharing.import_adsense(db, start=body.start, end=body.end, actor_id=admin.id)
    db.commit()
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
        raise _err(exc) from None
    db.commit()
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
        raise _err(exc) from None
    except FinancialIntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from None
    db.commit()
    return out
