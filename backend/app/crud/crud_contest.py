from typing import Any, Dict, List, Optional, Union
from datetime import datetime

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
        from app.models.contest import VerificationType, ParticipantType
        
        # Convertir location_id=0 en None pour éviter les violations de FK
        location_id = obj_in.location_id if obj_in.location_id and obj_in.location_id > 0 else None
        template_id = obj_in.template_id if obj_in.template_id and obj_in.template_id > 0 else None
        
        # Convertir les strings en enums si nécessaire
        verification_type = obj_in.verification_type
        if isinstance(verification_type, str):
            try:
                verification_type = VerificationType(verification_type)
            except ValueError:
                verification_type = VerificationType.NONE
        
        participant_type = obj_in.participant_type
        if isinstance(participant_type, str):
            try:
                participant_type = ParticipantType(participant_type)
            except ValueError:
                participant_type = ParticipantType.INDIVIDUAL
        
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
            template_id=template_id,
            # Verification requirements
            requires_kyc=obj_in.requires_kyc,
            verification_type=verification_type,
            participant_type=participant_type,
            requires_visual_verification=obj_in.requires_visual_verification,
            requires_voice_verification=obj_in.requires_voice_verification,
            requires_brand_verification=obj_in.requires_brand_verification,
            requires_content_verification=obj_in.requires_content_verification,
            min_age=obj_in.min_age,
            max_age=obj_in.max_age
        )
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj


    def update(self, db: Session, *, db_obj: Contest, obj_in: Union[ContestUpdate, Dict[str, Any]]) -> Contest:
        """Met à jour un concours existant"""
        from app.models.contest import VerificationType, ParticipantType
        
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
                # Convertir les strings en enums pour verification_type
                elif field == 'verification_type' and value is not None:
                    if isinstance(value, str):
                        try:
                            value = VerificationType(value)
                        except ValueError:
                            value = VerificationType.NONE
                # Convertir les strings en enums pour participant_type
                elif field == 'participant_type' and value is not None:
                    if isinstance(value, str):
                        try:
                            value = ParticipantType(value)
                        except ValueError:
                            value = ParticipantType.INDIVIDUAL
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
        from app.models.user import User
        
        # Compter le nombre de participants (contestants avec season_id = contest.id)
        # Utiliser distinct pour éviter les doublons et exclure les supprimés
        entries_count = db.query(func.count(Contestant.id.distinct()))\
            .filter(
                Contestant.season_id == contest.id,
                Contestant.is_deleted == False
            )\
            .scalar() or 0
        
        # Récupérer les top 5 contestants par votes
        top_contestants = []
        import logging
        import json
        logger = logging.getLogger(__name__)
        
        try:
            from app.models.media import Media
            
            # Récupérer les contestants avec leurs infos utilisateur (sans votes pour simplifier)
            contestants_with_user = db.query(
                Contestant,
                User
            ).join(
                User, Contestant.user_id == User.id
            ).filter(
                Contestant.season_id == contest.id,
                Contestant.is_deleted == False
            ).order_by(
                Contestant.created_at.desc()
            ).limit(5).all()
            
            logger.info(f"Found {len(contestants_with_user)} contestants for contest {contest.id}")
            
            for rank, (contestant, user) in enumerate(contestants_with_user, 1):
                # Extraire la première image du contestant depuis image_media_ids
                contestant_image_url = None
                logger.info(f"Processing contestant {contestant.id} - image_media_ids: {contestant.image_media_ids}")
                
                if contestant.image_media_ids:
                    try:
                        raw_value = contestant.image_media_ids.strip() if isinstance(contestant.image_media_ids, str) else contestant.image_media_ids
                        
                        # Cas 1: C'est déjà une URL directe (pas du JSON)
                        if isinstance(raw_value, str) and raw_value.startswith(('http://', 'https://')):
                            contestant_image_url = raw_value
                            logger.debug(f"image_media_ids is direct URL: {raw_value[:50]}")
                        # Cas 2: C'est du JSON
                        elif isinstance(raw_value, str) and (raw_value.startswith('[') or raw_value.startswith('{')):
                            image_ids = json.loads(raw_value)
                            if isinstance(image_ids, list) and len(image_ids) > 0:
                                first_image = image_ids[0]
                                logger.debug(f"First image from JSON: {first_image}")
                                
                                # Si c'est une URL directe
                                if isinstance(first_image, str) and first_image.startswith(('http://', 'https://')):
                                    contestant_image_url = first_image
                                # Si c'est un ID de média (int ou string numérique)
                                else:
                                    try:
                                        media_id = int(first_image) if isinstance(first_image, str) else first_image
                                        # Récupérer l'URL depuis la table Media
                                        media = db.query(Media).filter(Media.id == media_id).first()
                                        if media and media.url:
                                            contestant_image_url = media.url
                                            logger.debug(f"Got URL from Media table: {media.url[:50] if media.url else 'None'}")
                                        else:
                                            logger.warning(f"Media {media_id} not found in database")
                                    except (ValueError, TypeError) as ve:
                                        logger.warning(f"Error converting media_id: {ve}")
                        # Cas 3: C'est peut-être juste un ID
                        elif raw_value:
                            try:
                                media_id = int(raw_value)
                                media = db.query(Media).filter(Media.id == media_id).first()
                                if media and media.url:
                                    contestant_image_url = media.url
                            except (ValueError, TypeError):
                                pass
                    except (json.JSONDecodeError, TypeError) as e:
                        logger.warning(f"Error parsing image_media_ids for contestant {contestant.id}: {e}")
                
                logger.info(f"Contestant {contestant.id} - Final image_url: {contestant_image_url}")
                
                top_contestants.append({
                    "id": contestant.id,
                    "author_name": f"{user.first_name or ''} {user.last_name or ''}".strip() or user.username or "Anonyme",
                    "author_avatar_url": user.avatar_url,
                    "image_url": contestant_image_url,
                    "votes_count": 0,  # Simplified - no vote count for now
                    "rank": rank
                })
        except Exception as e:
            # En cas d'erreur, on continue sans les top contestants
            import traceback
            logger.error(f"Error fetching top contestants for contest {contest.id}: {e}")
            logger.error(traceback.format_exc())
        
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
        
        # Extraire les valeurs des enums de vérification
        verification_type_value = 'none'
        if hasattr(contest, 'verification_type') and contest.verification_type:
            if hasattr(contest.verification_type, 'value'):
                verification_type_value = contest.verification_type.value
            else:
                verification_type_value = str(contest.verification_type)
        
        participant_type_value = 'individual'
        if hasattr(contest, 'participant_type') and contest.participant_type:
            if hasattr(contest.participant_type, 'value'):
                participant_type_value = contest.participant_type.value
            else:
                participant_type_value = str(contest.participant_type)
        
        # Calculer dynamiquement is_submission_open basé sur les dates
        from datetime import date
        today = date.today()
        
        # is_submission_open est true seulement si:
        # 1. Le flag dans la DB est true (admin peut fermer manuellement)
        # 2. La date actuelle est >= submission_start_date (si définie)
        # 3. La date actuelle est <= submission_end_date (si définie)
        is_submission_open_calculated = contest.is_submission_open
        
        if is_submission_open_calculated:
            # Vérifier si la date de début est passée
            if contest.submission_start_date:
                start_date = contest.submission_start_date
                if isinstance(start_date, datetime):
                    start_date = start_date.date()
                if today < start_date:
                    is_submission_open_calculated = False
            
            # Vérifier si la date de fin est passée
            if contest.submission_end_date:
                end_date = contest.submission_end_date
                if isinstance(end_date, datetime):
                    end_date = end_date.date()
                if today > end_date:
                    is_submission_open_calculated = False
        
        # Calculer dynamiquement is_voting_open basé sur les dates
        is_voting_open_calculated = contest.is_voting_open
        
        if is_voting_open_calculated:
            if contest.voting_start_date:
                voting_start = contest.voting_start_date
                if isinstance(voting_start, datetime):
                    voting_start = voting_start.date()
                if today < voting_start:
                    is_voting_open_calculated = False
            
            if contest.voting_end_date:
                voting_end = contest.voting_end_date
                if isinstance(voting_end, datetime):
                    voting_end = voting_end.date()
                if today > voting_end:
                    is_voting_open_calculated = False
        
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
            "is_submission_open": is_submission_open_calculated,
            "is_voting_open": is_voting_open_calculated,
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
            # Verification requirements
            "requires_kyc": getattr(contest, 'requires_kyc', True),
            "verification_type": verification_type_value,
            "participant_type": participant_type_value,
            "requires_visual_verification": getattr(contest, 'requires_visual_verification', False),
            "requires_voice_verification": getattr(contest, 'requires_voice_verification', False),
            "requires_brand_verification": getattr(contest, 'requires_brand_verification', False),
            "requires_content_verification": getattr(contest, 'requires_content_verification', False),
            "min_age": getattr(contest, 'min_age', None),
            "max_age": getattr(contest, 'max_age', None),
            # Top contestants preview
            "top_contestants": top_contestants,
        }
        
        return result


contest = CRUDContest()
