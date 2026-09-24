"""Client-confirmed NEW_V2 commission policies (data only, no schema change).

Shafi Abeid confirmed on 2026-09-25:
- a paid $100 Referral Pool entry pays the DIRECT sponsor 20% and is Leaders-eligible revenue;
- KYC / other products: commission base is the full price (provider cost is code-side, see
  new_model_revenue.COMMISSION_BASE_DEFINITION); only the policy notes change here;
- marketplace: 20% of the markup (unchanged values, notes only).

Only the NEW_V2 revenue_policies configuration rows are touched, with an audit_trails row
per change. Policies apply to future recognitions only; no historical row is recalculated.

Revision ID: x7y8z9a0b1c2
Revises: w6x7y8z9a0b1
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from alembic import op
from sqlalchemy.orm import Session

revision = "x7y8z9a0b1c2"
down_revision = "w6x7y8z9a0b1"
branch_labels = None
depends_on = None

_PROVISIONAL_POOL = dict(
    commission_eligible=False,
    commission_rate=Decimal("0"),
    leaders_revenue_eligible=False,
    notes=(
        "PROVISIONAL (client decision pending): the $100 pool entry is booked as revenue but does not "
        "generate direct commission and is excluded from the Leaders revenue base until confirmed."
    ),
)
_PROVISIONAL_NOTES = {
    "kyc": "PROVISIONAL: website revenue = gross - KYC provider cost (20%), recognized when verification is performed.",
    "kyc_verification": "PROVISIONAL: website revenue = gross - KYC provider cost (20%), recognized when verification is performed.",
    "marketplace_markup": (
        "Website revenue = the 20% markup only; the seller base is never MyHigh5 revenue. "
        "Direct commission = 20% of the markup (interpretation A)."
    ),
}


def _snapshot(p) -> dict:
    return {"commission_eligible": p.commission_eligible, "commission_rate": str(p.commission_rate),
            "leaders_revenue_eligible": p.leaders_revenue_eligible, "notes": p.notes}


def _apply(targets: dict, action: str) -> None:
    from app.models.accounting import AuditTrail
    from app.models.business_model import RevenuePolicy
    from app.services.new_model_reference_data import NEW_MODEL_VERSION

    db = Session(bind=op.get_bind())
    for code, values in targets.items():
        policy = db.query(RevenuePolicy).filter(
            RevenuePolicy.model_version == NEW_MODEL_VERSION, RevenuePolicy.product_code == code
        ).first()
        if policy is None:
            continue
        old = _snapshot(policy)
        for k, v in values.items():
            setattr(policy, k, v)
        db.flush()
        new = _snapshot(policy)
        if old != new:
            db.add(AuditTrail(table_name="revenue_policies", record_id=policy.id, action=action, old_values=old,
                              new_values=dict(new, reason="Client-confirmed commission policy 2026-09-25 (x7y8z9a0b1c2)"),
                              timestamp=datetime.utcnow(), created_at=datetime.utcnow()))
    db.flush()


def upgrade() -> None:
    from app.services.new_model_reference_data import (
        MARKETPLACE_PRODUCT_CODE,
        NEW_MODEL_REVENUE_POLICIES,
        REFERRAL_POOL_PRODUCT_CODE,
    )

    pool = NEW_MODEL_REVENUE_POLICIES[REFERRAL_POOL_PRODUCT_CODE]
    targets = {
        REFERRAL_POOL_PRODUCT_CODE: {k: pool[k] for k in ("commission_eligible", "commission_rate",
                                                          "leaders_revenue_eligible", "notes")},
        "kyc": {"notes": NEW_MODEL_REVENUE_POLICIES["kyc"]["notes"]},
        "kyc_verification": {"notes": NEW_MODEL_REVENUE_POLICIES["kyc_verification"]["notes"]},
        MARKETPLACE_PRODUCT_CODE: {"notes": NEW_MODEL_REVENUE_POLICIES[MARKETPLACE_PRODUCT_CODE]["notes"]},
    }
    _apply(targets, "POLICY_CONFIRMED")


def downgrade() -> None:
    targets = {"referral_pool_entry": dict(_PROVISIONAL_POOL)}
    targets.update({code: {"notes": notes} for code, notes in _PROVISIONAL_NOTES.items()})
    _apply(targets, "POLICY_CONFIRMED_ROLLBACK")
