"""Advertising campaign & creative workflow (owner-approved requirements, 2026-11-05).

Built on the existing campaign service (ad_campaigns), package registry (ad_packages), delivery
(ad_delivery) and commission engine (new_model_revenue). Nothing here moves advertiser credit or
reserves budget: the existing ledger, locking, reservation and idempotency controls stay the only path.

  * creatives: public copy limits, preset call-to-action, approved display name, HTTPS destination,
    incomplete drafts, revisions of approved creatives (the approved version keeps serving until the
    revision is approved), structured review issues;
  * campaigns: explicit "all" / "list" targeting (clearing a list never widens a campaign), country codes
    checked against the MyHigh5 geography, page-type / placement compatibility, schedules entered in the
    advertiser's time zone and stored in UTC, start after approval;
  * the package catalog the form shows (price, unit, billable event, minimum, media, placements, state)
    and per-package estimates (never a CPM estimate for another package);
  * derived display status and non-delivery reasons, budget summary, daily report reconciled to the
    campaign's charged days, members' daily estimated earnings (never withdrawable);
  * the advertiser's direct-sponsor commission (20% / 40%) on recognized charges, behind its own switch.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import ROUND_DOWN, Decimal
from typing import Optional
from urllib.parse import urlsplit

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.accounting import AuditTrail
from app.models.advertising_v2 import AdvCampaign, AdvCampaignDay, AdvCreative
from app.services import ad_campaigns as camp
from app.services.ad_campaigns import AdError
from app.services.financial_integrity import money

HEADLINE_MAX = 40
DESCRIPTION_MAX = 125
DISPLAY_NAME_MAX = 60
CTA_PRESETS = {
    "LEARN_MORE": "Learn more", "SHOP_NOW": "Shop now", "SIGN_UP": "Sign up", "CONTACT_US": "Contact us",
    "BOOK_NOW": "Book now", "DOWNLOAD": "Download", "WATCH_MORE": "Watch more", "APPLY_NOW": "Apply now",
}
REVIEW_CATEGORIES = ("COPY", "MEDIA", "DESTINATION", "PLACEMENT")
ALL, LIST = "ALL", "LIST"
# Page types a slot is actually rendered on today (frontend AdSlot usages). The others are accepted by the
# delivery API but no page sends them yet, so a campaign limited to them would never serve.
RENDERED_PAGE_TYPES = ("FEED", "CONTEST_LISTING", "CONTEST_ENTRY")
PUBLIC_FIELDS = ("headline", "body", "display_name", "cta_code", "destination_url", "image_url", "video_url",
                 "video_poster_url")
OPEN_FOR_CREATIVES = ("DRAFT", "CHANGES_REQUESTED", "PENDING_REVIEW", "ACTIVE", "PAUSED")

# Media guidance per placement, derived from the rendered slots: in-feed and contest-entry units are fluid
# full-width cards; the desktop sidebar is 288 px wide (w-72), so a 6:5 image (600 x 500) fills it.
IMAGE_SPECS = {
    "IN_FEED": {"ratios": ["1:1", "4:5"], "recommended": ["1200x1200", "1200x1500"]},
    "SIDEBAR": {"ratios": ["6:5"], "recommended": ["600x500"], "slot_width_px": 288},
    "IN_CONTENT": {"ratios": ["1:1"], "recommended": ["1200x1200"]},
}
RATIOS = {"1:1": Decimal("1"), "4:5": Decimal("0.8"), "6:5": Decimal("1.2"), "9:16": Decimal("0.5625")}
RATIO_TOLERANCE = Decimal("0.03")
WORKFLOW_IMAGE_TYPES = ("image/jpeg", "image/png", "image/webp")
WORKFLOW_IMAGE_MAX_BYTES = 5 * 1024 * 1024
WORKFLOW_IMAGE_MIN_SIDE = 300


# ---------------------------------------------------------------- creatives

def _clean(value, limit: int, label: str) -> Optional[str]:
    text = " ".join(str(value or "").split())
    if len(text) > limit:
        raise AdError("TEXT_TOO_LONG", f"The {label} can have at most {limit} characters", 400)
    return text or None


def destination(url: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """(normalized HTTPS URL, its domain). Never fetched server-side (no request to an advertiser URL)."""
    from app.services.advertising_integrity import AdvertisingIntegrityError, normalize_destination_url

    if not (url or "").strip():
        return None, None
    try:
        out = normalize_destination_url(url)
    except AdvertisingIntegrityError as exc:
        raise AdError("INVALID_URL", str(exc), 400) from None
    if not out.startswith("https://"):
        raise AdError("HTTPS_REQUIRED", "The destination must be an HTTPS address", 400)
    return out, domain_of(out)


def domain_of(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    host = (urlsplit(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host or None


def _image(campaign: AdvCampaign, image_url: Optional[str]) -> Optional[str]:
    from app.services.advertising_integrity import AdvertisingIntegrityError, normalize_destination_url

    if not image_url:
        return None
    if image_url.startswith(camp.UPLOAD_PREFIX):
        return camp.own_upload_url(campaign.advertiser_user_id, image_url)
    try:
        image = normalize_destination_url(image_url)
    except AdvertisingIntegrityError as exc:
        raise AdError("INVALID_URL", str(exc), 400) from None
    if not image.startswith("https://"):
        raise AdError("INVALID_URL", "Images must be served over HTTPS", 400)
    return image


def _fields(campaign: AdvCampaign, data: dict) -> dict:
    """Validated public fields present in `data` (limits are checked even in a draft)."""
    out = {}
    if "headline" in data:
        out["headline"] = _clean(data["headline"], HEADLINE_MAX, "headline")
    if "body" in data or "description" in data:
        out["body"] = _clean(data.get("body", data.get("description")), DESCRIPTION_MAX, "description")
    if "display_name" in data:
        out["display_name"] = _clean(data["display_name"], DISPLAY_NAME_MAX, "advertiser display name")
    if "cta_code" in data:
        code = (data["cta_code"] or "").strip().upper() or None
        if code is not None and code not in CTA_PRESETS:
            raise AdError("INVALID_CTA", "Choose a call-to-action from the list", 400)
        out["cta_code"] = code
    if "destination_url" in data:
        out["destination_url"] = destination(data["destination_url"])[0]
    if "image_url" in data:
        out["image_url"] = _image(campaign, data["image_url"])
    return out


def missing_for_review(cr: AdvCreative) -> list:
    """What a creative still needs before it can be submitted for review."""
    missing = []
    if not (cr.headline or "").strip():
        missing.append("headline")
    elif len(cr.headline) > HEADLINE_MAX and cr.review_status in ("DRAFT",):
        missing.append("headline_length")
    if not (cr.display_name or "").strip():
        missing.append("display_name")
    if not cr.cta_code:
        missing.append("cta_code")
    if not cr.destination_url or not str(cr.destination_url).startswith("https://"):
        missing.append("destination_url")
    return missing


def create_creative(db: Session, campaign: AdvCampaign, data: dict, *, actor_id: Optional[int],
                    draft: bool = True) -> AdvCreative:
    """A new creative. Saved as an incomplete DRAFT, or straight to review (PENDING) when complete and
    `draft` is False. Never served before an administrator approves it."""
    if campaign.status not in OPEN_FOR_CREATIVES:
        raise AdError("CAMPAIGN_CLOSED", "Creatives cannot be added to a closed campaign")
    fields = _fields(campaign, data)
    cr = AdvCreative(campaign_id=campaign.id, review_status="DRAFT",
                     destination_url=fields.pop("destination_url", None) or "", **fields)
    db.add(cr)
    db.flush()
    if not draft:
        _to_review(cr)
    _audit(db, cr, actor_id, "CREATE", {"status": cr.review_status})
    db.flush()
    return cr


def _to_review(cr: AdvCreative) -> None:
    missing = missing_for_review(cr)
    if missing:
        raise AdError("CREATIVE_INCOMPLETE", f"Complete the creative before review: {', '.join(missing)}", 400)
    cr.review_status, cr.reviewed_at, cr.reviewed_by_user_id = "PENDING", None, None


def _audit(db: Session, cr: AdvCreative, actor_id: Optional[int], action: str, new: dict) -> None:
    db.add(AuditTrail(table_name="adv_creatives", record_id=cr.id or 0, action=action, old_values=None,
                      new_values={k: (str(v) if v is not None else None) for k, v in new.items()}, user_id=actor_id))


_COPY_FIELDS = ("headline", "body", "display_name", "cta_code", "destination_url", "image_url", "image_mime",
                "image_bytes", "image_width", "image_height", "creative_format", "video_url", "video_mime",
                "video_bytes", "video_duration_ms", "video_poster_url", "video_width", "video_height")


def _revision_of(db: Session, cr: AdvCreative) -> AdvCreative:
    """The open revision of an APPROVED creative (one at a time), or a new DRAFT copy of it. The approved row
    is locked first, so two concurrent edits can never open two revisions."""
    db.query(AdvCreative.id).filter(AdvCreative.id == cr.id).with_for_update().first()
    pending = (db.query(AdvCreative).filter(AdvCreative.supersedes_creative_id == cr.id,
                                            AdvCreative.review_status.in_(("DRAFT", "PENDING", "REJECTED")))
               .order_by(AdvCreative.id.desc()).with_for_update().first())
    if pending is not None:
        if pending.review_status == "REJECTED":
            pending.review_status = "DRAFT"
        return pending
    target = AdvCreative(campaign_id=cr.campaign_id, supersedes_creative_id=cr.id, review_status="DRAFT",
                         **{k: getattr(cr, k) for k in _COPY_FIELDS})
    db.add(target)
    db.flush()
    return target


def edit_creative(db: Session, campaign: AdvCampaign, cr: AdvCreative, data: dict, *,
                  actor_id: Optional[int]) -> AdvCreative:
    """Edit a creative. A DRAFT / PENDING / REJECTED creative is edited in place (a PENDING one stays in
    review with its new content; a REJECTED one becomes a DRAFT again). Changing any public field of an
    APPROVED creative creates a revision that needs a fresh approval; the approved version keeps serving
    until then. Returns the creative that now holds the edit."""
    if campaign.status not in OPEN_FOR_CREATIVES:
        raise AdError("CAMPAIGN_CLOSED", "The campaign is closed")
    if cr.review_status == "ARCHIVED":
        raise AdError("CREATIVE_ARCHIVED", "This version was replaced by a newer approved version")
    fields = _fields(campaign, data)
    changed = {k: v for k, v in fields.items() if getattr(cr, k) != v}
    if not changed:
        return cr
    if cr.review_status == "APPROVED":
        target = _revision_of(db, cr)
        for k, v in changed.items():
            setattr(target, k, v)
        _audit(db, target, actor_id, "REVISION", {"supersedes": cr.id, "fields": ",".join(sorted(changed))})
        db.flush()
        return target
    for k, v in changed.items():
        setattr(cr, k, v)
    if cr.review_status == "REJECTED":
        cr.review_status = "DRAFT"
    if cr.review_status == "PENDING":
        cr.reviewed_at, cr.reviewed_by_user_id = None, None
    _audit(db, cr, actor_id, "EDIT", {"fields": ",".join(sorted(changed))})
    db.flush()
    return cr


def submit_creative(db: Session, campaign: AdvCampaign, cr: AdvCreative, *, actor_id: Optional[int]) -> AdvCreative:
    """Send one complete DRAFT creative (a new one or a revision) to review."""
    if cr.review_status != "DRAFT":
        raise AdError("INVALID_STATE", "Only a draft creative can be submitted for review")
    if campaign.status not in OPEN_FOR_CREATIVES:
        raise AdError("CAMPAIGN_CLOSED", "The campaign is closed")
    _to_review(cr)
    _audit(db, cr, actor_id, "SUBMIT", {"status": cr.review_status})
    db.flush()
    return cr


def submit_campaign_creatives(db: Session, campaign: AdvCampaign) -> None:
    """At campaign submission: every complete draft goes to review; an incomplete one blocks submission
    (nothing is reviewed half-written). Campaigns with only legacy PENDING creatives are unchanged."""
    drafts = db.query(AdvCreative).filter(AdvCreative.campaign_id == campaign.id,
                                          AdvCreative.review_status == "DRAFT").all()
    for cr in drafts:
        _to_review(cr)


def on_creative_reviewed(db: Session, cr: AdvCreative, *, approved: bool) -> None:
    """An approved revision replaces the version it supersedes (that one is archived and never served
    again). A rejected revision leaves the approved version serving."""
    if approved and cr.supersedes_creative_id:
        old = (db.query(AdvCreative).filter(AdvCreative.id == cr.supersedes_creative_id).with_for_update().first())
        if old is not None and old.review_status == "APPROVED":
            old.review_status = "ARCHIVED"
            _audit(db, old, cr.reviewed_by_user_id, "ARCHIVE", {"replaced_by": cr.id})
    db.flush()


def normalize_issues(issues) -> Optional[list]:
    if not issues:
        return None
    out = []
    for item in issues:
        category = str((item or {}).get("category") or "").upper()
        if category not in REVIEW_CATEGORIES:
            raise AdError("INVALID_ISSUE", f"Issue categories: {', '.join(REVIEW_CATEGORIES)}", 400)
        note = " ".join(str((item or {}).get("note") or "").split())[:300]
        out.append({"category": category, "note": note})
    return out[:20]


def attach_media(db: Session, campaign: AdvCampaign, cr: AdvCreative, *, actor_id: Optional[int],
                 **media) -> AdvCreative:
    """New media on a creative. An APPROVED creative gets a revision (fresh approval), others in place."""
    if cr.review_status == "APPROVED":
        cr = _revision_of(db, cr)
    elif cr.review_status == "ARCHIVED":
        raise AdError("CREATIVE_ARCHIVED", "This version was replaced by a newer approved version")
    for k, v in media.items():
        setattr(cr, k, v)
    if cr.review_status == "REJECTED":
        cr.review_status = "DRAFT"
    if cr.review_status == "PENDING":
        cr.reviewed_at, cr.reviewed_by_user_id = None, None
    _audit(db, cr, actor_id, "MEDIA", {k: v for k, v in media.items() if not k.endswith("_url")})
    db.flush()
    return cr


def image_compatibility(width: Optional[int], height: Optional[int], mime: Optional[str] = None,
                        size: Optional[int] = None) -> dict:
    """Per placement: does the image fit the rendered slot? Never blocks an upload on ratio alone."""
    out = {}
    problems = []
    if mime and mime not in WORKFLOW_IMAGE_TYPES:
        problems.append("Use JPG, PNG or WebP")
    if size and int(size) > WORKFLOW_IMAGE_MAX_BYTES:
        problems.append("At most 5 MB")
    if width and height and min(int(width), int(height)) < WORKFLOW_IMAGE_MIN_SIDE:
        problems.append(f"At least {WORKFLOW_IMAGE_MIN_SIDE} px on each side")
    ratio = (Decimal(int(width)) / Decimal(int(height))) if width and height else None
    for placement, spec in IMAGE_SPECS.items():
        fits = ratio is not None and any(abs(ratio - RATIOS[r]) <= RATIO_TOLERANCE for r in spec["ratios"])
        out[placement] = {"compatible": bool(fits and not problems), "ratios": spec["ratios"],
                          "recommended": spec["recommended"],
                          "message": ("Fits this placement" if fits and not problems else
                                      "; ".join(problems) if problems else
                                      f"Use a {' or '.join(spec['ratios'])} image ({', '.join(spec['recommended'])})")}
    return out


def creative_view(db: Session, cr: AdvCreative) -> dict:
    out = camp.creative_payload(cr)
    out.update({
        "description": cr.body, "display_name": cr.display_name, "cta_code": cr.cta_code,
        "cta_label": CTA_PRESETS.get(cr.cta_code or ""), "destination_domain": domain_of(cr.destination_url),
        "sponsored_label": "Sponsored", "review_issues": cr.review_issues or [],
        "supersedes_creative_id": cr.supersedes_creative_id, "format": cr.creative_format or "IMAGE",
        "video": ({"url": cr.video_url, "mime": cr.video_mime, "bytes": cr.video_bytes,
                   "duration_ms": cr.video_duration_ms, "width": cr.video_width, "height": cr.video_height,
                   "poster_url": cr.video_poster_url} if cr.video_url else None),
        "missing_for_review": missing_for_review(cr) if cr.review_status == "DRAFT" else [],
        "serving": cr.review_status == "APPROVED",
        "compatibility": image_compatibility(cr.image_width, cr.image_height, cr.image_mime, cr.image_bytes)
        if cr.image_width else None,
        "limits": {"headline": HEADLINE_MAX, "description": DESCRIPTION_MAX, "display_name": DISPLAY_NAME_MAX},
    })
    return out


# ---------------------------------------------------------------- targeting and schedule

def _mode(value: Optional[str], items: list) -> str:
    if value in (ALL, LIST):
        return value
    if value not in (None, ""):
        raise AdError("INVALID_TARGETING", "Targeting mode must be ALL or LIST", 400)
    return LIST if items else ALL           # campaigns written before the workflow: a list means LIST


def known_countries(db: Session) -> dict:
    from app.models.geography import Country

    return {str(code).upper(): name for code, name in db.query(Country.code, Country.name)
            .filter(Country.code.isnot(None)).all() if code and len(str(code)) == 2}


def normalize_targeting(db: Session, requested: dict, current: Optional[dict] = None) -> dict:
    """{"countries_mode", "countries", "page_types_mode", "page_types"}. LIST with nothing selected is
    refused: clearing a selection never silently widens a campaign to everything."""
    current = dict(current or {})
    out = {}
    for key, mode_key in (("countries", "countries_mode"), ("page_types", "page_types_mode")):
        if key in requested or mode_key in requested:
            items = requested.get(key, current.get(key) if mode_key in requested else None)
            items = list(items or [])
            mode = requested.get(mode_key) or (current.get(mode_key) if key in requested and current.get(mode_key)
                                               else None)
            if mode is None and key in requested and current.get(key):
                mode = LIST                 # an existing list being edited stays a list
            mode = _mode(mode, items)
        else:
            items = list(current.get(key) or [])
            mode = _mode(current.get(mode_key), items)
        if mode == ALL:
            items = []
        elif not items:
            raise AdError("TARGETING_EMPTY", f"Choose at least one {'country' if key == 'countries' else 'page type'}"
                                             f" or select all eligible", 400)
        out[key], out[mode_key] = items, mode
    countries = [str(c).strip().upper() for c in out["countries"]]
    if any(len(c) != 2 or not c.isalpha() for c in countries):
        raise AdError("INVALID_TARGETING", "Countries must be two-letter codes", 400)
    known = known_countries(db)
    if known:
        unknown = [c for c in countries if c not in known]
        if unknown:
            raise AdError("UNKNOWN_COUNTRY", f"Unknown country code(s): {', '.join(unknown)}", 400)
    out["countries"] = sorted(set(countries))
    pages = list(dict.fromkeys(out["page_types"]))
    if any(p not in camp.PAGE_TYPES for p in pages):
        raise AdError("INVALID_TARGETING", f"Page types must be chosen from {', '.join(camp.PAGE_TYPES)}", 400)
    out["page_types"] = pages
    return out


def check_combinations(placements: list, targeting: dict) -> None:
    """Every chosen placement must exist on at least one chosen page type (ad_delivery.ALLOWED_SLOTS)."""
    from app.services.ad_delivery import ALLOWED_SLOTS

    pages = (targeting or {}).get("page_types") or list(RENDERED_PAGE_TYPES)
    for placement in placements or []:
        if not any(placement in ALLOWED_SLOTS.get(p, ()) for p in pages):
            raise AdError("PLACEMENT_PAGE_MISMATCH",
                          f"{placement} is not shown on any of the chosen page types", 400)


def check_timezone(tz: Optional[str]) -> Optional[str]:
    if tz in (None, ""):
        return None
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

    try:
        ZoneInfo(str(tz))
    except (ZoneInfoNotFoundError, ValueError):
        raise AdError("INVALID_TIMEZONE", "Unknown time zone", 400) from None
    return str(tz)


def to_utc(value: Optional[datetime], tz: Optional[str]) -> Optional[datetime]:
    """Stored and delivered in UTC. An offset is honoured (never silently dropped); a time without an
    offset is read in the campaign's time zone, else as UTC (the behaviour before the workflow)."""
    if value is None:
        return None
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    if tz:
        from zoneinfo import ZoneInfo

        return value.replace(tzinfo=ZoneInfo(tz)).astimezone(timezone.utc).replace(tzinfo=None)
    return value


