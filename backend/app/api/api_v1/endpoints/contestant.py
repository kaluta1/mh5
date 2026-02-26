from typing import List, Optional, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks

from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.api import deps
from app.crud import contestant as crud_contestant, report
from app.models.user import User
from app.models.contests import Contestant, ContestSubmission, ContestSeason, ContestStage, ContestantSeason, SeasonLevel
from app.models.voting import MyFavorites, Vote, ContestantReaction, ContestantShare, ReactionType, ContestantVoting, ContestLike, ContestComment
from app.models.contest import Contest
from app.schemas.comment import ContestantReportCreate, ReportResponse
from app.schemas.voting import (
    ReactionCreate, Reaction, ReactionStats, ReactionDetails, ReactionUserDetail,
    VoteDetails, VoteUserDetail,
    FavoriteDetails, FavoriteUserDetail,
    ShareCreate, Share, ShareStats, ShareUserDetail
)
from app.schemas.contestant import (
    ContestantCreate, ContestantResponse, ContestantListResponse, ContestantSubmissionResponse,
    ContestantWithAuthorAndStats
)
from app.services.content_moderation import content_moderation_service, ContentType
from app.services.content_relevance import content_relevance_service

router = APIRouter()


# DEBUG ENDPOINT: Test if contestants exist in database
@router.get("/debug/all-contestants")
def debug_get_all_contestants(
    *,
    db: Session = Depends(deps.get_db),
    limit: int = Query(20, ge=1, le=100)
):
    """
    DEBUG: Get all contestants from database (no filters) to verify they exist.
    This endpoint helps diagnose why contestants aren't appearing.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        # Query ALL non-deleted contestants
        all_contestants = db.query(Contestant).filter(
            Contestant.is_deleted == False
        ).limit(limit).all()
        
        logger.info(f"[DEBUG] Found {len(all_contestants)} total contestants in database")
        
        result = []
        for c in all_contestants:
            result.append({
                "id": c.id,
                "user_id": c.user_id,
                "season_id": c.season_id,
                "round_id": c.round_id,
                "title": c.title,
                "is_deleted": c.is_deleted,
                "registration_date": c.registration_date.isoformat() if c.registration_date else None
            })
            logger.info(f"[DEBUG] Contestant {c.id}: season_id={c.season_id}, round_id={c.round_id}, user_id={c.user_id}")
        
        return {
            "total_found": len(all_contestants),
            "contestants": result,
            "message": f"Found {len(all_contestants)} contestants. Check logs for details."
        }
    except Exception as e:
        logger.error(f"[DEBUG] Error querying contestants: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


# Routes spécifiques d'abord (avant les routes génériques avec {id})
# IMPORTANT: Les routes plus spécifiques DOIVENT venir avant les routes générales

@router.get("/user/my-entries", response_model=List[ContestantWithAuthorAndStats])
def get_my_contestants(
    *,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100)
) -> List[ContestantWithAuthorAndStats]:
    """Récupère les candidatures de l'utilisateur connecté avec stats enrichies"""
    contestants = crud_contestant.get_multi_by_user_with_stats(
        db, current_user.id, skip=skip, limit=limit
    )
    return contestants


@router.get("/user/my-votes")
def get_my_votes(
    *,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
    season_id: Optional[int] = Query(None, description="Filter by season_id")
) -> dict:
    """
    Récupère les votes de l'utilisateur connecté (MyHigh5), groupés par season.
    Retourne uniquement les votes des saisons actives (is_active=True dans ContestSeasonLink).
    Les votes sont limités à 5 par season.
    """
    from sqlalchemy.orm import joinedload
    from sqlalchemy import case, func
    from app.models.contests import Contestant, ContestSeasonLink
    from app.models.contest import Contest
    
    # Construire la requête de base avec filtre sur les saisons actives
    query = db.query(ContestantVoting).options(
        joinedload(ContestantVoting.contestant),
        joinedload(ContestantVoting.season),
        joinedload(ContestantVoting.contest)
    ).join(
        ContestSeasonLink,
        and_(
            ContestSeasonLink.contest_id == ContestantVoting.contest_id,
            ContestSeasonLink.season_id == ContestantVoting.season_id,
            ContestSeasonLink.is_active == True
        )
    ).filter(
        ContestantVoting.user_id == current_user.id
    )
    
    # Filtrer par season_id si fourni
    if season_id:
        query = query.filter(ContestantVoting.season_id == season_id)
    
    # Récupérer tous les votes
    all_votes = query.order_by(
        ContestantVoting.season_id,
        # Les votes avec position définie d'abord, triés par position
        # Puis les votes sans position, triés par date
        case(
            (ContestantVoting.position.isnot(None), ContestantVoting.position),
            else_=1000  # Mettre les votes sans position à la fin
        ),
        ContestantVoting.vote_date.asc()
    ).all()
    
    # Grouper par season_id
    votes_by_season = {}
    for vote in all_votes:
        season_key = vote.season_id
        if season_key not in votes_by_season:
            votes_by_season[season_key] = []
        votes_by_season[season_key].append(vote)
    
    # Limiter à 5 votes par season et construire le résultat
    result = {
        "seasons": []
    }
    
    for season_id_key, votes in votes_by_season.items():
        # Limiter à 5 votes par season
        season_votes = votes[:5]
        
        # Récupérer les infos de la season et du contest
        first_vote = season_votes[0]
        season = first_vote.season
        contest = db.query(Contest).filter(Contest.id == first_vote.contest_id).first()
        
        season_votes_list = []
        for idx, vote in enumerate(season_votes, 1):
            contestant = vote.contestant
            if not contestant:
                continue
                
            # Récupérer l'auteur du contestant
            author = db.query(User).filter(User.id == contestant.user_id).first()
            
            # Compter les votes pour ce contestant
            votes_count = db.query(ContestantVoting).filter(
                ContestantVoting.contestant_id == contestant.id
            ).count()
            
            # Calculer les points si position est définie, sinon utiliser la position par défaut
            position = vote.position if vote.position else idx
            points = vote.points if vote.points is not None else (6 - position if 1 <= position <= 5 else None)
            
            season_votes_list.append({
                "position": position,
                "points": points,
                "contestant_id": contestant.id,
                "contestant_title": contestant.title,
                "contestant_description": contestant.description,
                "author_id": contestant.user_id,
                "author_name": author.full_name if author else None,
                "author_avatar_url": author.avatar_url if author else None,
                "author_country": author.country if author else None,
                "author_city": author.city if author else None,
                "votes_count": votes_count,
                "vote_date": vote.vote_date.isoformat() if vote.vote_date else None,
                "season_id": vote.season_id,
                "contest_id": vote.contest_id,
                "season_level": season.level if season else None
            })
        
        result["seasons"].append({
            "season_id": season_id_key,
            "season_level": season.level if season else None,
            "contest_id": first_vote.contest_id,
            "contest_name": contest.name if contest else None,
            "votes": season_votes_list,
            "votes_count": len(season_votes_list),
            "remaining_slots": 5 - len(season_votes_list)
        })
    
    return result


@router.get("/user/my-votes/history")
def get_my_votes_history(
    *,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
    contest_id: Optional[int] = Query(None, description="Filter by contest_id")
) -> dict:
    """
    Récupère l'historique complet des votes de l'utilisateur connecté (MyHigh5).
    Retourne tous les votes, y compris ceux des saisons inactives, groupés par contestant et season.
    """
    from sqlalchemy.orm import joinedload
    from sqlalchemy import case
    from app.models.contests import Contestant
    from app.models.contest import Contest
    
    # Construire la requête de base (sans filtre sur is_active)
    query = db.query(ContestantVoting).options(
        joinedload(ContestantVoting.contestant),
        joinedload(ContestantVoting.season),
        joinedload(ContestantVoting.contest)
    ).filter(
        ContestantVoting.user_id == current_user.id
    )
    
    # Filtrer par contest_id si fourni
    if contest_id:
        query = query.filter(ContestantVoting.contest_id == contest_id)
    
    # Récupérer tous les votes, triés par contest_id, puis season_id, puis position/date
    all_votes = query.order_by(
        ContestantVoting.contest_id,
        ContestantVoting.season_id,
        # Les votes avec position définie d'abord, triés par position
        # Puis les votes sans position, triés par date
        case(
            (ContestantVoting.position.isnot(None), ContestantVoting.position),
            else_=1000
        ),
        ContestantVoting.vote_date.asc()
    ).all()
    
    # Grouper par contest_id, puis par season_id
    votes_by_contest = {}
    for vote in all_votes:
        contest_key = vote.contest_id
        season_key = vote.season_id
        
        if contest_key not in votes_by_contest:
            votes_by_contest[contest_key] = {}
        if season_key not in votes_by_contest[contest_key]:
            votes_by_contest[contest_key][season_key] = []
        
        votes_by_contest[contest_key][season_key].append(vote)
    
    # Construire le résultat groupé par contestant
    result = {
        "history": []
    }
    
    for contest_id_key, seasons in votes_by_contest.items():
        contest = db.query(Contest).filter(Contest.id == contest_id_key).first()
        
        contest_data = {
            "contest_id": contest_id_key,
            "contest_name": contest.name if contest else None,
            "seasons": []
        }
        
        for season_id_key, votes in seasons.items():
            # Limiter à 5 votes par season pour l'affichage
            season_votes = votes[:5]
            
            if not season_votes:
                continue
            
            first_vote = season_votes[0]
            season = first_vote.season
            
            # Vérifier si la saison est active
            from app.models.contests import ContestSeasonLink
            season_link = db.query(ContestSeasonLink).filter(
                ContestSeasonLink.contest_id == contest_id_key,
                ContestSeasonLink.season_id == season_id_key
            ).first()
            is_active = season_link.is_active if season_link else False
            
            season_votes_list = []
            for idx, vote in enumerate(season_votes, 1):
                contestant = vote.contestant
                if not contestant:
                    continue
                    
                # Récupérer l'auteur du contestant
                author = db.query(User).filter(User.id == contestant.user_id).first()
                
                # Compter les votes pour ce contestant
                votes_count = db.query(ContestantVoting).filter(
                    ContestantVoting.contestant_id == contestant.id
                ).count()
                
                # Calculer les points si position est définie, sinon utiliser la position par défaut
                position = vote.position if vote.position else idx
                points = vote.points if vote.points is not None else (6 - position if 1 <= position <= 5 else None)
                
                season_votes_list.append({
                    "position": position,
                    "points": points,
                    "contestant_id": contestant.id,
                    "contestant_title": contestant.title,
                    "contestant_description": contestant.description,
                    "author_id": contestant.user_id,
                    "author_name": author.full_name if author else None,
                    "author_avatar_url": author.avatar_url if author else None,
                    "author_country": author.country if author else None,
                    "author_city": author.city if author else None,
                    "votes_count": votes_count,
                    "vote_date": vote.vote_date.isoformat() if vote.vote_date else None,
                    "season_id": vote.season_id,
                    "contest_id": vote.contest_id,
                    "season_level": season.level if season else None
                })
            
            contest_data["seasons"].append({
                "season_id": season_id_key,
                "season_level": season.level if season else None,
                "is_active": is_active,
                "votes": season_votes_list,
                "votes_count": len(season_votes_list)
            })
        
        result["history"].append(contest_data)
    
    return result


