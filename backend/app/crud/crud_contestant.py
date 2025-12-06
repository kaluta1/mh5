from typing import List, Optional, Dict, Any
from datetime import datetime
import json

from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, and_

from app.models.contests import Contestant, ContestSubmission, ContestSeason
from app.models.voting import Vote, MyFavorites, ContestLike, ContestComment


class CRUDContestant:
    """CRUD operations for Contestant model"""
    
    def get(self, db: Session, id: int) -> Optional[Contestant]:
        """Récupère une candidature par son ID"""
        return db.query(Contestant)\
            .filter(
                Contestant.id == id,
                Contestant.is_deleted == False
            )\
            .options(
                joinedload(Contestant.user),
                joinedload(Contestant.submissions)
            )\
            .first()
    
    def get_with_stats(
        self, db: Session, id: int, current_user_id: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """Récupère une candidature avec stats enrichies (votes, rang, infos auteur, infos contest)"""
        from app.models.voting import MyFavorites
        
        contestant = db.query(Contestant)\
            .filter(
                Contestant.id == id,
                Contestant.is_deleted == False
            )\
            .options(
                joinedload(Contestant.user),
                joinedload(Contestant.submissions)
            )\
            .first()
        
        if not contestant:
            return None
        
        # Compter les votes
        votes_count = db.query(func.count(Vote.id))\
            .filter(Vote.contestant_id == id)\
            .scalar() or 0
        
        # Compter les images et vidéos
        images_count = 0
        videos_count = 0
        if contestant.image_media_ids:
            try:
                images_count = len(json.loads(contestant.image_media_ids))
            except (json.JSONDecodeError, TypeError):
                images_count = 0
        if contestant.video_media_ids:
            try:
                videos_count = len(json.loads(contestant.video_media_ids))
            except (json.JSONDecodeError, TypeError):
                videos_count = 0
        
        # Calculer le rang en fonction des votes
        # Créer une sous-requête pour compter les votes par contestant de la même saison
        # Exclure les contestants supprimés du calcul du rang
        votes_per_contestant = db.query(
            Vote.contestant_id,
            func.count(Vote.id).label('vote_count')
        ).join(Contestant, Vote.contestant_id == Contestant.id)\
         .filter(
             Contestant.season_id == contestant.season_id,
             Contestant.is_deleted == False
         )\
         .group_by(Vote.contestant_id).subquery()
        
        # Compter combien de contestants ont plus de votes que le contestant actuel
        rank_count = db.query(func.count(votes_per_contestant.c.contestant_id))\
            .filter(votes_per_contestant.c.vote_count > votes_count)\
            .scalar() or 0
        
        rank = rank_count + 1
        
        # Vérifier si l'utilisateur a voté
        has_voted = False
        can_vote = False
        if current_user_id:
            has_voted = db.query(Vote).filter(
                and_(Vote.voter_id == current_user_id, Vote.contestant_id == id)
            ).first() is not None
            can_vote = current_user_id != contestant.user_id and not has_voted
        
        # Récupérer la position si c'est un favori de l'utilisateur courant
        position = None
        if current_user_id:
            favorite = db.query(MyFavorites).filter(
                MyFavorites.user_id == current_user_id,
                MyFavorites.contestant_id == id
            ).first()
            if favorite:
                position = favorite.position
        
        # Récupérer les infos du contest (saison)
        season = db.query(ContestSeason).filter(ContestSeason.id == contestant.season_id).first()
        contest_title = season.name if season else None
        
        # Compter le nombre total de participants pour cette saison
        total_participants = db.query(func.count(Contestant.id))\
            .filter(Contestant.season_id == contestant.season_id)\
            .scalar() or 0
        
        # Récupérer le continent de l'utilisateur
        author_continent = None
        if contestant.user and contestant.user.country:
            # Mapping simplifié pays -> continent
            continent_map = {
                'France': 'Europe', 'Germany': 'Europe', 'Italy': 'Europe', 'Spain': 'Europe',
                'USA': 'North America', 'Canada': 'North America', 'Mexico': 'North America',
                'Brazil': 'South America', 'Argentina': 'South America',
                'China': 'Asia', 'Japan': 'Asia', 'India': 'Asia', 'Thailand': 'Asia',
                'Australia': 'Oceania',
                'Egypt': 'Africa', 'Nigeria': 'Africa', 'South Africa': 'Africa',
            }
            author_continent = continent_map.get(contestant.user.country, 'Unknown')
        
        return {
            "id": contestant.id,
            "user_id": contestant.user_id,
            "season_id": contestant.season_id,
            "title": contestant.title,
            "description": contestant.description,
            "image_media_ids": contestant.image_media_ids,
            "video_media_ids": contestant.video_media_ids,
            "registration_date": contestant.registration_date,
            "is_qualified": contestant.is_qualified,
            # Infos auteur
            "author_name": contestant.user.full_name or f"{contestant.user.first_name or ''} {contestant.user.last_name or ''}".strip() if contestant.user else None,
            "author_country": contestant.user.country if contestant.user else None,
            "author_city": contestant.user.city if contestant.user else None,
            "author_continent": author_continent,
            "author_avatar_url": contestant.user.avatar_url if contestant.user else None,
            # Stats
            "rank": rank,
            "votes_count": votes_count,
            "images_count": images_count,
            "videos_count": videos_count,
            # Infos du contest
            "contest_title": contest_title,
            "contest_id": contestant.season_id,
            "total_participants": total_participants,
            # Position dans les favoris
            "position": position,
            # État du vote
            "has_voted": has_voted,
            "can_vote": can_vote,
        }
    
    def get_by_season_and_user(
        self, db: Session, season_id: int, user_id: int
    ) -> Optional[Contestant]:
        """Récupère la candidature d'un utilisateur pour une saison"""
        return db.query(Contestant)\
            .filter(
                and_(
                    Contestant.season_id == season_id,
                    Contestant.user_id == user_id,
                    Contestant.is_deleted == False
                )
            )\
            .first()
    
    def get_multi_by_season(
        self, db: Session, season_id: int, *, skip: int = 0, limit: int = 100
    ) -> List[Contestant]:
        """Récupère les candidatures d'une saison"""
        return db.query(Contestant)\
            .filter(Contestant.season_id == season_id)\
            .options(
                joinedload(Contestant.user),
                joinedload(Contestant.submissions)
            )\
            .order_by(Contestant.registration_date.desc())\
            .offset(skip)\
            .limit(limit)\
            .all()
    
    def get_multi_by_season_with_stats(
        self, db: Session, season_id: int, current_user_id: Optional[int] = None, 
        *, skip: int = 0, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Récupère les candidatures d'une saison avec stats enrichies (votes, rang, infos auteur).
        """
        # Récupérer tous les contestants de la saison avec leurs relations (exclure les supprimés)
        contestants = db.query(Contestant)\
            .filter(
                Contestant.season_id == season_id,
                Contestant.is_deleted == False
            )\
            .options(
                joinedload(Contestant.user),
                joinedload(Contestant.submissions)
            )\
            .order_by(Contestant.registration_date.desc())\
            .offset(skip)\
            .limit(limit)\
            .all()
        
        # Calculer les votes pour chaque contestant
        votes_by_contestant = {}
        for contestant in contestants:
            votes_count = db.query(func.count(Vote.id))\
                .filter(Vote.contestant_id == contestant.id)\
                .scalar() or 0
            votes_by_contestant[contestant.id] = votes_count
        
        # Calculer les rangs (trié par votes décroissants)
        ranked_contestants = sorted(
            [(c.id, votes_by_contestant[c.id]) for c in contestants],
            key=lambda x: x[1],
            reverse=True
        )
        ranks = {cid: rank + 1 for rank, (cid, _) in enumerate(ranked_contestants)}
        
        # Vérifier les votes de l'utilisateur courant
        user_votes = {}
        if current_user_id:
            user_votes_list = db.query(Vote.contestant_id)\
                .filter(Vote.voter_id == current_user_id, Vote.contestant_id.in_([c.id for c in contestants]))\
                .all()
            user_votes = {row[0] for row in user_votes_list}
        
        # Construire la réponse enrichie
        result = []
        for contestant in contestants:
            # Compter les images et vidéos
            images_count = 0
            videos_count = 0
            if contestant.image_media_ids:
                try:
                    images_count = len(json.loads(contestant.image_media_ids))
                except (json.JSONDecodeError, TypeError):
                    images_count = 0
            if contestant.video_media_ids:
                try:
                    videos_count = len(json.loads(contestant.video_media_ids))
                except (json.JSONDecodeError, TypeError):
                    videos_count = 0
            
            # Déterminer si l'utilisateur peut voter
            can_vote = False
            if current_user_id and current_user_id != contestant.user_id:
                # L'utilisateur n'est pas l'auteur et n'a pas déjà voté
                can_vote = contestant.id not in user_votes
            
            # Compter les favoris
            favorites_count = db.query(func.count(MyFavorites.id))\
                .filter(MyFavorites.contestant_id == contestant.id)\
                .scalar() or 0
            
            # Compter les réactions (likes)
            reactions_count = db.query(func.count(ContestLike.id))\
                .filter(ContestLike.contestant_id == contestant.id)\
                .scalar() or 0
            
            # Compter les commentaires
            comments_count = db.query(func.count(ContestComment.id))\
                .filter(ContestComment.contestant_id == contestant.id)\
                .scalar() or 0
            
            result.append({
                "id": contestant.id,
                "user_id": contestant.user_id,
                "season_id": contestant.season_id,
                "title": contestant.title,
                "description": contestant.description,
                "image_media_ids": contestant.image_media_ids,
                "video_media_ids": contestant.video_media_ids,
                "registration_date": contestant.registration_date,
                "is_qualified": contestant.is_qualified,
                # Infos auteur
                "author_name": contestant.user.full_name or f"{contestant.user.first_name or ''} {contestant.user.last_name or ''}".strip() if contestant.user else None,
                "author_country": contestant.user.country if contestant.user else None,
                "author_city": contestant.user.city if contestant.user else None,
                "author_avatar_url": contestant.user.avatar_url if contestant.user else None,
                # Stats
                "rank": ranks.get(contestant.id),
                "votes_count": votes_by_contestant.get(contestant.id, 0),
                "images_count": images_count,
                "videos_count": videos_count,
                "favorites_count": favorites_count,
                "reactions_count": reactions_count,
                "comments_count": comments_count,
                # État du vote
                "has_voted": contestant.id in user_votes,
                "can_vote": can_vote,
            })
        
        # Trier le résultat par votes décroissants (du plus élevé au plus bas)
        result.sort(key=lambda x: x["votes_count"], reverse=True)
        
        return result
    
    def get_multi_by_user(
        self, db: Session, user_id: int, *, skip: int = 0, limit: int = 100
    ) -> List[Contestant]:
        """Récupère les candidatures d'un utilisateur"""
        return db.query(Contestant)\
            .filter(
                Contestant.user_id == user_id,
                Contestant.is_deleted == False
            )\
            .options(
                joinedload(Contestant.seasons),
                joinedload(Contestant.submissions)
            )\
            .order_by(Contestant.registration_date.desc())\
            .offset(skip)\
            .limit(limit)\
            .all()
    
    def create(
        self, 
        db: Session, 
        *, 
        user_id: int, 
        season_id: int, 
        title: Optional[str] = None,
        description: Optional[str] = None,
        image_media_ids: Optional[str] = None,
        video_media_ids: Optional[str] = None
    ) -> Contestant:
        """Crée une nouvelle candidature"""
        # Vérifier qu'il n'existe pas déjà une candidature pour cet utilisateur
        existing = self.get_by_season_and_user(db, season_id, user_id)
        if existing:
            raise ValueError("L'utilisateur a déjà une candidature pour cette saison")
        
        # Créer la candidature
        db_obj = Contestant(
            user_id=user_id,
            season_id=season_id,
            title=title,
            description=description,
            image_media_ids=image_media_ids,
            video_media_ids=video_media_ids,
            registration_date=datetime.utcnow(),
            verification_status="pending",
            is_active=True
        )
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj
    
    def add_submission(
        self, db: Session, *, contestant_id: int, media_type: str, 
        file_url: Optional[str] = None, external_url: Optional[str] = None,
        title: Optional[str] = None, description: Optional[str] = None
    ) -> ContestSubmission:
        """Ajoute une soumission à une candidature"""
        submission = ContestSubmission(
            contestant_id=contestant_id,
            media_type=media_type,
            file_url=file_url,
            external_url=external_url,
            title=title,
            description=description,
            upload_date=datetime.utcnow(),
            is_approved=False,
            moderation_status="pending"
        )
        db.add(submission)
        db.commit()
        db.refresh(submission)
        return submission
    
    def approve_submission(self, db: Session, submission_id: int) -> ContestSubmission:
        """Approuve une soumission"""
        submission = db.query(ContestSubmission).filter(ContestSubmission.id == submission_id).first()
        if submission:
            submission.is_approved = True
            submission.moderation_status = "approved"
            db.add(submission)
            db.commit()
            db.refresh(submission)
        return submission
    
    def reject_submission(self, db: Session, submission_id: int) -> ContestSubmission:
        """Rejette une soumission"""
        submission = db.query(ContestSubmission).filter(ContestSubmission.id == submission_id).first()
        if submission:
            submission.is_approved = False
            submission.moderation_status = "rejected"
            db.add(submission)
            db.commit()
            db.refresh(submission)
        return submission
    
    def get_leaderboard(
        self, db: Session, season_id: int, *, skip: int = 0, limit: int = 100
    ) -> List[Contestant]:
        """Récupère le classement d'une saison"""
        return db.query(Contestant)\
            .filter(
                Contestant.season_id == season_id,
                Contestant.is_deleted == False
            )\
            .options(
                joinedload(Contestant.user),
                joinedload(Contestant.submissions),
                joinedload(Contestant.rankings)
            )\
            .order_by(Contestant.is_qualified.desc())\
            .offset(skip)\
            .limit(limit)\
            .all()
    
    def update(
        self,
        db: Session,
        *,
        id: int,
        title: Optional[str] = None,
        description: Optional[str] = None,
        image_media_ids: Optional[str] = None,
        video_media_ids: Optional[str] = None
    ) -> Optional[Contestant]:
        """Met à jour une candidature"""
        db_obj = db.query(Contestant).filter(Contestant.id == id).first()
        if not db_obj:
            return None
        
        # Mettre à jour les champs fournis
        if title is not None:
            db_obj.title = title
        if description is not None:
            db_obj.description = description
        if image_media_ids is not None:
            db_obj.image_media_ids = image_media_ids
        if video_media_ids is not None:
            db_obj.video_media_ids = video_media_ids
        
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj
    
    def delete(self, db: Session, *, id: int) -> bool:
        """Supprime une candidature (soft delete)"""
        db_obj = db.query(Contestant).filter(
            Contestant.id == id,
            Contestant.is_deleted == False
        ).first()
        if db_obj:
            db_obj.is_deleted = True
            db.commit()
            db.refresh(db_obj)
            return True
        return False


# Instance globale
crud_contestant = CRUDContestant()
