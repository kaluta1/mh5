"""MyHigh5 advertising: settings, advertiser credit and CPM campaigns.

Ledger (NEW_V2, via new_model_ledger.post_entry):
  advertiser pays (SoncoPay deposit of product ``advertising_credit``):  Dr 1001 / Cr 2320 advertiser credit
  delivery is validated and recognized per campaign per UTC day:         Dr 2320 / Cr 4020 ordinary ad revenue
  invalid activity found after recognition (credit back):               Dr 4020 / Cr 2320
A deposit is a liability until delivery: nothing is revenue before a validated, viewable impression.

The advertiser credit balance is the sum of adv_credit_movements (a sub-ledger of 2320). It is not a
member wallet and is never withdrawable through cash-out. Refunds of unspent credit are not issued
automatically (no approved refund policy): the refundable amount is reported.

Prices: adv_settings.cpm_rate_usd is set by an administrator; NULL = pending approval, and then no
campaign can be submitted or served. A campaign keeps the rate fixed at submission.
"""
from __future__ import annotations

from datetime import datetime
from decimal import ROUND_DOWN, Decimal
from typing import Iterable, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.accounting import AuditTrail
from app.models.advertising_v2 import AdvCampaign, AdvCreative, AdvCreditMovement, AdvSettings
from app.services.financial_integrity import money

AD_CREDIT_PRODUCT_CODE = "advertising_credit"
CREDIT_ACCOUNT = "2320"
ORDINARY_REVENUE_ACCOUNT = "4020"
ADSENSE_REVENUE_ACCOUNT = "4021"
ADSENSE_RECEIVABLE_ACCOUNT = "1240"
HELD_SHARES_ACCOUNT = "2322"
SHARE_EXPENSE_ACCOUNT = "5006"
SOURCE_AD_CAMPAIGN = "AD_CAMPAIGN"
SOURCE_AD_ALLOCATION = "AD_ALLOCATION"
SOURCE_ADSENSE_MONTH = "ADSENSE_MONTH"

SLOT_KINDS = ("SIDEBAR", "IN_FEED", "IN_CONTENT")
PAGE_TYPES = ("CONTEST_LISTING", "CONTEST_ENTRY", "FEED", "POST", "DISCOVERY", "PROFILE", "MARKETPLACE")
SETTINGS_FIELDS = {
    "cpm_rate_usd": "money4", "min_campaign_budget_usd": "money", "min_daily_cap_usd": "money",
    "campaigns_enabled": "bool", "funding_enabled": "bool", "adsense_fallback_enabled": "bool",
    "adsense_sharing_enabled": "bool", "contest_sharing_enabled": "bool",
    "reservation_ttl_seconds": "int", "frequency_cap_per_day": "int", "max_viewable_per_viewer_hour": "int",
}
PERMISSION_MANAGE = "manage_advertising"


class AdError(Exception):
    def __init__(self, code: str, message: str, status: int = 409):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def floor_cents(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_DOWN)


def unit_price(cpm) -> Decimal:
    """Price of one impression (CPM / 1000), 6 decimals, never rounded up."""
    return (Decimal(str(cpm)) / Decimal(1000)).quantize(Decimal("0.000001"), rounding=ROUND_DOWN)


# ---------------------------------------------------------------- settings

def get_settings(db: Session, *, lock: bool = False) -> AdvSettings:
    q = db.query(AdvSettings).order_by(AdvSettings.id.asc())
    row = (q.with_for_update() if lock else q).first()
    if row is None:
        row = AdvSettings()
        db.add(row)
        db.flush()
    return row


def pricing_state(row: AdvSettings) -> str:
    return "CONFIGURED" if row.cpm_rate_usd is not None and Decimal(str(row.cpm_rate_usd)) > 0 else "PENDING_APPROVAL"


def settings_payload(row: AdvSettings) -> dict:
    out = {k: getattr(row, k) for k in SETTINGS_FIELDS}
    for k in ("cpm_rate_usd", "min_campaign_budget_usd", "min_daily_cap_usd"):
        out[k] = None if out[k] is None else str(out[k])
    out["pricing_state"] = pricing_state(row)
    out["currency"] = "USD"
    return out


