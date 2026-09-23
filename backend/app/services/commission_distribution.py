"""
Service de distribution des commissions d'affiliation.

Règles de commission (MyHigh5 — init_commission_rules.py):
- KYC, MFM, annual, EFM: L1 10%, L2–L10 1% each (max 10 levels)
- Commission accrual commits independently of any external payout side effect
"""

from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timedelta
from decimal import Decimal
import logging

from app.models.user import User
from app.models.affiliate import AffiliateCommission, CommissionType, CommissionStatus
from app.models.payment import Deposit, ProductType
from app.services.email import email_service
from app.services.affiliate_hierarchy import MAX_AFFILIATE_LEVELS
from app.services.financial_integrity import money
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
    product_code: str,
    *,
    commit: bool = True,
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

    # The 10-level engine is retired for all future activity. Existing rows are
    # left untouched; the direct-only model replaces this writer.
    from app.services.legacy_business_model import legacy_business_model_enabled

    if not legacy_business_model_enabled():
        logger.info(
            "Legacy 10-level commission engine retired; no commissions created for deposit %s",
            deposit.id,
        )
        return commissions_created

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

    if deposit.id:
        existing = (
            db.query(AffiliateCommission)
            .filter(AffiliateCommission.deposit_id == deposit.id)
            .all()
        )
        if existing:
            logger.info(
                "Commissions already exist for deposit %s (%s row(s)); skipping distribution",
                deposit.id,
                len(existing),
            )
            return existing
    
    # Remonter l'arbre des parrains
    current_sponsor_id = source_user.sponsor_id
    level = 1
    visited_sponsor_ids: set[int] = {int(deposit.user_id)}
    
    max_levels = min(max(int(config["max_levels"] or 0), 0), MAX_AFFILIATE_LEVELS)
    
    while current_sponsor_id and level <= max_levels:
        if current_sponsor_id in visited_sponsor_ids:
            logger.warning(
                "Sponsor cycle detected at user %s for deposit %s; stopping at level %s",
                current_sponsor_id,
                deposit.id,
                level,
            )
            break
        visited_sponsor_ids.add(current_sponsor_id)
        # Déterminer le montant de la commission
        if level == 1:
            commission_amount = config["direct_amount"]
        else:
            commission_amount = config["indirect_amount"]
        
        # Ignorer les montants nuls ou négatifs
        if commission_amount <= 0:
            break

        sponsor = db.query(User).filter(User.id == current_sponsor_id).first()
        if not sponsor:
            break

        if sponsor.is_active is False or sponsor.is_deleted is True:
            logger.warning(
                "Ineligible sponsor %s skipped for deposit %s at level %s",
                sponsor.id,
                deposit.id,
                level,
            )
            current_sponsor_id = sponsor.sponsor_id
            level += 1
            continue

        if deposit.id:
            duplicate = (
                db.query(AffiliateCommission)
                .filter(
                    AffiliateCommission.deposit_id == deposit.id,
                    AffiliateCommission.user_id == current_sponsor_id,
                )
                .first()
            )
            if duplicate:
                logger.warning(
                    "Duplicate commission skipped for deposit %s beneficiary %s at level %s",
                    deposit.id,
                    current_sponsor_id,
                    level,
                )
                current_sponsor_id = sponsor.sponsor_id
                level += 1
                continue

        # No wallet → PENDING until user adds one; has wallet → APPROVED then auto-payout
        initial_status = (
            CommissionStatus.APPROVED
            if (sponsor.usdt_wallet_address or "").strip()
            else CommissionStatus.PENDING
        )

        # Créer la commission
        commission = AffiliateCommission(
            user_id=current_sponsor_id,
            source_user_id=deposit.user_id,
            product_type_id=deposit.product_type_id,
            deposit_id=deposit.id,
            commission_type=config["commission_type"],
            level=level,
            base_amount=money(deposit.amount),
            commission_amount=money(commission_amount),
            status=initial_status,
            transaction_date=datetime.utcnow()
        )

        db.add(commission)
        commissions_created.append(commission)

        logger.info(
            "Commission created: user=%s, level=%s, amount=%s, type=%s, status=%s",
            current_sponsor_id,
            level,
            commission_amount,
            config["commission_type"].value,
            initial_status.value,
        )

        current_sponsor_id = sponsor.sponsor_id
        level += 1

    if commissions_created:
        try:
            if commit:
                db.commit()
            else:
                db.flush()
            for c in commissions_created:
                db.refresh(c)
            logger.info(f"Created {len(commissions_created)} commissions for deposit {deposit.id}")
        except Exception as e:
            logger.error(f"Error saving commissions: {e}")
            db.rollback()
            if not commit:
                raise

    return commissions_created