def schedule_view(c: AdvCampaign) -> dict:
    tz = c.timezone or "UTC"
    from zoneinfo import ZoneInfo

    def local(dt):
        return dt.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(tz)).isoformat() if dt else None

    duration = None
    if c.start_at and c.end_at:
        duration = int((c.end_at - c.start_at).total_seconds() // 60)
    return {"timezone": tz, "start_at_utc": c.start_at.isoformat() + "Z" if c.start_at else None,
            "end_at_utc": c.end_at.isoformat() + "Z" if c.end_at else None,
            "start_at_local": local(c.start_at), "end_at_local": local(c.end_at),
            "starts_after_approval": c.start_at is None, "duration_minutes": duration,
            "launch": "Delivery starts automatically once the campaign is approved, at its start time "
                      "(or at approval when no start time is set)."}


# ---------------------------------------------------------------- packages

EVENT_DEFINITIONS = {   # from the ad_packages registry contract (owner-approved event definitions)
    "cpm": "A valid viewable impression: at least 50% of the ad in view for at least 1 second",
    "cpm_video": "A qualifying video impression: at least 2 seconds of continuous playback, at least 50% in view",
    "cpc": "A valid click through the MyHigh5 click redirect",
    "cpv": "A qualifying video view: at least 10 seconds of playback, or the whole video when shorter",
    "engagement": "A qualifying engagement: a click on the call-to-action (the only implemented action)",
    "lead": "An accepted lead (charged when the advertiser accepts it, never automatically)",
    "daily_local": "One booked local-area day, settled after the day",
    "daily_city": "One booked city day, earned only with the minimum valid viewable impressions from verified "
                  "residents",
}
PACKAGE_MEDIA = {"cpm": ["IMAGE"], "cpm_video": ["VIDEO"], "cpc": ["IMAGE"], "cpv": ["VIDEO"],
                 "engagement": ["IMAGE"], "lead": ["IMAGE"], "daily_local": ["IMAGE"], "daily_city": ["IMAGE"]}


def package_catalog(cfg) -> list:
    from app.services import ad_packages as pk

    out = []
    for p in pk.PACKAGES.values():
        ok, why = pk.availability(cfg, p)
        creatable = True
        try:
            pk.require_creatable(cfg, p)
        except pk.PackageError:
            creatable = False
        if p.code == pk.LEGACY_CODE:
            price = Decimal(str(cfg.cpm_rate_usd)) if cfg.cpm_rate_usd else p.floor
            minimum = str(cfg.min_campaign_budget_usd) if cfg.min_campaign_budget_usd else None
            minimum_note = f"Minimum campaign budget {minimum} USD" if minimum else None
        else:
            price = p.floor
            minimum = str(pk.unit_charge(p, p.floor)) if not p.booking else str(p.floor)
            minimum_note = ("At least one booked day" if p.booking
                            else f"The budget must cover at least one {p.unit}")
        reason = (p.not_ready if why == "NOT_READY" else pk.THRESHOLD_MESSAGE if why == "THRESHOLD_NOT_SET"
                  else {"PACKAGE_DISABLED": "Not switched on by MyHigh5 yet",
                        "CAMPAIGNS_DISABLED": "MyHigh5 advertising campaigns are not open yet",
                        "FUNDING_DISABLED": "Advertiser credit cannot be bought yet"}.get(why or ""))
        out.append({"code": p.code, "name": p.name, "pricing_model": p.pricing_model, "price": str(price),
                    "minimum_rate": str(p.floor), "currency": "USD", "billing_unit": p.unit,
                    "price_label": f"{price} USD per {p.unit}", "billable_event": EVENT_DEFINITIONS[p.code],
                    "minimum_budget": minimum, "minimum_note": minimum_note,
                    "supported_media": PACKAGE_MEDIA[p.code], "supported_placements": list(camp.SLOT_KINDS),
                    "booking": p.booking, "state": "AVAILABLE" if ok else (why or "PACKAGE_DISABLED"),
                    "purchasable": bool(ok), "can_draft": creatable, "disabled_reason": None if ok else reason})
    return out


def package_estimate(cfg, code: str, budget, rate=None) -> dict:
    """Upper bound of billable units a budget buys at a package's rate. Never a delivery promise; never a
    CPM figure for another package."""
    from app.services import ad_packages as pk

    try:
        p = pk.get(code)
        budget_d = money(budget)
        if p.code == pk.LEGACY_CODE:
            rate_d = Decimal(str(cfg.cpm_rate_usd)) if cfg.cpm_rate_usd else None
        else:
            rate_d = pk.validate_rate(p, rate if rate not in (None, "") else p.floor)
    except pk.PackageError as exc:
        raise AdError(exc.code, exc.message, exc.status) from None
    if budget_d <= 0:
        raise AdError("INVALID_BUDGET", "Enter a positive budget", 400)
    if rate_d is None:
        return {"package": p.code, "units": None, "unit": p.unit, "note": "Price pending approval"}
    if p.booking:
        units = int((budget_d / rate_d).to_integral_value(rounding=ROUND_DOWN))
        label = "booked days"
    else:
        per = pk.unit_charge(p, rate_d)
        units = int((budget_d / per).to_integral_value(rounding=ROUND_DOWN)) if per > 0 else None
        label = {"cpm": "valid viewable impressions", "cpm_video": "qualifying video impressions",
                 "cpc": "valid clicks", "cpv": "qualifying video views", "engagement": "qualifying engagements",
                 "lead": "accepted leads"}[p.code]
    return {"package": p.code, "budget": str(budget_d), "rate": str(rate_d), "units": units, "unit": label,
            "note": "Maximum billable units for this budget at this rate; delivery is not guaranteed."}


# ---------------------------------------------------------------- status, reasons, budget

def display_status(c: AdvCampaign, now: Optional[datetime] = None) -> str:
    now = now or datetime.utcnow()
    if c.status == "ACTIVE":
        if c.end_at and c.end_at <= now:
            return "ENDED"
        if c.start_at and c.start_at > now:
            return "SCHEDULED"
        return "ACTIVE"
    return {"DRAFT": "DRAFT", "PENDING_REVIEW": "SUBMITTED", "CHANGES_REQUESTED": "CHANGES_REQUIRED",
            "PAUSED": "PAUSED", "COMPLETED": "ENDED", "REJECTED": "REJECTED",
            "CANCELLED": "CANCELLED"}.get(c.status, c.status)


def non_delivery_reasons(db: Session, c: AdvCampaign, cfg, now: Optional[datetime] = None) -> list:
    """Why an approved campaign is not serving right now (empty = eligible to serve)."""
    from app.services import ad_packages as pk

    now = now or datetime.utcnow()
    if c.status not in ("ACTIVE", "PAUSED"):
        return []
    out = []

    def add(code, message):
        out.append({"code": code, "message": message})

    if c.status == "PAUSED":
        add("PAUSED", "The campaign is paused")
    if not cfg.campaigns_enabled or camp.pricing_state(cfg) != "CONFIGURED":
        add("CAMPAIGNS_SWITCHED_OFF", "MyHigh5 advertising delivery is switched off")
    ok, why = pk.deliverable(cfg, pk.of_model(c.pricing_model))
    if not ok:
        add("PACKAGE_NOT_DELIVERABLE", f"The package is not deliverable ({why})")
    if c.start_at and c.start_at > now:
        add("NOT_STARTED", "The start time has not been reached")
    if c.end_at and c.end_at <= now:
        add("ENDED", "The end time has passed")
    if Decimal(str(c.spent or 0)) + Decimal(str(c.reserved or 0)) >= Decimal(str(c.budget_total or 0)):
        add("BUDGET_EXHAUSTED", "The budget is fully used or reserved")
    if c.daily_cap is not None:
        day = db.query(AdvCampaignDay).filter(AdvCampaignDay.campaign_id == c.id,
                                              AdvCampaignDay.day == now.date()).first()
        if day is not None and Decimal(str(day.spent)) + Decimal(str(day.reserved)) >= Decimal(str(c.daily_cap)):
            add("DAILY_LIMIT_REACHED", "Today's spending limit is reached (UTC day)")
    if not db.query(AdvCreative.id).filter(AdvCreative.campaign_id == c.id,
                                           AdvCreative.review_status == "APPROVED").first():
        add("NO_APPROVED_CREATIVE", "No approved creative")
    pages = (c.targeting or {}).get("page_types") or []
    if pages and not set(pages) & set(RENDERED_PAGE_TYPES):
        add("NO_SLOT_ON_PAGES", "None of the chosen page types shows ads yet")
    return out


def budget_summary(db: Session, advertiser_id: int, c: Optional[AdvCampaign] = None) -> dict:
    available = camp.credit_balance(db, advertiser_id)
    out = {"available_credit": str(available), "currency": "USD", "fees": "None: no advertising fee is charged "
           "on top of the budget (payment-provider fees, if any, are shown at checkout)",
           "unused_credit": "Unspent budget returns to your advertiser credit when the campaign ends; credit is "
                            "reusable for new campaigns and is not withdrawable."}
    if c is not None:
        budget = money(c.budget_total)
        spent = camp.floor_cents(c.spent)
        out.update({"required_reservation": str(budget), "maximum_spend": str(budget),
                    "daily_limit": str(c.daily_cap) if c.daily_cap is not None else None,
                    "spent": str(spent), "reserved_now": str(Decimal(str(c.reserved or 0))),
                    "remaining_budget": str(budget - spent),
                    "credit_sufficient": c.status != "DRAFT" or available >= budget})
    return out


def campaign_view(db: Session, c: AdvCampaign, cfg=None, *, detail: bool = True) -> dict:
    """campaign_report plus the workflow fields."""
    from app.services import ad_packages as pk

    cfg = cfg or camp.get_settings(db)
    out = camp.campaign_report(db, c, detail=detail)
    t = c.targeting or {}
    out.update({"display_status": display_status(c), "schedule": schedule_view(c),
                "targeting": {"countries_mode": _mode(t.get("countries_mode"), t.get("countries") or []),
                              "countries": t.get("countries") or [],
                              "page_types_mode": _mode(t.get("page_types_mode"), t.get("page_types") or []),
                              "page_types": t.get("page_types") or []},
                "package": pk.of_model(c.pricing_model).code,
                "unit_rate_usd": str(c.unit_rate_usd) if c.unit_rate_usd is not None else None,
                "review_issues": c.review_issues or [], "non_delivery_reasons": non_delivery_reasons(db, c, cfg),
                "budget": budget_summary(db, c.advertiser_user_id, c)})
    if detail:
        out["creatives"] = [creative_view(db, cr) for cr in db.query(AdvCreative)
                            .filter(AdvCreative.campaign_id == c.id).order_by(AdvCreative.id.asc()).all()]
    return out


# ---------------------------------------------------------------- reporting

def daily_report(db: Session, c: AdvCampaign, *, days: int = 31) -> dict:
    """Billable activity per UTC day x creative x placement x billing metric, adjustments (reversals), and
    the reconciliation of charged events to the campaign's charged days (adv_campaign_days) and spend."""
    from app.models.advertising_v2 import AdvImpressionEvent, AdvServeDecision

    since = datetime.utcnow().date() - timedelta(days=days)
    base = (db.query(AdvImpressionEvent.earning_day, AdvServeDecision.creative_id, AdvServeDecision.slot_kind,
                     AdvImpressionEvent.event_type, func.count(AdvImpressionEvent.id),
                     func.coalesce(func.sum(AdvImpressionEvent.charged_amount), 0))
            .join(AdvServeDecision, AdvServeDecision.id == AdvImpressionEvent.decision_id)
            .filter(AdvServeDecision.campaign_id == c.id, AdvImpressionEvent.validation_status == "VALID",
                    AdvImpressionEvent.event_type != "SERVED", AdvImpressionEvent.earning_day >= since))
    rows = (base.filter(AdvImpressionEvent.reversed_at.is_(None))
            .group_by(AdvImpressionEvent.earning_day, AdvServeDecision.creative_id, AdvServeDecision.slot_kind,
                      AdvImpressionEvent.event_type).all())
    adjustments = (base.filter(AdvImpressionEvent.reversed_at.isnot(None))
                   .group_by(AdvImpressionEvent.earning_day, AdvServeDecision.creative_id, AdvServeDecision.slot_kind,
                             AdvImpressionEvent.event_type).all())
    charged_by_day: dict = {}
    activity = []
    for day, creative_id, slot, metric, n, amount in rows:
        amount = Decimal(str(amount))
        charged_by_day[day] = charged_by_day.get(day, Decimal(0)) + amount
        activity.append({"day": day.isoformat() if day else None, "creative_id": creative_id, "placement": slot,
                         "billing_metric": metric, "events": int(n), "charged": str(amount.quantize(Decimal("0.000001")))})
    day_rows = (db.query(AdvCampaignDay).filter(AdvCampaignDay.campaign_id == c.id, AdvCampaignDay.day >= since)
                .order_by(AdvCampaignDay.day.desc()).all())
    daily = []
    for d in day_rows:
        events = charged_by_day.get(d.day, Decimal(0))
        spent = Decimal(str(d.spent))
        daily.append({"day": d.day.isoformat(), "spend": str(camp.floor_cents(spent)), "spend_exact": str(spent),
                      "charged_events": str(events.quantize(Decimal("0.000001"))),
                      "direct_charges": str((spent - events).quantize(Decimal("0.000001"))),
                      "recognized": d.recognized_journal_id is not None})
    all_days = Decimal(str(db.query(func.coalesce(func.sum(AdvCampaignDay.spent), 0))
                           .filter(AdvCampaignDay.campaign_id == c.id).scalar() or 0))
    budget = money(c.budget_total)
    return {"campaign_id": c.id, "currency": "USD", "window_days": days, "daily": daily, "activity": activity,
            "adjustments": [{"day": d.isoformat() if d else None, "creative_id": cr, "placement": s,
                             "billing_metric": m, "events": int(n), "reversed": str(Decimal(str(a)))}
                            for d, cr, s, m, n, a in adjustments],
            "remaining_budget": str(budget - camp.floor_cents(c.spent)),
            "reconciliation": {"campaign_spent": str(Decimal(str(c.spent or 0))), "sum_of_days": str(all_days),
                               "ok": Decimal(str(c.spent or 0)) == all_days,
                               "detail": "Campaign spend equals the sum of its charged days (the days the ledger "
                                         "recognizes as revenue, rounded down to the cent)"}}


def member_daily(db: Session, user_id: int, *, days: int = 31) -> dict:
    """The member's estimated daily contest-entry earnings (creative and sponsor roles) from valid,
    unreversed MyHigh5 charges on the entry's page, at the entry's preserved original rate. AdSense days
    show activity only: no amount until Google finalizes the month. Never withdrawable: the monthly
    allocation remains the only payable record."""
    from app.models.advertising_v2 import AdvEntryOrigin, AdvImpressionEvent
    from app.services import ad_attribution
    from app.services.ad_revenue_policy import CONTEST_PAGE_SPONSOR_RATE

    since = datetime.utcnow().date() - timedelta(days=days)
    out = []
    for role, column in (("CREATIVE", AdvImpressionEvent.creative_user_id),
                         ("SPONSOR", AdvImpressionEvent.sponsor_user_id)):
        rows = (db.query(AdvImpressionEvent.earning_day, AdvImpressionEvent.source, AdvImpressionEvent.contestant_id,
                         func.count(AdvImpressionEvent.id),
                         func.coalesce(func.sum(AdvImpressionEvent.charged_amount), 0))
                .filter(column == user_id, AdvImpressionEvent.validation_status == "VALID",
                        AdvImpressionEvent.event_type == "VIEWABLE", AdvImpressionEvent.reversed_at.is_(None),
                        AdvImpressionEvent.contestant_id.isnot(None), AdvImpressionEvent.earning_day >= since)
                .group_by(AdvImpressionEvent.earning_day, AdvImpressionEvent.source, AdvImpressionEvent.contestant_id)
                .all())
        for day, source, contestant_id, n, charged in rows:
            origin = db.query(AdvEntryOrigin).filter(AdvEntryOrigin.contestant_id == contestant_id).first()
            kind = origin.origin_kind if origin is not None and origin.status == "RESOLVED" else None
            rate = (ad_attribution.creative_rate(kind) if role == "CREATIVE" else CONTEST_PAGE_SPONSOR_RATE)
            amount = None
            if source == "MYHIGH5" and rate is not None and kind is not None:
                amount = (Decimal(str(charged)) * Decimal(str(rate))).quantize(Decimal("0.0001"), rounding=ROUND_DOWN)
            out.append({"day": day.isoformat(), "role": role, "source": source, "contest_entry_id": contestant_id,
                        "original_submission_type": kind, "rate": str(rate) if rate is not None else None,
                        "valid_impressions": int(n), "estimated_amount": str(amount) if amount is not None else None,
                        "status": ("ESTIMATED" if amount is not None else
                                   "AWAITING_GOOGLE" if source == "ADSENSE" else "ORIGIN_UNDER_REVIEW"),
                        "withdrawable": False})
    out.sort(key=lambda r: (r["day"], r["role"]), reverse=True)
    return {"days": out, "note": "Daily figures are estimates and are not withdrawable. Earnings are released "
                                 "monthly after validation (AdSense: after Google finalizes and pays the month)."}


# ---------------------------------------------------------------- advertiser's direct sponsor

SPONSOR_SOURCE = "ADV_CAMPAIGN_DAY"
SPONSOR_RECORDED, SPONSOR_MISSED_KYC, SPONSOR_NONE, SPONSOR_REVERSED, SPONSOR_REVIEW = (
    "RECORDED", "MISSED_KYC", "NO_SPONSOR", "REVERSED", "FINANCE_REVIEW")


def decide_sponsor_commission(db: Session, day: AdvCampaignDay, campaign: AdvCampaign, amount: Decimal) -> Optional[str]:
    """Once per recognized campaign day, while the switch is on: the advertiser's direct sponsor earns 20%
    (40% once permanently qualified) of the amount just recognized as revenue (Dr 2320 / Cr 4020) - never
    of a deposit, a budget or a reservation. Existing commission engine: KYC rule (missed earning),
    direct sponsor only, idempotent per source."""
    from app.models.business_model import RevenuePolicy
    from app.services.ad_revenue_policy import ad_slot_split
    from app.services.affiliate_rate_policy import AD_SLOT_PURCHASE
    from app.services.new_model_revenue import RevenueBreakdown, accrue_direct_commission

    if day.sponsor_commission_status is not None:
        return day.sponsor_commission_status
    cfg = camp.get_settings(db)
    if not getattr(cfg, "advertiser_sponsor_commission_enabled", False):
        return None
    amount = money(amount)
    if amount <= 0:
        return None
    split = ad_slot_split(db, buyer_user_id=campaign.advertiser_user_id, gross_amount=amount)
    if split.sponsor_user_id is None or split.sponsor_rate is None or split.sponsor_rate <= 0:
        day.sponsor_commission_status = SPONSOR_NONE
        return SPONSOR_NONE
    rate = Decimal(str(split.sponsor_rate))
    policy = RevenuePolicy(model_version="NEW_V2", product_code="advertising_campaign",
                           revenue_category=AD_SLOT_PURCHASE, revenue_account_code=camp.ORDINARY_REVENUE_ACCOUNT,
                           commission_eligible=True, commission_rate=rate)
    breakdown = RevenueBreakdown(product_code="advertising_campaign", revenue_category=AD_SLOT_PURCHASE, gross=amount,
                                 seller_base=Decimal("0.00"), provider_cost=Decimal("0.00"), website_revenue=amount,
                                 commission_eligible=True, commission_rate=rate, leaders_revenue_eligible=False,
                                 policy=policy)
    commission = accrue_direct_commission(db, source_type=SPONSOR_SOURCE, source_id=day.id,
                                          payer_user_id=campaign.advertiser_user_id, breakdown=breakdown)
    day.sponsor_rate = rate
    if commission is not None:
        day.sponsor_commission_status = SPONSOR_RECORDED
        day.sponsor_commission_id, day.sponsor_commission_amount = commission.id, money(commission.commission_amount)
    else:
        day.sponsor_commission_status = SPONSOR_MISSED_KYC
        day.sponsor_commission_amount = money(split.sponsor_commission)
    return day.sponsor_commission_status


def after_charge_reversed(db: Session, campaign_id: int, day_value, *, reason: str) -> Optional[str]:
    """A recognized day's charge was reduced. A decided commission is reversed through the existing engine
    when the whole day was reversed and it is unpaid; any other case (partial, paid, in a payout) goes to
    finance review - no automatic clawback without an approved recovery policy (Annual Ads precedent)."""
    from app.models.affiliate import AffiliateCommission, CommissionStatus
    from app.services.financial_integrity import FinancialIntegrityError
    from app.services.new_model_revenue import reverse_direct_commissions

    day = (db.query(AdvCampaignDay).filter(AdvCampaignDay.campaign_id == campaign_id, AdvCampaignDay.day == day_value)
           .with_for_update().first())
    if day is None or day.sponsor_commission_status not in (SPONSOR_RECORDED, SPONSOR_MISSED_KYC):
        return None
    whole = camp.floor_cents(day.spent) <= 0
    commission = db.get(AffiliateCommission, day.sponsor_commission_id) if day.sponsor_commission_id else None
    in_payout = commission is not None and (commission.status == CommissionStatus.PAID
                                            or commission.payout_reference is not None)
    if not whole or in_payout:
        day.sponsor_commission_status = SPONSOR_REVIEW
        return SPONSOR_REVIEW
    try:
        with db.begin_nested():
            reverse_direct_commissions(db, source_type=SPONSOR_SOURCE, source_id=day.id,
                                       reason=f"Advertising charge reversed: {reason[:120]}")
    except FinancialIntegrityError:
        day.sponsor_commission_status = SPONSOR_REVIEW
        return SPONSOR_REVIEW
    day.sponsor_commission_status = SPONSOR_REVERSED
    return SPONSOR_REVERSED
