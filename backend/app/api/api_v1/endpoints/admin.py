from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import IntegrityError
from psycopg2.errors import UniqueViolation
from app.db.base_class import Base
from app.api.deps import get_db, get_current_user
from app.models.user import User, Role
from app.models.contest import Contest, ContestEntry, SuggestedContest
from app.models.contests import ContestSeason, ContestStage, ContestStageLevel, VotingRestriction, Contestant, ContestSubmission, SeasonLevel, ContestantSeason, ContestSeasonLink
from app.models.media import Media
from app.models.comment import Comment, Report
from app.models.payment import Deposit, ProductType, DepositStatus
from app.models.transaction import UserTransaction, TransactionType, TransactionStatus
from app.models.clubs import FanClub, ClubMembership, ClubAdmin
from app.models.category import Category
from pydantic import BaseModel
from typing import List, Optional, Dict, Any, Dict, Any
from datetime import datetime, timedelta, date
from app.crud.crud_contest import calculate_season_dates

router = APIRouter()

# Pydantic models
class ContestCreateRequest(BaseModel):
    name: str
    description: Optional[str] = None
    contest_type: str
    season_id: Optional[int] = None  # ID de la saison à lier
    level: Optional[str] = None  # Déprécié, sera dérivé de la saison
    is_active: bool = True
    is_submission_open: bool = True
    is_voting_open: bool = False
    submission_start_date: Optional[str] = None  # Will be auto-generated if not provided
    submission_end_date: Optional[str] = None  # Will be auto-generated if not provided
    voting_start_date: Optional[str] = None  # Will be auto-generated if not provided
    voting_end_date: Optional[str] = None  # Will be auto-generated if not provided
    # Season dates
    city_season_start_date: Optional[str] = None
    city_season_end_date: Optional[str] = None
    country_season_start_date: Optional[str] = None
    country_season_end_date: Optional[str] = None
    regional_start_date: Optional[str] = None
    regional_end_date: Optional[str] = None
    continental_start_date: Optional[str] = None
    continental_end_date: Optional[str] = None
    global_start_date: Optional[str] = None
    global_end_date: Optional[str] = None
    image_url: Optional[str] = None
    voting_restriction: str = "none"
    voting_type_id: Optional[int] = None
    category_id: Optional[int] = None
    # Verification requirements
    requires_kyc: bool = False
    verification_type: str = "none"
    participant_type: str = "individual"
    requires_visual_verification: bool = False
    requires_voice_verification: bool = False
    requires_brand_verification: bool = False
    requires_content_verification: bool = False
    min_age: Optional[int] = None
    max_age: Optional[int] = None
    # Media requirements
    requires_video: bool = False
    max_videos: int = 1
    video_max_duration: int = 3000  # 50 minutes in seconds
    video_max_size_mb: int = 500
    min_images: int = 0
    max_images: int = 10
    # Verification media limits
    verification_video_max_duration: int = 30  # 30 seconds
    verification_max_size_mb: int = 50

    class Config:
        from_attributes = True

class ContestResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    contest_type: str
    level: str
    season_id: Optional[int] = None
    is_active: bool
    is_submission_open: bool
    is_voting_open: bool
    submission_start_date: datetime
    submission_end_date: datetime
    voting_start_date: datetime
    voting_end_date: datetime
    image_url: Optional[str]
    cover_image_url: Optional[str] = None
    voting_restriction: str
    voting_type_id: Optional[int] = None
    voting_type: Optional[Dict[str, Any]] = None
    category_id: Optional[int] = None
    category: Optional[Dict[str, Any]] = None
    participant_count: int
    approved_count: int
    pending_count: int
    created_at: datetime
    updated_at: datetime
    # Season dates
    city_season_start_date: Optional[date] = None
    city_season_end_date: Optional[date] = None
    country_season_start_date: Optional[date] = None
    country_season_end_date: Optional[date] = None
    regional_start_date: Optional[date] = None
    regional_end_date: Optional[date] = None
    continental_start_date: Optional[date] = None
    continental_end_date: Optional[date] = None
    global_start_date: Optional[date] = None
    global_end_date: Optional[date] = None
    # Verification requirements
    requires_kyc: bool = False
    verification_type: str = "none"
    participant_type: str = "individual"
    requires_visual_verification: bool = False
    requires_voice_verification: bool = False
    requires_brand_verification: bool = False
    requires_content_verification: bool = False
    min_age: Optional[int] = None
    max_age: Optional[int] = None
    # Media requirements
    requires_video: bool = False
    max_videos: int = 1
    video_max_duration: int = 3000
    video_max_size_mb: int = 500
    min_images: int = 0
    max_images: int = 10
    # Verification media limits
    verification_video_max_duration: int = 30
    verification_max_size_mb: int = 50

    class Config:
        from_attributes = True

# Helper function to check if user is admin
def check_admin(current_user: User) -> User:
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vous n'avez pas les permissions pour accéder à cette ressource"
        )
    return current_user

# Helper function to get contest statistics
def get_contest_stats(db: Session, contest_id: int):
    """
    Récupère les statistiques des participants pour un concours.
    Note: season_id dans la table contestants correspond à l'ID du contest
    Retourne : (total_count, approved_count, pending_count)
    """
    try:
        # Total des participants pour ce contest
        total = db.query(Contestant).filter(
            Contestant.season_id == contest_id
        ).count()
        
        # Participants approuvés (verification_status = 'verified')
        approved = db.query(Contestant).filter(
            Contestant.season_id == contest_id,
            Contestant.verification_status == 'verified'
        ).count()
        
        # Participants en attente (verification_status = 'pending')
        pending = db.query(Contestant).filter(
            Contestant.season_id == contest_id,
            Contestant.verification_status == 'pending'
        ).count()
        
        print(f"DEBUG: Contest {contest_id} - Total: {total}, Approved: {approved}, Pending: {pending}")
        return total, approved, pending
    except Exception as e:
        print(f"Error getting contest stats for contest {contest_id}: {str(e)}")
        return 0, 0, 0

# Helper function to auto-generate dates
def generate_contest_dates(submission_start_date: Optional[str] = None):
    """
    Génère automatiquement les dates du concours :
    - submission_start_date: date de création (aujourd'hui)
    - submission_end_date: 1 mois après le début
    - voting_start_date: 1 jour après la fin des submissions
    - voting_end_date: 1 mois après le début du vote
    """
    from datetime import date as date_class
    
    if submission_start_date:
        try:
            # Essayer de parser comme datetime d'abord
            dt = datetime.fromisoformat(submission_start_date)
            start = dt.date()
        except:
            try:
                # Essayer de parser comme date
                start = date_class.fromisoformat(submission_start_date)
            except:
                start = date_class.today()
    else:
        start = date_class.today()
    
    submission_end = start + timedelta(days=30)
    voting_start = submission_end + timedelta(days=1)
    voting_end = voting_start + timedelta(days=30)
    
    return start, submission_end, voting_start, voting_end


# Contests endpoints
@router.get("/contests", response_model=List[ContestResponse])
async def get_all_contests(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    level: Optional[str] = None,
    is_active: Optional[bool] = None,
    contest_type: Optional[str] = None
):
    """
    Récupère tous les concours (admin uniquement)
    """
    # Vérifier que l'utilisateur est admin
    if not current_user.is_admin:
        print(f"DEBUG: User {current_user.id} is not admin (is_admin={current_user.is_admin})")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vous n'avez pas les permissions pour accéder à cette ressource"
        )
    
    try:
        query = db.query(Contest).filter(Contest.is_deleted == False).options(
            joinedload(Contest.voting_type),
            joinedload(Contest.category)
        )
        
        if level:
            query = query.filter(Contest.level == level)
        if is_active is not None:
            query = query.filter(Contest.is_active == is_active)
        if contest_type:
            query = query.filter(Contest.contest_type == contest_type)
        
        contests = query.all()
        
        # Récupérer tous les season_id en une seule requête pour optimiser
        contest_ids = [c.id for c in contests]
        season_links = {}
        if contest_ids:
            links = db.query(ContestSeasonLink).filter(
                ContestSeasonLink.contest_id.in_(contest_ids),
                ContestSeasonLink.is_active == True
            ).all()
            for link in links:
                season_links[link.contest_id] = link.season_id
        
        # Ajouter les statistiques pour chaque concours
        result = []
        for contest in contests:
            total, approved, pending = get_contest_stats(db, contest.id)
            contest_dict = {
                'id': contest.id,
                'name': contest.name,
                'description': contest.description,
                'contest_type': contest.contest_type,
                'level': contest.level,
                'season_id': season_links.get(contest.id),
                'is_active': contest.is_active,
                'is_submission_open': contest.is_submission_open,
                'is_voting_open': contest.is_voting_open,
                'submission_start_date': contest.submission_start_date,
                'submission_end_date': contest.submission_end_date,
                'voting_start_date': contest.voting_start_date,
                'voting_end_date': contest.voting_end_date,
                'image_url': contest.image_url,
                'cover_image_url': contest.cover_image_url,
                'voting_restriction': contest.voting_restriction.value if contest.voting_restriction else 'none',
                'voting_type_id': contest.voting_type_id,
                'voting_type': {
                    "id": contest.voting_type.id,
                    "name": contest.voting_type.name,
                    "voting_level": contest.voting_type.voting_level.value if hasattr(contest.voting_type.voting_level, 'value') else str(contest.voting_type.voting_level),
                    "commission_source": contest.voting_type.commission_source.value if hasattr(contest.voting_type.commission_source, 'value') else str(contest.voting_type.commission_source),
                } if contest.voting_type else None,
                'category_id': contest.category_id,
                'category': {
                    "id": contest.category.id,
                    "name": contest.category.name,
                    "slug": contest.category.slug,
                    "description": contest.category.description,
                    "is_active": contest.category.is_active
                } if contest.category else None,
                'participant_count': total,
                'approved_count': approved,
                'pending_count': pending,
                'created_at': contest.created_at,
                'updated_at': contest.updated_at,
                # Season dates
                'city_season_start_date': contest.city_season_start_date,
                'city_season_end_date': contest.city_season_end_date,
                'country_season_start_date': contest.country_season_start_date,
                'country_season_end_date': contest.country_season_end_date,
                'regional_start_date': contest.regional_start_date,
                'regional_end_date': contest.regional_end_date,
                'continental_start_date': contest.continental_start_date,
                'continental_end_date': contest.continental_end_date,
                'global_start_date': contest.global_start_date,
                'global_end_date': contest.global_end_date,
                # Verification fields
                'requires_kyc': contest.requires_kyc,
                'verification_type': contest.verification_type.value if contest.verification_type else 'none',
                'participant_type': contest.participant_type.value if contest.participant_type else 'individual',
                'requires_visual_verification': contest.requires_visual_verification,
                'requires_voice_verification': contest.requires_voice_verification,
                'requires_brand_verification': contest.requires_brand_verification,
                'requires_content_verification': contest.requires_content_verification,
                'min_age': contest.min_age,
                'max_age': contest.max_age,
                # Media requirements
                'requires_video': getattr(contest, 'requires_video', False),
                'max_videos': getattr(contest, 'max_videos', 1),
                'video_max_duration': getattr(contest, 'video_max_duration', 3000),
                'video_max_size_mb': getattr(contest, 'video_max_size_mb', 500),
                'min_images': getattr(contest, 'min_images', 0),
                'max_images': getattr(contest, 'max_images', 10),
                'verification_video_max_duration': getattr(contest, 'verification_video_max_duration', 30),
                'verification_max_size_mb': getattr(contest, 'verification_max_size_mb', 50)
            }
            result.append(contest_dict)
        
        print(f"DEBUG: Found {len(contests)} contests for user {current_user.id}")
        return result
    except HTTPException:
        raise
    except Exception as e:
        print(f"ERROR in get_all_contests: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la récupération des concours: {str(e)}"
        )

