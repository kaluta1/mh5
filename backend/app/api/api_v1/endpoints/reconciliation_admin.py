"""Prompt 6: read-only reconciliation (Annual Ads, Referral Pool, DSM) for administrators, the one
administrator-approved DSM sponsor restoration, and the member's own Annual Ads history."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user, get_db
from app.models.user import User

admin_router = APIRouter()
member_router = APIRouter()


def _finance_viewer(user: User) -> None:
    from app.api.api_v1.endpoints.soncopay import _require_payout_viewer

    _require_payout_viewer(user)


def _membership_admin(user: User) -> None:
    """DSM identity and sponsor data: a Super Admin or the explicit manage_administrators permission."""
    from app.services import admin_security, super_admin

    if not (super_admin.is_super_admin(user)
            or admin_security.has_permission(user, admin_security.PERMISSION_MANAGE_ADMINS)):
        raise HTTPException(status_code=403, detail={"code": "FORBIDDEN",
                                                     "message": "A Super Admin or manage_administrators is required."})


@admin_router.get("/annual-ads")
def annual_ads(db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    _finance_viewer(user)
    from app.services import annualads_commissions

    out = annualads_commissions.reconciliation(db)
    db.rollback()
    return out


@admin_router.get("/referral-pool")
def referral_pool(db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    _finance_viewer(user)
    from app.services import referral_pool_reconciliation

    out = referral_pool_reconciliation.report(db)
    db.rollback()
    return out


@admin_router.get("/dsm")
def dsm(db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    _membership_admin(user)
    from app.services import dsm_reconciliation

    out = dsm_reconciliation.report(db, sample=20)
    db.rollback()
    return out


@admin_router.get("/dsm/candidates")
def dsm_candidates(db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    _membership_admin(user)
    from app.services import dsm_reconciliation

    out = {"candidates": dsm_reconciliation.candidates(db)}
    db.rollback()
    return out


class RestoreBody(BaseModel):
    user_id: int = Field(gt=0)
    note: str = Field(min_length=5, max_length=300)
    current_password: str = Field(default="", max_length=256)


@admin_router.post("/dsm/restorations")
def dsm_restore(body: RestoreBody, db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    """One explicit, audited restoration of a DSM sponsor link (Super Admin + current password)."""
    from app.services import dsm_reconciliation, payment_config, super_admin

    if not super_admin.is_super_admin(user):
        raise HTTPException(status_code=403, detail={"code": "SUPER_ADMIN_REQUIRED",
                                                     "message": "Only a Super Admin can restore a sponsor link."})
    try:
        payment_config.require_reauth(user, body.current_password)
    except payment_config.PaymentConfigError as exc:
        raise HTTPException(status_code=403, detail={"code": exc.code, "message": str(exc)}) from None
    try:
        out = dsm_reconciliation.restore(db, user, user_id=body.user_id, note=body.note)
        db.commit()
    except dsm_reconciliation.DsmError as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status, detail={"code": exc.code, "message": exc.message}) from None
    return out


@member_router.get("/history")
def my_annual_ads(db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    """The member's own Annual Ads purchases (as identified buyer) and the commissions they earned as the
    buyer's direct sponsor. No other member's personal data."""
    from app.models.advertising_v2 import AdvAnnualAdsPayment
    from app.models.affiliate import AffiliateCommission
    from app.services import annualads_commissions as ac

    bought = (db.query(AdvAnnualAdsPayment).filter(AdvAnnualAdsPayment.buyer_user_id == user.id)
              .order_by(AdvAnnualAdsPayment.id.desc()).limit(100).all())
    earned = (db.query(AdvAnnualAdsPayment).filter(AdvAnnualAdsPayment.sponsor_user_id == user.id)
              .order_by(AdvAnnualAdsPayment.id.desc()).limit(100).all())
    commission = {c.source_id: c for c in db.query(AffiliateCommission).filter(
        AffiliateCommission.source_type == ac.SOURCE_TYPE, AffiliateCommission.user_id == user.id)}
    out = {
        "purchases": [{"id": p.id, "date": p.created_at.isoformat() if p.created_at else None,
                       "gross_amount": str(p.gross_amount), "payment_status": "CONFIRMED",
                       "refund_status": p.refund_status} for p in bought],
        "sponsor_commissions": [{"id": p.id, "date": p.created_at.isoformat() if p.created_at else None,
                                 "gross_amount": str(p.gross_amount),
                                 "rate_percent": str((p.sponsor_rate or 0) * 100) if p.sponsor_rate is not None else None,
                                 "amount": str(p.sponsor_commission_amount) if p.sponsor_commission_amount is not None else None,
                                 "status": p.sponsor_commission_status,
                                 "commission_status": commission[p.id].status.value if p.id in commission else None,
                                 "refund_status": p.refund_status} for p in earned],
    }
    db.rollback()
    return out
