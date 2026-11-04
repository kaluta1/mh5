"""Ad serving decisions, impression capture, validation, charging and daily revenue recognition.

Decision (``decide``): eligible MyHigh5 campaign first (status, schedule, targeting, placement, approved
creative, pacing, frequency cap, budget), else Google AdSense fallback, else no fill. A MyHigh5 decision
atomically RESERVES the price of exactly one impression on the campaign and on its UTC day:

    UPDATE adv_campaigns SET reserved = reserved + :u
     WHERE id = :id AND status = 'ACTIVE' AND spent + reserved + :u <= budget_total

so concurrent decisions can never reserve more than the budget (or the daily cap); a charge can only
consume an existing reservation. Overspending is impossible by construction.

Viewability: MRC/IAB display standard - at least 50% of the ad's pixels in view for at least one
continuous second, measured by the client and re-checked here, plus page visible.

Validation (``validate_pending``): first VIEWABLE per decision only (unique), decision not expired,
same viewer as the decision, not a known bot user agent, viewer rate limit, no self-view (advertiser on
its own ad; creative on its own entry page). Valid MyHigh5 impressions are charged; invalid ones and
expired reservations release their reservation. AdSense impressions are never charged: they only count
for proportional attribution of Google earnings.

Recognition (``recognize_closed_days``): one idempotent journal per campaign per closed UTC day,
Dr 2320 / Cr 4020, cumulative and rounded down to the cent.

Advertising Phase A (ad_packages): the decision reserves ONE unit of the campaign's package (rate/1000 for
Standard and Video CPM, the rate for CPC / CPV / engagement; nothing for leads and daily bookings) and only
the package's billable event type charges that reservation. Other event types of the same decision are
validated as evidence (VALID / INVALID) and never touch money. Daily City bookings are served only to
signed-in viewers with a verified city (KYC address verified + city on the profile) and settled once per
booked UTC day (``settle_bookings``): the fixed fee is charged when the day reached the booking's minimum
delivery threshold of valid viewable impressions, otherwise it returns to the advertiser's credit, once. Every
decision records the viewer's verified city (signed-in members only): the evidence of a city's inventory. Six decimals throughout; whole cents only
at recognition (cumulative, rounded down), so no fraction of a cent is charged or lost.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re
import uuid
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.advertising_v2 import (AdvCampaign, AdvCampaignDay, AdvCreative, AdvImpressionEvent,
                                       AdvServeDecision)
from app.services import ad_attribution
from app.services import ad_campaigns as camp
from app.services import ad_packages as pk
from app.services.financial_integrity import money

logger = logging.getLogger(__name__)

VIEWABLE_MIN_MS = 1000
VIEWABLE_MIN_RATIO = Decimal("0.5")
LATE_EVENT_GRACE = timedelta(minutes=2)       # network delay allowed after a decision expires
BOT_UA = re.compile(r"bot|crawl|spider|slurp|headless|phantom|puppeteer|playwright|selenium|lighthouse|"
                    r"preview|fetch|curl|wget|python-requests|httpclient|monitor|pingdom|facebookexternalhit",
                    re.IGNORECASE)
ALLOWED_SLOTS = {
    "CONTEST_LISTING": ("SIDEBAR", "IN_FEED"),
    "CONTEST_ENTRY": ("SIDEBAR", "IN_CONTENT"),
    "FEED": ("SIDEBAR", "IN_FEED"),
    "POST": ("SIDEBAR", "IN_CONTENT"),
    "DISCOVERY": ("SIDEBAR", "IN_FEED"),
    "PROFILE": ("SIDEBAR", "IN_FEED"),
    "MARKETPLACE": ("IN_FEED",),
}
# Only units on an individual contest-entry page are attributable to that entry.
ATTRIBUTABLE_PAGE = "CONTEST_ENTRY"


def adsense_client() -> str:
    return (os.getenv("ADSENSE_CLIENT_ID") or "ca-pub-5582556318526474").strip()


def adsense_slot_for(slot_kind: str) -> Optional[str]:
    """AdSense ad unit per slot kind. Default: the responsive unit already used on /contests."""
    default = (os.getenv("ADSENSE_DEFAULT_SLOT") or "8189486989").strip()
    return (os.getenv(f"ADSENSE_SLOT_{slot_kind}") or default).strip() or None


def _secret() -> bytes:
    from app.core.config import settings

    return (getattr(settings, "SECRET_KEY", "") or "mh5-ad-viewer").encode("utf-8")


def viewer_hash_for_user(user_id: int) -> str:
    return hmac.new(_secret(), f"user:{int(user_id)}".encode(), hashlib.sha256).hexdigest()


def viewer_hash(user_id: Optional[int], ip: Optional[str], user_agent: Optional[str]) -> str:
    """Pseudonymous viewer key (no raw IP or user agent is stored)."""
    if user_id:
        return viewer_hash_for_user(user_id)
    return hmac.new(_secret(), f"anon:{ip or ''}|{(user_agent or '')[:300]}".encode(), hashlib.sha256).hexdigest()


def ua_hash(user_agent: Optional[str]) -> str:
    return hashlib.sha256((user_agent or "").encode("utf-8")).hexdigest()


def is_bot(user_agent: Optional[str]) -> bool:
    return not (user_agent or "").strip() or bool(BOT_UA.search(user_agent or ""))


# ---------------------------------------------------------------- decide

def _entry_is_public(db: Session, contestant_id: int):
    from app.models.contest_eligibility import ContestEntrySafety
    from app.models.contests import Contestant

    c = db.query(Contestant).filter(Contestant.id == contestant_id).first()
    if c is None or c.is_deleted or not c.is_active:
        return None
    safety = db.query(ContestEntrySafety).filter(ContestEntrySafety.contestant_id == c.id).first()
    if safety is not None and safety.exposure_status != "PUBLIC":
        return None                              # held / blocked / child-safety entries carry no ads
    return c


def _targets(campaign: AdvCampaign, *, page_type: str, slot_kind: str, country: Optional[str]) -> bool:
    if slot_kind not in (campaign.placements or []):
        return False
    t = campaign.targeting or {}
    if t.get("page_types") and page_type not in t["page_types"]:
        return False
    if t.get("countries") and (country or "").upper() not in t["countries"]:
        return False
    return True


def _paced(campaign: AdvCampaign, day_row: Optional[AdvCampaignDay], unit: Decimal, now: datetime) -> bool:
    """Even pacing of the daily cap over the UTC day (one impression of slack)."""
    if campaign.daily_cap is None:
        return True
    used = Decimal(str(day_row.spent + day_row.reserved)) if day_row else Decimal(0)
    elapsed = Decimal((now - datetime.combine(now.date(), time.min)).total_seconds()) / Decimal(86400)
    return used + unit <= Decimal(str(campaign.daily_cap)) * max(elapsed, Decimal("0.02")) + unit


def _day_row(db: Session, campaign_id: int, day: date) -> AdvCampaignDay:
    row = db.query(AdvCampaignDay).filter(AdvCampaignDay.campaign_id == campaign_id, AdvCampaignDay.day == day).first()
    if row is None:
        try:
            with db.begin_nested():
                row = AdvCampaignDay(campaign_id=campaign_id, day=day, spent=0, reserved=0)
                db.add(row)
                db.flush()
        except IntegrityError:
            row = db.query(AdvCampaignDay).filter(AdvCampaignDay.campaign_id == campaign_id,
                                                  AdvCampaignDay.day == day).one()
    return row


def _reserve(db: Session, campaign: AdvCampaign, unit: Decimal, day: date) -> bool:
    """Atomic: both the campaign budget and the daily cap, or nothing."""
    _day_row(db, campaign.id, day)
    try:
        with db.begin_nested():
            res = db.execute(
                update(AdvCampaign)
                .where(AdvCampaign.id == campaign.id, AdvCampaign.status == "ACTIVE",
                       AdvCampaign.spent + AdvCampaign.reserved + unit <= AdvCampaign.budget_total)
                .values(reserved=AdvCampaign.reserved + unit)
                .execution_options(synchronize_session="fetch"))
            if res.rowcount != 1:
                raise _NoReservation()
            cond = [AdvCampaignDay.campaign_id == campaign.id, AdvCampaignDay.day == day]
            if campaign.daily_cap is not None:
                cond.append(AdvCampaignDay.spent + AdvCampaignDay.reserved + unit <= Decimal(str(campaign.daily_cap)))
            res = db.execute(update(AdvCampaignDay).where(*cond)
                             .values(reserved=AdvCampaignDay.reserved + unit)
                             .execution_options(synchronize_session="fetch"))
            if res.rowcount != 1:
                raise _NoReservation()
    except _NoReservation:
        return False
    return True


class _NoReservation(Exception):
    pass


def verified_city(db: Session, user_id: Optional[int]) -> Optional[int]:
    """The viewer's attested city (ad_geo): signed-in, address-verified, with a current attestation for the
    unchanged profile city. Never a request header (cf-ipcountry / x-country are client-controlled)."""
    from app.services.ad_geo import verified_city as _attested

    return _attested(db, user_id)


def _campaign_rate(campaign: AdvCampaign, package) -> Optional[Decimal]:
    if package.code == pk.LEGACY_CODE:
        return Decimal(str(campaign.cpm_rate_usd)) if campaign.cpm_rate_usd is not None else None
    return Decimal(str(campaign.unit_rate_usd)) if campaign.unit_rate_usd is not None else None


def campaign_unit(campaign: AdvCampaign) -> Decimal:
    """The price of one billable event of this campaign (0 for leads and daily bookings)."""
    package = pk.of_model(campaign.pricing_model)
    if not pk.reserve_at_decision(package):
        return Decimal(0)
    rate = _campaign_rate(campaign, package)
    return pk.unit_charge(package, rate) if rate is not None else Decimal(0)


def _booked_today(db: Session, campaign: AdvCampaign, package, city_id: Optional[int], today: date) -> bool:
    from app.models.advertising_v2 import AdvBooking

    if package.booking != "CITY" or not city_id:
        return False                              # Daily Local has no verified areas yet (NOT READY)
    return db.query(AdvBooking.id).filter(AdvBooking.campaign_id == campaign.id, AdvBooking.scope == "CITY",
                                          AdvBooking.area_id == city_id, AdvBooking.day == today,
                                          AdvBooking.status == "BOOKED").first() is not None


def decide(db: Session, *, page_type: str, slot_kind: str, slot_key: str, contestant_id: Optional[int],
           viewer: str, country: Optional[str] = None, now: Optional[datetime] = None,
           allowed_sources: Optional[set] = None, viewer_user_id: Optional[int] = None) -> dict:
    """allowed_sources: the viewer's ad eligibility (interaction_safety.ad_eligibility) - 'myhigh5_ads'
    and/or 'adsense'. A source the viewer may not receive is never chosen."""
    now = now or datetime.utcnow()
    allowed_sources = {"myhigh5_ads", "adsense"} if allowed_sources is None else allowed_sources
    if slot_kind not in ALLOWED_SLOTS.get(page_type, ()):
        return {"fill": False, "reason": "PLACEMENT_NOT_ALLOWED"}
    if page_type == ATTRIBUTABLE_PAGE:
        if not contestant_id or _entry_is_public(db, int(contestant_id)) is None:
            return {"fill": False, "reason": "ENTRY_NOT_ELIGIBLE"}
    else:
        contestant_id = None                     # never attribute non-entry pages to an entry
    cfg = camp.get_settings(db)
    ttl = timedelta(seconds=max(60, int(cfg.reservation_ttl_seconds or 900)))
    decision_id = str(uuid.uuid4())
    # The viewer's verified city, recorded on every decision (any source): the evidence a Daily City booking
    # and a city's measured inventory rely on. Signed-in, address-verified members only; never geo-IP.
    city_id = verified_city(db, viewer_user_id)
    if "myhigh5_ads" in allowed_sources and cfg.campaigns_enabled and camp.pricing_state(cfg) == "CONFIGURED":
        candidates = (db.query(AdvCampaign)
                      .filter(AdvCampaign.status == "ACTIVE", AdvCampaign.start_at <= now, AdvCampaign.end_at > now,
                              AdvCampaign.spent + AdvCampaign.reserved < AdvCampaign.budget_total)
                      .order_by((AdvCampaign.spent / AdvCampaign.budget_total).asc(), AdvCampaign.id.asc())
                      .limit(50).all())
        today = now.date()
        for campaign in _fair_order(db, candidates, city_id, today):
            if not _targets(campaign, page_type=page_type, slot_kind=slot_kind, country=country):
                continue
            package = pk.of_model(campaign.pricing_model)
            if not pk.deliverable(cfg, package)[0]:
                continue                          # not ready, or switched off: never served
            if package.booking:
                if not _booked_today(db, campaign, package, city_id, today):
                    continue
                unit = Decimal(0)
            else:
                unit = campaign_unit(campaign)
                if unit <= 0:
                    continue
            seen = (db.query(func.count(AdvServeDecision.id))
                    .filter(AdvServeDecision.campaign_id == campaign.id, AdvServeDecision.viewer_hash == viewer,
                            AdvServeDecision.created_at >= datetime.combine(today, time.min)).scalar())
            if int(seen or 0) >= int(cfg.frequency_cap_per_day or 20):
                continue
            day_row = db.query(AdvCampaignDay).filter(AdvCampaignDay.campaign_id == campaign.id,
                                                      AdvCampaignDay.day == today).first()
            if not _paced(campaign, day_row, unit, now):
                continue
            creative_q = db.query(AdvCreative).filter(AdvCreative.campaign_id == campaign.id,
                                                      AdvCreative.review_status == "APPROVED")
            if package.billable_event in (pk.VIDEO_2S, pk.VIDEO_VIEW):
                creative_q = creative_q.filter(AdvCreative.creative_format == "VIDEO")
            creative = creative_q.order_by(func.random()).first()
            if creative is None:
                continue
            if unit > 0 and not _reserve(db, campaign, unit, today):
                continue
            legacy = package.code == pk.LEGACY_CODE
            db.add(AdvServeDecision(id=decision_id, slot_kind=slot_kind, page_type=page_type, slot_key=slot_key[:80],
                                    contestant_id=contestant_id, source="MYHIGH5", product="ORDINARY",
                                    campaign_id=campaign.id, creative_id=creative.id, reserved_amount=unit,
                                    reserved_day=today, state="RESERVED" if unit > 0 else "UNPAID",
                                    viewer_hash=viewer, expires_at=now + ttl, created_at=now, updated_at=now,
                                    package=None if legacy else package.code,
                                    viewer_user_id=int(viewer_user_id) if viewer_user_id else None,
                                    viewer_city_id=city_id))
            db.flush()
            return {"fill": True, "decision_id": decision_id, "source": "MYHIGH5", "sponsored_label": "Sponsored",
                    "creative": {"headline": creative.headline, "body": creative.body, "image_url": creative.image_url,
                                 "destination_url": creative.destination_url,
                                 # Clicks go through MyHigh5 (counted once, then redirected to the reviewed
                                 # URL), authorised by a signed token bound to this decision (D1).
                                 "click_url": f"/api/v1/ads/click/{decision_id}?t="
                                              f"{click_token(decision_id, campaign.id, creative.id, now + ttl)}"}}
    slot = adsense_slot_for(slot_kind) if (cfg.adsense_fallback_enabled and "adsense" in allowed_sources) else None
    if slot:
        db.add(AdvServeDecision(id=decision_id, slot_kind=slot_kind, page_type=page_type, slot_key=slot_key[:80],
                                contestant_id=contestant_id, source="ADSENSE", product="ADSENSE", adsense_slot=slot,
                                reserved_amount=0, state="UNPAID", viewer_hash=viewer, expires_at=now + ttl,
                                created_at=now, updated_at=now,
                                viewer_user_id=int(viewer_user_id) if viewer_user_id else None,
                                viewer_city_id=city_id))
        db.flush()
        return {"fill": True, "decision_id": decision_id, "source": "ADSENSE", "sponsored_label": "Sponsored",
                "adsense": {"client": adsense_client(), "slot": slot}}
    return {"fill": False, "reason": "NO_FILL"}


# ---------------------------------------------------------------- events

def record_event(db: Session, *, decision_id: str, event_id: str, event_type: str, visible_ms: Optional[int],
                 visible_ratio, page_visible: Optional[bool], user_agent: Optional[str], viewer: str,
                 now: Optional[datetime] = None, played_ms: Optional[int] = None, action: Optional[str] = None,
                 allow_click: bool = False) -> str:
    """Durable capture only (validated later). Returns RECORDED, DUPLICATE or UNKNOWN_DECISION. A CLICK is
    recorded only by the MyHigh5 click redirect (allow_click), never by a client beacon."""
    now = now or datetime.utcnow()
    if event_type not in pk.EVENT_TYPES or (event_type == pk.CLICK and not allow_click):
        return "INVALID_TYPE"
    if event_type == pk.CLICK and (action or "CTA_CLICK") not in pk.ENGAGEMENT_ACTIONS:
        return "UNSUPPORTED_ACTION"
    try:
        uuid.UUID(event_id)
        uuid.UUID(decision_id)
    except (ValueError, TypeError):
        return "INVALID_ID"
    if db.query(AdvServeDecision.id).filter(AdvServeDecision.id == decision_id).first() is None:
        return "UNKNOWN_DECISION"
    ratio = None
    if visible_ratio is not None:
        ratio = max(Decimal(0), min(Decimal(1), Decimal(str(visible_ratio)))).quantize(Decimal("0.001"))
    try:
        with db.begin_nested():
            db.add(AdvImpressionEvent(event_id=event_id, decision_id=decision_id, event_type=event_type,
                                      received_at=now, visible_ms=max(0, int(visible_ms or 0)), visible_ratio=ratio,
                                      page_visible=page_visible, ua_hash=ua_hash(user_agent), viewer_hash=viewer,
                                      is_bot_ua=is_bot(user_agent), validation_status="PENDING",
                                      played_ms=max(0, int(played_ms)) if played_ms is not None else None,
                                      action=(action or "CTA_CLICK") if event_type == pk.CLICK else None))
            db.flush()
    except IntegrityError:
        return "DUPLICATE"                        # same event id, or a second VIEWABLE for the decision
    return "RECORDED"


def _invalid(event: AdvImpressionEvent, reason: str, now: datetime) -> None:
    event.validation_status, event.invalid_reason, event.validated_at = "INVALID", reason, now


def _release(db: Session, decision: AdvServeDecision) -> None:
    if decision.state != "RESERVED":
        return
    unit = Decimal(str(decision.reserved_amount))
    db.execute(update(AdvCampaign).where(AdvCampaign.id == decision.campaign_id, AdvCampaign.reserved >= unit)
               .values(reserved=AdvCampaign.reserved - unit).execution_options(synchronize_session="fetch"))
    db.execute(update(AdvCampaignDay).where(AdvCampaignDay.campaign_id == decision.campaign_id,
                                            AdvCampaignDay.day == decision.reserved_day,
                                            AdvCampaignDay.reserved >= unit)
               .values(reserved=AdvCampaignDay.reserved - unit).execution_options(synchronize_session="fetch"))
    decision.state = "RELEASED"


def _charge(db: Session, decision: AdvServeDecision) -> Decimal:
    unit = Decimal(str(decision.reserved_amount))
    res = db.execute(update(AdvCampaign).where(AdvCampaign.id == decision.campaign_id, AdvCampaign.reserved >= unit)
                     .values(reserved=AdvCampaign.reserved - unit, spent=AdvCampaign.spent + unit)
                     .execution_options(synchronize_session="fetch"))
    if res.rowcount != 1:
        raise RuntimeError("Reservation missing for a charge")       # cannot happen: rolled back
    db.execute(update(AdvCampaignDay).where(AdvCampaignDay.campaign_id == decision.campaign_id,
                                            AdvCampaignDay.day == decision.reserved_day,
                                            AdvCampaignDay.reserved >= unit)
               .values(reserved=AdvCampaignDay.reserved - unit, spent=AdvCampaignDay.spent + unit)
               .execution_options(synchronize_session="fetch"))
    decision.state = "CHARGED"
    return unit


def _earning_day(event_time: datetime, source: str) -> date:
    """UTC accounting day; AdSense impressions use the AdSense reporting time zone so they fall in the
    same bucket as Google's report (ADSENSE_REPORTING_TIMEZONE, default UTC)."""
    if source != "ADSENSE":
        return event_time.date()
    tz_name = (os.getenv("ADSENSE_REPORTING_TIMEZONE") or "UTC").strip()
    try:
        from zoneinfo import ZoneInfo
        from datetime import timezone

        return event_time.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(tz_name)).date()
    except Exception:  # noqa: BLE001 - unknown zone: UTC
        return event_time.date()


