"""Legacy $100 Founding membership -> Referral Pool seat migration.

Evidence is IDs and payment records only (never names). Classes:
  AUTOMATIC_ELIGIBLE  provider-backed, validated, >= $100, not refunded, cash journal present
  MANUAL_REVIEW       admin-granted, missing provider evidence/cash journal, underpaid,
                      inactive user, or an extra (duplicate) Founding payment
  NOT_ELIGIBLE        not validated (pending/expired/failed/rejected) or refunded

Execution is only from a manifest whose SHA-256 was reviewed; it inserts pool seats
(entitlement_source=LEGACY_FOUNDING_MIGRATION, source_deposit_id=<original deposit>) and
never creates, alters or charges a payment.
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.accounting import ChartOfAccounts, JournalEntry, JournalLine
from app.models.affiliate import AffiliateCommission
from app.models.business_model import ReferralPoolMembership, ReferralPoolMigrationRun
from app.models.payment import Deposit, DepositStatus, ProductType
from app.models.user import User
from app.services import referral_pool_service as pool
from app.services.legacy_business_model import LEGACY_FOUNDING_PRODUCT_CODES

AUTOMATIC = "AUTOMATIC_ELIGIBLE"
MANUAL = "MANUAL_REVIEW"
NOT_ELIGIBLE = "NOT_ELIGIBLE"
REQUIRED_AMOUNT = Decimal("100.00")
_REFUND_MARKER = "Provider refund reconciled"


class MigrationAborted(RuntimeError):
    pass


@dataclass
class Candidate:
    deposit_id: int
    user_id: int
    product_code: str
    amount: str
    deposit_status: str
    classification: str
    reasons: list[str] = field(default_factory=list)
    external_payment_id_present: bool = False
    tx_hash_present: bool = False
    admin_granted: bool = False
    refunded: bool = False
    cash_journal_entry_id: Optional[int] = None


def _cash_journal_id(db: Session, deposit_id: int) -> Optional[int]:
    """Legacy journals reference deposits only in text: exact number match (5 never matches 51)."""
    pattern = re.compile(rf"Deposit #{int(deposit_id)}(?!\d)")
    rows = (
        db.query(JournalEntry.id, JournalEntry.description)
        .join(JournalLine, JournalLine.entry_id == JournalEntry.id)
        .join(ChartOfAccounts, ChartOfAccounts.id == JournalLine.account_id)
        .filter(ChartOfAccounts.account_code == "1001", JournalLine.debit_amount > 0)
        .filter(JournalEntry.description.like(f"%Deposit #{int(deposit_id)}%"))
        .all()
    )
    for entry_id, description in rows:
        if pattern.search(description or ""):
            return int(entry_id)
    return None


def classify(db: Session) -> list[Candidate]:
    rows = (
        db.query(Deposit, ProductType.code)
        .join(ProductType, ProductType.id == Deposit.product_type_id)
        .filter(ProductType.code.in_(sorted(LEGACY_FOUNDING_PRODUCT_CODES)))
        .order_by(Deposit.id.asc())
        .all()
    )
    out: list[Candidate] = []
    automatic_users: set[int] = set()
    for deposit, code in rows:
        status = deposit.status.value if hasattr(deposit.status, "value") else str(deposit.status)
        refunded = _REFUND_MARKER in str(deposit.admin_notes or "")
        admin_granted = str(deposit.order_id or "").startswith("ADMIN-") or deposit.validated_by is not None
        cand = Candidate(
            deposit_id=deposit.id, user_id=deposit.user_id, product_code=code, amount=str(deposit.amount),
            deposit_status=status, classification=NOT_ELIGIBLE,
            external_payment_id_present=bool((deposit.external_payment_id or "").strip()),
            tx_hash_present=bool((deposit.tx_hash or "").strip()),
            admin_granted=admin_granted, refunded=refunded,
        )
        if status != DepositStatus.VALIDATED.value:
            cand.reasons.append(f"DEPOSIT_{status.upper()}")
            out.append(cand)
            continue
        if refunded:
            cand.reasons.append("REFUNDED")
            out.append(cand)
            continue
        cand.cash_journal_entry_id = _cash_journal_id(db, deposit.id)
        user = db.query(User).filter(User.id == deposit.user_id).first()
        if admin_granted:
            cand.reasons.append("ADMIN_GRANTED_NO_PROVIDER_PAYMENT")
        if not (cand.external_payment_id_present or cand.tx_hash_present):
            cand.reasons.append("NO_PROVIDER_EVIDENCE")
        if Decimal(str(deposit.amount)) < REQUIRED_AMOUNT:
            cand.reasons.append("AMOUNT_BELOW_100")
        if cand.cash_journal_entry_id is None:
            cand.reasons.append("NO_CASH_JOURNAL")
        if user is None or user.is_deleted is True or user.is_active is False:
            cand.reasons.append("USER_MISSING_INACTIVE_OR_DELETED")
        if deposit.user_id in automatic_users:
            cand.reasons.append("DUPLICATE_EXTRA_FOUNDING_PAYMENT")
        cand.classification = MANUAL if cand.reasons else AUTOMATIC
        if cand.classification == AUTOMATIC:
            automatic_users.add(deposit.user_id)
        out.append(cand)
    return out


def build_manifest(db: Session) -> dict:
    candidates = classify(db)
    counts = {k: sum(1 for c in candidates if c.classification == k) for k in (AUTOMATIC, MANUAL, NOT_ELIGIBLE)}
    already = {
        int(m.source_deposit_id)
        for m in db.query(ReferralPoolMembership).filter(ReferralPoolMembership.source_deposit_id.isnot(None)).all()
    }
    to_insert = [c for c in candidates if c.classification == AUTOMATIC and c.deposit_id not in already]
    cfg = pool.get_config(db)
    seats = pool.seats_in_use(db)
    body = {
        "manifest_version": 1,
        "counts": counts,
        "total_users": db.query(func.count(User.id)).scalar(),
        "distinct_users_with_founding_deposits": len({c.user_id for c in candidates}),
        "duplicate_candidates": sorted({c.user_id for c in candidates if "DUPLICATE_EXTRA_FOUNDING_PAYMENT" in c.reasons}),
        "already_migrated_deposit_ids": sorted(already & {c.deposit_id for c in candidates}),
        "to_insert_deposit_ids": [c.deposit_id for c in to_insert],
        "capacity": int(cfg.capacity),
        "seats_in_use_before": seats,
        "would_exceed_capacity_by": max(0, seats + len(to_insert) - int(cfg.capacity)),
        "candidates": [asdict(c) for c in candidates],
    }
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return {"sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(), "manifest": body}


def reconciliation_snapshot(db: Session) -> dict:
    return {
        "users": db.query(func.count(User.id)).scalar(),
        "deposits": db.query(func.count(Deposit.id)).scalar(),
        "deposit_amount_sum": str(db.query(func.coalesce(func.sum(Deposit.amount), 0)).scalar()),
        "journal_entries": db.query(func.count(JournalEntry.id)).scalar(),
        "journal_lines": db.query(func.count(JournalLine.id)).scalar(),
        "affiliate_commissions": db.query(func.count(AffiliateCommission.id)).scalar(),
        "pool_memberships": db.query(func.count(ReferralPoolMembership.id)).scalar(),
        "pool_legacy_memberships": db.query(func.count(ReferralPoolMembership.id))
        .filter(ReferralPoolMembership.entitlement_source == pool.SOURCE_LEGACY).scalar(),
        "pool_seats_in_use": pool.seats_in_use(db),
    }


def execute(db: Session, *, expected_sha256: str, operator: str) -> dict:
    """Insert seats for AUTOMATIC_ELIGIBLE deposits of an approved manifest. Idempotent."""
    before = reconciliation_snapshot(db)
    built = build_manifest(db)
    if built["sha256"] != expected_sha256:
        raise MigrationAborted("Manifest changed since review (SHA-256 mismatch); re-run the dry run")
    manifest = built["manifest"]
    if manifest["would_exceed_capacity_by"] > 0:
        raise MigrationAborted("Migration would exceed Referral Pool capacity")
    run_id = f"legacy-founding-{uuid.uuid4().hex[:12]}"
    inserted = []
    by_deposit = {c["deposit_id"]: c for c in manifest["candidates"]}
    for deposit_id in manifest["to_insert_deposit_ids"]:
        row = pool.grant_legacy_seat(db, user_id=by_deposit[deposit_id]["user_id"], deposit_id=deposit_id, run_id=run_id)
        if row is not None:
            inserted.append(deposit_id)
    db.add(ReferralPoolMigrationRun(
        run_id=run_id, manifest_sha256=built["sha256"], operator=operator,
        automatic_eligible=manifest["counts"][AUTOMATIC], manual_review=manifest["counts"][MANUAL],
        not_eligible=manifest["counts"][NOT_ELIGIBLE], inserted=len(inserted),
        manifest_json=json.dumps(manifest, sort_keys=True),
    ))
    db.flush()
    after = reconciliation_snapshot(db)
    for key in ("users", "deposits", "deposit_amount_sum", "journal_entries", "journal_lines", "affiliate_commissions"):
        if before[key] != after[key]:
            raise MigrationAborted(f"Reconciliation failed: {key} changed ({before[key]} -> {after[key]})")
    if after["pool_memberships"] - before["pool_memberships"] != len(inserted):
        raise MigrationAborted("Reconciliation failed: unexpected pool membership delta")
    if after["pool_seats_in_use"] > manifest["capacity"]:
        raise MigrationAborted("Reconciliation failed: capacity exceeded")
    return {"run_id": run_id, "inserted_deposit_ids": inserted, "before": before, "after": after}
