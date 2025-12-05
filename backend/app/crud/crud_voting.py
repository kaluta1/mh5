from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc, func
from datetime import datetime

# from app.crud.base import CRUDBase
from app.models.voting import Vote, VoteSession, MyFavorites, ContestComment, ContestLike, PageView
from app.models.contests import Contestant, ContestStage
from app.models.user import User
from app.schemas.voting import (
    VoteCreate, VoteUpdate, VotingStatsCreate, VotingStatsUpdate,
    VoteRankingCreate, VoteRankingUpdate, VotingSessionCreate,
    StageLeaderboard, ContestantVotingProfile, VotingAnalytics, UserVotingHistory
)


class CRUDVote:
    def create_vote(
        self, 
        db: Session, 
        *, 
        obj_in: VoteCreate, 
        voter_id: int
    ) -> Vote:
        """Créer un nouveau vote"""
        db_obj = Vote(
            voter_id=voter_id,
            contestant_id=obj_in.contestant_id,
            stage_id=obj_in.stage_id,
            points=obj_in.points,
            vote_type=obj_in.vote_type,
            vote_date=datetime.utcnow(),
            is_valid=True
        )
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def get_user_vote_for_contestant(
        self, 
        db: Session, 
        *, 
        voter_id: int, 
        contestant_id: int, 
        stage_id: int
    ) -> Optional[Vote]:
        """Vérifier si un utilisateur a déjà voté pour un participant"""
        return db.query(Vote).filter(
            and_(
                Vote.voter_id == voter_id,
                Vote.contestant_id == contestant_id,
                Vote.stage_id == stage_id,
                Vote.is_valid == True
            )
        ).first()

    def get_user_votes_for_stage(
        self, 
        db: Session, 
        *, 
        user_id: int, 
        stage_id: int
    ) -> List[Vote]:
        """Récupérer tous les votes d'un utilisateur pour une étape"""
        return db.query(Vote).filter(
            and_(
                Vote.voter_id == user_id,
                Vote.stage_id == stage_id,
                Vote.is_valid == True
            )
        ).all()

    def check_voting_eligibility(
        self, 
        db: Session, 
        *, 
        user_id: int, 
        stage_id: int
    ) -> Dict[str, Any]:
        """Vérifier l'éligibilité de vote d'un utilisateur"""
        # Vérifier si l'étape permet encore les votes
        stage = db.query(ContestStage).filter(ContestStage.id == stage_id).first()
        if not stage:
            return {"can_vote": False, "reason": "Étape non trouvée"}
        
        now = datetime.utcnow()
        if now < stage.voting_start:
            return {"can_vote": False, "reason": "Le vote n'a pas encore commencé"}
        
        if now > stage.voting_end:
            return {"can_vote": False, "reason": "Le vote est terminé"}
        
        # Vérifier si l'utilisateur est participant dans cette étape
        is_contestant = db.query(Contestant).filter(
            and_(
                Contestant.user_id == user_id,
                Contestant.stage_id == stage_id,
                Contestant.is_active == True
            )
        ).first()
        
        if is_contestant:
            return {"can_vote": False, "reason": "Les participants ne peuvent pas voter dans leur propre étape"}
        
        return {"can_vote": True, "reason": "Éligible pour voter"}

    def update_vote(
        self, 
        db: Session, 
        *, 
        vote_id: int, 
        obj_in: VoteUpdate
    ) -> Optional[Vote]:
        """Mettre à jour un vote existant"""
        vote = db.query(Vote).filter(Vote.id == vote_id).first()
        if vote:
            for field, value in obj_in.dict(exclude_unset=True).items():
                setattr(vote, field, value)
            db.commit()
            db.refresh(vote)
        return vote

    def delete_vote(self, db: Session, *, vote_id: int) -> bool:
        """Supprimer un vote"""
        vote = db.query(Vote).filter(Vote.id == vote_id).first()
        if vote:
            vote.is_valid = False
            db.commit()
            return True
        return False

    def get_vote(self, db: Session, vote_id: int) -> Optional[Vote]:
        """Récupérer un vote par ID"""
        return db.query(Vote).filter(Vote.id == vote_id).first()