def update_settings(db: Session, actor, changes: dict) -> AdvSettings:
    """Permission + current password are checked by the caller. Audited old/new values."""
    row = get_settings(db, lock=True)
    old, new = {}, {}
    for key, value in (changes or {}).items():
        kind = SETTINGS_FIELDS.get(key)
        if kind is None:
            raise AdError("UNKNOWN_SETTING", f"Unknown advertising setting: {key}", 400)
        if kind in ("money", "money4"):
            if value in (None, ""):
                parsed = None
            else:
                parsed = Decimal(str(value))
                if parsed <= 0:
                    raise AdError("INVALID_VALUE", f"{key} must be greater than zero", 400)
                parsed = parsed.quantize(Decimal("0.0001") if kind == "money4" else Decimal("0.01"))
        elif kind == "bool":
            parsed = bool(value)
        else:
            parsed = int(value)
            if parsed < 1 or parsed > 100000:
                raise AdError("INVALID_VALUE", f"{key} is out of range", 400)
        old[key], new[key] = getattr(row, key), parsed
        setattr(row, key, parsed)
    if new.get("campaigns_enabled") and pricing_state(row) != "CONFIGURED":
        raise AdError("PRICING_PENDING", "Set an approved CPM price before enabling campaigns")
    if new.get("funding_enabled") and pricing_state(row) != "CONFIGURED":
        raise AdError("PRICING_PENDING", "Set an approved CPM price before enabling advertiser funding")
    row.updated_by_user_id = actor.id
    db.add(AuditTrail(table_name="adv_settings", record_id=row.id or 0, action="UPDATE",
                      old_values={k: (str(v) if v is not None else None) for k, v in old.items()},
                      new_values={k: (str(v) if v is not None else None) for k, v in new.items()}, user_id=actor.id))
    db.flush()
    return row


# ---------------------------------------------------------------- advertiser credit

def credit_balance(db: Session, advertiser_user_id: int) -> Decimal:
    total = (db.query(func.coalesce(func.sum(AdvCreditMovement.amount), 0))
             .filter(AdvCreditMovement.advertiser_user_id == advertiser_user_id).scalar())
    return money(total or 0)


def _movement(db: Session, *, advertiser_id: int, kind: str, amount: Decimal, key: str, campaign_id=None,
              deposit_id=None, journal_entry_id=None, note=None, actor_id=None) -> AdvCreditMovement:
    existing = db.query(AdvCreditMovement).filter(AdvCreditMovement.idempotency_key == key).first()
    if existing is not None:
        return existing
    row = AdvCreditMovement(advertiser_user_id=advertiser_id, movement_type=kind, amount=money(amount),
                            campaign_id=campaign_id, deposit_id=deposit_id, journal_entry_id=journal_entry_id,
                            idempotency_key=key, note=note, actor_user_id=actor_id)
    db.add(row)
    db.flush()
    return row


def _lock_advertiser(db: Session, advertiser_id: int) -> None:
    from app.models.user import User

    db.query(User.id).filter(User.id == advertiser_id).with_for_update().first()


def on_credit_deposit_validated(db: Session, deposit) -> None:
    """A validated advertising_credit deposit: cash in, liability to the advertiser. Idempotent."""
    from app.services.new_model_ledger import Line, PostingType, SourceType, post_entry

    amount = money(deposit.amount)
    entry = post_entry(
        db, source_type=SourceType.DEPOSIT, source_id=deposit.id, posting_type=PostingType.RECEIPT,
        lines=[Line("1001", debit=amount, description="Cash received - advertiser credit"),
               Line(CREDIT_ACCOUNT, credit=amount,
                    description=f"Advertiser credit (unearned) - User #{deposit.user_id}")],
        description=f"NEW_V2 advertiser credit deposit {deposit.id} - user {deposit.user_id}",
    )
    _movement(db, advertiser_id=deposit.user_id, kind="DEPOSIT", amount=amount, key=f"deposit:{deposit.id}",
              deposit_id=deposit.id, journal_entry_id=entry.id, note="SoncoPay deposit validated")


def on_credit_deposit_reversed(db: Session, deposit, reason: str) -> None:
    """Provider refund of an advertiser credit deposit (the ledger entries are reversed by the caller's
    existing path). The credit is taken back; if part of it is already in campaigns, the advertiser's
    campaigns are paused for review - never silently overspent."""
    _lock_advertiser(db, deposit.user_id)
    _movement(db, advertiser_id=deposit.user_id, kind="DEPOSIT_REVERSAL", amount=-money(deposit.amount),
              key=f"deposit-reversal:{deposit.id}", deposit_id=deposit.id, note=(reason or "")[:300])
    if credit_balance(db, deposit.user_id) < 0:
        for campaign in (db.query(AdvCampaign).filter(AdvCampaign.advertiser_user_id == deposit.user_id,
                                                      AdvCampaign.status.in_(("ACTIVE", "PENDING_REVIEW")))
                         .with_for_update().all()):
            campaign.status = "PAUSED"
            campaign.review_note = "Paused: the funding payment was refunded by the provider"
    db.flush()


