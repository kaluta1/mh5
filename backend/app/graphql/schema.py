"""
GraphQL Schema and Resolvers for MyHigh5 Platform
"""

import strawberry
from typing import List, Optional
from strawberry.fastapi import GraphQLRouter
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime
import os

from app.graphql.types import (
    ContestType, RoundType, ContestantType, VoteType, 
    UserType, SeasonType, VotingTypeType, ContestInRoundType,
    AccountTypeEnum, EntryStatusEnum, ChartOfAccountsType, JournalEntryType, JournalLineType
)
from app.db.session import SessionLocal
from app.models.contest import Contest, VotingType
from app.models.round import Round, round_contests
from app.models.contests import Contestant, ContestantRanking, ContestSeasonLink, ContestSeason, SeasonLevel
from app.models.user import User
from app.models.accounting import ChartOfAccounts, JournalEntry, JournalLine, AccountType
from app.api import deps # To get user logic if needed, or just types


def get_db():
    """Get database session - MUST be closed after use"""
    db = SessionLocal()
    return db


def map_user_to_type(user: User) -> UserType:
    """Convert SQLAlchemy User to GraphQL UserType"""
    return UserType(
        id=user.id,
        username=user.username,
        full_name=user.full_name,
        avatar_url=user.avatar_url,
        country=getattr(user, 'country', None),
        city=getattr(user, 'city', None)
    )


def map_contestant_to_type(contestant: Contestant, db: Session) -> ContestantType:
    """Convert SQLAlchemy Contestant to GraphQL ContestantType"""
    author = None
    if contestant.user_id:
        user = db.query(User).filter(User.id == contestant.user_id).first()
        if user:
            author = map_user_to_type(user)
    
    # Get votes count from dynamic attribute or calculate
    votes_count = getattr(contestant, 'votes_count', 0)
    
    # If not present, try to fetch from ranking (sum of stages)
    if votes_count == 0:
        votes_count = db.query(func.sum(ContestantRanking.total_votes)).filter(
            ContestantRanking.contestant_id == contestant.id
        ).scalar() or 0
    
    return ContestantType(
        id=contestant.id,
        user_id=contestant.user_id,
        round_id=getattr(contestant, 'round_id', None),
        title=contestant.title,
        description=contestant.description,
        image_url=getattr(contestant, 'image_url', None),
        image_media_ids=getattr(contestant, 'image_media_ids', None),
        video_media_ids=getattr(contestant, 'video_media_ids', None),
        nominator_city=getattr(contestant, 'nominator_city', None),
        nominator_country=getattr(contestant, 'nominator_country', None),
        votes_count=votes_count,
        rank=getattr(contestant, 'rank', None),
        author=author,
        votes=[]  # Will be loaded separately if needed
    )