@router.get("/contests/{contest_id}", response_model=ContestResponse)
async def get_contest(
    contest_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Récupère un concours spécifique (admin uniquement)
    """
    check_admin(current_user)
    
    contest = db.query(Contest).filter(Contest.id == contest_id, Contest.is_deleted == False).options(
        joinedload(Contest.voting_type),
        joinedload(Contest.category)
    ).first()
    if not contest:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Concours non trouvé"
        )
    
    # Get contest statistics
    total, approved, pending = get_contest_stats(db, contest.id)
    
    # Récupérer le season_id via ContestSeasonLink
    season_link = db.query(ContestSeasonLink).filter(
        ContestSeasonLink.contest_id == contest_id,
        ContestSeasonLink.is_active == True
    ).first()
    season_id = season_link.season_id if season_link else None
    
    # Return contest with statistics
    return {
        'id': contest.id,
        'name': contest.name,
        'description': contest.description,
        'contest_type': contest.contest_type,
        'level': contest.level,
        'season_id': season_id,
        'is_active': contest.is_active,
        'is_submission_open': contest.is_submission_open,
        'is_voting_open': contest.is_voting_open,
        'submission_start_date': contest.submission_start_date,
        'submission_end_date': contest.submission_end_date,
        'voting_start_date': contest.voting_start_date,
        'voting_end_date': contest.voting_end_date,
        'image_url': contest.image_url,
        'cover_image_url': contest.cover_image_url,
        'voting_restriction': contest.voting_restriction.value if contest.voting_restriction else 'none',
        'voting_type_id': contest.voting_type_id,
        'voting_type': {
            "id": contest.voting_type.id,
            "name": contest.voting_type.name,
            "voting_level": contest.voting_type.voting_level.value if hasattr(contest.voting_type.voting_level, 'value') else str(contest.voting_type.voting_level),
            "commission_source": contest.voting_type.commission_source.value if hasattr(contest.voting_type.commission_source, 'value') else str(contest.voting_type.commission_source),
        } if contest.voting_type else None,
        'category_id': contest.category_id,
        'category': {
            "id": contest.category.id,
            "name": contest.category.name,
            "slug": contest.category.slug,
            "description": contest.category.description,
            "is_active": contest.category.is_active
        } if contest.category else None,
        'participant_count': total,
        'approved_count': approved,
        'pending_count': pending,
        'created_at': contest.created_at,
        'updated_at': contest.updated_at,
        # Verification fields
        'requires_kyc': contest.requires_kyc,
        'verification_type': contest.verification_type.value if contest.verification_type else 'none',
        'participant_type': contest.participant_type.value if contest.participant_type else 'individual',
        'requires_visual_verification': contest.requires_visual_verification,
        'requires_voice_verification': contest.requires_voice_verification,
        'requires_brand_verification': contest.requires_brand_verification,
        'requires_content_verification': contest.requires_content_verification,
        'min_age': contest.min_age,
        'max_age': contest.max_age,
        # Season dates
        'city_season_start_date': contest.city_season_start_date,
        'city_season_end_date': contest.city_season_end_date,
        'country_season_start_date': contest.country_season_start_date,
        'country_season_end_date': contest.country_season_end_date,
        'regional_start_date': contest.regional_start_date,
        'regional_end_date': contest.regional_end_date,
        'continental_start_date': contest.continental_start_date,
        'continental_end_date': contest.continental_end_date,
        'global_start_date': contest.global_start_date,
        'global_end_date': contest.global_end_date,
        # Media requirements
        'requires_video': getattr(contest, 'requires_video', False),
        'max_videos': getattr(contest, 'max_videos', 1),
        'video_max_duration': getattr(contest, 'video_max_duration', 3000),
        'video_max_size_mb': getattr(contest, 'video_max_size_mb', 500),
        'min_images': getattr(contest, 'min_images', 0),
        'max_images': getattr(contest, 'max_images', 10),
        'verification_video_max_duration': getattr(contest, 'verification_video_max_duration', 30),
        'verification_max_size_mb': getattr(contest, 'verification_max_size_mb', 50)
    }

@router.get("/contestants")
async def get_all_contestants(
    status_filter: Optional[str] = Query(None, alias="status_filter"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Récupère tous les candidats (admin uniquement)
    """
    check_admin(current_user)
    
    import json
    
    # Query all contestants
    # Ne pas charger les commentaires pour éviter les problèmes de performance
    query = db.query(Contestant).options(
        joinedload(Contestant.user)
    ).filter(Contestant.is_deleted == False)
    
    # Apply status filter if provided
    if status_filter and status_filter != 'all':
        query = query.filter(Contestant.verification_status == status_filter)
    
    contestants = query.all()
    
    # Get all submissions and comments in bulk to avoid N+1 queries
    from sqlalchemy import func
    
    contestant_ids = [c.id for c in contestants]
    
    # Get submission counts for all contestants
    submission_counts = {}
    if contestant_ids:
        submissions_data = db.query(
            ContestSubmission.contestant_id,
            func.count(ContestSubmission.id).label('count')
        ).filter(ContestSubmission.contestant_id.in_(contestant_ids)).group_by(
            ContestSubmission.contestant_id
        ).all()
        
        for contestant_id, count in submissions_data:
            submission_counts[contestant_id] = count
    
    # Get comment counts for all contestants (optimisé)
    comment_counts = {}
    if contestant_ids:
        comments_data = db.query(
            Comment.contestant_id,
            func.count(Comment.id).label('count')
        ).filter(
            Comment.contestant_id.in_(contestant_ids),
            Comment.is_deleted == False
        ).group_by(
            Comment.contestant_id
        ).all()
        
        for contestant_id, count in comments_data:
            comment_counts[contestant_id] = count
    
    # Return contestants with their data
    result = []
    for c in contestants:
        # Count images and videos from JSON arrays
        images_count = 0
        videos_count = 0
        
        if c.image_media_ids:
            try:
                image_ids = json.loads(c.image_media_ids)
                images_count = len(image_ids) if isinstance(image_ids, list) else 0
            except:
                images_count = 0
        
        if c.video_media_ids:
            try:
                video_ids = json.loads(c.video_media_ids)
                videos_count = len(video_ids) if isinstance(video_ids, list) else 0
            except:
                videos_count = 0
        
        # Get votes count from pre-fetched data
        votes_count = submission_counts.get(c.id, 0)
        
        # Get comment count from pre-fetched data
        comments_count = comment_counts.get(c.id, 0)
        
        # Get media items from image_media_ids and video_media_ids
        # These contain URLs, not IDs
        media_items = []
        
        # Process image media URLs
        if c.image_media_ids:
            try:
                image_urls = json.loads(c.image_media_ids)
                if isinstance(image_urls, list):
                    for idx, url in enumerate(image_urls):
                        if url:  # Only add if URL is not empty
                            media_items.append({
                                'id': f"image_{c.id}_{idx}",
                                'type': 'image',
                                'url': url,
                            })
            except:
                pass
        
        # Process video media URLs
        if c.video_media_ids:
            try:
                video_urls = json.loads(c.video_media_ids)
                if isinstance(video_urls, list):
                    for idx, url in enumerate(video_urls):
                        if url:  # Only add if URL is not empty
                            media_items.append({
                                'id': f"video_{c.id}_{idx}",
                                'type': 'video',
                                'url': url,
                            })
            except:
                pass
        
        # Ne pas charger tous les commentaires pour éviter les problèmes de performance
        # Si nécessaire, les commentaires peuvent être récupérés via un endpoint séparé
        
        result.append({
            'id': c.id,
            'user_id': c.user_id,
            'season_id': c.season_id,
            'title': c.title,
            'description': c.description,
            'registration_date': c.created_at,
            'verification_status': c.verification_status,
            'is_active': c.is_active,
            'is_qualified': c.is_qualified,
            'author_name': c.user.full_name if c.user else None,
            'author_avatar_url': c.user.avatar_url if c.user else None,
            'votes_count': votes_count,
            'comments_count': comments_count,
            'images_count': images_count,
            'videos_count': videos_count,
            'media_items': media_items,
        })
    
    return result

@router.get("/contests/{contest_id}/contestants")
async def get_contest_contestants(
    contest_id: int,
    status_filter: Optional[str] = Query(None, alias="status_filter"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Récupère les candidats d'un concours spécifique (admin uniquement)
    """
    check_admin(current_user)
    
    import json
    
    # Verify contest exists and is not deleted
    contest = db.query(Contest).filter(Contest.id == contest_id, Contest.is_deleted == False).first()
    if not contest:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Concours non trouvé"
        )
    
    # Query contestants for this contest (season_id = contest_id)
    # Ne pas charger les commentaires pour éviter les problèmes de performance
    query = db.query(Contestant).options(
        joinedload(Contestant.user)
    ).filter(Contestant.season_id == contest_id, Contestant.is_deleted == False)
    
    # Apply status filter if provided
    if status_filter and status_filter != 'all':
        query = query.filter(Contestant.verification_status == status_filter)
    
    contestants = query.all()
    
    # Get all submissions and comments in bulk to avoid N+1 queries
    from sqlalchemy import func
    
    contestant_ids = [c.id for c in contestants]
    
    # Get submission counts for all contestants
    submission_counts = {}
    if contestant_ids:
        submissions_data = db.query(
            ContestSubmission.contestant_id,
            func.count(ContestSubmission.id).label('count')
        ).filter(ContestSubmission.contestant_id.in_(contestant_ids)).group_by(
            ContestSubmission.contestant_id
        ).all()
        
        for contestant_id, count in submissions_data:
            submission_counts[contestant_id] = count
    
    # Get comment counts for all contestants (optimisé)
    comment_counts = {}
    if contestant_ids:
        comments_data = db.query(
            Comment.contestant_id,
            func.count(Comment.id).label('count')
        ).filter(
            Comment.contestant_id.in_(contestant_ids),
            Comment.is_deleted == False
        ).group_by(
            Comment.contestant_id
        ).all()
        
        for contestant_id, count in comments_data:
            comment_counts[contestant_id] = count
    
    # Return contestants with their data
    result = []
    for c in contestants:
        # Count images and videos from JSON arrays
        images_count = 0
        videos_count = 0
        
        if c.image_media_ids:
            try:
                image_ids = json.loads(c.image_media_ids)
                images_count = len(image_ids) if isinstance(image_ids, list) else 0
            except:
                images_count = 0
        
        if c.video_media_ids:
            try:
                video_ids = json.loads(c.video_media_ids)
                videos_count = len(video_ids) if isinstance(video_ids, list) else 0
            except:
                videos_count = 0
        
        # Get votes count from pre-fetched data
        votes_count = submission_counts.get(c.id, 0)
        
        # Get comment count from pre-fetched data
        comments_count = comment_counts.get(c.id, 0)
        
        # Get media items from image_media_ids and video_media_ids
        # These contain URLs, not IDs
        media_items = []
        
        # Process image media URLs
        if c.image_media_ids:
            try:
                image_urls = json.loads(c.image_media_ids)
                if isinstance(image_urls, list):
                    for idx, url in enumerate(image_urls):
                        if url:  # Only add if URL is not empty
                            media_items.append({
                                'id': f"image_{c.id}_{idx}",
                                'type': 'image',
                                'url': url,
                            })
            except:
                pass
        
        # Process video media URLs
        if c.video_media_ids:
            try:
                video_urls = json.loads(c.video_media_ids)
                if isinstance(video_urls, list):
                    for idx, url in enumerate(video_urls):
                        if url:  # Only add if URL is not empty
                            media_items.append({
                                'id': f"video_{c.id}_{idx}",
                                'type': 'video',
                                'url': url,
                            })
            except:
                pass
        
        # Ne pas charger tous les commentaires pour éviter les problèmes de performance
        # Si nécessaire, les commentaires peuvent être récupérés via un endpoint séparé
        
        result.append({
            'id': c.id,
            'user_id': c.user_id,
            'season_id': c.season_id,
            'title': c.title,
            'description': c.description,
            'registration_date': c.created_at,
            'verification_status': c.verification_status,
            'is_active': c.is_active,
            'is_qualified': c.is_qualified,
            'author_name': c.user.full_name if c.user else None,
            'author_avatar_url': c.user.avatar_url if c.user else None,
            'votes_count': votes_count,
            'comments_count': comments_count,
            'images_count': images_count,
            'videos_count': videos_count,
            'media_items': media_items,
        })
    
    return result


@router.get("/contestants/{contestant_id}/comments")
async def get_contestant_comments(
    contestant_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Récupère les commentaires d'un contestant spécifique (admin uniquement)
    """
    check_admin(current_user)
    
    from sqlalchemy.orm import joinedload
    
    # Vérifier que le contestant existe
    contestant = db.query(Contestant).filter(
        Contestant.id == contestant_id,
        Contestant.is_deleted == False
    ).first()
    
    if not contestant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidature non trouvée"
        )
    
    # Récupérer les commentaires avec les informations de l'utilisateur
    comments = db.query(Comment).options(
        joinedload(Comment.user)
    ).filter(
        Comment.contestant_id == contestant_id,
        Comment.is_deleted == False
    ).order_by(Comment.created_at.desc()).all()
    
    # Formater les commentaires
    comments_list = []
    for comment in comments:
        comments_list.append({
            'id': comment.id,
            'text': comment.content,
            'author_name': comment.user.full_name if comment.user else 'Anonymous',
            'created_at': comment.created_at.isoformat() if comment.created_at else None,
            'is_hidden': comment.is_hidden if hasattr(comment, 'is_hidden') else False,
        })
    
    return comments_list


@router.post("/contests", response_model=ContestResponse, status_code=status.HTTP_201_CREATED)
async def create_contest(
    contest_data: ContestCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Crée un nouveau concours (admin uniquement)
    Les dates sont générées automatiquement si non fournies.
    Le niveau par défaut est "city".
    """
    check_admin(current_user)
    
    try:
        # Vérifier que la saison existe si season_id est fourni
        season = None
        level = "city"  # Valeur par défaut
        if contest_data.season_id:
            season = db.query(ContestSeason).filter(
                ContestSeason.id == contest_data.season_id,
                ContestSeason.is_deleted == False
            ).first()
            if not season:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Saison non trouvée"
                )
            level = season.level.value
        elif contest_data.level:
            level = contest_data.level
        
        # Auto-generate dates
        submission_start, submission_end, voting_start, voting_end = generate_contest_dates(
            contest_data.submission_start_date
        )
        
        # Convertir voting_start en date pour calculer les dates des saisons
        voting_start_date_for_calc = voting_start
        if isinstance(voting_start_date_for_calc, str):
            try:
                voting_start_date_for_calc = datetime.strptime(voting_start_date_for_calc, '%Y-%m-%d').date()
            except (ValueError, TypeError):
                try:
                    if 'T' in voting_start_date_for_calc:
                        voting_start_date_for_calc = datetime.fromisoformat(voting_start_date_for_calc.replace('Z', '+00:00')).date()
                    else:
                        voting_start_date_for_calc = datetime.fromisoformat(voting_start_date_for_calc).date()
                except (ValueError, TypeError):
                    voting_start_date_for_calc = None
        elif isinstance(voting_start_date_for_calc, datetime):
            voting_start_date_for_calc = voting_start_date_for_calc.date()
        # Si c'est déjà un objet date, on le garde tel quel
        
        # Calculer les dates des saisons à partir de voting_start_date
        # Les dates sont calculées selon les règles :
        # - city_season_start_date = voting_start_date
        # - city_season_end_date = 1 mois après voting_start_date
        # - country_season_start_date = city_season_end_date
        # - country_season_end_date = 1 mois après country_season_start_date
        # - regional_start_date = country_season_end_date
        # - regional_end_date = 1 mois après regional_start_date
        # - continental_start_date = regional_end_date
        # - continental_end_date = 1 mois après continental_start_date
        # - global_start_date = continental_end_date
        # - global_end_date = 1 mois après global_start_date
        season_dates = calculate_season_dates(voting_start_date_for_calc) if voting_start_date_for_calc else {}
        
        # Handle enum conversions for verification_type and participant_type
        from app.models.contest import VerificationType, ParticipantType
        try:
            verification_type = VerificationType(contest_data.verification_type)
        except (ValueError, TypeError):
            verification_type = VerificationType.NONE
        try:
            participant_type = ParticipantType(contest_data.participant_type)
        except (ValueError, TypeError):
            participant_type = ParticipantType.INDIVIDUAL
        
        # Convertir voting_type_id=0 en None pour éviter les violations de FK
        voting_type_id = contest_data.voting_type_id if contest_data.voting_type_id and contest_data.voting_type_id > 0 else None
        category_id = contest_data.category_id if contest_data.category_id and contest_data.category_id > 0 else None
        
        # Si category_id est fourni, valider et récupérer la catégorie pour mettre à jour contest_type
        contest_type = contest_data.contest_type
        if category_id:
            category = db.query(Category).filter(Category.id == category_id).first()
            if category:
                contest_type = category.slug
        
        
        # Create contest with auto-generated values
        new_contest = Contest(
            name=contest_data.name,
            description=contest_data.description,
            contest_type=contest_data.contest_type,
            level=level,
            is_active=contest_data.is_active,
            is_submission_open=contest_data.is_submission_open,
            is_voting_open=contest_data.is_voting_open,
            submission_start_date=submission_start,
            submission_end_date=submission_end,
            voting_start_date=voting_start,
            voting_end_date=voting_end,
            image_url=contest_data.image_url,
            voting_restriction=contest_data.voting_restriction,
            voting_type_id=voting_type_id,
            category_id=category_id,
            # Verification fields

            requires_kyc=contest_data.requires_kyc,
            verification_type=verification_type,
            participant_type=participant_type,
            requires_visual_verification=contest_data.requires_visual_verification,
            requires_voice_verification=contest_data.requires_voice_verification,
            requires_brand_verification=contest_data.requires_brand_verification,
            requires_content_verification=contest_data.requires_content_verification,
            min_age=contest_data.min_age,
            max_age=contest_data.max_age,
            # Media requirements
            requires_video=contest_data.requires_video,
            max_videos=contest_data.max_videos,
            video_max_duration=contest_data.video_max_duration,
            video_max_size_mb=contest_data.video_max_size_mb,
            min_images=contest_data.min_images,
            max_images=contest_data.max_images,
            verification_video_max_duration=contest_data.verification_video_max_duration,
            verification_max_size_mb=contest_data.verification_max_size_mb,
            # Season dates
            **season_dates
        )
        
        db.add(new_contest)
        db.flush()  # Pour obtenir l'ID du contest
        
        # Créer la liaison avec la saison via ContestSeasonLink si season_id est fourni
        if contest_data.season_id:
            contest_season_link = ContestSeasonLink(
                contest_id=new_contest.id,
                season_id=contest_data.season_id,
                is_active=True
            )
            db.add(contest_season_link)
        
        db.commit()
        db.refresh(new_contest)
        
        # Get contest statistics (should be 0 for new contest)
        total, approved, pending = get_contest_stats(db, new_contest.id)
        
        # Return contest with statistics
        return {
            'id': new_contest.id,
            'name': new_contest.name,
            'description': new_contest.description,
            'contest_type': new_contest.contest_type,
            'level': new_contest.level,
            'season_id': contest_data.season_id,
            'is_active': new_contest.is_active,
            'is_submission_open': new_contest.is_submission_open,
            'is_voting_open': new_contest.is_voting_open,
            'submission_start_date': new_contest.submission_start_date,
            'submission_end_date': new_contest.submission_end_date,
            'voting_start_date': new_contest.voting_start_date,
            'voting_end_date': new_contest.voting_end_date,
            'image_url': new_contest.image_url,
            'cover_image_url': new_contest.cover_image_url,
            'voting_restriction': new_contest.voting_restriction.value if new_contest.voting_restriction else 'none',
            'voting_type_id': new_contest.voting_type_id,
            'voting_type': None, # Newly created, relationship might not be loaded yet
            'category_id': new_contest.category_id,
            'category': None, # Newly created, relationship might not be loaded yet
            'participant_count': total,
            'approved_count': approved,
            'pending_count': pending,
            'created_at': new_contest.created_at,
            'updated_at': new_contest.updated_at,
            # Verification fields
            'requires_kyc': new_contest.requires_kyc,
            'verification_type': new_contest.verification_type.value if new_contest.verification_type else 'none',
            'participant_type': new_contest.participant_type.value if new_contest.participant_type else 'individual',
            'requires_visual_verification': new_contest.requires_visual_verification,
            'requires_voice_verification': new_contest.requires_voice_verification,
            'requires_brand_verification': new_contest.requires_brand_verification,
            'requires_content_verification': new_contest.requires_content_verification,
            'min_age': new_contest.min_age,
            'max_age': new_contest.max_age,
            # Media requirements
            'requires_video': new_contest.requires_video,
            'max_videos': new_contest.max_videos,
            'video_max_duration': new_contest.video_max_duration,
            'video_max_size_mb': new_contest.video_max_size_mb,
            'min_images': new_contest.min_images,
            'max_images': new_contest.max_images,
            'verification_video_max_duration': new_contest.verification_video_max_duration,
            'verification_max_size_mb': new_contest.verification_max_size_mb
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Erreur lors de la création du concours: {str(e)}"
        )

@router.put("/contests/{contest_id}", response_model=ContestResponse)
async def update_contest(
    contest_id: int,
    contest_data: ContestCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Met à jour un concours (admin uniquement)
    """
    check_admin(current_user)
    
    contest = db.query(Contest).filter(Contest.id == contest_id).first()
    if not contest:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Concours non trouvé"
        )
    
    try:
        # Vérifier que la saison existe si season_id est fourni
        season = None
        level = contest.level  # Conserver le niveau actuel par défaut
        if contest_data.season_id:
            season = db.query(ContestSeason).filter(
                ContestSeason.id == contest_data.season_id,
                ContestSeason.is_deleted == False
            ).first()
            if not season:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Saison non trouvée"
                )
            level = season.level.value
        
        # Update fields
        contest.name = contest_data.name
        contest.description = contest_data.description
        contest.contest_type = contest_data.contest_type
        contest.level = level
        contest.is_active = contest_data.is_active
        contest.is_submission_open = contest_data.is_submission_open
        contest.is_voting_open = contest_data.is_voting_open
        contest.image_url = contest_data.image_url
        contest.voting_restriction = contest_data.voting_restriction
        # Convertir voting_type_id=0 en None pour éviter les violations de FK
        contest.voting_type_id = contest_data.voting_type_id if contest_data.voting_type_id and contest_data.voting_type_id > 0 else None
        
        # Gestion de category_id
        contest.category_id = contest_data.category_id if contest_data.category_id and contest_data.category_id > 0 else None
        
        # Si category_id est fourni, mettre à jour contest_type
        if contest.category_id:
            category = db.query(Category).filter(Category.id == contest.category_id).first()
            if category:
                contest.contest_type = category.slug

        
        # Update verification fields
        contest.requires_kyc = contest_data.requires_kyc
        contest.requires_visual_verification = contest_data.requires_visual_verification
        contest.requires_voice_verification = contest_data.requires_voice_verification
        contest.requires_brand_verification = contest_data.requires_brand_verification
        contest.requires_content_verification = contest_data.requires_content_verification
        contest.min_age = contest_data.min_age
        contest.max_age = contest_data.max_age
        
        # Update media requirements fields
        contest.requires_video = contest_data.requires_video
        contest.max_videos = contest_data.max_videos
        contest.video_max_duration = contest_data.video_max_duration
        contest.video_max_size_mb = contest_data.video_max_size_mb
        contest.min_images = contest_data.min_images
        contest.max_images = contest_data.max_images
        contest.verification_video_max_duration = contest_data.verification_video_max_duration
        contest.verification_max_size_mb = contest_data.verification_max_size_mb
        
        # Handle enum conversions for verification_type and participant_type
        from app.models.contest import VerificationType, ParticipantType
        try:
            contest.verification_type = VerificationType(contest_data.verification_type)
        except (ValueError, TypeError):
            contest.verification_type = VerificationType.NONE
        try:
            contest.participant_type = ParticipantType(contest_data.participant_type)
        except (ValueError, TypeError):
            contest.participant_type = ParticipantType.INDIVIDUAL
        
        # Gérer la liaison avec la saison
        if contest_data.season_id is not None:
            # Récupérer la liaison actuelle
            current_link = db.query(ContestSeasonLink).filter(
                ContestSeasonLink.contest_id == contest_id,
                ContestSeasonLink.is_active == True
            ).first()
            
            if current_link:
                if current_link.season_id != contest_data.season_id:
                    # Désactiver l'ancienne liaison
                    current_link.is_active = False
                    # Vérifier si une liaison existe déjà pour la nouvelle saison
                    existing_link = db.query(ContestSeasonLink).filter(
                        ContestSeasonLink.contest_id == contest_id,
                        ContestSeasonLink.season_id == contest_data.season_id
                    ).first()
                    if existing_link:
                        # Réactiver la liaison existante
                        existing_link.is_active = True
                    else:
                        # Créer une nouvelle liaison
                        new_link = ContestSeasonLink(
                            contest_id=contest_id,
                            season_id=contest_data.season_id,
                            is_active=True
                        )
                        db.add(new_link)
            else:
                # Créer une nouvelle liaison
                new_link = ContestSeasonLink(
                    contest_id=contest_id,
                    season_id=contest_data.season_id,
                    is_active=True
                )
                db.add(new_link)
        
        # Helper function pour parser les dates
        def parse_date(date_str: Optional[str]):
            if not date_str:
                return None
            try:
                if 'T' in date_str:
                    parsed = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                    return parsed.date() if isinstance(parsed, datetime) else parsed
                else:
                    return datetime.strptime(date_str, '%Y-%m-%d').date()
            except (ValueError, TypeError):
                return None
        
        # Update main dates if provided
        voting_start_changed = False
        
        # Mettre à jour les dates individuellement si elles sont fournies
        if contest_data.submission_start_date is not None:
            parsed_date = parse_date(contest_data.submission_start_date)
            if parsed_date:
                contest.submission_start_date = parsed_date
                # Si seulement submission_start_date est fourni, générer les autres dates automatiquement
                if not contest_data.submission_end_date and not contest_data.voting_start_date and not contest_data.voting_end_date:
                    submission_start, submission_end, voting_start, voting_end = generate_contest_dates(
                        contest_data.submission_start_date
                    )
                    contest.submission_end_date = submission_end
                    if contest.voting_start_date != voting_start:
                        voting_start_changed = True
                    contest.voting_start_date = voting_start
                    contest.voting_end_date = voting_end
        
        if contest_data.submission_end_date is not None:
            parsed_date = parse_date(contest_data.submission_end_date)
            if parsed_date:
                contest.submission_end_date = parsed_date
        
        if contest_data.voting_start_date is not None:
            parsed_date = parse_date(contest_data.voting_start_date)
            if parsed_date:
                old_voting_start = contest.voting_start_date
                if isinstance(old_voting_start, datetime):
                    old_voting_start = old_voting_start.date()
                if old_voting_start != parsed_date:
                    voting_start_changed = True
                contest.voting_start_date = parsed_date
        
        if contest_data.voting_end_date is not None:
            parsed_date = parse_date(contest_data.voting_end_date)
            if parsed_date:
                contest.voting_end_date = parsed_date
        
        # Recalculer les dates des saisons si voting_start_date a changé
        if voting_start_changed:
            voting_start_for_calc = contest.voting_start_date
            if isinstance(voting_start_for_calc, datetime):
                voting_start_for_calc = voting_start_for_calc.date()
            elif isinstance(voting_start_for_calc, str):
                try:
                    if 'T' in voting_start_for_calc:
                        voting_start_for_calc = datetime.fromisoformat(voting_start_for_calc.replace('Z', '+00:00')).date()
                    else:
                        voting_start_for_calc = datetime.strptime(voting_start_for_calc, '%Y-%m-%d').date()
                except (ValueError, TypeError):
                    voting_start_for_calc = None
            
            if voting_start_for_calc:
                calculated_dates = calculate_season_dates(voting_start_for_calc)
                contest.city_season_start_date = calculated_dates.get('city_season_start_date')
                contest.city_season_end_date = calculated_dates.get('city_season_end_date')
                contest.country_season_start_date = calculated_dates.get('country_season_start_date')
                contest.country_season_end_date = calculated_dates.get('country_season_end_date')
                contest.regional_start_date = calculated_dates.get('regional_start_date')
                contest.regional_end_date = calculated_dates.get('regional_end_date')
                contest.continental_start_date = calculated_dates.get('continental_start_date')
                contest.continental_end_date = calculated_dates.get('continental_end_date')
                contest.global_start_date = calculated_dates.get('global_start_date')
                contest.global_end_date = calculated_dates.get('global_end_date')
        
        # Mettre à jour les dates des saisons si elles sont fournies explicitement
        if contest_data.city_season_start_date is not None:
            contest.city_season_start_date = parse_date(contest_data.city_season_start_date)
        if contest_data.city_season_end_date is not None:
            contest.city_season_end_date = parse_date(contest_data.city_season_end_date)
        if contest_data.country_season_start_date is not None:
            contest.country_season_start_date = parse_date(contest_data.country_season_start_date)
        if contest_data.country_season_end_date is not None:
            contest.country_season_end_date = parse_date(contest_data.country_season_end_date)
        if contest_data.regional_start_date is not None:
            contest.regional_start_date = parse_date(contest_data.regional_start_date)
        if contest_data.regional_end_date is not None:
            contest.regional_end_date = parse_date(contest_data.regional_end_date)
        if contest_data.continental_start_date is not None:
            contest.continental_start_date = parse_date(contest_data.continental_start_date)
        if contest_data.continental_end_date is not None:
            contest.continental_end_date = parse_date(contest_data.continental_end_date)
        if contest_data.global_start_date is not None:
            contest.global_start_date = parse_date(contest_data.global_start_date)
        if contest_data.global_end_date is not None:
            contest.global_end_date = parse_date(contest_data.global_end_date)
        
        db.commit()
        db.refresh(contest)
        
        # Get contest statistics
        total, approved, pending = get_contest_stats(db, contest.id)
        
        # Récupérer le season_id actuel
        current_season_link = db.query(ContestSeasonLink).filter(
            ContestSeasonLink.contest_id == contest_id,
            ContestSeasonLink.is_active == True
        ).first()
        season_id = current_season_link.season_id if current_season_link else None
        
        # Return contest with statistics
        return {
            'id': contest.id,
            'name': contest.name,
            'description': contest.description,
            'contest_type': contest.contest_type,
            'level': contest.level,
            'season_id': season_id,
            'is_active': contest.is_active,
            'is_submission_open': contest.is_submission_open,
            'is_voting_open': contest.is_voting_open,
            'submission_start_date': contest.submission_start_date,
            'submission_end_date': contest.submission_end_date,
            'voting_start_date': contest.voting_start_date,
            'voting_end_date': contest.voting_end_date,
            'image_url': contest.image_url,
            'cover_image_url': contest.cover_image_url,
            'voting_restriction': contest.voting_restriction.value if contest.voting_restriction else 'none',
            'voting_type_id': contest.voting_type_id,
            'voting_type': {
                "id": contest.voting_type.id,
                "name": contest.voting_type.name,
                "voting_level": contest.voting_type.voting_level.value if hasattr(contest.voting_type.voting_level, 'value') else str(contest.voting_type.voting_level),
                "commission_source": contest.voting_type.commission_source.value if hasattr(contest.voting_type.commission_source, 'value') else str(contest.voting_type.commission_source),
            } if contest.voting_type else None,
            'category_id': contest.category_id,
            'category': {
                "id": contest.category.id,
                "name": contest.category.name,
                "slug": contest.category.slug,
                "description": contest.category.description,
                "is_active": contest.category.is_active
            } if contest.category else None,
            'participant_count': total,
            'approved_count': approved,
            'pending_count': pending,
            'created_at': contest.created_at,
            'updated_at': contest.updated_at,
            # Verification fields
            'requires_kyc': contest.requires_kyc,
            'verification_type': contest.verification_type.value if contest.verification_type else 'none',
            'participant_type': contest.participant_type.value if contest.participant_type else 'individual',
            'requires_visual_verification': contest.requires_visual_verification,
            'requires_voice_verification': contest.requires_voice_verification,
            'requires_brand_verification': contest.requires_brand_verification,
            'requires_content_verification': contest.requires_content_verification,
            'min_age': contest.min_age,
            'max_age': contest.max_age,
            # Season dates
            'city_season_start_date': getattr(contest, 'city_season_start_date', None),
            'city_season_end_date': getattr(contest, 'city_season_end_date', None),
            'country_season_start_date': getattr(contest, 'country_season_start_date', None),
            'country_season_end_date': getattr(contest, 'country_season_end_date', None),
            'regional_start_date': getattr(contest, 'regional_start_date', None),
            'regional_end_date': getattr(contest, 'regional_end_date', None),
            'continental_start_date': getattr(contest, 'continental_start_date', None),
            'continental_end_date': getattr(contest, 'continental_end_date', None),
            'global_start_date': getattr(contest, 'global_start_date', None),
            'global_end_date': getattr(contest, 'global_end_date', None),
            # Media requirements
            'requires_video': getattr(contest, 'requires_video', False),
            'max_videos': getattr(contest, 'max_videos', 1),
            'video_max_duration': getattr(contest, 'video_max_duration', 3000),
            'video_max_size_mb': getattr(contest, 'video_max_size_mb', 500),
            'min_images': getattr(contest, 'min_images', 0),
            'max_images': getattr(contest, 'max_images', 10),
            'verification_video_max_duration': getattr(contest, 'verification_video_max_duration', 30),
            'verification_max_size_mb': getattr(contest, 'verification_max_size_mb', 50)
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Erreur lors de la mise à jour du concours: {str(e)}"
        )

@router.delete("/contests/{contest_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_contest(
    contest_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Soft delete un concours et tous ses contestants (admin uniquement)
    """
    check_admin(current_user)
    
    contest = db.query(Contest).filter(Contest.id == contest_id).first()
    if not contest:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Concours non trouvé"
        )
    
    try:
        # Soft delete le concours
        contest.is_deleted = True
        
        # Soft delete tous les contestants du concours
        contestants = db.query(Contestant).filter(
            Contestant.season_id == contest_id
        ).all()
        for contestant in contestants:
            contestant.is_deleted = True
        
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Erreur lors de la suppression du concours: {str(e)}"
        )

# Seasons endpoints
class SeasonCreateRequest(BaseModel):
    title: str
    level: str  # city, country, regional, continent, global

    class Config:
        from_attributes = True

class SeasonResponse(BaseModel):
    id: int
    title: str
    level: str
    contestants_count: int = 0
    contests_count: int = 0

    class Config:
        from_attributes = True

@router.get("/seasons", response_model=List[SeasonResponse])
async def get_all_seasons(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Récupère toutes les saisons (admin uniquement)
    """
    check_admin(current_user)
    
    seasons = db.query(ContestSeason).filter(ContestSeason.is_deleted == False).all()
    
    result = []
    for season in seasons:
        # Count contestants linked to this season
        contestants_count = db.query(ContestantSeason).filter(
            ContestantSeason.season_id == season.id,
            ContestantSeason.is_active == True
        ).count()
        
        # Count contests linked to this season
        contests_count = db.query(ContestSeasonLink).filter(
            ContestSeasonLink.season_id == season.id,
            ContestSeasonLink.is_active == True
        ).count()
        
        result.append({
            "id": season.id,
            "title": season.title,
            "level": season.level.value,
            "contestants_count": contestants_count,
            "contests_count": contests_count,
        })
    
    return result

@router.post("/seasons", response_model=SeasonResponse, status_code=status.HTTP_201_CREATED)
async def create_season(
    season_data: SeasonCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Crée une nouvelle saison (admin uniquement)
    """
    check_admin(current_user)
    
    # Validate level
    valid_levels = ['city', 'country', 'regional', 'continent', 'global']
    if season_data.level not in valid_levels:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Niveau invalide. Les niveaux valides sont: {', '.join(valid_levels)}"
        )
    
    # Check if a season with this level already exists
    existing_season = db.query(ContestSeason).filter(
        ContestSeason.level == SeasonLevel(season_data.level),
        ContestSeason.is_deleted == False
    ).first()
    
    if existing_season:
        level_names = {
            'city': 'ville',
            'country': 'pays',
            'regional': 'régional',
            'continent': 'continent',
            'global': 'global'
        }
        level_name = level_names.get(season_data.level, season_data.level)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Une saison avec le niveau '{level_name}' existe déjà. Il ne peut y avoir qu'une seule saison active par niveau."
        )
    
    try:
        new_season = ContestSeason(
            title=season_data.title,
            level=SeasonLevel(season_data.level)
        )
        db.add(new_season)
        db.commit()
        db.refresh(new_season)
        
        return {
            "id": new_season.id,
            "title": new_season.title,
            "level": new_season.level.value
        }
    except IntegrityError as e:
        db.rollback()
        # Check if it's a unique constraint violation
        if isinstance(e.orig, UniqueViolation) and 'uq_contest_seasons_level_active' in str(e.orig):
            level_names = {
                'city': 'ville',
                'country': 'pays',
                'regional': 'régional',
                'continent': 'continent',
                'global': 'global'
            }
            level_name = level_names.get(season_data.level, season_data.level)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Une saison avec le niveau '{level_name}' existe déjà. Il ne peut y avoir qu'une seule saison active par niveau."
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Erreur lors de la création de la saison: {str(e)}"
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Erreur lors de la création de la saison: {str(e)}"
        )

@router.put("/seasons/{season_id}", response_model=SeasonResponse)
async def update_season(
    season_id: int,
    season_data: SeasonCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Met à jour une saison (admin uniquement)
    """
    check_admin(current_user)
    
    season = db.query(ContestSeason).filter(ContestSeason.id == season_id, ContestSeason.is_deleted == False).first()
    if not season:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Saison non trouvée"
        )
    
    # Validate level
    valid_levels = ['city', 'country', 'regional', 'continent', 'global']
    if season_data.level not in valid_levels:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Niveau invalide. Les niveaux valides sont: {', '.join(valid_levels)}"
        )
    
    # Check if another season with this level already exists (excluding current season)
    if season.level != SeasonLevel(season_data.level):
        existing_season = db.query(ContestSeason).filter(
            ContestSeason.level == SeasonLevel(season_data.level),
            ContestSeason.is_deleted == False,
            ContestSeason.id != season_id
        ).first()
        
        if existing_season:
            level_names = {
                'city': 'ville',
                'country': 'pays',
                'regional': 'régional',
                'continent': 'continent',
                'global': 'global'
            }
            level_name = level_names.get(season_data.level, season_data.level)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Une saison avec le niveau '{level_name}' existe déjà. Il ne peut y avoir qu'une seule saison active par niveau."
            )
    
    try:
        season.title = season_data.title
        season.level = SeasonLevel(season_data.level)
        
        db.commit()
        db.refresh(season)
        
        return {
            "id": season.id,
            "title": season.title,
            "level": season.level.value
        }
    except IntegrityError as e:
        db.rollback()
        # Check if it's a unique constraint violation
        if isinstance(e.orig, UniqueViolation) and 'uq_contest_seasons_level_active' in str(e.orig):
            level_names = {
                'city': 'ville',
                'country': 'pays',
                'regional': 'régional',
                'continent': 'continent',
                'global': 'global'
            }
            level_name = level_names.get(season_data.level, season_data.level)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Une saison avec le niveau '{level_name}' existe déjà. Il ne peut y avoir qu'une seule saison active par niveau."
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Erreur lors de la mise à jour de la saison: {str(e)}"
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Erreur lors de la mise à jour de la saison: {str(e)}"
        )