# ---------------------------------------------------------------- campaigns

def _audit(db: Session, actor_id: Optional[int], campaign: AdvCampaign, action: str, new: dict) -> None:
    db.add(AuditTrail(table_name="adv_campaigns", record_id=campaign.id, action=action, old_values=None,
                      new_values={k: (str(v) if v is not None else None) for k, v in new.items()}, user_id=actor_id))


def _validate_terms(cfg: AdvSettings, *, budget: Decimal, daily_cap: Optional[Decimal], start_at, end_at,
                    placements: Iterable[str], targeting: Optional[dict]) -> None:
    if budget <= 0:
        raise AdError("INVALID_BUDGET", "The campaign budget must be greater than zero", 400)
    if cfg.min_campaign_budget_usd is not None and budget < Decimal(str(cfg.min_campaign_budget_usd)):
        raise AdError("BUDGET_BELOW_MINIMUM", f"The minimum campaign budget is {cfg.min_campaign_budget_usd} USD", 400)
    if daily_cap is not None:
        if daily_cap <= 0 or daily_cap > budget:
            raise AdError("INVALID_DAILY_CAP", "The daily limit must be positive and not above the budget", 400)
        if cfg.min_daily_cap_usd is not None and daily_cap < Decimal(str(cfg.min_daily_cap_usd)):
            raise AdError("DAILY_CAP_BELOW_MINIMUM", f"The minimum daily limit is {cfg.min_daily_cap_usd} USD", 400)
    if not start_at or not end_at or end_at <= start_at:
        raise AdError("INVALID_SCHEDULE", "The end date must be after the start date", 400)
    bad = [p for p in (placements or []) if p not in SLOT_KINDS]
    if bad or not placements:
        raise AdError("INVALID_PLACEMENTS", f"Placements must be chosen from {', '.join(SLOT_KINDS)}", 400)
    pages = (targeting or {}).get("page_types") or []
    if any(p not in PAGE_TYPES for p in pages):
        raise AdError("INVALID_TARGETING", f"Page types must be chosen from {', '.join(PAGE_TYPES)}", 400)
    countries = (targeting or {}).get("countries") or []
    if any(not isinstance(c, str) or len(c) != 2 for c in countries):
        raise AdError("INVALID_TARGETING", "Countries must be two-letter codes", 400)


def create_campaign(db: Session, advertiser, *, name: str, budget, daily_cap=None, start_at: datetime,
                    end_at: datetime, placements: list, targeting: Optional[dict] = None) -> AdvCampaign:
    cfg = get_settings(db)
    budget_d, cap_d = money(budget), (money(daily_cap) if daily_cap not in (None, "") else None)
    _validate_terms(cfg, budget=budget_d, daily_cap=cap_d, start_at=start_at, end_at=end_at,
                    placements=placements, targeting=targeting)
    campaign = AdvCampaign(advertiser_user_id=advertiser.id, name=(name or "").strip()[:160] or "Campaign",
                           status="DRAFT", budget_total=budget_d, daily_cap=cap_d, start_at=start_at, end_at=end_at,
                           placements=list(placements),
                           targeting={"countries": [c.upper() for c in (targeting or {}).get("countries") or []],
                                      "page_types": list((targeting or {}).get("page_types") or [])})
    db.add(campaign)
    db.flush()
    _audit(db, advertiser.id, campaign, "CREATE", {"budget": budget_d, "daily_cap": cap_d})
    return campaign


def add_creative(db: Session, campaign: AdvCampaign, *, headline: str, body: Optional[str], image_url: Optional[str],
                 destination_url: str) -> AdvCreative:
    from app.services.advertising_integrity import AdvertisingIntegrityError, normalize_destination_url

    if campaign.status not in ("DRAFT", "PAUSED", "PENDING_REVIEW", "ACTIVE"):
        raise AdError("CAMPAIGN_CLOSED", "Creatives cannot be added to a closed campaign")
    try:
        destination = normalize_destination_url(destination_url)
        image = normalize_destination_url(image_url) if image_url else None
    except AdvertisingIntegrityError as exc:
        raise AdError("INVALID_URL", str(exc), 400) from None
    if image and not image.startswith("https://"):
        raise AdError("INVALID_URL", "Images must be served over HTTPS", 400)
    headline = (headline or "").strip()
    if not headline:
        raise AdError("INVALID_CREATIVE", "A headline is required", 400)
    creative = AdvCreative(campaign_id=campaign.id, headline=headline[:90], body=(body or "").strip()[:240] or None,
                           image_url=image, destination_url=destination, review_status="PENDING")
    db.add(creative)
    db.flush()
    return creative


