"""
Wallet API Endpoints
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
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
    
    # Récupérer les commissions
    commissions_query = db.query(AffiliateCommission).filter(
        AffiliateCommission.user_id == current_user.id
    )
    
    if transaction_type == "commission":
        commissions = commissions_query.order_by(
            AffiliateCommission.transaction_date.desc()
        ).offset(skip).limit(limit).all()
    elif transaction_type in ["deposit", "withdrawal"]:
        commissions = []
    else:
        commissions = commissions_query.order_by(
            AffiliateCommission.transaction_date.desc()
        ).limit(limit // 2).all()
    
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
    
    for c in commissions:
        # Récupérer le nom de l'utilisateur source
        source_user = db.query(User).filter(User.id == c.source_user_id).first()
        source_name = source_user.full_name or source_user.username if source_user else "Utilisateur"
        
        # Type de commission pour l'affichage
        comm_type_value = c.commission_type.value if c.commission_type else None
        comm_type_label = commission_type_labels.get(comm_type_value, comm_type_value)
        
        # Description avec le type
        level_str = "direct" if c.level == 1 else f"N{c.level}"
        description = f"Commission {comm_type_label} ({level_str}) - {source_name}"
        
        # Mapping des statuts
        if c.status == CommissionStatus.PAID:
            status = "completed"
        elif c.status == CommissionStatus.APPROVED:
            status = "approved"
        elif c.status == CommissionStatus.PENDING:
            status = "pending"
        else:
            status = "failed"
        
        transactions.append({
            "id": f"comm_{c.id}",
            "type": "credit",
            "category": "commission",
            "amount": float(c.commission_amount) if c.commission_amount else 0,
            "description": description,
            "date": c.transaction_date.isoformat() if c.transaction_date else None,
            "status": status,
            "commission_type": comm_type_value,
            "commission_type_label": comm_type_label,
            "level": c.level,
            "source_user": source_name
        })
    
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
