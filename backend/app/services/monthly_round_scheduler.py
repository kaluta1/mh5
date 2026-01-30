"""
Background Monthly Round Generator Service
Automatically creates a round for the current month and links all active contests
Runs on the 1st of each month at midnight
"""
import asyncio
import logging
from datetime import datetime, date
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import select, insert
from app.db.session import SessionLocal
from app.models.round import Round, RoundStatus, round_contests
from app.models.contest import Contest
from app.scripts.generate_monthly_rounds import generate_monthly_round

logger = logging.getLogger(__name__)


class MonthlyRoundScheduler:
    """
    Background service that automatically creates monthly rounds
    """
    
    def __init__(self, check_interval_seconds: int = 86400):  # 24 hours default
        self.check_interval = check_interval_seconds
        self.running = False
        self._task = None
    
    async def start(self):
        """Start the background round generator"""
        if self.running:
            logger.warning("Monthly round scheduler already running")
            return
        
        self.running = True
        self._task = asyncio.create_task(self._check_loop())
        logger.info(f"Monthly round scheduler started (interval: {self.check_interval}s)")
    
    async def stop(self):
        """Stop the background round generator"""
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Monthly round scheduler stopped")
    
    async def _check_loop(self):
        """Main loop that checks and creates rounds periodically"""
        while self.running:
            try:
                await asyncio.sleep(self.check_interval)
                
                if not self.running:
                    break
                
                logger.info(f"[MonthlyRoundScheduler] Running check at {datetime.utcnow()}")
                
                # Check if we need to create a round for the current month
                await self._create_monthly_round_if_needed()
                
            except asyncio.CancelledError:
                logger.info("[MonthlyRoundScheduler] Task cancelled")
                break
            except Exception as e:
                logger.error(f"[MonthlyRoundScheduler] Error: {e}", exc_info=True)
    
    async def _create_monthly_round_if_needed(self):
        """Create a round for the current month if it doesn't exist"""
        db = SessionLocal()
        try:
            today = date.today()
            
            # Check if round for current month already exists
            month_name = today.strftime("%B %Y")
            round_name = f"Round {month_name}"
            
            existing_round = db.query(Round).filter(
                Round.name == round_name
            ).first()
            
            if existing_round:
                logger.info(f"[MonthlyRoundScheduler] Round '{round_name}' already exists (id={existing_round.id})")
                return
            
            # Create the round
            logger.info(f"[MonthlyRoundScheduler] Creating round for {month_name}...")
            new_round = generate_monthly_round(db, target_date=today)
            
            logger.info(f"[MonthlyRoundScheduler] ✅ Round '{round_name}' created successfully (id={new_round.id})")
            
        except Exception as e:
            logger.error(f"[MonthlyRoundScheduler] Error creating monthly round: {e}", exc_info=True)
            db.rollback()
        finally:
            db.close()
    
    def create_round_for_month(self, year: int, month: int) -> Optional[Round]:
        """
        Synchronously create a round for a specific month.
        Useful for manual creation or immediate execution.
        
        Args:
            year: Year (e.g., 2025)
            month: Month (1-12, e.g., 1 for January)
            
        Returns:
            The created Round or None if error
        """
        db = SessionLocal()
        try:
            target_date = date(year, month, 1)
            round_obj = generate_monthly_round(db, target_date=target_date)
            logger.info(f"✅ Round created for {target_date.strftime('%B %Y')} (id={round_obj.id})")
            return round_obj
        except Exception as e:
            logger.error(f"Error creating round for {year}-{month:02d}: {e}", exc_info=True)
            db.rollback()
            return None
        finally:
            db.close()
    
    def ensure_january_round_exists(self) -> Optional[Round]:
        """
        Ensure a January round exists for the current year.
        Creates it if it doesn't exist and links all active contests.
        
        Returns:
            The Round object (existing or newly created)
        """
        db = SessionLocal()
        try:
            today = date.today()
            year = today.year
            month = 1  # January
            
            month_name = f"January {year}"
            round_name = f"Round {month_name}"
            
            logger.info(f"Checking for January round: {round_name}")
            
            # Check if January round already exists
            try:
                existing_round = db.query(Round).filter(
                    Round.name == round_name
                ).first()
            except Exception as e:
                logger.error(f"Error querying for existing round: {e}", exc_info=True)
                raise
            
            if existing_round:
                logger.info(f"January round '{round_name}' already exists (id={existing_round.id})")
                
                # Check if all active contests are linked
                try:
                    active_contests = db.query(Contest).filter(
                        Contest.is_active == True
                    ).all()
                    logger.info(f"Found {len(active_contests)} active contests")
                except Exception as e:
                    logger.error(f"Error querying active contests: {e}", exc_info=True)
                    # Continue without linking if we can't query contests
                    return existing_round
                
                try:
                    linked_contest_ids = set()
                    links = db.execute(
                        select(round_contests).where(
                            round_contests.c.round_id == existing_round.id
                        )
                    ).all()
                    linked_contest_ids = {link.contest_id for link in links}
                    
                    active_contest_ids = {c.id for c in active_contests}
                    unlinked_contests = active_contest_ids - linked_contest_ids
                    
                    if unlinked_contests:
                        logger.info(f"Linking {len(unlinked_contests)} unlinked contests to January round...")
                        linked_count = 0
                        for contest_id in unlinked_contests:
                            try:
                                # Check if link already exists (avoid duplicates)
                                existing_link = db.execute(
                                    select(round_contests).where(
                                        round_contests.c.round_id == existing_round.id,
                                        round_contests.c.contest_id == contest_id
                                    )
                                ).first()
                                
                                if not existing_link:
                                    stmt = insert(round_contests).values(
                                        round_id=existing_round.id,
                                        contest_id=contest_id,
                                        created_at=datetime.utcnow()
                                    )
                                    db.execute(stmt)
                                    linked_count += 1
                            except Exception as e:
                                logger.warning(f"Could not link contest {contest_id}: {e}")
                        
                        if linked_count > 0:
                            db.commit()
                            logger.info(f"✅ Linked {linked_count} contests to January round")
                    else:
                        logger.info("All active contests are already linked to January round")
                except Exception as e:
                    logger.error(f"Error linking contests: {e}", exc_info=True)
                    db.rollback()
                    # Return existing round even if linking failed
                    return existing_round
                
                return existing_round
            
            # Create January round
            logger.info(f"Creating January round for {year}...")
            try:
                round_obj = self.create_round_for_month(year, month)
                if round_obj:
                    logger.info(f"✅ Successfully created January round (id={round_obj.id})")
                    return round_obj
                else:
                    logger.error("create_round_for_month returned None")
                    raise Exception("Failed to create round - create_round_for_month returned None")
            except Exception as e:
                logger.error(f"Error in create_round_for_month: {e}", exc_info=True)
                raise
            
        except Exception as e:
            logger.error(f"Error ensuring January round exists: {e}", exc_info=True)
            db.rollback()
            # Re-raise with more context
            raise Exception(f"Failed to ensure January round exists: {str(e)}") from e
        finally:
            db.close()


# Instance globale du scheduler
monthly_round_scheduler = MonthlyRoundScheduler()
