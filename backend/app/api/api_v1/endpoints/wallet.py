"""
Wallet API Endpoints
"""
from decimal import Decimal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, and_, case
from typing import List, Optional
from datetime import datetime, timedelta

from app.api import deps
from app.models.user import User
from app.models.affiliate import AffiliateCommission, CommissionStatus
from app.models.payment import Deposit, DepositStatus, ProductType
from app.schemas.wallet import (
    CashoutCancel,
    CashoutMethodUpdate,
    PayoutWalletConfirm,
    UsdCashoutRequest,
    WithdrawPreviewResponse,
    WithdrawRequest,
    WithdrawResponse,
)

router = APIRouter()


@router.get("/balance")
def get_wallet_balance(
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    """
    Récupère le solde du portefeuille de l'utilisateur.
    Available = unreserved APPROVED commissions; paid rows are historical payouts.
    """
    from app.services.financial_balances import get_commission_balance

    balance = get_commission_balance(db, current_user.id)
    available_balance = balance.available
    pending_balance = balance.pending
    
    # Total des gains (toutes les commissions non annulées)
    total_earnings = balance.earned_lifetime
    
    # Gains ce mois-ci
    now = datetime.utcnow()
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    this_month_earnings = db.query(
        func.coalesce(func.sum(AffiliateCommission.commission_amount), 0)
    ).filter(
        and_(
            AffiliateCommission.user_id == current_user.id,
            AffiliateCommission.status != CommissionStatus.CANCELLED,
            AffiliateCommission.transaction_date >= start_of_month
        )
    ).scalar() or Decimal(0)
    
    # Gains le mois dernier
    start_of_last_month = (start_of_month - timedelta(days=1)).replace(day=1)
    
    last_month_earnings = db.query(
        func.coalesce(func.sum(AffiliateCommission.commission_amount), 0)
    ).filter(
        and_(
            AffiliateCommission.user_id == current_user.id,
            AffiliateCommission.status != CommissionStatus.CANCELLED,
            AffiliateCommission.transaction_date >= start_of_last_month,
            AffiliateCommission.transaction_date < start_of_month
        )
    ).scalar() or Decimal(0)
    
    # Calcul du taux de croissance
    if last_month_earnings > 0:
        growth_rate = ((this_month_earnings - last_month_earnings) / last_month_earnings) * 100
    else:
        growth_rate = 100.0 if this_month_earnings > 0 else 0.0
    
    return {
        "available_balance": float(available_balance),
        "pending_balance": float(pending_balance),
        "reserved_balance": float(balance.reserved),
        "total_earnings": float(total_earnings),
        "this_month": float(this_month_earnings),
        "last_month": float(last_month_earnings),
        "growth_rate": round(float(growth_rate), 1)
    }


@router.get("/transactions")
def get_wallet_transactions(
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    transaction_type: Optional[str] = None  # commission, deposit, withdrawal
):
    """
    Récupère l'historique des transactions du portefeuille.
    Combine les commissions et les dépôts.
    """
    transactions = []

    # Mapping des types de commission pour l'affichage
    commission_type_labels = {
        "KYC_PAYMENT": "KYC",
        "FOUNDING_MEMBERSHIP_FEE": "MFM Joining Fee",
        "ANNUAL_MEMBERSHIP_FEE": "Cotisation FM",
        "EFM_MEMBERSHIP": "EFM",
        "CLUB_MEMBERSHIP": "Club",
        "CONTEST_PARTICIPATION": "Concours",
        "SHOP_PURCHASE": "Boutique",
        "AD_REVENUE": "Pub",
        "MONTHLY_REVENUE_POOL": "Pool Mensuel",
        "ANNUAL_PROFIT_POOL": "Pool Annuel"
    }
    
    def build_commission_transactions() -> List[dict]:
        """
        Level 1: one row per commission with referral username visible.
        Levels 2–10: aggregated per (level, commission_type) — no indirect referral identities.
        """
        out: List[dict] = []

        # --- Level 1: detail rows (direct referrals)
        direct_limit = limit if transaction_type == "commission" else max(1, limit // 2)
        direct_skip = skip if transaction_type == "commission" else 0
        l1_rows = (
            db.query(AffiliateCommission)
            .options(joinedload(AffiliateCommission.source_user))
            .filter(
                AffiliateCommission.user_id == current_user.id,
                AffiliateCommission.level == 1,
            )
            .order_by(AffiliateCommission.transaction_date.desc())
            .offset(direct_skip)
            .limit(direct_limit)
            .all()
        )
        for c in l1_rows:
            source_user = c.source_user
            referral_username = (
                (source_user.username or source_user.full_name or "User").strip()
                if source_user
                else "User"
            )
            comm_type_value = c.commission_type.value if c.commission_type else None
            comm_type_label = commission_type_labels.get(comm_type_value, comm_type_value)
            description = f"{comm_type_label} · Level 1 · {referral_username}"

            if c.status == CommissionStatus.PAID:
                status = "completed"
            elif c.status == CommissionStatus.APPROVED:
                status = "approved"
            elif c.status == CommissionStatus.PENDING:
                status = "pending"
            else:
                status = "failed"

            out.append(
                {
                    "id": f"comm_{c.id}",
                    "type": "credit",
                    "category": "commission",
                    "amount": float(c.commission_amount) if c.commission_amount else 0,
                    "description": description,
                    "date": c.transaction_date.isoformat() if c.transaction_date else None,
                    "status": status,
                    "commission_type": comm_type_value,
                    "commission_type_label": comm_type_label,
                    "level": 1,
                    "source_user": referral_username,
                    "aggregate": False,
                    "payout_reference": c.payout_reference,
                }
            )

        # --- Levels 2–10: totals only (privacy)
        agg_rows = (
            db.query(
                AffiliateCommission.level,
                AffiliateCommission.commission_type,
                func.sum(AffiliateCommission.commission_amount).label("total_amt"),
                func.max(AffiliateCommission.transaction_date).label("last_dt"),
                func.max(
                    case(
                        (AffiliateCommission.status == CommissionStatus.PENDING, 1),
                        else_=0,
                    )
                ).label("has_pending"),
            )
            .filter(
                AffiliateCommission.user_id == current_user.id,
                AffiliateCommission.level >= 2,
                AffiliateCommission.level <= 10,
            )
            .group_by(AffiliateCommission.level, AffiliateCommission.commission_type)
            .all()
        )
        for row in agg_rows:
            level = row.level
            ct_enum = row.commission_type
            total_amt = row.total_amt or Decimal(0)
            last_dt = row.last_dt
            has_pending = bool(row.has_pending)
            comm_type_value = ct_enum.value if ct_enum else None
            comm_type_label = commission_type_labels.get(comm_type_value, comm_type_value)
            description = f"Level {level} · {comm_type_label} · Total (indirect)"

            safe_ct = comm_type_value or "NONE"
            out.append(
                {
                    "id": f"agg_comm_{level}_{safe_ct}",
                    "type": "credit",
                    "category": "commission",
                    "amount": float(total_amt),
                    "description": description,
                    "date": last_dt.isoformat() if last_dt else None,
                    "status": "pending" if has_pending else "completed",
                    "commission_type": comm_type_value,
                    "commission_type_label": comm_type_label,
                    "level": level,
                    "source_user": None,
                    "aggregate": True,
                }
            )

        out.sort(key=lambda x: x["date"] or "", reverse=True)
        return out

    if transaction_type not in ("deposit", "withdrawal"):
        commission_items = build_commission_transactions()
        if transaction_type == "commission":
            transactions.extend(commission_items[skip : skip + limit])
        else:
            half = max(1, limit // 2)
            transactions.extend(commission_items[:half])
    
    # Récupérer les dépôts (uniquement en attente et validés)
    if transaction_type in [None, "deposit"]:
        deposit_limit = limit if transaction_type == "deposit" else max(1, limit // 2)
        deposit_skip = skip if transaction_type == "deposit" else 0
        deposits = db.query(Deposit).options(joinedload(Deposit.product_type)).filter(
            Deposit.user_id == current_user.id,
            Deposit.status.in_([DepositStatus.PENDING, DepositStatus.VALIDATED])
        ).order_by(Deposit.created_at.desc()).offset(deposit_skip).limit(deposit_limit).all()
        
        for d in deposits:
            # Récupérer le type de produit
            product = d.product_type
            product_name = product.name if product else "Produit"
            
            # Mapping des statuts de dépôt (seuls PENDING et VALIDATED sont affichés)
            deposit_status = "completed" if d.status == DepositStatus.VALIDATED else "pending"
            
            transactions.append({
                "id": f"dep_{d.id}",
                "type": "debit",
                "category": "deposit",
                "amount": float(d.amount) if d.amount else 0,
                "description": f"Achat - {product_name}",
                "date": d.created_at.isoformat() if d.created_at else None,
                "status": deposit_status,
                "product_code": product.code if product else None,
                "deposit_id": d.id,
                "external_payment_id": d.external_payment_id
            })
    
    # Trier par date décroissante
    transactions.sort(key=lambda x: x["date"] or "", reverse=True)
    
    return transactions[:limit]


@router.get("/stats")
def get_wallet_stats(
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    """
    Récupère les statistiques du portefeuille.
    """
    # Nombre de commissions
    total_commissions = db.query(func.count(AffiliateCommission.id)).filter(
        AffiliateCommission.user_id == current_user.id
    ).scalar() or 0
    
    # Nombre de dépôts
    total_deposits = db.query(func.count(Deposit.id)).filter(
        Deposit.user_id == current_user.id
    ).scalar() or 0
    
    # Montant total des dépôts validés
    total_deposit_amount = db.query(
        func.coalesce(func.sum(Deposit.amount), 0)
    ).filter(
        and_(
            Deposit.user_id == current_user.id,
            Deposit.status == DepositStatus.VALIDATED
        )
    ).scalar() or Decimal(0)
    
    return {
        "total_commissions_count": total_commissions,
        "total_deposits_count": total_deposits,
        "total_deposit_amount": float(total_deposit_amount)
    }


@router.get("/withdraw/preview", response_model=WithdrawPreviewResponse)
def preview_withdrawal(
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Preview a USD Cashout: the whole available balance, the existing fee and the net."""
    from app.services import cashout_service

    data = cashout_service.summary(db, current_user)
    usd = data["fees"]["USD"]
    return WithdrawPreviewResponse(
        available_to_withdraw=data["payable_amount"],
        minimum_withdrawal=data["minimums"]["USD"],
        fee=usd["fee"] or 0.0,
        net_amount=usd["net_amount"] or 0.0,
        # USD Cashout needs no crypto wallet; kept true so older clients do not block on it.
        wallet_configured=True,
        payout_currency="usd",
        eligibility_status=data["eligibility_status"],
        eligibility_next_step=data["eligibility_next_step"],
        cashout_method=data["cashout_method"],
    )


def _cashout_http_error(exc) -> HTTPException:
    unprocessable = status.HTTP_422_UNPROCESSABLE_ENTITY
    codes = {"FORBIDDEN": status.HTTP_403_FORBIDDEN, "INVALID_METHOD": unprocessable,
             "INVALID_OUTCOME": unprocessable, "REFERENCE_REQUIRED": unprocessable,
             "DESTINATION_REQUIRED": unprocessable, "DESTINATION_TOO_LONG": unprocessable,
             "LINK_INVALID": status.HTTP_400_BAD_REQUEST}
    return HTTPException(status_code=codes.get(exc.code, status.HTTP_409_CONFLICT),
                         detail={"code": exc.code, "message": str(exc)})


def _request_usd(db: Session, user: User, amount, idempotency_key: Optional[str],
                 destination: Optional[str] = None):
    from app.services import cashout_service
    from app.services.financial_eligibility import FinancialEligibilityHold, http_error

    try:
        return cashout_service.request_usd_cashout(db, user, idempotency_key=idempotency_key, amount=amount,
                                                   destination=destination)
    except FinancialEligibilityHold as exc:
        # Phase 10: generic member-facing body; balances and commissions untouched.
        raise http_error(exc) from None
    except cashout_service.CashoutError as exc:
        raise _cashout_http_error(exc) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/withdraw", response_model=WithdrawResponse)
def request_withdrawal(
    body: WithdrawRequest,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
):
    """
    USD Cashout request (kept at its original address). The minimum and the
    fee are the configured ones (Admin > Finance & Payments). The request is
    reserved and tracked; no payout provider is called.
    """
    cashout = _request_usd(db, current_user, body.amount, idempotency_key)
    return WithdrawResponse(gross_amount=float(cashout.gross_amount), fee=float(cashout.fee),
                            net_amount=float(cashout.net_amount), payout_reference=None,
                            commissions_marked_paid=0, status=cashout.status)


# ---------------------------------------------------------------------------
# Dual cashout: member preference, summary, history
# ---------------------------------------------------------------------------

@router.get("/cashout")
def get_cashout_summary(db: Session = Depends(deps.get_db),
                        current_user: User = Depends(deps.get_current_active_user)):
    """Balances by state, the chosen method, its minimum and fees, the
    destination and the member's own cashout status."""
    from app.services import cashout_service

    return cashout_service.summary(db, current_user)


@router.put("/cashout/method")
def set_cashout_method(body: CashoutMethodUpdate, db: Session = Depends(deps.get_db),
                       current_user: User = Depends(deps.get_current_active_user)):
    """Choose Crypto Cashout or USD Cashout. Moves no money and starts no payout."""
    from app.services import cashout_service

    try:
        cashout_service.set_cashout_method(db, current_user, body.method)
    except cashout_service.CashoutError as exc:
        db.rollback()
        raise _cashout_http_error(exc) from exc
    db.refresh(current_user)
    return cashout_service.summary(db, current_user)


@router.get("/cashout/history")
def get_cashout_history(limit: int = Query(50, ge=1, le=100), db: Session = Depends(deps.get_db),
                        current_user: User = Depends(deps.get_current_active_user)):
    from app.services import cashout_service

    return cashout_service.history(db, current_user.id, limit=limit)


@router.post("/cashout/usd")
def request_usd_cashout(body: UsdCashoutRequest, db: Session = Depends(deps.get_db),
                        current_user: User = Depends(deps.get_current_active_user),
                        idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key")):
    """Ask for a USD Cashout of the whole available balance."""
    from app.services import cashout_service

    return cashout_service.cashout_dict(
        _request_usd(db, current_user, body.amount, idempotency_key, body.destination))


@router.post("/payout-wallet/confirm")
def confirm_payout_wallet(body: PayoutWalletConfirm, request: Request, db: Session = Depends(deps.get_db),
                          current_user: User = Depends(deps.get_current_active_user)):
    """Confirm a payout wallet change with the one-time link sent by email.
    The link works once, for the signed-in account it was issued to, and only
    for the exact wallet and network it names. The security hold starts now."""
    from app.core.client_ip import client_ip
    from app.services import cashout_service

    try:
        state = cashout_service.confirm_payout_wallet(db, current_user, body.token, ip=client_ip(request))
    except cashout_service.CashoutError as exc:
        db.rollback()
        raise _cashout_http_error(exc) from None
    return {"wallet": cashout_service.mask_address(state.address), "wallet_status": state.status,
            "payout_currency": state.currency, "network": cashout_service.network_label(state.currency),
            "payable_from": state.payable_from.isoformat() if state.payable_from else None}


@router.post("/cashout/{cashout_id}/cancel")
def cancel_own_cashout(cashout_id: int, body: CashoutCancel, db: Session = Depends(deps.get_db),
                       current_user: User = Depends(deps.get_current_active_user)):
    """Cancel the member's own request while nothing has been sent."""
    from app.models.affiliate import AffiliateCashoutRequest
    from app.services import cashout_service

    cashout = (db.query(AffiliateCashoutRequest)
               .filter(AffiliateCashoutRequest.id == cashout_id,
                       AffiliateCashoutRequest.user_id == current_user.id).first())
    if cashout is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cashout not found")
    try:
        return cashout_service.cashout_dict(
            cashout_service.cancel_request(db, cashout, actor=current_user, reason=body.reason))
    except cashout_service.CashoutError as exc:
        raise _cashout_http_error(exc) from exc
