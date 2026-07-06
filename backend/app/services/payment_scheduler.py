"""
Background Payment Status Checker Service
Checks pending crypto payments every 2 minutes
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
        """Check all pending payments and update their status"""
        db: Session = SessionLocal()
        try:
            # Expiration time: 1 hour
            expiration_time = datetime.utcnow() - timedelta(hours=1)
            
            # Pending / partial payments with a NOWPayments id
            open_deposits: List[Deposit] = db.query(Deposit).filter(
                Deposit.status.in_([DepositStatus.PENDING, DepositStatus.PARTIALLY_PAID]),
                Deposit.external_payment_id.isnot(None),
            ).all()

            if not open_deposits:
                print("[PaymentScheduler] No open deposits to sync")
                return

            print(f"[PaymentScheduler] Found {len(open_deposits)} open payments")
            logger.info("Checking %s open payments...", len(open_deposits))

            for deposit in open_deposits:
                try:
                    # Only expire untouched pending invoices (not partial payments)
                    if (
                        deposit.status == DepositStatus.PENDING
                        and deposit.created_at < expiration_time
                    ):
                        deposit.status = DepositStatus.EXPIRED
                        logger.info(
                            "Deposit %s marked as EXPIRED (created at %s)",
                            deposit.id,
                            deposit.created_at,
                        )
                        print(f"[PaymentScheduler] Deposit {deposit.id} EXPIRED after 1 hour")
                        continue

                    await self._check_single_payment(db, deposit)
                except Exception as e:
                    logger.error(f"Error checking deposit {deposit.id}: {e}")
            
            db.commit()
            
        finally:
            db.close()
    
    async def _check_single_payment(self, db: Session, deposit: Deposit):
        """Poll NOWPayments and finalize deposit when finished."""
        if not deposit.external_payment_id:
            return
        if deposit.status != DepositStatus.PENDING and deposit.status != DepositStatus.PARTIALLY_PAID:
            return

        from app.services.nowpayments_service import (
            finalize_deposit_from_nowpayments,
            get_payment_status,
        )

        try:
            payload = await get_payment_status(deposit.external_payment_id)
            ok = finalize_deposit_from_nowpayments(db, deposit, payload, defer_commit=True)
            if not ok:
                logger.warning("Commission/accounting failed for deposit %s during scheduler sync", deposit.id)
        except Exception as exc:
            logger.error("NOWPayments sync failed for deposit %s: %s", deposit.id, exc)
    
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


# Global instance
payment_scheduler = PaymentScheduler()


async def check_payment_now(db: Session, deposit_id: int) -> dict:
    """Check payment status via NOWPayments (or return current deposit state)."""
    from app.services.nowpayments_service import NowPaymentsError, sync_deposit_with_provider

    deposit = db.query(Deposit).filter(Deposit.id == deposit_id).first()
    if not deposit:
        return {"error": "Deposit not found", "status": None}

    expiration_time = datetime.utcnow() - timedelta(hours=1)
    if deposit.created_at < expiration_time and deposit.status == DepositStatus.PENDING:
        deposit.status = DepositStatus.EXPIRED
        db.commit()
        return {
            "status": "expired",
            "payment_status": "expired",
            "is_confirmed": False,
            "message": "Payment expired after 1 hour",
        }

    if deposit.external_payment_id and deposit.status in (
        DepositStatus.PENDING,
        DepositStatus.PARTIALLY_PAID,
    ):
        try:
            payload = await sync_deposit_with_provider(db, deposit)
            db.commit()
            return payload
        except NowPaymentsError as exc:
            db.rollback()
            return {
                "status": deposit.status.value,
                "payment_status": deposit.status.value,
                "is_confirmed": False,
                "message": str(exc),
            }

    return {
        "status": deposit.status.value,
        "payment_status": deposit.status.value,
        "is_confirmed": deposit.status == DepositStatus.VALIDATED,
    }


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
