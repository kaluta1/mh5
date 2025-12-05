"""
Service pour gérer l'état des contests (submission/voting open/closed)
"""
from datetime import date, datetime
from sqlalchemy.orm import Session
from app.models.contest import Contest


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
            
            # Déterminer l'état de soumission
            # Soumission ouverte si aujourd'hui est entre submission_start_date et submission_end_date
            is_submission_open = (
                contest.submission_start_date <= today <= contest.submission_end_date
            )
            
            # Déterminer l'état de vote
            # Vote ouvert si aujourd'hui est >= submission_end_date ET <= voting_end_date
            is_voting_open = (
                contest.submission_end_date <= today <= contest.voting_end_date
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
            return False, "Concours non trouvé"
        
        # Vérifier si le contest est actif
        if not contest.is_active:
            return False, "Ce concours n'est pas actif"
        
        # Vérifier si les soumissions sont ouvertes
        if not contest.is_submission_open:
            return False, "Les inscriptions pour ce concours sont fermées"
        
        # Vérifier si le voting est déjà ouvert (on ne peut plus soumettre si le vote est ouvert)
        if contest.is_voting_open:
            return False, "Les inscriptions sont fermées car le vote est déjà ouvert"
        
        # Vérifier les dates
        today = date.today()
        if today < contest.submission_start_date:
            return False, f"Les inscriptions commenceront le {contest.submission_start_date}"
        
        if today > contest.submission_end_date:
            return False, f"Les inscriptions se sont terminées le {contest.submission_end_date}"
        
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
            return False, "Concours non trouvé"
        
        # Vérifier si le contest est actif
        if not contest.is_active:
            return False, "Ce concours n'est pas actif"
        
        # Vérifier si le vote est ouvert
        if not contest.is_voting_open:
            return False, "Le vote n'est pas ouvert pour ce concours"
        
        # Vérifier les dates
        today = date.today()
        if today < contest.submission_end_date:
            return False, f"Le vote commencera après le {contest.submission_end_date}"
        
        if today > contest.voting_end_date:
            return False, f"Le vote s'est terminé le {contest.voting_end_date}"
        
        return True, ""


# Instance du service
contest_status_service = ContestStatusService()

