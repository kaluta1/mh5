from sqlalchemy.orm import Session
from app.models.affiliate import CommissionRule, CommissionType
import logging

logger = logging.getLogger(__name__)

def init_commission_rules(db: Session):
    """
    LEGACY seed of the `commission_rules` table. NOT the current policy.

    `commission_rules` belongs to the retired pre-NEW_V2 commission engine
    (app.services.commission_distribution), which creates nothing unless the
    legacy model is re-enabled. The active affiliate program is direct
    referrals only (level 1) and its rate comes from `revenue_policies`
    (NEW_V2), never from this table.

    A fresh environment is seeded direct-only: no indirect percentage and one
    level. Existing rows (the historical 10% / 1% / 10-level configuration) are
    never modified by this function, so the audit trail of what the old program
    paid stays intact.
    """
    rules = [
        {
            "product_code": "kyc",
            "commission_type": CommissionType.KYC_PAYMENT,
            "direct_percentage": 10.0,
            "indirect_percentage": 0.0,
            "max_levels": 1
        },
        {
            "product_code": "mfm_membership",
            "commission_type": CommissionType.FOUNDING_MEMBERSHIP_FEE,
            "direct_percentage": 10.0,
            "indirect_percentage": 0.0,
            "max_levels": 1
        },
        {
            "product_code": "annual_membership",
            "commission_type": CommissionType.ANNUAL_MEMBERSHIP_FEE,
            "direct_percentage": 10.0,
            "indirect_percentage": 0.0,
            "max_levels": 1
        },
        {
            "product_code": "efm_membership",
            "commission_type": CommissionType.EFM_MEMBERSHIP,
            "direct_percentage": 10.0,
            "indirect_percentage": 0.0,
            "max_levels": 1
        }
    ]
    
    for rule_data in rules:
        existing_rule = db.query(CommissionRule).filter(
            CommissionRule.product_code == rule_data["product_code"]
        ).first()
        
        if not existing_rule:
            new_rule = CommissionRule(**rule_data)
            db.add(new_rule)
            logger.info(f"Created default commission rule for {rule_data['product_code']}")
        else:
            # Optionnel : mettre à jour si des valeurs ont changé (force update)
            # Pour l'instant on ne touche pas si ça existe déjà pour ne pas écraser les customs user
            pass
            
    try:
        db.commit()
    except Exception as e:
        logger.error(f"Error initializing commission rules: {e}")
        db.rollback()