def _self_view(db: Session, event: AdvImpressionEvent, decision: AdvServeDecision) -> bool:
    if decision.campaign_id:
        campaign = db.query(AdvCampaign).filter(AdvCampaign.id == decision.campaign_id).first()
        if campaign and event.viewer_hash == viewer_hash_for_user(campaign.advertiser_user_id):
            return True
    if decision.contestant_id:
        from app.models.contests import Contestant

        c = db.query(Contestant).filter(Contestant.id == decision.contestant_id).first()
        if c is not None:
            att = ad_attribution.attribute(db, c)
            ids = {c.user_id, att.creative_user_id}
            if any(uid and event.viewer_hash == viewer_hash_for_user(uid) for uid in ids):
                return True
    return False


def _quality_problem(db: Session, event: AdvImpressionEvent, decision: AdvServeDecision, now: datetime) -> Optional[str]:
    """The event-type qualification contract (server-side; the client only reports measurements, and every
    duration is bounded by server time: a client cannot claim more playback than time has passed)."""
    ratio = Decimal(str(event.visible_ratio or 0))
    since_decision_ms = int((event.received_at - decision.created_at).total_seconds() * 1000) \
        if decision.created_at else 0
    if event.event_type == pk.VIEWABLE:
        if (event.visible_ms or 0) < VIEWABLE_MIN_MS or ratio < VIEWABLE_MIN_RATIO:
            return "NOT_VIEWABLE"
        return None
    if event.event_type in (pk.VIDEO_2S, pk.VIDEO_VIEW):
        creative = db.query(AdvCreative).filter(AdvCreative.id == decision.creative_id).first() \
            if decision.creative_id else None
        if creative is None or creative.creative_format != "VIDEO" or not creative.video_duration_ms:
            return "NOT_A_VIDEO"
        played = int(event.played_ms or 0)
        if event.event_type == pk.VIDEO_2S:
            need = pk.VIDEO_IMPRESSION_MIN_MS
        else:
            from app.services.ad_video import cpv_threshold_ms

            need = cpv_threshold_ms(creative.video_duration_ms) or 10**9
        if ratio < VIEWABLE_MIN_RATIO or played < need:
            return "NOT_PLAYED"
        if played > since_decision_ms + 1000 or played > int(creative.video_duration_ms) + 1000:
            return "IMPOSSIBLE_PLAYBACK"           # more playback than wall-clock time or than the video
        return None
    if event.event_type == pk.CLICK:
        if (event.action or "CTA_CLICK") not in pk.ENGAGEMENT_ACTIONS:
            return "UNSUPPORTED_ACTION"
        if since_decision_ms < pk.CLICK_MIN_DELAY_MS:
            return "TOO_FAST"
        rendered = (db.query(AdvImpressionEvent.id)
                    .filter(AdvImpressionEvent.decision_id == decision.id,
                            AdvImpressionEvent.event_type.in_((pk.SERVED, pk.VIEWABLE))).first())
        if rendered is None:
            return "NOT_RENDERED"                  # a click on an ad that was never shown
        return None
    return "INVALID_TYPE"


