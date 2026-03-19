from typing import List, Optional, Dict, Any
from datetime import datetime, date
import json

from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, and_

from app.models.contests import Contestant, ContestSubmission, ContestSeason, ContestantRanking, ContestStage
from app.models.contest import Contest
from app.models.voting import Vote, MyFavorites, ContestLike, ContestComment, ContestantVoting, ContestantReaction, ContestantShare
from app.models.user import User


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
        
        # Récupérer la saison active du contestant via ContestantSeason
        from app.models.contests import ContestSeasonLink, ContestantSeason
        season = None
        contest_id = None
        
        # Récupérer la saison active via ContestantSeason
        contestant_season_link = db.query(ContestantSeason).filter(
            ContestantSeason.contestant_id == id,
            ContestantSeason.is_active == True
        ).first()
        
        if contestant_season_link:
            # Récupérer la saison active
            season = db.query(ContestSeason).filter(
                ContestSeason.id == contestant_season_link.season_id,
                ContestSeason.is_deleted == False
            ).first()
            
            if season:
                # Récupérer le contest_id depuis la saison via ContestSeasonLink
                contest_link = db.query(ContestSeasonLink).filter(
                    ContestSeasonLink.season_id == season.id,
                    ContestSeasonLink.is_active == True
                ).first()
                if contest_link:
                    contest_id = contest_link.contest_id
        
        # Si pas de saison active trouvée, fallback sur l'ancien système
        if not season:
            # Essayer de récupérer la saison directement via season_id
            season = db.query(ContestSeason).filter(ContestSeason.id == contestant.season_id).first()
            if not season:
                # Si season_id est un Contest.id, chercher la saison active via ContestSeasonLink
                contest_link = db.query(ContestSeasonLink).filter(
                    ContestSeasonLink.contest_id == contestant.season_id,
                    ContestSeasonLink.is_active == True
                ).first()
                if contest_link:
                    season = db.query(ContestSeason).filter(
                        ContestSeason.id == contest_link.season_id,
                        ContestSeason.is_deleted == False
                    ).first()
                    if season:
                        contest_id = contest_link.contest_id
        
        # Déterminer le niveau de la saison
        season_level: Optional[str] = None
        if season and hasattr(season, "level") and season.level is not None:
            raw_level = season.level.value if hasattr(season.level, "value") else str(season.level)
            if isinstance(raw_level, str):
                season_level = raw_level.lower()
        
        # Compter les votes avec ContestantVoting par saison
        votes_count = 0
        if season:
            vote_count_query = db.query(func.count(ContestantVoting.id)).filter(
                ContestantVoting.contestant_id == id,
                ContestantVoting.season_id == season.id
            )
            votes_count = vote_count_query.scalar() or 0
        
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
        
        # Récupérer l'URL de la première image pour le contestant
        contestant_image_url = None
        for submission in contestant.submissions:
            if submission.media_type == "image" and (submission.file_url or submission.external_url):
                contestant_image_url = submission.file_url or submission.external_url
                break
        
        # Calculer le rang dynamiquement en fonction des votes et du niveau de la saison
        # On applique les mêmes règles que pour get_contest_with_enriched_contestants :
        # - city    -> classement par ville + pays
        # - country -> classement par pays + continent
        # - regional-> classement par région + continent
        # - continent -> classement par continent
        # - global  -> classement global (tous ensemble)
        rank: Optional[int] = None
        contestants_same_season = []
        contestant_ids = []
        
        if season:
            # Récupérer les contestants de la saison active via ContestantSeason
            contestants_same_season = db.query(Contestant)\
                .join(ContestantSeason)\
                .filter(
                    ContestantSeason.season_id == season.id,
                    ContestantSeason.is_active == True,
                    Contestant.is_deleted == False
                )\
                .options(joinedload(Contestant.user))\
                .all()
            
            contestant_ids = [c.id for c in contestants_same_season]
        else:
            # Fallback : utiliser l'ancien système
            contestants_same_season = db.query(Contestant)\
                .filter(
                    Contestant.season_id == contestant.season_id,
                    Contestant.is_deleted == False
                )\
                .options(joinedload(Contestant.user))\
                .all()
            contestant_ids = [c.id for c in contestants_same_season]

        # Compter les votes pour tous les contestants de la saison (par saison)
        votes_counts = []
        if season:
            votes_counts = (
                db.query(
                    ContestantVoting.contestant_id,
                    func.count(ContestantVoting.id).label("vote_count"),
                )
                .filter(
                    ContestantVoting.contestant_id.in_(contestant_ids),
                    ContestantVoting.season_id == season.id
                )
                .group_by(ContestantVoting.contestant_id)
                .all()
            )

        votes_count_by_contestant: Dict[int, int] = {
            cid: count for cid, count in votes_counts
        }
        for cid in contestant_ids:
            votes_count_by_contestant.setdefault(cid, 0)

        def get_group_key(c: Contestant) -> str:
            if not c.user:
                return "global"
            lvl = (season_level or "global") if isinstance(season_level, str) else "global"
            lvl = lvl.lower()
            country = (c.user.country or "").lower() if getattr(c.user, "country", None) else ""
            city = (c.user.city or "").lower() if getattr(c.user, "city", None) else ""
            continent = (c.user.continent or "").lower() if getattr(c.user, "continent", None) else ""
            region = (getattr(c.user, "region", "") or "").lower()

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
        for c in contestants_same_season:
            key = get_group_key(c)
            groups.setdefault(key, []).append(c.id)

        current_group_key = get_group_key(contestant)
        group_ids = groups.get(current_group_key, contestant_ids)
        ranked_ids = sorted(
            group_ids,
            key=lambda cid: votes_count_by_contestant.get(cid, 0),
            reverse=True,
        )
        for position, cid in enumerate(ranked_ids, start=1):
            if cid == contestant.id:
                rank = position
                break
        
        # Vérifier si l'utilisateur peut voter pour ce contestant dans la saison active
        # IMPORTANT: Le vote est par saison. Si un utilisateur a voté dans la saison CITY,
        # il ne peut plus voter tant qu'on est en CITY. Mais s'il migre vers COUNTRY,
        # il peut voter à nouveau dans la nouvelle saison COUNTRY (même pour le même contestant).
        has_voted = False
        can_vote = False
        vote_restriction_reason = None
        
        # Si pas d'utilisateur authentifié ou pas de saison, can_vote reste False
        if not current_user_id or not season:
            can_vote = False
            has_voted = False
            if not current_user_id:
                vote_restriction_reason = "not_authenticated"
            else:
                vote_restriction_reason = "no_season"
        elif current_user_id == contestant.user_id:
            # L'utilisateur ne peut pas voter pour sa propre candidature
            can_vote = False
            has_voted = False
            vote_restriction_reason = "own_contestant"
        else:
            # Vérifier si l'utilisateur a déjà voté pour ce contestant dans cette saison active
            # IMPORTANT: Un utilisateur peut voter pour plusieurs contestants différents dans la même saison
            # Mais il ne peut pas voter deux fois pour le même contestant dans la même saison
            # Si l'utilisateur a voté pour le contestant X dans la saison CITY, il peut voter pour le contestant Y dans la même saison CITY
            # Mais il ne peut pas voter deux fois pour X dans la même saison CITY
            # S'il migre vers COUNTRY, il peut voter à nouveau pour X dans la nouvelle saison COUNTRY
            existing_vote = db.query(ContestantVoting).filter(
                ContestantVoting.user_id == current_user_id,
                ContestantVoting.contestant_id == contestant.id,  # Vérification par contestant
                ContestantVoting.season_id == season.id  # Vérification par (user_id, contestant_id, season_id)
            ).first()
            
            if existing_vote:
                # L'utilisateur a déjà voté pour ce contestant dans cette saison en cours
                has_voted = True
                can_vote = False
                vote_restriction_reason = "already_voted"
            else:
                # L'utilisateur n'a pas encore voté dans cette saison
                has_voted = False
                
                # Récupérer l'utilisateur pour les restrictions géographiques
                current_user = db.query(User).filter(User.id == current_user_id).first()
                
                if not current_user:
                    can_vote = False
                    vote_restriction_reason = "user_not_found"
                else:
                    # Vérifier les restrictions géographiques selon le niveau de la saison
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
                    
                    geo_ok = True
                    if season_level and contestant.user:
                        lvl = str(season_level).lower()
                        v = current_user
                        u = contestant.user
                        
                        if lvl == "city":
                            country_match = compare_with_unknown(v.country, u.country)
                            if not country_match:
                                geo_ok = False
                                vote_restriction_reason = "different_country"
                            else:
                                city_match = compare_with_unknown(v.city, u.city)
                                if not city_match:
                                    geo_ok = False
                                    vote_restriction_reason = "different_city"
                                else:
                                    geo_ok = True
                        elif lvl == "country":
                            continent_match = compare_with_unknown(v.continent, u.continent)
                            if not continent_match:
                                geo_ok = False
                                vote_restriction_reason = "different_continent"
                            else:
                                country_match = compare_with_unknown(v.country, u.country)
                                if not country_match:
                                    geo_ok = False
                                    vote_restriction_reason = "different_country"
                                else:
                                    geo_ok = True
                        elif lvl in ("regional", "region"):
                            continent_match = compare_with_unknown(v.continent, u.continent)
                            if not continent_match:
                                geo_ok = False
                                vote_restriction_reason = "different_continent"
                            else:
                                v_region = getattr(v, "region", None)
                                u_region = getattr(u, "region", None)
                                region_match = compare_with_unknown(v_region, u_region)
                                if not region_match:
                                    geo_ok = False
                                    vote_restriction_reason = "different_region"
                                else:
                                    geo_ok = True
                        elif lvl == "continent":
                            continent_match = compare_with_unknown(v.continent, u.continent)
                            if not continent_match:
                                geo_ok = False
                                vote_restriction_reason = "different_continent"
                            else:
                                geo_ok = True
                        # Pour "global" ou niveau inconnu, geo_ok reste True
                    
                    can_vote = geo_ok
                    
                    # S'assurer que vote_restriction_reason est défini si can_vote est False
                    if not can_vote and not vote_restriction_reason:
                        vote_restriction_reason = "geographic_restriction"
        
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
        contest_title = None
        contest_image_url = None
        
        if season:
            # Essayer d'abord de récupérer le titre du contest lié via ContestSeasonLink
            from app.models.contests import ContestSeasonLink
            contest_link = db.query(ContestSeasonLink).filter(
                ContestSeasonLink.season_id == season.id,
                ContestSeasonLink.is_active == True
            ).first()
            
            if contest_link:
                from app.models.contest import Contest as MyfavContest
                contest = db.query(MyfavContest).filter(
                    MyfavContest.id == contest_link.contest_id,
                    MyfavContest.is_deleted == False
                ).first()
                if contest:
                    contest_title = contest.name
                    # Préférer image_url, puis cover_image_url
                    contest_image_url = contest.image_url or contest.cover_image_url
                else:
                    contest_title = season.title
            else:
                # Si pas de contest lié, utiliser le titre de la saison
                contest_title = season.title
        
        # Compter le nombre total de participants pour cette saison
        total_participants = db.query(func.count(Contestant.id))\
            .filter(Contestant.season_id == contestant.season_id)\
            .scalar() or 0
        
        # Compter les favoris
        favorites_count = db.query(func.count(MyFavorites.id))\
            .filter(MyFavorites.contestant_id == id)\
            .scalar() or 0
        
        # Compter les réactions avec ContestantReaction
        reactions_count = db.query(func.count(ContestantReaction.id))\
            .filter(ContestantReaction.contestant_id == id)\
            .scalar() or 0

        # Compter les partages
        shares_count = db.query(func.count(ContestantShare.id))\
            .filter(ContestantShare.contestant_id == id)\
            .scalar() or 0
        
        # Compter les commentaires
        comments_count = db.query(func.count(ContestComment.id))\
            .filter(ContestComment.contestant_id == id)\
            .scalar() or 0
        
        # Récupérer le continent de l'utilisateur depuis la table User
        author_continent = None
        if contestant.user:
            author_continent = contestant.user.continent if hasattr(contestant.user, 'continent') else None
        
        return {
            "id": contestant.id,
            "user_id": contestant.user_id,
            "season_id": contestant.season_id,
            "title": contestant.title,
            "description": contestant.description,
            "image_media_ids": contestant.image_media_ids,
            "video_media_ids": contestant.video_media_ids,
            "contestant_image_url": contestant_image_url,
            "registration_date": contestant.registration_date,
            "is_qualified": contestant.is_qualified or False,
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
            "favorites_count": favorites_count,
            "reactions_count": reactions_count,
            "comments_count": comments_count,
            "shares_count": shares_count,
            # Infos du contest
            "contest_title": contest_title,
            "contest_image_url": contest_image_url,
            "contest_id": contestant.season_id,
            "total_participants": total_participants,
            # Position dans les favoris
            "position": position,
            # État du vote
            "has_voted": has_voted,
            "can_vote": can_vote,
            "vote_restriction_reason": vote_restriction_reason,
        }
    
    def get_by_season_and_user(
        self, db: Session, season_id: int, user_id: int, entry_type: str = None
    ) -> Optional[Contestant]:
        """Récupère la candidature d'un utilisateur pour une saison"""
        filters = [
            Contestant.season_id == season_id,
            Contestant.user_id == user_id,
            Contestant.is_deleted == False
        ]
        if entry_type:
            filters.append(Contestant.entry_type == entry_type)
        return db.query(Contestant)\
            .filter(and_(*filters))\
            .first()
            
    def get_by_round_and_user(
        self, db: Session, round_id: int, user_id: int, entry_type: str = None, season_id: int = None
    ) -> Optional[Contestant]:
        """Récupère la candidature d'un utilisateur pour un round spécifique et un contest (season_id)"""
        filters = [
            Contestant.round_id == round_id,
            Contestant.user_id == user_id,
            Contestant.is_deleted == False
        ]
        if entry_type:
            filters.append(Contestant.entry_type == entry_type)
        if season_id is not None:
            filters.append(Contestant.season_id == season_id)
        return db.query(Contestant)\
            .filter(and_(*filters))\
            .first()
    
    def get_multi_by_season(
        self, db: Session, season_id: int, *, skip: int = 0, limit: int = 10
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
    
    def get_multi_by_rounds_with_stats(
        self, db: Session, round_ids: List[int], current_user_id: Optional[int] = None, 
        *, skip: int = 0, limit: int = 10,
        filter_country: Optional[str] = None,
        filter_region: Optional[str] = None,
        filter_continent: Optional[str] = None,
        filter_city: Optional[str] = None,
        filter_user_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Récupère les candidatures d'un ou plusieurs rounds avec stats enrichies (votes, rang, infos auteur).
        Cette fonction est utilisée pour récupérer les contestants liés à un contest via ses rounds.
        
        Paramètres de filtrage géographique:
        - filter_country: Affiche uniquement les contestants de ce pays
        - filter_region: Affiche uniquement les contestants de cette région
        - filter_continent: Affiche uniquement les contestants de ce continent
        - filter_city: Affiche uniquement les contestants de cette ville
        - filter_user_id: Affiche uniquement les contestants de cet utilisateur
        """
        if not round_ids:
            return []
        
        # Récupérer tous les contestants des rounds avec leurs relations (exclure les supprimés)
        contestants_query = db.query(Contestant)\
            .filter(
                Contestant.round_id.in_(round_ids),
                Contestant.is_deleted == False
            )
        
        # Appliquer les filtres géographiques si fournis
        if filter_country:
            contestants_query = contestants_query.filter(
                func.lower(Contestant.country) == func.lower(filter_country)
            )
        if filter_region:
            contestants_query = contestants_query.filter(
                func.lower(Contestant.region) == func.lower(filter_region)
            )
        if filter_continent:
            contestants_query = contestants_query.filter(
                func.lower(Contestant.continent) == func.lower(filter_continent)
            )
        if filter_city:
            contestants_query = contestants_query.filter(
                func.lower(Contestant.city) == func.lower(filter_city)
            )
        
        # Filtre par user_id
        if filter_user_id:
            contestants_query = contestants_query.filter(
                Contestant.user_id == filter_user_id
            )
        
        contestants = contestants_query\
            .options(
                joinedload(Contestant.user),
                joinedload(Contestant.submissions)
            )\
            .order_by(Contestant.registration_date.desc())\
            .offset(skip)\
            .limit(limit)\
            .all()
        
        # Use the same stats enrichment logic as get_multi_by_season_with_stats
        # Copy the enrichment logic from get_multi_by_season_with_stats
        contestant_ids = [c.id for c in contestants]
        
        # Initialiser les dictionnaires de comptes
        votes_by_contestant = {}
        favorites_by_contestant = {}
        reactions_by_contestant = {}
        comments_by_contestant = {}
        
        if contestant_ids:
            # Récupérer les votes en une seule requête
            votes_results = db.query(Vote.contestant_id, func.count(Vote.id))\
                .filter(Vote.contestant_id.in_(contestant_ids))\
                .group_by(Vote.contestant_id).all()
            votes_by_contestant = {cid: count for cid, count in votes_results}
            
            # Récupérer les favoris en une seule requête
            fav_results = db.query(MyFavorites.contestant_id, func.count(MyFavorites.id))\
                .filter(MyFavorites.contestant_id.in_(contestant_ids))\
                .group_by(MyFavorites.contestant_id).all()
            favorites_by_contestant = {cid: count for cid, count in fav_results}
            
            # Récupérer les réactions (likes) en une seule requête
            like_results = db.query(ContestLike.contestant_id, func.count(ContestLike.id))\
                .filter(ContestLike.contestant_id.in_(contestant_ids))\
                .group_by(ContestLike.contestant_id).all()
            reactions_by_contestant = {cid: count for cid, count in like_results}
            
            # Récupérer les commentaires en une seule requête
            comment_results = db.query(ContestComment.contestant_id, func.count(ContestComment.id))\
                .filter(ContestComment.contestant_id.in_(contestant_ids))\
                .group_by(ContestComment.contestant_id).all()
            comments_by_contestant = {cid: count for cid, count in comment_results}
        
        # Calculer les rangs (trié par votes décroissants)
        ranked_contestants = sorted(
            [(c.id, votes_by_contestant.get(c.id, 0)) for c in contestants],
            key=lambda x: x[1],
            reverse=True
        )
        ranks = {cid: rank + 1 for rank, (cid, _) in enumerate(ranked_contestants)}
        
        # Vérifier les votes de l'utilisateur courant
        user_votes = {}
        if current_user_id and contestant_ids:
            user_votes_list = db.query(Vote.contestant_id)\
                .filter(Vote.voter_id == current_user_id, Vote.contestant_id.in_(contestant_ids))\
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
            
            # Utiliser les comptes pré-calculés
            favorites_count = favorites_by_contestant.get(contestant.id, 0)
            reactions_count = reactions_by_contestant.get(contestant.id, 0)
            comments_count = comments_by_contestant.get(contestant.id, 0)
            
            result.append({
                "id": contestant.id,
                "user_id": contestant.user_id,
                "season_id": contestant.season_id,
                "round_id": contestant.round_id,
                "entry_type": contestant.entry_type or "participation",
                "title": contestant.title,
                "description": contestant.description,
                "image_media_ids": contestant.image_media_ids,
                "video_media_ids": contestant.video_media_ids,
                "nominator_city": contestant.nominator_city,
                "nominator_country": contestant.nominator_country,
                "registration_date": contestant.registration_date,
                "is_qualified": contestant.is_qualified,
                # Infos auteur (depuis l'utilisateur)
                "author_name": contestant.user.full_name or f"{contestant.user.first_name or ''} {contestant.user.last_name or ''}".strip() if contestant.user else None,
                "author_country": contestant.user.country if contestant.user else None,
                "author_city": contestant.user.city if contestant.user else None,
                "author_continent": contestant.user.continent if contestant.user else None,
                "author_region": contestant.user.region if contestant.user else None,
                "author_avatar_url": contestant.user.avatar_url if contestant.user else None,
                # Données géographiques du contestant (copiées à la création)
                "country": contestant.country,
                "city": contestant.city,
                "continent": contestant.continent,
                "region": contestant.region,
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
    
    def get_multi_by_season_with_stats(
        self, db: Session, season_id: int, current_user_id: Optional[int] = None, 
        *, skip: int = 0, limit: int = 10,
        filter_country: Optional[str] = None,
        filter_region: Optional[str] = None,
        filter_continent: Optional[str] = None,
        filter_city: Optional[str] = None,
        filter_user_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Récupère les candidatures d'une saison avec stats enrichies (votes, rang, infos auteur).
        NOTE: Cette fonction utilise season_id (legacy). Pour les nouveaux contestants liés via round_id,
        utilisez get_multi_by_rounds_with_stats.
        
        Paramètres de filtrage géographique:
        - filter_country: Affiche uniquement les contestants de ce pays
        - filter_region: Affiche uniquement les contestants de cette région
        - filter_continent: Affiche uniquement les contestants de ce continent
        - filter_city: Affiche uniquement les contestants de cette ville
        - filter_user_id: Affiche uniquement les contestants de cet utilisateur
        """
        # Récupérer tous les contestants de la saison avec leurs relations (exclure les supprimés)
        # Also check round_id if contestants are linked via rounds
        from app.models.round import Round
        from app.models.contests import round_contests
        
        # Get rounds linked to contests that might have this season_id
        # First try direct season_id match (legacy)
        contestants_query = db.query(Contestant)\
            .filter(
                Contestant.season_id == season_id,
                Contestant.is_deleted == False
            )
        
        # Appliquer les filtres géographiques si fournis
        if filter_country:
            contestants_query = contestants_query.filter(
                func.lower(Contestant.country) == func.lower(filter_country)
            )
        if filter_region:
            contestants_query = contestants_query.filter(
                func.lower(Contestant.region) == func.lower(filter_region)
            )
        if filter_continent:
            contestants_query = contestants_query.filter(
                func.lower(Contestant.continent) == func.lower(filter_continent)
            )
        if filter_city:
            contestants_query = contestants_query.filter(
                func.lower(Contestant.city) == func.lower(filter_city)
            )
        
        # Filtre par user_id
        if filter_user_id:
            contestants_query = contestants_query.filter(
                Contestant.user_id == filter_user_id
            )
        
        contestants = contestants_query\
            .options(
                joinedload(Contestant.user),
                joinedload(Contestant.submissions)
            )\
            .order_by(Contestant.registration_date.desc())\
            .offset(skip)\
            .limit(limit)\
            .all()
        
        # Optimisation: Récupérer tous les IDs pour éviter les requêtes N+1
        contestant_ids = [c.id for c in contestants]
        
        # Initialiser les dictionnaires de comptes
        votes_by_contestant = {}
        favorites_by_contestant = {}
        reactions_by_contestant = {}
        comments_by_contestant = {}
        
        if contestant_ids:
            # Récupérer les votes en une seule requête
            votes_results = db.query(Vote.contestant_id, func.count(Vote.id))\
                .filter(Vote.contestant_id.in_(contestant_ids))\
                .group_by(Vote.contestant_id).all()
            votes_by_contestant = {cid: count for cid, count in votes_results}
            
            # Récupérer les favoris en une seule requête
            fav_results = db.query(MyFavorites.contestant_id, func.count(MyFavorites.id))\
                .filter(MyFavorites.contestant_id.in_(contestant_ids))\
                .group_by(MyFavorites.contestant_id).all()
            favorites_by_contestant = {cid: count for cid, count in fav_results}
            
            # Récupérer les réactions (likes) en une seule requête
            like_results = db.query(ContestLike.contestant_id, func.count(ContestLike.id))\
                .filter(ContestLike.contestant_id.in_(contestant_ids))\
                .group_by(ContestLike.contestant_id).all()
            reactions_by_contestant = {cid: count for cid, count in like_results}
            
            # Récupérer les commentaires en une seule requête
            comment_results = db.query(ContestComment.contestant_id, func.count(ContestComment.id))\
                .filter(ContestComment.contestant_id.in_(contestant_ids))\
                .group_by(ContestComment.contestant_id).all()
            comments_by_contestant = {cid: count for cid, count in comment_results}
        
        # Calculer les rangs (trié par votes décroissants)
        ranked_contestants = sorted(
            [(c.id, votes_by_contestant.get(c.id, 0)) for c in contestants],
            key=lambda x: x[1],
            reverse=True
        )
        ranks = {cid: rank + 1 for rank, (cid, _) in enumerate(ranked_contestants)}
        
        # Vérifier les votes de l'utilisateur courant
        user_votes = {}
        if current_user_id and contestant_ids:
            user_votes_list = db.query(Vote.contestant_id)\
                .filter(Vote.voter_id == current_user_id, Vote.contestant_id.in_(contestant_ids))\
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
            
            # Utiliser les comptes pré-calculés
            favorites_count = favorites_by_contestant.get(contestant.id, 0)
            reactions_count = reactions_by_contestant.get(contestant.id, 0)
            comments_count = comments_by_contestant.get(contestant.id, 0)
            
            result.append({
                "id": contestant.id,
                "user_id": contestant.user_id,
                "season_id": contestant.season_id,
                "title": contestant.title,
                "description": contestant.description,
                "image_media_ids": contestant.image_media_ids,
                "video_media_ids": contestant.video_media_ids,
                "nominator_city": contestant.nominator_city,
                "nominator_country": contestant.nominator_country,
                "registration_date": contestant.registration_date,
                "is_qualified": contestant.is_qualified,
                # Infos auteur (depuis l'utilisateur)
                "author_name": contestant.user.full_name or f"{contestant.user.first_name or ''} {contestant.user.last_name or ''}".strip() if contestant.user else None,
                "author_country": contestant.user.country if contestant.user else None,
                "author_city": contestant.user.city if contestant.user else None,
                "author_continent": contestant.user.continent if contestant.user else None,
                "author_region": contestant.user.region if contestant.user else None,
                "author_avatar_url": contestant.user.avatar_url if contestant.user else None,
                # Données géographiques du contestant (copiées à la création)
                "country": contestant.country,
                "city": contestant.city,
                "continent": contestant.continent,
                "region": contestant.region,
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
        self, db: Session, user_id: int, *, skip: int = 0, limit: int = 10
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
        video_media_ids: Optional[str] = None,
        nominator_city: Optional[str] = None,
        nominator_country: Optional[str] = None,
        round_id: Optional[int] = None,
        entry_type: str = "participation"
    ) -> Contestant:
        """Crée une nouvelle candidature"""
        # We no longer check `get_by_season_and_user` here because the API endpoint
        # already checks `get_by_round_and_user` to prevent duplicate submissions in the same round,
        # but allows submissions across different rounds of the same season/contest.
        # Récupérer l'utilisateur pour copier ses données géographiques
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise ValueError("Utilisateur non trouvé")
        
        # Créer la candidature avec les données géographiques et le genre de l'utilisateur
        author_gender_value = None
        if user.gender:
            author_gender_value = user.gender.value if hasattr(user.gender, 'value') else str(user.gender)
        
        db_obj = Contestant(
            user_id=user_id,
            season_id=season_id,
            title=title,
            description=description,
            image_media_ids=image_media_ids,
            video_media_ids=video_media_ids,
            city=user.city,
            country=user.country,
            region=user.region,
            continent=user.continent,
            author_gender=author_gender_value,
            nominator_city=nominator_city,
            nominator_country=nominator_country,
            round_id=round_id,
            entry_type=entry_type,
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
        self, db: Session, season_id: int, *, skip: int = 0, limit: int = 10
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
        video_media_ids: Optional[str] = None,
        nominator_city: Optional[str] = None,
        nominator_country: Optional[str] = None
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
        if nominator_city is not None:
            db_obj.nominator_city = nominator_city
        if nominator_country is not None:
            db_obj.nominator_country = nominator_country
        
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
    
    def check_registration_eligibility(
        self, db: Session, *, user_id: int, season_id: int, category_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Vérifie si un utilisateur peut s'inscrire à un concours.
        Retourne un dict avec 'eligible' (bool) et 'reason' (str si non éligible).
        Le season_id peut être un Contest.id ou un ContestSeason.id.
        """
        # Vérifier si l'utilisateur a déjà une candidature pour cette saison
        existing = self.get_by_season_and_user(db, season_id, user_id)
        if existing:
            return {
                "eligible": False,
                "reason": "Vous êtes déjà inscrit à ce concours"
            }
        
        # D'abord, essayer de récupérer comme un Contest (table contest)
        contest = db.query(Contest).filter(Contest.id == season_id, Contest.is_deleted == False).first()
        
        if contest:
            # C'est un Contest - vérifier les dates et l'état
            if not contest.is_active:
                return {
                    "eligible": False,
                    "reason": "Ce concours n'est pas actif"
                }
            
            # Vérifier is_submission_open
            if not contest.is_submission_open:
                return {
                    "eligible": False,
                    "reason": "Les inscriptions sont fermées pour ce concours"
                }
            
            # Vérifier les dates de soumission via le Round actif
            today = date.today()
            
            # Récupérer le round actif
            from app.crud import crud_round
            active_round = crud_round.round.get_active_round_for_contest(db, contest_id=contest.id)
            
            submission_start_date = active_round.submission_start_date if active_round else None
            submission_end_date = active_round.submission_end_date if active_round else None

            if submission_start_date:
                start_date = submission_start_date
                if isinstance(start_date, datetime):
                    start_date = start_date.date()
                if today < start_date:
                    return {
                        "eligible": False,
                        "reason": "La période d'inscription n'a pas encore commencé"
                    }
            
            if submission_end_date:
                end_date = submission_end_date
                if isinstance(end_date, datetime):
                    end_date = end_date.date()
                if today > end_date:
                    return {
                        "eligible": False,
                        "reason": "La période d'inscription est terminée"
                    }
            
            return {
                "eligible": True,
                "reason": None
            }
        
        # Sinon, essayer comme ContestSeason
        season = db.query(ContestSeason).filter(ContestSeason.id == season_id).first()
        if not season:
            return {
                "eligible": False,
                "reason": "Concours non trouvé"
            }
        
        # ContestSeason n'a pas de dates de soumission par défaut, on vérifie juste s'il existe
        return {
            "eligible": True,
            "reason": None
        }
    
    def is_submission_period_open(self, db: Session, *, contestant_id: int) -> bool:
        """
        Vérifie si la période de soumission est ouverte pour un contestant.
        Le season_id peut être un Contest.id ou un ContestSeason.id.
        """
        contestant = self.get(db, contestant_id)
        if not contestant:
            return False
        
        # D'abord, essayer comme Contest
        contest = db.query(Contest).filter(
            Contest.id == contestant.season_id, 
            Contest.is_deleted == False
        ).first()
        
        if contest:
            # Vérifier is_submission_open
            if not contest.is_submission_open:
                return False
            
            # Vérifier is_active
            if not contest.is_active:
                return False
            
            # Vérifier les dates via le Round actif
            today = date.today()
            
            # Récupérer le round actif
            from app.crud import crud_round
            active_round = crud_round.round.get_active_round_for_contest(db, contest_id=contest.id)
            
            submission_start_date = active_round.submission_start_date if active_round else None
            submission_end_date = active_round.submission_end_date if active_round else None
            
            if submission_start_date:
                start_date = submission_start_date
                if isinstance(start_date, datetime):
                    start_date = start_date.date()
                if today < start_date:
                    return False
            
            if submission_end_date:
                end_date = submission_end_date
                if isinstance(end_date, datetime):
                    end_date = end_date.date()
                if today > end_date:
                    return False
            
            return True
        
        # Sinon, essayer comme ContestSeason
        season = db.query(ContestSeason).filter(ContestSeason.id == contestant.season_id).first()
        if not season:
            return False
        
        # ContestSeason n'a pas de dates de soumission par défaut, on considère que c'est ouvert
        return True
    
    def create_with_user(
        self, db: Session, *, obj_in: Any, user_id: int
    ) -> Contestant:
        """Crée une candidature pour un utilisateur"""
        return self.create(
            db,
            user_id=user_id,
            season_id=obj_in.season_id,
            title=getattr(obj_in, 'title', None),
            description=getattr(obj_in, 'description', None),
            image_media_ids=getattr(obj_in, 'image_media_ids', None),
            video_media_ids=getattr(obj_in, 'video_media_ids', None)
        )

    def get_multi_by_user_with_stats(
        self, db: Session, user_id: int, *, skip: int = 0, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Récupère les candidatures d'un utilisateur avec stats enrichies.
        Optimisé pour éviter les requêtes N+1.
        """
        # Récupérer les candidatures de l'utilisateur
        contestants = db.query(Contestant)\
            .filter(
                Contestant.user_id == user_id,
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
        
        if not contestants:
            return []
            
        contestant_ids = [c.id for c in contestants]
        
        # Initialiser les dictionnaires de comptes
        votes_by_contestant = {}
        favorites_by_contestant = {}
        reactions_by_contestant = {}
        comments_by_contestant = {}
        
        # Récupérer les votes en une seule requête
        votes_results = db.query(Vote.contestant_id, func.count(Vote.id))\
            .filter(Vote.contestant_id.in_(contestant_ids))\
            .group_by(Vote.contestant_id).all()
        votes_by_contestant = {cid: count for cid, count in votes_results}
        
        # Récupérer les favoris en une seule requête
        fav_results = db.query(MyFavorites.contestant_id, func.count(MyFavorites.id))\
            .filter(MyFavorites.contestant_id.in_(contestant_ids))\
            .group_by(MyFavorites.contestant_id).all()
        favorites_by_contestant = {cid: count for cid, count in fav_results}
        
        # Récupérer les réactions (likes) en une seule requête
        like_results = db.query(ContestLike.contestant_id, func.count(ContestLike.id))\
            .filter(ContestLike.contestant_id.in_(contestant_ids))\
            .group_by(ContestLike.contestant_id).all()
        reactions_by_contestant = {cid: count for cid, count in like_results}
        
        # Récupérer les commentaires en une seule requête
        comment_results = db.query(ContestComment.contestant_id, func.count(ContestComment.id))\
            .filter(ContestComment.contestant_id.in_(contestant_ids))\
            .group_by(ContestComment.contestant_id).all()
        comments_by_contestant = {cid: count for cid, count in comment_results}
        
        # Récupérer les partages en une seule requête
        share_results = db.query(ContestantShare.contestant_id, func.count(ContestantShare.id))\
            .filter(ContestantShare.contestant_id.in_(contestant_ids))\
            .group_by(ContestantShare.contestant_id).all()
        shares_by_contestant = {cid: count for cid, count in share_results}
        
        # Récupérer les infos du contest (titre, image) pour chaque contestant
        # Cela nécessite de remonter à la saison/contest
        from app.models.contests import ContestSeasonLink, ContestSeason
        from app.models.contest import Contest as MyfavContest
        
        contest_info_by_season = {}
        # Note: contestants.season_id contient le contest_id (pas l'id de la saison)
        contestant_season_ids = list(set([c.season_id for c in contestants]))

        if contestant_season_ids:
            # D'abord chercher directement dans la table contest
            contests_data = db.query(MyfavContest).filter(
                MyfavContest.id.in_(contestant_season_ids)
            ).all()
            contest_map = {c.id: c for c in contests_data}

            for cid in contestant_season_ids:
                if cid in contest_map:
                    contest = contest_map[cid]
                    contest_info_by_season[cid] = {
                        "contest_title": contest.name,
                        "contest_level": contest.level if hasattr(contest, 'level') else None,
                        "contest_image_url": getattr(contest, 'image_url', None) or getattr(contest, 'cover_image_url', None),
                        "contest_id": cid
                    }

            # Fallback: si certains IDs sont de vraies season_ids
            missing_ids = [cid for cid in contestant_season_ids if cid not in contest_info_by_season]
            if missing_ids:
                season_links = db.query(ContestSeasonLink).filter(
                    ContestSeasonLink.season_id.in_(missing_ids),
                    ContestSeasonLink.is_active == True
                ).all()
                link_contest_ids = list(set([link.contest_id for link in season_links]))
                if link_contest_ids:
                    linked_contests = db.query(MyfavContest).filter(
                        MyfavContest.id.in_(link_contest_ids)
                    ).all()
                    linked_map = {c.id: c for c in linked_contests}
                    for link in season_links:
                        if link.contest_id in linked_map:
                            contest = linked_map[link.contest_id]
                            contest_info_by_season[link.season_id] = {
                                "contest_title": contest.name,
                                "contest_level": contest.level if hasattr(contest, 'level') else None,
                                "contest_image_url": getattr(contest, 'image_url', None) or getattr(contest, 'cover_image_url', None),
                                "contest_id": link.contest_id
                            }

                # Dernier fallback: ContestSeason
                still_missing = [cid for cid in missing_ids if cid not in contest_info_by_season]
                if still_missing:
                    seasons_data = db.query(ContestSeason).filter(
                        ContestSeason.id.in_(still_missing)
                    ).all()
                    for season in seasons_data:
                        level_val = None
                        if hasattr(season, 'level') and season.level:
                            level_val = season.level.value if hasattr(season.level, 'value') else str(season.level)
                        contest_info_by_season[season.id] = {
                            "contest_title": season.title,
                            "contest_level": level_val,
                            "contest_image_url": None,
                            "contest_id": season.id
                        }
        
        
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
            
            # Utiliser les comptes pré-calculés
            favorites_count = favorites_by_contestant.get(contestant.id, 0)
            reactions_count = reactions_by_contestant.get(contestant.id, 0)
            comments_count = comments_by_contestant.get(contestant.id, 0)
            shares_count = shares_by_contestant.get(contestant.id, 0)
            
            # Infos contest
            contest_info = contest_info_by_season.get(contestant.season_id, {})
            
            result.append({
                "id": contestant.id,
                "user_id": contestant.user_id,
                "season_id": contestant.season_id,
                "round_id": contestant.round_id,
                "entry_type": contestant.entry_type or "participation",
                "title": contestant.title,
                "description": contestant.description,
                "image_media_ids": contestant.image_media_ids,
                "video_media_ids": contestant.video_media_ids,
                "nominator_city": contestant.nominator_city,
                "nominator_country": contestant.nominator_country,
                "registration_date": contestant.registration_date,
                "is_qualified": contestant.is_qualified,
                # Infos auteur (depuis l'utilisateur)
                "author_name": contestant.user.full_name or f"{contestant.user.first_name or ''} {contestant.user.last_name or ''}".strip() if contestant.user else None,
                "author_country": contestant.user.country if contestant.user else None,
                "author_city": contestant.user.city if contestant.user else None,
                "author_continent": contestant.user.continent if contestant.user else None,
                "author_region": contestant.user.region if contestant.user else None,
                "author_avatar_url": contestant.user.avatar_url if contestant.user else None,
                # Données géographiques du contestant
                "country": contestant.country,
                "city": contestant.city,
                "continent": contestant.continent,
                "region": contestant.region,
                # Stats
                "rank": None, # Rank is relative to contest, hard to calc global rank here efficiently
                "votes_count": votes_by_contestant.get(contestant.id, 0),
                "images_count": images_count,
                "videos_count": videos_count,
                "favorites_count": favorites_count,
                "reactions_count": reactions_count,
                "comments_count": comments_count,
                "shares_count": shares_count,
                # Infos du contest
                "contest_title": contest_info.get("contest_title"),
                "contest_level": contest_info.get("contest_level"),
                "contest_image_url": contest_info.get("contest_image_url"),
                "contest_id": contest_info.get("contest_id", contestant.season_id),
                "total_participants": 0, # Not calculating total participants per contest here
                # Position dans les favoris
                "position": None,
                # État du vote (l'utilisateur ne peut pas voter pour lui-même)
                "has_voted": False,
                "can_vote": False,
                "vote_restriction_reason": "own_contestant"
            })
        
        return result


# Instance globale
crud_contestant = CRUDContestant()


# Classe pour les soumissions de contest
class CRUDContestSubmission:
    """CRUD operations for ContestSubmission model"""
    
    def create_with_contestant(
        self, db: Session, *, obj_in: Any, contestant_id: int
    ) -> ContestSubmission:
        """Crée une soumission pour un contestant"""
        submission = ContestSubmission(
            contestant_id=contestant_id,
            media_type=getattr(obj_in, 'media_type', 'image'),
            file_url=getattr(obj_in, 'file_url', None),
            external_url=getattr(obj_in, 'external_url', None),
            title=getattr(obj_in, 'title', None),
            description=getattr(obj_in, 'description', None),
            upload_date=datetime.utcnow(),
            is_approved=False,
            moderation_status="pending"
        )
        db.add(submission)
        db.commit()
        db.refresh(submission)
        return submission
    
    def handle_media_upload(
        self, db: Session, *, contestant_id: int, file: Any,
        title: Optional[str] = None, description: Optional[str] = None
    ) -> Dict[str, Any]:
        """Gère l'upload d'un fichier média"""
        # TODO: Implémenter l'upload vers le service de stockage
        return {
            "success": False,
            "error": "L'upload de fichiers n'est pas encore implémenté"
        }


# Instance globale
contest_submission = CRUDContestSubmission()