def map_contest_in_round_to_type(contest: Contest, round_id: int, db: Session, current_user: Optional[User] = None, filter_country: Optional[str] = None, filter_region: Optional[str] = None, filter_continent: Optional[str] = None, search_term: Optional[str] = None) -> ContestInRoundType:
    """Convert Contest to ContestInRoundType with context-specific stats"""
    
    # Check if contest matches search term (if provided)
    # If not matching, we still return it but maybe with 0 count? 
    # Or should searching filter out the contest entirely?
    # Usually search filters the LIST of contests. 
    # But here we are mapping A SPECIFIC contest found via Round.
    # The filtering of the contest LIST should happen BEFORE calling this if possible.
    # However, rounds -> contests is a list.
    # If we filter here, we can't "not return" efficiently without changing return type or handling in caller.
    # Caller (map_round_to_type) appends the result.
    # So we should probably return None if it doesn't match search, and handle that in caller.
    # BUT wait, the loop in map_round_to_type iterates over linked_contests.
    # We should filter linked_contests THERE.
    
    # So search_term here might be for filtering PARTICIPANTS? Use case: "Search for a contestant in a contest".
    # User said: "recherche. Par defaut, on retourne les données en fonction des information de l'utilisateur connectés".
    # "recherche" usually implies finding a contest or a participant.
    # Given the context "tri par pays... recherche", it's likely filtering the VIEW of the data.
    
    # Logic:
    # If search_term is for FILTERING CONTESTS, it should be applied in map_round_to_type.
    # If search_term is for FILTERING PARTICIPANTS, it applies here.
    # Let's assume search_term filters contests (Title/Desc).
    
    # RE-READING USER REQUEST: "On va revoir le trie par pays et ou ville , recherche."
    # AND "Par defaut, on retourne les données en fonction des information de l'utilisateur connectés"
    # This implies the stats (counts) should reflect the filter.
    
    # Let's support geo filters here for the counts.
    
    # Determine valid Season IDs for this contest
    linked_seasons_subquery = db.query(ContestSeasonLink.season_id).filter(
        ContestSeasonLink.contest_id == contest.id
    )
    
    # Logic to determine season level similar to REST API
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
    
    # Fallback to contest level
    if not season_level:
        season_level = contest.level.lower() if contest.level else None
        
    # FIXED: Query participants DIRECTLY from database using comprehensive OR query
    from app.models.round import Round, round_contests as rc_table
    from sqlalchemy import or_
    
    # Find ALL possible round IDs linked to this contest
    round_ids_via_table = db.query(rc_table.c.round_id).filter(
        rc_table.c.contest_id == contest.id
    ).all()
    round_ids_from_table = [r[0] for r in round_ids_via_table] if round_ids_via_table else []
    
    # Also check legacy round.contest_id
    legacy_rounds = db.query(Round.id).filter(Round.contest_id == contest.id).all()
    legacy_round_ids = [r[0] for r in legacy_rounds] if legacy_rounds else []
    
    # Combine all round IDs
    all_round_ids = list(set(round_ids_from_table + legacy_round_ids))
    
    # Build comprehensive OR query (handle all cases including NULL season_id)
    or_conditions = []
    
    # Condition 1: season_id matches contest.id
    or_conditions.append(Contestant.season_id == contest.id)
    
    # Condition 2: round_id matches any of the found rounds
    if all_round_ids:
        or_conditions.append(Contestant.round_id.in_(all_round_ids))
    
    # Condition 3: Handle NULL season_id but valid round_id (for migrated data)
    if all_round_ids:
        from sqlalchemy import and_
        or_conditions.append(
            and_(
                Contestant.season_id.is_(None),
                Contestant.round_id.in_(all_round_ids)
            )
        )
    
    if or_conditions:
        participants_query = db.query(Contestant).filter(
            Contestant.is_deleted == False,
            or_(*or_conditions)
        )
    else:
        participants_query = db.query(Contestant).filter(
            Contestant.is_deleted == False,
            Contestant.season_id == contest.id
        )

    # Apply Geo Filters
    # Priority: Explicit filters > User Location > Default (Global)
    
    applied_geo_filter = False
    
    if filter_country:
         participants_query = participants_query.filter(func.lower(Contestant.country) == func.lower(filter_country))
         applied_geo_filter = True
    elif filter_region:
         participants_query = participants_query.filter(func.lower(Contestant.region) == func.lower(filter_region))
         applied_geo_filter = True
    elif filter_continent:
         participants_query = participants_query.filter(func.lower(Contestant.continent) == func.lower(filter_continent))
         applied_geo_filter = True
         
    # If no explicit filter, use User location based on season level
    if not applied_geo_filter and current_user and season_level:
        season_level_lower = str(season_level).lower()
        if season_level_lower == "city":
             participants_query = participants_query.filter(
                Contestant.city == current_user.city,
                Contestant.country == current_user.country
            )
        elif season_level_lower == "country":
             participants_query = participants_query.filter(
                Contestant.country == current_user.country
            )
        elif season_level_lower in ("regional", "region"):
             participants_query = participants_query.filter(
                Contestant.region == current_user.region
            )
        elif season_level_lower == "continent":
             participants_query = participants_query.filter(
                Contestant.continent == current_user.continent
            )
    
    participants_count = participants_query.count()
    
    # Calculate total votes for this contest in this round (Apply same filters)
    # FIXED: Use the same comprehensive OR query as participants
    # Include the current round_id if provided
    if round_id and round_id not in all_round_ids:
        all_round_ids.append(round_id)
    
    or_conditions_votes = []
    
    # Condition 1: season_id matches contest.id
    or_conditions_votes.append(Contestant.season_id == contest.id)
    
    # Condition 2: round_id matches any of the found rounds
    if all_round_ids:
        or_conditions_votes.append(Contestant.round_id.in_(all_round_ids))
    
    # Condition 3: Handle NULL season_id but valid round_id (for migrated data)
    if all_round_ids:
        or_conditions_votes.append(
            and_(
                Contestant.season_id.is_(None),
                Contestant.round_id.in_(all_round_ids)
            )
        )
    
    if or_conditions_votes:
        votes_query = db.query(func.sum(ContestantRanking.total_votes)).join(
            Contestant, Contestant.id == ContestantRanking.contestant_id
        ).filter(
            Contestant.is_deleted == False,
            or_(*or_conditions_votes)
        )
    else:
        votes_query = db.query(func.sum(ContestantRanking.total_votes)).join(
            Contestant, Contestant.id == ContestantRanking.contestant_id
        ).filter(
            Contestant.is_deleted == False,
            Contestant.season_id == contest.id
        )
    
    # Apply EXACT SAME filters to votes
    if filter_country:
         votes_query = votes_query.filter(func.lower(Contestant.country) == func.lower(filter_country))
    elif filter_region:
         votes_query = votes_query.filter(func.lower(Contestant.region) == func.lower(filter_region))
    elif filter_continent:
         votes_query = votes_query.filter(func.lower(Contestant.continent) == func.lower(filter_continent))
    elif current_user and season_level: # Only if no explicit filter
        season_level_lower = str(season_level).lower()
        if season_level_lower == "city":
             votes_query = votes_query.filter(
                Contestant.city == current_user.city,
                Contestant.country == current_user.country
            )
        elif season_level_lower == "country":
             votes_query = votes_query.filter(
                Contestant.country == current_user.country
            )
        elif season_level_lower in ("regional", "region"):
             votes_query = votes_query.filter(
                Contestant.region == current_user.region
            )
        elif season_level_lower == "continent":
             votes_query = votes_query.filter(
                Contestant.continent == current_user.continent
            )

    votes_count = votes_query.scalar() or 0
    
    # Get participants list (Top 100)
    db_participants = participants_query.limit(100).all()
    participants_list = [map_contestant_to_type(p, db) for p in db_participants]

    return ContestInRoundType(
        id=contest.id,
        name=contest.name,
        description=contest.description,
        contest_type=contest.contest_type,
        cover_image_url=contest.image_url,
        level=os.getenv("DEBUG_LEVEL_OVERRIDE", contest.level), # Debug trick if needed, otherwise just contest.level
        participants_count=participants_count,
        votes_count=votes_count, 
        participants=participants_list
    )


