"""
Service pour gérer l'état des contests (submission/voting open/closed)

Optional operator extension (UTC, naive datetime string):
  MYHIGH5_NOMINATION_EXTENSION_UNTIL=2026-04-01T18:30:00

When set and now < that instant, any round whose calendar voting window is active
keeps nominations/submissions open and voting stays closed until the instant passes.
Remove the env var or restart without it to resume normal voting.
"""
import asyncio
import logging
import os
from datetime import date, datetime, time, timedelta
from typing import Optional
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.models.contest import Contest

logger = logging.getLogger(__name__)


class ContestStatusService:
    """Service pour gérer l'état des contests"""

    # Extra hours after key milestones (UTC) to keep nominations open for testing / overlap rules.
    SUBMISSION_GRACE_HOURS = 5

    @staticmethod
    def _utc_now() -> datetime:
        return datetime.utcnow()

    @staticmethod
    def nomination_extension_deadline() -> Optional[datetime]:
        """
        Parse MYHIGH5_NOMINATION_EXTENSION_UNTIL (UTC naive ISO: YYYY-MM-DDTHH:MM:SS).
        Returns None if unset or invalid.
        """
        raw = os.environ.get("MYHIGH5_NOMINATION_EXTENSION_UNTIL", "").strip()
        if not raw:
            return None
        s = raw.replace("Z", "").replace("z", "")
        try:
            if len(s) >= 19:
                return datetime.fromisoformat(s[:19])
            return datetime.fromisoformat(s)
        except ValueError:
            logger.warning("Invalid MYHIGH5_NOMINATION_EXTENSION_UNTIL=%r", raw)
            return None

    @staticmethod
    def round_in_voting_calendar(round_obj, when: datetime) -> bool:
        if not round_obj.voting_start_date or not round_obj.voting_end_date:
            return False
        vs = datetime.combine(round_obj.voting_start_date, time.min)
        ve = datetime.combine(round_obj.voting_end_date, time(23, 59, 59))
        return vs <= when <= ve

    @staticmethod
    def env_extra_nomination_active(round_obj, when: datetime) -> bool:
        """
        True when operator extension is active: still in voting calendar but nominations
        remain open and voting must stay off until the extension instant.
        """
        until = ContestStatusService.nomination_extension_deadline()
        if until is None or when >= until:
            return False
        return ContestStatusService.round_in_voting_calendar(round_obj, when)

    @staticmethod
    def extended_submission_deadline(submission_end_day: date) -> datetime:
        """End of submission calendar day + SUBMISSION_GRACE_HOURS (UTC)."""
        end_of_day = datetime.combine(submission_end_day, time(23, 59, 59))
        return end_of_day + timedelta(hours=ContestStatusService.SUBMISSION_GRACE_HOURS)

    @staticmethod
    def round_nomination_closes_at(round_obj) -> Optional[datetime]:
        """
        Last moment nominations are accepted for this round.

        Uses the *later* of:
        - end of submission day + SUBMISSION_GRACE_HOURS
        - start of voting day + SUBMISSION_GRACE_HOURS

        So if the calendar voting period has started but submission+5h already passed,
        nomination stays open until voting_day 00:00 + 5h; then voting can run.
        """
        deadlines: list[datetime] = []
        if getattr(round_obj, "submission_end_date", None):
            deadlines.append(
                ContestStatusService.extended_submission_deadline(round_obj.submission_end_date)
            )
        if getattr(round_obj, "voting_start_date", None):
            vote_day_start = datetime.combine(round_obj.voting_start_date, time.min)
            deadlines.append(
                vote_day_start + timedelta(hours=ContestStatusService.SUBMISSION_GRACE_HOURS)
            )
        if not deadlines:
            out = None
        else:
            out = max(deadlines)
        now = ContestStatusService._utc_now()
        until = ContestStatusService.nomination_extension_deadline()
        if until and now < until and ContestStatusService.round_in_voting_calendar(round_obj, now):
            if out is None:
                return until
            return max(out, until)
        return out

    @staticmethod
    def round_submission_open_at(round_obj, when: datetime) -> bool:
        """True if nominations/submissions are allowed for this round at ``when`` (includes grace)."""
        if ContestStatusService.env_extra_nomination_active(round_obj, when):
            return True
        if not round_obj.submission_start_date or not round_obj.submission_end_date:
            return False
        start = datetime.combine(round_obj.submission_start_date, time.min)
        end = ContestStatusService.round_nomination_closes_at(round_obj)
        if end is None:
            return False
        return start <= when <= end

    @staticmethod
    def round_in_submission_grace(round_obj, when: datetime) -> bool:
        """True after end of submission calendar day but nominations still accepted (voting not yet)."""
        if not round_obj.submission_end_date:
            return False
        end_of_cal_day = datetime.combine(round_obj.submission_end_date, time(23, 59, 59))
        nom_close = ContestStatusService.round_nomination_closes_at(round_obj)
        if not nom_close:
            return False
        return end_of_cal_day < when <= nom_close

    @staticmethod
    def round_voting_open_at(round_obj, when: datetime) -> bool:
        """
        Voting allowed only after the full nomination window (including grace) has ended,
        and while within the round voting date range (inclusive by calendar day).
        """
        if ContestStatusService.env_extra_nomination_active(round_obj, when):
            return False
        if not round_obj.voting_start_date or not round_obj.voting_end_date:
            return False
        nom_close = ContestStatusService.round_nomination_closes_at(round_obj)
        if nom_close is not None and when <= nom_close:
            return False
        vs = datetime.combine(round_obj.voting_start_date, time.min)
        ve = datetime.combine(round_obj.voting_end_date, time(23, 59, 59))
        return vs <= when <= ve

    @staticmethod
    def update_contest_statuses(db: Session) -> dict:
        """
        Met à jour automatiquement les statuts is_submission_open et is_voting_open
        pour tous les contests actifs basés sur les dates des rounds actifs.
        
        Règles:
        - is_submission_open = True si AU MOINS UN round actif accepte les soumissions
        - is_voting_open = True si AU MOINS UN round actif est en phase de vote
        
        Utilise la table round_contests pour la relation N:N (Round.contest_id est toujours NULL).
        """
        from app.models.round import Round, RoundStatus, round_contests
        
        now = ContestStatusService._utc_now()
        updated_count = 0
        results = []
        
        # Récupérer tous les contests actifs
        contests = db.query(Contest).filter(
            Contest.is_deleted == False,
            Contest.is_active == True
        ).all()
        
        for contest in contests:
            old_submission_open = contest.is_submission_open
            old_voting_open = contest.is_voting_open
            
            # Récupérer les rounds actifs pour ce contest via round_contests (N:N)
            active_rounds = db.query(Round).join(
                round_contests, round_contests.c.round_id == Round.id
            ).filter(
                round_contests.c.contest_id == contest.id,
                Round.status != RoundStatus.CANCELLED
            ).all()
            
            # Par défaut, tout est fermé
            is_submission_open = False
            is_voting_open = False
            
            for round_obj in active_rounds:
                # Vérifier soumission (inclut la fenêtre de grâce après la fin calendaire)
                if ContestStatusService.round_submission_open_at(round_obj, now):
                    is_submission_open = True
                
                # Vérifier vote (fermé pendant la grâce de soumission)
                if ContestStatusService.round_voting_open_at(round_obj, now):
                    is_voting_open = True
                
                # Si les deux sont ouverts, on peut arrêter de chercher (optimisation)
                if is_submission_open and is_voting_open:
                    break
            
            # Mettre à jour si nécessaire
            if (contest.is_submission_open != is_submission_open or 
                contest.is_voting_open != is_voting_open):
                
                contest.is_submission_open = is_submission_open
                contest.is_voting_open = is_voting_open
                updated_count += 1
                
                results.append({
                    "contest_id": contest.id,
                    "contest_name": contest.name,
                    "old_submission_open": old_submission_open,
                    "new_submission_open": is_submission_open,
                    "old_voting_open": old_voting_open,
                    "new_voting_open": is_voting_open
                })
        
        if updated_count > 0:
            db.commit()
        
        return {
            "updated_count": updated_count,
            "results": results
        }
    
    @staticmethod
    def check_submission_allowed(db: Session, contest_id: int) -> tuple[bool, str]:
        """
        Vérifie si les soumissions sont autorisées pour un contest.
        Allows submissions based on contest deadline, not rounds.
        
        Returns:
            (is_allowed, error_message)
        """
        from app.models.round import Round, RoundStatus, round_contests
        
        contest = db.query(Contest).filter(
            Contest.id == contest_id,
            Contest.is_deleted == False
        ).first()
        
        if not contest:
            return False, "Contest not found"
        
        # Vérifier si le contest est actif
        if not contest.is_active:
            return False, "This contest is not active"
            
        now = ContestStatusService._utc_now()
        
        # Check if contest has a submission_end_date (with grace hours after last day)
        if contest.submission_end_date:
            if contest.submission_start_date:
                start_dt = datetime.combine(contest.submission_start_date, time.min)
                if now < start_dt:
                    return False, "Submissions are not open yet for this contest."
            ext = ContestStatusService.extended_submission_deadline(contest.submission_end_date)
            if now > ext:
                return False, f"Submissions closed. Extended deadline was {ext.date()} (includes {ContestStatusService.SUBMISSION_GRACE_HOURS}h grace)."
            return True, ""
        
        # If no submission_end_date, check for active rounds as fallback via round_contests
        candidate_rounds = db.query(Round).join(
            round_contests, round_contests.c.round_id == Round.id
        ).filter(
            round_contests.c.contest_id == contest_id,
            Round.status != RoundStatus.CANCELLED,
        ).all()
        
        for r in candidate_rounds:
            if ContestStatusService.round_submission_open_at(r, now):
                return True, ""
            
        # If no rounds and no deadline, allow submission (default behavior)
        return True, ""
    
    @staticmethod
    def check_voting_allowed(db: Session, contest_id: int) -> tuple[bool, str]:
        """
        Vérifie si le vote est autorisé pour un contest.
        Un round doit être en phase de vote (voting_start_date <= today <= voting_end_date).
        
        Utilise la table round_contests pour la relation N:N (Round.contest_id est toujours NULL).
        
        Returns:
            (is_allowed, error_message)
        """
        from app.models.round import Round, RoundStatus, round_contests
        
        contest = db.query(Contest).filter(
            Contest.id == contest_id,
            Contest.is_deleted == False
        ).first()
        
        if not contest:
            return False, "Contest not found"
        
        # Vérifier si le contest est actif
        if not contest.is_active:
            return False, "This contest is not active"
        
        now = ContestStatusService._utc_now()
        today = date.today()

        rounds = db.query(Round).join(
            round_contests, round_contests.c.round_id == Round.id
        ).filter(
            round_contests.c.contest_id == contest_id,
            Round.status != RoundStatus.CANCELLED,
        ).all()

        for r in rounds:
            if ContestStatusService.round_voting_open_at(r, now):
                return True, ""

        for r in rounds:
            if ContestStatusService.env_extra_nomination_active(r, now):
                u = ContestStatusService.nomination_extension_deadline()
                if u:
                    return False, (
                        f"Nominations extended until {u.isoformat()} UTC "
                        "(MYHIGH5_NOMINATION_EXTENSION_UNTIL). Voting opens after that."
                    )

        # Message utile si pas de vote — chercher le prochain round de vote
        next_voting_round = db.query(Round).join(
            round_contests, round_contests.c.round_id == Round.id
        ).filter(
            round_contests.c.contest_id == contest_id,
            Round.status != RoundStatus.CANCELLED,
            Round.voting_start_date > today
        ).order_by(Round.voting_start_date.asc()).first()
        
        if next_voting_round:
            return False, f"Voting for the next round ({next_voting_round.name}) will start on {next_voting_round.voting_start_date}"
        
        # Nominations still open (grace / voting-day extension) — voting waits
        for r in rounds:
            nom_close = ContestStatusService.round_nomination_closes_at(r)
            if not nom_close or not r.voting_start_date or not r.voting_end_date:
                continue
            vs = datetime.combine(r.voting_start_date, time.min)
            ve = datetime.combine(r.voting_end_date, time(23, 59, 59))
            if vs <= now <= ve and now <= nom_close:
                return False, (
                    f"Nominations for {r.name} stay open until {nom_close.isoformat()} UTC "
                    f"({ContestStatusService.SUBMISSION_GRACE_HOURS}h grace). Voting opens after that."
                )
            if ContestStatusService.round_in_submission_grace(r, now):
                return False, (
                    f"Nomination period extended for {r.name}. Voting opens after {nom_close.isoformat()} UTC."
                )

        # Calendar submission phase (no grace yet) or generic message
        for r in rounds:
            if r.submission_start_date and r.submission_end_date:
                sd, ed = r.submission_start_date, r.submission_end_date
                if sd <= today <= ed:
                    return False, (
                        f"Submission phase is active for {r.name}. "
                        f"Voting starts after the nomination window and {ContestStatusService.SUBMISSION_GRACE_HOURS}h grace."
                    )

        return False, "Voting is not open for any round at this time"