class CRUDVotingStats:
    def update_voting_stats(self, db: Session, *, contestant_id: int):
        """Mettre à jour les statistiques de vote d'un participant"""
        # Calculer les nouvelles statistiques
        votes = db.query(Vote).filter(
            and_(
                Vote.contestant_id == contestant_id,
                Vote.is_valid == True
            )
        ).all()
        
        total_votes = len(votes)
        total_points = sum(vote.points for vote in votes)
        
        # Compter les votes par points
        points_breakdown = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        for vote in votes:
            points_breakdown[vote.points] += 1
        
        average_rating = total_points / total_votes if total_votes > 0 else 0.0
        
        # Pour l'instant, retourner un dictionnaire avec les statistiques calculées
        # En attendant la création du modèle VotingStats approprié
        return {
            "contestant_id": contestant_id,
            "total_votes": total_votes,
            "total_points": total_points,
            "average_rating": average_rating,
            "last_updated": datetime.utcnow(),
            "points_5": points_breakdown[5],
            "points_4": points_breakdown[4],
            "points_3": points_breakdown[3],
            "points_2": points_breakdown[2],
            "points_1": points_breakdown[1]
        }

    def update_stage_rankings(self, db: Session, *, stage_id: int):
        """Mettre à jour le classement d'une étape"""
        # Fonction temporairement désactivée en attendant le modèle VotingStats
        pass

    def get_contestant_voting_stats(
        self, 
        db: Session, 
        *, 
        contestant_id: int
    ) -> Optional[Dict[str, Any]]:
        """Récupérer les statistiques de vote d'un participant"""
        # Retourner les statistiques calculées à la volée
        return self.update_voting_stats(db, contestant_id=contestant_id)


class CRUDVotingSession:
    def get_or_create_voting_session(
        self, 
        db: Session, 
        *, 
        user_id: int, 
        stage_id: int
    ) -> VoteSession:
        """Récupérer ou créer une session de vote"""
        session = db.query(VoteSession).filter(
            and_(
                VoteSession.voter_id == user_id,
                VoteSession.stage_id == stage_id
            )
        ).first()
        
        if not session:
            session = VoteSession(
                voter_id=user_id,
                stage_id=stage_id,
                votes_count=0,
                max_votes_reached=False,
                last_vote_date=datetime.utcnow()
            )
            db.add(session)
            db.commit()
            db.refresh(session)
        
        return session

    def end_voting_session(self, db: Session, *, session_id: int):
        """Terminer une session de vote"""
        session = db.query(VoteSession).filter(VoteSession.id == session_id).first()
        if session:
            session.max_votes_reached = True
            session.last_vote_date = datetime.utcnow()
            db.commit()


def get_stage_leaderboard(
    db: Session, 
    *, 
    stage_id: int, 
    skip: int = 0, 
    limit: int = 50
) -> StageLeaderboard:
    """Récupérer le classement complet d'une étape"""
    # Récupérer les informations de l'étape
    stage = db.query(ContestStage).filter(ContestStage.id == stage_id).first()
    if not stage:
        return None
    
    # Fonction temporairement simplifiée - retourner une liste vide
    return StageLeaderboard(
        stage_id=stage_id,
        total_contestants=0,
        rankings=[]
    )


def get_contestant_voting_profile(
    db: Session, 
    *, 
    contestant_id: int
) -> Optional[ContestantVotingProfile]:
    """Récupérer le profil de vote complet d'un participant"""
    # Récupérer le participant et ses informations
    contestant_data = db.query(Contestant, User).join(
        User, Contestant.user_id == User.id
    ).filter(Contestant.id == contestant_id).first()
    
    if not contestant_data:
        return None
    
    contestant, user = contestant_data
    
    # Calculer les statistiques à la volée (VotingStats n'existe pas encore)
    stats = None
    
    # Récupérer les votes récents
    recent_votes = db.query(Vote).filter(
        and_(
            Vote.contestant_id == contestant_id,
            Vote.is_valid == True
        )
    ).order_by(desc(Vote.vote_date)).limit(10).all()
    
    # Calculer la répartition des votes
    vote_breakdown = {str(i): 0 for i in range(1, 6)}
    if stats:
        vote_breakdown = {
            "5": stats.points_5,
            "4": stats.points_4,
            "3": stats.points_3,
            "2": stats.points_2,
            "1": stats.points_1
        }
    
    return ContestantVotingProfile(
        contestant_id=contestant_id,
        contestant_name=user.full_name or user.email,
        contestant_number=contestant.contestant_number,
        profile_picture_url=user.profile_picture_url,
        bio=contestant.bio,
        current_rank=stats.current_rank if stats else 0,
        total_votes=stats.total_votes if stats else 0,
        total_points=stats.total_points if stats else 0,
        average_rating=stats.average_rating if stats else 0.0,
        vote_breakdown=vote_breakdown,
        recent_votes=recent_votes
    )