def validate_pending(db: Session, *, limit: int = 500, now: Optional[datetime] = None) -> dict:
    """Validate captured events once each. Safe to run concurrently (SKIP LOCKED on PostgreSQL)."""
    now = now or datetime.utcnow()
    q = (db.query(AdvImpressionEvent).filter(AdvImpressionEvent.validation_status == "PENDING")
         .order_by(AdvImpressionEvent.id.asc()).limit(limit))
    if db.get_bind().dialect.name == "postgresql":
        q = q.with_for_update(skip_locked=True)
    counts = {"valid": 0, "invalid": 0}
    cfg = camp.get_settings(db)
    for event in q.all():
        if event.event_type == "SERVED":
            event.validation_status, event.validated_at = "VALID", now
            continue
        decision = (db.query(AdvServeDecision).filter(AdvServeDecision.id == event.decision_id)
                    .with_for_update().one())
        package = pk.of_model(None) if decision.source != "MYHIGH5" else pk.get(decision.package or pk.LEGACY_CODE)
        # Only the package's billable event type can charge (or release) the decision's reservation;
        # every other event is evidence. Standard CPM (and AdSense): VIEWABLE, exactly as before.
        billable = decision.source == "MYHIGH5" and event.event_type == package.billable_event \
            and decision.state != "UNPAID"
        reason = None
        if billable and (not cfg.campaigns_enabled or not pk.deliverable(cfg, package)[0]):
            reason = "PACKAGE_DISABLED"           # switched off: no new billable activity, reservation released
        elif billable and decision.state in ("CHARGED", "RELEASED"):
            reason = "EXPIRED" if decision.state == "RELEASED" else "DUPLICATE"
        elif event.received_at > decision.expires_at + LATE_EVENT_GRACE:
            reason = "EXPIRED"
        elif event.is_bot_ua:
            reason = "BOT"
        elif event.page_visible is False:
            reason = "HIDDEN"
        else:
            reason = _quality_problem(db, event, decision, now)
            if reason is None and event.viewer_hash != decision.viewer_hash:
                reason = "VIEWER_MISMATCH"
        if reason is None and event.event_type == pk.VIEWABLE:
            recent = (db.query(func.count(AdvImpressionEvent.id))
                      .filter(AdvImpressionEvent.viewer_hash == event.viewer_hash,
                              AdvImpressionEvent.event_type == "VIEWABLE",
                              AdvImpressionEvent.validation_status == "VALID",
                              AdvImpressionEvent.validated_at >= now - timedelta(hours=1)).scalar())
            if int(recent or 0) >= int(cfg.max_viewable_per_viewer_hour or 120):
                reason = "RATE_LIMIT"
        if reason is None and _self_view(db, event, decision):
            reason = "SELF_VIEW"
        if reason is None and decision.campaign_id:
            campaign = db.query(AdvCampaign).filter(AdvCampaign.id == decision.campaign_id).first()
            if campaign is None or (campaign.end_at and event.received_at > campaign.end_at + LATE_EVENT_GRACE):
                reason = "CAMPAIGN_ENDED"
        if reason is not None:
            _invalid(event, reason, now)
            if billable:
                _release(db, decision)
            counts["invalid"] += 1
            continue
        charged = _charge(db, decision) if billable else Decimal(0)
        event.validation_status, event.validated_at = "VALID", now
        event.package = package.code if decision.source == "MYHIGH5" else None
        event.source, event.product = decision.source, decision.product
        event.campaign_id, event.adsense_slot, event.charged_amount = decision.campaign_id, decision.adsense_slot, charged
        event.earning_day = _earning_day(event.received_at, decision.source)
        if decision.contestant_id and decision.page_type == ATTRIBUTABLE_PAGE:
            from app.models.contests import Contestant

            c = db.query(Contestant).filter(Contestant.id == decision.contestant_id).first()
            if c is not None:
                att = ad_attribution.attribute(db, c)
                event.contestant_id, event.origin_kind = att.contestant_id, att.origin_kind
                event.creative_user_id, event.sponsor_user_id = att.creative_user_id, att.sponsor_user_id
                event.sponsor_status, event.contest_level = att.sponsor_status, att.contest_level
                event.season_id, event.rule_version = att.season_id, att.rule_version
                # The earning event: whether each beneficiary may earn is decided now, once.
                from app.services import kyc_eligibility

                event.creative_kyc_approved = (kyc_eligibility.is_approved(db, att.creative_user_id)
                                               if att.creative_user_id else None)
                event.sponsor_kyc_approved = (kyc_eligibility.is_approved(db, att.sponsor_user_id)
                                              if att.sponsor_status == "VALID" and att.sponsor_user_id else None)
        counts["valid"] += 1
    db.flush()
    return counts


