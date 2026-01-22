"""
Service de gestion des migrations de saisons pour les contests.
Gère la progression automatique des contestants à travers les différents niveaux.
S'exécute toutes les 24h pour vérifier les migrations selon les dates des saisons.
"""
from datetime import datetime, timedelta, date
from typing import List, Optional, Dict
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_

from app.models.contest import Contest
from app.models.contests import (
    ContestSeason, 
    Contestant, 
    ContestantSeason, 
    ContestSeasonLink,
    ContestStage,
    ContestantRanking,
    SeasonLevel,
    ContestStageLevel,
    ContestStatus
)
from app.models.user import User
from app.models.voting import ContestantVoting
from app.models.round import Round, RoundStatus


class SeasonMigrationService:
    """Service pour gérer les migrations de saisons"""
    
    @staticmethod
    def get_or_create_season(
        db: Session, 
        level: SeasonLevel, 
        title: Optional[str] = None,
        round_id: Optional[int] = None
    ) -> ContestSeason:
        """
        Récupère ou crée une saison pour un niveau donné et un round donné.
        """
        if title is None:
            title = f"Saison {level.value.capitalize()}"
        
        # Chercher une saison existante pour ce niveau et ce round
        query = db.query(ContestSeason).filter(
            and_(
                ContestSeason.level == level,
                ContestSeason.is_deleted == False
            )
        )
        
        if round_id:
            query = query.filter(ContestSeason.round_id == round_id)
            
        season = query.first()
        
        if not season:
            season = ContestSeason(
                title=title,
                level=level,
                is_deleted=False,
                round_id=round_id
            )
            db.add(season)
            db.commit()
            db.refresh(season)
        
        return season
    
    @staticmethod
    def get_top_contestants_by_location(
        db: Session,
        season_id: int,  # ID de la saison, pas du contest
        location_field: str,  # 'city', 'country', 'region', 'continent'
        limit: int = 5,
        stage_id: Optional[int] = None  # Non utilisé maintenant, gardé pour compatibilité
    ) -> Dict[str, List[Contestant]]:
        """
        Récupère les N meilleurs contestants groupés par localisation.
        Utilise les votes depuis ContestantVoting (par season_id) au lieu des stages.
        Retourne un dictionnaire {location_value: [contestants]}
        """
        import logging
        logger = logging.getLogger(__name__)
        
        # Vérifier d'abord combien de contestants sont liés à cette saison
        total_contestants_in_season = db.query(ContestantSeason).filter(
            and_(
                ContestantSeason.season_id == season_id,
                ContestantSeason.is_active == True
            )
        ).count()
        
        logger.info(f"get_top_contestants_by_location: season_id={season_id}, location_field={location_field}, limit={limit}")
        logger.info(f"  - Total contestants liés à la saison: {total_contestants_in_season}")
        print(f"[Migration]   Total contestants liés à la saison {season_id}: {total_contestants_in_season}")
        
        # Récupérer tous les contestants actifs et qualifiés de la saison via ContestantSeason
        contestants_query = db.query(Contestant).join(
            ContestantSeason
        ).join(
            User
        ).filter(
            and_(
                ContestantSeason.season_id == season_id,
                ContestantSeason.is_active == True,
                Contestant.is_active == True,
                Contestant.is_deleted == False,
                Contestant.is_qualified == True
            )
        )
        
        # Filtrer par localisation non nulle
        if location_field == 'city':
            contestants_query = contestants_query.filter(User.city.isnot(None))
        elif location_field == 'country':
            contestants_query = contestants_query.filter(User.country.isnot(None))
        elif location_field == 'region':
            contestants_query = contestants_query.filter(User.region.isnot(None))
        elif location_field == 'continent':
            contestants_query = contestants_query.filter(User.continent.isnot(None))
        
        contestants = contestants_query.all()
        
        logger.info(f"  - Contestants qualifiés avec localisation {location_field}: {len(contestants)}")
        print(f"[Migration]   Contestants qualifiés avec localisation {location_field}: {len(contestants)}")
        
        if not contestants:
            # Vérifier pourquoi aucun contestant n'est trouvé
            contestants_without_location = db.query(Contestant).join(
                ContestantSeason
            ).join(
                User
            ).filter(
                and_(
                    ContestantSeason.season_id == season_id,
                    ContestantSeason.is_active == True,
                    Contestant.is_active == True,
                    Contestant.is_deleted == False,
                    Contestant.is_qualified == True
                )
            ).count()
            
            contestants_not_qualified = db.query(Contestant).join(
                ContestantSeason
            ).filter(
                and_(
                    ContestantSeason.season_id == season_id,
                    ContestantSeason.is_active == True,
                    Contestant.is_active == True,
                    Contestant.is_deleted == False,
                    Contestant.is_qualified == False
                )
            ).count()
            
            logger.warning(f"  - Aucun contestant trouvé pour la saison {season_id}")
            logger.warning(f"    - Contestants qualifiés sans localisation: {contestants_without_location}")
            logger.warning(f"    - Contestants non qualifiés: {contestants_not_qualified}")
            print(f"[Migration]   Aucun contestant trouvé pour la saison {season_id}")
            print(f"[Migration]     - Contestants qualifiés sans localisation: {contestants_without_location}")
            print(f"[Migration]     - Contestants non qualifiés: {contestants_not_qualified}")
            return {}
        
        # Récupérer les votes par contestant depuis ContestantVoting (par season_id)
        vote_counts = db.query(
            ContestantVoting.contestant_id,
            func.count(ContestantVoting.id).label('vote_count')
        ).filter(
            ContestantVoting.season_id == season_id
        ).group_by(
            ContestantVoting.contestant_id
        ).all()
        
        votes_by_contestant = {vc.contestant_id: vc.vote_count for vc in vote_counts}
        logger.info(f"  - Votes trouvés pour {len(votes_by_contestant)} contestants")
        print(f"[Migration]   Votes trouvés pour {len(votes_by_contestant)} contestants")
        
        # Grouper par localisation
        grouped = {}
        for contestant in contestants:
            location_value = None
            if location_field == 'city':
                location_value = contestant.user.city
            elif location_field == 'country':
                location_value = contestant.user.country
            elif location_field == 'region':
                location_value = contestant.user.region
            elif location_field == 'continent':
                location_value = contestant.user.continent
            
            if not location_value:
                continue
            
            if location_value not in grouped:
                grouped[location_value] = []
            
            grouped[location_value].append(contestant)
        
        # Trier et limiter pour chaque localisation
        result = {}
        logger.info(f"  - Groupes par localisation: {len(grouped)}")
        for location_value, location_contestants in grouped.items():
            # Trier par nombre de votes décroissant
            sorted_contestants = sorted(
                location_contestants,
                key=lambda c: votes_by_contestant.get(c.id, 0),
                reverse=True
            )
            
            # Prendre les N premiers (ou tous si moins de N)
            selected = sorted_contestants[:limit]
            result[location_value] = selected
            logger.info(f"    - {location_value}: {len(selected)}/{len(location_contestants)} contestants sélectionnés")
            print(f"[Migration]     {location_value}: {len(selected)}/{len(location_contestants)} contestants")
        
        total_selected = sum(len(contestants) for contestants in result.values())
        logger.info(f"  - Total sélectionné: {total_selected} contestants")
        print(f"[Migration]   Total sélectionné: {total_selected} contestants")
        
        return result
    
    @staticmethod
    def migrate_to_city_season(db: Session, contest_id: int, round_id: int) -> dict:
        """
        Migre tous les contestants d'un contest/round vers la saison CITY
        """
        contest = db.query(Contest).filter(Contest.id == contest_id).first()
        round_obj = db.query(Round).filter(Round.id == round_id).first()
        
        if not contest or not round_obj:
            return {"error": "Contest or Round not found"}
        
        # Vérifier si la migration a déjà été faite pour ce round
        existing_link = db.query(ContestSeasonLink).join(ContestSeason).filter(
            and_(
                ContestSeasonLink.contest_id == contest_id,
                ContestSeasonLink.is_active == True,
                ContestSeason.round_id == round_id,
                ContestSeason.level == SeasonLevel.CITY
            )
        ).first()
        
        if existing_link:
            return {"message": "Migration already done", "season_id": existing_link.season_id}
        
        # Récupérer ou créer la saison CITY liée au round
        city_season = SeasonMigrationService.get_or_create_season(
            db, 
            SeasonLevel.CITY,
            title=f"Saison City - {contest.name} - {round_obj.name}",
            round_id=round_id
        )
        
        # Récupérer tous les contestants actifs du contest
        contestants = db.query(Contestant).filter(
            and_(
                Contestant.season_id == contest_id,
                Contestant.is_active == True,
                Contestant.is_deleted == False
            )
        ).all()
        
        import logging
        logger = logging.getLogger(__name__)
        
        # Tous les contestants sont qualifiés par défaut
        migrated_contestant_ids = []
        for contestant in contestants:
            contestant.is_qualified = True
            # Créer le lien contestant-season
            existing_contestant_season = db.query(ContestantSeason).filter(
                and_(
                    ContestantSeason.contestant_id == contestant.id,
                    ContestantSeason.season_id == city_season.id
                )
            ).first()
            
            if not existing_contestant_season:
                contestant_season = ContestantSeason(
                    contestant_id=contestant.id,
                    season_id=city_season.id,
                    joined_at=datetime.utcnow(),
                    is_active=True
                )
                db.add(contestant_season)
                logger.info(f"  - Création du lien ContestantSeason pour contestant {contestant.id} dans saison CITY {city_season.id}")
                migrated_contestant_ids.append(contestant.id)
            else:
                existing_contestant_season.is_active = True
                existing_contestant_season.joined_at = datetime.utcnow()  # Mettre à jour la date de migration
                logger.info(f"  - Réactivation du lien ContestantSeason existant pour contestant {contestant.id} (date mise à jour)")
                migrated_contestant_ids.append(contestant.id)
        
        logger.info(f"Contestants migrés vers CITY ({len(migrated_contestant_ids)}): {migrated_contestant_ids}")
        
        # Mettre à jour le contest : changer le level et créer le lien
        contest.level = "city"
        existing_contest_link = db.query(ContestSeasonLink).filter(
            and_(
                ContestSeasonLink.contest_id == contest.id,
                ContestSeasonLink.season_id == city_season.id
            )
        ).first()
        
        if not existing_contest_link:
            contest_season_link = ContestSeasonLink(
                contest_id=contest.id,
                season_id=city_season.id,
                linked_at=datetime.utcnow(),
                is_active=True
            )
            db.add(contest_season_link)
            logger.info(f"  - Création du lien ContestSeasonLink pour contest {contest.id} et saison CITY {city_season.id}")
        else:
            existing_contest_link.is_active = True
            existing_contest_link.linked_at = datetime.utcnow()  # Mettre à jour la date de migration
            logger.info(f"  - Réactivation du lien ContestSeasonLink existant pour contest {contest.id} (date mise à jour)")
        
        # Créer le stage CITY pour cette saison
        city_stage = db.query(ContestStage).filter(
            and_(
                ContestStage.season_id == city_season.id,
                ContestStage.stage_level == ContestStageLevel.CITY
            )
        ).first()
        
        if not city_stage:
            # Utiliser les dates de la saison city du contest
            start_date = contest.city_season_start_date
            end_date = contest.city_season_end_date
            
            if not start_date or not end_date:
                # Fallback : calculer à partir de voting_start_date
                start_date = contest.voting_start_date
                if isinstance(start_date, date):
                    start_date = datetime.combine(start_date, datetime.min.time())
                end_date = start_date + timedelta(days=30)
            
            city_stage = ContestStage(
                season_id=city_season.id,
                stage_level=ContestStageLevel.CITY,
                status=ContestStatus.VOTING_ACTIVE,
                start_date=start_date,
                end_date=end_date,
                max_qualifiers=5,
                min_participants=2
            )
            db.add(city_stage)
        
        db.commit()
        
        logger.info(f"Migration vers CITY réussie: {len(migrated_contestant_ids)} contestants migrés")
        logger.info(f"  - Contest {contest.id} lié à la saison CITY {city_season.id}")
        logger.info(f"  - Contestants migrés: {migrated_contestant_ids}")
        print(f"[Migration] ✓ Migration vers CITY réussie: Contest {contest.id}")
        print(f"[Migration]   Contestants migrés ({len(migrated_contestant_ids)}): {migrated_contestant_ids}")
        
        return {
            "message": f"Migrated {len(contestants)} contestants to CITY season",
            "season_id": city_season.id,
            "contestants_migrated": len(contestants),
            "migrated_contestant_ids": migrated_contestant_ids
        }

    @staticmethod
    def migrate_to_country_start(db: Session, contest_id: int, round_id: int) -> dict:
        """
        Initialise la saison COUNTRY pour les contests de type Nomination (Nomination starts at Country).
        """
        contest = db.query(Contest).filter(Contest.id == contest_id).first()
        round_obj = db.query(Round).filter(Round.id == round_id).first()
        
        if not contest or not round_obj:
            return {"error": "Contest or Round not found"}
        
        # Vérifier si la migration a déjà été faite
        existing_link = db.query(ContestSeasonLink).join(ContestSeason).filter(
            and_(
                ContestSeasonLink.contest_id == contest_id,
                ContestSeasonLink.is_active == True,
                ContestSeason.level == SeasonLevel.COUNTRY,
                ContestSeason.round_id == round_id
            )
        ).first()
        
        if existing_link:
            return {"message": "Migration already done", "season_id": existing_link.season_id}
        
        # Récupérer ou créer la saison COUNTRY
        country_season = SeasonMigrationService.get_or_create_season(
            db, 
            SeasonLevel.COUNTRY,
            title=f"Saison Country - {contest.name} - {round_obj.name}",
            round_id=round_id
        )
        
        # Récupérer tous les contestants actifs du contest (Entry Season)
        contestants = db.query(Contestant).filter(
            and_(
                Contestant.season_id == contest_id,
                Contestant.is_active == True,
                Contestant.is_deleted == False
            )
        ).all()
        
        import logging
        logger = logging.getLogger(__name__)
        
        # Tous les contestants sont qualifiés par défaut pour le démarrage
        migrated_contestant_ids = []
        for contestant in contestants:
            contestant.is_qualified = True
            # Créer le lien contestant-season
            existing_contestant_season = db.query(ContestantSeason).filter(
                and_(
                    ContestantSeason.contestant_id == contestant.id,
                    ContestantSeason.season_id == country_season.id
                )
            ).first()
            
            if not existing_contestant_season:
                contestant_season = ContestantSeason(
                    contestant_id=contestant.id,
                    season_id=country_season.id,
                    joined_at=datetime.utcnow(),
                    is_active=True
                )
                db.add(contestant_season)
                migrated_contestant_ids.append(contestant.id)
            else:
                existing_contestant_season.is_active = True
                existing_contestant_season.joined_at = datetime.utcnow()
                migrated_contestant_ids.append(contestant.id)
        
        logger.info(f"Contestants initialisés en COUNTRY ({len(migrated_contestant_ids)}): {migrated_contestant_ids}")
        
        # Mettre à jour le contest
        contest.level = "country"
        
        existing_contest_link = db.query(ContestSeasonLink).filter(
            and_(
                ContestSeasonLink.contest_id == contest.id,
                ContestSeasonLink.season_id == country_season.id
            )
        ).first()
        
        if not existing_contest_link:
            contest_season_link = ContestSeasonLink(
                contest_id=contest.id,
                season_id=country_season.id,
                linked_at=datetime.utcnow(),
                is_active=True
            )
            db.add(contest_season_link)
        else:
            existing_contest_link.is_active = True
            existing_contest_link.linked_at = datetime.utcnow()
        
        db.commit()
        
        print(f"[Migration] ✓ Initialisation COUNTRY réussie: Contest {contest.id}")
        
        return {
            "message": f"Initialized {len(contestants)} contestants to COUNTRY season",
            "season_id": country_season.id,
            "contestants_migrated": len(contestants),
            "migrated_contestant_ids": migrated_contestant_ids
        }
    
    @staticmethod
    def promote_to_next_level(
        db: Session,
        from_level: SeasonLevel,
        to_level: SeasonLevel,
        contest_id: int,
        limit: int = 5  # 5 pour tous sauf GLOBAL (3)
    ) -> dict:
        """
        Promouvoit les meilleurs contestants d'un niveau vers le niveau supérieur.
        Pour CITY/COUNTRY/REGIONAL/CONTINENTAL : 5 premiers par localisation
        Pour GLOBAL : 3 premiers au total
        """
        # Récupérer la saison source via le lien contest-season
        contest_season_link = db.query(ContestSeasonLink).join(
            ContestSeason
        ).filter(
            and_(
                ContestSeasonLink.contest_id == contest_id,
                ContestSeason.level == from_level,
                ContestSeason.is_deleted == False,
                ContestSeasonLink.is_active == True
            )
        ).first()
        
        import logging
        logger = logging.getLogger(__name__)
        
        if not contest_season_link:
            error_msg = f"No active season found for level {from_level.value} and contest {contest_id}"
            logger.error(error_msg)
            print(f"[Migration] ERROR: {error_msg}")
            return {"error": error_msg}
        
        from_season = contest_season_link.season
        logger.info(f"Promotion de {from_level.value} vers {to_level.value} pour contest {contest_id}")
        logger.info(f"  - Saison source: {from_season.id} (niveau {from_level.value})")
        print(f"[Migration] Promotion contest {contest_id} de {from_level.value} vers {to_level.value}")
        print(f"[Migration]   Saison source: {from_season.id}")
        
        # Sélectionner les contestants selon le niveau (sans dépendre des stages)
        selected_contestants = []
        
        if to_level == SeasonLevel.GLOBAL:
            # Pour GLOBAL : prendre les 3 premiers au total basés sur les votes de la saison
            # Compter les votes par contestant dans cette saison
            vote_counts = db.query(
                ContestantVoting.contestant_id,
                func.count(ContestantVoting.id).label('vote_count')
            ).filter(
                ContestantVoting.season_id == from_season.id
            ).group_by(
                ContestantVoting.contestant_id
            ).order_by(
                func.count(ContestantVoting.id).desc()
            ).group_by(
                ContestantVoting.contestant_id
            ).order_by(
                func.count(ContestantVoting.id).desc()
            ).limit(limit).all()
            
            contestant_ids = [vc.contestant_id for vc in vote_counts]
            selected_contestants = db.query(Contestant).join(
                ContestantSeason
            ).filter(
                and_(
                    Contestant.id.in_(contestant_ids),
                    ContestantSeason.season_id == from_season.id,
                    ContestantSeason.is_active == True,
                    Contestant.is_active == True,
                    Contestant.is_deleted == False,
                    Contestant.is_qualified == True
                )
            ).all()
            
            # Trier selon l'ordre des votes
            vote_dict = {vc.contestant_id: vc.vote_count for vc in vote_counts}
            selected_contestants = sorted(
                selected_contestants,
                key=lambda c: vote_dict.get(c.id, 0),
                reverse=True
            )
            
            logger.info(f"  - {len(selected_contestants)} contestants sélectionnés pour GLOBAL")
        else:
            # Pour les autres niveaux : prendre les 5 premiers par localisation
            location_field_map = {
                SeasonLevel.COUNTRY: 'city',
                SeasonLevel.REGIONAL: 'country',
                SeasonLevel.CONTINENT: 'region',
                SeasonLevel.GLOBAL: 'continent'
            }
            
            location_field = location_field_map.get(to_level)
            if not location_field:
                return {"error": f"Invalid target level: {to_level.value}"}
            
            # Récupérer les meilleurs par localisation (sans stage_id)
            logger.info(f"  - Récupération des meilleurs contestants par {location_field} (limit: {limit})")
            grouped_contestants = SeasonMigrationService.get_top_contestants_by_location(
                db, from_season.id, location_field, limit=limit, stage_id=None
            )
            
            logger.info(f"  - Groupes trouvés: {len(grouped_contestants)} localisations")
            for location, contestants in grouped_contestants.items():
                logger.info(f"    - {location}: {len(contestants)} contestants")
            
            # Flatten la liste
            for location_contestants in grouped_contestants.values():
                selected_contestants.extend(location_contestants)
        
        logger.info(f"  - Total contestants sélectionnés: {len(selected_contestants)}")
        print(f"[Migration]   Contestants sélectionnés: {len(selected_contestants)}")
        
        if len(selected_contestants) == 0:
            error_msg = f"No contestants to promote from {from_level.value} (season_id: {from_season.id})"
            logger.warning(error_msg)
            print(f"[Migration] WARNING: {error_msg}")
            return {"error": error_msg, "message": error_msg}
        
        # Marquer les non sélectionnés comme non qualifiés
        all_contestants = db.query(Contestant).join(
            ContestantSeason
        ).filter(
            and_(
                ContestantSeason.season_id == from_season.id,
                ContestantSeason.is_active == True,
                Contestant.is_active == True,
                Contestant.is_deleted == False
            )
        ).all()
        
        selected_ids = {c.id for c in selected_contestants}
        for contestant in all_contestants:
            if contestant.id not in selected_ids:
                contestant.is_qualified = False
        
        # Récupérer ou créer la saison destination
        contest = db.query(Contest).filter(Contest.id == contest_id).first()
        
        # S'assurer de garder le round_id de la saison source
        round_id = from_season.round_id
        round_name = from_season.round.name if from_season.round else ""
        
        logger.info(f"  - Création/récupération de la saison {to_level.value}")
        to_season = SeasonMigrationService.get_or_create_season(
            db,
            to_level,
            title=f"Saison {to_level.value.capitalize()} - {contest.name} - {round_name}",
            round_id=round_id
        )
        logger.info(f"  - Saison destination: {to_season.id} (niveau {to_level.value})")
        print(f"[Migration]   Saison destination: {to_season.id}")
        
        # Désactiver les liens dans l'ancienne saison pour les promus et créer les nouveaux liens
        promoted_contestant_ids = []
        for contestant in selected_contestants:
            # Marquer comme qualifié
            contestant.is_qualified = True
            
            old_link = db.query(ContestantSeason).filter(
                and_(
                    ContestantSeason.contestant_id == contestant.id,
                    ContestantSeason.season_id == from_season.id,
                    ContestantSeason.is_active == True
                )
            ).first()
            
            if old_link:
                old_link.is_active = False
                logger.info(f"  - Désactivation du lien ContestantSeason pour contestant {contestant.id} dans saison {from_season.id}")
            
            # Créer le nouveau lien ContestantSeason
            existing_new_link = db.query(ContestantSeason).filter(
                and_(
                    ContestantSeason.contestant_id == contestant.id,
                    ContestantSeason.season_id == to_season.id
                )
            ).first()
            
            if not existing_new_link:
                new_link = ContestantSeason(
                    contestant_id=contestant.id,
                    season_id=to_season.id,
                    joined_at=datetime.utcnow(),
                    is_active=True
                )
                db.add(new_link)
                logger.info(f"  - Création du lien ContestantSeason pour contestant {contestant.id} dans saison {to_season.id}")
                promoted_contestant_ids.append(contestant.id)
            else:
                # Réactiver le lien s'il existe déjà et mettre à jour la date
                existing_new_link.is_active = True
                existing_new_link.joined_at = datetime.utcnow()  # Mettre à jour la date de migration
                logger.info(f"  - Réactivation du lien ContestantSeason existant pour contestant {contestant.id} dans saison {to_season.id} (date mise à jour)")
                promoted_contestant_ids.append(contestant.id)
        
        logger.info(f"Contestants promus ({len(promoted_contestant_ids)}): {promoted_contestant_ids}")
        print(f"[Migration] Contestants promus ({len(promoted_contestant_ids)}): {promoted_contestant_ids}")
        
        # Désactiver l'ancien lien contest-season
        old_contest_link = db.query(ContestSeasonLink).filter(
            and_(
                ContestSeasonLink.contest_id == contest_id,
                ContestSeasonLink.season_id == from_season.id,
                ContestSeasonLink.is_active == True
            )
        ).first()
        
        if old_contest_link:
            old_contest_link.is_active = False
        
        # Mettre à jour le level du contest
        contest.level = to_level.value
        
        # Créer le nouveau lien ContestSeasonLink
        existing_contest_link = db.query(ContestSeasonLink).filter(
            and_(
                ContestSeasonLink.contest_id == contest_id,
                ContestSeasonLink.season_id == to_season.id
            )
        ).first()
        
        if not existing_contest_link:
            new_contest_link = ContestSeasonLink(
                contest_id=contest_id,
                season_id=to_season.id,
                linked_at=datetime.utcnow(),
                is_active=True
            )
            db.add(new_contest_link)
            logger.info(f"  - Création du lien ContestSeasonLink pour contest {contest_id} et saison {to_season.id}")
        else:
            existing_contest_link.is_active = True
            existing_contest_link.linked_at = datetime.utcnow()  # Mettre à jour la date de migration
            logger.info(f"  - Réactivation du lien ContestSeasonLink existant pour contest {contest_id} et saison {to_season.id} (date mise à jour)")
        
        # Pas besoin de créer de stage - on utilise directement les saisons
        
        try:
            db.commit()
            logger.info(f"  - Commit réussi")
            print(f"[Migration]   Commit réussi")
        except Exception as e:
            logger.error(f"  - Erreur lors du commit: {e}", exc_info=True)
            print(f"[Migration] ERROR lors du commit: {e}")
            db.rollback()
            raise
        
        logger.info(f"Migration réussie: {len(selected_contestants)} contestants promus de {from_level.value} vers {to_level.value}")
        logger.info(f"  - Contest {contest_id} lié à la saison {to_season.id} (niveau {to_level.value})")
        logger.info(f"  - Contestants promus: {promoted_contestant_ids}")
        print(f"[Migration] ✓ Migration réussie: Contest {contest_id} promu de {from_level.value} vers {to_level.value}")
        print(f"[Migration]   Contestants promus ({len(promoted_contestant_ids)}): {promoted_contestant_ids}")
        
        return {
            "message": f"Promoted {len(selected_contestants)} contestants from {from_level.value} to {to_level.value}",
            "from_season_id": from_season.id,
            "to_season_id": to_season.id,
            "promoted_count": len(selected_contestants),
            "promoted_contestant_ids": promoted_contestant_ids
        }
    

    @staticmethod
    def check_and_process_migrations(db: Session) -> dict:
        """
        Vérifie et traite toutes les migrations nécessaires pour tous les rounds actifs.
        Basé sur les dates définies dans le Round.
        """
        import logging
        logger = logging.getLogger(__name__)
        from app.services.contest_status import contest_status_service
        
        # TODO: Mettre à jour les statuts des rounds ?
        # status_update_result = contest_status_service.update_contest_statuses(db)
        status_update_result = {}
        
        results = []
        today = date.today()
        logger.info(f"Checking season migrations for date: {today}")
        
        # 1. PARTICIPATION: Start at CITY
        # Query Rounds with city_season_start_date reached
        rounds_to_migrate_city = db.query(Round).join(Contest).filter(
            and_(
                Round.city_season_start_date <= today,
                Round.status != RoundStatus.CANCELLED,
                Contest.voting_type_id == None  # Participation
            )
        ).all()
        
        for round_obj in rounds_to_migrate_city:
            # Check if season exists
            existing_link = db.query(ContestSeasonLink).join(ContestSeason).filter(
                and_(
                    ContestSeasonLink.contest_id == round_obj.contest_id,
                    ContestSeason.round_id == round_obj.id,
                    ContestSeason.level == SeasonLevel.CITY
                )
            ).first()
            
            if not existing_link:
                result = SeasonMigrationService.migrate_to_city_season(db, round_obj.contest_id, round_obj.id)
                results.append({"contest_id": round_obj.contest_id, "round_id": round_obj.id, "action": "init_participation_city", "result": result})

        # 1b. NOMINATION: Start at COUNTRY
        rounds_to_start_country = db.query(Round).join(Contest).filter(
            and_(
                Round.country_season_start_date <= today,
                Round.status != RoundStatus.CANCELLED,
                Contest.voting_type_id != None  # Nomination
            )
        ).all()
        
        for round_obj in rounds_to_start_country:
             existing_link = db.query(ContestSeasonLink).join(ContestSeason).filter(
                and_(
                    ContestSeasonLink.contest_id == round_obj.contest_id,
                    ContestSeason.round_id == round_obj.id,
                    ContestSeason.level == SeasonLevel.COUNTRY
                )
            ).first()
            
             if not existing_link:
                result = SeasonMigrationService.migrate_to_country_start(db, round_obj.contest_id, round_obj.id)
                results.append({"contest_id": round_obj.contest_id, "round_id": round_obj.id, "action": "init_nomination_country", "result": result})

        # 2. PROMOTIONS (Generic loop based on existing Seasons linked to Rounds)
        # We look for active Seasons and check if they should end based on Round dates
        
        active_seasons = db.query(ContestSeason).join(Round).filter(
            and_(
                ContestSeason.is_deleted == False,
                Round.status != RoundStatus.CANCELLED
            )
        ).all()
        
        for season in active_seasons:
            if not season.round:
                continue
                
            round_obj = season.round
            contest_id = round_obj.contest_id
            contest = round_obj.contest
            
            # Check promotion criteria based on level
            next_level = None
            limit = 5
            should_promote = False
            
            if season.level == SeasonLevel.CITY:
                # City -> Country
                if round_obj.city_season_end_date and round_obj.city_season_end_date <= today:
                    should_promote = True
                elif round_obj.country_season_start_date and round_obj.country_season_start_date <= today:
                    should_promote = True
                next_level = SeasonLevel.COUNTRY
                
            elif season.level == SeasonLevel.COUNTRY:
                # Country -> Regional
                if round_obj.country_season_end_date and round_obj.country_season_end_date <= today:
                    should_promote = True
                elif round_obj.regional_start_date and round_obj.regional_start_date <= today:
                    should_promote = True
                next_level = SeasonLevel.REGIONAL
                
            elif season.level == SeasonLevel.REGIONAL:
                # Regional -> ...
                if contest.voting_type_id is None:
                     # Participation: Regional -> Global
                    if round_obj.regional_end_date and round_obj.regional_end_date <= today:
                        should_promote = True
                    elif round_obj.global_start_date and round_obj.global_start_date <= today:
                        should_promote = True
                    next_level = SeasonLevel.GLOBAL
                else:
                    # Nomination: Regional -> Continent
                    if round_obj.regional_end_date and round_obj.regional_end_date <= today:
                        should_promote = True
                    elif round_obj.continental_start_date and round_obj.continental_start_date <= today:
                        should_promote = True
                    next_level = SeasonLevel.CONTINENT
                    
            elif season.level == SeasonLevel.CONTINENT:
                # Continent -> Global
                if round_obj.continental_end_date and round_obj.continental_end_date <= today:
                    should_promote = True
                elif round_obj.global_start_date and round_obj.global_start_date <= today:
                    should_promote = True
                next_level = SeasonLevel.GLOBAL
            
            if should_promote and next_level:
                # Check duplication
                existing_next = db.query(ContestSeason).filter(
                    and_(
                        ContestSeason.round_id == round_obj.id,
                        ContestSeason.level == next_level
                    )
                ).first()
                
                if not existing_next:
                    result = SeasonMigrationService.promote_to_next_level(
                        db, season.level, next_level, contest_id, limit=limit
                    )
                    results.append({
                        "contest_id": contest_id, 
                        "round_id": round_obj.id, 
                        "action": f"promote_{season.level.value}_to_{next_level.value}", 
                        "result": result
                    })

        return {
            "processed": len(results),
            "results": results,
            "contest_status_updates": status_update_result
        }


# Instance du service
season_migration_service = SeasonMigrationService()