def map_round_to_type(
    round_obj: Round, 
    db: Session, 
    include_contestants: bool = False, 
    include_contest: bool = False, 
    filter_by_contest_id: Optional[int] = None, 
    current_user: Optional[User] = None, 
    filter_country: Optional[str] = None, 
    filter_region: Optional[str] = None, 
    filter_continent: Optional[str] = None, 
    search_term: Optional[str] = None,
    has_voting_type: Optional[bool] = None  # Added argument
) -> RoundType:
    """Convert SQLAlchemy Round to GraphQL RoundType"""
    # 0. Initialize lists
    contestants = []

    # 1. Fetch Contests in this Round
    contests_in_round = []
    
    # FIXED: Query contests DIRECTLY from database - check both round_contests table AND legacy round.contest_id
    from sqlalchemy import or_
    
    # Method 1: Via round_contests association table (N:N)
    contests_via_table = db.query(Contest).join(
        round_contests, Contest.id == round_contests.c.contest_id
    ).filter(
        round_contests.c.round_id == round_obj.id
    ).all()
    
    # Method 2: Via legacy round.contest_id (1:N) - if round has direct contest_id
    contests_via_legacy = []
    if round_obj.contest_id:
        legacy_contest = db.query(Contest).filter(Contest.id == round_obj.contest_id).first()
        if legacy_contest:
            contests_via_legacy = [legacy_contest]
    
    # Combine and deduplicate
    all_contests_dict = {}
    for c in contests_via_table:
        all_contests_dict[c.id] = c
    for c in contests_via_legacy:
        if c.id not in all_contests_dict:
            all_contests_dict[c.id] = c
    
    linked_contests = list(all_contests_dict.values())
    
    # Apply filters to the combined list
    if has_voting_type is not None:
        if has_voting_type:
            linked_contests = [c for c in linked_contests if c.voting_type_id is not None]
        else:
            linked_contests = [c for c in linked_contests if c.voting_type_id is None]
        
    # Filter linked contests by search term (Name or Description)
    if search_term:
        term = search_term.lower()
        linked_contests = [c for c in linked_contests if (
            (c.name and term in c.name.lower()) or
            (c.description and term in c.description.lower()) or
            (c.contest_type and term in c.contest_type.lower())
        )]
    
    for contest in linked_contests:
        contests_in_round.append(map_contest_in_round_to_type(
            contest, 
            round_obj.id, 
            db, 
            current_user=current_user,
            filter_country=filter_country,
            filter_region=filter_region,
            filter_continent=filter_continent,
            search_term=search_term # Passed down if needed for further filtering context
        ))
    
    # 2. Fetch all contestants if requested (Flat list)
    # Apply filter by contest if provided
    contestants_query = db.query(Contestant).filter(Contestant.round_id == round_obj.id)
    
    if filter_by_contest_id:
        # Filter by season_id (legacy/current link)
        # Also check linked seasons
        linked_seasons_subquery = db.query(ContestSeasonLink.season_id).filter(
            ContestSeasonLink.contest_id == filter_by_contest_id
        )
        contestants_query = contestants_query.filter(
            (Contestant.season_id == filter_by_contest_id) | (Contestant.season_id.in_(linked_seasons_subquery))
        )

    if include_contestants:
        db_contestants = contestants_query.limit(100).all()
        contestants = [map_contestant_to_type(c, db) for c in db_contestants]
        
    participants_count = contestants_query.count()

    # 3. Top Contestants (Global for Round or Filtered)
    from app.models.contests import ContestantRanking
    top_contestants_query = db.query(Contestant).join(
        ContestantRanking, Contestant.id == ContestantRanking.contestant_id
    ).filter(
        Contestant.round_id == round_obj.id
    )
    
    if filter_by_contest_id:
         # Apply same filter logic
        linked_seasons_subquery_2 = db.query(ContestSeasonLink.season_id).filter(
            ContestSeasonLink.contest_id == filter_by_contest_id
        )
        top_contestants_query = top_contestants_query.filter(
            (Contestant.season_id == filter_by_contest_id) | (Contestant.season_id.in_(linked_seasons_subquery_2))
        )
        
    top_contestants_query = top_contestants_query.order_by(ContestantRanking.total_votes.desc()).limit(3).all()
    
    top_contestants_list = [map_contestant_to_type(c, db) for c in top_contestants_query]
    
    # Stats 
    
    votes_count_query = db.query(func.sum(ContestantRanking.total_votes)).join(
        Contestant, Contestant.id == ContestantRanking.contestant_id
    ).filter(
        Contestant.round_id == round_obj.id
    )
    
    if filter_by_contest_id:
         # Apply same filter logic
        linked_seasons_subquery_3 = db.query(ContestSeasonLink.season_id).filter(
            ContestSeasonLink.contest_id == filter_by_contest_id
        )
        votes_count_query = votes_count_query.filter(
            (Contestant.season_id == filter_by_contest_id) | (Contestant.season_id.in_(linked_seasons_subquery_3))
        )
        
    votes_count_val = votes_count_query.scalar() or 0

    return RoundType(
        id=round_obj.id,
        name=round_obj.name,
        status=round_obj.status.value if round_obj.status else "upcoming",
        is_submission_open=round_obj.is_submission_open,
        is_voting_open=round_obj.is_voting_open,
        current_season_level=round_obj.current_season_level,
        submission_start_date=round_obj.submission_start_date,
        submission_end_date=round_obj.submission_end_date,
        voting_start_date=round_obj.voting_start_date,
        voting_end_date=round_obj.voting_end_date,
        participants_count=participants_count,
        votes_count=votes_count_val,
        top_contestants=top_contestants_list,
        seasons=[],
        contests=contests_in_round,
        contestants=contestants # Restored field
    )


