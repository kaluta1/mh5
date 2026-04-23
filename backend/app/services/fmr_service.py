"""
Founding Membership Points (FMP) and ratio (FMR) support for month-end Founding pool splits.

- +1 FMP: founding / MFM membership payment recognized (per deposit)
- +1 FMP: direct sponsor when referred user fully completes KYC (per verification)
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import List, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.affiliate import AffiliateTree
from app.models.fmr import MemberFmpBalance, MemberFmpLedger

FmpSourceType = str  # FOUNDING_JOIN | REFERRAL_VERIFIED

FOUNDING_JOIN = "FOUNDING_JOIN"
REFERRAL_VERIFIED = "REFERRAL_VERIFIED"

Q6 = Decimal("0.000001")


def _ledger_exists(
    db: Session, *, user_id: int, source_type: str, source_id: int
) -> bool:
    return (
        db.query(MemberFmpLedger.id)
        .filter(
            MemberFmpLedger.user_id == user_id,
            MemberFmpLedger.source_type == source_type,
            MemberFmpLedger.source_id == source_id,
        )
        .first()
        is not None
    )


def add_fmp(
    db: Session,
    user_id: int,
    points: Decimal,
    source_type: FmpSourceType,
    source_id: int,
) -> bool:
    """
    Idempotent: returns True if a new row was added and balance updated, False if duplicate source.
    Caller session must commit.
    """
    if points <= 0:
        raise ValueError("FMP points must be positive")
    if _ledger_exists(db, user_id=user_id, source_type=source_type, source_id=source_id):
        return False

    p = points.quantize(Q6, rounding=ROUND_HALF_UP)
    line = MemberFmpLedger(
        user_id=user_id,
        source_type=source_type,
        source_id=source_id,
        points=p,
    )
    db.add(line)
    db.flush()

    bal = db.query(MemberFmpBalance).filter(MemberFmpBalance.user_id == user_id).first()
    if not bal:
        bal = MemberFmpBalance(user_id=user_id, total_fmp=Decimal("0"))
        db.add(bal)
        db.flush()
    bal.total_fmp = (Decimal(str(bal.total_fmp or 0)) + p).quantize(Q6, rounding=ROUND_HALF_UP)
    return True


def record_founding_join_fmp(db: Session, user_id: int, deposit_id: int) -> bool:
    return add_fmp(
        db, user_id, Decimal("1"), FOUNDING_JOIN, int(deposit_id)
    )


def record_referral_kyc_fmp(
    db: Session, *, verified_user_id: int, kyc_verification_id: int
) -> bool:
    """
    Award +1 FMP to the direct sponsor (affiliate tree) when a referred user fully verifies KYC.
    """
    tree = (
        db.query(AffiliateTree)
        .filter(
            AffiliateTree.user_id == verified_user_id,
            AffiliateTree.is_active == True,  # noqa: E712
        )
        .first()
    )
    if not tree or not tree.sponsor_id:
        return False
    return add_fmp(
        db, int(tree.sponsor_id), Decimal("1"), REFERRAL_VERIFIED, int(kyc_verification_id)
    )


def get_user_total_fmp(db: Session, user_id: int) -> Decimal:
    row = (
        db.query(MemberFmpBalance.total_fmp)
        .filter(MemberFmpBalance.user_id == user_id)
        .first()
    )
    if not row or row[0] is None:
        return Decimal("0")
    return Decimal(str(row[0])).quantize(Q6, rounding=ROUND_HALF_UP)


def get_global_fmp_total(db: Session) -> Decimal:
    total = (
        db.query(func.coalesce(func.sum(MemberFmpBalance.total_fmp), 0))
        .select_from(MemberFmpBalance)
        .scalar()
    )
    return Decimal(str(total or 0)).quantize(Q6, rounding=ROUND_HALF_UP)


def fmp_weights_for_pool(db: Session) -> Tuple[List[int], dict[int, Decimal]]:
    """
    Weights for allocate: {user_id: FMP}. Empty dict if no one has FMP.
    """
    rows = (
        db.query(MemberFmpBalance)
        .filter(MemberFmpBalance.total_fmp > 0)
        .order_by(MemberFmpBalance.user_id.asc())
        .all()
    )
    if not rows:
        return [], {}
    weights = {int(r.user_id): Decimal(str(r.total_fmp or 0)).quantize(Q6, rounding=ROUND_HALF_UP) for r in rows}
    return sorted(weights.keys()), weights