def expire_reservations(db: Session, *, now: Optional[datetime] = None) -> int:
    """Release reservations whose decision expired without a VIEWABLE event still waiting."""
    now = now or datetime.utcnow()
    rows = (db.query(AdvServeDecision).filter(AdvServeDecision.state == "RESERVED",
                                              AdvServeDecision.expires_at < now - LATE_EVENT_GRACE)
            .limit(2000).all())
    released = 0
    for decision in rows:
        billable = pk.get(decision.package or pk.LEGACY_CODE).billable_event or "VIEWABLE"
        waiting = (db.query(AdvImpressionEvent.id)
                   .filter(AdvImpressionEvent.decision_id == decision.id, AdvImpressionEvent.event_type == billable,
                           AdvImpressionEvent.validation_status == "PENDING").first())
        if waiting:
            continue
        locked = db.query(AdvServeDecision).filter(AdvServeDecision.id == decision.id).with_for_update().one()
        if locked.state == "RESERVED":
            _release(db, locked)
            released += 1
    db.flush()
    return released


def complete_due_campaigns(db: Session, *, now: Optional[datetime] = None) -> int:
    now = now or datetime.utcnow()
    done = 0
    for c in db.query(AdvCampaign).filter(AdvCampaign.status.in_(("ACTIVE", "PAUSED"))).with_for_update().all():
        remaining = Decimal(str(c.budget_total)) - Decimal(str(c.spent))
        unit = campaign_unit(c)
        if c.end_at and c.end_at <= now:
            camp.complete_campaign(db, c, reason="ENDED")
            done += 1
        elif unit > 0 and remaining < unit and Decimal(str(c.reserved)) == 0:
            camp.complete_campaign(db, c, reason="BUDGET_EXHAUSTED")
            done += 1
    for c in db.query(AdvCampaign).filter(AdvCampaign.status.in_(camp.CLOSED_STATUSES),
                                          AdvCampaign.settled_at.is_(None)).with_for_update().all():
        camp.settle_campaign(db, c, reason=c.completion_reason or c.status)
    db.flush()
    return done


