"""
GraphQL Schema and Resolvers for MyHigh5 Platform
"""

import strawberry
from typing import List, Optional
from strawberry.fastapi import GraphQLRouter
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.graphql.types import (
    ContestType, RoundType, ContestantType, VoteType, 
    UserType, SeasonType, VotingTypeType
)
from app.db.session import SessionLocal
from app.models.contest import Contest, VotingType
from app.models.round import Round
from app.models.contests import Contestant, ContestantRanking
from app.models.user import User


def get_db():
    """Get database session"""
    db = SessionLocal()
    try:
        return db
    finally:
        pass  # Will be closed after use


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
    
    # Get votes count
    votes_count = getattr(contestant, 'votes_count', 0) or 0
    
    return ContestantType(
        id=contestant.id,
        user_id=contestant.user_id,
        round_id=getattr(contestant, 'round_id', None),
        title=contestant.title,
        description=contestant.description,
        image_url=getattr(contestant, 'image_url', None),
        votes_count=votes_count,
        rank=getattr(contestant, 'rank', None),
        author=author,
        votes=[]  # Will be loaded separately if needed
    )


def map_round_to_type(round_obj: Round, db: Session, include_contestants: bool = False, include_contest: bool = False, filter_by_contest_id: Optional[int] = None) -> RoundType:
    """Convert SQLAlchemy Round to GraphQL RoundType"""
    contestants = []
    
    # Build base query for contestants
    query = db.query(Contestant).filter(Contestant.round_id == round_obj.id)
    
    # Apply filter by contest if provided (using season_id as proxy for contest link)
    if filter_by_contest_id:
        query = query.filter(Contestant.season_id == filter_by_contest_id)
        
    if include_contestants:
        # Load contestants for this round (filtered)
        db_contestants = query.limit(50).all()
        contestants = [map_contestant_to_type(c, db) for c in db_contestants]
    
    # Count participants (filtered)
    participants_count = query.count()
    
    # Count votes (simplistic sum of votes_count on ContestantRanking or count of Vote)
    # Since Contestant model does NOT have votes_count, we need to join or sum from related tables.
    # Looking at models, ContestantRanking seems to store aggregated stats per stage.
    # But for a Round context, we might want to sum records generally or link via ContestantRanking.
    # Let's try to sum `ContestantRanking.total_votes` if it exists.
    
    from app.models.contests import ContestantRanking
    # Using ContestantRanking to get votes
    votes_count_query = db.query(func.sum(ContestantRanking.total_votes)).join(
        Contestant, Contestant.id == ContestantRanking.contestant_id
    ).filter(
        Contestant.round_id == round_obj.id
    )
    
    if filter_by_contest_id:
        votes_count_query = votes_count_query.filter(Contestant.season_id == filter_by_contest_id)
    
    votes_count_val = votes_count_query.scalar() or 0
    
    # Get top contestants (by ranking votes)
    # Optimization: Join Contestant with Ranking
    top_contestants_query = db.query(Contestant).join(
        ContestantRanking, Contestant.id == ContestantRanking.contestant_id
    ).filter(
        Contestant.round_id == round_obj.id
    )
    
    if filter_by_contest_id:
        top_contestants_query = top_contestants_query.filter(Contestant.season_id == filter_by_contest_id)
        
    top_contestants_query = top_contestants_query.order_by(ContestantRanking.total_votes.desc()).limit(3).all()
    
    # Need to manually attach votes_count to the contestant objects because it's not a field on Contestant
    top_contestants_list = []
    for c in top_contestants_query:
        # Fetch rankings sum for this contestant
        c_votes = db.query(func.sum(ContestantRanking.total_votes)).filter(ContestantRanking.contestant_id == c.id).scalar() or 0
        c_type = map_contestant_to_type(c, db)
        c_type.votes_count = c_votes
        top_contestants_list.append(c_type)

    contest = None
    if include_contest:
        # Load parent contest via relation N:N
        from app.models.round import round_contests
        # Get the first contest linked to this round (assuming primarily one parent for now or picking first)
        result = db.execute(
            round_contests.select().where(round_contests.c.round_id == round_obj.id)
        ).first()
        
        if result:
            contest_id = result.contest_id
            contest_obj = db.query(Contest).filter(Contest.id == contest_id).first()
            if contest_obj:
                # Avoid infinite recursion: don't include rounds when loading parent contest
                contest = map_contest_to_type(contest_obj, db, include_rounds=False)

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
        contestants=contestants,
        seasons=[],  # Will be loaded separately
        contest=contest
    )


