from typing import Any, List
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.crud import contest
from app.db.session import get_db
from app.schemas.contest import Contest, ContestCreate, ContestUpdate, ContestWithEntries

router = APIRouter()

@router.post("/", response_model=Contest, status_code=status.HTTP_201_CREATED)
def create_contest(
    *,
    db: Session = Depends(get_db),
    contest_in: ContestCreate,
    current_user: Any = Depends(get_current_active_user),
) -> Any:
    """
    Créer un nouveau concours.
    """
    # Seuls les administrateurs peuvent créer des concours
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission insuffisante pour créer un concours"
        )
    
    new_contest = contest.create(db=db, obj_in=contest_in)
    return new_contest

@router.get("/", response_model=List[Contest])
def read_contests(
    *,
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
    location_id: int = None,
    contest_type: str = None,
    active: bool = Query(None),
) -> Any:
    """
    Récupérer tous les concours avec filtrage optionnel et statistiques.
    Endpoint public - accessible sans authentification.
    """
    filters = {}
    if location_id:
        filters["location_id"] = location_id
    if contest_type:
        filters["contest_type"] = contest_type
    if active is not None:
        filters["is_active"] = active
    
    contests = contest.get_multi_with_filters(
        db=db, skip=skip, limit=limit, filters=filters
    )
    
    # Enrichir chaque contest avec les statistiques
    enriched_contests = []
    for c in contests:
        # Récupérer directement voting_restriction depuis le modèle Contest
        voting_restriction_value = 'none'
        if c.voting_restriction:
            if hasattr(c.voting_restriction, 'value'):
                voting_restriction_value = c.voting_restriction.value
            elif isinstance(c.voting_restriction, str):
                voting_restriction_value = c.voting_restriction
            else:
                voting_restriction_value = str(c.voting_restriction)
        
        # Enrichir avec les stats
        enriched = contest.enrich_contest_with_stats(db=db, contest=c)
        
        # FORCER voting_restriction à être présent avec la valeur du modèle
        # S'assurer que c'est toujours une chaîne de caractères
        enriched['voting_restriction'] = str(voting_restriction_value) if voting_restriction_value else 'none'
        
        # S'assurer que tous les champs requis sont présents
        if 'gender_restriction' not in enriched:
            enriched['gender_restriction'] = None
        
        # Créer l'objet Contest à partir du dictionnaire
        try:
            contest_response = Contest(**enriched)
            enriched_contests.append(contest_response)
        except Exception as e:
            # En cas d'erreur, retourner le dictionnaire tel quel (FastAPI le sérialisera)
            enriched_contests.append(enriched)
    
    return enriched_contests

@router.get("/{contest_id}", response_model=ContestWithEntries)
def read_contest(
    *,
    db: Session = Depends(get_db),
    contest_id: int,
) -> Any:
    """
    Récupérer un concours par ID avec ses participants.
    Endpoint public - accessible sans authentification.
    """
    contest_obj = contest.get_with_entries(db=db, id=contest_id)
    if not contest_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Concours non trouvé"
        )
    
    # Récupérer directement voting_restriction depuis le modèle Contest
    voting_restriction_value = 'none'
    if contest_obj.voting_restriction:
        if hasattr(contest_obj.voting_restriction, 'value'):
            voting_restriction_value = contest_obj.voting_restriction.value
        elif isinstance(contest_obj.voting_restriction, str):
            voting_restriction_value = contest_obj.voting_restriction
        else:
            voting_restriction_value = str(contest_obj.voting_restriction)
    
    # Enrichir avec les stats
    enriched = contest.enrich_contest_with_stats(db=db, contest=contest_obj)
    
    # FORCER voting_restriction à être présent avec la valeur du modèle
    enriched['voting_restriction'] = str(voting_restriction_value) if voting_restriction_value else 'none'
    
    # S'assurer que tous les champs requis sont présents
    if 'gender_restriction' not in enriched:
        enriched['gender_restriction'] = None
    
    return enriched

@router.put("/{contest_id}", response_model=Contest)
def update_contest(
    *,
    db: Session = Depends(get_db),
    contest_id: int,
    contest_in: ContestUpdate,
    current_user: Any = Depends(get_current_active_user),
) -> Any:
    """
    Mettre à jour un concours.
    """
    contest_obj = contest.get(db=db, id=contest_id)
    if not contest_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Concours non trouvé"
        )
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission insuffisante"
        )
    contest_obj = contest.update(db=db, db_obj=contest_obj, obj_in=contest_in)
    return contest_obj

@router.post("/{contest_id}/entry", status_code=status.HTTP_201_CREATED)
def create_contest_entry(
    *,
    db: Session = Depends(get_db),
    contest_id: int,
    media_id: int,
    current_user: Any = Depends(get_current_active_user),
) -> Any:
    """
    Participer à un concours avec un média.
    """
    contest_obj = contest.get(db=db, id=contest_id)
    if not contest_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Concours non trouvé"
        )
    
    # Vérifier si les soumissions sont autorisées
    from app.services.contest_status import contest_status_service
    is_allowed, error_message = contest_status_service.check_submission_allowed(db, contest_id)
    if not is_allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_message
        )
    
    # Créer la participation
    result = contest.create_entry(
        db=db, contest_id=contest_id, media_id=media_id, user_id=current_user.id
    )
    
    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result["error"]
        )
        
    return {"message": "Participation enregistrée avec succès"}