@router.delete("/seasons/{season_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_season(
    season_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Soft delete une saison (admin uniquement)
    """
    check_admin(current_user)
    
    season = db.query(ContestSeason).filter(ContestSeason.id == season_id, ContestSeason.is_deleted == False).first()
    if not season:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Saison non trouvée"
        )
    
    try:
        season.is_deleted = True
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Erreur lors de la suppression de la saison: {str(e)}"
        )

@router.post("/contestants/{contestant_id}/approve")
async def approve_contestant(
    contestant_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Approuve un candidat (admin uniquement)
    """
    check_admin(current_user)
    
    contestant = db.query(Contestant).filter(Contestant.id == contestant_id).first()
    if not contestant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidat non trouvé"
        )
    
    try:
        contestant.verification_status = "verified"
        db.commit()
        db.refresh(contestant)
        
        return {
            'id': contestant.id,
            'verification_status': contestant.verification_status,
            'message': 'Candidat approuvé avec succès'
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Erreur lors de l'approbation du candidat: {str(e)}"
        )

@router.post("/contestants/{contestant_id}/reject")
async def reject_contestant(
    contestant_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Rejette un candidat (admin uniquement)
    """
    check_admin(current_user)
    
    contestant = db.query(Contestant).filter(Contestant.id == contestant_id).first()
    if not contestant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidat non trouvé"
        )
    
    try:
        contestant.verification_status = "rejected"
        db.commit()
        db.refresh(contestant)
        
        return {
            'id': contestant.id,
            'verification_status': contestant.verification_status,
            'message': 'Candidat rejeté avec succès'
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Erreur lors du rejet du candidat: {str(e)}"
        )

@router.put("/contestants/{contestant_id}/status")
async def update_contestant_status(
    contestant_id: int,
    status: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Met à jour le statut d'un candidat (admin uniquement)
    """
    check_admin(current_user)
    
    # Validate status
    valid_statuses = ['pending', 'verified', 'rejected']
    if status not in valid_statuses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Statut invalide. Les statuts valides sont: {', '.join(valid_statuses)}"
        )
    
    contestant = db.query(Contestant).filter(Contestant.id == contestant_id).first()
    if not contestant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidat non trouvé"
        )
    
    try:
        contestant.verification_status = status
        db.commit()
        db.refresh(contestant)
        
        return {
            'id': contestant.id,
            'verification_status': contestant.verification_status,
            'message': f'Statut du candidat mis à jour avec succès'
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Erreur lors de la mise à jour du statut: {str(e)}"
        )

