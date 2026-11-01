"""Annual Ads: audit records, buyer attribution and scheduled revenue recognition.

The Annual Ads product, prices and entitlements belong to the Annual Ads platform. MyHigh5 keeps:
  * the existing posting (Dr 1030 / Cr 2310 at the net agent amount; daily Dr 2310 / Cr 4010);
  * one adv_annualads_payments row per signed webhook payment, with the buyer matched ONLY through a
    signed field equal to the SSO subject MyHigh5 issued (users.id), and the payload's entitlement
    fields copied verbatim (never invented);
  * no Type 1 sponsor commission is posted automatically: its base (gross vs net) is not approved
    (sponsor_commission_status = PENDING_POLICY).
Annual Ads never enters contest-entry revenue sharing, AdSense or ordinary advertising accounts.
"""
from __future__ import annotations

import hashlib
import logging
from decimal import Decimal
from typing import Any, Mapping, Optional

from sqlalchemy.orm import Session

from app.models.advertising_v2 import AdvAnnualAdsPayment

logger = logging.getLogger(__name__)

BUYER_FIELDS = ("buyer_external_id", "external_user_id", "sso_sub", "member_external_id")
ENTITLEMENT_FIELDS = ("order_id", "campaign_id", "ad_id", "slot_id", "placement", "placement_id", "package",
                      "package_id", "start_date", "end_date", "duration_days", "starts_at", "ends_at")


def _buyer_reference(payment: Mapping[str, Any], data: Mapping[str, Any]) -> Optional[str]:
    for block in (payment, data, data.get("buyer") if isinstance(data.get("buyer"), dict) else {},
                  payment.get("buyer") if isinstance(payment.get("buyer"), dict) else {}):
        for field in BUYER_FIELDS + ("external_id",):
            value = block.get(field) if isinstance(block, Mapping) else None
            if value not in (None, ""):
                return str(value).strip()[:64]
    return None


def record_payment(db: Session, *, tx_hash: str, event: str, payment: Mapping[str, Any], data: Mapping[str, Any],
                   raw: bytes, gross: Decimal, fee: Decimal, net: Decimal,
                   journal_entry_id: Optional[int]) -> AdvAnnualAdsPayment:
    """Insert-or-get the audit record of one signed Annual Ads payment."""
    from app.models.user import User

    existing = db.query(AdvAnnualAdsPayment).filter(AdvAnnualAdsPayment.tx_hash == tx_hash).first()
    if existing is not None:
        if existing.journal_entry_id is None and journal_entry_id:
            existing.journal_entry_id = journal_entry_id
        return existing
    reference = _buyer_reference(payment, data)
    buyer_id, match = None, "ABSENT"
    if reference is not None:
        match = "UNMATCHED"
        if reference.isdigit():
            user = db.query(User).filter(User.id == int(reference)).first()
            if user is not None and not getattr(user, "is_deleted", False):
                buyer_id, match = user.id, "MATCHED"
    snapshot = {k: payment.get(k, data.get(k)) for k in ENTITLEMENT_FIELDS if payment.get(k, data.get(k)) is not None}
    row = AdvAnnualAdsPayment(tx_hash=tx_hash, event=event[:100], buyer_reference=reference, buyer_user_id=buyer_id,
                              buyer_match=match, gross_amount=gross, platform_fee=fee, net_amount=net,
                              entitlement_snapshot={k: str(v)[:200] for k, v in snapshot.items()} or None,
                              journal_entry_id=journal_entry_id, sponsor_commission_status="PENDING_POLICY",
                              raw_payload_sha256=hashlib.sha256(raw or b"").hexdigest())
    db.add(row)
    db.flush()
    return row


class AnnualAdsRecognitionScheduler:
    """Daily recognition (Dr 2310 / Cr 4010) as a background task. A no-op unless ANNUALADS_ENABLED:
    with the integration disabled there is nothing to recognize and nothing runs."""

    def __init__(self, interval_seconds: int = 3600):
        import asyncio  # noqa: F401

        self.interval = interval_seconds
        self.running = False
        self._task = None

    async def start(self):
        import asyncio

        if self.running:
            return
        self.running = True
        self._task = asyncio.create_task(self._loop())

    async def stop(self):
        import asyncio

        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _loop(self):
        import asyncio

        await asyncio.sleep(60)
        while self.running:
            try:
                await self._run_pass()
            except Exception as exc:  # noqa: BLE001
                logger.error("Annual Ads recognition pass failed: %s", type(exc).__name__)
            await asyncio.sleep(self.interval)

    async def _run_pass(self):
        import asyncio

        from app.core.config import settings

        if not getattr(settings, "ANNUALADS_ENABLED", False):
            return
        from app.db.session import SessionLocal
        from app.scripts.annualads_daily_recognition import run_daily_recognition

        def _run():
            db = SessionLocal()
            try:
                return run_daily_recognition(db)
            finally:
                db.close()

        await asyncio.to_thread(_run)
