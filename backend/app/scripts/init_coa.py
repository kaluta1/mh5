import logging

from sqlalchemy.orm import Session

from app.services.accounting_posting import accounting_posting_service

logger = logging.getLogger(__name__)

def init_chart_of_accounts(db: Session):
    """
    Seed or update the canonical chart of accounts.

    The rollout is intentionally idempotent so existing environments can be
    updated safely without deleting or recreating accounts.
    """
    try:
        changed_count = accounting_posting_service.seed_chart_of_accounts(db)
        db.commit()
        logger.info("Chart of accounts seed completed with %s changed rows", changed_count)
    except Exception as e:
        logger.error(f"Error initializing CoA: {e}")
        db.rollback()
        raise