@router.put("/user/my-votes/reorder")
def reorder_my_votes(
    *,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
    data: dict
) -> dict:
    """
    Réordonne les votes MyHigh5 de l'utilisateur pour une season donnée.
    Le 1er reçoit 5 points, le 2ème 4 points, le 3ème 3 points, etc.
    Les votes sont groupés par season_id.
    """
    votes_to_reorder = data.get("votes", [])
    season_id = data.get("season_id")
    
    if not votes_to_reorder:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No votes to reorder"
        )
    
    if not season_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="season_id is required"
        )
    
    if len(votes_to_reorder) > 5:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum 5 votes allowed per season"
        )
    
    # Vérifier que tous les votes appartiennent à l'utilisateur et à la même season
    contestant_ids = [v["contestant_id"] for v in votes_to_reorder]
    
    user_votes = db.query(ContestantVoting).filter(
        ContestantVoting.user_id == current_user.id,
        ContestantVoting.contestant_id.in_(contestant_ids),
        ContestantVoting.season_id == season_id
    ).all()
    
    user_vote_contestant_ids = {vote.contestant_id for vote in user_votes}
    
    for contestant_id in contestant_ids:
        if contestant_id not in user_vote_contestant_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Vote for contestant {contestant_id} not found in season {season_id}"
            )
    
    # Mettre à jour les positions et les points
    # Points: position 1 = 5 points, position 2 = 4 points, etc.
    for vote_data in votes_to_reorder:
        contestant_id = vote_data["contestant_id"]
        new_position = vote_data["position"]
        
        # Calculer les points selon la position (1->5, 2->4, 3->3, 4->2, 5->1)
        new_points = 6 - new_position if 1 <= new_position <= 5 else None
        
        # Trouver le vote correspondant et mettre à jour sa position et ses points
        for vote in user_votes:
            if vote.contestant_id == contestant_id:
                vote.position = new_position
                vote.points = new_points
                break
    
    db.commit()
    
    return {"message": "Votes reordered successfully", "count": len(votes_to_reorder), "season_id": season_id}


# IMPORTANT: Cette route DOIT venir avant /contest/{contest_id}
@router.get("/favorites")
def get_user_favorites(
    *,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user)
) -> List[int]:
    """Récupère les IDs des contestants en favoris de l'utilisateur"""
    favorites = db.query(MyFavorites.contestant_id).filter(
        MyFavorites.user_id == current_user.id
    ).all()
    
    return [fav[0] for fav in favorites]


# IMPORTANT: Cette route DOIT venir avant /contest/{contest_id}
@router.get("/leaderboard/contest/{contest_id}", response_model=List[ContestantListResponse])
def get_contest_leaderboard(
    *,
    db: Session = Depends(deps.get_db),
    contest_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100)
) -> List[ContestantListResponse]:
    """Récupère le classement d'un concours"""
    # Vérifier que la saison existe
    season = db.query(ContestSeason).filter(ContestSeason.id == contest_id).first()
    if not season:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contest not found"
        )
    
    contestants = crud_contestant.get_leaderboard(
        db, contest_id, skip=skip, limit=limit
    )
    
    result = []
    for rank, contestant in enumerate(contestants, 1):
        result.append(ContestantListResponse(
            id=contestant.id,
            user_id=contestant.user_id,
            season_id=contestant.season_id,
            title=contestant.title,
            description=contestant.description,
            registration_date=contestant.registration_date,
            is_qualified=contestant.is_qualified
        ))
    
    return result


