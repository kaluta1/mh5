"""
Background Payment Status Checker Service
Checks open crypto payments with the provider (default: once an hour).
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import List

from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.models.payment import Deposit, DepositStatus, ProductType
from app.models.affiliate import CommissionType
from app.crud.crud_affiliate import affiliate_commission
# Note: Crypto payments use NOWPayments; verified via IPN webhook + scheduler polling.
from app.services.commission_distribution import process_payment_validation

logger = logging.getLogger(__name__)

# Existing policy: an invoice nobody paid is closed here one hour after it was
# created. The provider keeps the same invoice payable for 7 days.
LOCAL_EXPIRY = timedelta(hours=1)
PROVIDER_PAYMENT_WINDOW = timedelta(days=7)
EXPIRED_RECHECK_LIMIT = 200
POLLED_STATUSES = (DepositStatus.PENDING, DepositStatus.PARTIALLY_PAID, DepositStatus.EXPIRED)
# Provider statuses that say no money has arrived for the invoice.
NOTHING_RECEIVED = ("waiting", "expired")


def apply_provider_status(db: Session, deposit_id: int, payload: dict) -> str:
    """Apply one provider answer to one deposit under a row lock, then commit.

    * a deposit already expired here is touched only when the provider reports
      that money arrived (so "waiting" never re-opens it);
    * an open deposit follows the provider; when it is still unpaid one hour
      after creation and the provider confirms nothing was received, it is
      expired (the existing one-hour policy, now decided with the provider's
      answer instead of without it)."""
    from app.services.financial_integrity import FinancialIntegrityError
    from app.services.nowpayments_service import finalize_deposit_from_nowpayments

    provider_status = str(payload.get("payment_status") or payload.get("status") or "").lower()
    deposit = db.query(Deposit).filter(Deposit.id == deposit_id).with_for_update().one()
    if deposit.status not in POLLED_STATUSES:
        db.rollback()
        return "SKIPPED"
    was_expired = deposit.status == DepositStatus.EXPIRED
    if was_expired and (not provider_status or provider_status in NOTHING_RECEIVED):
        db.rollback()
        return "STILL_EXPIRED"
    try:
        ok = finalize_deposit_from_nowpayments(db, deposit, payload, defer_commit=True)
    except FinancialIntegrityError:
        db.rollback()
        logger.error("Provider answer for deposit %s does not match the deposit; nothing applied", deposit_id)
        return "IDENTITY_REJECTED"
    if not ok:
        db.rollback()
        logger.warning("Commission/accounting failed for deposit %s during scheduler sync", deposit_id)
        return "ERROR"
    outcome = "SYNCED"
    if (deposit.status == DepositStatus.PENDING and provider_status in NOTHING_RECEIVED
            and deposit.created_at is not None and deposit.created_at < datetime.utcnow() - LOCAL_EXPIRY):
        deposit.status = DepositStatus.EXPIRED
        _release_pool_seat_for_deposit(db, deposit.id)
        logger.info("Deposit %s marked as EXPIRED (created at %s, provider status %s)", deposit.id,
                    deposit.created_at, provider_status)
        outcome = "EXPIRED"
    elif was_expired:
        logger.warning("Deposit %s had expired here but the provider reports %s", deposit.id, provider_status)
        outcome = "REOPENED"
    db.commit()
    return outcome


class PaymentScheduler:
    """
    Background service that periodically checks pending payment statuses
    """
    
    def __init__(self, check_interval_seconds: int = 3600):  # 1 hour default
        self.check_interval = check_interval_seconds
        self.running = False
        self._task = None
    
    async def start(self):
        """Start the background payment checker"""
        if self.running:
            logger.warning("Payment scheduler already running")
            return
        
        self.running = True
        self._task = asyncio.create_task(self._check_loop())
        logger.info(f"Payment scheduler started (interval: {self.check_interval}s)")
    
    async def stop(self):
        """Stop the background payment checker"""
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Payment scheduler stopped")
    
    async def _check_loop(self):
        """Main loop that checks payments periodically"""
        # Wait a bit before first check to let the app fully start
        await asyncio.sleep(10)
        
        while self.running:
            try:
                print(f"[PaymentScheduler] Running check at {datetime.utcnow()}")
                await self._check_pending_payments()
            except Exception as e:
                print(f"[PaymentScheduler] Error: {e}")
                logger.error(f"Error in payment check loop: {e}")
            
            print(f"[PaymentScheduler] Next check in {self.check_interval} seconds")
            await asyncio.sleep(self.check_interval)
    
    async def _check_pending_payments(self):
        """Ask the provider about every open payment and apply what it says.

        Each deposit is its own transaction: it is committed (or rolled back)
        before the next one is read, so one deposit can never undo another.
        The provider's status is authoritative. An invoice is expired locally
        only after the provider was asked and reported that nothing has been
        received; when the provider cannot be reached the deposit is left as
        it is and looked at again on the next pass."""
        db: Session = SessionLocal()
        try:
            now = datetime.utcnow()
            open_ids = [row.id for row in db.query(Deposit.id).filter(
                Deposit.status.in_([DepositStatus.PENDING, DepositStatus.PARTIALLY_PAID]),
                Deposit.external_payment_id.isnot(None),
                Deposit.external_payment_id != "",
            ).order_by(Deposit.id).all()]
            # Invoices expired here that the provider still accepts money for
            # (its own window is 7 days): a late payment must still be found.
            expired_ids = [row.id for row in db.query(Deposit.id).filter(
                Deposit.status == DepositStatus.EXPIRED,
                Deposit.external_payment_id.isnot(None),
                Deposit.external_payment_id != "",
                Deposit.created_at >= now - PROVIDER_PAYMENT_WINDOW,
            ).order_by(Deposit.id.desc()).limit(EXPIRED_RECHECK_LIMIT).all()]
            db.rollback()

            if not open_ids and not expired_ids:
                return
            logger.info("Checking %s open and %s recently expired payments", len(open_ids), len(expired_ids))
            for deposit_id in open_ids + expired_ids:
                try:
                    await self._check_single_payment(db, deposit_id)
                except Exception:  # noqa: BLE001 - one deposit never stops the others
                    db.rollback()
                    logger.exception("Error checking deposit %s", deposit_id)
        finally:
            db.close()

    async def _check_single_payment(self, db: Session, deposit_id: int) -> str:
        """Poll NOWPayments for one deposit and apply its answer. Commits."""
        from app.services.nowpayments_service import get_payment_status

        deposit = db.query(Deposit).filter(Deposit.id == deposit_id).first()
        if deposit is None or not deposit.external_payment_id or deposit.status not in POLLED_STATUSES:
            db.rollback()
            return "SKIPPED"
        payment_id = str(deposit.external_payment_id)
        db.rollback()                                   # no transaction is held while waiting
        try:
            payload = await get_payment_status(payment_id)
        except Exception as exc:  # noqa: BLE001 - no answer: nothing is decided
            logger.error("NOWPayments status unavailable for deposit %s: %s", deposit_id, type(exc).__name__)
            return "PROVIDER_UNAVAILABLE"
        return apply_provider_status(db, deposit_id, payload)

    def _create_sponsor_commission(self, db: Session, deposit: Deposit):
        """Crée les commissions pour les parrains quand un paiement est validé"""
        try:
            # Utiliser le nouveau service de distribution des commissions
            print(f"[PaymentScheduler] Processing commission distribution for deposit {deposit.id}")
            success = process_payment_validation(db, deposit)
            
            if success:
                print(f"[PaymentScheduler] Commission distribution completed for deposit {deposit.id}")
                logger.info(f"Commission distribution completed for deposit {deposit.id}")
            else:
                print(f"[PaymentScheduler] Commission distribution failed for deposit {deposit.id}")
                logger.warning(f"Commission distribution failed for deposit {deposit.id}")
            
        except Exception as e:
            print(f"[PaymentScheduler] Error creating commission: {e}")
            logger.error(f"Error creating commission for deposit {deposit.id}: {e}")


def _release_pool_seat_for_deposit(db: Session, deposit_id: int) -> None:
    """An expired invoice must not keep a Referral Pool seat reserved."""
    from app.models.business_model import ReferralPoolMembership
    from app.services import referral_pool_service as pool

    seat = db.query(ReferralPoolMembership).filter(ReferralPoolMembership.source_deposit_id == deposit_id).first()
    if seat is not None:
        pool.release_reservation(db, seat, "Invoice expired unpaid")


# Global instance
payment_scheduler = PaymentScheduler()


async def check_payment_now(db: Session, deposit_id: int) -> dict:
    """Check payment status via NOWPayments (or return current deposit state).
    The provider is asked before anything is expired."""
    from app.services.nowpayments_service import get_payment_status

    deposit = db.query(Deposit).filter(Deposit.id == deposit_id).first()
    if not deposit:
        return {"error": "Deposit not found", "status": None}

    if deposit.external_payment_id and deposit.status in POLLED_STATUSES:
        payment_id = str(deposit.external_payment_id)
        db.rollback()
        try:
            payload = await get_payment_status(payment_id)
        except Exception as exc:  # noqa: BLE001
            deposit = db.query(Deposit).filter(Deposit.id == deposit_id).first()
            return {
                "status": deposit.status.value,
                "payment_status": deposit.status.value,
                "is_confirmed": False,
                "message": "The payment provider could not be reached; nothing was changed.",
            }
        apply_provider_status(db, deposit_id, payload)
        deposit = db.query(Deposit).filter(Deposit.id == deposit_id).first()

    result = {
        "status": deposit.status.value,
        "payment_status": deposit.status.value,
        "is_confirmed": deposit.status == DepositStatus.VALIDATED,
    }
    if deposit.status == DepositStatus.EXPIRED:
        result["message"] = "Payment expired after 1 hour"
    return result


def _create_commission_for_deposit(db: Session, deposit: Deposit):
    """Fonction helper pour créer les commissions lors d'une vérification manuelle"""
    try:
        # Utiliser le nouveau service de distribution des commissions
        from app.services.commission_distribution import process_payment_validation
        
        print(f"[ManualCheck] Processing commission distribution for deposit {deposit.id}")
        success = process_payment_validation(db, deposit)
        
        if success:
            print(f"[ManualCheck] Commission distribution completed for deposit {deposit.id}")
        else:
            print(f"[ManualCheck] Commission distribution failed for deposit {deposit.id}")
            
    except Exception as e:
        print(f"[ManualCheck] Error creating commission: {e}")
