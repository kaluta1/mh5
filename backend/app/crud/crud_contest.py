from typing import Any, Dict, List, Optional, Union
from datetime import datetime

from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func

from app.models.contest import Contest, ContestEntry, ContestVote
from app.models.contests import Contestant, ContestantRanking
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


    def get_contest_with_enriched_contestants(
        self, db: Session, contest_id: int, current_user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Récupère un contest avec tous ses contestants enrichis de toutes les informations :
        - Commentaires avec utilisateurs
        - Votes avec utilisateurs
        - Réactions avec utilisateurs
        - Favoris avec utilisateurs
        - Partages avec utilisateurs
        - Saison
        """
        from app.models.contests import ContestSeasonLink, ContestSeason
        from app.models.user import User
        from app.models.voting import (
            ContestComment, ContestantReaction, ContestantShare, 
            MyFavorites, ContestantVoting
        )
        from app.models.comment import Comment
        from sqlalchemy.orm import joinedload
        import json
        
        # Récupérer le contest
        contest_obj = self.get(db, id=contest_id)
        if not contest_obj:
            return None
        
        # Enrichir le contest avec les stats
        contest_data = self.enrich_contest_with_stats(db, contest_obj)
        
        # Récupérer tous les contestants du contest
        contestants = db.query(Contestant)\
            .filter(
                Contestant.season_id == contest_id,
                Contestant.is_deleted == False
            )\
            .options(
                joinedload(Contestant.user)
            )\
            .all()
        
        # Récupérer la saison active
        season = None
        season_link = db.query(ContestSeasonLink).filter(
            ContestSeasonLink.contest_id == contest_id,
            ContestSeasonLink.is_active == True
        ).first()
        
        if season_link:
            season = db.query(ContestSeason).filter(
                ContestSeason.id == season_link.season_id
            ).first()
        
        # Récupérer tous les IDs des contestants
        contestant_ids = [c.id for c in contestants]
        
        # Récupérer tous les votes avec utilisateurs (depuis ContestantVoting)
        # Filtrer par contest_id pour ne récupérer que les votes de ce contest
        votes_data = db.query(ContestantVoting, User)\
            .join(User, ContestantVoting.user_id == User.id)\
            .filter(
                ContestantVoting.contestant_id.in_(contestant_ids),
                ContestantVoting.contest_id == contest_id
            )\
            .all()
        
        # Grouper les votes par contestant_id
        votes_by_contestant = {}
        for voting, user in votes_data:
            if voting.contestant_id not in votes_by_contestant:
                votes_by_contestant[voting.contestant_id] = []
            votes_by_contestant[voting.contestant_id].append({
                "id": voting.id,  # ID du vote dans contestant_voting
                "user_id": user.id,
                "username": user.username,
                "full_name": user.full_name,
                "avatar_url": user.avatar_url,
                "points": 5,  # Par défaut, on peut ajuster si nécessaire
                "vote_date": voting.vote_date,
                "contest_id": voting.contest_id,  # ID du contest
                "season_id": voting.season_id  # ID de la saison
            })
        
        # Récupérer tous les commentaires avec utilisateurs
        comments_data = db.query(Comment, User)\
            .join(User, Comment.user_id == User.id)\
            .filter(
                Comment.contestant_id.in_(contestant_ids),
                Comment.is_hidden == False,
                Comment.is_deleted == False
            )\
            .order_by(Comment.created_at.desc())\
            .all()
        
        # Grouper les commentaires par contestant_id
        comments_by_contestant = {}
        for comment, user in comments_data:
            if comment.contestant_id not in comments_by_contestant:
                comments_by_contestant[comment.contestant_id] = []
            comments_by_contestant[comment.contestant_id].append({
                "id": comment.id,  # ID du commentaire
                "user_id": user.id,
                "username": user.username,
                "full_name": user.full_name,
                "avatar_url": user.avatar_url,
                "content": comment.content,
                "created_at": comment.created_at,
                "parent_id": comment.parent_id
            })
        
        # Récupérer toutes les réactions avec utilisateurs
        reactions_data = db.query(ContestantReaction, User)\
            .join(User, ContestantReaction.user_id == User.id)\
            .filter(ContestantReaction.contestant_id.in_(contestant_ids))\
            .all()
        
        # Grouper les réactions par contestant_id et type
        reactions_by_contestant = {}
        for reaction, user in reactions_data:
            if reaction.contestant_id not in reactions_by_contestant:
                reactions_by_contestant[reaction.contestant_id] = {}
            reaction_type = reaction.reaction_type
            if reaction_type not in reactions_by_contestant[reaction.contestant_id]:
                reactions_by_contestant[reaction.contestant_id][reaction_type] = []
            reactions_by_contestant[reaction.contestant_id][reaction_type].append({
                "id": reaction.id,  # ID de la réaction
                "user_id": user.id,
                "username": user.username,
                "full_name": user.full_name,
                "avatar_url": user.avatar_url,
                "reaction_type": reaction_type
            })
        
        # Récupérer tous les favoris avec utilisateurs
        favorites_data = db.query(MyFavorites, User)\
            .join(User, MyFavorites.user_id == User.id)\
            .filter(MyFavorites.contestant_id.in_(contestant_ids))\
            .all()
        
        # Grouper les favoris par contestant_id
        favorites_by_contestant = {}
        for favorite, user in favorites_data:
            if favorite.contestant_id not in favorites_by_contestant:
                favorites_by_contestant[favorite.contestant_id] = []
            favorites_by_contestant[favorite.contestant_id].append({
                "id": favorite.id,  # ID du favori
                "user_id": user.id,
                "username": user.username,
                "full_name": user.full_name,
                "avatar_url": user.avatar_url,
                "position": favorite.position,
                "added_date": favorite.added_date
            })
        
        # Récupérer tous les partages avec utilisateurs
        shares_data = db.query(ContestantShare, User)\
            .outerjoin(User, ContestantShare.user_id == User.id)\
            .filter(ContestantShare.contestant_id.in_(contestant_ids))\
            .all()
        
        # Grouper les partages par contestant_id
        shares_by_contestant = {}
        for share, user in shares_data:
            if share.contestant_id not in shares_by_contestant:
                shares_by_contestant[share.contestant_id] = []
            shares_by_contestant[share.contestant_id].append({
                "id": share.id,  # ID du partage
                "user_id": user.id if user else None,
                "username": user.username if user else None,
                "full_name": user.full_name if user else None,
                "avatar_url": user.avatar_url if user else None,
                "platform": share.platform,
                "share_link": share.share_link,
                "created_at": share.created_at
            })
        
        # Vérifier si l'auteur a ajouté chaque contestant en favoris
        author_favorites = {}
        if current_user_id:
            author_favs = db.query(MyFavorites.contestant_id)\
                .filter(
                    MyFavorites.user_id == current_user_id,
                    MyFavorites.contestant_id.in_(contestant_ids)
                )\
                .all()
            author_favorites = {fav[0] for fav in author_favs}
        
        # Vérifier les votes de l'utilisateur courant
        user_votes = {}
        if current_user_id:
            user_votes_list = db.query(ContestantVoting.contestant_id)\
                .filter(
                    ContestantVoting.user_id == current_user_id,
                    ContestantVoting.contestant_id.in_(contestant_ids)
                )\
                .all()
            user_votes = {vote[0] for vote in user_votes_list}
        
        # Compter les votes pour chaque contestant
        votes_count_by_contestant = {}
        for contestant_id in contestant_ids:
            votes_count_by_contestant[contestant_id] = len(votes_by_contestant.get(contestant_id, []))
        
        # Récupérer les rangs depuis contestant_rankings si disponibles, sinon calculer
        from app.models.contests import ContestantRanking
        
        # Récupérer les rangs depuis la base de données pour cette saison
        rankings_from_db = db.query(ContestantRanking)\
            .filter(
                ContestantRanking.contestant_id.in_(contestant_ids),
                ContestantRanking.stage_id == season.id
            )\
            .all()
        
        ranks = {}
        if rankings_from_db:
            # Utiliser les rangs de la base de données
            for ranking in rankings_from_db:
                if ranking.final_rank:
                    ranks[ranking.contestant_id] = ranking.final_rank
        else:
            # Calculer les rangs si pas disponibles en base
            ranked_contestants = sorted(
                [(cid, votes_count_by_contestant.get(cid, 0)) for cid in contestant_ids],
                key=lambda x: x[1],
                reverse=True
            )
            ranks = {cid: rank + 1 for rank, (cid, _) in enumerate(ranked_contestants)}
        
        # Construire la liste des contestants enrichis
        enriched_contestants = []
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
                can_vote = contestant.id not in user_votes
            
            enriched_contestants.append({
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
                "votes_count": votes_count_by_contestant.get(contestant.id, 0),
                "images_count": images_count,
                "videos_count": videos_count,
                "favorites_count": len(favorites_by_contestant.get(contestant.id, [])),
                "reactions_count": sum(len(reactions) for reactions in reactions_by_contestant.get(contestant.id, {}).values()),
                "comments_count": len(comments_by_contestant.get(contestant.id, [])),
                "shares_count": len(shares_by_contestant.get(contestant.id, [])),
                # Détails enrichis
                "comments": comments_by_contestant.get(contestant.id, []),
                "votes": votes_by_contestant.get(contestant.id, []),
                "reactions": reactions_by_contestant.get(contestant.id, {}),
                "favorites": favorites_by_contestant.get(contestant.id, []),
                "shares": shares_by_contestant.get(contestant.id, []),
                "is_in_favorites": contestant.id in author_favorites,
                # Saison
                "season": {
                    "id": season.id,
                    "title": season.title,
                    "level": season.level.value if hasattr(season.level, 'value') else str(season.level)
                } if season else None,
                # État du vote
                "has_voted": contestant.id in user_votes,
                "can_vote": can_vote,
            })
        
        # Trier par rangs (final_rank) si disponibles, sinon par votes décroissants
        # Les contestants avec le même rang sont triés par votes décroissants
        enriched_contestants.sort(key=lambda x: (
            x.get("rank", float('inf')),  # Utiliser le rang si disponible, sinon mettre à la fin
            -x["votes_count"]  # Ensuite par votes décroissants
        ))
        
        # Ajouter les contestants enrichis au résultat
        contest_data["contestants"] = enriched_contestants
        
        return contest_data

    def update_contestant_rankings(
        self, db: Session, contest_id: int, season_id: int
    ) -> None:
        """
        Met à jour les rangs de tous les contestants d'un contest pour une saison donnée.
        Le stage_id dans contestant_rankings sera l'id de la saison.
        """
        from app.models.voting import ContestantVoting
        
        # Récupérer tous les contestants du contest pour cette saison
        contestants = db.query(Contestant).filter(
            Contestant.season_id == season_id,
            Contestant.is_deleted == False
        ).all()
        
        # Compter les votes pour chaque contestant
        votes_by_contestant = {}
        for contestant in contestants:
            votes_count = db.query(func.count(ContestantVoting.id))\
                .filter(
                    ContestantVoting.contestant_id == contestant.id,
                    ContestantVoting.contest_id == contest_id
                )\
                .scalar() or 0
            votes_by_contestant[contestant.id] = votes_count
        
        # Trier les contestants par votes décroissants
        ranked_contestants = sorted(
            [(c.id, votes_by_contestant.get(c.id, 0)) for c in contestants],
            key=lambda x: x[1],
            reverse=True
        )
        
        # Créer ou mettre à jour les rangs
        for rank, (contestant_id, votes_count) in enumerate(ranked_contestants, start=1):
            # Chercher un rang existant pour ce contestant et cette saison
            ranking = db.query(ContestantRanking).filter(
                ContestantRanking.contestant_id == contestant_id,
                ContestantRanking.stage_id == season_id  # Utiliser season_id comme stage_id
            ).first()
            
            if ranking:
                # Mettre à jour le rang existant
                ranking.total_votes = votes_count
                ranking.final_rank = rank
                ranking.last_updated = datetime.utcnow()
            else:
                # Créer un nouveau rang
                ranking = ContestantRanking(
                    contestant_id=contestant_id,
                    stage_id=season_id,  # Utiliser season_id comme stage_id
                    total_votes=votes_count,
                    total_points=0,  # Pour l'instant, on ne gère que les votes
                    page_views=0,
                    likes=0,
                    final_rank=rank,
                    last_updated=datetime.utcnow()
                )
                db.add(ranking)
        
        db.commit()


contest = CRUDContest()
