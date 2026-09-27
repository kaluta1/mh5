"""Child/Teen Safety Phase 10: the member's OWN prize/financial eligibility.

Read-only. Returns only status (ALLOWED / HOLD / REVIEW_REQUIRED) and a safe
next step per operation: no reason codes, DOB, age, guardian or KYC data.
Enforcement itself happens in each writer through app.services.financial_eligibility.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api import deps
from app.models.user import User
from app.services import financial_eligibility as fe

router = APIRouter()


@router.get("/me")
def my_financial_eligibility(
    operation: Optional[List[fe.FinancialOperation]] = Query(None),
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    ops = operation or [fe.FinancialOperation.PAYMENT, fe.FinancialOperation.WITHDRAWAL,
                        fe.FinancialOperation.KYC_INITIATION, fe.FinancialOperation.PRIZE_CLAIM]
    return {"items": fe.member_status(db, current_user, ops)}