# Contestants endpoints - Create/Update
class ContestantCreateRequest(BaseModel):
    user_id: int
    season_id: int
    title: Optional[str] = None
    description: Optional[str] = None
    image_media_ids: Optional[str] = None
    video_media_ids: Optional[str] = None
    verification_status: str = "pending"

    class Config:
        from_attributes = True

class ContestantUpdateRequest(BaseModel):
    season_id: Optional[int] = None
    title: Optional[str] = None
    description: Optional[str] = None
    image_media_ids: Optional[str] = None
    video_media_ids: Optional[str] = None
    verification_status: Optional[str] = None

    class Config:
        from_attributes = True

@router.get("/seasons/by-level/{level}")
async def get_seasons_by_level(
    level: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Récupère les saisons par niveau (admin uniquement)
    """
    check_admin(current_user)
    
    valid_levels = ['city', 'country', 'regional', 'continent', 'global']
    if level not in valid_levels:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Niveau invalide. Les niveaux valides sont: {', '.join(valid_levels)}"
        )
    
    seasons = db.query(ContestSeason).filter(
        ContestSeason.level == SeasonLevel(level),
        ContestSeason.is_deleted == False
    ).all()
    
    return [
        {
            "id": season.id,
            "title": season.title,
            "level": season.level.value,
        }
        for season in seasons
    ]

@router.post("/contestants", status_code=status.HTTP_201_CREATED)
async def create_contestant(
    contestant_data: ContestantCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Crée un nouveau candidat et le lie à une saison (admin uniquement)
    """
    check_admin(current_user)
    
    # Vérifier que l'utilisateur existe
    user = db.query(User).filter(User.id == contestant_data.user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Utilisateur non trouvé"
        )
    
    # Vérifier que la saison existe
    season = db.query(ContestSeason).filter(
        ContestSeason.id == contestant_data.season_id,
        ContestSeason.is_deleted == False
    ).first()
    if not season:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Saison non trouvée"
        )
    
    # Vérifier que l'utilisateur n'a pas déjà un candidat pour cette saison
    existing_contestant = db.query(Contestant).filter(
        Contestant.user_id == contestant_data.user_id,
        Contestant.season_id == contestant_data.season_id,
        Contestant.is_deleted == False
    ).first()
    
    if existing_contestant:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cet utilisateur a déjà un candidat pour cette saison"
        )
    
    try:
        # Créer le candidat
        new_contestant = Contestant(
            user_id=contestant_data.user_id,
            season_id=contestant_data.season_id,
            title=contestant_data.title,
            description=contestant_data.description,
            image_media_ids=contestant_data.image_media_ids,
            video_media_ids=contestant_data.video_media_ids,
            verification_status=contestant_data.verification_status
        )
        db.add(new_contestant)
        db.flush()  # Pour obtenir l'ID du candidat
        
        # Créer la liaison avec la saison via ContestantSeason
        contestant_season_link = ContestantSeason(
            contestant_id=new_contestant.id,
            season_id=contestant_data.season_id,
            is_active=True
        )
        db.add(contestant_season_link)
        
        db.commit()
        db.refresh(new_contestant)
        
        return {
            "id": new_contestant.id,
            "user_id": new_contestant.user_id,
            "season_id": new_contestant.season_id,
            "title": new_contestant.title,
            "description": new_contestant.description,
            "verification_status": new_contestant.verification_status,
            "message": "Candidat créé avec succès"
        }
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Erreur lors de la création du candidat: {str(e)}"
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Erreur lors de la création du candidat: {str(e)}"
        )

