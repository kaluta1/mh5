from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import IntegrityError
from psycopg2.errors import UniqueViolation
from app.db.base_class import Base
from app.api.deps import get_db, get_current_user
from app.models.user import User
from app.models.contest import Contest, ContestEntry
from app.models.contests import ContestSeason, ContestStage, ContestStageLevel, VotingRestriction, Contestant, ContestSubmission, SeasonLevel, ContestantSeason, ContestSeasonLink
from app.models.media import Media
from app.models.comment import Comment, Report
from pydantic import BaseModel
from typing import List, Optional, Dict, Any, Dict, Any
from datetime import datetime, timedelta

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
    image_url: Optional[str] = None
    voting_restriction: str = "none"

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
    voting_restriction: str
    participant_count: int
    approved_count: int
    pending_count: int
    created_at: datetime
    updated_at: datetime

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
        query = db.query(Contest).filter(Contest.is_deleted == False)
        
        if level:
            query = query.filter(Contest.level == level)
        if is_active is not None:
            query = query.filter(Contest.is_active == is_active)
        if contest_type:
            query = query.filter(Contest.contest_type == contest_type)
        
        contests = query.all()
        
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
                'is_active': contest.is_active,
                'is_submission_open': contest.is_submission_open,
                'is_voting_open': contest.is_voting_open,
                'submission_start_date': contest.submission_start_date,
                'submission_end_date': contest.submission_end_date,
                'voting_start_date': contest.voting_start_date,
                'voting_end_date': contest.voting_end_date,
                'image_url': contest.image_url,
                'voting_restriction': contest.voting_restriction.value if contest.voting_restriction else 'none',
                'participant_count': total,
                'approved_count': approved,
                'pending_count': pending,
                'created_at': contest.created_at,
                'updated_at': contest.updated_at
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
    
    contest = db.query(Contest).filter(Contest.id == contest_id, Contest.is_deleted == False).first()
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
        'voting_restriction': contest.voting_restriction.value if contest.voting_restriction else 'none',
        'participant_count': total,
        'approved_count': approved,
        'pending_count': pending,
        'created_at': contest.created_at,
        'updated_at': contest.updated_at
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
            voting_restriction=contest_data.voting_restriction
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
            'voting_restriction': new_contest.voting_restriction.value if new_contest.voting_restriction else 'none',
            'participant_count': total,
            'approved_count': approved,
            'pending_count': pending,
            'created_at': new_contest.created_at,
            'updated_at': new_contest.updated_at
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
        
        # Only update dates if provided
        if contest_data.submission_start_date:
            submission_start, submission_end, voting_start, voting_end = generate_contest_dates(
                contest_data.submission_start_date
            )
            contest.submission_start_date = submission_start
            contest.submission_end_date = submission_end
            contest.voting_start_date = voting_start
            contest.voting_end_date = voting_end
        
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
            'voting_restriction': contest.voting_restriction.value if contest.voting_restriction else 'none',
            'participant_count': total,
            'approved_count': approved,
            'pending_count': pending,
            'created_at': contest.created_at,
            'updated_at': contest.updated_at
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
        
        users = query.all()
        
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
            'last_login': user.last_login
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
                'resolved': resolved_reports
            }
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la récupération des statistiques: {str(e)}"
        )

@router.get("/statistics/user-progress")
async def get_user_progress_statistics(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    days: int = 7
):
    """
    Récupère les données de progression des utilisateurs pour le graphique
    Retourne les statistiques des 7 derniers jours par défaut
    """
    check_admin(current_user)
    
    try:
        from sqlalchemy import func, cast, Date
        from datetime import datetime, timedelta, date
        
        # Calculer la date de début
        end_date = date.today()
        start_date = end_date - timedelta(days=days - 1)
        
        # Initialiser les données
        progress_data = []
        
        # Pour chaque jour dans la période
        for i in range(days):
            current_date = start_date + timedelta(days=i)
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