# Instance du service
contest_status_service = ContestStatusService()


class ContestStatusScheduler:
    """
    Service en arrière-plan qui vérifie périodiquement et met à jour les statuts des contests
    """
    
    def __init__(self, check_interval_seconds: int = 3600):  # 1 heure par défaut
        self.check_interval = check_interval_seconds
        self.running = False
        self._task = None
    
    async def start(self):
        """Démarrer le vérificateur de statut des contests en arrière-plan"""
        if self.running:
            logger.warning("Contest status scheduler déjà en cours d'exécution")
            return
        
        self.running = True
        self._task = asyncio.create_task(self._check_loop())
        logger.info(f"Contest status scheduler démarré (intervalle: {self.check_interval}s)")
    
    async def stop(self):
        """Arrêter le vérificateur de statut des contests en arrière-plan"""
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Contest status scheduler arrêté")
    
    async def _check_loop(self):
        """Boucle principale qui vérifie les statuts des contests périodiquement"""
        # Attendre un peu avant la première vérification pour laisser l'app démarrer complètement
        await asyncio.sleep(10)
        
        while self.running:
            try:
                print(f"[ContestStatusScheduler] Exécution de la vérification à {datetime.utcnow()}")
                await self._check_contest_statuses()
            except Exception as e:
                print(f"[ContestStatusScheduler] Erreur: {e}")
                logger.error(f"Erreur dans la boucle de vérification des contests: {e}")
            
            print(f"[ContestStatusScheduler] Prochaine vérification dans {self.check_interval} secondes")
            await asyncio.sleep(self.check_interval)
    
    async def _check_contest_statuses(self):
        """Vérifier et mettre à jour les statuts de tous les contests actifs"""
        db: Session = SessionLocal()
        try:
            result = ContestStatusService.update_contest_statuses(db)
            
            if result["updated_count"] > 0:
                print(f"[ContestStatusScheduler] {result['updated_count']} contest(s) mis à jour")
                logger.info(f"{result['updated_count']} contest(s) mis à jour")
                for contest_result in result["results"]:
                    print(f"[ContestStatusScheduler] Contest {contest_result['contest_id']} ({contest_result['contest_name']}): "
                          f"submission {contest_result['old_submission_open']} -> {contest_result['new_submission_open']}, "
                          f"voting {contest_result['old_voting_open']} -> {contest_result['new_voting_open']}")
            else:
                print("[ContestStatusScheduler] Aucun contest à mettre à jour")
        except Exception as e:
            logger.error(f"Erreur lors de la vérification des statuts des contests: {e}")
            print(f"[ContestStatusScheduler] Erreur lors de la vérification: {e}")
        finally:
            db.close()


# Instance globale du scheduler
contest_status_scheduler = ContestStatusScheduler()
