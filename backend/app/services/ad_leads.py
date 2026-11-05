"""Lead package foundation (Advertising Phase A). Lead collection is CLOSED: ad_packages marks Lead NOT READY
until a retention period and a privacy notice are approved, so ``submit`` refuses and no personal data is
ever stored. The lifecycle below is the approved contract the later collection form will use:

  SUBMITTED (consent recorded, contact hashed) -> ACCEPTED (by the advertiser, within 7 days) -> charged ONCE
                                               -> REJECTED (closed list of reasons)          -> never charged
                                               -> EXPIRED  (no answer within 7 days)         -> never charged
  ACCEPTED -> REVERSED (finance administrator, audited): the charge is credited back once.
There is NO automatic acceptance (owner decision 2026-11-04): silence never bills the advertiser.
Duplicate: the same normalised contact for the same campaign (keyed hash, unique in the database).
Only an ACCEPTED lead is billable; the charge is atomic against the campaign's remaining budget.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.advertising_v2 import AdvCampaign, AdvLead
from app.services import ad_packages as pk

ACCEPTANCE_WINDOW = timedelta(days=7)
# Retention (owner-approved defaults): identifiable data of rejected / expired leads is erased 30 days after the
# decision, of accepted (and later reversed) leads after 90 days. Status, charge and audit rows are kept.
RETENTION_UNACCEPTED = timedelta(days=30)
RETENTION_ACCEPTED = timedelta(days=90)
PII_PURPOSE = "mh5-ads:lead-pii"
REJECTION_REASONS = ("DUPLICATE", "INVALID_CONTACT", "OUT_OF_TARGET", "TEST_OR_FAKE")


class LeadError(Exception):
    def __init__(self, code: str, message: str, status: int = 409):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def contact_hash(contact: str) -> str:
    """Keyed hash of a normalised e-mail or phone number: duplicates can be detected without keeping it."""
    normal = "".join(str(contact or "").strip().lower().split())
    if len(normal) < 5:
        raise LeadError("INVALID_CONTACT", "A valid e-mail address or phone number is required", 400)
    key = (os.getenv("AD_VIEWER_SECRET") or os.getenv("SECRET_KEY") or "mh5-lead").encode()
    return hmac.new(key, f"lead:{normal}".encode(), hashlib.sha256).hexdigest()


def submit(db: Session, *, campaign_id: int, name: str, contact: str, consent: bool, consent_version: str,
           decision_id: Optional[str] = None, privacy_notice_version: Optional[str] = None,
           advertiser_identity: Optional[str] = None, now: Optional[datetime] = None) -> AdvLead:
    """Refused while the Lead package is not ready (final legal/privacy readiness not verified): nothing is
    stored."""
    package = pk.PACKAGES["lead"]
    if package.not_ready:
        raise LeadError("NOT_READY", f"Lead collection is closed: {package.not_ready}")
    return _record(db, campaign_id=campaign_id, name=name, contact=contact, consent=consent,
                   consent_version=consent_version, decision_id=decision_id,
                   privacy_notice_version=privacy_notice_version, advertiser_identity=advertiser_identity, now=now)


def _record(db: Session, *, campaign_id: int, name: str, contact: str, consent: bool, consent_version: str,
            decision_id: Optional[str], now: Optional[datetime], privacy_notice_version: Optional[str] = None,
            advertiser_identity: Optional[str] = None) -> AdvLead:
    from app.services import payment_crypto

    now = now or datetime.utcnow()
    if not (name or "").strip():
        raise LeadError("NAME_REQUIRED", "A name is required", 400)
    if not consent or not (consent_version or "").strip():
        raise LeadError("CONSENT_REQUIRED", "Explicit consent to share the details with the advertiser is required",
                        400)
    if not (privacy_notice_version or "").strip() or not (advertiser_identity or "").strip():
        raise LeadError("PRIVACY_NOTICE_REQUIRED", "The member must be shown the privacy notice and the advertiser "
                                                   "identity before sharing details", 400)
    if not payment_crypto.key_configured():
        raise LeadError("ENCRYPTION_UNAVAILABLE", "Lead details cannot be stored securely: encryption is not "
                                                  "configured", 503)
    campaign = db.query(AdvCampaign).filter(AdvCampaign.id == campaign_id).first()
    if campaign is None or pk.of_model(campaign.pricing_model).code != "lead":
        raise LeadError("NOT_A_LEAD_CAMPAIGN", "This campaign does not collect leads", 400)
    pii = json.dumps({"name": name.strip()[:120], "contact": str(contact).strip()[:200]})   # nothing else is kept
    lead = AdvLead(campaign_id=campaign_id, decision_id=decision_id, contact_hash=contact_hash(contact),
                   consent_version=consent_version.strip()[:40], consented_at=now, status="SUBMITTED",
                   decision_deadline=now + ACCEPTANCE_WINDOW,
                   pii_ciphertext=payment_crypto.encrypt(pii, PII_PURPOSE),
                   privacy_notice_version=privacy_notice_version.strip()[:40],
                   advertiser_identity=advertiser_identity.strip()[:120])
    try:
        with db.begin_nested():
            db.add(lead)
            db.flush()
    except IntegrityError:
        raise LeadError("DUPLICATE", "This contact already sent a lead to this campaign") from None
    return lead


def accept(db: Session, lead_id: int, *, actor_id: Optional[int] = None, now: Optional[datetime] = None) -> AdvLead:
    """An explicit advertiser decision within the 7-day window: accept once and charge once (row lock +
    status). After the window the lead can only expire, unbilled."""
    from app.services.ad_delivery import charge_direct

    now = now or datetime.utcnow()
    lead = db.query(AdvLead).filter(AdvLead.id == lead_id).with_for_update().one()
    if lead.status != "SUBMITTED":
        raise LeadError("ALREADY_DECIDED", f"This lead is already {lead.status.lower()}")
    if now > lead.decision_deadline:
        raise LeadError("WINDOW_CLOSED", "The 7-day decision window has passed")
    if lead.pii_purged_at is not None:
        raise LeadError("ERASED", "The member asked for this lead to be deleted: it cannot be accepted or charged")
    campaign = db.query(AdvCampaign).filter(AdvCampaign.id == lead.campaign_id).with_for_update().one()
    from app.services.ad_campaigns import get_settings

    cfg = get_settings(db)
    if not cfg.campaigns_enabled or not pk.deliverable(cfg, pk.PACKAGES["lead"])[0]:
        raise LeadError("PACKAGE_DISABLED", "The Lead package is switched off: no lead can be charged")
    price = _lead_price(campaign)
    if not charge_direct(db, campaign.id, price, now.date()):
        raise LeadError("BUDGET_EXHAUSTED", "The campaign budget cannot pay this lead")
    lead.status, lead.decided_at, lead.decided_by_user_id = "ACCEPTED", now, actor_id
    lead.charged_amount, lead.charge_day = price, now.date()
    db.flush()
    return lead  # leads reserve nothing at serving (ad_packages): this is their only charge


def expire_unanswered(db: Session, *, now: Optional[datetime] = None, limit: int = 500) -> int:
    """Leads the advertiser did not answer within the window become EXPIRED: never charged, never accepted.
    Idempotent (only SUBMITTED rows past their deadline change, under a row lock)."""
    now = now or datetime.utcnow()
    rows = (db.query(AdvLead).filter(AdvLead.status == "SUBMITTED", AdvLead.decision_deadline < now)
            .order_by(AdvLead.id.asc()).limit(limit).with_for_update(skip_locked=True).all())
    for lead in rows:
        lead.status, lead.decided_at = "EXPIRED", now
    db.flush()
    return len(rows)


def reverse(db: Session, lead_id: int, *, actor_id: int, reason: str, now: Optional[datetime] = None) -> AdvLead:
    """Reverse an ACCEPTED, charged lead exactly once (lead row lock + status): the charge leaves the
    campaign's spend (Dr 4020 / Cr 2320 when that day was already recognized) and, if the campaign is already
    settled, returns to the advertiser's credit (movement lead:<id>:reversal). Audited. No commission or
    earning exists for leads in Phase A, so nothing else is adjusted."""
    from app.models.accounting import AuditTrail
    from app.services.ad_delivery import _credit_back

    if not (reason or "").strip() or len(reason.strip()) < 3:
        raise LeadError("NOTE_REQUIRED", "A reason is required", 400)
    now = now or datetime.utcnow()
    # Lock order lead -> campaign, as in accept(): the two can never deadlock on the same lead.
    lead = db.query(AdvLead).filter(AdvLead.id == lead_id).with_for_update().first()
    if lead is None:
        raise LeadError("NOT_FOUND", "Lead not found", 404)
    campaign = db.query(AdvCampaign).filter(AdvCampaign.id == lead.campaign_id).with_for_update().one()
    if lead.status != "ACCEPTED" or lead.reversed_at is not None:
        raise LeadError("NOT_REVERSIBLE", f"Only an accepted, charged lead can be reversed (this one is "
                                          f"{lead.status.lower()})")
    amount = Decimal(str(lead.charged_amount or 0))
    _credit_back(db, campaign, lead.charge_day, amount, journal_suffix=f"lead-reversal:{lead.id}",
                 movement_key=f"lead:{lead.id}:reversal", note=f"Accepted lead {lead.id} reversed: {reason.strip()}",
                 actor_id=actor_id, release_budget=False)
    lead.status, lead.reversed_at, lead.reversed_by_user_id = "REVERSED", now, actor_id
    lead.reversal_reason = reason.strip()[:200]
    db.add(AuditTrail(table_name="adv_leads", record_id=lead.id, action="REVERSE",
                      old_values={"status": "ACCEPTED", "charged_amount": str(amount)},
                      new_values={"status": "REVERSED", "reason": reason.strip()[:200]}, user_id=actor_id))
    db.flush()
    return lead


def reject(db: Session, lead_id: int, *, reason: str, actor_id: Optional[int] = None,
           now: Optional[datetime] = None) -> AdvLead:
    now = now or datetime.utcnow()
    if reason not in REJECTION_REASONS:
        raise LeadError("INVALID_REASON", f"Choose one of: {', '.join(REJECTION_REASONS)}", 400)
    lead = db.query(AdvLead).filter(AdvLead.id == lead_id).with_for_update().one()
    if lead.status != "SUBMITTED":
        raise LeadError("ALREADY_DECIDED", f"This lead is already {lead.status.lower()}")
    if now > lead.decision_deadline:
        raise LeadError("WINDOW_CLOSED", "The 7-day decision window has passed")
    lead.status, lead.decided_at, lead.decided_by_user_id, lead.rejection_reason = "REJECTED", now, actor_id, reason
    db.flush()
    return lead


def _lead_price(campaign: AdvCampaign) -> Decimal:
    package = pk.PACKAGES["lead"]
    return pk.unit_charge(package, pk.validate_rate(package, campaign.unit_rate_usd))


# ---------------------------------------------------------------- privacy: access, export, deletion, retention

def _log(db: Session, lead: AdvLead, actor_id: Optional[int], action: str, detail: str = "") -> None:
    from app.models.advertising_v2 import AdvLeadAccess

    db.add(AdvLeadAccess(lead_id=lead.id, actor_user_id=actor_id, action=action, detail=detail[:200] or None))


def _may_read(db: Session, lead: AdvLead, actor) -> bool:
    """The campaign's advertiser for an ACCEPTED lead only; an administrator with manage_advertising always."""
    from app.services.ad_campaigns import PERMISSION_MANAGE
    from app.services.admin_security import has_permission

    if actor is None:
        return False
    if has_permission(actor, PERMISSION_MANAGE):
        return True
    campaign = db.query(AdvCampaign).filter(AdvCampaign.id == lead.campaign_id).first()
    return campaign is not None and int(campaign.advertiser_user_id) == int(actor.id) and lead.status == "ACCEPTED"