def map_contest_to_type(contest: Contest, db: Session, include_rounds: bool = True) -> ContestType:
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
                rounds.append(map_round_to_type(round_obj, db, include_contestants=False, filter_by_contest_id=contest.id))
    
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
    
    return ContestType(
        id=contest.id,
        name=contest.name,
        description=contest.description,
        contest_type=contest.contest_type,
        cover_image_url=contest.image_url,
        is_active=contest.is_active,
        level=contest.level,
        entries_count=db.query(Contestant).filter(
            # Using season_id link (legacy) or round link. 
            # Ideally count distinct users or total active contestants linked to this contest
            # For now, simplistic count. Improve data model link later if needed.
            # Assuming contestants linked via round_contests is hard to join here without complex query.
            # Fallback to season_id as simpler proxy or 0 if heavy.
            Contestant.season_id == contest.id 
        ).count() if not hasattr(contest, 'participant_count') else contest.participant_count,
        total_votes=db.query(func.sum(ContestantRanking.total_votes)).join(
            Contestant, Contestant.id == ContestantRanking.contestant_id
        ).filter(
            Contestant.season_id == contest.id
        ).scalar() or 0,
        rounds=rounds,
        voting_type=voting_type
    )


@strawberry.type
class Query:
    """GraphQL Queries"""
    
    @strawberry.field
    def contests(
        self,
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
            return [map_contest_to_type(c, db) for c in contests]
        finally:
            db.close()
    
    @strawberry.field
    def contest(self, id: int) -> Optional[ContestType]:
        """Get single contest by ID with all nested data"""
        db = get_db()
        try:
            contest = db.query(Contest).filter(Contest.id == id).first()
            if not contest:
                return None
            return map_contest_to_type(contest, db)
        finally:
            db.close()
    
    @strawberry.field
    def rounds(
        self,
        contest_id: Optional[int] = None,
        skip: int = 0,
        limit: int = 20,
        is_active: bool = True,
        # Filtres indirects via Contest
        has_voting_type: Optional[bool] = None,
        contest_type: Optional[str] = None
    ) -> List[RoundType]:
        """
        Get rounds. Can be filtered directly or via parent contest attributes.
        Returns rounds with their parent contest loaded.
        """
        db = get_db()
        try:
            # Base query on Round
            query = db.query(Round)
            
            # Filter by active status directly on Round (if field exists) or assume implies parent contest active
            # Round doesn't have is_active usually, status is used. 
            # But let's assume we want rounds from active contests
            
            # Join with Contest via round_contests if contest filters are present
            from app.models.round import round_contests
            
            if contest_id or has_voting_type is not None or contest_type or is_active:
                query = query.join(round_contests, Round.id == round_contests.c.round_id)
                query = query.join(Contest, Contest.id == round_contests.c.contest_id)
                
                if contest_id:
                    query = query.filter(Contest.id == contest_id)
                
                if is_active:
                    query = query.filter(Contest.is_active == True)
                    
                if contest_type:
                    query = query.filter(Contest.contest_type == contest_type)
                    
                if has_voting_type is not None:
                    if has_voting_type:
                        query = query.filter(Contest.voting_type_id.isnot(None))
                    else:
                        query = query.filter(Contest.voting_type_id.is_(None))
            
            rounds = query.offset(skip).limit(limit).all()
            
            # Always include contest parent for the new UI logic
            return [map_round_to_type(r, db, include_contestants=False, include_contest=True) for r in rounds]
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


# Create schema
schema = strawberry.Schema(query=Query)

# Create GraphQL router for FastAPI
graphql_app = GraphQLRouter(schema)
