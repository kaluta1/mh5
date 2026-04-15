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
from app.models.voting import ContestantShare, ContestLike, ContestComment, PageView
from app.models.round import Round, RoundStatus


class SeasonMigrationService:
    """Service pour gérer les migrations de saisons"""

    @staticmethod
    def _engagement_by_contestant(db: Session, contestant_ids: List[int]) -> Dict[int, Dict[str, int]]:
        """
        Build engagement metrics used for deterministic winner tie-breaks.
        Order required by business rules:
        stars(points) -> shares -> likes -> comments -> views -> first contestant.
        """
        if not contestant_ids:
            return {}

        shares_rows = db.query(
            ContestantShare.contestant_id,
            func.count(ContestantShare.id).label("shares_count"),
        ).filter(
            ContestantShare.contestant_id.in_(contestant_ids)
        ).group_by(
            ContestantShare.contestant_id
        ).all()

        likes_rows = db.query(
            ContestLike.contestant_id,
            func.count(ContestLike.id).label("likes_count"),
        ).filter(
            ContestLike.contestant_id.in_(contestant_ids)
        ).group_by(
            ContestLike.contestant_id
        ).all()

        comments_rows = db.query(
            ContestComment.contestant_id,
            func.count(ContestComment.id).label("comments_count"),
        ).filter(
            ContestComment.contestant_id.in_(contestant_ids)
        ).group_by(
            ContestComment.contestant_id
        ).all()

        views_rows = db.query(
            PageView.contestant_id,
            func.count(PageView.id).label("views_count"),
        ).filter(
            PageView.contestant_id.in_(contestant_ids)
        ).group_by(
            PageView.contestant_id
        ).all()

        shares_by_id = {r.contestant_id: int(r.shares_count or 0) for r in shares_rows}
        likes_by_id = {r.contestant_id: int(r.likes_count or 0) for r in likes_rows}
        comments_by_id = {r.contestant_id: int(r.comments_count or 0) for r in comments_rows}
        views_by_id = {r.contestant_id: int(r.views_count or 0) for r in views_rows}

        out: Dict[int, Dict[str, int]] = {}
        for cid in contestant_ids:
            out[cid] = {
                "shares": shares_by_id.get(cid, 0),
                "likes": likes_by_id.get(cid, 0),
                "comments": comments_by_id.get(cid, 0),
                "views": views_by_id.get(cid, 0),
            }
        return out

    @staticmethod
    def _ensure_source_season_links(db: Session, contest_id: int, season_id: int) -> int:
        """
        Repair missing contestant-season links for a source season.
        This handles data states where votes/contestants exist but ContestantSeason links are missing.
        Returns number of links created/reactivated.
        """
        current_count = db.query(ContestantSeason).filter(
            and_(
                ContestantSeason.season_id == season_id,
                ContestantSeason.is_active == True,
            )
        ).count()
        if current_count > 0:
            return 0

        # Prefer contestants that already have votes in this contest/season.
        voted_ids_rows = db.query(ContestantVoting.contestant_id).filter(
            and_(
                ContestantVoting.contest_id == contest_id,
                ContestantVoting.season_id == season_id,
            )
        ).distinct().all()
        candidate_ids = [row[0] for row in voted_ids_rows]

        # Fallback to active contest contestants from legacy linkage.
        if not candidate_ids:
            candidate_ids = [
                c.id
                for c in db.query(Contestant).filter(
                    and_(
                        Contestant.season_id == contest_id,
                        Contestant.is_active == True,
                        Contestant.is_deleted == False,
                    )
                ).all()
            ]

        if not candidate_ids:
            return 0

        repaired = 0
        for cid in candidate_ids:
            contestant = db.query(Contestant).filter(Contestant.id == cid).first()
            if not contestant:
                continue
            contestant.is_qualified = True
            existing = db.query(ContestantSeason).filter(
                and_(
                    ContestantSeason.contestant_id == cid,
                    ContestantSeason.season_id == season_id,
                )
            ).first()
            if existing:
                if not existing.is_active:
                    existing.is_active = True
                    existing.joined_at = datetime.utcnow()
                    repaired += 1
            else:
                db.add(
                    ContestantSeason(
                        contestant_id=cid,
                        season_id=season_id,
                        joined_at=datetime.utcnow(),
                        is_active=True,
                    )
                )
                repaired += 1
        db.flush()
        return repaired
    
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
        contest_id: Optional[int] = None,
        country_filter: Optional[str] = None,
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
        
        logger.info(
            f"get_top_contestants_by_location: season_id={season_id}, "
            f"contest_id={contest_id}, location_field={location_field}, limit={limit}"
        )
        logger.info(f"  - Total contestants linked to season: {total_contestants_in_season}")
        print(f"[Migration]   Total contestants linked to season {season_id}: {total_contestants_in_season}")
        
        # Récupérer tous les contestants actifs et qualifiés de la saison via ContestantSeason
        contestants_query = db.query(Contestant).join(
            ContestantSeason, ContestantSeason.contestant_id == Contestant.id
        ).join(
            User, User.id == Contestant.user_id
        ).filter(
            and_(
                ContestantSeason.season_id == season_id,
                ContestantSeason.is_active == True,
                Contestant.is_active == True,
                Contestant.is_deleted == False,
                Contestant.is_qualified == True
            )
        )
        if contest_id is not None:
            # Keep winner selection scoped to the current contest only.
            contestants_query = contestants_query.filter(Contestant.season_id == contest_id)
        if country_filter:
            contestants_query = contestants_query.filter(
                func.lower(func.trim(User.country)) == country_filter.strip().lower()
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
        
        logger.info(f"  - Qualified contestants with {location_field} location: {len(contestants)}")
        print(f"[Migration]   Qualified contestants with {location_field} location: {len(contestants)}")
        
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
            
            logger.warning(f"  - No contestant found for season {season_id}")
            logger.warning(f"    - Qualified contestants without location: {contestants_without_location}")
            logger.warning(f"    - Non-qualified contestants: {contestants_not_qualified}")
            print(f"[Migration]   No contestant found for season {season_id}")
            print(f"[Migration]     - Qualified contestants without location: {contestants_without_location}")
            print(f"[Migration]     - Non-qualified contestants: {contestants_not_qualified}")
            return {}
        
        # Récupérer les points par contestant depuis ContestantVoting.
        # Primary: contest+season (strict migration scope)
        # Fallback: contest only (legacy data where season_id on votes may drift)
        points_query = db.query(
            ContestantVoting.contestant_id,
            func.coalesce(func.sum(ContestantVoting.points), 0).label('total_points'),
            func.count(ContestantVoting.id).label('vote_count')
        )
        if contest_id is not None:
            points_query = points_query.filter(
                and_(
                    ContestantVoting.season_id == season_id,
                    ContestantVoting.contest_id == contest_id,
                )
            )
        else:
            points_query = points_query.filter(ContestantVoting.season_id == season_id)
        points_data = points_query.group_by(ContestantVoting.contestant_id).all()

        if not points_data and contest_id is not None:
            logger.warning(
                f"  - No vote points found with season+contest scope "
                f"(season_id={season_id}, contest_id={contest_id}); fallback to contest-only scope"
            )
            points_data = db.query(
                ContestantVoting.contestant_id,
                func.coalesce(func.sum(ContestantVoting.points), 0).label('total_points'),
                func.count(ContestantVoting.id).label('vote_count')
            ).filter(
                ContestantVoting.contest_id == contest_id
            ).group_by(
                ContestantVoting.contestant_id
            ).all()
        
        points_by_contestant = {p.contestant_id: p.total_points for p in points_data}
        votes_by_contestant = {p.contestant_id: p.vote_count for p in points_data}
        logger.info(f"  - Points/Votes found for {len(points_by_contestant)} contestants")
        print(f"[Migration]   Points/Votes found for {len(points_by_contestant)} contestants")
        
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
        
        contestant_ids = [c.id for c in contestants]
        engagement_by_id = SeasonMigrationService._engagement_by_contestant(db, contestant_ids)

        # Trier et limiter pour chaque localisation
        result = {}
        logger.info(f"  - Groups by location: {len(grouped)}")
        for location_value, location_contestants in grouped.items():
            # Business winner order:
            # 1) total stars(points), 2) shares, 3) likes, 4) comments, 5) views, 6) first contestant
            sorted_contestants = sorted(
                location_contestants,
                key=lambda c: (
                    points_by_contestant.get(c.id, 0),
                    engagement_by_id.get(c.id, {}).get("shares", 0),
                    engagement_by_id.get(c.id, {}).get("likes", 0),
                    engagement_by_id.get(c.id, {}).get("comments", 0),
                    engagement_by_id.get(c.id, {}).get("views", 0),
                    -(c.id or 0),
                ),
                reverse=True
            )
            
            # Prendre les N premiers (ou tous si moins de N)
            selected = sorted_contestants[:limit]
            result[location_value] = selected
            logger.info(f"    - {location_value}: {len(selected)}/{len(location_contestants)} contestants selected")
            print(f"[Migration]     {location_value}: {len(selected)}/{len(location_contestants)} contestants")
        
        total_selected = sum(len(contestants) for contestants in result.values())
        logger.info(f"  - Total selected: {total_selected} contestants")
        print(f"[Migration]   Total selected: {total_selected} contestants")
        
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
            # Utiliser les dates de la saison city du round (pas du contest car NULL)
            start_date = round_obj.city_season_start_date
            end_date = round_obj.city_season_end_date
            
            if not start_date or not end_date:
                # Fallback : calculer à partir de voting_start_date du round
                start_date = round_obj.voting_start_date
                if isinstance(start_date, date) and not isinstance(start_date, datetime):
                    start_date = datetime.combine(start_date, datetime.min.time())
                if start_date:
                    end_date = start_date + timedelta(days=30)
                else:
                    # Dernier fallback: mois suivant
                    now = datetime.utcnow()
                    start_date = now
                    end_date = now + timedelta(days=30)
            
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
        limit: int = 5,  # 5 pour tous sauf GLOBAL (3)
        from_season_id: Optional[int] = None,
    ) -> dict:
        """
        Promouvoit les meilleurs contestants d'un niveau vers le niveau supérieur.
        Pour CITY/COUNTRY/REGIONAL/CONTINENTAL : 5 premiers par localisation
        Pour GLOBAL : 3 premiers au total
        """
        # Récupérer la saison source via le lien contest-season.
        # If from_season_id is provided, force that season to avoid ambiguity when
        # multiple active links exist for the same contest/level.
        query = db.query(ContestSeasonLink).join(ContestSeason).filter(
            and_(
                ContestSeasonLink.contest_id == contest_id,
                ContestSeason.level == from_level,
                ContestSeason.is_deleted == False,
                ContestSeasonLink.is_active == True
            )
        )
        if from_season_id is not None:
            query = query.filter(ContestSeasonLink.season_id == from_season_id)
        else:
            # deterministic fallback for legacy calls
            query = query.order_by(ContestSeasonLink.linked_at.desc(), ContestSeasonLink.id.desc())
        contest_season_link = query.first()
        
        import logging
        logger = logging.getLogger(__name__)
        
        if not contest_season_link:
            error_msg = f"No active season found for level {from_level.value} and contest {contest_id}"
            logger.error(error_msg)
            print(f"[Migration] ERROR: {error_msg}")
            return {"error": error_msg}
        
        from_season = contest_season_link.season
        logger.info(f"Promotion from {from_level.value} to {to_level.value} for contest {contest_id}")
        logger.info(f"  - Source season: {from_season.id} (level {from_level.value})")
        print(f"[Migration] Promotion contest {contest_id} from {from_level.value} to {to_level.value}")
        print(f"[Migration]   Source season: {from_season.id}")

        repaired_links = SeasonMigrationService._ensure_source_season_links(
            db=db,
            contest_id=contest_id,
            season_id=from_season.id,
        )
        if repaired_links > 0:
            logger.warning(
                f"  - Auto-repaired missing source season links: {repaired_links} "
                f"(contest {contest_id}, season {from_season.id})"
            )
            print(
                f"[Migration]   Auto-repaired source season links: {repaired_links} "
                f"(contest {contest_id}, season {from_season.id})"
            )
        
        # Sélectionner les contestants selon le niveau (sans dépendre des stages)
        selected_contestants = []
        
        if to_level == SeasonLevel.GLOBAL:
            # For GLOBAL: rank all active contestants in the source season.
            # Votes in the current season may be zero; in that case, tie-break
            # still relies on shares/likes/comments/views and then lowest id.
            season_contestants = db.query(Contestant).join(
                ContestantSeason
            ).filter(
                and_(
                    ContestantSeason.season_id == from_season.id,
                    ContestantSeason.is_active == True,
                    Contestant.is_active == True,
                    Contestant.is_deleted == False,
                    Contestant.is_qualified == True
                )
            ).all()

            contestant_ids = [c.id for c in season_contestants]
            if contestant_ids:
                vote_counts = db.query(
                    ContestantVoting.contestant_id,
                    func.coalesce(func.sum(ContestantVoting.points), 0).label('total_points')
                ).filter(
                    and_(
                        ContestantVoting.season_id == from_season.id,
                        ContestantVoting.contestant_id.in_(contestant_ids)
                    )
                ).group_by(
                    ContestantVoting.contestant_id
                ).all()
                points_dict = {vc.contestant_id: vc.total_points for vc in vote_counts}
                engagement_by_id = SeasonMigrationService._engagement_by_contestant(db, contestant_ids)

                ranked = sorted(
                    season_contestants,
                    key=lambda c: (
                        points_dict.get(c.id, 0),
                        engagement_by_id.get(c.id, {}).get("shares", 0),
                        engagement_by_id.get(c.id, {}).get("likes", 0),
                        engagement_by_id.get(c.id, {}).get("comments", 0),
                        engagement_by_id.get(c.id, {}).get("views", 0),
                        -(c.id or 0),
                    ),
                    reverse=True
                )
                selected_contestants = ranked[:limit]
            else:
                selected_contestants = []

            logger.info(f"  - {len(selected_contestants)} contestants selected for GLOBAL")
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
            logger.info(f"  - Selecting top contestants by {location_field} (limit: {limit})")
            grouped_contestants = SeasonMigrationService.get_top_contestants_by_location(
                db, from_season.id, location_field, contest_id=contest_id, limit=limit, stage_id=None
            )
            
            logger.info(f"  - Groups found: {len(grouped_contestants)} locations")
            for location, contestants in grouped_contestants.items():
                logger.info(f"    - {location}: {len(contestants)} contestants")
            
            # Flatten la liste
            for location_contestants in grouped_contestants.values():
                selected_contestants.extend(location_contestants)
        
        logger.info(f"  - Total contestants selected: {len(selected_contestants)}")
        print(f"[Migration]   Contestants selected: {len(selected_contestants)}")
        
        if len(selected_contestants) == 0:
            # Not a failure: calendar may say "promote" while nobody qualified in this season yet.
            # Return a success-shaped payload so schedulers log a skip, not ERROR.
            msg = f"No contestants to promote from {from_level.value} (season_id: {from_season.id})"
            logger.warning(msg)
            print(f"[Migration] WARNING: {msg}")
            return {
                "message": msg,
                "skipped": True,
                "from_season_id": from_season.id,
                "promoted_count": 0,
                "promoted_contestant_ids": [],
            }
        
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
        logger.info(f"  - Destination season: {to_season.id} (level {to_level.value})")
        print(f"[Migration]   Destination season: {to_season.id}")
        
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
        
        logger.info(f"Promoted contestants ({len(promoted_contestant_ids)}): {promoted_contestant_ids}")
        print(f"[Migration] Promoted contestants ({len(promoted_contestant_ids)}): {promoted_contestant_ids}")
        
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
            logger.info(f"  - Commit successful")
            print(f"[Migration]   Commit successful")
        except Exception as e:
            logger.error(f"  - Erreur lors du commit: {e}", exc_info=True)
            print(f"[Migration] ERROR lors du commit: {e}")
            db.rollback()
            raise
        
        logger.info(f"Migration successful: {len(selected_contestants)} contestants promoted from {from_level.value} to {to_level.value}")
        logger.info(f"  - Contest {contest_id} lié à la saison {to_season.id} (niveau {to_level.value})")
        logger.info(f"  - Promoted contestants: {promoted_contestant_ids}")
        print(f"[Migration] ✓ Migration successful: Contest {contest_id} promoted from {from_level.value} to {to_level.value}")
        print(f"[Migration]   Promoted contestants ({len(promoted_contestant_ids)}): {promoted_contestant_ids}")
        
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
        Utilise round_contests (N:N) car Round.contest_id est toujours NULL.
        
        Lifecycle d'un round :
        1. Création du round (1er du mois) → is_submission_open=True, is_voting_open=False
        2. Fin du mois → is_submission_open=False 
        3. Mois suivant (M+1) → is_voting_open=True, migration vers CITY (participation) ou COUNTRY (nomination)
        4. Fin M+1 → top 5 par ville/pays promus vers le niveau suivant
        5. M+2 → top 5 par pays promus vers régional
        6. M+3 → top 5 par région promus vers continental
        7. M+4 → top 5 par continent promus vers global
        8. M+5 → fin, round terminé
        """
        import logging
        logger = logging.getLogger(__name__)
        from app.models.round import round_contests as rc_table
        from app.services.contest_status import contest_status_service
        
        results = []
        today = date.today()
        logger.info(f"Checking season migrations for date: {today}")
        print(f"[Migration] Checking migrations for {today}")
        
        # ============================================================
        # STEP 0: Auto-close submission / open voting on rounds
        # ============================================================
        active_rounds = db.query(Round).filter(
            Round.status != RoundStatus.CANCELLED
        ).all()
        
        for round_obj in active_rounds:
            changed = False
            
            # Fermer la soumission si la date est passée
            if (round_obj.is_submission_open and 
                round_obj.submission_end_date and 
                today > round_obj.submission_end_date):
                round_obj.is_submission_open = False
                changed = True
                logger.info(f"  Round {round_obj.id} ({round_obj.name}): submission closed")
                print(f"[Migration] Round {round_obj.id}: soumission fermée")
            
            # Ouvrir le vote si la date est atteinte
            if (not round_obj.is_voting_open and 
                round_obj.voting_start_date and 
                today >= round_obj.voting_start_date and
                round_obj.voting_end_date and
                today <= round_obj.voting_end_date):
                round_obj.is_voting_open = True
                changed = True
                logger.info(f"  Round {round_obj.id} ({round_obj.name}): voting opened")
                print(f"[Migration] Round {round_obj.id}: vote ouvert")
            
            # Fermer le vote si la date est passée
            if (round_obj.is_voting_open and 
                round_obj.voting_end_date and 
                today > round_obj.voting_end_date):
                round_obj.is_voting_open = False
                round_obj.status = RoundStatus.COMPLETED
                changed = True
                logger.info(f"  Round {round_obj.id} ({round_obj.name}): voting closed, round completed")
                print(f"[Migration] Round {round_obj.id}: vote fermé, round terminé")
            
            if changed:
                db.commit()
        
        # Mettre à jour les statuts des contests (basé sur les rounds via round_contests)
        try:
            contest_status_service.update_contest_statuses(db)
        except Exception as e:
            logger.warning(f"Error updating contest statuses: {e}")
        
        # ============================================================
        # STEP 1: Init seasons - PARTICIPATION → CITY, NOMINATION → COUNTRY
        # Utilise round_contests (N:N) pour trouver les contests liés aux rounds
        # ============================================================
        
        # Récupérer tous les rounds dont la city_season_start_date est atteinte
        rounds_ready = db.query(Round).filter(
            and_(
                Round.city_season_start_date <= today,
                Round.status != RoundStatus.CANCELLED
            )
        ).all()
        
        for round_obj in rounds_ready:
            # Trouver les contests liés à ce round via round_contests
            from sqlalchemy import select
            contest_ids_result = db.execute(
                select(rc_table.c.contest_id).where(rc_table.c.round_id == round_obj.id)
            ).fetchall()
            contest_ids = [r[0] for r in contest_ids_result]
            
            for cid in contest_ids:
                contest = db.query(Contest).filter(Contest.id == cid).first()
                if not contest:
                    continue
                
                contest_mode = getattr(contest, 'contest_mode', None)
                
                if contest_mode == "participation":
                    # PARTICIPATION → init CITY
                    existing_link = db.query(ContestSeasonLink).join(ContestSeason).filter(
                        and_(
                            ContestSeasonLink.contest_id == cid,
                            ContestSeason.round_id == round_obj.id,
                            ContestSeason.level == SeasonLevel.CITY
                        )
                    ).first()
                    
                    if not existing_link:
                        try:
                            result = SeasonMigrationService.migrate_to_city_season(db, cid, round_obj.id)
                            results.append({"contest_id": cid, "round_id": round_obj.id, "action": "init_participation_city", "result": result})
                        except Exception as e:
                            logger.error(f"Error migrating contest {cid} to city: {e}")
                            results.append({"contest_id": cid, "round_id": round_obj.id, "action": "init_participation_city", "result": {"error": str(e)}})
                
                elif contest_mode == "nomination":
                    # NOMINATION → init COUNTRY
                    existing_link = db.query(ContestSeasonLink).join(ContestSeason).filter(
                        and_(
                            ContestSeasonLink.contest_id == cid,
                            ContestSeason.round_id == round_obj.id,
                            ContestSeason.level == SeasonLevel.COUNTRY
                        )
                    ).first()
                    
                    if not existing_link:
                        try:
                            result = SeasonMigrationService.migrate_to_country_start(db, cid, round_obj.id)
                            results.append({"contest_id": cid, "round_id": round_obj.id, "action": "init_nomination_country", "result": result})
                        except Exception as e:
                            logger.error(f"Error migrating contest {cid} to country: {e}")
                            results.append({"contest_id": cid, "round_id": round_obj.id, "action": "init_nomination_country", "result": {"error": str(e)}})
        
        # ============================================================
        # STEP 2: Promotions - basé sur les saisons actives liées aux rounds
        # ============================================================
        active_seasons = db.query(ContestSeason).filter(
            and_(
                ContestSeason.is_deleted == False,
                ContestSeason.round_id.isnot(None)
            )
        ).all()
        
        for season in active_seasons:
            if not season.round:
                continue
            
            round_obj = season.round
            if round_obj.status == RoundStatus.CANCELLED:
                continue
            
            # Trouver le contest lié à cette saison via ContestSeasonLink
            contest_link = db.query(ContestSeasonLink).filter(
                and_(
                    ContestSeasonLink.season_id == season.id,
                    ContestSeasonLink.is_active == True
                )
            ).first()
            
            if not contest_link:
                continue
            
            contest_id = contest_link.contest_id
            
            # Déterminer si une promotion est nécessaire
            next_level = None
            limit = 5
            should_promote = False
            
            if season.level == SeasonLevel.CITY:
                if round_obj.city_season_end_date and round_obj.city_season_end_date <= today:
                    should_promote = True
                elif round_obj.country_season_start_date and round_obj.country_season_start_date <= today:
                    should_promote = True
                next_level = SeasonLevel.COUNTRY
                
            elif season.level == SeasonLevel.COUNTRY:
                if round_obj.country_season_end_date and round_obj.country_season_end_date <= today:
                    should_promote = True
                elif round_obj.regional_start_date and round_obj.regional_start_date <= today:
                    should_promote = True
                next_level = SeasonLevel.REGIONAL
                
            elif season.level == SeasonLevel.REGIONAL:
                if round_obj.regional_end_date and round_obj.regional_end_date <= today:
                    should_promote = True
                elif round_obj.continental_start_date and round_obj.continental_start_date <= today:
                    should_promote = True
                next_level = SeasonLevel.CONTINENT
                    
            elif season.level == SeasonLevel.CONTINENT:
                if round_obj.continental_end_date and round_obj.continental_end_date <= today:
                    should_promote = True
                elif round_obj.global_start_date and round_obj.global_start_date <= today:
                    should_promote = True
                next_level = SeasonLevel.GLOBAL
            
            if should_promote and next_level:
                # Vérifier qu'on n'a pas déjà promu
                existing_next = db.query(ContestSeason).filter(
                    and_(
                        ContestSeason.round_id == round_obj.id,
                        ContestSeason.level == next_level
                    )
                ).first()
                
                if not existing_next:
                    try:
                        result = SeasonMigrationService.promote_to_next_level(
                            db, season.level, next_level, contest_id, limit=limit
                        )
                        results.append({
                            "contest_id": contest_id, 
                            "round_id": round_obj.id, 
                            "action": f"promote_{season.level.value}_to_{next_level.value}", 
                            "result": result
                        })
                    except Exception as e:
                        logger.error(f"Error promoting contest {contest_id}: {e}")
                        results.append({
                            "contest_id": contest_id,
                            "round_id": round_obj.id,
                            "action": f"promote_{season.level.value}_to_{next_level.value}",
                            "result": {"error": str(e)}
                        })

        processed = len(results)
        if processed > 0:
            print(f"[Migration] Processed {processed} migrations")
        else:
            print(f"[Migration] No migrations needed")
        
        return {
            "processed": processed,
            "results": results
        }


# Instance du service
season_migration_service = SeasonMigrationService()