@router.get("/contest/{contest_id}", response_model=List[ContestantWithAuthorAndStats])
def get_contest_contestants(
    *,
    db: Session = Depends(deps.get_db),
    contest_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    filter_country: str = Query(None, description="Filtrer par pays"),
    filter_region: str = Query(None, description="Filtrer par région"),
    filter_continent: str = Query(None, description="Filtrer par continent"),
    filter_city: str = Query(None, description="Filtrer par ville"),
    user_id: Optional[int] = Query(None, description="Filtrer par user_id"),
    current_user: Optional[User] = Depends(deps.get_current_active_user_optional)
) -> List[ContestantWithAuthorAndStats]:
    """
    Récupère les candidatures d'un concours avec stats enrichies.
    
    Paramètres de filtrage géographique:
    - filter_country: Affiche uniquement les contestants de ce pays
    - filter_region: Affiche uniquement les contestants de cette région  
    - filter_continent: Affiche uniquement les contestants de ce continent
    - filter_city: Affiche uniquement les contestants de cette ville
    - user_id: Affiche uniquement les contestants de cet utilisateur
    """
    # Essayer d'abord de trouver une ContestSeason avec cet ID
    season = db.query(ContestSeason).filter(ContestSeason.id == contest_id).first()
    
    # Si pas trouvé, chercher dans la table Contest
    if not season:
        from app.models.contest import Contest as MyfavContest
        contest = db.query(MyfavContest).filter(MyfavContest.id == contest_id).first()
        if not contest:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Contest not found"
            )
    
    # FIXED: Simplified query to avoid database errors and 503 responses
    from app.models.round import Round
    from app.models.contests import round_contests, Contestant
    from sqlalchemy import or_, func
    from sqlalchemy.orm import joinedload
    import logging
    
    logger = logging.getLogger(__name__)
    
    try:
        # Step 1: Find round IDs linked to this contest (simplified approach)
        all_round_ids = []
        
        try:
            # Method 1: Via round_contests table
            round_ids_via_table = db.query(round_contests.c.round_id).filter(
                round_contests.c.contest_id == contest_id
            ).all()
            if round_ids_via_table:
                all_round_ids.extend([r[0] for r in round_ids_via_table])
        except Exception as e:
            logger.warning(f"Error querying round_contests: {e}")
        
        try:
            # Method 2: Via legacy round.contest_id
            legacy_rounds = db.query(Round.id).filter(Round.contest_id == contest_id).all()
            if legacy_rounds:
                all_round_ids.extend([r[0] for r in legacy_rounds])
        except Exception as e:
            logger.warning(f"Error querying legacy rounds: {e}")
        
        # Remove duplicates
        all_round_ids = list(set(all_round_ids))
        
        # DEBUG: First check if ANY contestants exist for this contest (without filters)
        debug_query = db.query(
            Contestant.id,
            Contestant.season_id,
            Contestant.round_id,
            Contestant.is_deleted
        ).filter(Contestant.is_deleted == False)
        
        # Try to find contestants by ANY possible link
        debug_conditions = []
        if all_round_ids:
            debug_conditions.append(Contestant.round_id.in_(all_round_ids))
        debug_conditions.append(Contestant.season_id == contest_id)
        
        if debug_conditions:
            debug_results = debug_query.filter(or_(*debug_conditions)).limit(10).all()
            logger.info(f"[DEBUG] Found {len(debug_results)} contestants matching contest_id={contest_id}, round_ids={all_round_ids}")
            for d in debug_results:
                logger.info(f"[DEBUG] Contestant id={d.id}, season_id={d.season_id}, round_id={d.round_id}")
        else:
            # If no conditions, check ALL non-deleted contestants to see what exists
            all_contestants_sample = db.query(
                Contestant.id,
                Contestant.season_id,
                Contestant.round_id
            ).filter(Contestant.is_deleted == False).limit(20).all()
            logger.warning(f"[DEBUG] No round_ids found. Sample of all contestants: {[(c.id, c.season_id, c.round_id) for c in all_contestants_sample]}")
        
        # Step 2: Build simplified query - try season_id first (most common)
        query = db.query(Contestant).filter(Contestant.is_deleted == False)
        
        # Build OR conditions (comprehensive - handle all cases)
        conditions = []
        
        # Condition 1: season_id matches contest_id
        conditions.append(Contestant.season_id == contest_id)
        
        # Condition 2: round_id matches any of the found rounds
        if all_round_ids:
            conditions.append(Contestant.round_id.in_(all_round_ids))
        
        # Condition 3: Handle NULL season_id but valid round_id (for migrated data)
        if all_round_ids:
            conditions.append(
                and_(
                    Contestant.season_id.is_(None),
                    Contestant.round_id.in_(all_round_ids)
                )
            )
        
        # Apply OR condition
        if conditions:
            query = query.filter(or_(*conditions))
        else:
            # Fallback: if no conditions, just query by season_id
            query = query.filter(Contestant.season_id == contest_id)
        
        # Apply geographic filters
        if filter_country:
            query = query.filter(func.lower(Contestant.country) == func.lower(filter_country))
        if filter_region:
            query = query.filter(func.lower(Contestant.region) == func.lower(filter_region))
        if filter_continent:
            query = query.filter(func.lower(Contestant.continent) == func.lower(filter_continent))
        if filter_city:
            query = query.filter(func.lower(Contestant.city) == func.lower(filter_city))
        if user_id:
            query = query.filter(Contestant.user_id == user_id)
        
        # Get contestants with relations (limit joins to avoid timeouts)
        # Note: We'll sort by votes after fetching stats, but order by registration_date as fallback
        try:
            contestants = query.options(
                joinedload(Contestant.user)
            ).order_by(Contestant.registration_date.desc()).offset(skip).limit(limit * 2).all()  # Fetch more to sort properly
        except Exception as e:
            logger.error(f"Error fetching contestants with relations: {e}")
            # Fallback: fetch without relations
            contestants = query.order_by(Contestant.registration_date.desc()).offset(skip).limit(limit * 2).all()
        
        # If no contestants found, try simpler fallback
        if not contestants:
            logger.warning(f"[get_contest_contestants] No contestants found with filters. Trying fallback queries...")
            
            # Fallback 1: Try by season_id only (no geographic filters)
            try:
                fallback1 = db.query(Contestant).filter(
                    Contestant.is_deleted == False,
                    Contestant.season_id == contest_id
                ).limit(limit).all()
                logger.info(f"[get_contest_contestants] Fallback 1 (season_id only): Found {len(fallback1)} contestants")
                if fallback1:
                    contestants = fallback1
            except Exception as e:
                logger.error(f"Error in fallback 1: {e}")
            
            # Fallback 2: Try by round_id only (if we have round_ids)
            if not contestants and all_round_ids:
                try:
                    fallback2 = db.query(Contestant).filter(
                        Contestant.is_deleted == False,
                        Contestant.round_id.in_(all_round_ids)
                    ).limit(limit).all()
                    logger.info(f"[get_contest_contestants] Fallback 2 (round_id only): Found {len(fallback2)} contestants")
                    if fallback2:
                        contestants = fallback2
                except Exception as e:
                    logger.error(f"Error in fallback 2: {e}")
            
            # Fallback 3: Try ANY non-deleted contestant (for debugging)
            if not contestants:
                try:
                    fallback3 = db.query(Contestant).filter(
                        Contestant.is_deleted == False
                    ).limit(5).all()
                    logger.warning(f"[get_contest_contestants] Fallback 3 (ANY contestant): Found {len(fallback3)} contestants. Sample IDs: {[c.id for c in fallback3]}")
                except Exception as e:
                    logger.error(f"Error in fallback 3: {e}")
            
            # Apply geographic filters to fallback results if we found any
            if contestants and (filter_country or filter_region or filter_continent or filter_city):
                original_count = len(contestants)
                if filter_country:
                    contestants = [c for c in contestants if c.country and func.lower(c.country) == func.lower(filter_country)]
                if filter_region:
                    contestants = [c for c in contestants if c.region and func.lower(c.region) == func.lower(filter_region)]
                if filter_continent:
                    contestants = [c for c in contestants if c.continent and func.lower(c.continent) == func.lower(filter_continent)]
                if filter_city:
                    contestants = [c for c in contestants if c.city and func.lower(c.city) == func.lower(filter_city)]
                logger.info(f"[get_contest_contestants] After geographic filters: {len(contestants)}/{original_count} contestants remain")
            
            # Apply user_id filter if specified
            if contestants and user_id:
                contestants = [c for c in contestants if c.user_id == user_id]
            
            # Load user relations for fallback results
            if contestants:
                contestant_ids = [c.id for c in contestants]
                contestants_with_users = db.query(Contestant).filter(
                    Contestant.id.in_(contestant_ids)
                ).options(joinedload(Contestant.user)).all()
                contestants = contestants_with_users
        
        # Enrich contestants with stats (with error handling)
        contestant_ids = [c.id for c in contestants] if contestants else []
        
        if not contestant_ids:
            return []
        
        # Initialize stats dictionaries
        votes_by_contestant = {}
        favorites_by_contestant = {}
        reactions_by_contestant = {}
        comments_by_contestant = {}
        
        # Get stats with error handling for each query
        try:
            from app.models.voting import Vote, ContestLike, ContestComment
            
            votes_results = db.query(Vote.contestant_id, func.count(Vote.id))\
                .filter(Vote.contestant_id.in_(contestant_ids))\
                .group_by(Vote.contestant_id).all()
            votes_by_contestant = {cid: count for cid, count in votes_results}
        except Exception as e:
            logger.warning(f"Error fetching votes: {e}")
        
        try:
            fav_results = db.query(MyFavorites.contestant_id, func.count(MyFavorites.id))\
                .filter(MyFavorites.contestant_id.in_(contestant_ids))\
                .group_by(MyFavorites.contestant_id).all()
            favorites_by_contestant = {cid: count for cid, count in fav_results}
        except Exception as e:
            logger.warning(f"Error fetching favorites: {e}")
        
        try:
            like_results = db.query(ContestLike.contestant_id, func.count(ContestLike.id))\
                .filter(ContestLike.contestant_id.in_(contestant_ids))\
                .group_by(ContestLike.contestant_id).all()
            reactions_by_contestant = {cid: count for cid, count in like_results}
        except Exception as e:
            logger.warning(f"Error fetching reactions: {e}")
        
        try:
            comment_results = db.query(ContestComment.contestant_id, func.count(ContestComment.id))\
                .filter(ContestComment.contestant_id.in_(contestant_ids))\
                .group_by(ContestComment.contestant_id).all()
            comments_by_contestant = {cid: count for cid, count in comment_results}
        except Exception as e:
            logger.warning(f"Error fetching comments: {e}")
        
        # Calculate ranks
        ranked_contestants = sorted(
            [(c.id, votes_by_contestant.get(c.id, 0)) for c in contestants],
            key=lambda x: x[1],
            reverse=True
        )
        ranks = {cid: rank + 1 for rank, (cid, _) in enumerate(ranked_contestants)}
        
        # Check user votes (with error handling)
        user_votes = set()
        current_user_id = current_user.id if current_user else None
        if current_user_id:
            try:
                from app.models.voting import Vote
                user_votes_list = db.query(Vote.contestant_id)\
                    .filter(Vote.voter_id == current_user_id, Vote.contestant_id.in_(contestant_ids))\
                    .all()
                user_votes = {row[0] for row in user_votes_list}
            except Exception as e:
                logger.warning(f"Error fetching user votes: {e}")
        
        # Build enriched response
        import json
        contestants_data = []
        for contestant in contestants:
            # Count images and videos
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
            
            can_vote = False
            if current_user_id and current_user_id != contestant.user_id:
                can_vote = contestant.id not in user_votes
            
            contestants_data.append({
                "id": contestant.id,
                "user_id": contestant.user_id,
                "season_id": contestant.season_id,
                "round_id": contestant.round_id,
                "title": contestant.title,
                "description": contestant.description,
                "image_media_ids": contestant.image_media_ids,
                "video_media_ids": contestant.video_media_ids,
                "nominator_city": contestant.nominator_city,
                "nominator_country": contestant.nominator_country,
                "registration_date": contestant.registration_date,
                "is_qualified": contestant.is_qualified,
                "author_name": contestant.user.full_name or f"{contestant.user.first_name or ''} {contestant.user.last_name or ''}".strip() if contestant.user else None,
                "author_country": contestant.user.country if contestant.user else None,
                "author_city": contestant.user.city if contestant.user else None,
                "author_continent": contestant.user.continent if contestant.user else None,
                "author_region": contestant.user.region if contestant.user else None,
                "author_avatar_url": contestant.user.avatar_url if contestant.user else None,
                "country": contestant.country,
                "city": contestant.city,
                "continent": contestant.continent,
                "region": contestant.region,
                "rank": ranks.get(contestant.id),
                "votes_count": votes_by_contestant.get(contestant.id, 0),
                "images_count": images_count,
                "videos_count": videos_count,
                "favorites_count": favorites_by_contestant.get(contestant.id, 0),
                "reactions_count": reactions_by_contestant.get(contestant.id, 0),
                "comments_count": comments_by_contestant.get(contestant.id, 0),
                "has_voted": contestant.id in user_votes,
                "can_vote": can_vote,
            })
        
        # Sort by votes descending first (most votes first), then by rank
        # This ensures contestants with most participants/votes appear at top immediately
        contestants_data.sort(key=lambda x: (
            -x["votes_count"],  # Votes first (descending - most votes first)
            x.get("rank", float('inf'))  # Then by rank (lower is better)
        ))
        
        # Log pour vérifier les données
        if contestants_data and len(contestants_data) > 0:
            first_contestant = contestants_data[0]
            print(f"[ContestantEndpoint] First contestant data: id={first_contestant.get('id')}, image_media_ids={first_contestant.get('image_media_ids')}, video_media_ids={first_contestant.get('video_media_ids')}")
        
    except Exception as e:
        import traceback
        logger.error(f"[ContestantEndpoint] ERROR fetching contestants for contest {contest_id}: {str(e)}")
        logger.error(traceback.format_exc())
        # Return empty array instead of raising exception to prevent network errors
        # This allows the frontend to handle gracefully
        return []
    
    # Convertir en schéma Pydantic
    try:
        result = [ContestantWithAuthorAndStats(**data) for data in contestants_data]
    except Exception as e:
        logger.error(f"[ContestantEndpoint] ERROR serializing contestants: {str(e)}")
        # Return empty array if serialization fails
        return []
    
    return result


# Routes génériques après les routes spécifiques

