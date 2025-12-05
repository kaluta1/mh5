from typing import Any, Dict, List, Optional, Union

from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func

from app.models.contest import Contest, ContestEntry, ContestVote
from app.models.contests import Contestant
from app.schemas.contest import ContestCreate, ContestUpdate


class CRUDContest:
    def get(self, db: Session, id: int) -> Optional[Contest]:
        """Récupère un concours par son ID"""
        return db.query(Contest).filter(Contest.id == id, Contest.is_deleted == False).first()

    def get_with_entries(self, db: Session, id: int) -> Optional[Contest]:
        """Récupère un concours avec ses participants"""
        return db.query(Contest)\
            .filter(Contest.id == id, Contest.is_deleted == False)\
            .options(joinedload(Contest.entries).joinedload(ContestEntry.media))\
            .first()

    def get_multi(self, db: Session, *, skip: int = 0, limit: int = 100) -> List[Contest]:
        """Récupère une liste de concours"""
        return db.query(Contest).filter(Contest.is_deleted == False).offset(skip).limit(limit).all()

    def get_multi_with_filters(self,
        db: Session, *, skip: int = 0, limit: int = 100, filters: Dict[str, Any] = {}
    ) -> List[Contest]:
        """Récupère une liste de concours avec filtres"""
        query = db.query(Contest).filter(Contest.is_deleted == False)
        
        for field, value in filters.items():
            if hasattr(Contest, field):
                query = query.filter(getattr(Contest, field) == value)
        
        return query.offset(skip).limit(limit).all()

    def create(self, db: Session, *, obj_in: ContestCreate) -> Contest:
        """Crée un nouveau concours"""
        # Convertir location_id=0 en None pour éviter les violations de FK
        location_id = obj_in.location_id if obj_in.location_id and obj_in.location_id > 0 else None
        template_id = obj_in.template_id if obj_in.template_id and obj_in.template_id > 0 else None
        
        db_obj = Contest(
            name=obj_in.name,
            description=obj_in.description,
            contest_type=obj_in.contest_type,
            cover_image_url=obj_in.cover_image_url,
            submission_start_date=obj_in.submission_start_date,
            submission_end_date=obj_in.submission_end_date,
            voting_start_date=obj_in.voting_start_date,
            voting_end_date=obj_in.voting_end_date,
            is_active=obj_in.is_active,
            is_submission_open=obj_in.is_submission_open,
            is_voting_open=obj_in.is_voting_open,
            level=obj_in.level,
            location_id=location_id,
            gender_restriction=obj_in.gender_restriction,
            max_entries_per_user=obj_in.max_entries_per_user,
            template_id=template_id
        )
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj


    def update(self, db: Session, *, db_obj: Contest, obj_in: Union[ContestUpdate, Dict[str, Any]]) -> Contest:
        """Met à jour un concours existant"""
        if isinstance(obj_in, dict):
            update_data = obj_in
        else:
            update_data = obj_in.dict(exclude_unset=True)
        
        for field in update_data:
            if field in update_data:
                value = update_data[field]
                # Convertir les IDs 0 en None pour éviter les violations de FK
                if field in ('location_id', 'template_id') and value == 0:
                    value = None
                setattr(db_obj, field, value)
        
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def remove(self, db: Session, *, id: int) -> Contest:
        """Supprime un concours"""
        obj = db.query(Contest).get(id)
        db.delete(obj)
        db.commit()
        return obj


    def create_entry(self,
        db: Session, *, contest_id: int, media_id: int, user_id: int
    ) -> Dict[str, Any]:
        """
        Crée une participation à un concours
        Retourne un dict avec success=True/False et un message d'erreur éventuel
        """
        # Vérifier si l'utilisateur a déjà participé à ce concours
        existing_entry = db.query(ContestEntry).filter(
            ContestEntry.contest_id == contest_id,
            ContestEntry.user_id == user_id
        ).count()
        
        # Récupérer les informations du concours
        contest = self.get(db, id=contest_id)
        if not contest:
            return {"success": False, "error": "Concours non trouvé"}
        
        # Vérifier si le concours est ouvert aux inscriptions
        if not contest.is_submission_open:
            return {"success": False, "error": "Les inscriptions pour ce concours sont fermées"}
        
        # Vérifier le nombre maximum de participations par utilisateur
        if existing_entry >= contest.max_entries_per_user:
            return {"success": False, "error": f"Vous avez déjà atteint le nombre maximum de participations ({contest.max_entries_per_user})"}
        
        # Créer la participation
        entry = ContestEntry(
            contest_id=contest_id,
            media_id=media_id,
            user_id=user_id,
            total_score=0,
            rank=None
        )
        db.add(entry)
        db.commit()
        db.refresh(entry)
        
        return {"success": True, "entry_id": entry.id}

    def enrich_contest_with_stats(self, db: Session, contest: Contest) -> Dict[str, Any]:
        """Enrichit un contest avec les statistiques (nombre de participants et votes)"""
        from app.models.contests import ContestSeasonLink, ContestSeason
        
        # Compter le nombre de participants (contestants avec season_id = contest.id)
        # Utiliser distinct pour éviter les doublons et exclure les supprimés
        entries_count = db.query(func.count(Contestant.id.distinct()))\
            .filter(
                Contestant.season_id == contest.id,
                Contestant.is_deleted == False
            )\
            .scalar() or 0
        
        # Compter le nombre total de votes
        # Les votes peuvent venir de ContestVote ou être comptés via ContestEntry
        total_votes = db.query(func.count(ContestVote.id))\
            .join(ContestEntry, ContestVote.entry_id == ContestEntry.id)\
            .filter(ContestEntry.contest_id == contest.id)\
            .scalar() or 0
        
        # Si pas de votes via ContestVote, compter les ContestEntry comme votes
        if total_votes == 0:
            total_votes = db.query(func.count(ContestEntry.id))\
                .filter(ContestEntry.contest_id == contest.id)\
                .scalar() or 0
        
        # Récupérer le niveau depuis la season via ContestSeasonLink
        season_level = contest.level  # Par défaut, utiliser le niveau du contest
        season_link = db.query(ContestSeasonLink).filter(
            ContestSeasonLink.contest_id == contest.id,
            ContestSeasonLink.is_active == True
        ).first()
        
        if season_link:
            season = db.query(ContestSeason).filter(ContestSeason.id == season_link.season_id).first()
            if season:
                season_level = season.level.value if hasattr(season.level, 'value') else str(season.level)
        
        # Construire l'URL complète de l'image de couverture si elle existe
        # Priorité: image_url > cover_image_url
        cover_image_url = None
        image_to_use = contest.image_url or contest.cover_image_url
        
        if image_to_use:
            # Si c'est déjà une URL complète, l'utiliser telle quelle
            if image_to_use.startswith('http://') or image_to_use.startswith('https://'):
                cover_image_url = image_to_use
            # Si c'est un chemin relatif, construire l'URL complète
            elif image_to_use.startswith('/'):
                import os
                # Utiliser NEXT_PUBLIC_API_URL ou API_BASE_URL ou localhost par défaut
                api_base_url = os.getenv("NEXT_PUBLIC_API_URL") or os.getenv("API_BASE_URL") or "http://localhost:8000"
                cover_image_url = f"{api_base_url}{image_to_use}"
            else:
                # Sinon, utiliser tel quel (peut être un emoji ou autre)
                cover_image_url = image_to_use
        
        # Construire aussi l'URL complète pour image_url si elle existe
        image_url_processed = None
        if contest.image_url:
            if contest.image_url.startswith('http://') or contest.image_url.startswith('https://'):
                image_url_processed = contest.image_url
            elif contest.image_url.startswith('/'):
                import os
                api_base_url = os.getenv("NEXT_PUBLIC_API_URL") or os.getenv("API_BASE_URL") or "http://localhost:8000"
                image_url_processed = f"{api_base_url}{contest.image_url}"
            else:
                image_url_processed = contest.image_url
        
        # Extraire la restriction de genre depuis voting_restriction
        gender_restriction_from_voting = None
        voting_restriction_str = 'none'  # Valeur par défaut
        
        # Obtenir la valeur de l'enum depuis le Contest (toujours présent car c'est un champ non-nullable avec valeur par défaut)
        if hasattr(contest.voting_restriction, 'value'):
            voting_restriction_str = contest.voting_restriction.value
        elif isinstance(contest.voting_restriction, str):
            voting_restriction_str = contest.voting_restriction
        else:
            voting_restriction_str = str(contest.voting_restriction)
        
        # Si la restriction du Contest est NONE, essayer de récupérer depuis ContestType
        if voting_restriction_str == 'none' or not voting_restriction_str:
            from app.models.contests import ContestType
            # Essayer de trouver le ContestType par slug ou name
            contest_type_obj = db.query(ContestType).filter(
                (ContestType.slug == contest.contest_type) | (ContestType.name == contest.contest_type)
            ).first()
            
            if contest_type_obj and contest_type_obj.voting_restriction:
                if hasattr(contest_type_obj.voting_restriction, 'value'):
                    voting_restriction_str = contest_type_obj.voting_restriction.value
                elif isinstance(contest_type_obj.voting_restriction, str):
                    voting_restriction_str = contest_type_obj.voting_restriction
                else:
                    voting_restriction_str = str(contest_type_obj.voting_restriction)
        
        # Normaliser la valeur et extraire la restriction de genre
        voting_restriction_normalized = voting_restriction_str.lower().strip() if voting_restriction_str else None
        
        # Vérifier explicitement si ce n'est pas NONE
        if voting_restriction_normalized and voting_restriction_normalized != 'none':
            if voting_restriction_normalized == 'male_only':
                gender_restriction_from_voting = 'male'
            elif voting_restriction_normalized == 'female_only':
                gender_restriction_from_voting = 'female'
        
        # Utiliser gender_restriction si disponible, sinon utiliser voting_restriction
        final_gender_restriction = contest.gender_restriction or gender_restriction_from_voting
        
        result = {
            "id": contest.id,
            "name": contest.name,
            "description": contest.description,
            "contest_type": contest.contest_type,
            "cover_image_url": cover_image_url,
            "image_url": image_url_processed,  # Retourner aussi image_url traitée
            "submission_start_date": contest.submission_start_date,
            "submission_end_date": contest.submission_end_date,
            "voting_start_date": contest.voting_start_date,
            "voting_end_date": contest.voting_end_date,
            "is_active": contest.is_active,
            "is_submission_open": contest.is_submission_open,
            "is_voting_open": contest.is_voting_open,
            "level": contest.level,
            "season_level": season_level,  # Niveau depuis la season
            "location_id": contest.location_id,
            "gender_restriction": final_gender_restriction,
            "voting_restriction": voting_restriction_str,  # TOUJOURS retourner, même si 'none'
            "max_entries_per_user": contest.max_entries_per_user,
            "template_id": contest.template_id,
            "created_at": contest.created_at,
            "updated_at": contest.updated_at,
            "entries_count": entries_count,
            "total_votes": total_votes,
        }
        
        return result


contest = CRUDContest()
