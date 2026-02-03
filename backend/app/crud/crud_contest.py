from __future__ import annotations

from typing import Any, Dict, List, Optional, Union, TYPE_CHECKING
from datetime import datetime, date, timedelta

from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, or_

from app.models.contest import Contest, ContestEntry, ContestVote
from app.models.contests import Contestant, ContestantRanking
from app.schemas.contest import ContestCreate, ContestUpdate

if TYPE_CHECKING:
    from app.models.user import User



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

    def get_multi(self, db: Session, *, skip: int = 0, limit: int = 10) -> List[Contest]:
        """Récupère une liste de concours"""
        return db.query(Contest).filter(Contest.is_deleted == False).offset(skip).limit(limit).all()

    def get_multi_with_filters(self,
        db: Session, *, skip: int = 0, limit: int = 10, filters: Dict[str, Any] = {}
    ) -> List[Contest]:
        """Récupère une liste de concours avec filtres"""
        # Note: On ne fait plus de joinedload sur voting_type ici car la table peut ne pas exister
        # Le voting_type est chargé séparément dans enrich_contest_with_stats si nécessaire
        
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            # FIXED: Try to filter by is_deleted, but handle if column doesn't exist
            try:
                query = db.query(Contest).filter(Contest.is_deleted == False)
            except Exception as col_error:
                # If is_deleted column doesn't exist, query without it
                logger.warning(f"Could not filter by is_deleted, column may not exist: {str(col_error)}")
                query = db.query(Contest)
        except Exception as e:
            logger.error(f"Error creating base query: {str(e)}", exc_info=True)
            raise
        
        # Gérer la recherche textuelle sur plusieurs champs
        if "search" in filters and filters["search"]:
            search_term = f"%{filters['search']}%"
            query = query.filter(
                or_(
                    Contest.name.ilike(search_term),
                    Contest.description.ilike(search_term),
                    Contest.level.ilike(search_term),
                    Contest.contest_type.ilike(search_term)
                )
            )
        
        # Gérer le filtre par voting_level
        # Note: On vérifie d'abord si la table voting_type existe avant de faire des joins
        if "voting_level" in filters and filters["voting_level"]:
            try:
                from app.models.contest import VotingType
                from sqlalchemy import inspect as sa_inspect
                
                # Vérifier si la table voting_type existe
                insp = sa_inspect(db.bind)
                if 'voting_type' in insp.get_table_names():
                    # Pour "country", on veut seulement les contests avec voting_type et voting_level = "country"
                    if filters["voting_level"].lower() == "country":
                        query = query.join(VotingType, Contest.voting_type_id == VotingType.id)\
                            .filter(VotingType.voting_level == filters["voting_level"])
                    else:
                        # Pour les autres cas, utiliser outerjoin
                        query = query.outerjoin(VotingType, Contest.voting_type_id == VotingType.id)\
                            .filter(
                                or_(
                                    VotingType.voting_level == filters["voting_level"],
                                    Contest.voting_type_id.is_(None)
                                )
                            )
                # Si la table n'existe pas, on ignore ce filtre
            except Exception:
                # En cas d'erreur, on ignore ce filtre
                pass
        
        # Gérer le filtre par voting_type_id (pour filtrer les contests avec un voting_type)
        if "voting_type_id" in filters:
            voting_type_id_value = filters["voting_type_id"]
            if voting_type_id_value is not None:
                # Si voting_type_id est fourni, filtrer par cet ID
                query = query.filter(Contest.voting_type_id == voting_type_id_value)
            # Si voting_type_id est explicitement None ou une valeur spéciale, on peut filtrer les contests sans voting_type
        
        # Gérer le filtre has_voting_type (pour filtrer les contests avec/sans voting_type)
        if "has_voting_type" in filters:
            has_voting_type_value = filters["has_voting_type"]
            if has_voting_type_value is True:
                # Filtrer les contests qui ont un voting_type_id (non null)
                query = query.filter(Contest.voting_type_id.isnot(None))
            elif has_voting_type_value is False:
                # Filtrer les contests qui n'ont pas de voting_type_id (null)
                query = query.filter(Contest.voting_type_id.is_(None))
        
        # Gérer les autres filtres
        for field, value in filters.items():
            if field in ["search", "voting_level", "voting_type_id", "has_voting_type"]:
                continue  # Déjà traité ci-dessus
            try:
                if hasattr(Contest, field) and value is not None:
                    query = query.filter(getattr(Contest, field) == value)
            except Exception as e:
                logger.warning(f"Error applying filter {field}={value}: {str(e)}")
                # Continue with other filters
        
        # FIXED: Increase default limit if not specified to get all active contests
        # This ensures we don't miss contests due to low limits
        effective_limit = limit if limit > 0 else 1000
        
        # FIXED: Defer date columns that don't exist in database to avoid SQL errors
        from sqlalchemy.orm import defer
        try:
            # Add defer options to exclude date columns that may not exist
            query = query.options(
                defer(Contest.submission_start_date),
                defer(Contest.submission_end_date),
                defer(Contest.voting_start_date),
                defer(Contest.voting_end_date),
                defer(Contest.city_season_start_date),
                defer(Contest.city_season_end_date),
                defer(Contest.country_season_start_date),
                defer(Contest.country_season_end_date),
                defer(Contest.regional_start_date),
                defer(Contest.regional_end_date),
                defer(Contest.continental_start_date),
                defer(Contest.continental_end_date),
                defer(Contest.global_start_date),
                defer(Contest.global_end_date),
            )
        except Exception as defer_error:
            logger.warning(f"Could not add defer options: {defer_error}")
            # Continue without defer - may fail if columns don't exist
        
        try:
            logger.info(f"Executing query with skip={skip}, limit={effective_limit}")
            results = query.offset(skip).limit(effective_limit).all()
            logger.info(f"Query returned {len(results)} contests")
            return results
        except Exception as e:
            logger.error(f"Error executing contest query: {str(e)}", exc_info=True)
            raise

    def create(self, db: Session, *, obj_in: ContestCreate) -> Contest:
        """Crée un nouveau concours"""
        from app.models.contest import VerificationType, ParticipantType
        
        # S'assurer que le nom commence par "High5"
        contest_name = obj_in.name.strip()
        if not contest_name.startswith("High5"):
            contest_name = f"High5 {contest_name}"
        
        # Convertir location_id=0 en None pour éviter les violations de FK
        location_id = obj_in.location_id if obj_in.location_id and obj_in.location_id > 0 else None
        template_id = obj_in.template_id if obj_in.template_id and obj_in.template_id > 0 else None
        voting_type_id = obj_in.voting_type_id if obj_in.voting_type_id and obj_in.voting_type_id > 0 else None
        category_id = obj_in.category_id if obj_in.category_id and obj_in.category_id > 0 else None
        
        # Si category_id est fourni, récupération de la catégorie (inchangé)
        contest_type = obj_in.contest_type
        if category_id:
            from app.models.category import Category
            category = db.query(Category).filter(Category.id == category_id).first()
            if category:
                contest_type = category.slug
        
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
            name=contest_name,
            description=obj_in.description,
            contest_type=contest_type,
            cover_image_url=obj_in.cover_image_url,
            # Les dates sont maintenant gérées par les Rounds
            # On conserve les indicateurs d'état
            is_active=obj_in.is_active,
            is_submission_open=obj_in.is_submission_open,
            is_voting_open=obj_in.is_voting_open,
            level=obj_in.level,
            location_id=location_id,
            gender_restriction=obj_in.gender_restriction,
            max_entries_per_user=obj_in.max_entries_per_user,
            template_id=template_id,
            voting_type_id=voting_type_id,
            category_id=category_id,
            # Verification requirements
            # Verification requirements
            requires_kyc=obj_in.requires_kyc,
            verification_type=verification_type,
            participant_type=participant_type,
            requires_visual_verification=obj_in.requires_visual_verification,
            requires_voice_verification=obj_in.requires_voice_verification,
            requires_brand_verification=obj_in.requires_brand_verification,
            requires_content_verification=obj_in.requires_content_verification,
            min_age=obj_in.min_age,
            max_age=obj_in.max_age,
            
            # Dates mandataires pour la BD (Not Null constraints)
            # On initialise avec les dates du mois courant par défaut
            submission_start_date=date(date.today().year, date.today().month, 1),
            submission_end_date=date(date.today().year, date.today().month, 28), # simplified
            voting_start_date=date(date.today().year, date.today().month, 1) + timedelta(days=30), # next month
            voting_end_date=date(date.today().year, date.today().month, 1) + timedelta(days=60), # next 2 months
        )
        
        # Calculate better dates if possible using logic similar to rounds
        try:
            from app.crud.crud_round import round as crud_round
            now = date.today()
            computed_dates = crud_round.calculate_dates_for_month(now.month, now.year, is_nomination=bool(voting_type_id))
            db_obj.submission_start_date = computed_dates["submission_start_date"]
            db_obj.submission_end_date = computed_dates["submission_end_date"]
            db_obj.voting_start_date = computed_dates["voting_start_date"]
            db_obj.voting_end_date = computed_dates["voting_end_date"]
            # Populate season dates if needed
            db_obj.city_season_start_date = computed_dates["city_season_start_date"]
            db_obj.city_season_end_date = computed_dates["city_season_end_date"]
            db_obj.country_season_start_date = computed_dates["country_season_start_date"]
            db_obj.country_season_end_date = computed_dates["country_season_end_date"]
            db_obj.regional_start_date = computed_dates["regional_start_date"]
            db_obj.regional_end_date = computed_dates["regional_end_date"]
            db_obj.continental_start_date = computed_dates["continental_start_date"]
            db_obj.continental_end_date = computed_dates["continental_end_date"]
            db_obj.global_start_date = computed_dates["global_start_date"]
            db_obj.global_end_date = computed_dates["global_end_date"]
        except Exception as e:
            # Fallback already set in constructor
            pass
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        
        # --- AUTOMATION: Link to Active Round ---
        # --- AUTOMATION: Link to Active Round ---
        # Note: We purposely don't wrap this in a broad try/except that swallows errors
        # so we can debug why linking fails.
        try:
            # 1. Determine current month round name
            import calendar
            from sqlalchemy import insert
            from app.models.round import Round, RoundStatus, round_contests
    
            now = date.today()
            month_name = calendar.month_name[now.month]
            round_name = f"Round {month_name} {now.year}"
            
            # 2. Find existing round
            # Priority 1: Match Name (e.g. "Round January 2026")
            active_round = db.query(Round).filter(
                Round.name == round_name
            ).first()
            
            if not active_round:
                # Priority 2: Match Active Date Coverage
                active_round = db.query(Round).filter(
                    Round.submission_start_date <= now,
                    Round.submission_end_date >= now,
                    Round.status != RoundStatus.CANCELLED
                ).first()
                
            if not active_round:
                # Priority 3: Fallback to LAST created round (User Request)
                active_round = db.query(Round).filter(
                    Round.status != RoundStatus.CANCELLED
                ).order_by(Round.id.desc()).first()
                
            # 3. Link Contest to Round
            if active_round:
                # Check if link exists
                link_exists = db.query(round_contests).filter(
                    round_contests.c.round_id == active_round.id,
                    round_contests.c.contest_id == db_obj.id
                ).first()
                
                if not link_exists:
                    stmt = insert(round_contests).values(
                        round_id=active_round.id,
                        contest_id=db_obj.id,
                        created_at=datetime.utcnow()
                    )
                    db.execute(stmt)
                    db.commit()
                 
        except Exception as e:
            print(f"ERROR in auto-link logic: {e}")
            import traceback
            traceback.print_exc()
        
        return db_obj


    def update(self, db: Session, *, db_obj: Contest, obj_in: Union[ContestUpdate, Dict[str, Any]]) -> Contest:
        """Met à jour un concours existant"""
        from app.models.contest import VerificationType, ParticipantType
        
        if isinstance(obj_in, dict):
            update_data = obj_in.copy()
        else:
            if hasattr(obj_in, 'model_dump'):
                update_data = obj_in.model_dump(exclude_unset=True)
            else:
                update_data = obj_in.dict(exclude_unset=True)
            
            if hasattr(obj_in, 'category_id'):
                category_id_value = getattr(obj_in, 'category_id', None)
                update_data['category_id'] = category_id_value
        
        # Date fields are now supported in the model, so we don't remove them.
        # But we ensures they are not None if they are required (though update handles partials)
        pass
        
        for field in update_data:
            if field in update_data:
                value = update_data[field]
                
                # S'assurer que le nom commence par "High5"
                if field == 'name' and value is not None:
                    value = str(value).strip()
                    if not value.startswith("High5"):
                        value = f"High5 {value}"
                
                # Convertir les IDs 0 en None
                elif field in ('location_id', 'template_id', 'voting_type_id', 'category_id') and value == 0:
                    value = None
                    
                # Si category_id est fourni
                elif field == 'category_id':
                    if value is not None and value != 0:
                        from app.models.category import Category
                        category = db.query(Category).filter(Category.id == value).first()
                        if category:
                            update_data['contest_type'] = category.slug
                
                # Enums
                elif field == 'verification_type' and value is not None:
                    if isinstance(value, str):
                        try:
                            value = VerificationType(value)
                        except ValueError:
                            value = VerificationType.NONE
                            
                elif field == 'participant_type' and value is not None:
                    if isinstance(value, str):
                        try:
                            value = ParticipantType(value)
                        except ValueError:
                            value = ParticipantType.INDIVIDUAL
                
                if hasattr(db_obj, field):
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

    def enrich_contest_with_stats(
        self, db: Session, contest: Contest, current_user: Optional['User'] = None,
        filter_country: Optional[str] = None,
        filter_region: Optional[str] = None,
        filter_continent: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Enrichit un contest avec les statistiques (nombre de participants et votes).
        
        Paramètres de filtrage géographique:
        - filter_country: Si fourni, compte les contestants de ce pays
        - filter_region: Si fourni, compte les contestants de cette région
        - filter_continent: Si fourni, compte les contestants de ce continent
        - Par défaut (aucun filtre), utilise la localisation de l'utilisateur connecté
        """
        import logging
        logger = logging.getLogger(__name__)

        from app.models.contests import ContestSeasonLink, ContestSeason, SeasonLevel
        from app.models.user import User
        
        # Récupérer la saison active du contest via ContestSeasonLink
        season_level = None
        season_link = db.query(ContestSeasonLink).filter(
            ContestSeasonLink.contest_id == contest.id,
            ContestSeasonLink.is_active == True
        ).first()
        
        if season_link:
            season = db.query(ContestSeason).filter(
                ContestSeason.id == season_link.season_id,
                ContestSeason.is_deleted == False
            ).first()
            if season:
                season_level = season.level.value if hasattr(season.level, 'value') else str(season.level)
        
        # Si pas de saison trouvée, utiliser le niveau du contest par défaut
        if not season_level:
            season_level = contest.level.lower() if contest.level else None
        
        # FIXED: Query contestants by both round_id and season_id
        from app.models.round import Round, round_contests
        
        # Find round IDs linked to this contest
        round_ids = []
        try:
            from sqlalchemy import select
            round_ids_via_table = db.execute(
                select(round_contests.c.round_id).where(
                    round_contests.c.contest_id == contest.id
                )
            ).fetchall()
            if round_ids_via_table:
                round_ids.extend([r[0] for r in round_ids_via_table])
                logger.debug(f"Contest {contest.id} linked to rounds via table: {round_ids}")
        except Exception as e:
            logger.warning(f"Error querying round_contests for contest {contest.id}: {e}")
            pass
        
        try:
            legacy_rounds = db.query(Round.id).filter(Round.contest_id == contest.id).all()
            if legacy_rounds:
                legacy_ids = [r[0] for r in legacy_rounds]
                round_ids.extend(legacy_ids)
                logger.debug(f"Contest {contest.id} linked to rounds via legacy: {legacy_ids}")
        except Exception as e:
            logger.warning(f"Error querying legacy rounds for contest {contest.id}: {e}")
            pass
        
        round_ids = list(set(round_ids))
        if round_ids:
            logger.debug(f"Contest {contest.id} has {len(round_ids)} linked rounds: {round_ids}")
        else:
            logger.debug(f"Contest {contest.id} has no linked rounds")
        
        # Build query with OR conditions for round_id and season_id
        from sqlalchemy import or_
        conditions = []
        
        # Always include season_id condition (legacy support)
        conditions.append(Contestant.season_id == contest.id)
        
        # Add round_id condition if rounds are linked
        if round_ids:
            conditions.append(Contestant.round_id.in_(round_ids))
        
        # FIXED: If no rounds linked, still show the contest (it will have 0 contestants until rounds are created)
        # This ensures contests are visible even before rounds are set up
        
        # FIXED: Always count ALL contestants for the contest first (without location filters)
        # This ensures the count is accurate even when no user is logged in
        if conditions:
            base_entries_query = db.query(func.count(Contestant.id.distinct()))\
                .filter(
                    Contestant.is_deleted == False,
                    or_(*conditions) if len(conditions) > 1 else conditions[0]
                )
        else:
            # No conditions - return 0 (contest has no rounds or seasons linked yet)
            base_entries_query = db.query(func.count(Contestant.id.distinct()))\
                .filter(Contestant.id == -1)  # Impossible condition = 0 results
        
        # Get total count without location filters (for display purposes)
        total_entries_count = base_entries_query.scalar() or 0
        
        # Compter le nombre de participants selon la saison/round et la localisation
        if conditions:
            entries_query = db.query(func.count(Contestant.id.distinct()))\
                .filter(
                    Contestant.is_deleted == False,
                    or_(*conditions) if len(conditions) > 1 else conditions[0]
                )
        else:
            # No conditions - return 0
            entries_query = db.query(func.count(Contestant.id.distinct()))\
                .filter(Contestant.id == -1)  # Impossible condition = 0 results
        
        # Appliquer les filtres géographiques
        # Priorité: filtres explicites > localisation de l'utilisateur
        has_location_filter = filter_country or filter_region or filter_continent
        applied_location_filter = False
        
        if has_location_filter:
            # Utiliser les filtres fournis par l'utilisateur
            applied_location_filter = True
            if filter_country:
                entries_query = entries_query.filter(
                    func.lower(Contestant.country) == func.lower(filter_country)
                )
            if filter_region:
                entries_query = entries_query.filter(
                    func.lower(Contestant.region) == func.lower(filter_region)
                )
            if filter_continent:
                entries_query = entries_query.filter(
                    func.lower(Contestant.continent) == func.lower(filter_continent)
                )
        elif current_user and season_level:
            # Filtrer par localisation selon le niveau de la saison et l'utilisateur connecté
            season_level_lower = season_level.lower()
            
            if season_level_lower == "city":
                # Filtrer par ville et pays
                if current_user.city and current_user.country:
                    entries_query = entries_query.filter(
                        Contestant.city == current_user.city,
                        Contestant.country == current_user.country
                    )
                    applied_location_filter = True
            elif season_level_lower == "country":
                # Filtrer par pays
                if current_user.country:
                    entries_query = entries_query.filter(
                        Contestant.country == current_user.country
                    )
                    applied_location_filter = True
            elif season_level_lower in ("regional", "region"):
                # Filtrer par région
                if current_user.region:
                    entries_query = entries_query.filter(
                        Contestant.region == current_user.region
                    )
                    applied_location_filter = True
            elif season_level_lower == "continent":
                # Filtrer par continent
                if current_user.continent:
                    entries_query = entries_query.filter(
                        Contestant.continent == current_user.continent
                    )
                    applied_location_filter = True
            # Pour "global", pas de filtre géographique
        
        # Use total count if no location filters were applied, otherwise use filtered count
        # IMPORTANT: For public display (no user logged in), always show total count
        if not applied_location_filter:
            entries_count = total_entries_count
        else:
            entries_count = entries_query.scalar() or 0
        
        # Vérifier si l'utilisateur connecté participe à ce concours
        current_user_contesting = False
        if current_user:
            try:
                user_conditions = [Contestant.season_id == contest.id]
                if round_ids:
                    user_conditions.append(Contestant.round_id.in_(round_ids))
                
                user_contestant = db.query(Contestant).filter(
                    Contestant.is_deleted == False,
                    Contestant.user_id == current_user.id,
                    or_(*user_conditions) if len(user_conditions) > 1 else user_conditions[0]
                ).first()
                current_user_contesting = user_contestant is not None
            except Exception:
                # Fallback to season_id only
                user_contestant = db.query(Contestant).filter(
                    Contestant.season_id == contest.id,
                    Contestant.user_id == current_user.id,
                    Contestant.is_deleted == False
                ).first()
                current_user_contesting = user_contestant is not None
        
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
        
        # Charger l'objet voting_type si voting_type_id existe
        voting_type_data = None
        if contest.voting_type_id:
            try:
                from app.models.contest import VotingType
                from sqlalchemy import inspect as sa_inspect
                
                # Vérifier si la table voting_type existe
                insp = sa_inspect(db.bind)
                if 'voting_type' in insp.get_table_names():
                    voting_type = db.query(VotingType).filter(VotingType.id == contest.voting_type_id).first()
                    if voting_type:
                        voting_type_data = {
                            "id": voting_type.id,
                            "name": voting_type.name,
                            "voting_level": voting_type.voting_level.value if hasattr(voting_type.voting_level, 'value') else str(voting_type.voting_level),
                            "commission_source": voting_type.commission_source.value if hasattr(voting_type.commission_source, 'value') else str(voting_type.commission_source),
                            "commission_rules": voting_type.commission_rules,
                            "created_at": voting_type.created_at,
                            "updated_at": voting_type.updated_at
                        }
            except Exception:
                # Si la table n'existe pas ou erreur, on laisse voting_type_data à None
                pass
        
        # Charger l'objet category si category_id existe
        category_data = None
        category_id_value = getattr(contest, 'category_id', None)
        if category_id_value:
            try:
                from app.models.category import Category
                category = db.query(Category).filter(Category.id == category_id_value).first()
                if category:
                    category_data = {
                        "id": category.id,
                        "name": category.name,
                        "slug": category.slug,
                        "description": category.description,
                        "is_active": category.is_active
                    }
            except Exception as e:
                # En cas d'erreur, on laisse category_data à None
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"Error loading category {category_id_value} for contest {contest.id}: {e}")
                pass
        
        # Calculer dynamiquement is_submission_open basé sur les dates
        from datetime import date
        today = date.today()
        
        # Récupérer le round actif pour obtenir les dates
        from app.crud import crud_round
        active_round = crud_round.round.get_active_round_for_contest(db, contest_id=contest.id)
        
        submission_start_date = active_round.submission_start_date if active_round else None
        submission_end_date = active_round.submission_end_date if active_round else None
        voting_start_date = active_round.voting_start_date if active_round else None
        voting_end_date = active_round.voting_end_date if active_round else None

        # is_submission_open est true seulement si:
        # 1. Le flag dans la DB est true (admin peut fermer manuellement)
        # 2. La date actuelle est >= submission_start_date (si définie)
        # 3. La date actuelle est <= submission_end_date (si définie)
        is_submission_open_calculated = contest.is_submission_open
        
        if is_submission_open_calculated:
            # Vérifier si la date de début est passée
            if submission_start_date:
                start_date = submission_start_date
                if isinstance(start_date, datetime):
                    start_date = start_date.date()
                if today < start_date:
                    is_submission_open_calculated = False
            
            # Vérifier si la date de fin est passée
            if submission_end_date:
                end_date = submission_end_date
                if isinstance(end_date, datetime):
                    end_date = end_date.date()
                if today > end_date:
                    is_submission_open_calculated = False
        
        # Calculer dynamiquement is_voting_open basé sur les dates
        is_voting_open_calculated = contest.is_voting_open
        
        if is_voting_open_calculated:
            if voting_start_date:
                voting_start = voting_start_date
                if isinstance(voting_start, datetime):
                    voting_start = voting_start.date()
                if today < voting_start:
                    is_voting_open_calculated = False
            
            if voting_end_date:
                voting_end = voting_end_date
                if isinstance(voting_end, datetime):
                    voting_end = voting_end.date()
                if today > voting_end:
                    is_voting_open_calculated = False
        
        # Convertir level en string (peut être un enum)
        level_value = contest.level
        if hasattr(level_value, 'value'):
            level_value = level_value.value
        elif level_value is not None and not isinstance(level_value, str):
            level_value = str(level_value)
        
        result = {
            "id": contest.id,
            "name": contest.name,
            "description": contest.description,
            "contest_type": contest.contest_type,
            "cover_image_url": cover_image_url,
            "image_url": image_url_processed,  # Retourner aussi image_url traitée
            "submission_start_date": submission_start_date,
            "submission_end_date": submission_end_date,
            "voting_start_date": voting_start_date,
            "voting_end_date": voting_end_date,
            "is_active": contest.is_active,
            "is_submission_open": is_submission_open_calculated,
            "is_voting_open": is_voting_open_calculated,
            "level": level_value,
            "season_level": season_level,  # Niveau depuis la season (déjà converti en string)
            "location_id": contest.location_id,
            "gender_restriction": final_gender_restriction,
            "voting_restriction": voting_restriction_str,  # TOUJOURS retourner, même si 'none'
            "max_entries_per_user": contest.max_entries_per_user,
            "template_id": contest.template_id,
            "voting_type_id": getattr(contest, 'voting_type_id', None),
            "voting_type": voting_type_data,  # Objet voting_type complet (déjà un dict)
            "category_id": category_id_value,  # ID de la catégorie (toujours inclure, même si None)
            "category": category_data,  # Objet category complet (déjà un dict) ou None
            "created_at": contest.created_at,
            "updated_at": contest.updated_at,
            "entries_count": entries_count,
            "total_votes": total_votes,
            # Season dates
            "city_season_start_date": getattr(contest, 'city_season_start_date', None),
            "city_season_end_date": getattr(contest, 'city_season_end_date', None),
            "country_season_start_date": getattr(contest, 'country_season_start_date', None),
            "country_season_end_date": getattr(contest, 'country_season_end_date', None),
            "regional_start_date": getattr(contest, 'regional_start_date', None),
            "regional_end_date": getattr(contest, 'regional_end_date', None),
            "continental_start_date": getattr(contest, 'continental_start_date', None),
            "continental_end_date": getattr(contest, 'continental_end_date', None),
            "global_start_date": getattr(contest, 'global_start_date', None),
            "global_end_date": getattr(contest, 'global_end_date', None),
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
            # Vérifier si l'utilisateur connecté participe
            "current_user_contesting": current_user_contesting,
        }
        
        # Log pour vérifier que category_id est bien dans le résultat
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"Contest {contest.id} - result dict contains category_id: {'category_id' in result}, value: {result.get('category_id')}")
        
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
        
        # Récupérer l'utilisateur si current_user_id est fourni
        current_user = None
        if current_user_id:
            current_user = db.query(User).filter(User.id == current_user_id).first()
        
        # Enrichir le contest avec les stats
        contest_data = self.enrich_contest_with_stats(db, contest_obj, current_user=current_user)
        
        # Récupérer la saison active d'abord
        from app.models.contests import ContestantSeason
        season = None
        season_link = db.query(ContestSeasonLink).filter(
            ContestSeasonLink.contest_id == contest_id,
            ContestSeasonLink.is_active == True
        ).first()
        
        if season_link:
            season = db.query(ContestSeason).filter(
                ContestSeason.id == season_link.season_id
            ).first()
        
        # FIXED: Query contestants by BOTH round_id and season_id
        from app.models.round import Round, round_contests
        from sqlalchemy import or_
        
        # Find round IDs linked to this contest
        round_ids = []
        try:
            round_ids_via_table = db.query(round_contests.c.round_id).filter(
                round_contests.c.contest_id == contest_id
            ).all()
            if round_ids_via_table:
                round_ids.extend([r[0] for r in round_ids_via_table])
        except Exception:
            pass
        
        try:
            legacy_rounds = db.query(Round.id).filter(Round.contest_id == contest_id).all()
            if legacy_rounds:
                round_ids.extend([r[0] for r in legacy_rounds])
        except Exception:
            pass
        
        round_ids = list(set(round_ids))
        
        # Build comprehensive OR conditions for round_id and season_id
        conditions = []
        
        # Condition 1: season_id matches contest_id
        conditions.append(Contestant.season_id == contest_id)
        
        # Condition 2: round_id matches any of the found rounds
        if round_ids:
            conditions.append(Contestant.round_id.in_(round_ids))
        
        # Condition 3: Handle NULL season_id but valid round_id (for migrated data)
        if round_ids:
            from sqlalchemy import and_
            conditions.append(
                and_(
                    Contestant.season_id.is_(None),
                    Contestant.round_id.in_(round_ids)
                )
            )
        
        # Query contestants using comprehensive OR conditions
        if conditions:
            contestants_query = db.query(Contestant)\
                .filter(
                    Contestant.is_deleted == False,
                    or_(*conditions)
                )\
                .options(
                    joinedload(Contestant.user)
                )
        else:
            # Fallback: just season_id
            contestants_query = db.query(Contestant)\
                .filter(
                    Contestant.is_deleted == False,
                    Contestant.season_id == contest_id
                )\
                .options(
                    joinedload(Contestant.user)
                )
        
        # Appliquer le filtrage géographique selon le niveau de la saison et l'utilisateur connecté
        # Récupérer l'utilisateur courant pour le filtrage géographique
        current_user = None
        if current_user_id:
            current_user = db.query(User).filter(User.id == current_user_id).first()
        
        # Déterminer le niveau de la saison pour le filtrage
        season_level = None
        if season and hasattr(season, "level") and season.level is not None:
            season_level = season.level.value if hasattr(season.level, "value") else str(season.level)
            if isinstance(season_level, str):
                season_level = season_level.lower()
        
        # Appliquer le filtrage géographique dans la requête SQL si un utilisateur est connecté
        # Utilisation directe des colonnes de Contestant (plus besoin de jointure avec User)
        if contestants_query and current_user and season_level and season_level != "global":
            from sqlalchemy import and_
            
            # Fonction helper pour créer des conditions de filtrage
            def create_location_filter(level: str, user: User):
                """
                Crée un filtre SQL basé sur le niveau et la localisation de l'utilisateur.
                Utilise directement les colonnes de Contestant (city, country, region, continent).
                """
                def is_valid_location(value: Optional[str]) -> bool:
                    if not value:
                        return False
                    val_lower = str(value).lower().strip()
                    return val_lower not in ("unknown", "none", "", "null")
                
                # Construire les conditions selon le niveau en utilisant les colonnes de Contestant
                if level == "city":
                    # Même ville ET même pays
                    conditions = []
                    if is_valid_location(user.country):
                        conditions.append(Contestant.country.ilike(user.country))
                    if is_valid_location(user.city):
                        conditions.append(Contestant.city.ilike(user.city))
                    # Si aucune condition valide, pas de filtre (afficher tous)
                    if not conditions:
                        return None
                    # Combiner avec AND (les deux doivent correspondre si les deux sont valides)
                    return and_(*conditions) if len(conditions) > 1 else conditions[0]
                    
                elif level == "country":
                    # Même pays
                    if is_valid_location(user.country):
                        return Contestant.country.ilike(user.country)
                    return None
                    
                elif level in ("regional", "region"):
                    # Même région
                    user_region = getattr(user, "region", None)
                    if is_valid_location(user_region):
                        return Contestant.region.ilike(user_region)
                    return None
                    
                elif level == "continent":
                    # Même continent uniquement
                    if is_valid_location(user.continent):
                        return Contestant.continent.ilike(user.continent)
                    return None
                
                # Niveau inconnu ou global -> pas de filtre
                return None
            
            location_filter = create_location_filter(season_level, current_user)
            if location_filter is not None:
                contestants_query = contestants_query.filter(location_filter)
        
        # Exécuter la requête
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            # DEBUG: First check what contestants actually exist
            debug_sample = db.query(
                Contestant.id,
                Contestant.season_id,
                Contestant.round_id,
                Contestant.is_deleted
            ).filter(Contestant.is_deleted == False).limit(20).all()
            logger.info(f"[DEBUG] Sample of all contestants in DB: {[(c.id, c.season_id, c.round_id) for c in debug_sample]}")
            
            # Log query details for debugging
            logger.info(f"[get_contest_with_enriched_contestants] Querying contestants for contest_id={contest_id}, round_ids={round_ids}")
            logger.info(f"[get_contest_with_enriched_contestants] OR conditions: season_id={contest_id}, round_ids={round_ids}")
            contestants = contestants_query.all()
            logger.info(f"[get_contest_with_enriched_contestants] Found {len(contestants)} contestants")
            
            # If no contestants, try fallbacks
            if not contestants:
                logger.warning(f"[get_contest_with_enriched_contestants] No contestants found. Trying fallbacks...")
                
                # Fallback 1: season_id only
                try:
                    fallback1 = db.query(Contestant).filter(
                        Contestant.is_deleted == False,
                        Contestant.season_id == contest_id
                    ).options(joinedload(Contestant.user)).limit(100).all()
                    logger.info(f"[get_contest_with_enriched_contestants] Fallback 1 (season_id={contest_id}): Found {len(fallback1)}")
                    if fallback1:
                        contestants = fallback1
                except Exception as e1:
                    logger.error(f"Error in fallback 1: {e1}")
                
                # Fallback 2: round_id only
                if not contestants and round_ids:
                    try:
                        fallback2 = db.query(Contestant).filter(
                            Contestant.is_deleted == False,
                            Contestant.round_id.in_(round_ids)
                        ).options(joinedload(Contestant.user)).limit(100).all()
                        logger.info(f"[get_contest_with_enriched_contestants] Fallback 2 (round_ids={round_ids}): Found {len(fallback2)}")
                        if fallback2:
                            contestants = fallback2
                    except Exception as e2:
                        logger.error(f"Error in fallback 2: {e2}")
                
                # Fallback 3: ANY contestant (for debugging)
                if not contestants:
                    try:
                        fallback3 = db.query(Contestant).filter(
                            Contestant.is_deleted == False
                        ).options(joinedload(Contestant.user)).limit(10).all()
                        logger.warning(f"[get_contest_with_enriched_contestants] Fallback 3 (ANY): Found {len(fallback3)}. Sample: {[(c.id, c.season_id, c.round_id) for c in fallback3]}")
                    except Exception as e3:
                        logger.error(f"Error in fallback 3: {e3}")
                        
        except Exception as e:
            logger.error(f"Error fetching contestants: {e}", exc_info=True)
            contestants = []
        
        # Récupérer tous les IDs des contestants (après filtrage)
        contestant_ids = [c.id for c in contestants]
        logger.info(f"[get_contest_with_enriched_contestants] Returning {len(contestant_ids)} contestant IDs")
        
        # Récupérer tous les votes avec utilisateurs (depuis ContestantVoting)
        # Filtrer par season_id pour ne récupérer que les votes de cette saison
        votes_data = []
        if season:
            votes_data = db.query(ContestantVoting, User)\
                .join(User, ContestantVoting.user_id == User.id)\
                .filter(
                    ContestantVoting.contestant_id.in_(contestant_ids),
                    ContestantVoting.season_id == season.id
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
        # Récupérer les signalements de l'utilisateur courant pour les contestants
        reported_contestants = set()
        if current_user_id:
            try:
                from app.models.comment import Report
                from sqlalchemy import inspect as sa_inspect
                # Vérifier si la colonne contestant_id existe dans la table report
                insp = sa_inspect(db.bind)
                report_columns = [col['name'] for col in insp.get_columns('report')]
                if 'contestant_id' in report_columns:
                    user_reports = db.query(Report.contestant_id).filter(
                        Report.reporter_id == current_user_id,
                        Report.status == "pending",
                        Report.contestant_id.isnot(None)
                    ).all()
                    reported_contestants = {report[0] for report in user_reports if report[0] is not None}
            except Exception:
                # Si la colonne n'existe pas, on ignore les signalements
                pass
        
        if current_user_id:
            author_favs = db.query(MyFavorites.contestant_id)\
                .filter(
                    MyFavorites.user_id == current_user_id,
                    MyFavorites.contestant_id.in_(contestant_ids)
                )\
                .all()
            author_favorites = {fav[0] for fav in author_favs}
        
        # Récupérer tous les votes de l'utilisateur pour cette saison (pour tous les contestants)
        # IMPORTANT: Un utilisateur peut voter pour plusieurs contestants dans la même saison
        # Mais il ne peut pas voter deux fois pour le même contestant dans la même saison
        user_votes_in_season = {}
        if current_user_id and season:
            user_votes = db.query(ContestantVoting)\
                .filter(
                    ContestantVoting.user_id == current_user_id,
                    ContestantVoting.season_id == season.id,
                    ContestantVoting.contestant_id.in_(contestant_ids)
                )\
                .all()
            # Créer un dictionnaire {contestant_id: vote} pour vérification rapide
            user_votes_in_season = {vote.contestant_id: vote for vote in user_votes}
        
        # Déterminer le niveau de la saison (city, country, regional, continent, global, etc.)
        season_level = None
        if season and hasattr(season, "level") and season.level is not None:
            season_level = season.level.value if hasattr(season.level, "value") else str(season.level)
            if isinstance(season_level, str):
                season_level = season_level.lower()
        
        # Compter les votes pour chaque contestant
        votes_count_by_contestant = {}
        for contestant_id in contestant_ids:
            votes_count_by_contestant[contestant_id] = len(votes_by_contestant.get(contestant_id, []))
        
        ranks: Dict[int, int] = {}
        # Calculer les rangs (on ignore les rangs éventuellement stockés en base
        # pour appliquer les nouvelles règles dynamiques basées sur la localisation)
        # Règles :
        # - city    -> classement par ville + pays
        # - country -> classement par pays + continent
        # - regional-> classement par région + continent
        # - continent -> classement par continent
        # - global  -> classement global (tous ensemble)
        def get_group_key(c: Contestant) -> str:
            # Utiliser directement les champs du Contestant (plus besoin de relation User)
            lvl = (season_level or "global") if isinstance(season_level, str) else "global"
            lvl = lvl.lower()
            country = (c.country or "").lower() if c.country else ""
            city = (c.city or "").lower() if c.city else ""
            continent = (c.continent or "").lower() if c.continent else ""
            region = (c.region or "").lower() if c.region else ""
            
            if lvl == "city":
                return f"city:{country}:{city}"
            if lvl == "country":
                return f"country:{continent}:{country}"
            if lvl in ("regional", "region"):
                return f"regional:{continent}:{region}"
            if lvl == "continent":
                return f"continent:{continent}"
            return "global"

        groups: Dict[str, list[int]] = {}
        for c in contestants:
            key = get_group_key(c)
            groups.setdefault(key, []).append(c.id)

        for group_ids in groups.values():
            ranked_contestants = sorted(
                group_ids,
                key=lambda cid: votes_count_by_contestant.get(cid, 0),
                reverse=True,
            )
            for position, cid in enumerate(ranked_contestants, start=1):
                ranks[cid] = position
        
        # Fonction utilitaire pour vérifier si un utilisateur peut voter pour un contestant
        # Utilise maintenant directement les champs du Contestant (simplifié)
        def is_geographically_allowed(voter: Optional['User'], candidate: Contestant) -> bool:
            # Si pas de voter ou pas de season_level, permettre le vote
            if not voter or not season_level:
                return True
            
            lvl = str(season_level).lower()
            v = voter
            
            def eq(a: Optional[str], b: Optional[str]) -> bool:
                return bool(a and b and a.lower() == b.lower())
            
            def is_valid_location(value: Optional[str]) -> bool:
                if not value:
                    return False
                val_lower = str(value).lower().strip()
                return val_lower not in ("unknown", "none", "", "null")
            
            def compare_with_unknown(val1: Optional[str], val2: Optional[str]) -> bool:
                """Compare deux valeurs géographiques en ignorant 'Unknown'"""
                valid1 = is_valid_location(val1)
                valid2 = is_valid_location(val2)
                if valid1 and valid2:
                    return eq(val1, val2)
                # Si au moins une est "Unknown", on accepte (pas de restriction)
                return True
            
            # Utiliser directement les champs du Contestant au lieu de candidate.user
            # Appliquer les restrictions selon le niveau de la saison
            if lvl == "city":
                # Même ville ET même pays
                country_match = compare_with_unknown(v.country, candidate.country)
                if not country_match:
                    return False
                return compare_with_unknown(v.city, candidate.city)
            elif lvl == "country":
                # Même pays
                return compare_with_unknown(v.country, candidate.country)
            elif lvl in ("regional", "region"):
                # Même région
                v_region = getattr(v, "region", None)
                return compare_with_unknown(v_region, candidate.region)
            elif lvl == "continent":
                # Même continent
                return compare_with_unknown(v.continent, candidate.continent)
            else:
                # Global ou niveau inconnu -> pas de restriction géographique
                return True

        # Construire la liste des contestants enrichis
        enriched_contestants = []
        for contestant in contestants:
            # S'assurer que la relation user est chargée
            if not hasattr(contestant, 'user') or contestant.user is None:
                # Recharger le contestant avec la relation user si nécessaire
                contestant = db.query(Contestant)\
                    .options(joinedload(Contestant.user))\
                    .filter(Contestant.id == contestant.id)\
                    .first()
                if not contestant:
                    continue  # Skip si le contestant n'existe plus
            
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
            
            # Déterminer si l'utilisateur peut voter pour ce contestant
            # Un utilisateur peut voter si :
            # 1. Il est authentifié
            # 2. Ce n'est pas sa propre candidature
            # 3. Il n'a pas déjà voté pour ce contestant dans cette saison
            # Note: Les restrictions géographiques sont appliquées au niveau de l'affichage des contestants,
            # pas au niveau du vote. Si un contestant est visible, l'utilisateur peut voter pour lui.
            # IMPORTANT: Un utilisateur peut voter pour plusieurs contestants différents dans la même saison
            # Mais il ne peut pas voter deux fois pour le même contestant dans la même saison
            # Si l'utilisateur a voté pour le contestant X dans la saison CITY, il peut voter pour le contestant Y dans la même saison CITY
            # Mais il ne peut pas voter deux fois pour X dans la même saison CITY
            # S'il migre vers COUNTRY, il peut voter à nouveau pour X dans la nouvelle saison COUNTRY
            can_vote = False
            has_voted = False
            vote_restriction_reason = None
            
            if current_user_id:
                if not current_user:
                    # Si current_user n'est pas chargé, le charger
                    current_user = db.query(User).filter(User.id == current_user_id).first()
                
                if current_user:
                    if current_user_id == contestant.user_id:
                        # L'utilisateur ne peut pas voter pour sa propre candidature
                        can_vote = False
                        has_voted = False
                        vote_restriction_reason = "own_contestant"
                    else:
                        # Vérifier si l'utilisateur a déjà voté pour ce contestant dans cette saison
                        # IMPORTANT: Un utilisateur peut voter pour plusieurs contestants différents dans la même saison
                        # Mais il ne peut pas voter deux fois pour le même contestant dans la même saison
                        # Si l'utilisateur a voté pour le contestant X dans la saison CITY, il peut voter pour le contestant Y dans la même saison CITY
                        # Mais il ne peut pas voter deux fois pour X dans la même saison CITY
                        # S'il migre vers COUNTRY, il peut voter à nouveau pour X dans la nouvelle saison COUNTRY
                        existing_vote_for_contestant = user_votes_in_season.get(contestant.id)
                        
                        if existing_vote_for_contestant:
                            # L'utilisateur a déjà voté pour ce contestant dans cette saison
                            has_voted = True
                            can_vote = False
                            vote_restriction_reason = "already_voted"
                        else:
                            # L'utilisateur n'a pas encore voté pour ce contestant dans cette saison
                            has_voted = False
                            # Plus de restriction géographique pour le vote
                            # L'utilisateur peut voter s'il n'a pas déjà voté et ce n'est pas sa propre candidature
                            can_vote = True
           
           
            else:
                # Si current_user_id est None (utilisateur non authentifié), can_vote et has_voted restent False
                vote_restriction_reason = "not_authenticated"
            
            # Utiliser les données directement du Contestant (plus besoin de relation User pour les données géographiques)
            # Mais on garde la relation User pour le nom et l'avatar
            author_name = None
            author_avatar_url = None
            if contestant.user:
                author_name = contestant.user.full_name or f"{contestant.user.first_name or ''} {contestant.user.last_name or ''}".strip()
                author_avatar_url = contestant.user.avatar_url
            
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
                # Infos auteur - utiliser directement les champs du Contestant
                "author_name": author_name,
                "author_country": contestant.country,
                "author_city": contestant.city,
                "author_continent": contestant.continent,
                "author_region": contestant.region,
                "author_gender": contestant.author_gender,
                "author_avatar_url": author_avatar_url,
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
                # État du vote (par saison)
                "has_voted": has_voted,  # L'utilisateur a déjà voté dans cette saison
                "can_vote": can_vote,  # L'utilisateur peut voter pour ce contestant dans cette saison
                "vote_restriction_reason": vote_restriction_reason,  # Raison de restriction si can_vote est False
                # État du signalement
                "has_reported": contestant.id in reported_contestants,  # L'utilisateur a déjà signalé ce contestant
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
        Trouve ou crée le ContestStage correspondant à la saison.
        """
        from app.models.voting import ContestantVoting
        from app.models.contests import ContestStage, ContestStatus, ContestStageLevel
        from datetime import datetime, timedelta
        
        # Récupérer ou créer le ContestStage pour cette saison
        # Chercher d'abord un stage actif (voting_active) pour cette saison
        stage = db.query(ContestStage).filter(
            ContestStage.season_id == season_id,
            ContestStage.status == ContestStatus.VOTING_ACTIVE
        ).first()
        
        # Si aucun stage actif, chercher n'importe quel stage pour cette saison
        if not stage:
            stage = db.query(ContestStage).filter(
                ContestStage.season_id == season_id
            ).first()
        
        # Si aucun stage n'existe, créer un stage par défaut pour cette saison
        if not stage:
            # Récupérer la saison pour obtenir ses informations
            from app.models.contests import ContestSeason
            season = db.query(ContestSeason).filter(ContestSeason.id == season_id).first()
            if not season:
                # Si la saison n'existe pas, on ne peut pas créer de stage
                import logging
                logging.warning(f"Season {season_id} not found, cannot create rankings")
                return
            
            # Créer un stage par défaut
            now = datetime.utcnow()
            stage = ContestStage(
                season_id=season_id,
                stage_level=ContestStageLevel.REGIONAL,  # Valeur par défaut
                status=ContestStatus.VOTING_ACTIVE,
                start_date=now - timedelta(days=1),
                end_date=now + timedelta(days=30),
                max_qualifiers=5,
                min_participants=2
            )
            db.add(stage)
            db.flush()  # Pour obtenir l'ID du stage
        
        stage_id = stage.id
        
        # Récupérer tous les contestants du contest pour cette saison
        contestants = db.query(Contestant).filter(
            Contestant.season_id == season_id,
            Contestant.is_deleted == False
        ).all()
        
        # Compter les votes pour chaque contestant (par saison)
        votes_by_contestant = {}
        for contestant in contestants:
            votes_count = db.query(func.count(ContestantVoting.id))\
                .filter(
                    ContestantVoting.contestant_id == contestant.id,
                    ContestantVoting.season_id == season_id
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
            # Chercher un rang existant pour ce contestant et ce stage
            ranking = db.query(ContestantRanking).filter(
                ContestantRanking.contestant_id == contestant_id,
                ContestantRanking.stage_id == stage_id
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
                    stage_id=stage_id,
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