# ---------------------------------------------------------------- recognition

def recognize_closed_days(db: Session, *, now: Optional[datetime] = None) -> int:
    """Dr 2320 / Cr 4020 per campaign per closed UTC day (idempotent). Cumulative, rounded down."""
    from app.services.new_model_ledger import Line, PostingType, post_entry

    now = now or datetime.utcnow()
    posted = 0
    days = (db.query(AdvCampaignDay).filter(AdvCampaignDay.day < now.date(),
                                            AdvCampaignDay.recognized_at.is_(None))
            .order_by(AdvCampaignDay.campaign_id.asc(), AdvCampaignDay.day.asc()).with_for_update().all())
    for day in days:
        if Decimal(str(day.reserved)) > 0:
            continue                                  # a late reservation of that day is still open
        cumulative = (db.query(func.coalesce(func.sum(AdvCampaignDay.spent), 0))
                      .filter(AdvCampaignDay.campaign_id == day.campaign_id, AdvCampaignDay.day <= day.day).scalar())
        before = (db.query(func.coalesce(func.sum(AdvCampaignDay.spent), 0))
                  .filter(AdvCampaignDay.campaign_id == day.campaign_id, AdvCampaignDay.day < day.day).scalar())
        amount = camp.floor_cents(cumulative) - camp.floor_cents(before)
        if amount <= 0:
            day.recognized_at = now                  # nothing (or under a cent) to post: the day is closed
            continue
        campaign = db.query(AdvCampaign).filter(AdvCampaign.id == day.campaign_id).one()
        entry = post_entry(
            db, source_type=camp.SOURCE_AD_CAMPAIGN, source_id=day.campaign_id, posting_type=PostingType.RECOGNITION,
            key_suffix=day.day.isoformat(),
            lines=[Line(camp.CREDIT_ACCOUNT, debit=amount,
                        description=f"Advertiser credit used - User #{campaign.advertiser_user_id}"),
                   Line(camp.ORDINARY_REVENUE_ACCOUNT, credit=amount,
                        description="Ordinary MyHigh5 advertising revenue (validated viewable impressions)")],
            description=f"Ad delivery recognized - campaign {day.campaign_id} - {day.day.isoformat()}",
            entry_date=datetime.combine(day.day, time.max).replace(microsecond=0),
        )
        day.recognized_journal_id, day.recognized_at = entry.id, now
        posted += 1
    db.flush()
    return posted