def read_details(db: Session, lead_id: int, actor, *, export: bool = False) -> dict:
    """Decrypt a lead's contact details for an authorised reader; every read or export is logged."""
    from app.services import payment_crypto

    lead = db.query(AdvLead).filter(AdvLead.id == lead_id).first()
    if lead is None:
        raise LeadError("NOT_FOUND", "Lead not found", 404)
    if not _may_read(db, lead, actor):
        raise LeadError("FORBIDDEN", "You may not access this lead", 403)
    if lead.pii_ciphertext is None:
        raise LeadError("ERASED", "This lead's personal data was erased", 410)
    details = json.loads(payment_crypto.decrypt(lead.pii_ciphertext, PII_PURPOSE))
    _log(db, lead, actor.id, "EXPORT" if export else "VIEW")
    db.flush()
    return {"lead_id": lead.id, "advertiser_identity": lead.advertiser_identity,
            "privacy_notice_version": lead.privacy_notice_version, "consent_version": lead.consent_version,
            "consented_at": lead.consented_at.isoformat(), **details}


def _erase(lead: AdvLead, now: datetime) -> None:
    # The readable details go. The keyed hash (HMAC with a server secret, not reversible) stays so the same
    # contact cannot be sold to the same campaign twice; whether it may be kept is a legal-readiness item.
    lead.pii_ciphertext = None
    lead.pii_purged_at = now


