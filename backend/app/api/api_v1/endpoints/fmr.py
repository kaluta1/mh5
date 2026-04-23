"""Founding Membership Points (FMP) / ratio (FMR) for the current user."""

from decimal import Decimal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api import deps
from app.models.user import User
from app.services import fmr_service

router = APIRouter()


class FmpMeResponse(BaseModel):
    user_fmp: Decimal = Field(description="Total FMP for the logged-in member")
    global_fmp: Decimal = Field(description="Sum of all members' FMP (denominator for FMR)")
    fmr: Decimal = Field(
        description="Founding Membership Ratio = user_fmp / global_fmp (0 if global is 0)"
    )


@router.get("/fmp/me", response_model=FmpMeResponse)
def get_my_fmp(
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    Returns this member's total FMP, global FMP, and FMR (share of the global FMP pool).
    Used for Founding pool revenue allocation weights.
    """
    user_fmp = fmr_service.get_user_total_fmp(db, current_user.id)
    global_fmp = fmr_service.get_global_fmp_total(db)
    if global_fmp <= 0:
        fmr = Decimal("0")
    else:
        fmr = (user_fmp / global_fmp).quantize(Decimal("0.000000000001"))
    return FmpMeResponse(user_fmp=user_fmp, global_fmp=global_fmp, fmr=fmr)