def reverse_invalid_activity(db: Session, *, event_ids: list, reason: str, actor_id: int) -> dict:
    """Invalid traffic found after charging: credit the advertiser back and mark the events. Contest
    allocations of a finalized period are adjusted by ad_revenue_sharing.adjust_after_reversal."""
    from app.models.accounting import AuditTrail
    from app.services.new_model_ledger import Line, PostingType, post_entry

    if not (reason or "").strip():
        raise camp.AdError("NOTE_REQUIRED", "A reason is required", 400)
    now = datetime.utcnow()
    events = (db.query(AdvImpressionEvent).filter(AdvImpressionEvent.id.in_([int(i) for i in event_ids]),
                                                  AdvImpressionEvent.validation_status == "VALID",
                                                  AdvImpressionEvent.event_type.in_(
                                                      (pk.VIEWABLE, pk.VIDEO_2S, pk.VIDEO_VIEW, pk.CLICK)),
                                                  AdvImpressionEvent.reversed_at.is_(None))
              .with_for_update().all())
    per_campaign_day: dict = {}
    booking_keys: set = set()
    for e in events:
        e.reversed_at, e.reversal_reason = now, reason.strip()[:40]
        if e.event_type == pk.VIEWABLE and e.package == "daily_city":
            d = db.query(AdvServeDecision).filter(AdvServeDecision.id == e.decision_id).first()
            if d is not None and d.campaign_id and d.viewer_city_id and d.reserved_day:
                booking_keys.add((int(d.campaign_id), int(d.viewer_city_id), d.reserved_day))
        if e.campaign_id and Decimal(str(e.charged_amount)) > 0:
            per_campaign_day.setdefault((e.campaign_id, e.earning_day), Decimal(0))
            per_campaign_day[(e.campaign_id, e.earning_day)] += Decimal(str(e.charged_amount))
    credited = Decimal(0)
    for (campaign_id, day), amount in per_campaign_day.items():
        campaign = db.query(AdvCampaign).filter(AdvCampaign.id == campaign_id).with_for_update().one()
        day_row = _day_row(db, campaign_id, day)
        recognized = day_row.recognized_journal_id is not None
        campaign.spent = Decimal(str(campaign.spent)) - amount
        day_row.spent = Decimal(str(day_row.spent)) - amount
        if campaign.settled_at is not None:
            # already settled: the credit goes straight back to the advertiser's balance
            camp._movement(db, advertiser_id=campaign.advertiser_user_id, kind="RELEASE",
                           amount=money(amount), key=f"campaign:{campaign_id}:creditback:{day}:{now.timestamp()}",
                           campaign_id=campaign_id, note=f"Invalid activity credited back: {reason[:200]}",
                           actor_id=actor_id)
        if recognized and money(amount) > 0:
            post_entry(db, source_type=camp.SOURCE_AD_CAMPAIGN, source_id=campaign_id, posting_type=PostingType.REVERSAL,
                       key_suffix=f"invalid:{day.isoformat()}:{int(now.timestamp())}",
                       lines=[Line(camp.ORDINARY_REVENUE_ACCOUNT, debit=money(amount),
                                   description="Invalid activity: advertising revenue reversed"),
                              Line(camp.CREDIT_ACCOUNT, credit=money(amount),
                                   description=f"Advertiser credited back - User #{campaign.advertiser_user_id}")],
                       description=f"Invalid ad activity credited back - campaign {campaign_id} - {day.isoformat()}")
        credited += amount
    db.flush()                                    # the reversed events must be visible to the recount
    bookings_reversed = reassess_bookings(db, booking_keys, reason=reason, actor_id=actor_id, now=now) \
        if booking_keys else 0
    db.add(AuditTrail(table_name="adv_impression_events", record_id=0, action="REVERSE_INVALID",
                      old_values=None, new_values={"events": [e.id for e in events], "reason": reason[:200],
                                                   "credited": str(credited),
                                                   "bookings_reversed": bookings_reversed}, user_id=actor_id))
    db.flush()
    return {"reversed": len(events), "credited": str(money(credited)), "bookings_reversed": bookings_reversed,
            "periods": sorted({e.earning_day.strftime("%Y-%m") for e in events if e.earning_day})}


# ---------------------------------------------------------------- click authorisation (review defect D1)
#
# Members sign in with a bearer token sent in a header, which a browser navigation cannot carry, so a click
# must not be attributed by who the click request appears to be. The decision issues a short-lived signed
# click token bound to (decision, campaign, creative, expiry). The click redirect verifies it, records the
# CLICK against the DECISION's viewer (the member identified when the ad was served, never a browser-supplied
# id) and the database's unique (decision, CLICK) makes it single-use: replays and concurrent clicks record
# nothing more. The token carries no session or credential and is never forwarded to the destination.

def _click_sig(decision_id: str, campaign_id, creative_id, exp: int) -> str:
    import base64

    msg = f"ad-click:v1:{decision_id}:{int(campaign_id or 0)}:{int(creative_id or 0)}:{int(exp)}".encode()
    return base64.urlsafe_b64encode(hmac.new(_secret(), msg, hashlib.sha256).digest()).decode().rstrip("=")


def click_token(decision_id: str, campaign_id, creative_id, expires_at: datetime) -> str:
    exp = int((expires_at - datetime(1970, 1, 1)).total_seconds())
    return f"{exp}.{_click_sig(decision_id, campaign_id, creative_id, exp)}"


def check_click_token(decision: AdvServeDecision, token: Optional[str], now: datetime) -> Optional[str]:
    """None when the token authorises a click on this decision now; otherwise the refusal reason."""
    try:
        exp_s, sig = str(token or "").split(".", 1)
        exp = int(exp_s)
    except (ValueError, TypeError):
        return "INVALID_TOKEN"
    expected = _click_sig(decision.id, decision.campaign_id, decision.creative_id, exp)
    if not hmac.compare_digest(expected, sig):
        return "INVALID_TOKEN"                      # tampered, or minted for another decision / campaign
    if exp != int((decision.expires_at - datetime(1970, 1, 1)).total_seconds()):
        return "INVALID_TOKEN"
    if now > decision.expires_at + LATE_EVENT_GRACE:
        return "EXPIRED"
    return None


def record_click(db: Session, *, decision_id: str, token: Optional[str], user_agent: Optional[str],
                 now: Optional[datetime] = None) -> str:
    """Record ONE click for a served MyHigh5 ad, authorised by its click token. Returns RECORDED, DUPLICATE,
    INVALID_TOKEN, EXPIRED or UNKNOWN_DECISION. Billing happens later, in validation (bot, self-click, 1 s
    rule, rendered ad, package switched on)."""
    now = now or datetime.utcnow()
    try:
        uuid.UUID(decision_id)
    except (ValueError, TypeError):
        return "UNKNOWN_DECISION"
    decision = db.query(AdvServeDecision).filter(AdvServeDecision.id == decision_id).first()
    if decision is None or decision.source != "MYHIGH5":
        return "UNKNOWN_DECISION"
    problem = check_click_token(decision, token, now)
    if problem:
        return problem
    return record_event(db, decision_id=decision_id, event_id=str(uuid.uuid4()), event_type=pk.CLICK,
                        visible_ms=None, visible_ratio=None, page_visible=None, user_agent=user_agent,
                        viewer=decision.viewer_hash, now=now, action="CTA_CLICK", allow_click=True)


