"""Fetch validated deposits for admin invoice export."""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app.models.payment import Deposit, DepositStatus, ProductType


def fetch_validated_deposits_for_export(
    db: Session,
    *,
    user_id: Optional[int] = None,
    search: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> list[Deposit]:
    """All successful (validated) deposits — source records for invoices."""
    from app.models.user import User

    q = (
        db.query(Deposit)
        .filter(Deposit.status == DepositStatus.VALIDATED)
        .options(
            joinedload(Deposit.user),
            joinedload(Deposit.product_type),
            joinedload(Deposit.payment_method),
        )
    )
    if user_id:
        q = q.filter(Deposit.user_id == user_id)
    if date_from:
        q = q.filter(
            func.coalesce(func.date(Deposit.validated_at), func.date(Deposit.created_at))
            >= date_from
        )
    if date_to:
        q = q.filter(
            func.coalesce(func.date(Deposit.validated_at), func.date(Deposit.created_at))
            <= date_to
        )
    if search:
        term = f"%{search.lower()}%"
        q = q.join(User).outerjoin(ProductType).filter(
            or_(
                func.lower(Deposit.order_id).like(term),
                func.lower(Deposit.external_payment_id).like(term),
                func.lower(Deposit.tx_hash).like(term),
                func.lower(User.email).like(term),
                func.lower(User.username).like(term),
                func.lower(User.full_name).like(term),
                func.lower(ProductType.name).like(term),
            )
        )
    return q.order_by(
        Deposit.validated_at.desc().nullslast(),
        Deposit.created_at.desc(),
    ).all()


def deposit_product_name(deposit: Deposit) -> str:
    if deposit.product_type and deposit.product_type.name:
        return deposit.product_type.name
    return "Service"
