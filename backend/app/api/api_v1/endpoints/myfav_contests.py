from typing import List, Optional, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File
from sqlalchemy.orm import Session

from app.api import deps
from app.crud import crud_contests, crud_contestants
from app.schemas.contests import (
    ContestType, ContestTypeCreate, ContestTypeUpdate,
    ContestSeason, ContestSeasonCreate, ContestSeasonUpdate,
    ContestStage, ContestStageCreate,
    Contestant, ContestantCreate, ContestantProfile,
    ContestSubmission, ContestSubmissionCreate
)

router = APIRouter()


# Types de concours
@router.get("/types", response_model=List[ContestType])
def get_contest_types(
    db: Session = Depends(deps.get_db),
    skip: int = 0,
    limit: int = 100,
    is_active: Optional[bool] = None
):
    """
    Récupérer tous les types de concours disponibles.
    """
    contest_types = crud_contests.contest_type.get_multi_filtered(
        db=db, skip=skip, limit=limit, is_active=is_active
    )
    return contest_types


@router.get("/types/{contest_type_id}", response_model=ContestType)
def get_contest_type(
    contest_type_id: int,
    db: Session = Depends(deps.get_db)
):
    """
    Récupérer un type de concours par ID.
    """
    contest_type = crud_contests.contest_type.get(db=db, id=contest_type_id)
    if not contest_type:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Type de concours non trouvé"
        )
    return contest_type


@router.post("/types", response_model=ContestType, status_code=status.HTTP_201_CREATED)
def create_contest_type(
    *,
    db: Session = Depends(deps.get_db),
    contest_type_in: ContestTypeCreate,
    current_user = Depends(deps.get_current_active_superuser)
):
    """
    Créer un nouveau type de concours (admin seulement).
    """
    contest_type = crud_contests.contest_type.create(db=db, obj_in=contest_type_in)
    return contest_type


# Saisons de concours
@router.get("/types/{contest_type_id}/seasons", response_model=List[ContestSeason])
def get_contest_seasons(
    contest_type_id: int,
    db: Session = Depends(deps.get_db),
    skip: int = 0,
    limit: int = 10
):
    """
    Récupérer les saisons d'un type de concours.
    """
    seasons = crud_contests.contest_season.get_by_contest_type(
        db=db, contest_type_id=contest_type_id, skip=skip, limit=limit
    )
    return seasons


@router.get("/seasons/{season_id}", response_model=ContestSeason)
def get_contest_season(
    season_id: int,
    db: Session = Depends(deps.get_db)
):
    """
    Récupérer une saison de concours par ID.
    """
    season = crud_contests.contest_season.get(db=db, id=season_id)
    if not season:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Saison de concours non trouvée"
        )
    return season


@router.post("/seasons", response_model=ContestSeason, status_code=status.HTTP_201_CREATED)
def create_contest_season(
    *,
    db: Session = Depends(deps.get_db),
    season_in: ContestSeasonCreate,
    current_user = Depends(deps.get_current_active_superuser)
):
    """
    Créer une nouvelle saison de concours (admin seulement).
    """
    season = crud_contests.contest_season.create(db=db, obj_in=season_in)
    return season


# Étapes de concours
@router.get("/seasons/{season_id}/stages", response_model=List[ContestStage])
def get_contest_stages(
    season_id: int,
    db: Session = Depends(deps.get_db)
):
    """
    Récupérer toutes les étapes d'une saison de concours.
    """
    stages = crud_contests.contest_stage.get_by_season(db=db, season_id=season_id)
    return stages


@router.get("/stages/{stage_id}", response_model=ContestStage)
def get_contest_stage(
    stage_id: int,
    db: Session = Depends(deps.get_db)
):
    """
    Récupérer une étape de concours par ID.
    """
    stage = crud_contests.contest_stage.get(db=db, id=stage_id)
    if not stage:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Étape de concours non trouvée"
        )
    return stage


@router.get("/stages/{stage_id}/contestants", response_model=List[ContestantProfile])
def get_stage_contestants(
    stage_id: int,
    db: Session = Depends(deps.get_db),
    skip: int = 0,
    limit: int = 50
):
    """
    Récupérer tous les participants d'une étape de concours, triés par ranking.
    """
    contestants = crud_contestants.contestant.get_by_stage_ranked(
        db=db, stage_id=stage_id, skip=skip, limit=limit
    )
    return contestants


