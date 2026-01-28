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
# Note: Smart contract payments are verified on-demand via /verify endpoint
# This scheduler only handles expiration of pending payments
from app.services.commission_distribution import process_payment_validation

logger = logging.getLogger(__name__)


class PaymentScheduler:
    """
    Background service that periodically checks pending payment statuses
    """
    
    def __init__(self, check_interval_seconds: int = 120):  # 2 minutes default
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
            
            # Get only PENDING deposits with external payment ID
            pending_deposits: List[Deposit] = db.query(Deposit).filter(
                Deposit.status == DepositStatus.PENDING,
                Deposit.external_payment_id.isnot(None)
            ).all()
            
            if not pending_deposits:
                print("[PaymentScheduler] No pending deposits found")
                return
            
            print(f"[PaymentScheduler] Found {len(pending_deposits)} pending payments")
            logger.info(f"Checking {len(pending_deposits)} pending payments...")
            
            for deposit in pending_deposits:
                try:
                    # Check if payment is expired (older than 1 hour)
                    if deposit.created_at < expiration_time:
                        deposit.status = DepositStatus.EXPIRED
                        logger.info(f"Deposit {deposit.id} marked as EXPIRED (created at {deposit.created_at})")
                        print(f"[PaymentScheduler] Deposit {deposit.id} EXPIRED after 1 hour")
                        continue
                    
                    # Otherwise, check payment status with provider
                    await self._check_single_payment(db, deposit)
                except Exception as e:
                    logger.error(f"Error checking deposit {deposit.id}: {e}")
            
            db.commit()
            
        finally:
            db.close()
    
    async def _check_single_payment(self, db: Session, deposit: Deposit):
        """Check and update a single payment"""
        # For smart contract payments, verification is done on-demand
        # This function only handles expiration
        # If deposit has a tx_hash (external_payment_id), it should be verified via /verify endpoint
        pass
    
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
    """
    Check payment status (for smart contracts, verification is done via /verify endpoint)
    This function only checks expiration
    """
    deposit = db.query(Deposit).filter(Deposit.id == deposit_id).first()
    if not deposit:
        return {"error": "Deposit not found", "status": None}
    
    # Check if expired (older than 1 hour)
    expiration_time = datetime.utcnow() - timedelta(hours=1)
    if deposit.status == DepositStatus.PENDING and deposit.created_at < expiration_time:
        deposit.status = DepositStatus.EXPIRED
        db.commit()
        return {
            "status": "expired",
            "payment_status": "expired",
            "is_confirmed": False,
            "message": "Payment expired after 1 hour"
        }
    
    return {
        "status": str(deposit.status.value),
        "payment_status": deposit.status.value,
        "is_confirmed": deposit.status == DepositStatus.VALIDATED
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