@router.post("/{contest_id}", response_model=ContestantSubmissionResponse)
def create_contestant(
    *,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
    contest_id: int,
    contestant_data: ContestantCreate
) -> ContestantSubmissionResponse:
    """
    Créer une nouvelle candidature pour un concours
    
    - Prend le contest_id depuis l'URL (peut être Contest.id ou ContestSeason.id)
    - Vérifie que le concours existe
    - Vérifie que l'utilisateur n'a pas déjà une candidature
    - Vérifie que les soumissions sont ouvertes (pas de soumission si le vote est ouvert)
    - Crée la candidature avec titre, description et médias
    """
    from app.services.contest_status import contest_status_service
    
    # Essayer d'abord de trouver une ContestSeason avec cet ID
    season = db.query(ContestSeason).filter(
        ContestSeason.id == contest_id,
        ContestSeason.is_deleted == False
    ).first()
    
    # Si pas trouvé, chercher dans la table Contest
    contest = None
    if not season:
        from app.models.contest import Contest as MyfavContest
        contest = db.query(MyfavContest).filter(
            MyfavContest.id == contest_id,
            MyfavContest.is_deleted == False
        ).first()
        if not contest:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Contest not found"
            )
        # Vérifier que les soumissions sont autorisées
        is_allowed, error_message = contest_status_service.check_submission_allowed(db, contest_id)
        if not is_allowed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_message
            )
        # Utiliser l'ID du Contest directement comme season_id
        # Le modèle Contestant accepte n'importe quel season_id
        season_id = contest_id
    else:
        season_id = season.id
        # Si c'est une saison, vérifier si elle est liée à un contest
        from app.models.contests import ContestSeasonLink
        contest_link = db.query(ContestSeasonLink).filter(
            ContestSeasonLink.season_id == season_id,
            ContestSeasonLink.is_active == True
        ).first()
        if contest_link:
            from app.models.contest import Contest as MyfavContest
            contest = db.query(MyfavContest).filter(
                MyfavContest.id == contest_link.contest_id,
                MyfavContest.is_deleted == False
            ).first()
            if contest:
                is_allowed, error_message = contest_status_service.check_submission_allowed(db, contest.id)
                if not is_allowed:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=error_message
                    )
    
    # Vérifier les restrictions de genre si le contest existe
    if contest:
        # Récupérer la restriction de genre (peut venir de gender_restriction ou voting_restriction)
        gender_restriction = contest.gender_restriction
        
        # Si pas de gender_restriction directe, vérifier voting_restriction
        if not gender_restriction and hasattr(contest, 'voting_restriction') and contest.voting_restriction:
            # Accéder à la valeur de l'enum de manière sécurisée
            voting_restriction_value = contest.voting_restriction.value if hasattr(contest.voting_restriction, 'value') else str(contest.voting_restriction)
            voting_restriction_str = voting_restriction_value.lower().strip()
            
            # MALE_ONLY signifie que seuls les hommes peuvent participer
            if voting_restriction_str == 'male_only':
                gender_restriction = 'male'
            # FEMALE_ONLY signifie que seules les femmes peuvent participer
            elif voting_restriction_str == 'female_only':
                gender_restriction = 'female'
        
        # Vérifier si l'utilisateur respecte la restriction de genre pour participer
        if gender_restriction:
            if not current_user.gender:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Your profile does not contain gender information. Please complete your profile to participate in this contest."
                )
            
            # Récupérer le genre de l'utilisateur de manière sécurisée
            user_gender = current_user.gender.value.lower() if hasattr(current_user.gender, 'value') else str(current_user.gender).lower()
            gender_restriction_lower = gender_restriction.lower()
            
            # Vérifier la correspondance : si le contest est MALE_ONLY, seuls les hommes peuvent participer
            # Si le contest est FEMALE_ONLY, seules les femmes peuvent participer
            if gender_restriction_lower == 'male' and user_gender != 'male':
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="This contest is reserved for male participants only."
                )
            elif gender_restriction_lower == 'female' and user_gender != 'female':
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="This contest is reserved for female participants only."
                )
    
    # Determine the target round before checking participation
    target_round_id = contestant_data.round_id
    from app.models.round import Round
    
    # Extract real_contest_id needed for validations
    real_contest_id = contest.id if hasattr(contest, "id") and contest else contest_id
    if not contest and season:
        from app.models.contests import ContestSeasonLink
        link = db.query(ContestSeasonLink).filter(ContestSeasonLink.season_id == season.id, ContestSeasonLink.is_active == True).first()
        if link:
            real_contest_id = link.contest_id
            
    if target_round_id:
        round_obj = db.query(Round).filter(Round.id == target_round_id).first()
        if not round_obj:
            raise HTTPException(status_code=404, detail="Round id not found")
            
        # The round might belong directly to the contest we found (via legacy contest_id OR via round_contests N:N table).
        # Check both the legacy column and the many-to-many relationship.
        from app.models.round import round_contests
        round_belongs_to_contest = False
        
        if real_contest_id:
            # Check legacy contest_id column
            if round_obj.contest_id == real_contest_id:
                round_belongs_to_contest = True
            else:
                # Check N:N round_contests association table
                nn_link = db.query(round_contests).filter(
                    round_contests.c.round_id == target_round_id,
                    round_contests.c.contest_id == real_contest_id
                ).first()
                if nn_link:
                    round_belongs_to_contest = True
        
        if real_contest_id and not round_belongs_to_contest:
            # Maybe the user participated directly with the season ID in the URL, verify it matches
            if season and not contest:
                link = db.query(ContestSeasonLink).filter(
                    ContestSeasonLink.season_id == season.id, 
                    ContestSeasonLink.contest_id == round_obj.contest_id,
                    ContestSeasonLink.is_active == True
                ).first()
                if not link:
                    # Also check via round_contests N:N table
                    for rc_contest_id_row in db.query(round_contests.c.contest_id).filter(round_contests.c.round_id == target_round_id).all():
                        link = db.query(ContestSeasonLink).filter(
                            ContestSeasonLink.season_id == season.id, 
                            ContestSeasonLink.contest_id == rc_contest_id_row[0],
                            ContestSeasonLink.is_active == True
                        ).first()
                        if link:
                            break
                    if not link:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST, 
                            detail=f"Requested round does not belong to this contest/season"
                        )
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, 
                    detail=f"Requested round does not belong to this contest"
                )
    else:
        # Trouver le round actif
        if real_contest_id:
            from app import crud
            active_round = crud.round.get_active_round_for_contest(db, real_contest_id)
            if active_round:
                target_round_id = active_round.id
                
    if not target_round_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active round found for this contest. Participation requires an active round."
        )

    # Vérifier que l'utilisateur n'a pas déjà une candidature POUR CE ROUND
    existing = crud_contestant.get_by_round_and_user(
        db, target_round_id, current_user.id
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You already have a submission for this round of the contest"
        )
    
    # ============================================
    # MODÉRATION DU CONTENU AVANT CRÉATION
    # ============================================
    import json
    import logging
    from app.models.media import Media
    
    logger = logging.getLogger(__name__)
    logger.info(f"Starting content moderation for contestant submission by user {current_user.id}")
    
    # Modérer le texte (titre et description)
    text_to_moderate = f"{contestant_data.title} {contestant_data.description}"
    logger.info("Moderating text content...")
    text_moderation = content_moderation_service.moderate_text(text_to_moderate)
    logger.info(f"Text moderation completed: approved={text_moderation.is_approved}")
    
    if not text_moderation.is_approved:
        flags_desc = ", ".join([f.description for f in text_moderation.flags])
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Text content rejected: {flags_desc}"
        )
    
    # Helper pour extraire l'URL d'un média (ID ou URL directe)
    def get_media_url(media_ref: Any) -> Optional[str]:
        """Retourne l'URL du média, que ce soit un ID ou une URL directe"""
        if isinstance(media_ref, str):
            # Si c'est déjà une URL
            if media_ref.startswith(('http://', 'https://')):
                return media_ref
            # Si c'est un ID sous forme de string
            try:
                media_id = int(media_ref)
                media = db.query(Media).filter(Media.id == media_id).first()
                return media.url if media else None
            except ValueError:
                return None
        elif isinstance(media_ref, int):
            media = db.query(Media).filter(Media.id == media_ref).first()
            return media.url if media else None
        return None
    
    # Modérer les images si présentes
    if contestant_data.image_media_ids:
        logger.info(f"Moderating images: {contestant_data.image_media_ids[:100]}")
        try:
            image_refs = json.loads(contestant_data.image_media_ids)
            if isinstance(image_refs, list):
                for idx, media_ref in enumerate(image_refs[:10]):  # Max 10 images
                    media_url = get_media_url(media_ref)
                    if media_url:
                        logger.info(f"Moderating image {idx+1}/{len(image_refs)}")
                        moderation_result = content_moderation_service.moderate_image(media_url)
                        logger.info(f"Image {idx+1} moderation: approved={moderation_result.is_approved}")
                        if not moderation_result.is_approved:
                            flags_desc = ", ".join([f.description for f in moderation_result.flags])
                            raise HTTPException(
                                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                                detail=f"Image rejected by moderation: {flags_desc}"
                            )
        except json.JSONDecodeError as e:
            logger.warning(f"JSON decode error for image_media_ids: {e}")
    else:
        logger.info("No images to moderate")
    
    # Modérer les vidéos si présentes
    if contestant_data.video_media_ids:
        logger.info(f"Moderating videos: {contestant_data.video_media_ids[:100]}")
        try:
            video_refs = json.loads(contestant_data.video_media_ids)
            if isinstance(video_refs, list):
                for idx, media_ref in enumerate(video_refs[:5]):  # Max 5 vidéos
                    media_url = get_media_url(media_ref)
                    if media_url:
                        logger.info(f"Moderating video {idx+1}/{len(video_refs)}")
                        moderation_result = content_moderation_service.moderate_video(media_url)
                        logger.info(f"Video {idx+1} moderation: approved={moderation_result.is_approved}")
                        if not moderation_result.is_approved:
                            flags_desc = ", ".join([f.description for f in moderation_result.flags])
                            raise HTTPException(
                                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                                detail=f"Video rejected by moderation: {flags_desc}"
                            )
        except json.JSONDecodeError as e:
            logger.warning(f"JSON decode error for video_media_ids: {e}")
    else:
        logger.info("No videos to moderate")
    
    logger.info("Content moderation completed successfully")
    
    # ============================================
    # VÉRIFICATION DE LA PERTINENCE
    # ============================================
    logger.info("Starting relevance check...")
    
    # Récupérer les infos du concours pour la vérification de pertinence
    contest_title = ""
    contest_description = ""
    contest_type = None
    
    if contest:
        contest_title = contest.name or ""
        contest_description = contest.description or ""
        contest_type = getattr(contest, 'contest_type', None)
        if contest_type and hasattr(contest_type, 'value'):
            contest_type = contest_type.value
    elif season:
        contest_title = season.title or ""
        contest_description = getattr(season, 'description', "") or ""
    
    # Vérifier la pertinence de la candidature par rapport au concours
    relevance_result = content_relevance_service.check_relevance(
        contestant_title=contestant_data.title,
        contestant_description=contestant_data.description,
        contest_title=contest_title,
        contest_description=contest_description,
        contest_type=contest_type
    )
    
    logger.info(f"Relevance check completed: is_relevant={relevance_result.is_relevant}, score={relevance_result.score}")
    
    if not relevance_result.is_relevant:
        suggestions_text = " ".join(relevance_result.suggestions[:2])
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Submission not relevant for this contest. {suggestions_text}"
        )
    
    # ============================================
    # VALIDATION DU PAYS DU NOMINATEUR
    # ============================================
    if contestant_data.nominator_country:
        user_country = current_user.country
        if user_country and contestant_data.nominator_country.lower().strip() != user_country.lower().strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"The nominator country must match your country. Your country: {user_country}, Specified: {contestant_data.nominator_country}"
            )
    
    # ============================================
    # CRÉATION DE LA CANDIDATURE
    # ============================================
    logger.info("Starting contestant creation...")
    # Créer la candidature
    try:
        # Lier automatiquement le contestant à la saison "city"
        from app.services.season_migration import SeasonMigrationService
        from datetime import datetime


        # Trouver ou créer la saison "city" avant de créer le contestant
        # IMPORTANT: Utiliser le round_id pour scoper la saison
        city_season = SeasonMigrationService.get_or_create_season(
            db, 
            level=SeasonLevel.CITY,
            title="Saison City",
            round_id=target_round_id
        )
        
        # Créer la candidature
        contestant = crud_contestant.create(
            db, 
            user_id=current_user.id,
            season_id=season_id,
            title=contestant_data.title,
            description=contestant_data.description,
            image_media_ids=contestant_data.image_media_ids,
            video_media_ids=contestant_data.video_media_ids,
            nominator_city=contestant_data.nominator_city,
            nominator_country=contestant_data.nominator_country,
            round_id=target_round_id
        )
        
        # Vérifier si le lien existe déjà
        existing_link = db.query(ContestantSeason).filter(
            ContestantSeason.contestant_id == contestant.id,
            ContestantSeason.season_id == city_season.id
        ).first()
        
        if not existing_link:
            # Créer le lien contestant-season pour la saison city
            contestant_season_link = ContestantSeason(
                contestant_id=contestant.id,
                season_id=city_season.id,
                joined_at=datetime.utcnow(),
                is_active=True
            )
            db.add(contestant_season_link)
            db.commit()
            db.refresh(contestant)
    except ValueError as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating submission: {str(e)}"
        )
    
    return ContestantSubmissionResponse(
        id=contestant.id,
        season_id=contestant.season_id,
        round_id=contestant.round_id,
        user_id=contestant.user_id,
        title=contestant.title,
        description=contestant.description,
        registration_date=contestant.registration_date,
        message="Submission created successfully."
    )