@router.put("/contestants/{contestant_id}")
async def update_contestant(
    contestant_id: int,
    contestant_data: ContestantUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Met à jour un candidat et sa liaison avec les saisons (admin uniquement)
    """
    check_admin(current_user)
    
    contestant = db.query(Contestant).filter(
        Contestant.id == contestant_id,
        Contestant.is_deleted == False
    ).first()
    
    if not contestant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidat non trouvé"
        )
    
    try:
        # Mettre à jour les champs du candidat
        if contestant_data.title is not None:
            contestant.title = contestant_data.title
        if contestant_data.description is not None:
            contestant.description = contestant_data.description
        if contestant_data.image_media_ids is not None:
            contestant.image_media_ids = contestant_data.image_media_ids
        if contestant_data.video_media_ids is not None:
            contestant.video_media_ids = contestant_data.video_media_ids
        if contestant_data.verification_status is not None:
            contestant.verification_status = contestant_data.verification_status
        
        # Si la saison change, mettre à jour la liaison
        if contestant_data.season_id is not None and contestant_data.season_id != contestant.season_id:
            # Vérifier que la nouvelle saison existe
            season = db.query(ContestSeason).filter(
                ContestSeason.id == contestant_data.season_id,
                ContestSeason.is_deleted == False
            ).first()
            if not season:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Saison non trouvée"
                )
            
            # Désactiver l'ancienne liaison
            old_link = db.query(ContestantSeason).filter(
                ContestantSeason.contestant_id == contestant_id,
                ContestantSeason.season_id == contestant.season_id
            ).first()
            if old_link:
                old_link.is_active = False
            
            # Vérifier si une liaison existe déjà pour la nouvelle saison
            existing_link = db.query(ContestantSeason).filter(
                ContestantSeason.contestant_id == contestant_id,
                ContestantSeason.season_id == contestant_data.season_id
            ).first()
            
            if existing_link:
                # Réactiver la liaison existante
                existing_link.is_active = True
            else:
                # Créer une nouvelle liaison
                new_link = ContestantSeason(
                    contestant_id=contestant_id,
                    season_id=contestant_data.season_id,
                    is_active=True
                )
                db.add(new_link)
            
            contestant.season_id = contestant_data.season_id
        
        db.commit()
        db.refresh(contestant)
        
        return {
            "id": contestant.id,
            "user_id": contestant.user_id,
            "season_id": contestant.season_id,
            "title": contestant.title,
            "description": contestant.description,
            "verification_status": contestant.verification_status,
            "message": "Candidat mis à jour avec succès"
        }
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Erreur lors de la mise à jour du candidat: {str(e)}"
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Erreur lors de la mise à jour du candidat: {str(e)}"
        )

@router.put("/comments/{comment_id}")
async def update_comment(
    comment_id: int,
    update_data: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Met à jour un commentaire (masquer/afficher) - admin uniquement
    """
    check_admin(current_user)
    
    comment = db.query(Comment).filter(Comment.id == comment_id).first()
    if not comment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Commentaire non trouvé"
        )
    
    try:
        if 'is_hidden' in update_data:
            comment.is_hidden = update_data['is_hidden']
        
        db.commit()
        db.refresh(comment)
        
        return {
            'id': comment.id,
            'is_hidden': comment.is_hidden,
            'message': 'Commentaire mis à jour avec succès'
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Erreur lors de la mise à jour du commentaire: {str(e)}"
        )

@router.delete("/comments/{comment_id}")
async def delete_comment(
    comment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Marque un commentaire comme supprimé (soft delete) - admin uniquement
    """
    check_admin(current_user)
    
    comment = db.query(Comment).filter(Comment.id == comment_id).first()
    if not comment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Commentaire non trouvé"
        )
    
    try:
        comment.is_deleted = True
        db.commit()
        db.refresh(comment)
        
        return {
            'id': comment_id,
            'is_deleted': comment.is_deleted,
            'message': 'Commentaire supprimé avec succès'
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Erreur lors de la suppression du commentaire: {str(e)}"
        )

@router.put("/comments/{comment_id}/hide")
async def hide_comment(
    comment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Cache un commentaire (admin uniquement)
    """
    check_admin(current_user)
    
    comment = db.query(Comment).filter(Comment.id == comment_id).first()
    if not comment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Commentaire non trouvé"
        )
    
    try:
        comment.is_hidden = True
        db.commit()
        db.refresh(comment)
        
        return {
            'id': comment.id,
            'is_hidden': comment.is_hidden,
            'message': 'Commentaire caché avec succès'
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Erreur lors du masquage du commentaire: {str(e)}"
        )

