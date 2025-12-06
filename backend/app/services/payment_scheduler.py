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
from app.models.payment import Deposit, DepositStatus
from app.services.crypto_payment import crypto_payment_service, CryptoPaymentError

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
            # Get all pending deposits from the last 24 hours
            cutoff_time = datetime.utcnow() - timedelta(hours=24)
            pending_deposits: List[Deposit] = db.query(Deposit).filter(
                Deposit.status == DepositStatus.PENDING,
                Deposit.created_at >= cutoff_time,
                Deposit.external_payment_id.isnot(None)
            ).all()
            
            if not pending_deposits:
                print("[PaymentScheduler] No pending deposits found")
                return
            
            print(f"[PaymentScheduler] Found {len(pending_deposits)} pending payments")
            logger.info(f"Checking {len(pending_deposits)} pending payments...")
            
            for deposit in pending_deposits:
                try:
                    await self._check_single_payment(db, deposit)
                except Exception as e:
                    logger.error(f"Error checking deposit {deposit.id}: {e}")
            
            db.commit()
            
        finally:
            db.close()
    
    async def _check_single_payment(self, db: Session, deposit: Deposit):
        """Check and update a single payment"""
        try:
            # Get status from crypto payment provider
            payment_id = int(deposit.external_payment_id)
            print(f"[PaymentScheduler] Checking deposit {deposit.id} (ext: {payment_id})")
            status_response = await crypto_payment_service.get_payment_status(payment_id)
            
            payment_status = status_response.get("payment_status")
            print(f"[PaymentScheduler] Deposit {deposit.id} status: {payment_status}")
            
            if not payment_status:
                return
            
            old_status = deposit.status
            
            # Map payment provider status to deposit status
            if payment_status in ["finished", "confirmed"]:
                deposit.status = DepositStatus.VALIDATED
                deposit.validated_at = datetime.utcnow()
                logger.info(f"Deposit {deposit.id} marked as VALIDATED")
            elif payment_status == "partially_paid":
                deposit.status = DepositStatus.PARTIALLY_PAID
            elif payment_status in ["failed", "expired", "refunded"]:
                deposit.status = DepositStatus.FAILED
                logger.info(f"Deposit {deposit.id} marked as FAILED ({payment_status})")
            elif payment_status in ["waiting", "confirming", "sending"]:
                # Still pending, no change
                pass
            
            # Update crypto amount if available
            if status_response.get("actually_paid"):
                deposit.crypto_amount = status_response.get("actually_paid")
            
            if old_status != deposit.status:
                logger.info(f"Deposit {deposit.id} status changed: {old_status} -> {deposit.status}")
                
        except CryptoPaymentError as e:
            logger.warning(f"Could not check payment {deposit.external_payment_id}: {e.message}")


# Global instance
payment_scheduler = PaymentScheduler()


async def check_payment_now(db: Session, deposit_id: int) -> dict:
    """
    Manually check a single payment status
    Returns the updated status
    """
    deposit = db.query(Deposit).filter(Deposit.id == deposit_id).first()
    if not deposit:
        return {"error": "Deposit not found", "status": None}
    
    if not deposit.external_payment_id:
        return {"error": "No external payment ID", "status": str(deposit.status)}
    
    try:
        payment_id = int(deposit.external_payment_id)
        status_response = await crypto_payment_service.get_payment_status(payment_id)
        
        payment_status = status_response.get("payment_status")
        
        if payment_status in ["finished", "confirmed"]:
            deposit.status = DepositStatus.VALIDATED
            deposit.validated_at = datetime.utcnow()
        elif payment_status == "partially_paid":
            deposit.status = DepositStatus.PARTIALLY_PAID
        elif payment_status in ["failed", "expired", "refunded"]:
            deposit.status = DepositStatus.FAILED
        
        if status_response.get("actually_paid"):
            deposit.crypto_amount = status_response.get("actually_paid")
        
        db.commit()
        
        return {
            "status": str(deposit.status.value),
            "payment_status": payment_status,
            "is_confirmed": deposit.status == DepositStatus.VALIDATED
        }
        
    except CryptoPaymentError as e:
        return {"error": str(e.message), "status": str(deposit.status.value)}