def _rotation_key(campaign_id: int, today: date, city_id: int) -> int:
    """Deterministic tie-break that does not favour low campaign ids (changes every day and city)."""
    return int(hashlib.sha256(f"rotation:{campaign_id}:{today.isoformat()}:{city_id}".encode()).hexdigest()[:12], 16)


def _fair_order(db: Session, candidates: list, city_id: Optional[int], today: date) -> list:
    """Daily City campaigns booked for this viewer's city today come first, least-delivered first relative
    to their own threshold (decisions served today to verified residents), so non-exclusive bookings share
    the city fairly; ties are broken by a daily hash, never by campaign id. Other campaigns keep the
    existing order (lowest spend ratio first)."""
    from fractions import Fraction

    from app.models.advertising_v2 import AdvBooking

    booking_ids = [c.id for c in candidates if pk.of_model(c.pricing_model).booking]
    if not city_id or not booking_ids:
        return candidates
    served = dict(db.query(AdvServeDecision.campaign_id, func.count(AdvServeDecision.id))
                  .filter(AdvServeDecision.campaign_id.in_(booking_ids), AdvServeDecision.reserved_day == today,
                          AdvServeDecision.viewer_city_id == city_id)
                  .group_by(AdvServeDecision.campaign_id).all())
    need = dict(db.query(AdvBooking.campaign_id, AdvBooking.min_impressions)
                .filter(AdvBooking.campaign_id.in_(booking_ids), AdvBooking.scope == "CITY",
                        AdvBooking.area_id == city_id, AdvBooking.day == today, AdvBooking.status == "BOOKED").all())
    order = {c.id: i for i, c in enumerate(candidates)}

    def key(c):
        if c.id in need:
            return (0, Fraction(int(served.get(c.id, 0)), max(1, int(need[c.id] or 1))),
                    _rotation_key(c.id, today, city_id), 0)
        return (1, Fraction(0), 0, order[c.id])

    return sorted(candidates, key=key)


def _credit_back(db: Session, campaign: AdvCampaign, day: date, amount: Decimal, *, journal_suffix: str,
                 movement_key: str, note: str, actor_id: Optional[int], release_budget: bool) -> None:
    """Undo `amount` already charged to `campaign` on `day` (caller holds the campaign lock, and the
    reversed item's own row lock guarantees once-only). Ledger: Dr 4020 / Cr 2320 only when the day was
    already recognized (otherwise recognition simply posts less). Credit: back to the advertiser's free
    credit when the campaign is settled, or always when release_budget (a booked fee leaves the campaign's
    budget, as for a zero-delivery day). Idempotency keys come from the reversed item."""
    from app.services.new_model_ledger import Line, PostingType, post_entry

    amount = Decimal(str(amount))
    if amount <= 0:
        return
    day_row = _day_row(db, campaign.id, day)
    recognized = day_row.recognized_journal_id is not None
    if Decimal(str(campaign.spent)) < amount or Decimal(str(day_row.spent)) < amount:
        raise camp.AdError("REVERSAL_EXCEEDS_CHARGE", "The amount to reverse is larger than what was charged")
    campaign.spent = Decimal(str(campaign.spent)) - amount
    day_row.spent = Decimal(str(day_row.spent)) - amount
    if release_budget and campaign.settled_at is None:
        campaign.budget_total = Decimal(str(campaign.budget_total)) - amount
    if campaign.settled_at is not None or release_budget:
        camp._movement(db, advertiser_id=campaign.advertiser_user_id, kind="RELEASE", amount=money(amount),
                       key=movement_key, campaign_id=campaign.id, note=note[:300], actor_id=actor_id)
    if recognized and money(amount) > 0:
        post_entry(db, source_type=camp.SOURCE_AD_CAMPAIGN, source_id=campaign.id, posting_type=PostingType.REVERSAL,
                   key_suffix=journal_suffix,
                   lines=[Line(camp.ORDINARY_REVENUE_ACCOUNT, debit=money(amount),
                               description="Advertising charge reversed"),
                          Line(camp.CREDIT_ACCOUNT, credit=money(amount),
                               description=f"Advertiser credited back - User #{campaign.advertiser_user_id}")],
                   description=f"Advertising charge reversed - campaign {campaign.id} - {day.isoformat()} - "
                               f"{journal_suffix}")
    db.flush()


def reassess_bookings(db: Session, keys: set, *, reason: str, actor_id: Optional[int],
                      now: Optional[datetime] = None) -> int:
    """After invalid activity was reversed: every EARNED booked day in `keys` ((campaign, city, day)) whose
    valid, unreversed viewable impressions fell below its booked threshold is REVERSED - the fee returns to
    the advertiser's credit exactly once (movement booking:<id>:reversal, journal booking-reversal:<id>)."""
    from app.models.advertising_v2 import AdvBooking

    now = now or datetime.utcnow()
    reversed_count = 0
    for campaign_id, city_id, day in sorted(keys):
        campaign = db.query(AdvCampaign).filter(AdvCampaign.id == campaign_id).with_for_update().one()
        rows = (db.query(AdvBooking).filter(AdvBooking.campaign_id == campaign_id, AdvBooking.scope == "CITY",
                                            AdvBooking.area_id == city_id, AdvBooking.day == day,
                                            AdvBooking.status == "EARNED").with_for_update().all())
        for booking in rows:
            valid = (db.query(func.count(AdvImpressionEvent.id))
                     .join(AdvServeDecision, AdvServeDecision.id == AdvImpressionEvent.decision_id)
                     .filter(AdvServeDecision.campaign_id == campaign_id, AdvServeDecision.reserved_day == day,
                             AdvServeDecision.viewer_city_id == city_id, AdvImpressionEvent.event_type == pk.VIEWABLE,
                             AdvImpressionEvent.validation_status == "VALID", AdvImpressionEvent.reversed_at.is_(None))
                     .scalar()) or 0
            if int(valid) >= max(1, int(booking.min_impressions or 1)):
                booking.valid_impressions = int(valid)
                continue
            _credit_back(db, campaign, booking.day, Decimal(str(booking.charged_amount)),
                         journal_suffix=f"booking-reversal:{booking.id}", movement_key=f"booking:{booking.id}:reversal",
                         note=f"Booked day {booking.day.isoformat()} fell below its threshold after invalid "
                              f"activity: fee returned ({reason[:150]})", actor_id=actor_id, release_budget=True)
            booking.status, booking.valid_impressions = "REVERSED", int(valid)
            booking.reversed_at, booking.reversal_reason = now, (reason or "")[:200]
            reversed_count += 1
    db.flush()
    return reversed_count