@router.put("/comments/{comment_id}/show")
async def show_comment(
    comment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Affiche un commentaire caché (admin uniquement)
    """
    check_admin(current_user)
    
    comment = db.query(Comment).filter(Comment.id == comment_id).first()
    if not comment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Commentaire non trouvé"
        )
    
    try:
        comment.is_hidden = False
        db.commit()
        db.refresh(comment)
        
        return {
            'id': comment.id,
            'is_hidden': comment.is_hidden,
            'message': 'Commentaire affiché avec succès'
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Erreur lors de l'affichage du commentaire: {str(e)}"
        )

@router.put("/comments/{comment_id}/restore")
async def restore_comment(
    comment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Restaure un commentaire supprimé (admin uniquement)
    """
    check_admin(current_user)
    
    comment = db.query(Comment).filter(Comment.id == comment_id).first()
    if not comment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Commentaire non trouvé"
        )
    
    try:
        comment.is_deleted = False
        db.commit()
        db.refresh(comment)
        
        return {
            'id': comment.id,
            'is_deleted': comment.is_deleted,
            'message': 'Commentaire restauré avec succès'
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Erreur lors de la restauration du commentaire: {str(e)}"
        )

# Users endpoints
@router.get("/users")
async def get_all_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    is_admin: Optional[bool] = None,
    is_active: Optional[bool] = None,
    is_verified: Optional[bool] = None
):
    """
    Récupère tous les utilisateurs (admin uniquement)
    """
    check_admin(current_user)
    
    try:
        query = db.query(User).filter(User.is_deleted == False)
        
        if is_admin is not None:
            query = query.filter(User.is_admin == is_admin)
        if is_active is not None:
            query = query.filter(User.is_active == is_active)
        if is_verified is not None:
            query = query.filter(User.is_verified == is_verified)
        
        # Trier du plus récent au plus ancien
        users = query.order_by(User.created_at.desc()).all()
        
        # Enrichir avec les statistiques
        result = []
        for user in users:
            # Compter les participations (contestants créés)
            participations_count = db.query(Contestant).filter(Contestant.user_id == user.id).count()
            
            # Compter les prix (à implémenter selon votre modèle)
            prizes_count = 0
            
            # Compter les candidats (contestants créés)
            contestants_count = db.query(Contestant).filter(Contestant.user_id == user.id).count()
            
            # Compter les contests participés
            contests_participated = db.query(ContestEntry).filter(ContestEntry.user_id == user.id).count()
            
            user_dict = {
                'id': user.id,
                'email': user.email,
                'full_name': user.full_name,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'username': user.username,
                'avatar_url': user.avatar_url,
                'is_active': user.is_active,
                'is_verified': user.is_verified,
                'is_admin': user.is_admin,
                'created_at': user.created_at,
                'date_of_birth': user.date_of_birth,
                'city': user.city,
                'country': user.country,
                'continent': user.continent,
                'region': user.region,
                'kyc_status': 'verified' if user.identity_verified else 'pending',
                'kyc_verified_at': user.verification_date,
                'participations_count': participations_count,
                'prizes_count': prizes_count,
                'contestants_count': contestants_count,
                'contests_participated': contests_participated,
                'max_level_reached': None
            }
            result.append(user_dict)
        
        return result
    except Exception as e:
        print(f"ERROR in get_all_users: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la récupération des utilisateurs: {str(e)}"
        )

@router.get("/users/{user_id}")
async def get_user_details(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Récupère les détails d'un utilisateur spécifique (admin uniquement)
    """
    check_admin(current_user)
    
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Utilisateur non trouvé"
            )
        
        # Récupérer les statistiques
        participations_count = db.query(Contestant).filter(Contestant.user_id == user.id).count()
        prizes_count = 0  # À implémenter selon votre modèle Prize
        contestants_count = db.query(Contestant).filter(Contestant.user_id == user.id).count()
        contests_participated = db.query(ContestEntry).filter(ContestEntry.user_id == user.id).count()
        
        # Récupérer les contests participés
        contests = db.query(ContestEntry).filter(ContestEntry.user_id == user.id).all()
        contests_list = [
            {
                'id': c.contest_id,
                'title': c.contest.name if c.contest else 'Concours supprimé'
            }
            for c in contests
        ]
        
        # Récupérer les contestants créés
        contestants = db.query(Contestant).filter(Contestant.user_id == user.id).all()
        contestants_list = [
            {
                'id': c.id,
                'title': c.title,
                'verification_status': c.verification_status
            }
            for c in contestants
        ]
        
        # Récupérer les commentaires de l'utilisateur
        from sqlalchemy.orm import joinedload
        comments = db.query(Comment).options(
            joinedload(Comment.contestant)
        ).filter(
            Comment.user_id == user.id,
            Comment.is_deleted == False
        ).all()
        comments_list = []
        for c in comments:
            comment_data = {
                'id': c.id,
                'content': c.content,
                'created_at': c.created_at,
                'is_hidden': c.is_hidden,
                'contestant': None,
                'contest': None
            }
            
            # Ajouter les infos du contestant si disponible
            if c.contestant_id and c.contestant:
                comment_data['contestant'] = {
                    'id': c.contestant_id,
                    'title': c.contestant.title
                }
                
                # Récupérer le contest via season_id du contestant
                if c.contestant.season_id:
                    contest = db.query(Contest).filter(Contest.id == c.contestant.season_id).first()
                    if contest:
                        comment_data['contest'] = {
                            'id': contest.id,
                            'name': contest.name
                        }
            
            comments_list.append(comment_data)
        
        # Récupérer les dépôts
        deposits = db.query(Deposit).filter(Deposit.user_id == user.id).order_by(Deposit.created_at.desc()).all()
        deposits_list = []
        for d in deposits:
            product_type = db.query(ProductType).filter(ProductType.id == d.product_type_id).first()
            deposits_list.append({
                'id': d.id,
                'amount': float(d.amount),
                'currency': d.currency,
                'crypto_currency': d.crypto_currency,
                'crypto_amount': float(d.crypto_amount) if d.crypto_amount else None,
                'status': d.status.value if d.status else None,
                'product_type': product_type.code if product_type else None,
                'product_type_name': product_type.name if product_type else None,
                'order_id': d.order_id,
                'tx_hash': d.tx_hash,
                'created_at': d.created_at.isoformat() if d.created_at else None,
                'validated_at': d.validated_at.isoformat() if d.validated_at else None,
                'is_used': d.is_used
            })
        
        # Récupérer les retraits
        withdrawals = db.query(UserTransaction).filter(
            UserTransaction.user_id == user.id,
            UserTransaction.transaction_type == TransactionType.WITHDRAWAL
        ).order_by(UserTransaction.created_at.desc()).all()
        withdrawals_list = []
        for w in withdrawals:
            withdrawals_list.append({
                'id': w.id,
                'amount': float(w.amount),
                'currency': w.currency,
                'status': w.status.value if w.status else None,
                'description': w.description,
                'reference': w.reference,
                'payment_method': w.payment_method,
                'payment_reference': w.payment_reference,
                'processed_at': w.processed_at.isoformat() if w.processed_at else None,
                'created_at': w.created_at.isoformat() if w.created_at else None
            })
        
        # Récupérer le rôle
        role_info = None
        if user.role_id:
            role = db.query(Role).filter(Role.id == user.role_id).first()
            if role:
                role_info = {
                    'id': role.id,
                    'name': role.name,
                    'description': role.description
                }
        
        # Récupérer les clubs (clubs dont l'utilisateur est membre)
        club_memberships = db.query(ClubMembership).filter(ClubMembership.member_id == user.id).all()
        clubs_list = []
        for cm in club_memberships:
            club = db.query(FanClub).filter(FanClub.id == cm.club_id).first()
            if club:
                clubs_list.append({
                    'id': club.id,
                    'name': club.name,
                    'slug': club.slug,
                    'description': club.description,
                    'membership_type': cm.membership_type.value if cm.membership_type else None,
                    'membership_status': cm.status.value if cm.status else None,
                    'start_date': cm.start_date.isoformat() if cm.start_date else None,
                    'end_date': cm.end_date.isoformat() if cm.end_date else None,
                    'is_owner': club.owner_id == user.id,
                    'is_admin': db.query(ClubAdmin).filter(
                        ClubAdmin.club_id == club.id,
                        ClubAdmin.admin_id == user.id
                    ).first() is not None
                })
        
        # Récupérer les clubs dont l'utilisateur est propriétaire
        owned_clubs = db.query(FanClub).filter(FanClub.owner_id == user.id).all()
        for club in owned_clubs:
            # Vérifier si déjà dans la liste
            if not any(c['id'] == club.id for c in clubs_list):
                clubs_list.append({
                    'id': club.id,
                    'name': club.name,
                    'slug': club.slug,
                    'description': club.description,
                    'membership_type': None,
                    'membership_status': None,
                    'start_date': None,
                    'end_date': None,
                    'is_owner': True,
                    'is_admin': True
                })
        
        # Récupérer les suggestions de contest (si le modèle a un user_id, sinon liste vide)
        # Note: Le modèle SuggestedContest n'a pas de user_id, donc on retourne une liste vide
        # Si vous avez besoin de cette fonctionnalité, il faudra ajouter user_id au modèle
        suggested_contests_list = []
        
        # Récupérer les reports (signalements faits par l'utilisateur et signalements sur l'utilisateur)
        reports_made = db.query(Report).filter(Report.reporter_id == user.id).order_by(Report.created_at.desc()).all()
        reports_made_list = []
        for r in reports_made:
            reports_made_list.append({
                'id': r.id,
                'reason': r.reason,
                'description': r.description,
                'status': r.status,
                'media_id': r.media_id,
                'contest_entry_id': r.contest_entry_id,
                'comment_id': r.comment_id,
                'user_id': r.user_id,
                'contestant_id': r.contestant_id,
                'contest_id': r.contest_id,
                'reviewed_by': r.reviewed_by,
                'reviewed_at': r.reviewed_at.isoformat() if r.reviewed_at else None,
                'created_at': r.created_at.isoformat() if r.created_at else None
            })
        
        reports_received = db.query(Report).filter(Report.user_id == user.id).order_by(Report.created_at.desc()).all()
        reports_received_list = []
        for r in reports_received:
            reports_received_list.append({
                'id': r.id,
                'reason': r.reason,
                'description': r.description,
                'status': r.status,
                'reporter_id': r.reporter_id,
                'reviewed_by': r.reviewed_by,
                'reviewed_at': r.reviewed_at.isoformat() if r.reviewed_at else None,
                'created_at': r.created_at.isoformat() if r.created_at else None
            })
        
        # Récupérer l'arbre d'affiliation sur 10 niveaux
        from app.crud import user as crud_user
        affiliate_tree_data = crud_user.get_all_referrals_multilevel(
            db=db,
            user_id=user.id,
            skip=0,
            limit=10000,  # Limite élevée pour récupérer tous les niveaux
            level_filter=None,
            status_filter=None,
            search_query=None,
            kyc_status_filter=None
        )
        
        # Organiser l'arbre par niveaux
        affiliate_tree_by_level = {}
        for level in range(1, 11):
            affiliate_tree_by_level[level] = [
                r for r in affiliate_tree_data.get('referrals', []) if r.get('level') == level
            ]
        
        return {
            'id': user.id,
            'email': user.email,
            'full_name': user.full_name,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'username': user.username,
            'avatar_url': user.avatar_url,
            'bio': user.bio,
            'is_active': user.is_active,
            'is_verified': user.is_verified,
            'is_admin': user.is_admin,
            'created_at': user.created_at,
            'date_of_birth': user.date_of_birth,
            'city': user.city,
            'country': user.country,
            'continent': user.continent,
            'region': user.region,
            'gender': user.gender.value if user.gender else None,
            'phone_number': user.phone_number,
            'kyc_status': 'verified' if user.identity_verified else 'pending',
            'kyc_verified_at': user.verification_date,
            'participations_count': participations_count,
            'prizes_count': prizes_count,
            'contestants_count': contestants_count,
            'contests_participated': contests_participated,
            'contests_list': contests_list,
            'contestants_list': contestants_list,
            'contest_comments': comments_list,
            'last_login': user.last_login,
            'deposits': deposits_list,
            'withdrawals': withdrawals_list,
            'role': role_info,
            'clubs': clubs_list,
            'suggested_contests': suggested_contests_list,
            'reports_made': reports_made_list,
            'reports_received': reports_received_list,
            'affiliate_tree': {
                'total_referrals': affiliate_tree_data.get('total', 0),
                'total_all_levels': affiliate_tree_data.get('total_all_levels', 0),
                'level_stats': affiliate_tree_data.get('level_stats', {}),
                'kyc_stats': affiliate_tree_data.get('kyc_stats', {}),
                'by_level': affiliate_tree_by_level
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"ERROR in get_user_details: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la récupération des détails: {str(e)}"
        )

@router.put("/users/{user_id}/role")
async def update_user_role(
    user_id: int,
    role_data: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Met à jour le rôle admin d'un utilisateur (admin uniquement)
    """
    check_admin(current_user)
    
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Utilisateur non trouvé"
            )
        
        user.is_admin = role_data.get('is_admin', user.is_admin)
        db.commit()
        db.refresh(user)
        
        return {
            'id': user.id,
            'is_admin': user.is_admin,
            'message': 'Rôle mis à jour avec succès'
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Erreur lors de la mise à jour du rôle: {str(e)}"
        )