@router.get("/{contestant_id}", response_model=ContestantWithAuthorAndStats)
def get_contestant(
    *,
    db: Session = Depends(deps.get_db),
    contestant_id: int,
    current_user: Optional[User] = Depends(deps.get_current_active_user_optional)
) -> ContestantWithAuthorAndStats:
    """Récupère les détails d'une candidature avec infos auteur et stats enrichies"""
    contestant_data = crud_contestant.get_with_stats(
        db, contestant_id, current_user_id=current_user.id if current_user else None
    )
    if not contestant_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Submission not found"
        )
    
    return ContestantWithAuthorAndStats(**contestant_data)


@router.post("/{contestant_id}/submission")
def add_submission(
    *,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
    contestant_id: int,
    media_type: str = Query(...),
    file_url: Optional[str] = Query(None),
    external_url: Optional[str] = Query(None),
    title: Optional[str] = Query(None),
    description: Optional[str] = Query(None)
) -> dict:
    """Ajoute une soumission à une candidature"""
    # Vérifier que la candidature existe
    contestant = crud_contestant.get(db, contestant_id)
    if not contestant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Submission not found"
        )
    
    # Vérifier que c'est le propriétaire
    if contestant.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only add a submission for your own submission"
        )
    
    # Ajouter la soumission
    submission = crud_contestant.add_submission(
        db,
        contestant_id=contestant_id,
        media_type=media_type,
        file_url=file_url,
        external_url=external_url,
        title=title,
        description=description
    )
    
    return {"message": "Submission added successfully", "submission_id": submission.id}


# Routes spécifiques pour les favoris (DOIVENT venir AVANT les routes génériques avec {id})
@router.post("/{contestant_id}/favorite")
def add_to_favorites(
    *,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
    contestant_id: int
) -> dict:
    """Ajoute un contestant aux favoris de l'utilisateur"""
    # Vérifier que le contestant existe
    contestant = crud_contestant.get(db, contestant_id)
    if not contestant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contestant not found"
        )
    
    # Vérifier que l'utilisateur n'a pas déjà ce contestant en favoris
    existing = db.query(MyFavorites).filter(
        and_(
            MyFavorites.user_id == current_user.id,
            MyFavorites.contestant_id == contestant_id
        )
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This contestant is already in your favorites"
        )
    
    # Vérifier la limite de 5 favoris
    favorites_count = db.query(MyFavorites).filter(
        MyFavorites.user_id == current_user.id
    ).count()
    
    if favorites_count >= 5:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You have reached the limit of 5 favorites"
        )
    
    # Ajouter aux favoris
    favorite = MyFavorites(
        user_id=current_user.id,
        contestant_id=contestant_id
    )
    db.add(favorite)
    db.commit()
    
    return {"message": f"Contestant added to favorites"}


@router.delete("/{contestant_id}/favorite")
def remove_from_favorites(
    *,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
    contestant_id: int
) -> dict:
    """Retire un contestant des favoris de l'utilisateur"""
    # Vérifier que le contestant existe
    contestant = crud_contestant.get(db, contestant_id)
    if not contestant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contestant not found"
        )
    
    # Trouver et supprimer le favori
    favorite = db.query(MyFavorites).filter(
        and_(
            MyFavorites.user_id == current_user.id,
            MyFavorites.contestant_id == contestant_id
        )
    ).first()
    
    if not favorite:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="This contestant is not in your favorites"
        )
    
    db.delete(favorite)
    db.commit()
    
    return {"message": "Contestant removed from favorites"}


# Routes génériques (DOIVENT venir APRÈS les routes spécifiques)
@router.put("/{contestant_id}", response_model=ContestantResponse)
def update_contestant(
    *,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
    contestant_id: int,
    contestant_data: ContestantCreate
) -> ContestantResponse:
    """Met à jour une candidature (l'utilisateur peut mettre à jour sa propre candidature)"""
    # Vérifier que la candidature existe
    contestant = crud_contestant.get(db, contestant_id)
    if not contestant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Submission not found"
        )
    
    # Vérifier que c'est le propriétaire
    if contestant.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only update your own submission"
        )
    
    # ============================================
    # MODÉRATION DU CONTENU AVANT MISE À JOUR
    # ============================================
    import json
    import logging
    from app.models.media import Media
    
    logger = logging.getLogger(__name__)
    logger.info(f"Starting content moderation for contestant update by user {current_user.id}")
    
    # Modérer le texte (titre et description)
    text_to_moderate = f"{contestant_data.title} {contestant_data.description}"
    logger.info("Moderating text content...")
    text_moderation = content_moderation_service.moderate_text(text_to_moderate)
    logger.info(f"Text moderation completed: approved={text_moderation.is_approved}")
    
    if not text_moderation.is_approved:
        flags_desc = ", ".join([f.description for f in text_moderation.flags])
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Text content rejected: {flags_desc}"
        )
    
    # Helper pour extraire l'URL d'un média (ID ou URL directe)
    def get_media_url(media_ref: Any) -> Optional[str]:
        if isinstance(media_ref, str):
            if media_ref.startswith(('http://', 'https://')):
                return media_ref
            try:
                media_id = int(media_ref)
                media = db.query(Media).filter(Media.id == media_id).first()
                return media.url if media else None
            except ValueError:
                return None
        elif isinstance(media_ref, int):
            media = db.query(Media).filter(Media.id == media_ref).first()
            return media.url if media else None
        return None
    
    # Modérer les images si présentes
    if contestant_data.image_media_ids:
        logger.info(f"Moderating images: {contestant_data.image_media_ids[:100]}")
        try:
            image_refs = json.loads(contestant_data.image_media_ids)
            if isinstance(image_refs, list):
                for idx, media_ref in enumerate(image_refs[:10]):
                    media_url = get_media_url(media_ref)
                    if media_url:
                        logger.info(f"Moderating image {idx+1}/{len(image_refs)}")
                        moderation_result = content_moderation_service.moderate_image(media_url)
                        logger.info(f"Image {idx+1} moderation: approved={moderation_result.is_approved}")
                        if not moderation_result.is_approved:
                            flags_desc = ", ".join([f.description for f in moderation_result.flags])
                            raise HTTPException(
                                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                                detail=f"Image rejected by moderation: {flags_desc}"
                            )
        except json.JSONDecodeError as e:
            logger.warning(f"JSON decode error for image_media_ids: {e}")
    else:
        logger.info("No images to moderate")
    
    # Modérer les vidéos si présentes
    if contestant_data.video_media_ids:
        logger.info(f"Moderating videos: {contestant_data.video_media_ids[:100]}")
        try:
            video_refs = json.loads(contestant_data.video_media_ids)
            if isinstance(video_refs, list):
                for idx, media_ref in enumerate(video_refs[:5]):
                    media_url = get_media_url(media_ref)
                    if media_url:
                        logger.info(f"Moderating video {idx+1}/{len(video_refs)}")
                        moderation_result = content_moderation_service.moderate_video(media_url)
                        logger.info(f"Video {idx+1} moderation: approved={moderation_result.is_approved}")
                        if not moderation_result.is_approved:
                            flags_desc = ", ".join([f.description for f in moderation_result.flags])
                            raise HTTPException(
                                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                                detail=f"Video rejected by moderation: {flags_desc}"
                            )
        except json.JSONDecodeError as e:
            logger.warning(f"JSON decode error for video_media_ids: {e}")
    else:
        logger.info("No videos to moderate")
    
    logger.info("Content moderation completed successfully")
    
    # ============================================
    # VÉRIFICATION DE LA PERTINENCE
    # ============================================
    logger.info(f"Starting relevance check for contestant update {contestant_id}")
    
    # Récupérer les infos du concours pour la vérification de pertinence
    contest_title = ""
    contest_description = ""
    contest_type = None
    
    # Essayer de récupérer le Contest associé
    from app.models.contest import Contest as MyfavContest
    contest = db.query(MyfavContest).filter(
        MyfavContest.id == contestant.season_id,
        MyfavContest.is_deleted == False
    ).first()
    
    if contest:
        contest_title = contest.name or ""
        contest_description = contest.description or ""
        contest_type = getattr(contest, 'contest_type', None)
        if contest_type and hasattr(contest_type, 'value'):
            contest_type = contest_type.value
    else:
        # Sinon, essayer de récupérer la ContestSeason
        season = db.query(ContestSeason).filter(ContestSeason.id == contestant.season_id).first()
        if season:
            contest_title = season.title or ""
            contest_description = getattr(season, 'description', "") or ""
    
    # Vérifier la pertinence de la candidature par rapport au concours
    relevance_result = content_relevance_service.check_relevance(
        contestant_title=contestant_data.title,
        contestant_description=contestant_data.description,
        contest_title=contest_title,
        contest_description=contest_description,
        contest_type=contest_type
    )
    
    logger.info(f"Relevance check completed: is_relevant={relevance_result.is_relevant}, score={relevance_result.score}")
    
    if not relevance_result.is_relevant:
        suggestions_text = " ".join(relevance_result.suggestions[:2])
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Submission not relevant for this contest. {suggestions_text}"
        )
    
    # ============================================
    # VALIDATION DU PAYS DU NOMINATEUR
    # ============================================
    if contestant_data.nominator_country:
        user_country = current_user.country
        if user_country and contestant_data.nominator_country.lower().strip() != user_country.lower().strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"The nominator country must match your country. Your country: {user_country}, Specified: {contestant_data.nominator_country}"
            )
    
    # Mettre à jour la candidature
    updated_contestant = crud_contestant.update(
        db,
        id=contestant_id,
        title=contestant_data.title,
        description=contestant_data.description,
        image_media_ids=contestant_data.image_media_ids,
        video_media_ids=contestant_data.video_media_ids,
        nominator_city=contestant_data.nominator_city,
        nominator_country=contestant_data.nominator_country
    )
    
    return ContestantResponse.model_validate(updated_contestant)