def run_cycle(session_factory) -> dict:
    """One worker pass: validate, expire, complete/settle, recognize. Each step commits on its own."""
    result = {}
    from app.services.ad_leads import expire_unanswered

    for name, fn in (("validated", validate_pending), ("expired", expire_reservations),
                     ("leads_expired", expire_unanswered),
                     ("bookings", settle_bookings), ("completed", complete_due_campaigns),
                     ("recognized", recognize_closed_days)):
        db = session_factory()
        try:
            result[name] = fn(db)
            db.commit()
            camp.send_pending(db)          # campaign emails (completed / budget used), after the commit only
        except Exception as exc:  # noqa: BLE001 - one failing step must not stop the others
            db.rollback()
            camp.discard_pending(db)
            logger.error("Ad delivery step %s failed: %s", name, type(exc).__name__)
            result[name] = "ERROR"
        finally:
            db.close()
    return result


# ---------------------------------------------------------------- direct charges (leads, booked days)

def charge_direct(db: Session, campaign_id: int, amount: Decimal, day: date) -> bool:
    """Charge an amount that was not reserved at a serving decision (an accepted lead, an earned booked
    day): atomic against the remaining budget, so concurrent charges can never exceed it. False = refused."""
    amount = Decimal(str(amount))
    if amount <= 0:
        return False
    _day_row(db, campaign_id, day)
    try:
        with db.begin_nested():
            res = db.execute(update(AdvCampaign)
                             .where(AdvCampaign.id == campaign_id,
                                    AdvCampaign.spent + AdvCampaign.reserved + amount <= AdvCampaign.budget_total)
                             .values(spent=AdvCampaign.spent + amount)
                             .execution_options(synchronize_session="fetch"))
            if res.rowcount != 1:
                raise _NoReservation()
            db.execute(update(AdvCampaignDay).where(AdvCampaignDay.campaign_id == campaign_id,
                                                    AdvCampaignDay.day == day)
                       .values(spent=AdvCampaignDay.spent + amount).execution_options(synchronize_session="fetch"))
    except _NoReservation:
        return False
    return True


BOOKING_SETTLE_GRACE = timedelta(hours=2)    # late beacons of the day are validated first


def settle_bookings(db: Session, *, now: Optional[datetime] = None) -> int:
    """Settle every booked day that is over, once (row lock + status). EARNED: at least the booking's
    min_impressions valid, unreversed viewable impressions of the campaign that day in the booked area (the
    decision's verified city) -> the fixed fee is charged, never more. RETURNED: fewer -> the fee leaves the
    campaign budget and
    returns to the advertiser's credit (idempotent movement booking:<id>:return). No earning of any kind is
    created here; the impression counts (all placements, and contest-entry ones apart) are kept for Phase B."""
    from app.models.advertising_v2 import AdvBooking

    now = now or datetime.utcnow()
    settled = 0
    due = (db.query(AdvBooking).filter(AdvBooking.status == "BOOKED",
                                       AdvBooking.day < (now - BOOKING_SETTLE_GRACE).date())
           .order_by(AdvBooking.campaign_id.asc(), AdvBooking.day.asc(), AdvBooking.id.asc()).limit(500).all())
    for row in due:
        campaign = db.query(AdvCampaign).filter(AdvCampaign.id == row.campaign_id).with_for_update().one()
        booking = db.query(AdvBooking).filter(AdvBooking.id == row.id).with_for_update().one()
        if booking.status != "BOOKED":
            continue
        if campaign.status in ("DRAFT", "PENDING_REVIEW", "CHANGES_REQUESTED", "REJECTED", "CANCELLED") \
                or not db.query(camp.AdvCreditMovement.id).filter(
                    camp.AdvCreditMovement.idempotency_key == f"campaign:{campaign.id}:allocate").first():
            # Never funded or never served: no fee is owed; the unspent budget returns through settle_campaign.
            booking.status, booking.settled_at = "CANCELLED", now
            settled += 1
            continue
        pending = (db.query(AdvImpressionEvent.id).join(AdvServeDecision,
                                                        AdvServeDecision.id == AdvImpressionEvent.decision_id)
                   .filter(AdvServeDecision.campaign_id == campaign.id, AdvServeDecision.reserved_day == booking.day,
                           AdvImpressionEvent.validation_status == "PENDING").first())
        if pending is not None:
            continue                                  # validate the day's events first
        valid = (db.query(AdvServeDecision.page_type, func.count(AdvImpressionEvent.id))
                 .join(AdvImpressionEvent, AdvImpressionEvent.decision_id == AdvServeDecision.id)
                 .filter(AdvServeDecision.campaign_id == campaign.id, AdvServeDecision.reserved_day == booking.day,
                         AdvServeDecision.viewer_city_id == booking.area_id,
                         AdvImpressionEvent.event_type == pk.VIEWABLE, AdvImpressionEvent.validation_status == "VALID",
                         AdvImpressionEvent.reversed_at.is_(None))
                 .group_by(AdvServeDecision.page_type).all())
        by_page = {str(k): int(v) for k, v in valid}
        total = sum(by_page.values())
        booking.valid_impressions = total
        booking.entry_impressions = by_page.get(ATTRIBUTABLE_PAGE, 0)
        need = max(1, int(booking.min_impressions or 1))
        booking.evidence = {"impressions_by_page_type": by_page, "area": {"scope": booking.scope, "id": booking.area_id},
                            "min_impressions": need,
                            "settled_rule": "fee charged when the day reached the minimum valid viewable impressions "
                                            "from verified residents of the area"}
        price = Decimal(str(booking.price))
        if total >= need and charge_direct(db, campaign.id, price, booking.day):
            booking.status, booking.charged_amount = "EARNED", price
        else:
            # Zero delivery (or nothing left to charge): the whole fee goes back to reusable credit, once.
            res = db.execute(update(AdvCampaign)
                             .where(AdvCampaign.id == campaign.id,
                                    AdvCampaign.budget_total - price >= AdvCampaign.spent + AdvCampaign.reserved)
                             .values(budget_total=AdvCampaign.budget_total - price)
                             .execution_options(synchronize_session="fetch"))
            if res.rowcount != 1:
                logger.error("Booking %s could not be returned: campaign %s budget is inconsistent", booking.id,
                             campaign.id)
                continue
            camp._movement(db, advertiser_id=campaign.advertiser_user_id, kind="RELEASE", amount=money(price),
                           key=f"booking:{booking.id}:return", campaign_id=campaign.id,
                           note=f"Booked day {booking.day.isoformat()} had no valid delivery: fee returned")
            booking.status = "RETURNED"
        booking.settled_at = now
        settled += 1
    db.flush()
    return settled