@router.put("/users/{user_id}/status")
async def update_user_status(
    user_id: int,
    status_data: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Met à jour le statut actif d'un utilisateur (admin uniquement)
    """
    check_admin(current_user)
    
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Utilisateur non trouvé"
            )
        
        user.is_active = status_data.get('is_active', user.is_active)
        db.commit()
        db.refresh(user)
        
        return {
            'id': user.id,
            'is_active': user.is_active,
            'message': 'Statut mis à jour avec succès'
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Erreur lors de la mise à jour du statut: {str(e)}"
        )

@router.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Soft delete un utilisateur (admin uniquement)
    """
    check_admin(current_user)
    
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Utilisateur non trouvé"
            )
        
        user.is_deleted = True
        db.commit()
        
        return {
            'id': user.id,
            'is_deleted': user.is_deleted,
            'message': 'Utilisateur supprimé avec succès'
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Erreur lors de la suppression: {str(e)}"
        )

@router.get("/statistics")
async def get_admin_statistics(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Récupère les statistiques du dashboard admin
    """
    check_admin(current_user)
    
    try:
        from sqlalchemy import func
        
        # Statistiques des saisons
        total_seasons = db.query(ContestSeason).filter(ContestSeason.is_deleted == False).count()
        
        # Statistiques des contests
        total_contests = db.query(Contest).filter(Contest.is_deleted == False).count()
        active_contests = db.query(Contest).filter(Contest.is_deleted == False, Contest.is_active == True).count()
        inactive_contests = total_contests - active_contests
        
        # Statistiques des contestants
        total_contestants = db.query(Contestant).filter(Contestant.is_deleted == False).count()
        pending_contestants = db.query(Contestant).filter(
            Contestant.is_deleted == False,
            Contestant.verification_status == 'pending'
        ).count()
        verified_contestants = db.query(Contestant).filter(
            Contestant.is_deleted == False,
            Contestant.verification_status == 'verified'
        ).count()
        rejected_contestants = db.query(Contestant).filter(
            Contestant.is_deleted == False,
            Contestant.verification_status == 'rejected'
        ).count()
        
        # Statistiques des utilisateurs
        total_users = db.query(User).filter(User.is_deleted == False).count()
        active_users = db.query(User).filter(User.is_deleted == False, User.is_active == True).count()
        admin_users = db.query(User).filter(User.is_deleted == False, User.is_admin == True).count()
        verified_users = db.query(User).filter(User.is_deleted == False, User.is_verified == True).count()
        
        # Statistiques des votes (submissions)
        total_votes = db.query(ContestSubmission).count()
        
        # Statistiques des commentaires
        total_comments = db.query(Comment).filter(Comment.is_deleted == False).count()
        
        # Statistiques des rapports
        total_reports = db.query(Report).count()
        pending_reports = db.query(Report).filter(Report.status == 'pending').count()
        reviewed_reports = db.query(Report).filter(Report.status == 'reviewed').count()
        resolved_reports = db.query(Report).filter(Report.status == 'resolved').count()
        
        # Rapports par type
        # Rapports sur des contests (qui peuvent avoir des catégories)
        reports_by_contest = db.query(Report).filter(Report.contest_id.isnot(None)).count()
        reports_by_user = db.query(Report).filter(Report.user_id.isnot(None)).count()
        reports_by_contestant = db.query(Report).filter(Report.contestant_id.isnot(None)).count()
        reports_by_comment = db.query(Report).filter(Report.comment_id.isnot(None)).count()
        reports_by_media = db.query(Report).filter(Report.media_id.isnot(None)).count()
        
        # Rapports par catégorie (rapports sur des contests qui ont une catégorie)
        # On compte les rapports liés à des contests avec catégorie
        reports_by_category = db.query(Report).join(Contest).filter(
            Report.contest_id.isnot(None),
            Contest.category_id.isnot(None)
        ).count()
        
        # Statistiques des catégories
        total_categories = db.query(Category).filter(Category.is_active == True).count()
        
        # Catégories avec leurs statistiques
        categories_data = []
        categories = db.query(Category).filter(Category.is_active == True).all()
        for category in categories:
            contests_count = db.query(Contest).filter(
                Contest.category_id == category.id,
                Contest.is_deleted == False
            ).count()
            
            # Compter les utilisations (nombre de contests utilisant cette catégorie)
            categories_data.append({
                'name': category.name,
                'count': contests_count,
                'contests': contests_count
            })
        
        return {
            'seasons': {
                'total': total_seasons
            },
            'contests': {
                'total': total_contests,
                'active': active_contests,
                'inactive': inactive_contests
            },
            'contestants': {
                'total': total_contestants,
                'pending': pending_contestants,
                'verified': verified_contestants,
                'rejected': rejected_contestants
            },
            'users': {
                'total': total_users,
                'active': active_users,
                'admin': admin_users,
                'verified': verified_users
            },
            'votes': {
                'total': total_votes
            },
            'comments': {
                'total': total_comments
            },
            'reports': {
                'total': total_reports,
                'pending': pending_reports,
                'reviewed': reviewed_reports,
                'resolved': resolved_reports,
                'by_type': {
                    'category': reports_by_category,
                    'contest': reports_by_contest,
                    'user': reports_by_user,
                    'contestant': reports_by_contestant,
                    'comment': reports_by_comment,
                    'media': reports_by_media
                }
            },
            'categories': {
                'total': total_categories,
                'chart_data': categories_data
            }
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la récupération des statistiques: {str(e)}"
        )

@router.get("/reports")
async def get_reports(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    skip: int = 0,
    limit: int = 100,
    status: Optional[str] = Query(None, description="Filtrer par statut (pending, reviewed, resolved)"),
):
    """
    Récupère tous les reports avec les informations enrichies (contestant, auteur, reporter)
    """
    check_admin(current_user)
    
    try:
        query = db.query(Report)
        
        if status:
            query = query.filter(Report.status == status)
        
        # Filtrer uniquement les reports sur des contestants
        query = query.filter(Report.contestant_id.isnot(None))
        
        reports = query.order_by(Report.created_at.desc()).offset(skip).limit(limit).all()
        
        result = []
        for report in reports:
            # Récupérer le contestant
            contestant = db.query(Contestant).filter(Contestant.id == report.contestant_id).first()
            
            # Récupérer l'auteur du contestant
            author = None
            if contestant:
                author = db.query(User).filter(User.id == contestant.user_id).first()
            
            # Récupérer le reporter
            reporter = db.query(User).filter(User.id == report.reporter_id).first()
            
            # Récupérer le contest si disponible
            contest = None
            if report.contest_id:
                contest = db.query(Contest).filter(Contest.id == report.contest_id).first()
            
            result.append({
                'id': report.id,
                'reason': report.reason,
                'description': report.description,
                'status': report.status,
                'created_at': report.created_at.isoformat() if report.created_at else None,
                'reviewed_at': report.reviewed_at.isoformat() if report.reviewed_at else None,
                'reviewed_by': report.reviewed_by,
                'moderator_notes': report.moderator_notes,
                'contestant': {
                    'id': contestant.id if contestant else None,
                    'title': contestant.title if contestant else None,
                    'description': contestant.description if contestant else None,
                    'verification_status': contestant.verification_status if contestant else None,
                } if contestant else None,
                'author': {
                    'id': author.id if author else None,
                    'username': author.username if author else None,
                    'full_name': author.full_name if author else None,
                    'email': author.email if author else None,
                    'avatar_url': author.avatar_url if author else None,
                    'city': author.city if author else None,
                    'country': author.country if author else None,
                    'is_verified': author.is_verified if author else None,
                } if author else None,
                'reporter': {
                    'id': reporter.id if reporter else None,
                    'username': reporter.username if reporter else None,
                    'full_name': reporter.full_name if reporter else None,
                    'email': reporter.email if reporter else None,
                    'avatar_url': reporter.avatar_url if reporter else None,
                } if reporter else None,
                'contest': {
                    'id': contest.id if contest else None,
                    'name': contest.name if contest else None,
                } if contest else None,
            })
        
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la récupération des reports: {str(e)}"
        )

@router.get("/suggested-contests")
async def get_suggested_contests(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    skip: int = 0,
    limit: int = 100,
    status: Optional[str] = Query(None, description="Filtrer par statut (pending, approved, rejected)"),
):
    """
    Récupère toutes les suggestions de concours avec les informations de l'auteur
    """
    check_admin(current_user)
    
    try:
        from app.models.contest import SuggestedContest, SuggestedContestStatus
        
        query = db.query(SuggestedContest)
        
        if status:
            try:
                status_enum = SuggestedContestStatus(status)
                query = query.filter(SuggestedContest.status == status_enum)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Statut invalide: {status}"
                )
        
        suggestions = query.order_by(SuggestedContest.created_at.desc()).offset(skip).limit(limit).all()
        
        result = []
        for suggestion in suggestions:
            # Vérifier si le modèle a un user_id (peut être ajouté plus tard)
            author = None
            if hasattr(suggestion, 'user_id') and suggestion.user_id:
                author_user = db.query(User).filter(User.id == suggestion.user_id).first()
                if author_user:
                    author = {
                        'id': author_user.id,
                        'username': author_user.username,
                        'full_name': author_user.full_name,
                        'email': author_user.email,
                        'avatar_url': author_user.avatar_url,
                        'city': author_user.city,
                        'country': author_user.country,
                        'is_verified': author_user.is_verified,
                    }
            
            # SuggestedContest hérite de Base, donc il a id, created_at, updated_at
            result.append({
                'id': suggestion.id,
                'name': suggestion.name,
                'description': suggestion.description,
                'category': suggestion.category,
                'status': suggestion.status.value if hasattr(suggestion.status, 'value') else str(suggestion.status),
                'created_at': suggestion.created_at.isoformat() if suggestion.created_at else None,
                'updated_at': suggestion.updated_at.isoformat() if suggestion.updated_at else None,
                'author': author,
            })
        
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la récupération des suggestions: {str(e)}"
        )

@router.get("/statistics/user-progress")
async def get_user_progress_statistics(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    days: int = 7,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
):
    """
    Récupère les données de progression des utilisateurs pour le graphique
    Retourne les statistiques des 7 derniers jours par défaut
    """
    check_admin(current_user)
    
    try:
        from sqlalchemy import func, cast, Date
        from datetime import datetime, timedelta, date
        
        # Calculer la date de début et de fin
        if start_date and end_date:
            start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
            end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date()
            days = (end_date_obj - start_date_obj).days + 1
        else:
            end_date_obj = date.today()
            start_date_obj = end_date_obj - timedelta(days=days - 1)
        
        # Initialiser les données
        progress_data = []
        
        # Pour chaque jour dans la période
        for i in range(days):
            current_date = start_date_obj + timedelta(days=i)
            next_date = current_date + timedelta(days=1)
            
            # Convertir current_date en datetime pour la comparaison
            current_datetime_start = datetime.combine(current_date, datetime.min.time())
            current_datetime_end = datetime.combine(current_date, datetime.max.time())
            
            # Total d'utilisateurs jusqu'à ce jour
            total_users = db.query(User).filter(
                User.is_deleted == False,
                User.created_at <= current_datetime_end
            ).count()
            
            # Utilisateurs actifs (qui se sont connectés dans les 30 derniers jours)
            active_threshold = current_datetime_start - timedelta(days=30)
            active_users = db.query(User).filter(
                User.is_deleted == False,
                User.created_at <= current_datetime_end,
                User.last_login.isnot(None),
                User.last_login >= active_threshold
            ).count()
            
            # Nouveaux utilisateurs ce jour-là
            new_users = db.query(User).filter(
                User.is_deleted == False,
                User.created_at >= current_datetime_start,
                User.created_at <= current_datetime_end
            ).count()
            
            progress_data.append({
                'date': current_date.strftime('%d/%m'),
                'total': total_users,
                'active': active_users,
                'new': new_users
            })
        
        return progress_data
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la récupération des statistiques de progression: {str(e)}"
        )

@router.get("/statistics/deposits")
async def get_deposits_statistics(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    days: int = 30,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
):
    """
    Récupère les statistiques des dépôts pour le graphique
    """
    check_admin(current_user)
    
    try:
        from sqlalchemy import func, cast, Date
        from datetime import datetime, timedelta, date
        from app.models.payment import Deposit, DepositStatus
        
        # Calculer la date de début et de fin
        if start_date and end_date:
            start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
            end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date()
            days = (end_date_obj - start_date_obj).days + 1
        else:
            end_date_obj = date.today()
            start_date_obj = end_date_obj - timedelta(days=days - 1)
        
        # Total des dépôts validés
        total_amount = db.query(func.sum(Deposit.amount)).filter(
            Deposit.status == DepositStatus.VALIDATED
        ).scalar() or 0
        
        total_count = db.query(Deposit).filter(
            Deposit.status == DepositStatus.VALIDATED
        ).count()
        
        # Données pour le graphique (par jour)
        chart_data = []
        for i in range(days):
            current_date = start_date_obj + timedelta(days=i)
            next_date = current_date + timedelta(days=1)
            
            current_datetime_start = datetime.combine(current_date, datetime.min.time())
            current_datetime_end = datetime.combine(current_date, datetime.max.time())
            
            # Dépôts validés ce jour-là
            day_deposits = db.query(Deposit).filter(
                Deposit.status == DepositStatus.VALIDATED,
                Deposit.validated_at >= current_datetime_start,
                Deposit.validated_at < current_datetime_end
            ).all()
            
            day_amount = sum(float(d.amount) for d in day_deposits)
            day_count = len(day_deposits)
            
            chart_data.append({
                'date': current_date.strftime('%d/%m'),
                'amount': float(day_amount),
                'count': day_count
            })
        
        return {
            'total_amount': float(total_amount),
            'total_count': total_count,
            'chart_data': chart_data
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la récupération des statistiques de dépôts: {str(e)}"
        )

@router.get("/statistics/withdrawals")
async def get_withdrawals_statistics(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    days: int = 30,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
):
    """
    Récupère les statistiques des retraits pour le graphique
    """
    check_admin(current_user)
    
    try:
        from sqlalchemy import func, cast, Date
        from datetime import datetime, timedelta, date
        from app.models.transaction import UserTransaction, TransactionType, TransactionStatus
        
        # Calculer la date de début et de fin
        if start_date and end_date:
            start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
            end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date()
            days = (end_date_obj - start_date_obj).days + 1
        else:
            end_date_obj = date.today()
            start_date_obj = end_date_obj - timedelta(days=days - 1)
        
        # Total des retraits validés
        total_amount = db.query(func.sum(UserTransaction.amount)).filter(
            UserTransaction.transaction_type == TransactionType.WITHDRAWAL,
            UserTransaction.status == TransactionStatus.COMPLETED
        ).scalar() or 0
        
        total_count = db.query(UserTransaction).filter(
            UserTransaction.transaction_type == TransactionType.WITHDRAWAL,
            UserTransaction.status == TransactionStatus.COMPLETED
        ).count()
        
        # Données pour le graphique (par jour)
        chart_data = []
        for i in range(days):
            current_date = start_date_obj + timedelta(days=i)
            next_date = current_date + timedelta(days=1)
            
            current_datetime_start = datetime.combine(current_date, datetime.min.time())
            current_datetime_end = datetime.combine(current_date, datetime.max.time())
            
            # Retraits validés ce jour-là
            day_withdrawals = db.query(UserTransaction).filter(
                UserTransaction.transaction_type == TransactionType.WITHDRAWAL,
                UserTransaction.status == TransactionStatus.COMPLETED,
                UserTransaction.processed_at >= current_datetime_start,
                UserTransaction.processed_at < current_datetime_end
            ).all()
            
            day_amount = sum(float(w.amount) for w in day_withdrawals)
            day_count = len(day_withdrawals)
            
            chart_data.append({
                'date': current_date.strftime('%d/%m'),
                'amount': float(day_amount),
                'count': day_count
            })
        
        return {
            'total_amount': float(total_amount),
            'total_count': total_count,
            'chart_data': chart_data
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la récupération des statistiques de retraits: {str(e)}"
        )

@router.put("/users/{user_id}/kyc/verify")
async def verify_user_kyc(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Vérifie le KYC d'un utilisateur (admin uniquement)
    """
    check_admin(current_user)
    
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Utilisateur non trouvé"
            )
        
        user.identity_verified = True
        user.verification_date = datetime.utcnow()
        db.commit()
        db.refresh(user)
        
        return {
            'id': user.id,
            'identity_verified': user.identity_verified,
            'verification_date': user.verification_date,
            'message': 'KYC vérifié avec succès'
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Erreur lors de la vérification du KYC: {str(e)}"
        )

