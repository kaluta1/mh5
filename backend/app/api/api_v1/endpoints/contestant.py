from typing import List, Optional, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query

from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.api import deps
from app.crud import contestant as crud_contestant
from app.models.user import User
from app.models.contests import Contestant, ContestSubmission, ContestSeason, ContestStage, ContestantSeason, SeasonLevel
from app.models.voting import MyFavorites, Vote, ContestantReaction, ContestantShare, ReactionType
from app.schemas.voting import (
    ReactionCreate, Reaction, ReactionStats, ReactionDetails, ReactionUserDetail,
    VoteDetails, VoteUserDetail,
    FavoriteDetails, FavoriteUserDetail,
    ShareCreate, Share, ShareStats
)
from app.schemas.contestant import (
    ContestantCreate, ContestantResponse, ContestantListResponse, ContestantSubmissionResponse,
    ContestantWithAuthorAndStats
)
from app.services.content_moderation import content_moderation_service, ContentType
from app.services.content_relevance import content_relevance_service

router = APIRouter()


# Routes spécifiques d'abord (avant les routes génériques avec {id})
# IMPORTANT: Les routes plus spécifiques DOIVENT venir avant les routes générales

@router.get("/user/my-entries", response_model=List[ContestantListResponse])
def get_my_contestants(
    *,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000)
) -> List[ContestantListResponse]:
    """Récupère les candidatures de l'utilisateur connecté"""
    contestants = crud_contestant.get_multi_by_user(
        db, current_user.id, skip=skip, limit=limit
    )
    
    result = []
    for contestant in contestants:
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
    limit: int = Query(100, ge=1, le=1000)
) -> List[ContestantListResponse]:
    """Récupère le classement d'un concours"""
    # Vérifier que la saison existe
    season = db.query(ContestSeason).filter(ContestSeason.id == contest_id).first()
    if not season:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Concours non trouvé"
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
    limit: int = Query(100, ge=1, le=1000),
    current_user: Optional[User] = Depends(deps.get_current_active_user_optional)
) -> List[ContestantWithAuthorAndStats]:
    """Récupère les candidatures d'un concours avec infos auteur et stats enrichies"""
    # Essayer d'abord de trouver une ContestSeason avec cet ID
    season = db.query(ContestSeason).filter(ContestSeason.id == contest_id).first()
    
    # Si pas trouvé, chercher dans la table Contest
    if not season:
        from app.models.contest import Contest as MyfavContest
        contest = db.query(MyfavContest).filter(MyfavContest.id == contest_id).first()
        if not contest:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Concours non trouvé"
            )
    
    # Utiliser la nouvelle méthode avec stats enrichies
    contestants_data = crud_contestant.get_multi_by_season_with_stats(
        db, contest_id, current_user_id=current_user.id if current_user else None,
        skip=skip, limit=limit
    )
    
    # Log pour vérifier les données
    if contestants_data and len(contestants_data) > 0:
        first_contestant = contestants_data[0]
        print(f"[ContestantEndpoint] First contestant data: id={first_contestant.get('id')}, image_media_ids={first_contestant.get('image_media_ids')}, video_media_ids={first_contestant.get('video_media_ids')}")
    
    # Convertir en schéma Pydantic
    result = [ContestantWithAuthorAndStats(**data) for data in contestants_data]
    
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
                detail="Concours non trouvé"
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
                    detail="Votre profil ne contient pas d'information de genre. Veuillez compléter votre profil pour participer à ce concours."
                )
            
            # Récupérer le genre de l'utilisateur de manière sécurisée
            user_gender = current_user.gender.value.lower() if hasattr(current_user.gender, 'value') else str(current_user.gender).lower()
            gender_restriction_lower = gender_restriction.lower()
            
            # Vérifier la correspondance : si le contest est MALE_ONLY, seuls les hommes peuvent participer
            # Si le contest est FEMALE_ONLY, seules les femmes peuvent participer
            if gender_restriction_lower == 'male' and user_gender != 'male':
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Ce concours est réservé aux participants masculins uniquement."
                )
            elif gender_restriction_lower == 'female' and user_gender != 'female':
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Ce concours est réservé aux participantes féminines uniquement."
                )
    
    # Vérifier que l'utilisateur n'a pas déjà une candidature
    existing = crud_contestant.get_by_season_and_user(
        db, season_id, current_user.id
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vous avez déjà une candidature pour ce concours"
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
            detail=f"Contenu textuel rejeté: {flags_desc}"
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
                                detail=f"Image rejetée par la modération: {flags_desc}"
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
                                detail=f"Vidéo rejetée par la modération: {flags_desc}"
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
            detail=f"Candidature non pertinente pour ce concours. {suggestions_text}"
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
        city_season = SeasonMigrationService.get_or_create_season(
            db, 
            level=SeasonLevel.CITY,
            title="Saison City"
        )
        
        # Créer la candidature
        contestant = crud_contestant.create(
            db, 
            user_id=current_user.id,
            season_id=season_id,
            title=contestant_data.title,
            description=contestant_data.description,
            image_media_ids=contestant_data.image_media_ids,
            video_media_ids=contestant_data.video_media_ids
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
            detail=f"Erreur lors de la création de la candidature: {str(e)}"
        )
    
    return ContestantSubmissionResponse(
        id=contestant.id,
        season_id=contestant.season_id,
        user_id=contestant.user_id,
        title=contestant.title,
        description=contestant.description,
        registration_date=contestant.registration_date,
        message="Candidature créée avec succès."
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
            detail="Candidature non trouvée"
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
            detail="Candidature non trouvée"
        )
    
    # Vérifier que c'est le propriétaire
    if contestant.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vous ne pouvez ajouter une soumission que pour votre propre candidature"
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
    
    return {"message": "Soumission ajoutée avec succès", "submission_id": submission.id}


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
            detail="Contestant non trouvé"
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
            detail="Ce contestant est déjà dans vos favoris"
        )
    
    # Vérifier la limite de 5 favoris
    favorites_count = db.query(MyFavorites).filter(
        MyFavorites.user_id == current_user.id
    ).count()
    
    if favorites_count >= 5:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vous avez atteint la limite de 5 favoris"
        )
    
    # Ajouter aux favoris
    favorite = MyFavorites(
        user_id=current_user.id,
        contestant_id=contestant_id
    )
    db.add(favorite)
    db.commit()
    
    return {"message": f"Contestant ajouté aux favoris"}


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
            detail="Contestant non trouvé"
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
            detail="Ce contestant n'est pas dans vos favoris"
        )
    
    db.delete(favorite)
    db.commit()
    
    return {"message": "Contestant retiré des favoris"}


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
            detail="Candidature non trouvée"
        )
    
    # Vérifier que c'est le propriétaire
    if contestant.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vous ne pouvez mettre à jour que votre propre candidature"
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
            detail=f"Contenu textuel rejeté: {flags_desc}"
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
                                detail=f"Image rejetée par la modération: {flags_desc}"
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
                                detail=f"Vidéo rejetée par la modération: {flags_desc}"
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
            detail=f"Candidature non pertinente pour ce concours. {suggestions_text}"
        )
    
    # Mettre à jour la candidature
    updated_contestant = crud_contestant.update(
        db,
        id=contestant_id,
        title=contestant_data.title,
        description=contestant_data.description,
        image_media_ids=contestant_data.image_media_ids,
        video_media_ids=contestant_data.video_media_ids
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
            detail="Candidature non trouvée"
        )
    
    # Vérifier que la candidature n'est pas déjà supprimée
    if contestant.is_deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidature déjà supprimée"
        )
    
    # Vérifier que c'est le propriétaire ou un admin
    if contestant.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vous ne pouvez supprimer que votre propre candidature"
        )
    
    # Vérifier que les soumissions sont encore ouvertes (optionnel, mais recommandé)
    # On peut permettre la suppression même si les soumissions sont fermées
    
    success = crud_contestant.delete(db, id=contestant_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors de la suppression de la candidature"
        )
    
    return {"message": "Candidature supprimée avec succès"}


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
            detail="Candidature non trouvée"
        )
    
    # Vérifier que l'utilisateur ne vote pas pour sa propre candidature
    if contestant.user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vous ne pouvez pas voter pour votre propre candidature"
        )
    
    # Vérifier si le vote est autorisé
    # Récupérer le contest associé via la saison
    from app.models.contests import ContestSeasonLink, ContestSeason
    from app.models.contest import Contest as MyfavContest
    
    contest = None
    season = None
    
    # Vérifier si season_id est directement un Contest.id
    contest = db.query(MyfavContest).filter(
        MyfavContest.id == contestant.season_id,
        MyfavContest.is_deleted == False
    ).first()
    
    # Si pas trouvé, chercher via ContestSeasonLink
    if not contest:
        # Vérifier si season_id est une ContestSeason
        season = db.query(ContestSeason).filter(
            ContestSeason.id == contestant.season_id,
            ContestSeason.is_deleted == False
        ).first()
        
        if season:
            # Trouver le contest via ContestSeasonLink
            contest_link = db.query(ContestSeasonLink).filter(
                ContestSeasonLink.season_id == season.id,
                ContestSeasonLink.is_active == True
            ).first()
            
            if contest_link:
                contest = db.query(MyfavContest).filter(
                    MyfavContest.id == contest_link.contest_id,
                    MyfavContest.is_deleted == False
                ).first()
        else:
            # Si season_id n'est ni un Contest ni une ContestSeason, chercher via ContestSeasonLink inverse
            contest_season_link = db.query(ContestSeasonLink).filter(
                ContestSeasonLink.contest_id == contestant.season_id,
                ContestSeasonLink.is_active == True
            ).first()
            
            if contest_season_link:
                season = db.query(ContestSeason).filter(
                    ContestSeason.id == contest_season_link.season_id,
                    ContestSeason.is_deleted == False
                ).first()
                
                if season:
                    contest = db.query(MyfavContest).filter(
                        MyfavContest.id == contest_season_link.contest_id,
                        MyfavContest.is_deleted == False
                    ).first()
    
    # Vérifier que le contest existe et que le vote est autorisé
    if not contest:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Aucun concours trouvé pour cette candidature"
        )
    
    # Vérifier que le vote est ouvert pour ce contest
    is_allowed, error_message = contest_status_service.check_voting_allowed(db, contest.id)
    if not is_allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_message
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
                detail="Votre profil ne contient pas d'information de genre. Veuillez compléter votre profil pour voter dans ce concours."
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
                    detail="Ce concours est réservé aux participants masculins. Seules les participantes féminines peuvent voter."
                )
        elif gender_restriction_lower == 'female':
            # Contest réservé aux femmes pour participer, donc seuls les hommes peuvent voter
            if user_gender != 'male':
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Ce concours est réservé aux participantes féminines. Seuls les participants masculins peuvent voter."
                )
    
    # Vérifier si l'utilisateur a déjà voté pour ce contestant
    existing_vote = db.query(Vote).filter(
        Vote.voter_id == current_user.id,
        Vote.contestant_id == contestant_id
    ).first()
    
    if existing_vote:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vous avez déjà voté pour ce contestant"
        )
    
    # Récupérer le stage_id approprié pour cette saison
    # Le stage est nécessaire pour créer le vote
    # On récupère le stage via la saison du contestant
    stage = None
    
    # Si on a déjà la saison, l'utiliser
    if not season:
        # Sinon, récupérer la saison via ContestSeasonLink
        contest_season_link = db.query(ContestSeasonLink).filter(
            ContestSeasonLink.contest_id == contest.id,
            ContestSeasonLink.is_active == True
        ).first()
        
        if contest_season_link:
            season = db.query(ContestSeason).filter(
                ContestSeason.id == contest_season_link.season_id,
                ContestSeason.is_deleted == False
            ).first()
    
    # Récupérer le stage de la saison
    if season:
        stage = db.query(ContestStage).filter(
            ContestStage.season_id == season.id
        ).first()
    
    if not stage:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Aucune étape de concours trouvée pour cette saison"
        )
    
    # Créer un nouveau vote
    new_vote = Vote(
        voter_id=current_user.id,
        contestant_id=contestant_id,
        stage_id=stage.id,  # Utiliser le stage_id du stage trouvé
        rank_position=1,  # Position par défaut
        points=5  # Points par défaut
    )
    
    db.add(new_vote)
    db.commit()
    db.refresh(new_vote)
    
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
    
    return {"message": "Vote enregistré avec succès", "vote_id": new_vote.id}


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
            detail="Candidature non trouvée"
        )
    
    # Vérifier que le type de réaction est valide et le convertir en minuscules
    reaction_type_str = reaction_in.reaction_type.lower()
    try:
        reaction_type = ReactionType(reaction_type_str)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Type de réaction invalide. Types valides: {[e.value for e in ReactionType]}"
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
            detail="Candidature non trouvée"
        )
    
    # Trouver et supprimer la réaction
    reaction = db.query(ContestantReaction).filter(
        ContestantReaction.user_id == current_user.id,
        ContestantReaction.contestant_id == contestant_id
    ).first()
    
    if not reaction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Réaction non trouvée"
        )
    
    db.delete(reaction)
    db.commit()
    
    return {"message": "Réaction supprimée avec succès"}


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
            detail="Candidature non trouvée"
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
    """Enregistrer un partage de contestant"""
    # Vérifier que le contestant existe
    contestant = crud_contestant.get(db, contestant_id)
    if not contestant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidature non trouvée"
        )
    
    # Créer un nouveau partage
    new_share = ContestantShare(
        user_id=current_user.id if current_user else None,
        contestant_id=contestant_id,
        shared_by_user_id=share_in.shared_by_user_id or (current_user.id if current_user else None),
        share_link=share_in.share_link,
        platform=share_in.platform
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
    # Vérifier que le contestant existe
    contestant = crud_contestant.get(db, contestant_id)
    if not contestant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidature non trouvée"
        )
    
    # Compter les partages
    shares = db.query(ContestantShare).filter(
        ContestantShare.contestant_id == contestant_id
    ).all()
    
    # Compter par plateforme
    shares_by_platform = {}
    for share in shares:
        platform = share.platform or "other"
        shares_by_platform[platform] = shares_by_platform.get(platform, 0) + 1
    
    return ShareStats(
        contestant_id=contestant_id,
        total_shares=len(shares),
        shares_by_platform=shares_by_platform
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
            detail="Candidature non trouvée"
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
            detail="Candidature non trouvée"
        )
    
    # Récupérer tous les votes avec les utilisateurs
    votes = db.query(Vote).join(User, Vote.voter_id == User.id).filter(
        Vote.contestant_id == contestant_id
    ).order_by(Vote.vote_date.desc()).all()
    
    voters = [
        VoteUserDetail(
            user_id=vote.voter.id,
            username=vote.voter.username,
            full_name=vote.voter.full_name,
            avatar_url=vote.voter.avatar_url,
            points=vote.points,
            vote_date=vote.vote_date
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
            detail="Candidature non trouvée"
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