@router.delete("/{contestant_id}")
def delete_contestant(
    *,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
    contestant_id: int
) -> dict:
    """Supprime une candidature (l'utilisateur peut supprimer sa propre candidature)"""
    contestant = crud_contestant.get(db, contestant_id)
    if not contestant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Submission not found"
        )
    
    # Vérifier que la candidature n'est pas déjà supprimée
    if contestant.is_deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Submission already deleted"
        )
    
    # Vérifier que c'est le propriétaire ou un admin
    if contestant.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only delete your own submission"
        )
    
    # Vérifier que les soumissions sont encore ouvertes (optionnel, mais recommandé)
    # On peut permettre la suppression même si les soumissions sont fermées
    
    success = crud_contestant.delete(db, id=contestant_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error deleting submission"
        )
    
    return {"message": "Submission deleted successfully"}


@router.post("/{contestant_id}/vote", status_code=status.HTTP_201_CREATED)
def vote_for_contestant(
    *,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
    contestant_id: int
) -> dict:
    """Vote pour un contestant"""
    from app.services.contest_status import contest_status_service
    
    # Vérifier que le contestant existe
    contestant = crud_contestant.get(db, contestant_id)
    if not contestant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Submission not found"
        )
    
    # Vérifier que l'utilisateur ne vote pas pour sa propre candidature
    if contestant.user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot vote for your own submission"
        )
    
    # Récupérer la saison active du contestant via ContestantSeason
    from app.models.contests import ContestSeasonLink, ContestSeason, ContestantSeason
    from app.models.contest import Contest as MyfavContest
    
    # Récupérer la saison active pour ce contestant
    contestant_season_link = db.query(ContestantSeason).filter(
        ContestantSeason.contestant_id == contestant_id,
        ContestantSeason.is_active == True
    ).first()
    
    if not contestant_season_link:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This contestant is not active in any season"
        )
    
    # Récupérer la saison
    season = db.query(ContestSeason).filter(
        ContestSeason.id == contestant_season_link.season_id,
        ContestSeason.is_deleted == False
    ).first()
    
    if not season:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Season not found for this contestant"
        )
    
    # Récupérer le contest associé à cette saison via ContestSeasonLink
    contest_season_link = db.query(ContestSeasonLink).filter(
        ContestSeasonLink.season_id == season.id,
        ContestSeasonLink.is_active == True
    ).first()
    
    if not contest_season_link:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active contest found for this season"
        )
    
    # Récupérer le contest
    contest = db.query(MyfavContest).filter(
        MyfavContest.id == contest_season_link.contest_id,
        MyfavContest.is_deleted == False
    ).first()
    
    if not contest:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Contest not found for this season"
        )
    
    # Vérifier que le vote est ouvert pour ce contest
    is_allowed, error_message = contest_status_service.check_voting_allowed(db, contest.id)
    if not is_allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_message
        )

    # Règles de vote basées sur la localisation et le niveau de la saison
    # city      -> seuls les utilisateurs de la même ville (et même pays) peuvent voter
    # country   -> mêmes pays et continent
    # regional  -> mêmes région et continent
    # continent -> même continent
    # global    -> tout le monde peut voter
    season_level = None
    if hasattr(season, "level") and season.level is not None:
        season_level = season.level.value if hasattr(season.level, "value") else str(season.level)
        if isinstance(season_level, str):
            season_level = season_level.lower()

    from app.models.user import User as MyfavUser

    def locations_match() -> bool:
        if not season_level:
            return True

        lvl = str(season_level).lower()
        voter: MyfavUser = current_user
        author: MyfavUser = contestant.user  # chargé par crud_contestant.get avec joinedload

        if not author:
            return True

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

        if lvl == "city":
            country_match = compare_with_unknown(voter.country, author.country)
            return country_match and compare_with_unknown(voter.city, author.city) if country_match else False
        elif lvl == "country":
            continent_match = compare_with_unknown(voter.continent, author.continent)
            return continent_match and compare_with_unknown(voter.country, author.country) if continent_match else False
        elif lvl in ("regional", "region"):
            v_region = getattr(voter, "region", None)
            a_region = getattr(author, "region", None)
            continent_match = compare_with_unknown(voter.continent, author.continent)
            return continent_match and compare_with_unknown(v_region, a_region) if continent_match else False
        elif lvl == "continent":
            return compare_with_unknown(voter.continent, author.continent)
        else:
            # Pour "global" ou niveau inconnu, on accepte
            return True

    if not locations_match():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot vote for this contestant because you are not in the allowed location for this season"
        )
    
    # Vérifier les restrictions de genre pour le vote
    # Si le contest est MALE_ONLY (réservé aux hommes pour participer), seules les femmes peuvent voter
    # Si le contest est FEMALE_ONLY (réservé aux femmes pour participer), seuls les hommes peuvent voter
    gender_restriction = contest.gender_restriction
    
    # Si pas de gender_restriction directe, vérifier voting_restriction
    if not gender_restriction and hasattr(contest, 'voting_restriction') and contest.voting_restriction:
        voting_restriction_str = str(contest.voting_restriction).lower().strip()
        if voting_restriction_str == 'male_only':
            gender_restriction = 'male'
        elif voting_restriction_str == 'female_only':
            gender_restriction = 'female'
    
    # Vérifier si l'utilisateur respecte la restriction de genre pour voter
    if gender_restriction:
        if not current_user.gender:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Your profile does not contain gender information. Please complete your profile to vote in this contest."
            )
        
        user_gender = current_user.gender.value.lower() if hasattr(current_user.gender, 'value') else str(current_user.gender).lower()
        gender_restriction_lower = gender_restriction.lower()
        
        # Logique inverse : si le contest est réservé aux hommes (pour participer), seules les femmes peuvent voter
        # Si le contest est réservé aux femmes (pour participer), seuls les hommes peuvent voter
        if gender_restriction_lower == 'male':
            # Contest réservé aux hommes pour participer, donc seules les femmes peuvent voter
            if user_gender != 'female':
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="This contest is reserved for male participants. Only female participants can vote."
                )
        elif gender_restriction_lower == 'female':
            # Contest réservé aux femmes pour participer, donc seuls les hommes peuvent voter
            if user_gender != 'male':
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="This contest is reserved for female participants. Only male participants can vote."
                )
    
    # Vérifier si l'utilisateur a déjà voté pour ce contestant dans cette saison active
    # IMPORTANT: Un utilisateur peut voter pour plusieurs contestants différents dans la même saison
    # Mais il ne peut pas voter deux fois pour le même contestant dans la même saison
    # Un utilisateur peut voter à nouveau dans une nouvelle saison, même pour le même contestant
    import logging
    logger = logging.getLogger(__name__)
    
    # Log pour déboguer la saison récupérée
    logger.info(
        f"[VOTE CHECK] Checking vote for user {current_user.id}, contestant {contestant_id}, "
        f"season_id: {season.id}, season_level: {season_level}"
    )
    
    # Vérifier si l'utilisateur a déjà voté pour ce contestant dans cette saison
    # IMPORTANT: La vérification se fait par (user_id, contestant_id, season_id)
    # Un utilisateur peut voter pour plusieurs contestants dans la même saison
    # Mais il ne peut pas voter deux fois pour le même contestant dans la même saison
    existing_vote = db.query(ContestantVoting).filter(
        ContestantVoting.user_id == current_user.id,
        ContestantVoting.contestant_id == contestant_id,
        ContestantVoting.season_id == season.id  # Vérification par (user_id, contestant_id, season_id)
    ).first()
    
    if existing_vote:
        logger.warning(
            f"[VOTE CHECK] User {current_user.id} already voted for contestant {contestant_id} "
            f"in season {season.id} (level: {season_level}). "
            f"Existing vote ID: {existing_vote.id}, vote_date: {existing_vote.vote_date}"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"You have already voted for this contestant in this season."
        )
    
    logger.info(
        f"[VOTE CHECK] User {current_user.id} can vote in season {season.id} "
        f"(no existing vote found for this season)"
    )
    
    # Import pour case
    from sqlalchemy import case
    
    # Récupérer tous les votes existants de l'utilisateur pour cette saison
    # Triés par position (1-5) puis par date (le plus ancien en premier)
    existing_votes_for_season = db.query(ContestantVoting).filter(
        ContestantVoting.user_id == current_user.id,
        ContestantVoting.season_id == season.id
    ).order_by(
        # Les votes avec position définie d'abord, triés par position
        # Puis les votes sans position, triés par date (le plus ancien en premier)
        case(
            (ContestantVoting.position.isnot(None), ContestantVoting.position),
            else_=1000
        ),
        ContestantVoting.vote_date.asc()
    ).all()
    
    # Si on a déjà 5 votes, supprimer le 5ème (le plus ancien ou celui avec position=5)
    if len(existing_votes_for_season) >= 5:
        # Le 5ème vote à supprimer (le plus ancien ou celui avec position=5)
        vote_to_remove = existing_votes_for_season[4]  # Index 4 = 5ème élément
        logger.info(
            f"[VOTE REPLACE] Removing 5th vote (ID: {vote_to_remove.id}, "
            f"contestant_id: {vote_to_remove.contestant_id}, position: {vote_to_remove.position}) "
            f"to make room for new vote"
        )
        db.delete(vote_to_remove)
        # Retirer ce vote de la liste
        existing_votes_for_season = existing_votes_for_season[:4]
    
    # Créer le nouveau vote avec position=1 (le plus récent devient le 1er)
    new_voting = ContestantVoting(
        user_id=current_user.id,
        contestant_id=contestant_id,
        contest_id=contest.id,
        season_id=season.id,
        position=1,  # Le nouveau vote est toujours en position 1
        points=5     # Position 1 = 5 points
    )
    
    try:
        db.add(new_voting)
        db.flush()  # Flush pour obtenir l'ID sans commit
        
        # Réorganiser les positions des votes existants
        # Le nouveau vote est en position 1, les autres descendent (2, 3, 4, 5)
        for idx, existing_vote in enumerate(existing_votes_for_season, start=2):
            new_position = idx
            new_points = 6 - new_position  # 5, 4, 3, 2, 1 -> 4, 3, 2, 1 pour les positions 2-5
            existing_vote.position = new_position
            existing_vote.points = new_points
            logger.info(
                f"[VOTE REORDER] Updated vote ID {existing_vote.id}: "
                f"position={new_position}, points={new_points}"
            )
        
        db.commit()
        db.refresh(new_voting)
        logger.info(
            f"[VOTE SUCCESS] Vote created: user {current_user.id}, contestant {contestant_id}, "
            f"season {season.id}, voting_id: {new_voting.id}, position=1, points=5"
        )
    except Exception as e:
        db.rollback()
        error_str = str(e).lower()
        logger.error(
            f"[VOTE ERROR] Error creating vote: {e}. "
            f"User {current_user.id}, contestant {contestant_id}, season {season.id}"
        )
        
        # Si c'est une erreur de contrainte unique, c'est qu'un vote existe déjà
        if "uq_contestant_voting" in str(e) or "unique constraint" in error_str or "duplicate key" in error_str:
            # Vérifier si c'est l'ancienne contrainte (user_id, contestant_id, contest_id) ou la nouvelle (user_id, season_id)
            error_message = str(e)
            if "(user_id, contestant_id, contest_id)" in error_message:
                # L'ancienne contrainte est encore active - la migration n'a pas été exécutée
                logger.error(
                    f"[VOTE ERROR] Old unique constraint still active. "
                    f"Database migration needs to be run. "
                    f"User {current_user.id}, contestant {contestant_id}, contest {contest.id}, season {season.id}. "
                    f"Error: {error_message}"
                )
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Database migration required. The voting system needs to be updated. Please run: alembic upgrade head OR execute the SQL script in backend/migrations/fix_contestant_voting_constraint.sql"
                )
            
            # Si c'est la nouvelle contrainte (user_id, season_id), vérifier à nouveau
            existing_vote_check = db.query(ContestantVoting).filter(
                ContestantVoting.user_id == current_user.id,
                ContestantVoting.season_id == season.id
            ).first()
            
            if existing_vote_check:
                logger.warning(
                    f"[VOTE ERROR] Duplicate vote detected: user {current_user.id}, "
                    f"season {season.id}, existing vote ID: {existing_vote_check.id}, "
                    f"existing_contestant_id: {existing_vote_check.contestant_id}"
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"You have already voted in this {season_level or 'season'} season. You can only vote once per season (regardless of which contestant you vote for)."
                )
            else:
                # Contrainte unique mais pas de vote trouvé - peut-être que la migration n'a pas été exécutée complètement
                logger.error(
                    f"[VOTE ERROR] Unique constraint violation but no vote found. "
                    f"This might indicate the database migration hasn't been run or completed. "
                    f"User {current_user.id}, season {season.id}, error: {error_message}"
                )
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Database migration may be incomplete. Please run: alembic upgrade head OR execute the SQL script in backend/migrations/fix_contestant_voting_constraint.sql"
                )
        # Sinon, propager l'erreur
        raise
    
    # Mettre à jour les rangs de tous les contestants du contest pour cette saison
    from app.crud.crud_contest import contest as crud_contest
    try:
        crud_contest.update_contestant_rankings(db, contest.id, season.id)
    except Exception as e:
        # Log l'erreur mais ne bloque pas le vote
        import logging
        logging.error(f"Error updating rankings after vote: {e}")
    
    # Créer une notification pour le propriétaire du contestant
    from app.crud.crud_notification import crud_notification
    from app.models.notification import NotificationType
    
    voter_name = current_user.full_name or current_user.username or "Someone"
    crud_notification.create(
        db,
        user_id=contestant.user_id,
        type=NotificationType.CONTEST,
        title="New vote",
        message=f"{voter_name} voted for your application",
        related_contestant_id=contestant_id,
        related_contest_id=contest.id if contest else None
    )
    db.commit()
    
    return {
        "message": f"Vote recorded successfully for {season_level or 'season'} season",
        "voting_id": new_voting.id,
        "season_id": season.id,
        "season_level": season_level
    }