def process_payment_validation(
    db: Session, deposit: Deposit, *, defer_commit: bool = False
) -> bool:
    """
    Traite la validation d'un paiement.
    - Distribue les commissions
    - Active les services associés (KYC, Membership, etc.)
    - Écrit les journaux comptables (payment_accounting)

    Si defer_commit=True, aucun commit n'est fait ici : l'appelant valide dépôt + commissions +
    écritures en une seule transaction (ex. POST /payments/verify après preuve on-chain).

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

        # The deposit's creation-time stamp decides the business model (never deployment time).
        from app.services.new_model_ledger import is_new_model

        new_model = is_new_model(getattr(deposit, "business_model_version", None))

        # Legacy deposits: retired 10-level engine (creates nothing unless re-enabled).
        # NEW_V2 deposits: direct-only commission is accrued by the new posting path below.
        commissions = [] if new_model else distribute_commissions(
            db, deposit, product_code, commit=False
        )

        # The validated deposit is the durable entitlement record.  Do not set
        # transient, unmapped User attributes that disappear after the request.
        user = db.query(User).filter(User.id == deposit.user_id).first()
        if user:
            validity_days = int(getattr(product_type, "validity_days", 0) or 0)
            if validity_days > 0 and deposit.expires_at is None:
                deposit.expires_at = datetime.utcnow() + timedelta(days=validity_days)
            if product_code == "kyc":
                # KYC sera traité séparément après vérification
                logger.info(f"KYC payment validated for user {user.id}")
            elif product_code in ["mfm_membership", "efm_membership", "founding_membership"]:
                logger.info("Founding membership deposit validated for user %s", user.id)
            elif product_code == "annual_membership":
                logger.info("Annual membership deposit validated for user %s", user.id)

            db.flush()

        if new_model:
            from app.services.new_model_payments import process_new_model_deposit

            process_new_model_deposit(db, deposit)
        else:
            # Écritures comptables (plan comptable MyHigh5 — voir docs/MYHIGH5_CHART_OF_ACCOUNTS.md)
            from app.services.payment_accounting import payment_accounting

            journal_commit = False
            if product_code == "kyc":
                # Step 1: cash to deferred2113. Step 2 posts when KYC is approved (Shufti webhook / status sync).
                payment_accounting.process_kyc_cash_receipt_accounting(
                    db, deposit, journal_commit=journal_commit
                )
            elif product_code == "annual_membership":
                payment_accounting.process_membership_payment_accounting(
                    db, deposit, commissions, journal_commit=journal_commit
                )
            elif product_code in ("mfm_membership", "efm_membership", "founding_membership"):
                payment_accounting.process_founding_membership_payment_accounting(
                    db, deposit, commissions, journal_commit=journal_commit
                )
                from app.services.legacy_business_model import (
                    is_legacy_founding_product,
                    legacy_business_model_enabled,
                )

                if user and is_legacy_founding_product(product_code) and legacy_business_model_enabled():
                    from app.services.fmr_service import record_founding_join_fmp

                    record_founding_join_fmp(db, int(user.id), int(deposit.id))
            elif product_code == "club_membership":
                payment_accounting.process_club_membership_payment_accounting(
                    db, deposit, commissions, journal_commit=journal_commit
                )

        if not defer_commit:
            db.commit()
            if user:
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
                    logger.info("Payment confirmation email sent for user %s", user.id)
                except Exception as e:
                    logger.error("Failed to send payment confirmation email: %s", e)

        return True

    except Exception as e:
        logger.error(f"Error processing payment validation: {e}")
        db.rollback()
        return False