def map_contest_to_type(contest: Contest, db: Session, include_rounds: bool = True, include_contestants: bool = False, current_user: Optional[User] = None) -> ContestType:
    """Convert SQLAlchemy Contest to GraphQL ContestType"""
    rounds = []
    if include_rounds:
        # Load rounds via the new N:N relationship
        from app.models.round import round_contests
        round_ids = db.execute(
            round_contests.select().where(round_contests.c.contest_id == contest.id)
        ).fetchall()
        
        for row in round_ids:
            round_obj = db.query(Round).filter(Round.id == row.round_id).first()
            if round_obj:
                # Pass current contest ID to map_round_to_type to filter participants count
                rounds.append(map_round_to_type(round_obj, db, include_contestants=False, filter_by_contest_id=contest.id, current_user=current_user))
    
    # Get voting type
    voting_type = None
    if contest.voting_type_id:
        vt = db.query(VotingType).filter(VotingType.id == contest.voting_type_id).first()
        if vt:
            voting_type = VotingTypeType(
                id=vt.id,
                name=vt.name,
                voting_level=vt.voting_level.value if vt.voting_level else "city",
                commission_source=vt.commission_source.value if vt.commission_source else None
            )

    contestants_list = []
    # If specifically requested for detail view (we assume if include_rounds is True, we might want contestants for the detail view too? 
    # Actually, let's keep it separate or use include_rounds as proxy if specific arg not added. 
    # But to be safe and performant, we only load them if we are in the single contest query context)
    # Since I cannot easily change the signature everywhere without checking callers, I will use a conservative approach:
    # Only load if we are in a context where we know we need them.
    # But simpler: The frontend will access `contestants` field.
    # In `ContestType`, `contestants` is a list.
    # If I populate it here, it will be sent.
    # I should add `include_contestants` argument to `map_contest_to_type`.
    
    # FIXED: Query contestants DIRECTLY from database using comprehensive OR query
    from app.models.round import Round, round_contests as rc_table
    from sqlalchemy import or_
    
    # Find ALL possible round IDs linked to this contest
    round_ids_via_table = db.query(rc_table.c.round_id).filter(
        rc_table.c.contest_id == contest.id
    ).all()
    round_ids_from_table = [r[0] for r in round_ids_via_table] if round_ids_via_table else []
    
    legacy_rounds = db.query(Round.id).filter(Round.contest_id == contest.id).all()
    legacy_round_ids = [r[0] for r in legacy_rounds] if legacy_rounds else []
    
    all_round_ids = list(set(round_ids_from_table + legacy_round_ids))
    
    # Build comprehensive OR conditions (handle all cases including NULL season_id)
    or_conditions = []
    
    # Condition 1: season_id matches contest.id
    or_conditions.append(Contestant.season_id == contest.id)
    
    # Condition 2: round_id matches any of the found rounds
    if all_round_ids:
        or_conditions.append(Contestant.round_id.in_(all_round_ids))
    
    # Condition 3: Handle NULL season_id but valid round_id (for migrated data)
    if all_round_ids:
        from sqlalchemy import and_
        or_conditions.append(
            and_(
                Contestant.season_id.is_(None),
                Contestant.round_id.in_(all_round_ids)
            )
        )
    
    # Base filter for all queries
    base_filter = or_(*or_conditions) if or_conditions else (Contestant.season_id == contest.id)
    
    # Logic to fetch contestants if requested
    if include_contestants:
        import logging
        logger = logging.getLogger(__name__)
        
        # DEBUG: Log what we're querying
        logger.info(f"[map_contest_to_type] Querying contestants for contest.id={contest.id}, all_round_ids={all_round_ids}")
        logger.info(f"[map_contest_to_type] OR conditions count: {len(or_conditions)}")
        
        # First, try the comprehensive query
        qs = db.query(Contestant).filter(
            Contestant.is_deleted == False,
            base_filter
        ).limit(100).all()
        
        logger.info(f"[map_contest_to_type] Found {len(qs)} contestants with comprehensive query")
        
        # If no results, try fallback queries
        if not qs:
            logger.warning(f"[map_contest_to_type] No contestants found. Trying fallback queries...")
            
            # Fallback 1: season_id only
            fallback1 = db.query(Contestant).filter(
                Contestant.is_deleted == False,
                Contestant.season_id == contest.id
            ).limit(100).all()
            logger.info(f"[map_contest_to_type] Fallback 1 (season_id={contest.id}): Found {len(fallback1)}")
            if fallback1:
                qs = fallback1
            
            # Fallback 2: round_id only
            if not qs and all_round_ids:
                fallback2 = db.query(Contestant).filter(
                    Contestant.is_deleted == False,
                    Contestant.round_id.in_(all_round_ids)
                ).limit(100).all()
                logger.info(f"[map_contest_to_type] Fallback 2 (round_ids={all_round_ids}): Found {len(fallback2)}")
                if fallback2:
                    qs = fallback2
            
            # Fallback 3: ANY non-deleted contestant (for debugging)
            if not qs:
                fallback3 = db.query(Contestant).filter(
                    Contestant.is_deleted == False
                ).limit(10).all()
                logger.warning(f"[map_contest_to_type] Fallback 3 (ANY): Found {len(fallback3)}. Sample IDs: {[c.id for c in fallback3]}")
                logger.warning(f"[map_contest_to_type] Sample contestants season_id/round_id: {[(c.id, c.season_id, c.round_id) for c in fallback3]}")
        
        contestants_list = [map_contestant_to_type(c, db) for c in qs]
        logger.info(f"[map_contest_to_type] Returning {len(contestants_list)} contestants")

    # Resolve Current User Participation
    user_participation = None
    if current_user:
        up = db.query(Contestant).filter(
            Contestant.is_deleted == False,
            base_filter,
            Contestant.user_id == current_user.id
        ).first()
        if up:
            user_participation = map_contestant_to_type(up, db)
    
    # FIXED: Calculate entries_count and total_votes using comprehensive query
    if hasattr(contest, 'participant_count') and contest.participant_count is not None:
        entries_count_val = contest.participant_count
    else:
        entries_count_val = db.query(Contestant).filter(
            Contestant.is_deleted == False,
            base_filter
        ).count()
    
    total_votes_val = db.query(func.sum(ContestantRanking.total_votes)).join(
        Contestant, Contestant.id == ContestantRanking.contestant_id
    ).filter(
        Contestant.is_deleted == False,
        base_filter
    ).scalar() or 0

    return ContestType(
        id=contest.id,
        name=contest.name,
        description=contest.description,
        contest_type=contest.contest_type,
        cover_image_url=contest.image_url,
        is_active=contest.is_active,
        level=contest.level,
        
        # Submission Status & Dates
        is_submission_open=contest.is_submission_open,
        submission_start_date=contest.submission_start_date,
        submission_end_date=contest.submission_end_date,
        
        # Verification Requirements
        requires_kyc=contest.requires_kyc,
        requires_visual_verification=contest.requires_visual_verification,
        requires_voice_verification=contest.requires_voice_verification,
        requires_brand_verification=contest.requires_brand_verification,
        requires_content_verification=contest.requires_content_verification,
        participant_type=contest.participant_type.value if hasattr(contest.participant_type, 'value') else str(contest.participant_type),
        
        # Media Requirements
        requires_video=contest.requires_video,
        max_videos=contest.max_videos,
        video_max_duration=contest.video_max_duration,
        video_max_size_mb=contest.video_max_size_mb,
        min_images=contest.min_images,
        max_images=contest.max_images,
        
        # Verification Media Limits
        verification_video_max_duration=contest.verification_video_max_duration,
        verification_max_size_mb=contest.verification_max_size_mb,

        entries_count=entries_count_val,
        total_votes=total_votes_val,
        rounds=rounds,
        voting_type=voting_type,
        contestants=contestants_list,
        current_user_participation=user_participation
    )


