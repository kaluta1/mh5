"""
Service pour gérer l'état des contests (submission/voting open/closed)
"""
import asyncio
import logging
from datetime import date, datetime
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.models.contest import Contest

logger = logging.getLogger(__name__)


class ContestStatusService:
    """Service pour gérer l'état des contests"""
    
    @staticmethod
    def update_contest_statuses(db: Session) -> dict:
        """
        Met à jour automatiquement les statuts is_submission_open et is_voting_open
        pour tous les contests actifs basés sur les dates des rounds actifs.
        
        Règles:
        - is_submission_open = True si AU MOINS UN round actif accepte les soumissions
        - is_voting_open = True si AU MOINS UN round actif est en phase de vote
        """
        from app.models.round import Round, RoundStatus
        
        today = date.today()
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
            
            # Récupérer les rounds actifs pour ce contest
            active_rounds = db.query(Round).filter(
                Round.contest_id == contest.id,
                Round.status != RoundStatus.CANCELLED
            ).all()
            
            # Par défaut, tout est fermé
            is_submission_open = False
            is_voting_open = False
            
            for round_obj in active_rounds:
                # Vérifier soumission
                if round_obj.submission_start_date and round_obj.submission_end_date:
                    if round_obj.submission_start_date <= today <= round_obj.submission_end_date:
                        is_submission_open = True
                
                # Vérifier vote
                if round_obj.voting_start_date and round_obj.voting_end_date:
                    if round_obj.voting_start_date <= today <= round_obj.voting_end_date:
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
        from app.models.round import Round, RoundStatus
        
        contest = db.query(Contest).filter(
            Contest.id == contest_id,
            Contest.is_deleted == False
        ).first()
        
        if not contest:
            return False, "Contest not found"
        
        # Vérifier si le contest est actif
        if not contest.is_active:
            return False, "This contest is not active"
            
        # Check submission deadline instead of rounds
        today = date.today()
        
        # Check if contest has a submission_end_date and if it has passed
        if contest.submission_end_date:
            if today > contest.submission_end_date:
                return False, f"Submissions closed. Deadline was {contest.submission_end_date}"
            # If deadline hasn't passed, allow submission
            return True, ""
        
        # If no submission_end_date, check for active rounds as fallback
        active_submission_round = db.query(Round).filter(
            Round.contest_id == contest_id,
            Round.status != RoundStatus.CANCELLED,
            Round.submission_start_date <= today,
            Round.submission_end_date >= today
        ).first()
        
        if active_submission_round:
            return True, ""
            
        # If no rounds and no deadline, allow submission (default behavior)
        # This allows submissions regardless of rounds
        return True, ""
    
    @staticmethod
    def check_voting_allowed(db: Session, contest_id: int) -> tuple[bool, str]:
        """
        Vérifie si le vote est autorisé pour un contest (i.e., il y a un round actif en phase de vote).
        
        Returns:
            (is_allowed, error_message)
        """
        from app.models.round import Round, RoundStatus
        
        contest = db.query(Contest).filter(
            Contest.id == contest_id,
            Contest.is_deleted == False
        ).first()
        
        if not contest:
            return False, "Contest not found"
        
        # Vérifier si le contest est actif
        if not contest.is_active:
            return False, "This contest is not active"
        
        # Vérifier si un round permet le vote aujourd'hui
        today = date.today()
        
        active_voting_round = db.query(Round).filter(
            Round.contest_id == contest_id,
            Round.status != RoundStatus.CANCELLED,
            Round.voting_start_date <= today,
            Round.voting_end_date >= today
        ).first()
        
        if active_voting_round:
            return True, ""
            
        # Message utile si pas de vote
        next_voting_round = db.query(Round).filter(
            Round.contest_id == contest_id,
            Round.status != RoundStatus.CANCELLED,
            Round.voting_start_date > today
        ).order_by(Round.voting_start_date.asc()).first()
        
        if next_voting_round:
            return False, f"Voting for the next round ({next_voting_round.name}) will start on {next_voting_round.voting_start_date}"
            
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