@router.post("/{contestant_id}/reaction", response_model=Reaction, status_code=status.HTTP_201_CREATED)
def add_reaction(
    *,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
    contestant_id: int,
    reaction_in: ReactionCreate
) -> Reaction:
    """Ajouter ou mettre à jour une réaction pour un contestant"""
    # Vérifier que le contestant existe
    contestant = crud_contestant.get(db, contestant_id)
    if not contestant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Submission not found"
        )
    
    # Vérifier que le type de réaction est valide et le convertir en minuscules
    reaction_type_str = reaction_in.reaction_type.lower()
    try:
        reaction_type = ReactionType(reaction_type_str)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid reaction type. Valid types: {[e.value for e in ReactionType]}"
        )
    
    # S'assurer que nous utilisons la valeur de l'enum (string) et non l'enum lui-même
    # Avec native_enum=False, SQLAlchemy stocke la valeur comme string
    reaction_type_value = reaction_type.value
    
    # Vérifier si l'utilisateur a déjà une réaction pour ce contestant
    existing_reaction = db.query(ContestantReaction).filter(
        ContestantReaction.user_id == current_user.id,
        ContestantReaction.contestant_id == contestant_id
    ).first()
    
    if existing_reaction:
        # Mettre à jour la réaction existante
        existing_reaction.reaction_type = reaction_type.value
        db.commit()
        db.refresh(existing_reaction)
        return existing_reaction
    else:
        # Créer une nouvelle réaction
        new_reaction = ContestantReaction(
            user_id=current_user.id,
            contestant_id=contestant_id,
            reaction_type=reaction_type.value  # Utiliser la valeur string de l'enum
        )
        db.add(new_reaction)
        db.commit()
        db.refresh(new_reaction)
        
        # Créer une notification pour le propriétaire du contestant
        if contestant.user_id != current_user.id:
            from app.crud.crud_notification import crud_notification
            from app.models.notification import NotificationType
            
            reactor_name = current_user.full_name or current_user.username or "Someone"
            reaction_emoji = {
                'like': '👍',
                'love': '❤️',
                'wow': '😮',
                'dislike': '👎'
            }.get(reaction_type_str, '👍')
            
            crud_notification.create(
                db,
                user_id=contestant.user_id,
                type=NotificationType.CONTEST,
                title="New reaction",
                message=f"{reactor_name} reacted {reaction_emoji} to your application",
                related_contestant_id=contestant_id
            )
            db.commit()
        
        return new_reaction


@router.delete("/{contestant_id}/reaction", status_code=status.HTTP_200_OK)
def remove_reaction(
    *,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
    contestant_id: int
) -> dict:
    """Supprimer une réaction pour un contestant"""
    # Vérifier que le contestant existe
    contestant = crud_contestant.get(db, contestant_id)
    if not contestant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Submission not found"
        )
    
    # Trouver et supprimer la réaction
    reaction = db.query(ContestantReaction).filter(
        ContestantReaction.user_id == current_user.id,
        ContestantReaction.contestant_id == contestant_id
    ).first()
    
    if not reaction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Reaction not found"
        )
    
    db.delete(reaction)
    db.commit()
    
    return {"message": "Reaction removed successfully"}


@router.get("/{contestant_id}/reactions", response_model=ReactionStats)
def get_reaction_stats(
    *,
    db: Session = Depends(deps.get_db),
    current_user: Optional[User] = Depends(deps.get_current_active_user_optional),
    contestant_id: int
) -> ReactionStats:
    """Récupérer les statistiques de réactions pour un contestant"""
    # Vérifier que le contestant existe
    contestant = crud_contestant.get(db, contestant_id)
    if not contestant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Submission not found"
        )
    
    # Compter les réactions par type
    reactions = db.query(ContestantReaction).filter(
        ContestantReaction.contestant_id == contestant_id
    ).all()
    
    stats = ReactionStats(
        contestant_id=contestant_id,
        total_reactions=len(reactions),
        like_count=sum(1 for r in reactions if r.reaction_type == 'like'),
        love_count=sum(1 for r in reactions if r.reaction_type == 'love'),
        wow_count=sum(1 for r in reactions if r.reaction_type == 'wow'),
        dislike_count=sum(1 for r in reactions if r.reaction_type == 'dislike')
    )
    
    # Si l'utilisateur est connecté, récupérer sa réaction
    if current_user:
        user_reaction = db.query(ContestantReaction).filter(
            ContestantReaction.user_id == current_user.id,
            ContestantReaction.contestant_id == contestant_id
        ).first()
        if user_reaction:
            # reaction_type est maintenant une string
            stats.user_reaction = user_reaction.reaction_type
    
    return stats


@router.post("/{contestant_id}/share", response_model=Share, status_code=status.HTTP_201_CREATED)
def share_contestant(
    *,
    db: Session = Depends(deps.get_db),
    current_user: Optional[User] = Depends(deps.get_current_active_user_optional),
    contestant_id: int,
    share_in: ShareCreate
) -> Share:
    """Enregistrer un partage de contestant avec referral code et métadonnées"""
    # Vérifier que le contestant existe
    contestant = crud_contestant.get(db, contestant_id)
    if not contestant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Submission not found"
        )
    
    # Déterminer qui partage
    shared_by_user_id = share_in.shared_by_user_id or (current_user.id if current_user else None)
    
    # Récupérer le referral code de celui qui partage
    referral_code = share_in.referral_code
    if not referral_code and shared_by_user_id:
        sharing_user = db.query(User).filter(User.id == shared_by_user_id).first()
        if sharing_user and sharing_user.personal_referral_code:
            referral_code = sharing_user.personal_referral_code
    
    # Construire le lien de partage avec le referral code si disponible
    share_link = share_in.share_link
    if referral_code:
        from urllib.parse import urlparse, urlencode, parse_qs, urlunparse
        parsed = urlparse(share_link)
        query_params = parse_qs(parsed.query)
        query_params['ref'] = [referral_code]
        new_query = urlencode(query_params, doseq=True)
        share_link = urlunparse(parsed._replace(query=new_query))
    
    # Créer un nouveau partage avec toutes les informations
    new_share = ContestantShare(
        author_id=contestant.user_id,  # L'auteur du contestant
        shared_by_user_id=shared_by_user_id,  # Celui qui partage
        contestant_id=contestant_id,
        referral_code=referral_code,  # Code de parrainage
        share_link=share_link,  # Lien avec referral code
        platform=share_in.platform,
        # Conserver user_id pour compatibilité
        user_id=contestant.user_id
    )
    
    db.add(new_share)
    db.commit()
    db.refresh(new_share)
    
    return new_share