def map_chart_of_accounts_to_type(account: ChartOfAccounts) -> ChartOfAccountsType:
    return ChartOfAccountsType(
        id=account.id,
        account_code=account.account_code,
        account_name=account.account_name,
        account_type=AccountTypeEnum(account.account_type.value),
        parent_id=account.parent_id,
        description=account.description,
        is_active=account.is_active,
        total_liabilities=float(account.total_liabilities or 0),
        credit_balance=float(account.credit_balance or 0)
    )


def map_journal_line_to_type(line: JournalLine) -> JournalLineType:
    # Notice we don't pass DB here because we assume eager loading or simple relationship access
    return JournalLineType(
        id=line.id,
        account_id=line.account_id,
        debit_amount=float(line.debit_amount or 0),
        credit_amount=float(line.credit_amount or 0),
        description=line.description,
        account=map_chart_of_accounts_to_type(line.account) if line.account else None
    )


def map_journal_entry_to_type(entry: JournalEntry, db: Session) -> JournalEntryType:
    lines = [map_journal_line_to_type(line) for line in entry.lines]
    
    creator = None
    if entry.created_by:
         user = db.query(User).filter(User.id == entry.created_by).first()
         if user:
             creator = map_user_to_type(user)

    return JournalEntryType(
        id=entry.id,
        entry_number=entry.entry_number,
        entry_date=entry.entry_date,
        description=entry.description,
        threshold=float(entry.threshold) if entry.threshold else None,
        total_debit=float(entry.total_debit or 0),
        total_credit=float(entry.total_credit or 0),
        status=EntryStatusEnum(entry.status.value),
        created_at=entry.created_at,
        posted_at=entry.posted_at,
        lines=lines,
        created_by_user=creator
    )