def request_deletion(db: Session, lead_id: int, *, actor_id: Optional[int], now: Optional[datetime] = None) -> AdvLead:
    """A deletion request erases the identifiable data at once; the lead's status, charge and audit stay
    (financial evidence is never deleted)."""
    now = now or datetime.utcnow()
    lead = db.query(AdvLead).filter(AdvLead.id == lead_id).with_for_update().first()
    if lead is None:
        raise LeadError("NOT_FOUND", "Lead not found", 404)
    if lead.deletion_requested_at is None:
        lead.deletion_requested_at = now
    if lead.pii_purged_at is None:
        _erase(lead, now)
        _log(db, lead, actor_id, "DELETE", "deletion request")
    db.flush()
    return lead


def purge_expired(db: Session, *, now: Optional[datetime] = None, limit: int = 500) -> int:
    """Retention: erase identifiable data past its period. Only the personal-data columns change; status,
    charged_amount, charge_day, reversal and audit rows are untouched. Idempotent."""
    from sqlalchemy import and_, or_

    now = now or datetime.utcnow()
    rows = (db.query(AdvLead)
            .filter(AdvLead.pii_purged_at.is_(None), AdvLead.decided_at.isnot(None),
                    or_(and_(AdvLead.status.in_(("REJECTED", "EXPIRED")),
                             AdvLead.decided_at < now - RETENTION_UNACCEPTED),
                        and_(AdvLead.status.in_(("ACCEPTED", "REVERSED")),
                             AdvLead.decided_at < now - RETENTION_ACCEPTED)))
            .order_by(AdvLead.id.asc()).limit(limit).with_for_update(skip_locked=True).all())
    for lead in rows:
        _erase(lead, now)
        _log(db, lead, None, "PURGE", f"retention ({lead.status})")
    db.flush()
    return len(rows)
