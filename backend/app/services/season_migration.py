"""
Service de gestion des migrations de saisons pour les contests.
Gère la progression automatique des contestants à travers les différents niveaux.
"""
from datetime import datetime, timedelta, date
from typing import List, Optional
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
from app.models.voting import Vote, VoteStatus


class SeasonMigrationService:
    """Service pour gérer les migrations de saisons"""
    
    @staticmethod
    def get_or_create_season(
        db: Session, 
        level: SeasonLevel, 
        title: Optional[str] = None
    ) -> ContestSeason:
        """
        Récupère ou crée une saison pour un niveau donné.
        Une seule saison globale par niveau.
        """
        if title is None:
            title = f"Saison {level.value.capitalize()}"
        
        # Chercher une saison existante pour ce niveau
        season = db.query(ContestSeason).filter(
            and_(
                ContestSeason.level == level,
                ContestSeason.is_deleted == False
            )
        ).first()
        
        if not season:
            season = ContestSeason(
                title=title,
                level=level,
                is_deleted=False
            )
            db.add(season)
            db.commit()
            db.refresh(season)
        
        return season
    
    @staticmethod
    def migrate_to_city_season(db: Session, contest_id: int) -> dict:
        """
        Migre tous les contestants d'un contest vers la saison CITY
        quand submission_end_date arrive.
        """
        contest = db.query(Contest).filter(Contest.id == contest_id).first()
        if not contest:
            return {"error": "Contest not found"}
        
        # Vérifier si la migration a déjà été faite
        existing_link = db.query(ContestSeasonLink).filter(
            ContestSeasonLink.contest_id == contest_id,
            ContestSeasonLink.is_active == True
        ).first()
        
        if existing_link:
            return {"message": "Migration already done", "season_id": existing_link.season_id}
        
        # Récupérer ou créer la saison CITY
        city_season = SeasonMigrationService.get_or_create_season(
            db, 
            SeasonLevel.CITY,
            title=f"Saison City - {contest.name}"
        )
        
        # Récupérer tous les contestants actifs du contest
        contestants = db.query(Contestant).filter(
            and_(
                Contestant.season_id == contest_id,  # Les contestants sont liés au contest initialement
                Contestant.is_active == True,
                Contestant.is_deleted == False
            )
        ).all()
        
        migrated_count = 0
        for contestant in contestants:
            # Vérifier si le lien existe déjà
            existing_contestant_season = db.query(ContestantSeason).filter(
                and_(
                    ContestantSeason.contestant_id == contestant.id,
                    ContestantSeason.season_id == city_season.id
                )
            ).first()
            
            if not existing_contestant_season:
                # Créer le lien contestant-season
                contestant_season = ContestantSeason(
                    contestant_id=contestant.id,
                    season_id=city_season.id,
                    joined_at=datetime.utcnow(),
                    is_active=True
                )
                db.add(contestant_season)
                migrated_count += 1
        
        # Mettre à jour le contest : changer le level et créer le lien
        contest.level = "city"
        contest_season_link = ContestSeasonLink(
            contest_id=contest.id,
            season_id=city_season.id,
            linked_at=datetime.utcnow(),
            is_active=True
        )
        db.add(contest_season_link)
        
        # Créer le stage CITY pour cette saison
        city_stage = db.query(ContestStage).filter(
            and_(
                ContestStage.season_id == city_season.id,
                ContestStage.stage_level == ContestStageLevel.CITY
            )
        ).first()
        
        if not city_stage:
            # Calculer les dates : 1 mois de vote pour CITY
            start_date = contest.voting_start_date
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
        
        return {
            "message": f"Migrated {migrated_count} contestants to CITY season",
            "season_id": city_season.id,
            "contestants_migrated": migrated_count
        }
    
    @staticmethod
    def get_top_contestants_by_votes(
        db: Session, 
        season_id: int, 
        stage_level: ContestStageLevel,
        limit: int = 5
    ) -> List[Contestant]:
        """
        Récupère les N meilleurs contestants d'une saison basés sur total_votes
        dans ContestantRanking pour un stage donné.
        """
        # Récupérer le stage
        stage = db.query(ContestStage).filter(
            and_(
                ContestStage.season_id == season_id,
                ContestStage.stage_level == stage_level
            )
        ).first()
        
        if not stage:
            return []
        
        # Récupérer les rankings triés par total_votes décroissant
        rankings = db.query(ContestantRanking).filter(
            ContestantRanking.stage_id == stage.id
        ).order_by(
            ContestantRanking.total_votes.desc()
        ).limit(limit).all()
        
        # Récupérer les contestants
        contestant_ids = [r.contestant_id for r in rankings]
        contestants = db.query(Contestant).filter(
            Contestant.id.in_(contestant_ids)
        ).all()
        
        # Trier selon l'ordre des rankings
        contestant_dict = {c.id: c for c in contestants}
        return [contestant_dict[r.contestant_id] for r in rankings if r.contestant_id in contestant_dict]
    
    @staticmethod
    def promote_to_next_level(
        db: Session,
        from_level: SeasonLevel,
        to_level: SeasonLevel,
        contest_id: int
    ) -> dict:
        """
        Promouvoit les 5 meilleurs contestants d'un niveau vers le niveau supérieur.
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
        
        if not contest_season_link:
            return {"error": f"No active season found for level {from_level.value} and contest {contest_id}"}
        
        from_season = contest_season_link.season
        
        # Mapper le niveau vers ContestStageLevel
        stage_level_map = {
            SeasonLevel.CITY: ContestStageLevel.CITY,
            SeasonLevel.COUNTRY: ContestStageLevel.COUNTRY,
            SeasonLevel.REGIONAL: ContestStageLevel.REGIONAL,  # Note: vérifier si REGIONAL existe dans ContestStageLevel
            SeasonLevel.CONTINENT: ContestStageLevel.CONTINENTAL,
            SeasonLevel.GLOBAL: ContestStageLevel.GLOBAL
        }
        
        from_stage_level = stage_level_map.get(from_level)
        if not from_stage_level:
            return {"error": f"Invalid level: {from_level.value}"}
        
        # Récupérer les 5 meilleurs
        top_contestants = SeasonMigrationService.get_top_contestants_by_votes(
            db, from_season.id, from_stage_level, limit=5
        )
        
        if len(top_contestants) == 0:
            return {"message": f"No contestants to promote from {from_level.value}"}
        
        # Récupérer ou créer la saison destination
        to_season = SeasonMigrationService.get_or_create_season(
            db,
            to_level,
            title=f"Saison {to_level.value.capitalize()} - {db.query(Contest).filter(Contest.id == contest_id).first().name}"
        )
        
        # Désactiver les liens dans l'ancienne saison pour les promus
        for contestant in top_contestants:
            old_link = db.query(ContestantSeason).filter(
                and_(
                    ContestantSeason.contestant_id == contestant.id,
                    ContestantSeason.season_id == from_season.id,
                    ContestantSeason.is_active == True
                )
            ).first()
            
            if old_link:
                old_link.is_active = False
            
            # Créer le nouveau lien
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
        
        # Mettre à jour le contest : changer le level
        contest = db.query(Contest).filter(Contest.id == contest_id).first()
        if contest:
            contest.level = to_level.value
        
        # Mettre à jour le lien contest-season
        old_contest_link = db.query(ContestSeasonLink).filter(
            and_(
                ContestSeasonLink.contest_id == contest_id,
                ContestSeasonLink.season_id == from_season.id,
                ContestSeasonLink.is_active == True
            )
        ).first()
        
        if old_contest_link:
            old_contest_link.is_active = False
        
        # Créer le nouveau lien
        new_contest_link = ContestSeasonLink(
            contest_id=contest_id,
            season_id=to_season.id,
            linked_at=datetime.utcnow(),
            is_active=True
        )
        db.add(new_contest_link)
        
        # Créer le stage pour la nouvelle saison
        to_stage_level = stage_level_map.get(to_level)
        if to_stage_level:
            existing_stage = db.query(ContestStage).filter(
                and_(
                    ContestStage.season_id == to_season.id,
                    ContestStage.stage_level == to_stage_level
                )
            ).first()
            
            if not existing_stage:
                # Calculer les dates : 1 mois après la fin du stage précédent
                from_stage = db.query(ContestStage).filter(
                    and_(
                        ContestStage.season_id == from_season.id,
                        ContestStage.stage_level == from_stage_level
                    )
                ).first()
                
                if from_stage:
                    start_date = from_stage.end_date
                else:
                    start_date = datetime.utcnow()
                
                end_date = start_date + timedelta(days=30)
                
                new_stage = ContestStage(
                    season_id=to_season.id,
                    stage_level=to_stage_level,
                    status=ContestStatus.VOTING_ACTIVE,
                    start_date=start_date,
                    end_date=end_date,
                    max_qualifiers=5,
                    min_participants=2
                )
                db.add(new_stage)
        
        db.commit()
        
        return {
            "message": f"Promoted {len(top_contestants)} contestants from {from_level.value} to {to_level.value}",
            "from_season_id": from_season.id,
            "to_season_id": to_season.id,
            "promoted_count": len(top_contestants),
            "promoted_contestant_ids": [c.id for c in top_contestants]
        }
    
    @staticmethod
    def check_and_process_migrations(db: Session) -> dict:
        """
        Vérifie et traite toutes les migrations nécessaires pour tous les contests actifs.
        Cette fonction doit être appelée régulièrement (par un scheduler).
        Met aussi à jour automatiquement les statuts des contests (submission/voting open).
        """
        from app.services.contest_status import contest_status_service
        
        # Mettre à jour les statuts des contests en premier
        status_update_result = contest_status_service.update_contest_statuses(db)
        
        results = []
        today = datetime.utcnow().date()
        
        # 1. Vérifier les contests dont submission_end_date est arrivé
        contests_to_migrate = db.query(Contest).filter(
            and_(
                Contest.submission_end_date <= today,
                Contest.is_deleted == False,
                Contest.is_active == True
            )
        ).all()
        
        for contest in contests_to_migrate:
            # Vérifier si déjà migré
            existing_link = db.query(ContestSeasonLink).filter(
                ContestSeasonLink.contest_id == contest.id,
                ContestSeasonLink.is_active == True
            ).first()
            
            if not existing_link:
                result = SeasonMigrationService.migrate_to_city_season(db, contest.id)
                results.append({
                    "contest_id": contest.id,
                    "action": "migrate_to_city",
                    "result": result
                })
        
        # 2. Vérifier les promotions entre niveaux
        # CITY -> COUNTRY (1 mois après la fin de CITY)
        city_seasons = db.query(ContestSeason).join(
            ContestSeasonLink
        ).join(
            Contest
        ).filter(
            and_(
                ContestSeason.level == SeasonLevel.CITY,
                ContestSeason.is_deleted == False,
                Contest.is_deleted == False,
                ContestSeasonLink.is_active == True
            )
        ).all()
        
        for city_season in city_seasons:
            city_stage = db.query(ContestStage).filter(
                and_(
                    ContestStage.season_id == city_season.id,
                    ContestStage.stage_level == ContestStageLevel.CITY
                )
            ).first()
            
            if city_stage and city_stage.end_date.date() <= today:
                # Vérifier si déjà promu
                contest_link = db.query(ContestSeasonLink).filter(
                    ContestSeasonLink.season_id == city_season.id,
                    ContestSeasonLink.is_active == True
                ).first()
                
                if contest_link:
                    existing_country_link = db.query(ContestSeasonLink).join(
                        ContestSeason
                    ).filter(
                        and_(
                            ContestSeasonLink.contest_id == contest_link.contest_id,
                            ContestSeason.level == SeasonLevel.COUNTRY,
                            ContestSeasonLink.is_active == True
                        )
                    ).first()
                    
                    if not existing_country_link:
                        result = SeasonMigrationService.promote_to_next_level(
                            db, SeasonLevel.CITY, SeasonLevel.COUNTRY, contest_link.contest_id
                        )
                        results.append({
                            "contest_id": contest_link.contest_id,
                            "action": "promote_city_to_country",
                            "result": result
                        })
        
        # COUNTRY -> REGIONAL
        country_seasons = db.query(ContestSeason).join(
            ContestSeasonLink
        ).join(
            Contest
        ).filter(
            and_(
                ContestSeason.level == SeasonLevel.COUNTRY,
                ContestSeason.is_deleted == False,
                Contest.is_deleted == False,
                ContestSeasonLink.is_active == True
            )
        ).all()
        
        for country_season in country_seasons:
            country_stage = db.query(ContestStage).filter(
                and_(
                    ContestStage.season_id == country_season.id,
                    ContestStage.stage_level == ContestStageLevel.COUNTRY
                )
            ).first()
            
            if country_stage and country_stage.end_date.date() <= today:
                contest_link = db.query(ContestSeasonLink).filter(
                    ContestSeasonLink.season_id == country_season.id,
                    ContestSeasonLink.is_active == True
                ).first()
                
                if contest_link:
                    existing_regional_link = db.query(ContestSeasonLink).join(
                        ContestSeason
                    ).filter(
                        and_(
                            ContestSeasonLink.contest_id == contest_link.contest_id,
                            ContestSeason.level == SeasonLevel.REGIONAL,
                            ContestSeasonLink.is_active == True
                        )
                    ).first()
                    
                    if not existing_regional_link:
                        result = SeasonMigrationService.promote_to_next_level(
                            db, SeasonLevel.COUNTRY, SeasonLevel.REGIONAL, contest_link.contest_id
                        )
                        results.append({
                            "contest_id": contest_link.contest_id,
                            "action": "promote_country_to_regional",
                            "result": result
                        })
        
        # REGIONAL -> CONTINENT
        regional_seasons = db.query(ContestSeason).join(
            ContestSeasonLink
        ).join(
            Contest
        ).filter(
            and_(
                ContestSeason.level == SeasonLevel.REGIONAL,
                ContestSeason.is_deleted == False,
                Contest.is_deleted == False,
                ContestSeasonLink.is_active == True
            )
        ).all()
        
        for regional_season in regional_seasons:
            regional_stage = db.query(ContestStage).filter(
                and_(
                    ContestStage.season_id == regional_season.id,
                    ContestStage.stage_level == ContestStageLevel.REGIONAL
                )
            ).first()
            
            if regional_stage and regional_stage.end_date.date() <= today:
                contest_link = db.query(ContestSeasonLink).filter(
                    ContestSeasonLink.season_id == regional_season.id,
                    ContestSeasonLink.is_active == True
                ).first()
                
                if contest_link:
                    existing_continent_link = db.query(ContestSeasonLink).join(
                        ContestSeason
                    ).filter(
                        and_(
                            ContestSeasonLink.contest_id == contest_link.contest_id,
                            ContestSeason.level == SeasonLevel.CONTINENT,
                            ContestSeasonLink.is_active == True
                        )
                    ).first()
                    
                    if not existing_continent_link:
                        result = SeasonMigrationService.promote_to_next_level(
                            db, SeasonLevel.REGIONAL, SeasonLevel.CONTINENT, contest_link.contest_id
                        )
                        results.append({
                            "contest_id": contest_link.contest_id,
                            "action": "promote_regional_to_continent",
                            "result": result
                        })
        
        # CONTINENT -> GLOBAL
        continent_seasons = db.query(ContestSeason).join(
            ContestSeasonLink
        ).join(
            Contest
        ).filter(
            and_(
                ContestSeason.level == SeasonLevel.CONTINENT,
                ContestSeason.is_deleted == False,
                Contest.is_deleted == False,
                ContestSeasonLink.is_active == True
            )
        ).all()
        
        for continent_season in continent_seasons:
            continent_stage = db.query(ContestStage).filter(
                and_(
                    ContestStage.season_id == continent_season.id,
                    ContestStage.stage_level == ContestStageLevel.CONTINENTAL
                )
            ).first()
            
            if continent_stage and continent_stage.end_date.date() <= today:
                contest_link = db.query(ContestSeasonLink).filter(
                    ContestSeasonLink.season_id == continent_season.id,
                    ContestSeasonLink.is_active == True
                ).first()
                
                if contest_link:
                    existing_global_link = db.query(ContestSeasonLink).join(
                        ContestSeason
                    ).filter(
                        and_(
                            ContestSeasonLink.contest_id == contest_link.contest_id,
                            ContestSeason.level == SeasonLevel.GLOBAL,
                            ContestSeasonLink.is_active == True
                        )
                    ).first()
                    
                    if not existing_global_link:
                        result = SeasonMigrationService.promote_to_next_level(
                            db, SeasonLevel.CONTINENT, SeasonLevel.GLOBAL, contest_link.contest_id
                        )
                        results.append({
                            "contest_id": contest_link.contest_id,
                            "action": "promote_continent_to_global",
                            "result": result
                        })
        
        return {
            "processed": len(results),
            "results": results,
            "contest_status_updates": status_update_result
        }


# Instance du service
season_migration_service = SeasonMigrationService()

