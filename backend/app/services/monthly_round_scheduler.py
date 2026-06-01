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


def sync_round_calendar_flags(db: Session, round_obj: Round) -> bool:
    """
    Align is_submission_open / is_voting_open / status with calendar dates on the round row.
    Called when ensuring the current-month round so June submissions work on the 1st.
    """
    today = date.today()
    changed = False

    in_submission = bool(
        round_obj.submission_start_date
        and round_obj.submission_end_date
        and round_obj.submission_start_date <= today <= round_obj.submission_end_date
    )
    in_voting = bool(
        round_obj.voting_start_date
        and round_obj.voting_end_date
        and round_obj.voting_start_date <= today <= round_obj.voting_end_date
    )

    if in_submission:
        if round_obj.status == RoundStatus.COMPLETED:
            round_obj.status = RoundStatus.ACTIVE
            changed = True
        if not round_obj.is_submission_open:
            round_obj.is_submission_open = True
            changed = True
    elif round_obj.submission_end_date and today > round_obj.submission_end_date:
        if round_obj.is_submission_open:
            round_obj.is_submission_open = False
            changed = True

    if in_voting:
        if round_obj.status == RoundStatus.COMPLETED:
            round_obj.status = RoundStatus.ACTIVE
            changed = True
        if not round_obj.is_voting_open:
            round_obj.is_voting_open = True
            changed = True
    elif round_obj.voting_end_date and today > round_obj.voting_end_date:
        if round_obj.is_voting_open:
            round_obj.is_voting_open = False
            changed = True
        if round_obj.status != RoundStatus.CANCELLED and not in_submission:
            if round_obj.status != RoundStatus.COMPLETED:
                round_obj.status = RoundStatus.COMPLETED
                changed = True

    if changed:
        db.add(round_obj)
        db.commit()
        db.refresh(round_obj)
    return changed


def resolve_live_nomination_vote_round(db: Session, today: Optional[date] = None) -> Optional[Round]:
    """
    The round users vote in this calendar month: latest round whose submission month has ended.
    On 2026-06-01 that is May (not April with a stale is_voting_open flag).
    """
    today = today or date.today()
    rows = (
        db.query(Round)
        .filter(
            Round.is_voting_open == True,
            Round.status != RoundStatus.COMPLETED,
            Round.submission_end_date.isnot(None),
            Round.submission_end_date < today,
        )
        .all()
    )
    if not rows:
        return None
    return max(rows, key=lambda r: (r.submission_end_date, r.id))


def close_stale_voting_rounds(db: Session, today: Optional[date] = None) -> int:
    """Keep is_voting_open on at most one nomination vote round (latest completed submission month)."""
    today = today or date.today()
    live = resolve_live_nomination_vote_round(db, today)
    changed = 0
    flagged = db.query(Round).filter(Round.is_voting_open == True).all()
    for rnd in flagged:
        if live and rnd.id == live.id:
            continue
        if rnd.submission_end_date and rnd.submission_end_date < today:
            rnd.is_voting_open = False
            db.add(rnd)
            changed += 1
    if changed:
        db.commit()
    return changed


def dedupe_submission_month_rounds(db: Session, target_date: Optional[date] = None) -> int:
    """
    Collapse duplicate rows for the same calendar month (e.g. four 'Round June 2026').
    Keeps the highest id; cancels the rest so Submit picks one canonical round.
    """
    target_date = target_date or date.today()
    month_name = target_date.strftime("%B %Y")
    pattern = f"%{month_name}%"
    rows = (
        db.query(Round)
        .filter(Round.name.ilike(pattern))
        .order_by(Round.id.asc())
        .all()
    )
    if len(rows) <= 1:
        return 0
    keep = rows[-1]
    cancelled = 0
    for rnd in rows[:-1]:
        if rnd.id == keep.id:
            continue
        rnd.status = RoundStatus.CANCELLED
        rnd.is_submission_open = False
        rnd.is_voting_open = False
        db.add(rnd)
        cancelled += 1
    if cancelled:
        db.commit()
        logger.info(
            "Deduped %s submission month: kept id=%s, cancelled %s duplicate(s)",
            month_name,
            keep.id,
            cancelled,
        )
    return cancelled


