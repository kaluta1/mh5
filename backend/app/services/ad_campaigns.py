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
# Owner-approved advertising policy (Prompt 4, 2026-11-03), written into adv_settings by migration
# e5a7c9e1f3b4 where unset. adv_settings stays the authority; these are the reference values only.
APPROVED_CPM_USD = Decimal("0.50")
APPROVED_MIN_BUDGET_USD = Decimal("10.00")
# Lifecycle. Funding comes first: the budget leaves prepaid advertiser credit at submission, so there
# is no separate "awaiting payment" state. Approval never implies payment; payment never skips review.
EDITABLE_STATUSES = ("DRAFT", "CHANGES_REQUESTED")
CLOSED_STATUSES = ("COMPLETED", "REJECTED", "CANCELLED")
# Uploaded creative images (existing media storage, images only; no video, no new format).
UPLOAD_PREFIX = "/api/v1/media/file/"
CREATIVE_IMAGE_MAX_BYTES = 2 * 1024 * 1024
CREATIVE_IMAGE_TYPES = ("image/jpeg", "image/png", "image/webp", "image/gif")
CREATIVE_MIN_SIDE, CREATIVE_MAX_SIDE = 100, 4000


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
    from app.services.new_model_payments import funding_account

    amount = money(deposit.amount)
    entry = post_entry(
        db, source_type=SourceType.DEPOSIT, source_id=deposit.id, posting_type=PostingType.RECEIPT,
        lines=[Line(funding_account(deposit), debit=amount,
                    description=("Cash received" if funding_account(deposit) == "1001" else "Paid with commission earnings")
                    + " - advertiser credit"),
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

    if campaign.status not in ("DRAFT", "CHANGES_REQUESTED", "PAUSED", "PENDING_REVIEW", "ACTIVE"):
        raise AdError("CAMPAIGN_CLOSED", "Creatives cannot be added to a closed campaign")
    try:
        destination = normalize_destination_url(destination_url)
    except AdvertisingIntegrityError as exc:
        raise AdError("INVALID_URL", str(exc), 400) from None
    image = None
    if image_url:
        if image_url.startswith(UPLOAD_PREFIX):
            image = own_upload_url(campaign.advertiser_user_id, image_url)
        else:
            try:
                image = normalize_destination_url(image_url)
            except AdvertisingIntegrityError as exc:
                raise AdError("INVALID_URL", str(exc), 400) from None
            if not image.startswith("https://"):
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
    if campaign.status not in EDITABLE_STATUSES:
        raise AdError("INVALID_STATE", "Only a draft campaign or one with requested changes can be submitted")
    if not db.query(AdvCreative.id).filter(AdvCreative.campaign_id == campaign.id,
                                           AdvCreative.review_status != "REJECTED").first():
        raise AdError("NO_CREATIVE", "Add at least one creative before submitting")
    if campaign.status == "CHANGES_REQUESTED":
        # The budget is already in the campaign (allocated at the first submission) at the price fixed then.
        campaign.status = "PENDING_REVIEW"
        _audit(db, advertiser.id, campaign, "RESUBMIT", {"status": campaign.status})
        db.flush()
        notify(db, campaign, "SUBMITTED")
        return campaign
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
    notify(db, campaign, "SUBMITTED")
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
    notify(db, campaign, "APPROVED" if approve else "REJECTED")
    return campaign


def request_changes(db: Session, actor, campaign: AdvCampaign, *, note: str) -> AdvCampaign:
    """Administrator: send a campaign under review back to the advertiser. The budget stays in the campaign
    at its fixed price; the advertiser edits and resubmits, or cancels (which returns the budget)."""
    campaign = db.query(AdvCampaign).filter(AdvCampaign.id == campaign.id).with_for_update().one()
    if campaign.status != "PENDING_REVIEW":
        raise AdError("INVALID_STATE", "Changes can be requested only for a campaign pending review")
    if not (note or "").strip():
        raise AdError("NOTE_REQUIRED", "Describe the changes that are needed", 400)
    campaign.status = "CHANGES_REQUESTED"
    campaign.review_note, campaign.reviewed_by_user_id = note.strip()[:500], actor.id
    _audit(db, actor.id, campaign, "REQUEST_CHANGES", {"status": campaign.status, "note": campaign.review_note})
    db.flush()
    notify(db, campaign, "CHANGES_REQUESTED")
    return campaign


def update_campaign(db: Session, advertiser, campaign: AdvCampaign, changes: dict) -> AdvCampaign:
    """Advertiser edits: everything in a draft; after a change request everything except the budget
    (already moved into the campaign at its fixed price)."""
    if campaign.status not in EDITABLE_STATUSES:
        raise AdError("INVALID_STATE", "Only a draft campaign or one with requested changes can be edited")
    cfg = get_settings(db)
    changes = {k: v for k, v in (changes or {}).items() if v is not None}
    if campaign.status != "DRAFT" and ("budget" in changes or "daily_cap" in changes):
        raise AdError("BUDGET_LOCKED", "The budget is already in the campaign; cancel it to change the budget")
    budget = money(changes.get("budget", campaign.budget_total))
    cap = changes.get("daily_cap", campaign.daily_cap)
    cap = money(cap) if cap not in (None, "") else None
    targeting = dict(campaign.targeting or {})
    if "countries" in changes:
        targeting["countries"] = [str(c).upper() for c in changes["countries"] or []]
    if "page_types" in changes:
        targeting["page_types"] = list(changes["page_types"] or [])
    start_at, end_at = changes.get("start_at", campaign.start_at), changes.get("end_at", campaign.end_at)
    placements = list(changes.get("placements", campaign.placements) or [])
    _validate_terms(cfg, budget=budget, daily_cap=cap, start_at=start_at, end_at=end_at, placements=placements,
                    targeting=targeting)
    if "name" in changes:
        campaign.name = str(changes["name"]).strip()[:160] or campaign.name
    campaign.budget_total, campaign.daily_cap = budget, cap
    campaign.start_at, campaign.end_at, campaign.placements, campaign.targeting = start_at, end_at, placements, targeting
    _audit(db, advertiser.id, campaign, "UPDATE", {k: changes[k] for k in sorted(changes)})
    db.flush()
    return campaign


def cancel_campaign(db: Session, advertiser, campaign: AdvCampaign) -> AdvCampaign:
    """Advertiser: stop a campaign that never served (draft, changes requested, pending review). A budget
    already moved into the campaign returns to the advertiser's credit at once (idempotent movement)."""
    campaign = db.query(AdvCampaign).filter(AdvCampaign.id == campaign.id).with_for_update().one()
    if campaign.status not in ("DRAFT", "CHANGES_REQUESTED", "PENDING_REVIEW"):
        raise AdError("INVALID_STATE", "Only a campaign that has not started serving can be cancelled")
    campaign.status = "CANCELLED"
    campaign.completed_at, campaign.completion_reason = datetime.utcnow(), "CANCELLED_BY_ADVERTISER"
    _audit(db, advertiser.id, campaign, "CANCEL", {"status": campaign.status})
    db.flush()
    settle_campaign(db, campaign, reason="CANCELLED")
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
    if actor.id != campaign.advertiser_user_id:
        notify(db, campaign, "PAUSED" if paused else "RESUMED")
    return campaign


def complete_campaign(db: Session, campaign: AdvCampaign, *, reason: str, actor_id: Optional[int] = None) -> AdvCampaign:
    """Stop serving. Unspent budget returns to credit once no reservation is open (settle_campaign)."""
    if campaign.status in CLOSED_STATUSES:
        return campaign
    campaign.status = "COMPLETED"
    campaign.completed_at, campaign.completion_reason = datetime.utcnow(), reason[:40]
    _audit(db, actor_id, campaign, "COMPLETE", {"reason": reason})
    db.flush()
    notify(db, campaign, "BUDGET_EXHAUSTED" if reason == "BUDGET_EXHAUSTED" else "COMPLETED")
    return campaign


def settle_campaign(db: Session, campaign: AdvCampaign, *, reason: str) -> Optional[AdvCreditMovement]:
    """Return the unspent budget to the advertiser's credit, once, after every reservation is closed and
    every charged day is recognized. Charges are recognized in whole cents, rounded down, so the
    advertiser is never charged a fraction of a cent."""
    from app.models.advertising_v2 import AdvCampaignDay

    if campaign.settled_at is not None or Decimal(str(campaign.reserved or 0)) > 0:
        return None
    if campaign.status not in CLOSED_STATUSES:
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


def campaign_report(db: Session, campaign: AdvCampaign, *, detail: bool = True) -> dict:
    """Advertiser / administrator view. Only tracked metrics: clicks are not recorded (members are never
    paid for clicks and no click event exists), so they are reported as unavailable, never estimated."""
    from app.models.advertising_v2 import AdvCampaignDay, AdvImpressionEvent, AdvServeDecision

    valid = (db.query(func.count(AdvImpressionEvent.id))
             .filter(AdvImpressionEvent.campaign_id == campaign.id, AdvImpressionEvent.event_type == "VIEWABLE",
                     AdvImpressionEvent.validation_status == "VALID", AdvImpressionEvent.reversed_at.is_(None)).scalar())
    invalid = (db.query(func.count(AdvImpressionEvent.id))
               .join(AdvServeDecision, AdvServeDecision.id == AdvImpressionEvent.decision_id)
               .filter(AdvServeDecision.campaign_id == campaign.id,
                       AdvImpressionEvent.validation_status == "INVALID").scalar())
    served = (db.query(func.count(AdvImpressionEvent.id))
              .join(AdvServeDecision, AdvServeDecision.id == AdvImpressionEvent.decision_id)
              .filter(AdvServeDecision.campaign_id == campaign.id, AdvImpressionEvent.event_type == "SERVED").scalar())
    days = (db.query(AdvCampaignDay).filter(AdvCampaignDay.campaign_id == campaign.id)
            .order_by(AdvCampaignDay.day.desc()).limit(31).all())
    budget = money(campaign.budget_total)
    spent = floor_cents(campaign.spent)
    remaining = budget - spent
    out = {
        "id": campaign.id, "name": campaign.name, "status": campaign.status, "currency": campaign.currency,
        "pricing_model": campaign.pricing_model,
        "cpm_rate_usd": str(campaign.cpm_rate_usd) if campaign.cpm_rate_usd is not None else None,
        "budget_total": str(budget), "daily_cap": str(campaign.daily_cap) if campaign.daily_cap is not None else None,
        "spent": str(spent), "reserved": str(Decimal(str(campaign.reserved or 0))),
        "remaining_budget": str(remaining),
        "estimated_impressions": estimated_impressions(budget, campaign.cpm_rate_usd),
        "estimated_remaining_impressions": estimated_impressions(remaining, campaign.cpm_rate_usd),
        "delivery_progress_percent": (str((spent * 100 / budget).quantize(Decimal("0.1"), rounding=ROUND_DOWN))
                                      if budget > 0 else "0.0"),
        "start_at": campaign.start_at.isoformat() if campaign.start_at else None,
        "end_at": campaign.end_at.isoformat() if campaign.end_at else None,
        "placements": campaign.placements or [], "targeting": campaign.targeting or {},
        "served_impressions": int(served or 0), "valid_impressions": int(valid or 0), "invalid_events": int(invalid or 0),
        "clicks": None, "clicks_note": "Not tracked",
        "funding": _funding_state(db, campaign),
        "completion_reason": campaign.completion_reason, "review_note": campaign.review_note,
        "daily": [{"day": d.day.isoformat(), "spent": str(floor_cents(d.spent)),
                   "recognized": d.recognized_journal_id is not None} for d in days],
    }
    if detail:
        out["by_placement"] = _breakdown(db, campaign.id, AdvServeDecision.slot_kind)
        out["by_creative"] = _breakdown(db, campaign.id, AdvServeDecision.creative_id)
        out["creatives"] = [creative_payload(cr) for cr in db.query(AdvCreative)
                            .filter(AdvCreative.campaign_id == campaign.id).order_by(AdvCreative.id.asc()).all()]
    return out


def _funding_state(db: Session, campaign: AdvCampaign) -> str:
    """NOT_FUNDED (draft: no money moved) / FUNDED (budget moved from credit at submission) / RETURNED
    (unspent budget given back to credit when the campaign closed)."""
    keys = {k for (k,) in db.query(AdvCreditMovement.idempotency_key)
            .filter(AdvCreditMovement.campaign_id == campaign.id).all()}
    if f"campaign:{campaign.id}:release" in keys:
        return "UNSPENT_RETURNED"
    return "FUNDED" if f"campaign:{campaign.id}:allocate" in keys else "NOT_FUNDED"


def _breakdown(db: Session, campaign_id: int, column) -> list:
    """Valid viewable impressions and charged spend per placement kind or creative."""
    from app.models.advertising_v2 import AdvImpressionEvent, AdvServeDecision

    rows = (db.query(column, func.count(AdvImpressionEvent.id), func.coalesce(func.sum(AdvImpressionEvent.charged_amount), 0))
            .join(AdvServeDecision, AdvServeDecision.id == AdvImpressionEvent.decision_id)
            .filter(AdvServeDecision.campaign_id == campaign_id, AdvImpressionEvent.event_type == "VIEWABLE",
                    AdvImpressionEvent.validation_status == "VALID", AdvImpressionEvent.reversed_at.is_(None))
            .group_by(column).all())
    return [{"key": k, "valid_impressions": int(n), "spend": str(floor_cents(a))} for k, n, a in rows]


def creative_payload(cr: AdvCreative) -> dict:
    return {"id": cr.id, "headline": cr.headline, "body": cr.body, "image_url": cr.image_url,
            "destination_url": cr.destination_url, "review_status": cr.review_status, "review_note": cr.review_note,
            "image": ({"mime": cr.image_mime, "bytes": cr.image_bytes, "width": cr.image_width,
                       "height": cr.image_height} if cr.image_mime else None)}


# ---------------------------------------------------------------- pricing helpers and packages

def estimated_impressions(budget, cpm) -> Optional[int]:
    """Theoretical allowance of billable impressions for a budget at a CPM (budget / (CPM / 1000)),
    rounded down. Not a delivery promise: delivery depends on eligible inventory and validation."""
    if cpm is None or Decimal(str(cpm)) <= 0:
        return None
    unit = unit_price(cpm)
    if unit <= 0:
        return None
    return int((money(budget) / unit).to_integral_value(rounding=ROUND_DOWN))


def packages(db: Session) -> list:
    """Every advertising product the application represents, with its real terms and state. Nothing here is
    invented: a product without an approved price is reported as not purchasable with the decision needed."""
    from app.core.config import settings as app_settings

    cfg = get_settings(db)
    cpm = cfg.cpm_rate_usd
    priced = pricing_state(cfg) == "CONFIGURED"
    min_budget = cfg.min_campaign_budget_usd
    return [
        {"code": "MYHIGH5_CPM_CAMPAIGN", "name": "MyHigh5 CPM campaign", "type": "CPM",
         "price": str(cpm) if cpm is not None else None, "price_unit": "USD per 1,000 valid viewable impressions",
         "currency": "USD", "minimum_budget": str(min_budget) if min_budget is not None else None,
         "estimated_impressions_at_minimum": estimated_impressions(min_budget, cpm) if min_budget else None,
         "duration": "Chosen by the advertiser (start and end date)", "impression_allowance": "Budget / CPM x 1,000",
         "placements": list(SLOT_KINDS), "targeting": ["countries", "page_types"],
         "renewal": "None: a campaign ends at its end date or when its budget is spent",
         "revenue_sharing": "Contest-entry pages only: creative 20% (personal) / 10% (nomination), direct sponsor 1%",
         "payment": "Prepaid advertiser credit (SoncoPay checkout); the budget moves into the campaign at submission",
         "admin_controls": "Price, minimum budget, creative and campaign review, pause/resume, request changes",
         "state": ("AVAILABLE" if priced and cfg.campaigns_enabled and cfg.funding_enabled
                   else "PRICED_NOT_ACTIVATED" if priced else "PRICE_PENDING_APPROVAL"),
         "purchasable": bool(priced and cfg.campaigns_enabled and cfg.funding_enabled)},
        {"code": "ADVERTISER_CREDIT", "name": "MyHigh5 advertiser credit", "type": "PREPAID_CREDIT",
         "price": "1.00", "price_unit": "USD per unit (face value)", "currency": "USD", "minimum_budget": None,
         "duration": "No expiry", "impression_allowance": None, "placements": [], "targeting": [],
         "renewal": "None", "revenue_sharing": "None (a liability until validated delivery)",
         "payment": "SoncoPay checkout (product advertising_credit)",
         "admin_controls": "Funding switch", "state": "AVAILABLE" if (priced and cfg.funding_enabled) else "FUNDING_OFF",
         "purchasable": bool(priced and cfg.funding_enabled)},
        {"code": "GOOGLE_ADSENSE", "name": "Google AdSense fallback", "type": "THIRD_PARTY_FALLBACK",
         "price": None, "price_unit": "Set by Google", "currency": None, "minimum_budget": None,
         "duration": None, "impression_allowance": None, "placements": list(SLOT_KINDS), "targeting": [],
         "renewal": None, "revenue_sharing": "Only after finalized Google earnings and the AdSense sharing switch",
         "payment": "Paid by Google to MyHigh5", "admin_controls": "Fallback switch, sharing switch, monthly finalization",
         "state": "FALLBACK_ON" if cfg.adsense_fallback_enabled else "FALLBACK_OFF", "purchasable": False},
        {"code": "ANNUAL_ADS", "name": "Annual Ads (partner platform)", "type": "EXTERNAL_PLATFORM",
         "price": None, "price_unit": "Set on the Annual Ads platform", "currency": None, "minimum_budget": None,
         "duration": "Annual (Annual Ads terms)", "impression_allowance": None, "placements": [], "targeting": [],
         "renewal": "Annual Ads terms", "revenue_sharing": "Excluded from contest-entry revenue sharing",
         "payment": "Annual Ads checkout (not MyHigh5)", "admin_controls": "ANNUALADS_ENABLED server setting",
         "state": "ENABLED" if bool(getattr(app_settings, "ANNUALADS_ENABLED", False)) else "DISABLED",
         "purchasable": False},
        {"code": "LEGACY_AD_SYSTEM", "name": "Legacy ad_* campaigns (CPC/CPM/CPA/flat)", "type": "RETIRED",
         "price": None, "price_unit": None, "currency": None, "minimum_budget": None, "duration": None,
         "impression_allowance": None, "placements": [], "targeting": [], "renewal": None,
         "revenue_sharing": "Unapproved 40/10 design, never used", "payment": None,
         "admin_controls": "None (API never mounted)", "state": "RETIRED", "purchasable": False},
    ]


# ---------------------------------------------------------------- creative images

def own_upload_url(advertiser_id: int, url: str) -> str:
    """An uploaded image may be used only by the advertiser who uploaded it (path /api/v1/media/file/<uid>/<file>)."""
    import re

    m = re.fullmatch(r"/api/v1/media/file/(\d+)/([0-9a-f-]{36}\.(?:jpg|png|webp|gif))", url or "")
    if not m or int(m.group(1)) != int(advertiser_id):
        raise AdError("IMAGE_NOT_OWNED", "Use an image you uploaded for this campaign", 403)
    return url


def check_creative_image(metadata: dict) -> None:
    """Advertising limits on top of the media storage validation (signature, MIME, extension, pixels)."""
    if metadata.get("media_type") != "image" or metadata.get("content_type") not in CREATIVE_IMAGE_TYPES:
        raise AdError("INVALID_IMAGE", "Upload a JPEG, PNG, WebP or GIF image", 400)
    if int(metadata.get("file_size") or 0) > CREATIVE_IMAGE_MAX_BYTES:
        raise AdError("INVALID_IMAGE", "The image must be at most 2 MB", 400)
    w, h = int(metadata.get("width") or 0), int(metadata.get("height") or 0)
    if not (CREATIVE_MIN_SIDE <= w <= CREATIVE_MAX_SIDE and CREATIVE_MIN_SIDE <= h <= CREATIVE_MAX_SIDE):
        raise AdError("INVALID_IMAGE", f"Image sides must be between {CREATIVE_MIN_SIDE} and {CREATIVE_MAX_SIDE} pixels", 400)


def attach_image(db: Session, creative: AdvCreative, stored: dict, *, actor_id: Optional[int] = None) -> AdvCreative:
    """Use a stored upload as the creative's image. A changed image sends the creative back to review."""
    meta = stored.get("metadata") or {}
    creative.image_url = stored["url"]
    creative.image_mime, creative.image_bytes = meta.get("content_type"), meta.get("file_size")
    creative.image_width, creative.image_height = meta.get("width"), meta.get("height")
    if creative.review_status != "PENDING":
        creative.review_status, creative.reviewed_at, creative.reviewed_by_user_id = "PENDING", None, None
    db.add(AuditTrail(table_name="adv_creatives", record_id=creative.id, action="IMAGE_UPLOAD", old_values=None,
                      new_values={"mime": creative.image_mime, "bytes": creative.image_bytes,
                                  "width": creative.image_width, "height": creative.image_height}, user_id=actor_id))
    db.flush()
    return creative


# ---------------------------------------------------------------- notifications

_PENDING = "adv_pending_emails"


def notify(db: Session, campaign: AdvCampaign, kind: str) -> bool:
    """Queue one email to the advertiser for this campaign transition. Nothing is written here: the email
    service commits on its own, so emails are recorded only by send_pending() AFTER the caller committed
    (an email can never commit half of a campaign action). Nothing while campaigns are switched off."""
    try:
        if not get_settings(db).campaigns_enabled:
            return False
        n = db.query(func.count(AuditTrail.id)).filter(AuditTrail.table_name == "adv_campaigns",
                                                       AuditTrail.record_id == campaign.id).scalar()
        db.info.setdefault(_PENDING, []).append(
            (campaign.advertiser_user_id, f"adv-campaign:{campaign.id}:{kind}:{int(n or 0)}",
             {"kind": kind, "campaign": campaign.name[:80], "campaign_id": campaign.id,
              "note": (campaign.review_note or "")[:300]}))
        return True
    except Exception:  # noqa: BLE001 - an email never blocks a campaign action
        import logging

        logging.getLogger(__name__).exception("Advertising email for campaign %s could not be queued", campaign.id)
        return False


def notify_share_released(db: Session, line) -> bool:
    """Queue (see notify) the member's email for a released contest-page ad share (sharing switched on)."""
    try:
        if not get_settings(db).contest_sharing_enabled or not line.beneficiary_user_id:
            return False
        db.info.setdefault(_PENDING, []).append(
            (int(line.beneficiary_user_id), f"adv-share:{line.id}",
             {"kind": "SHARE_RELEASED", "amount": str(money(line.amount)), "period": line.period, "role": line.role}))
        return True
    except Exception:  # noqa: BLE001
        import logging

        logging.getLogger(__name__).exception("Advertising share email for line %s could not be queued", line.id)
        return False


def send_pending(db: Session) -> int:
    """Record the queued advertising emails. Call only AFTER the caller's commit (or rollback: a rolled-back
    action must call discard_pending instead). Idempotent by key; never raises."""
    pending = db.info.pop(_PENDING, [])
    sent = 0
    if not pending:
        return 0
    from app.models.user import User
    from app.services.email import email_service
    from app.services.email_events import EmailEvent

    for user_id, key, context in pending:
        try:
            user = db.query(User).filter(User.id == user_id).first()
            if user is None or not user.email or not user.is_active:
                continue
            if email_service.enqueue(db, event=EmailEvent.BILLING_ADVERTISING_UPDATE, recipient=user.email,
                                     idempotency_key=key, user_id=user.id, context=context) is not None:
                sent += 1
        except Exception:  # noqa: BLE001
            import logging

            logging.getLogger(__name__).exception("Advertising email %s could not be recorded", key)
            db.rollback()
    return sent


def discard_pending(db: Session) -> None:
    db.info.pop(_PENDING, None)


# ---------------------------------------------------------------- reconciliation (read-only)

def reconciliation(db: Session) -> dict:
    """Advertising money checks, read-only:
      * advertiser credit sub-ledger (adv_credit_movements) + budgets in open campaigns == liability 2320;
      * no campaign over budget or negative;
      * recognized revenue 4020 == recognized campaign days (cents, rounded down);
      * charged impressions == campaign spend."""
    from app.models.accounting import ChartOfAccounts, JournalLine
    from app.models.advertising_v2 import AdvCampaignDay, AdvImpressionEvent

    def balance(code: str) -> Decimal:
        row = (db.query(func.coalesce(func.sum(JournalLine.credit_amount), 0) - func.coalesce(func.sum(JournalLine.debit_amount), 0))
               .join(ChartOfAccounts, ChartOfAccounts.id == JournalLine.account_id)
               .filter(ChartOfAccounts.account_code == code).scalar())
        return money(row or 0)

    credit = money(db.query(func.coalesce(func.sum(AdvCreditMovement.amount), 0)).scalar() or 0)
    campaigns = db.query(AdvCampaign).all()
    funded = {m.campaign_id for m in db.query(AdvCreditMovement).filter(AdvCreditMovement.movement_type == "ALLOCATE")}
    open_budgets = sum((money(c.budget_total) for c in campaigns if c.id in funded and c.settled_at is None),
                       Decimal("0.00"))
    settled_spend = sum((floor_cents(c.spent) for c in campaigns if c.id in funded and c.settled_at is not None),
                        Decimal("0.00"))
    charged = Decimal(str(db.query(func.coalesce(func.sum(AdvImpressionEvent.charged_amount), 0))
                          .filter(AdvImpressionEvent.reversed_at.is_(None)).scalar() or 0))
    spent = sum((Decimal(str(c.spent or 0)) for c in campaigns), Decimal("0"))
    unrecognized_days = (db.query(func.count(AdvCampaignDay.id))
                         .filter(AdvCampaignDay.spent > 0, AdvCampaignDay.recognized_at.is_(None)).scalar())
    over = [c.id for c in campaigns if Decimal(str(c.spent or 0)) + Decimal(str(c.reserved or 0)) > Decimal(str(c.budget_total))
            or Decimal(str(c.spent or 0)) < 0 or Decimal(str(c.reserved or 0)) < 0]
    liability = balance(CREDIT_ACCOUNT)
    revenue = balance(ORDINARY_REVENUE_ACCOUNT)
    # 2320 = unallocated credit + budgets of funded open campaigns - revenue already recognized on them.
    expected_liability = credit + open_budgets - (revenue - settled_spend)
    checks = [
        {"check": "credit_liability", "expected": str(expected_liability), "actual": str(liability),
         "ok": expected_liability == liability,
         "detail": "Advertiser credit + funded open budgets - revenue recognized on them = account 2320"},
        {"check": "recognized_revenue_not_above_spend", "expected": f"<= {floor_cents(spent)}", "actual": str(revenue),
         "ok": revenue <= sum((floor_cents(c.spent) for c in campaigns), Decimal("0.00")),
         "detail": f"Account 4020 never exceeds charged spend; {int(unrecognized_days or 0)} charged day(s) await recognition"},
        {"check": "charged_vs_spent", "expected": str(spent), "actual": str(charged), "ok": spent == charged,
         "detail": "Charged valid impressions = campaign spend"},
        {"check": "budgets_within_limits", "expected": "[]", "actual": str(over), "ok": not over,
         "detail": "No campaign spent + reserved above its budget, nothing negative"},
    ]
    return {"ok": all(c["ok"] for c in checks), "checks": checks, "unallocated_credit": str(credit),
            "funded_open_budgets": str(open_budgets), "read_only": True}


def suspicious_activity(db: Session, *, limit: int = 100) -> dict:
    """Invalid impression events by reason and the most recent ones (for administrator review)."""
    from app.models.advertising_v2 import AdvImpressionEvent

    by_reason = dict(db.query(AdvImpressionEvent.invalid_reason, func.count(AdvImpressionEvent.id))
                     .filter(AdvImpressionEvent.validation_status == "INVALID")
                     .group_by(AdvImpressionEvent.invalid_reason).all())
    recent = (db.query(AdvImpressionEvent).filter(AdvImpressionEvent.validation_status == "INVALID")
              .order_by(AdvImpressionEvent.id.desc()).limit(limit).all())
    reversed_n = db.query(func.count(AdvImpressionEvent.id)).filter(AdvImpressionEvent.reversed_at.isnot(None)).scalar()
    return {"invalid_by_reason": {str(k): int(v) for k, v in by_reason.items()}, "reversed_events": int(reversed_n or 0),
            "recent": [{"id": e.id, "decision_id": e.decision_id, "event_type": e.event_type,
                        "reason": e.invalid_reason, "received_at": e.received_at.isoformat() if e.received_at else None,
                        "is_bot_ua": e.is_bot_ua} for e in recent]}