@router.get("/{contestant_id}/shares", response_model=ShareStats)
def get_share_stats(
    *,
    db: Session = Depends(deps.get_db),
    contestant_id: int
) -> ShareStats:
    """Récupérer les statistiques de partage pour un contestant"""
    from sqlalchemy.orm import joinedload
    
    # Vérifier que le contestant existe et charger l'utilisateur (auteur)
    contestant = db.query(Contestant)\
        .options(joinedload(Contestant.user))\
        .filter(Contestant.id == contestant_id)\
        .first()
    
    if not contestant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Submission not found"
        )
    
    # Récupérer tous les partages avec les utilisateurs
    shares = db.query(ContestantShare)\
        .options(joinedload(ContestantShare.shared_by))\
        .filter(ContestantShare.contestant_id == contestant_id)\
        .order_by(ContestantShare.created_at.desc())\
        .all()
    
    # Compter par plateforme
    shares_by_platform = {}
    for share in shares:
        platform = share.platform or "other"
        shares_by_platform[platform] = shares_by_platform.get(platform, 0) + 1
    
    # Construire la liste des utilisateurs qui ont partagé
    shares_list = []
    for share in shares:
        user_detail = ShareUserDetail(
            id=share.id,
            user_id=share.shared_by_user_id,
            username=share.shared_by.username if share.shared_by else None,
            full_name=(
                share.shared_by.full_name or 
                f"{share.shared_by.first_name or ''} {share.shared_by.last_name or ''}".strip()
                if share.shared_by else None
            ),
            avatar_url=share.shared_by.avatar_url if share.shared_by else None,
            platform=share.platform,
            share_link=share.share_link,
            created_at=share.created_at
        )
        shares_list.append(user_detail)
    
    # Récupérer les informations de l'auteur
    author_name = None
    author_username = None
    if contestant.user:
        author_name = contestant.user.full_name or f"{contestant.user.first_name or ''} {contestant.user.last_name or ''}".strip()
        author_username = contestant.user.username
    
    return ShareStats(
        contestant_id=contestant_id,
        total_shares=len(shares),
        shares_by_platform=shares_by_platform,
        # Informations du contestant
        contestant_title=contestant.title,
        contestant_description=contestant.description,
        contestant_registration_date=contestant.registration_date,
        # Informations de l'auteur
        author_id=contestant.user_id,
        author_name=author_name,
        author_username=author_username,
        author_country=contestant.user.country if contestant.user else None,
        author_city=contestant.user.city if contestant.user else None,
        author_avatar_url=contestant.user.avatar_url if contestant.user else None,
        # Liste des utilisateurs qui ont partagé
        shares=shares_list
    )


@router.get("/{contestant_id}/reactions/details", response_model=ReactionDetails)
def get_reaction_details(
    *,
    db: Session = Depends(deps.get_db),
    contestant_id: int
) -> ReactionDetails:
    """Récupérer les détails des réactions avec les noms des utilisateurs"""
    # Vérifier que le contestant existe
    contestant = crud_contestant.get(db, contestant_id)
    if not contestant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Submission not found"
        )
    
    # Récupérer toutes les réactions avec les utilisateurs
    reactions = db.query(ContestantReaction).join(User).filter(
        ContestantReaction.contestant_id == contestant_id
    ).all()
    
    # Grouper par type de réaction
    reactions_by_type: dict[str, List[ReactionUserDetail]] = {}
    for reaction in reactions:
        reaction_type = reaction.reaction_type
        if reaction_type not in reactions_by_type:
            reactions_by_type[reaction_type] = []
        
        reactions_by_type[reaction_type].append(
            ReactionUserDetail(
                user_id=reaction.user.id,
                username=reaction.user.username,
                full_name=reaction.user.full_name,
                avatar_url=reaction.user.avatar_url,
                reaction_type=reaction_type
            )
        )
    
    return ReactionDetails(
        contestant_id=contestant_id,
        reactions_by_type=reactions_by_type
    )


@router.get("/{contestant_id}/votes/details", response_model=VoteDetails)
def get_vote_details(
    *,
    db: Session = Depends(deps.get_db),
    contestant_id: int
) -> VoteDetails:
    """Récupérer les détails des votes avec les noms des utilisateurs"""
    # Vérifier que le contestant existe
    contestant = crud_contestant.get(db, contestant_id)
    if not contestant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Submission not found"
        )
    
    # Récupérer tous les votes avec les utilisateurs depuis ContestantVoting
    votes = db.query(ContestantVoting).join(User, ContestantVoting.user_id == User.id).filter(
        ContestantVoting.contestant_id == contestant_id
    ).order_by(ContestantVoting.vote_date.desc()).all()
    
    voters = [
        VoteUserDetail(
            id=vote.id,
            user_id=vote.user.id,
            username=vote.user.username,
            full_name=vote.user.full_name,
            avatar_url=vote.user.avatar_url,
            points=1,  # Chaque vote vaut 1 point dans le nouveau système
            vote_date=vote.vote_date,
            contest_id=vote.contest_id,
            season_id=vote.season_id
        )
        for vote in votes
    ]
    
    return VoteDetails(
        contestant_id=contestant_id,
        voters=voters
    )


@router.get("/{contestant_id}/favorites/details", response_model=FavoriteDetails)
def get_favorite_details(
    *,
    db: Session = Depends(deps.get_db),
    contestant_id: int
) -> FavoriteDetails:
    """Récupérer les détails des favoris avec les noms des utilisateurs"""
    # Vérifier que le contestant existe
    contestant = crud_contestant.get(db, contestant_id)
    if not contestant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Submission not found"
        )
    
    # Récupérer tous les favoris avec les utilisateurs
    favorites = db.query(MyFavorites).join(User, MyFavorites.user_id == User.id).filter(
        MyFavorites.contestant_id == contestant_id
    ).order_by(MyFavorites.added_date.desc()).all()
    
    users = [
        FavoriteUserDetail(
            user_id=favorite.user.id,
            username=favorite.user.username,
            full_name=favorite.user.full_name,
            avatar_url=favorite.user.avatar_url,
            position=favorite.position,
            added_date=favorite.added_date
        )
        for favorite in favorites
    ]
    
    return FavoriteDetails(
        contestant_id=contestant_id,
        users=users
    )


@router.post("/{contestant_id}/report", response_model=ReportResponse, status_code=status.HTTP_201_CREATED)
def report_contestant(
    *,
    db: Session = Depends(deps.get_db),
    contestant_id: int,
    report_data: ContestantReportCreate,
    current_user: User = Depends(deps.get_current_active_user),
    background_tasks: BackgroundTasks
) -> ReportResponse:
    """
    Signaler un contestant.
    Enregistre le signalement et envoie une notification à l'admin.
    """
    from fastapi import BackgroundTasks
    from app.services.email import email_service
    from app.crud import user as crud_user
    
    # Vérifier que le contestant existe
    contestant = crud_contestant.get(db, contestant_id)
    if not contestant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contestant not found"
        )
    
    # Vérifier que le contest existe
    contest = db.query(Contest).filter(Contest.id == report_data.contest_id).first()
    if not contest:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contest not found"
        )
    
    # Vérifier que le contestant appartient bien au contest
    # (vérification basique, peut être améliorée selon votre logique)
    
    # Vérifier que l'utilisateur ne signale pas son propre contestant
    if contestant.user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot report your own contestant"
        )
    
    # Vérifier qu'il n'y a pas déjà un signalement en attente du même utilisateur pour ce contestant
    from app.models.comment import Report as ReportModel
    existing_report = db.query(ReportModel).filter(
        ReportModel.reporter_id == current_user.id,
        ReportModel.contestant_id == contestant_id,
        ReportModel.status == "pending"
    ).first()
    
    if existing_report:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You have already reported this contestant. Please wait for admin review."
        )
    
    # Créer le signalement
    try:
        new_report = report.create_contestant_report(
            db=db,
            obj_in=report_data,
            reporter_id=current_user.id
        )
        
        # Récupérer l'auteur du contestant
        contestant_author = crud_user.get(db, contestant.user_id)
        author_name = contestant_author.full_name if contestant_author else "Unknown"
        
        # Envoyer une notification email à l'admin en arrière-plan
        # Récupérer tous les admins
        admin_users = db.query(User).filter(User.is_admin == True, User.is_active == True).all()
        
        if admin_users:
            from app.services.email_templates import get_contestant_report_email
            from app.core.config import settings
            
            for admin in admin_users:
                admin_lang = getattr(admin, 'preferred_language', 'en') or 'en'
                
                # Générer l'email
                subject, html_content, text_content = get_contestant_report_email(
                    lang=admin_lang,
                    contestant_title=contestant.title or "Untitled",
                    contestant_author_name=author_name,
                    contest_name=contest.name,
                    reporter_name=current_user.full_name or current_user.username,
                    reason=report_data.reason,
                    description=report_data.description,
                    report_id=new_report.id,
                    admin_url=f"{settings.FRONTEND_URL}/admin/reports/{new_report.id}"
                )
                
                background_tasks.add_task(
                    email_service.send_email,
                    to_email=admin.email,
                    subject=subject,
                    html_content=html_content,
                    text_content=text_content
                )
        
        # Construire la réponse
        return ReportResponse(
            id=new_report.id,
            reporter_id=new_report.reporter_id,
            contestant_id=new_report.contestant_id,
            contest_id=new_report.contest_id,
            reason=new_report.reason,
            description=new_report.description,
            status=new_report.status,
            created_at=new_report.created_at,
            updated_at=new_report.updated_at,
            contestant_title=contestant.title,
            contestant_author_name=author_name,
            contest_name=contest.name
        )
        
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating report: {str(e)}"
    )
