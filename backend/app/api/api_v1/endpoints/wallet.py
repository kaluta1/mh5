"""
Wallet API Endpoints
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, case
from typing import List, Optional
from datetime import datetime, timedelta
from decimal import Decimal

from app.api import deps
from app.models.user import User
from app.models.affiliate import AffiliateCommission, CommissionStatus
from app.models.payment import Deposit, DepositStatus, ProductType

router = APIRouter()


@router.get("/balance")
def get_wallet_balance(
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    """
    Récupère le solde du portefeuille de l'utilisateur.
    Le solde est basé sur les commissions payées et en attente.
    """
    # Solde disponible (commissions payées ou approuvées)
    available_balance = db.query(
        func.coalesce(func.sum(AffiliateCommission.commission_amount), 0)
    ).filter(
        and_(
            AffiliateCommission.user_id == current_user.id,
            AffiliateCommission.status.in_([CommissionStatus.PAID, CommissionStatus.APPROVED])
        )
    ).scalar() or Decimal(0)
    
    # Solde en attente (commissions pending)
    pending_balance = db.query(
        func.coalesce(func.sum(AffiliateCommission.commission_amount), 0)
    ).filter(
        and_(
            AffiliateCommission.user_id == current_user.id,
            AffiliateCommission.status == CommissionStatus.PENDING
        )
    ).scalar() or Decimal(0)
    
    # Si pas encore de système de paiement, inclure aussi les pending dans le solde disponible
    # pour montrer les gains accumulés
    if available_balance == 0 and pending_balance > 0:
        available_balance = pending_balance
    
    # Total des gains (toutes les commissions non annulées)
    total_earnings = db.query(
        func.coalesce(func.sum(AffiliateCommission.commission_amount), 0)
    ).filter(
        and_(
            AffiliateCommission.user_id == current_user.id,
            AffiliateCommission.status != CommissionStatus.CANCELLED
        )
    ).scalar() or Decimal(0)
    
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
        "total_earnings": float(total_earnings),
        "this_month": float(this_month_earnings),
        "last_month": float(last_month_earnings),
        "growth_rate": round(float(growth_rate), 1)
    }


@router.get("/transactions")
def get_wallet_transactions(
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
    skip: int = 0,
    limit: int = 50,
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
        "FOUNDING_MEMBERSHIP_FEE": "KYC",
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
        l1_rows = (
            db.query(AffiliateCommission)
            .filter(
                AffiliateCommission.user_id == current_user.id,
                AffiliateCommission.level == 1,
            )
            .order_by(AffiliateCommission.transaction_date.desc())
            .all()
        )
        for c in l1_rows:
            source_user = db.query(User).filter(User.id == c.source_user_id).first()
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
        deposits = db.query(Deposit).filter(
            Deposit.user_id == current_user.id,
            Deposit.status.in_([DepositStatus.PENDING, DepositStatus.VALIDATED])
        ).order_by(Deposit.created_at.desc()).limit(limit // 2 if not transaction_type else limit).all()
        
        for d in deposits:
            # Récupérer le type de produit
            product = db.query(ProductType).filter(ProductType.id == d.product_type_id).first()
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