def submit_campaign(db: Session, advertiser, campaign: AdvCampaign) -> AdvCampaign:
    """Fix the price, move the budget from credit into the campaign, send it to review."""
    cfg = get_settings(db)
    if pricing_state(cfg) != "CONFIGURED":
        raise AdError("PRICING_PENDING", "Advertising prices are pending approval. Campaigns cannot be submitted yet.")
    if not cfg.campaigns_enabled:
        raise AdError("CAMPAIGNS_DISABLED", "MyHigh5 advertising campaigns are not open yet.")
    if campaign.status != "DRAFT":
        raise AdError("INVALID_STATE", "Only a draft campaign can be submitted")
    if not db.query(AdvCreative.id).filter(AdvCreative.campaign_id == campaign.id).first():
        raise AdError("NO_CREATIVE", "Add at least one creative before submitting")
    _validate_terms(cfg, budget=money(campaign.budget_total), daily_cap=campaign.daily_cap, start_at=campaign.start_at,
                    end_at=campaign.end_at, placements=campaign.placements or [], targeting=campaign.targeting)
    _lock_advertiser(db, advertiser.id)
    budget = money(campaign.budget_total)
    if credit_balance(db, advertiser.id) < budget:
        raise AdError("INSUFFICIENT_CREDIT", "Your advertiser credit is lower than the campaign budget")
    _movement(db, advertiser_id=advertiser.id, kind="ALLOCATE", amount=-budget, key=f"campaign:{campaign.id}:allocate",
              campaign_id=campaign.id, note="Budget moved into the campaign", actor_id=advertiser.id)
    campaign.cpm_rate_usd = Decimal(str(cfg.cpm_rate_usd))
    campaign.status = "PENDING_REVIEW"
    _audit(db, advertiser.id, campaign, "SUBMIT", {"cpm_rate_usd": campaign.cpm_rate_usd, "budget": budget})
    db.flush()
    return campaign


def review_creative(db: Session, actor, creative: AdvCreative, *, approve: bool, note: str) -> AdvCreative:
    if not (note or "").strip() and not approve:
        raise AdError("NOTE_REQUIRED", "A reason is required to reject a creative", 400)
    creative.review_status = "APPROVED" if approve else "REJECTED"
    creative.review_note, creative.reviewed_by_user_id, creative.reviewed_at = (note or "")[:500], actor.id, datetime.utcnow()
    db.add(AuditTrail(table_name="adv_creatives", record_id=creative.id, action="REVIEW", old_values=None,
                      new_values={"review_status": creative.review_status, "note": creative.review_note}, user_id=actor.id))
    db.flush()
    return creative


def review_campaign(db: Session, actor, campaign: AdvCampaign, *, approve: bool, note: str) -> AdvCampaign:
    campaign = db.query(AdvCampaign).filter(AdvCampaign.id == campaign.id).with_for_update().one()
    if campaign.status != "PENDING_REVIEW":
        raise AdError("INVALID_STATE", "Only a campaign pending review can be reviewed")
    if approve:
        if not db.query(AdvCreative.id).filter(AdvCreative.campaign_id == campaign.id,
                                               AdvCreative.review_status == "APPROVED").first():
            raise AdError("NO_APPROVED_CREATIVE", "Approve at least one creative first")
        campaign.status = "ACTIVE"
    else:
        if not (note or "").strip():
            raise AdError("NOTE_REQUIRED", "A reason is required to reject a campaign", 400)
        campaign.status = "REJECTED"
        settle_campaign(db, campaign, reason="REJECTED")
    campaign.review_note, campaign.reviewed_by_user_id = (note or "")[:500], actor.id
    _audit(db, actor.id, campaign, "REVIEW", {"status": campaign.status, "note": note})
    db.flush()
    return campaign


def set_paused(db: Session, actor, campaign: AdvCampaign, *, paused: bool) -> AdvCampaign:
    campaign = db.query(AdvCampaign).filter(AdvCampaign.id == campaign.id).with_for_update().one()
    if paused and campaign.status != "ACTIVE":
        raise AdError("INVALID_STATE", "Only an active campaign can be paused")
    if not paused:
        if campaign.status != "PAUSED":
            raise AdError("INVALID_STATE", "Only a paused campaign can be resumed")
        if credit_balance(db, campaign.advertiser_user_id) < 0:
            raise AdError("FUNDING_REVERSED", "This campaign's funding was refunded; contact support")
        if campaign.end_at and campaign.end_at <= datetime.utcnow():
            raise AdError("CAMPAIGN_ENDED", "The campaign end date has passed")
    campaign.status = "PAUSED" if paused else "ACTIVE"
    _audit(db, actor.id, campaign, "PAUSE" if paused else "RESUME", {"status": campaign.status})
    db.flush()
    return campaign