def link_active_contests_to_round(db: Session, round_id: int) -> int:
    """Link every active contest to the round if not already linked. Returns new link count."""
    active_contests = db.query(Contest).filter(Contest.is_active == True).all()
    try:
        active_contests = [c for c in active_contests if not getattr(c, "is_deleted", False)]
    except Exception:
        pass

    linked = 0
    for contest in active_contests:
        existing_link = db.execute(
            select(round_contests).where(
                round_contests.c.round_id == round_id,
                round_contests.c.contest_id == contest.id,
            )
        ).first()
        if not existing_link:
            db.execute(
                insert(round_contests).values(
                    round_id=round_id,
                    contest_id=contest.id,
                    created_at=datetime.utcnow(),
                )
            )
            linked += 1
    if linked:
        db.commit()
    return linked


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
                logger.info(f"[MonthlyRoundScheduler] Running check at {datetime.utcnow()}")
                await self._create_monthly_round_if_needed()

                if not self.running:
                    break
                await asyncio.sleep(self.check_interval)
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
                sync_round_calendar_flags(db, existing_round)
                link_active_contests_to_round(db, existing_round.id)
                return

            logger.info(f"[MonthlyRoundScheduler] Creating round for {month_name}...")
            new_round = generate_monthly_round(db, target_date=today)
            sync_round_calendar_flags(db, new_round)

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
            logger.info(f"Calling generate_monthly_round for {target_date.strftime('%B %Y')}...")
            round_obj = generate_monthly_round(db, target_date=target_date)
            if round_obj:
                logger.info(f"✅ Round created for {target_date.strftime('%B %Y')} (id={round_obj.id})")
                return round_obj
            else:
                logger.error(f"generate_monthly_round returned None for {year}-{month:02d}")
                return None
        except Exception as e:
            import traceback
            error_traceback = traceback.format_exc()
            logger.error(f"Error creating round for {year}-{month:02d}: {e}", exc_info=True)
            logger.error(f"Full traceback: {error_traceback}")
            db.rollback()
            # Re-raise instead of returning None so the caller can see the actual error
            raise Exception(f"Failed to create round for {year}-{month:02d}: {str(e)}") from e
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
                    error_msg = "create_round_for_month returned None - check logs for underlying error"
                    logger.error(error_msg)
                    raise Exception(error_msg)
            except Exception as e:
                error_msg = f"Error in create_round_for_month: {str(e)}"
                logger.error(error_msg, exc_info=True)
                # Re-raise with more context
                raise Exception(f"Failed to create round for month: {str(e)}") from e
            
        except Exception as e:
            logger.error(f"Error ensuring January round exists: {e}", exc_info=True)
            db.rollback()
            # Re-raise with more context
            raise Exception(f"Failed to ensure January round exists: {str(e)}") from e
        finally:
            db.close()


    def ensure_current_month_round(self) -> Optional[Round]:
        """
        Ensure a round exists for the current month.
        Creates the round if missing, links active contests, and opens submission on the 1st.
        """
        today = date.today()
        month_name = today.strftime("%B %Y")
        round_name = f"Round {month_name}"

        logger.info(f"Ensuring round exists for {month_name}...")

        db = SessionLocal()
        try:
            dedupe_submission_month_rounds(db, today)
            close_stale_voting_rounds(db, today)

            month_start = date(today.year, today.month, 1)
            existing = (
                db.query(Round)
                .filter(
                    Round.name.ilike(f"%{month_name}%"),
                    Round.status != RoundStatus.CANCELLED,
                    Round.submission_start_date == month_start,
                )
                .order_by(Round.id.desc())
                .first()
            )
            if not existing:
                existing = (
                    db.query(Round)
                    .filter(Round.name == round_name, Round.status != RoundStatus.CANCELLED)
                    .order_by(Round.id.desc())
                    .first()
                )
            if existing:
                logger.info(f"Round '{round_name}' already exists (id={existing.id})")
                sync_round_calendar_flags(db, existing)
                linked = link_active_contests_to_round(db, existing.id)
                if linked:
                    logger.info(f"Linked {linked} new contests to {round_name}")
                return existing

            logger.info(f"Creating {round_name}...")
            round_obj = generate_monthly_round(db, target_date=today)
            sync_round_calendar_flags(db, round_obj)
            link_active_contests_to_round(db, round_obj.id)
            logger.info(f"{round_name} created (id={round_obj.id})")
            return round_obj
        except Exception as e:
            logger.error(f"Error ensuring current month round: {e}", exc_info=True)
            db.rollback()
            raise
        finally:
            db.close()


# Instance globale du scheduler
monthly_round_scheduler = MonthlyRoundScheduler()
