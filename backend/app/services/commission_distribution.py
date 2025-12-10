"""
Service de distribution des commissions d'affiliation.

Règles de commission (MyHigh5 Founding Members):
- Founding Membership Fee (100$): 20$ direct, 2$ indirect (N2-10)
- Annual Membership Fee (50$): 10$ direct, 1$ indirect (N2-10)
- KYC (10$): 2$ direct, 0.2$ indirect (N2-10)
"""

from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
from decimal import Decimal
import logging

from app.models.user import User
from app.models.affiliate import AffiliateCommission, CommissionType, CommissionStatus
from app.models.payment import Deposit, ProductType
from app.services.email import email_service

logger = logging.getLogger(__name__)


# Configuration des commissions par type de produit
COMMISSION_CONFIG = {
    # KYC Service (10$)
    "kyc": {
        "commission_type": CommissionType.KYC_PAYMENT,
        "direct_amount": Decimal("2.00"),      # 2$ pour le parrain direct
        "indirect_amount": Decimal("0.20"),    # 0.20$ pour N2-10
        "max_levels": 10
    },
    # MFM / Founding Membership (100$)
    "mfm_membership": {
        "commission_type": CommissionType.FOUNDING_MEMBERSHIP_FEE,
        "direct_amount": Decimal("20.00"),     # 20$ pour le parrain direct
        "indirect_amount": Decimal("2.00"),    # 2$ pour N2-10
        "max_levels": 10
    },
    # Annual Membership (50$)
    "annual_membership": {
        "commission_type": CommissionType.ANNUAL_MEMBERSHIP_FEE,
        "direct_amount": Decimal("10.00"),     # 10$ pour le parrain direct
        "indirect_amount": Decimal("1.00"),    # 1$ pour N2-10
        "max_levels": 10
    },
    # EFM Membership (legacy, same as MFM)
    "efm_membership": {
        "commission_type": CommissionType.EFM_MEMBERSHIP,
        "direct_amount": Decimal("20.00"),
        "indirect_amount": Decimal("2.00"),
        "max_levels": 10
    }
}


def distribute_commissions(
    db: Session,
    deposit: Deposit,
    product_code: str
) -> List[AffiliateCommission]:
    """
    Distribue les commissions d'affiliation pour un dépôt validé.
    
    Args:
        db: Session de base de données
        deposit: Le dépôt validé
        product_code: Code du produit (kyc, mfm_membership, annual_membership)
    
    Returns:
        Liste des commissions créées
    """
    commissions_created = []
    
    # Vérifier la configuration du produit
    config = COMMISSION_CONFIG.get(product_code)
    if not config:
        logger.warning(f"No commission config for product: {product_code}")
        return commissions_created
    
    # Trouver l'utilisateur qui a payé
    source_user = db.query(User).filter(User.id == deposit.user_id).first()
    if not source_user:
        logger.warning(f"Source user not found: {deposit.user_id}")
        return commissions_created
    
    if not source_user.sponsor_id:
        logger.info(f"User {deposit.user_id} has no sponsor, no commissions to distribute")
        return commissions_created
    
    # Remonter l'arbre des parrains
    current_sponsor_id = source_user.sponsor_id
    level = 1
    
    while current_sponsor_id and level <= config["max_levels"]:
        # Déterminer le montant de la commission
        if level == 1:
            commission_amount = config["direct_amount"]
        else:
            commission_amount = config["indirect_amount"]
        
        if commission_amount <= 0:
            break
        
        # Créer la commission
        commission = AffiliateCommission(
            user_id=current_sponsor_id,
            source_user_id=deposit.user_id,
            product_type_id=deposit.product_type_id,
            deposit_id=deposit.id,
            commission_type=config["commission_type"],
            level=level,
            base_amount=float(deposit.amount),
            commission_amount=float(commission_amount),
            status=CommissionStatus.APPROVED,
            transaction_date=datetime.utcnow()
        )
        
        db.add(commission)
        commissions_created.append(commission)
        
        logger.info(
            f"Commission created: user={current_sponsor_id}, "
            f"level={level}, amount={commission_amount}, "
            f"type={config['commission_type'].value}"
        )
        
        # Trouver le parrain du parrain
        sponsor = db.query(User).filter(User.id == current_sponsor_id).first()
        current_sponsor_id = sponsor.sponsor_id if sponsor else None
        level += 1
    
    if commissions_created:
        db.commit()
        for c in commissions_created:
            db.refresh(c)
        logger.info(f"Created {len(commissions_created)} commissions for deposit {deposit.id}")
    
    return commissions_created


def process_payment_validation(db: Session, deposit: Deposit) -> bool:
    """
    Traite la validation d'un paiement.
    - Met à jour le statut du dépôt
    - Distribue les commissions
    - Active les services associés (KYC, Membership, etc.)
    
    Returns:
        True si le traitement a réussi
    """
    try:
        # Récupérer le type de produit
        product_type = db.query(ProductType).filter(
            ProductType.id == deposit.product_type_id
        ).first()
        
        if not product_type:
            logger.warning(f"Product type not found for deposit {deposit.id}")
            return False
        
        product_code = product_type.code
        
        # Distribuer les commissions
        commissions = distribute_commissions(db, deposit, product_code)
        
        # Activer le service pour l'utilisateur
        user = db.query(User).filter(User.id == deposit.user_id).first()
        if user:
            if product_code == "kyc":
                # KYC sera traité séparément après vérification
                logger.info(f"KYC payment validated for user {user.id}")
            elif product_code in ["mfm_membership", "efm_membership"]:
                # Activer le statut Founding Member
                user.is_founding_member = True
                user.founding_member_since = datetime.utcnow()
                logger.info(f"Founding membership activated for user {user.id}")
            elif product_code == "annual_membership":
                # Renouveler le statut Founding Member
                if user.is_founding_member:
                    user.founding_member_expires = datetime.utcnow().replace(
                        year=datetime.utcnow().year + 1
                    )
                    logger.info(f"Annual membership renewed for user {user.id}")
            
            db.commit()
            
            # Envoyer l'email de confirmation de paiement
            try:
                user_lang = getattr(user, 'preferred_language', 'fr') or 'fr'
                email_service.send_payment_confirmation_email(
                    to_email=user.email,
                    amount=f"${float(deposit.amount):.2f}",
                    product=product_type.name,
                    reference=str(deposit.external_payment_id or deposit.id),
                    date=datetime.utcnow().strftime('%d/%m/%Y'),
                    lang=user_lang
                )
                logger.info(f"Payment confirmation email sent to {user.email}")
            except Exception as e:
                logger.error(f"Failed to send payment confirmation email: {e}")
        
        return True
        
    except Exception as e:
        logger.error(f"Error processing payment validation: {e}")
        db.rollback()
        return False