def get_voting_analytics(db: Session, *, stage_id: int) -> VotingAnalytics:
    """Récupérer les analytiques de vote pour une étape"""
    # Statistiques générales
    total_votes = db.query(Vote).filter(
        and_(Vote.stage_id == stage_id, Vote.is_valid == True)
    ).count()
    
    unique_voters = db.query(Vote.voter_id).filter(
        and_(Vote.stage_id == stage_id, Vote.is_valid == True)
    ).distinct().count()
    
    total_contestants = db.query(Contestant).filter(
        and_(Contestant.stage_id == stage_id, Contestant.is_active == True)
    ).count()
    
    avg_votes_per_contestant = total_votes / total_contestants if total_contestants > 0 else 0
    
    # Distribution des votes par points
    vote_distribution = {}
    for points in range(1, 6):
        count = db.query(Vote).filter(
            and_(
                Vote.stage_id == stage_id,
                Vote.points == points,
                Vote.is_valid == True
            )
        ).count()
        vote_distribution[str(points)] = count
    
    return VotingAnalytics(
        stage_id=stage_id,
        total_votes=total_votes,
        unique_voters=unique_voters,
        average_votes_per_contestant=avg_votes_per_contestant,
        vote_distribution=vote_distribution,
        geographic_distribution={},  # À implémenter selon les besoins
        daily_vote_counts=[]  # À implémenter selon les besoins
    )


def get_user_voting_history(
    db: Session, 
    *, 
    user_id: int, 
    skip: int = 0, 
    limit: int = 20
) -> UserVotingHistory:
    """Récupérer l'historique de vote d'un utilisateur"""
    # Votes récents avec détails
    recent_votes_query = db.query(Vote, Contestant, User).join(
        Contestant, Vote.contestant_id == Contestant.id
    ).join(
        User, Contestant.user_id == User.id
    ).filter(
        and_(Vote.voter_id == user_id, Vote.is_valid == True)
    ).order_by(desc(Vote.vote_date))
    
    if skip:
        recent_votes_query = recent_votes_query.offset(skip)
    if limit:
        recent_votes_query = recent_votes_query.limit(limit)
    
    recent_votes_data = recent_votes_query.all()
    recent_votes = []
    
    for vote, contestant, user in recent_votes_data:
        recent_votes.append({
            "id": vote.id,
            "voter_id": vote.voter_id,
            "contestant_id": vote.contestant_id,
            "stage_id": vote.stage_id,
            "points": vote.points,
            "vote_type": vote.vote_type,
            "vote_date": vote.vote_date,
            "is_valid": vote.is_valid,
            "voter_name": None,  # L'utilisateur actuel
            "contestant_name": user.full_name or user.email,
            "stage_name": None  # À récupérer si nécessaire
        })
    
    # Statistiques générales
    total_votes = db.query(Vote).filter(
        and_(Vote.voter_id == user_id, Vote.is_valid == True)
    ).count()
    
    # Sessions de vote
    voting_sessions = db.query(VoteSession).filter(
        VoteSession.voter_id == user_id
    ).order_by(desc(VoteSession.last_vote_date)).limit(10).all()
    
    return UserVotingHistory(
        user_id=user_id,
        total_votes_cast=total_votes,
        favorite_contestants=[],  # À implémenter
        voting_patterns={},  # À implémenter
        recent_votes=recent_votes,
        voting_sessions=voting_sessions
    )


# Instances CRUD
vote = CRUDVote()
voting_stats = CRUDVotingStats()
voting_session = CRUDVotingSession()