def complete_campaign(db: Session, campaign: AdvCampaign, *, reason: str, actor_id: Optional[int] = None) -> AdvCampaign:
    """Stop serving. Unspent budget returns to credit once no reservation is open (settle_campaign)."""
    if campaign.status in ("COMPLETED", "REJECTED"):
        return campaign
    campaign.status = "COMPLETED"
    campaign.completed_at, campaign.completion_reason = datetime.utcnow(), reason[:40]
    _audit(db, actor_id, campaign, "COMPLETE", {"reason": reason})
    db.flush()
    return campaign


def settle_campaign(db: Session, campaign: AdvCampaign, *, reason: str) -> Optional[AdvCreditMovement]:
    """Return the unspent budget to the advertiser's credit, once, after every reservation is closed and
    every charged day is recognized. Charges are recognized in whole cents, rounded down, so the
    advertiser is never charged a fraction of a cent."""
    from app.models.advertising_v2 import AdvCampaignDay

    if campaign.settled_at is not None or Decimal(str(campaign.reserved or 0)) > 0:
        return None
    if campaign.status not in ("COMPLETED", "REJECTED"):
        return None
    if db.query(AdvCampaignDay.id).filter(AdvCampaignDay.campaign_id == campaign.id, AdvCampaignDay.spent > 0,
                                          AdvCampaignDay.recognized_at.is_(None)).first():
        return None                          # a charged day still waits for its recognition
    remaining = money(campaign.budget_total) - floor_cents(campaign.spent)
    campaign.settled_at = datetime.utcnow()
    if remaining <= 0 or not db.query(AdvCreditMovement.id).filter(
            AdvCreditMovement.idempotency_key == f"campaign:{campaign.id}:allocate").first():
        db.flush()
        return None
    return _movement(db, advertiser_id=campaign.advertiser_user_id, kind="RELEASE", amount=remaining,
                     key=f"campaign:{campaign.id}:release", campaign_id=campaign.id,
                     note=f"Unspent budget returned ({reason})")


def campaign_report(db: Session, campaign: AdvCampaign) -> dict:
    from app.models.advertising_v2 import AdvCampaignDay, AdvImpressionEvent

    valid = (db.query(func.count(AdvImpressionEvent.id))
             .filter(AdvImpressionEvent.campaign_id == campaign.id, AdvImpressionEvent.event_type == "VIEWABLE",
                     AdvImpressionEvent.validation_status == "VALID", AdvImpressionEvent.reversed_at.is_(None)).scalar())
    invalid = (db.query(func.count(AdvImpressionEvent.id))
               .filter(AdvImpressionEvent.campaign_id == campaign.id,
                       AdvImpressionEvent.validation_status == "INVALID").scalar())
    days = (db.query(AdvCampaignDay).filter(AdvCampaignDay.campaign_id == campaign.id)
            .order_by(AdvCampaignDay.day.desc()).limit(31).all())
    budget = money(campaign.budget_total)
    return {
        "id": campaign.id, "name": campaign.name, "status": campaign.status, "currency": campaign.currency,
        "cpm_rate_usd": str(campaign.cpm_rate_usd) if campaign.cpm_rate_usd is not None else None,
        "budget_total": str(budget), "daily_cap": str(campaign.daily_cap) if campaign.daily_cap is not None else None,
        "spent": str(floor_cents(campaign.spent)), "reserved": str(Decimal(str(campaign.reserved or 0))),
        "remaining_budget": str(budget - floor_cents(campaign.spent)),
        "start_at": campaign.start_at.isoformat() if campaign.start_at else None,
        "end_at": campaign.end_at.isoformat() if campaign.end_at else None,
        "placements": campaign.placements or [], "targeting": campaign.targeting or {},
        "valid_impressions": int(valid or 0), "invalid_events": int(invalid or 0),
        "completion_reason": campaign.completion_reason, "review_note": campaign.review_note,
        "daily": [{"day": d.day.isoformat(), "spent": str(floor_cents(d.spent)),
                   "recognized": d.recognized_journal_id is not None} for d in days],
    }