@router.put("/users/{user_id}/kyc/unverify")
async def unverify_user_kyc(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Révoque la vérification KYC d'un utilisateur (admin uniquement)
    """
    check_admin(current_user)
    
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Utilisateur non trouvé"
            )
        
        user.identity_verified = False
        user.verification_date = None
        db.commit()
        db.refresh(user)
        
        return {
            'id': user.id,
            'identity_verified': user.identity_verified,
            'verification_date': user.verification_date,
            'message': 'Vérification KYC révoquée'
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Erreur lors de la révocation du KYC: {str(e)}"
        )


# Modèles de réponse pour les transactions
class TransactionEnriched(BaseModel):
    id: int
    type: str  # "deposit", "withdrawal", "entry_fee", "prize_payout", "commission", "refund"
    amount: float
    currency: str
    status: str
    description: Optional[str] = None
    reference: Optional[str] = None
    created_at: str
    processed_at: Optional[str] = None
    user: Optional[Dict[str, Any]] = None
    contest: Optional[Dict[str, Any]] = None
    payment_method: Optional[str] = None
    # Pour les dépôts
    product_type: Optional[str] = None
    order_id: Optional[str] = None
    external_payment_id: Optional[str] = None
    tx_hash: Optional[str] = None
    validated_at: Optional[str] = None
    validated_by: Optional[int] = None


@router.get("/transactions", response_model=List[TransactionEnriched])
async def get_all_transactions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    transaction_type: Optional[str] = Query(None, description="Filtrer par type (deposit, withdrawal, entry_fee, prize_payout, commission, refund)"),
    status: Optional[str] = Query(None, description="Filtrer par statut"),
    user_id: Optional[int] = Query(None, description="Filtrer par utilisateur"),
    search: Optional[str] = Query(None, description="Rechercher par référence, description, email ou username"),
    skip: int = 0,
    limit: int = 100
):
    """
    Récupère toutes les transactions (dépôts, retraits, et autres transactions) avec des informations enrichies (admin uniquement).
    """
    check_admin(current_user)
    
    try:
        from sqlalchemy import or_, func
        from app.models.payment import Deposit, DepositStatus, ProductType
        from app.models.transaction import UserTransaction, TransactionType, TransactionStatus
        
        all_transactions = []
        
        # Récupérer les dépôts
        deposits_query = db.query(Deposit).options(
            joinedload(Deposit.user),
            joinedload(Deposit.product_type),
            joinedload(Deposit.payment_method)
        )
        
        if transaction_type and transaction_type != "deposit":
            pass  # Ne pas inclure les dépôts
        elif transaction_type is None or transaction_type == "deposit":
            if status:
                try:
                    deposit_status = DepositStatus(status)
                    deposits_query = deposits_query.filter(Deposit.status == deposit_status)
                except ValueError:
                    pass
            
            if user_id:
                deposits_query = deposits_query.filter(Deposit.user_id == user_id)
            
            if search:
                search_term = f"%{search.lower()}%"
                from app.models.user import User as UserModel
                deposits_query = deposits_query.join(UserModel).filter(
                    or_(
                        func.lower(Deposit.order_id).like(search_term),
                        func.lower(Deposit.external_payment_id).like(search_term),
                        func.lower(UserModel.email).like(search_term),
                        func.lower(UserModel.username).like(search_term)
                    )
                )
            
            deposits = deposits_query.order_by(Deposit.created_at.desc()).offset(skip).limit(limit).all()
            
            for deposit in deposits:
                all_transactions.append({
                    "id": deposit.id,
                    "type": "deposit",
                    "amount": float(deposit.amount),
                    "currency": deposit.currency,
                    "status": deposit.status.value,
                    "description": f"Dépôt - {deposit.product_type.name if deposit.product_type else 'N/A'}",
                    "reference": deposit.order_id,
                    "created_at": deposit.created_at.isoformat() if deposit.created_at else None,
                    "processed_at": deposit.validated_at.isoformat() if deposit.validated_at else None,
                    "user": {
                        "id": deposit.user.id,
                        "username": deposit.user.username,
                        "email": deposit.user.email,
                        "full_name": deposit.user.full_name,
                        "avatar_url": deposit.user.avatar_url
                    } if deposit.user else None,
                    "contest": None,
                    "payment_method": deposit.payment_method.name if deposit.payment_method else None,
                    "product_type": deposit.product_type.name if deposit.product_type else None,
                    "order_id": deposit.order_id,
                    "external_payment_id": deposit.external_payment_id,
                    "tx_hash": deposit.tx_hash,
                    "validated_at": deposit.validated_at.isoformat() if deposit.validated_at else None,
                    "validated_by": deposit.validated_by
                })
        
        # Récupérer les transactions utilisateur (retraits, frais d'entrée, etc.)
        transactions_query = db.query(UserTransaction).options(
            joinedload(UserTransaction.user),
            joinedload(UserTransaction.contest)
        )
        
        if transaction_type and transaction_type != "deposit":
            try:
                trans_type = TransactionType(transaction_type)
                transactions_query = transactions_query.filter(UserTransaction.transaction_type == trans_type)
            except ValueError:
                pass
        elif transaction_type is None:
            # Inclure tous les types sauf deposit (déjà géré)
            transactions_query = transactions_query.filter(UserTransaction.transaction_type != TransactionType.DEPOSIT)
        
        if status:
            try:
                trans_status = TransactionStatus(status)
                transactions_query = transactions_query.filter(UserTransaction.status == trans_status)
            except ValueError:
                pass
        
        if user_id:
            transactions_query = transactions_query.filter(UserTransaction.user_id == user_id)
        
        if search:
            search_term = f"%{search.lower()}%"
            from app.models.user import User as UserModel
            transactions_query = transactions_query.join(UserModel).filter(
                or_(
                    func.lower(UserTransaction.reference).like(search_term),
                    func.lower(UserTransaction.description).like(search_term),
                    func.lower(UserModel.email).like(search_term),
                    func.lower(UserModel.username).like(search_term)
                )
            )
        
        transactions = transactions_query.order_by(UserTransaction.created_at.desc()).offset(skip).limit(limit).all()
        
        for transaction in transactions:
            all_transactions.append({
                "id": transaction.id,
                "type": transaction.transaction_type.value,
                "amount": float(transaction.amount),
                "currency": transaction.currency,
                "status": transaction.status.value,
                "description": transaction.description,
                "reference": transaction.reference,
                "created_at": transaction.created_at.isoformat() if transaction.created_at else None,
                "processed_at": transaction.processed_at.isoformat() if transaction.processed_at else None,
                "user": {
                    "id": transaction.user.id,
                    "username": transaction.user.username,
                    "email": transaction.user.email,
                    "full_name": transaction.user.full_name,
                    "avatar_url": transaction.user.avatar_url
                } if transaction.user else None,
                "contest": {
                    "id": transaction.contest.id,
                    "name": transaction.contest.name
                } if transaction.contest else None,
                "payment_method": transaction.payment_method,
                "product_type": None,
                "order_id": None,
                "external_payment_id": transaction.payment_reference,
                "tx_hash": None,
                "validated_at": None,
                "validated_by": None
            })
        
        # Trier toutes les transactions par date de création (plus récentes en premier)
        all_transactions.sort(key=lambda x: x.get("created_at") or "1970-01-01T00:00:00", reverse=True)
        
        # Appliquer skip et limit sur le résultat final
        return all_transactions[skip:skip + limit]
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la récupération des transactions: {str(e)}"
        )