# Participation aux concours
@router.post("/register", response_model=Contestant, status_code=status.HTTP_201_CREATED)
def register_for_contest(
    *,
    db: Session = Depends(deps.get_db),
    contestant_in: ContestantCreate,
    current_user = Depends(deps.get_current_active_user)
):
    """
    S'inscrire à un concours.
    """
    # Vérifier si l'utilisateur peut s'inscrire
    eligibility = crud_contestants.contestant.check_registration_eligibility(
        db=db,
        user_id=current_user.id,
        season_id=contestant_in.season_id,
        category_id=contestant_in.category_id
    )
    
    if not eligibility["eligible"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=eligibility["reason"]
        )
    
    contestant = crud_contestants.contestant.create_with_user(
        db=db, obj_in=contestant_in, user_id=current_user.id
    )
    return contestant


@router.get("/contestants/{contestant_id}", response_model=ContestantProfile)
def get_contestant_profile(
    contestant_id: int,
    db: Session = Depends(deps.get_db)
):
    """
    Récupérer le profil complet d'un participant.
    """
    contestant = crud_contestants.contestant.get_with_profile(db=db, id=contestant_id)
    if not contestant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Participant non trouvé"
        )
    return contestant


@router.post("/contestants/{contestant_id}/submit", response_model=ContestSubmission, status_code=status.HTTP_201_CREATED)
def submit_content(
    *,
    db: Session = Depends(deps.get_db),
    contestant_id: int,
    submission_in: ContestSubmissionCreate,
    current_user = Depends(deps.get_current_active_user)
):
    """
    Soumettre du contenu pour un concours (vidéo, image, lien externe).
    """
    # Vérifier que l'utilisateur est propriétaire du participant
    contestant = crud_contestants.contestant.get(db=db, id=contestant_id)
    if not contestant or contestant.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission insuffisante"
        )
    
    # Vérifier si la période de soumission est ouverte
    if not crud_contestants.contestant.is_submission_period_open(db=db, contestant_id=contestant_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La période de soumission est fermée"
        )
    
    submission = crud_contestants.contest_submission.create_with_contestant(
        db=db, obj_in=submission_in, contestant_id=contestant_id
    )
    return submission


@router.post("/contestants/{contestant_id}/upload-media")
def upload_media_content(
    *,
    db: Session = Depends(deps.get_db),
    contestant_id: int,
    file: UploadFile = File(...),
    title: Optional[str] = None,
    description: Optional[str] = None,
    current_user = Depends(deps.get_current_active_user)
):
    """
    Uploader un fichier média pour un concours.
    """
    # Vérifier que l'utilisateur est propriétaire du participant
    contestant = crud_contestants.contestant.get(db=db, id=contestant_id)
    if not contestant or contestant.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission insuffisante"
        )
    
    # Traitement de l'upload (à implémenter avec le service de stockage)
    result = crud_contestants.contest_submission.handle_media_upload(
        db=db,
        contestant_id=contestant_id,
        file=file,
        title=title,
        description=description
    )
    
    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result["error"]
        )
    
    return result["submission"]


@router.get("/my-participations", response_model=List[Contestant])
def get_my_participations(
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_active_user),
    skip: int = 0,
    limit: int = 20
):
    """
    Récupérer toutes les participations de l'utilisateur connecté.
    """
    participations = crud_contestants.contestant.get_by_user(
        db=db, user_id=current_user.id, skip=skip, limit=limit
    )
    return participations


@router.get("/search/contestants")
def search_contestants(
    q: str = Query(..., min_length=2),
    contest_type_id: Optional[int] = None,
    stage_id: Optional[int] = None,
    db: Session = Depends(deps.get_db),
    limit: int = 20
):
    """
    Rechercher des participants par nom.
    """
    contestants = crud_contestants.contestant.search_by_name(
        db=db,
        query=q,
        contest_type_id=contest_type_id,
        stage_id=stage_id,
        limit=limit
    )
    return contestants


@router.post("/recommend-contest", status_code=status.HTTP_201_CREATED)
def recommend_new_contest(
    *,
    db: Session = Depends(deps.get_db),
    recommendation: dict,  # {"name": str, "description": str, "justification": str}
    current_user = Depends(deps.get_current_active_user)
):
    """
    Recommander un nouveau type de concours.
    """
    result = crud_contests.contest_recommendation.create_recommendation(
        db=db,
        user_id=current_user.id,
        name=recommendation["name"],
        description=recommendation["description"],
        justification=recommendation["justification"]
    )
    
    return {"message": "Recommandation soumise avec succès", "id": result.id}