@strawberry.type
class Query:
    """GraphQL Queries"""
    
    @strawberry.field
    def contests(
        self,
        info: strawberry.Info,
        skip: int = 0,
        limit: int = 10,
        contest_type: Optional[str] = None,
        has_voting_type: Optional[bool] = None,
        is_active: bool = True,
        round_id: Optional[int] = None
    ) -> List[ContestType]:
        """
        Get contests, optionally filtered by round_id.
        """
        db = get_db()
        try:
            # Get current user from context
            current_user = info.context.get("user")

            query = db.query(Contest).filter(Contest.is_active == is_active)
            
            # Filter by round_id
            if round_id:
                from app.models.round import round_contests
                query = query.join(round_contests, Contest.id == round_contests.c.contest_id)
                query = query.filter(round_contests.c.round_id == round_id)
            
            if contest_type:
                query = query.filter(Contest.contest_type == contest_type)
            
            if has_voting_type is not None:
                if has_voting_type:
                    query = query.filter(Contest.voting_type_id.isnot(None))
                else:
                    query = query.filter(Contest.voting_type_id.is_(None))
            
            contests = query.offset(skip).limit(limit).all()
            return [map_contest_to_type(c, db, current_user=current_user) for c in contests]
        finally:
            db.close()
    
    @strawberry.field
    def contest(self, info: strawberry.Info, id: int) -> Optional[ContestType]:
        """Get single contest by ID with all nested data"""
        db = get_db()
        try:
            # Get current user from context
            current_user = info.context.get("user")

            contest = db.query(Contest).filter(Contest.id == id).first()
            if not contest:
                return None
            # FIXED: Always include contestants for single contest query
            return map_contest_to_type(contest, db, include_rounds=True, include_contestants=True, current_user=current_user)
        finally:
            db.close()
    
    @strawberry.field
    def rounds(
        self,
        info: strawberry.Info,
        id: Optional[int] = None, # Added id filter
        contest_id: Optional[int] = None,
        skip: int = 0,
        limit: int = 20,
        is_active: bool = True,
        # Filtres indirects via Contest
        has_voting_type: Optional[bool] = None,
        contest_type: Optional[str] = None,
        # Nouveaux filtres explicites
        filter_country: Optional[str] = None,
        filter_region: Optional[str] = None,
        filter_continent: Optional[str] = None,
        search_term: Optional[str] = None
    ) -> List[RoundType]:
        """
        Get rounds. Can be filtered directly or via parent contest attributes.
        Returns rounds with their parent contest loaded.
        """
        db = get_db()
        try:
            from app.models.round import RoundStatus
            
            # Base query on Round
            query = db.query(Round).filter(Round.status != RoundStatus.CANCELLED)
            
            # Filter by active status directly on Round (if field exists) or assume implies parent contest active
            # Round doesn't have is_active usually, status is used. 
            # But let's assume we want rounds from active contests
            
            if id:
                query = query.filter(Round.id == id)
            
            # FIXED: Query rounds directly first, then filter by contest attributes if needed
            # This avoids complex joins that might filter out rounds incorrectly
            from app.models.round import round_contests
            
            # First, get all rounds (without joining contests to avoid filtering issues)
            rounds = query.offset(skip).limit(limit).all()
            
            # If we have filters that require contest data, filter rounds after fetching
            if contest_id or has_voting_type is not None or contest_type or is_active is True:
                # Get round IDs that match the contest filters via round_contests table
                contest_query = db.query(round_contests.c.round_id).distinct()
                contest_query = contest_query.join(Contest, Contest.id == round_contests.c.contest_id)
                
                # Also check legacy round.contest_id
                legacy_round_ids_query = db.query(Round.id).filter(Round.contest_id.isnot(None))
                if contest_id:
                    legacy_round_ids_query = legacy_round_ids_query.filter(Round.contest_id == contest_id)
                legacy_round_ids = [r[0] for r in legacy_round_ids_query.all()]
                
                if contest_id:
                    contest_query = contest_query.filter(Contest.id == contest_id)
                
                # Only filter by is_active when explicitly True
                if is_active is True:
                    contest_query = contest_query.filter(Contest.is_active == True)
                    
                if contest_type:
                    contest_query = contest_query.filter(Contest.contest_type == contest_type)
                    
                if has_voting_type is not None:
                    if has_voting_type:
                        contest_query = contest_query.filter(Contest.voting_type_id.isnot(None))
                    else:
                        contest_query = contest_query.filter(Contest.voting_type_id.is_(None))
                
                # Get round IDs that match filters
                filtered_round_ids = set([r[0] for r in contest_query.all()] + legacy_round_ids)
                
                # Filter rounds to only include those with matching contests
                if filtered_round_ids:
                    rounds = [r for r in rounds if r.id in filtered_round_ids]
                else:
                    # If no rounds match filters, return empty list
                    rounds = []
            
            # Get current user from context
            current_user = info.context.get("user")

            # Always include contest parent for the new UI logic
            return [map_round_to_type(
                r, 
                db, 
                include_contestants=False, 
                include_contest=True, 
                current_user=current_user,
                filter_country=filter_country,
                filter_region=filter_region,
                filter_continent=filter_continent,
                search_term=search_term,
                has_voting_type=has_voting_type # Added argument
            ) for r in rounds]
        finally:
            db.close()
    
    @strawberry.field
    def round(self, id: int) -> Optional[RoundType]:
        """Get single round with contestants"""
        db = get_db()
        try:
            round_obj = db.query(Round).filter(Round.id == id).first()
            if not round_obj:
                return None
            return map_round_to_type(round_obj, db, include_contestants=True)
        finally:
            db.close()


    @strawberry.field
    def chart_of_accounts(self) -> List[ChartOfAccountsType]:
        """Get flattened chart of accounts"""
        db = get_db()
        try:
             accounts = db.query(ChartOfAccounts).filter(ChartOfAccounts.is_active == True).order_by(ChartOfAccounts.account_code).all()
             return [map_chart_of_accounts_to_type(a) for a in accounts]
        finally:
             db.close()

    @strawberry.field
    def journal_entries(
        self, 
        skip: int = 0, 
        limit: int = 20,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        min_amount: Optional[float] = None
    ) -> List[JournalEntryType]:
        """Get journal entries with pagination and filters"""
        db = get_db()
        try:
             query = db.query(JournalEntry).order_by(JournalEntry.entry_date.desc())
             
             if start_date:
                 query = query.filter(JournalEntry.entry_date >= start_date)
             if end_date:
                 query = query.filter(JournalEntry.entry_date <= end_date)
             if min_amount:
                 query = query.filter(JournalEntry.total_debit >= min_amount)
                 
             entries = query.offset(skip).limit(limit).all()
             return [map_journal_entry_to_type(e, db) for e in entries]
        finally:
             db.close()


from fastapi import Depends, Request, Response
from app.api import deps

async def get_context(
    request: Request,
    response: Response,
    user: Optional[User] = Depends(deps.get_current_active_user_optional),
):
    return {
        "request": request,
        "response": response,
        "user": user,
    }

# Create schema
schema = strawberry.Schema(query=Query)

# Create GraphQL router for FastAPI
graphql_app = GraphQLRouter(schema, context_getter=get_context)
