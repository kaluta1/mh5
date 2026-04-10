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
# REMARQUE: Cette configuration est maintenue comme fallback si la règle n'est pas en BD
DEFAULT_COMMISSION_CONFIG = {
    # KYC Service (10$)
    "kyc": {
        "commission_type": CommissionType.KYC_PAYMENT,
        "direct_amount": Decimal("1.00"),    # Legacy values as fallback
        "indirect_amount": Decimal("0.10"),
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
    Utilise les règles définies en base de données (CommissionRule).
    
    Args:
        db: Session de base de données
        deposit: Le dépôt validé
        product_code: Code du produit (kyc, mfm_membership, annual_membership)
    
    Returns:
        Liste des commissions créées
    """
    commissions_created = []
    
    # 1. Chercher la règle de commission dynamique
    # Import local pour éviter les cycles
    from app.models.affiliate import CommissionRule
    
    rule = db.query(CommissionRule).filter(
        CommissionRule.product_code == product_code,
        CommissionRule.is_active == True
    ).first()
    
    # Configuration extraite de la règle ou fallback
    config = {}
    
    if rule:
        # Calcul dynamique basé sur des pourcentages
        # Le montant du dépôt est utilisé comme base
        deposit_amount = Decimal(str(deposit.amount))
        
        # Calculer les montants absolus à partir des pourcentages
        # rule.direct_percentage est en % (ex: 10.0 pour 10%)
        direct_amount = (deposit_amount * Decimal(str(rule.direct_percentage))) / Decimal("100.0")
        indirect_amount = (deposit_amount * Decimal(str(rule.indirect_percentage))) / Decimal("100.0")
        
        config = {
            "commission_type": rule.commission_type,
            "direct_amount": direct_amount,
            "indirect_amount": indirect_amount,
            "max_levels": rule.max_levels
        }
        logger.info(f"Using dynamic commission rule for {product_code}: {rule.direct_percentage}% / {rule.indirect_percentage}%")
        
    else:
        # Tenter le fallback legacy (si existant)
        legacy_config = DEFAULT_COMMISSION_CONFIG.get(product_code)
        if legacy_config:
            config = legacy_config
            logger.warning(f"Using legacy fallback commission config for: {product_code}")
        else:
            logger.warning(f"No commission rule found for product: {product_code}")
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
    
    max_levels = config["max_levels"]
    
    while current_sponsor_id and level <= max_levels:
        # Déterminer le montant de la commission
        if level == 1:
            commission_amount = config["direct_amount"]
        else:
            commission_amount = config["indirect_amount"]
        
        # Ignorer les montants nuls ou négatifs
        if commission_amount <= 0:
            break
        
        # Créer la commission
        try:
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
        except Exception as e:
            logger.error(f"Error creating commission object: {e}")
        
        # Trouver le parrain du parrain
        sponsor = db.query(User).filter(User.id == current_sponsor_id).first()
        current_sponsor_id = sponsor.sponsor_id if sponsor else None
        level += 1
    
    if commissions_created:
        try:
            db.commit()
            for c in commissions_created:
                db.refresh(c)
            logger.info(f"Created {len(commissions_created)} commissions for deposit {deposit.id}")
        except Exception as e:
            logger.error(f"Error saving commissions: {e}")
            db.rollback()
    
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
            elif product_code in ["mfm_membership", "efm_membership", "founding_membership"]:
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

        # Écritures comptables (plan comptable MyHigh5 — voir docs/MYHIGH5_CHART_OF_ACCOUNTS.md)
        from app.services.payment_accounting import payment_accounting

        if product_code == "kyc":
            # Step 1: cash to deferred2113. Step 2 posts when KYC is approved (Shufti webhook / status sync).
            payment_accounting.process_kyc_cash_receipt_accounting(db, deposit)
        elif product_code == "annual_membership":
            payment_accounting.process_membership_payment_accounting(db, deposit, commissions)
        elif product_code in ("mfm_membership", "efm_membership", "founding_membership"):
            payment_accounting.process_founding_membership_payment_accounting(db, deposit, commissions)

        return True

    except Exception as e:
        logger.error(f"Error processing payment validation: {e}")
        db.rollback()
        return False
