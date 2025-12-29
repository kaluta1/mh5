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
        pour tous les contests actifs basés sur les dates.
        
        Règles:
        - is_submission_open = True si aujourd'hui est entre submission_start_date et submission_end_date
        - is_voting_open = True si aujourd'hui est >= submission_end_date ET <= voting_end_date
        - Quand submission_end_date arrive, is_submission_open devient False et is_voting_open devient True
        - Si le vote est ouvert (is_voting_open = True), les soumissions doivent être fermées (is_submission_open = False)
        """
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
            
            # Déterminer l'état de vote en premier
            # Vote ouvert si aujourd'hui est >= submission_end_date ET <= voting_end_date
            is_voting_open = (
                contest.submission_end_date <= today <= contest.voting_end_date
            )
            
            # Déterminer l'état de soumission
            # Soumission ouverte si aujourd'hui est entre submission_start_date et submission_end_date
            # MAIS seulement si le vote n'est pas encore ouvert
            is_submission_open = (
                contest.submission_start_date <= today <= contest.submission_end_date
                and not is_voting_open  # Les soumissions sont fermées si le vote est ouvert
            )
            
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
        
        Returns:
            (is_allowed, error_message)
        """
        contest = db.query(Contest).filter(
            Contest.id == contest_id,
            Contest.is_deleted == False
        ).first()
        
        if not contest:
            return False, "Contest not found"
        
        # Vérifier si le contest est actif
        if not contest.is_active:
            return False, "This contest is not active"
        
        # Vérifier si les soumissions sont ouvertes
        if not contest.is_submission_open:
            return False, "Submissions are closed for this contest"
        
        # Vérifier si le voting est déjà ouvert (on ne peut plus soumettre si le vote est ouvert)
        if contest.is_voting_open:
            return False, "Submissions are closed because voting is already open"
        
        # Vérifier les dates
        today = date.today()
        if today < contest.submission_start_date:
            return False, f"Submissions will start on {contest.submission_start_date}"
        
        if today > contest.submission_end_date:
            return False, f"Submissions ended on {contest.submission_end_date}"
        
        return True, ""
    
    @staticmethod
    def check_voting_allowed(db: Session, contest_id: int) -> tuple[bool, str]:
        """
        Vérifie si le vote est autorisé pour un contest.
        
        Returns:
            (is_allowed, error_message)
        """
        contest = db.query(Contest).filter(
            Contest.id == contest_id,
            Contest.is_deleted == False
        ).first()
        
        if not contest:
            return False, "Contest not found"
        
        # Vérifier si le contest est actif
        if not contest.is_active:
            return False, "This contest is not active"
        
        # Vérifier si le vote est ouvert
        if not contest.is_voting_open:
            return False, "Voting is not open for this contest"
        
        # Vérifier les dates
        today = date.today()
        if today < contest.submission_end_date:
            return False, f"Voting will start after {contest.submission_end_date}"
        
        if today > contest.voting_end_date:
            return False, f"Voting ended on {contest.voting_end_date}"
        
        return True, ""


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

