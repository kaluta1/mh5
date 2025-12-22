from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.crud import voting_type
from app.db.session import get_db
from app.schemas.contest import VotingType, VotingTypeCreate, VotingTypeUpdate
from app.models.contest import VotingLevel, CommissionSource

router = APIRouter()


# IMPORTANT: Les routes spécifiques (sans paramètres) doivent être définies AVANT les routes génériques (avec paramètres)
@router.post("", response_model=VotingType, status_code=status.HTTP_201_CREATED)
def create_voting_type(
    *,
    db: Session = Depends(get_db),
    voting_type_in: VotingTypeCreate,
    current_user: Any = Depends(get_current_active_user),
) -> Any:
    """
    Créer un nouveau type de vote.
    Seuls les administrateurs peuvent créer des types de vote.
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission insuffisante pour créer un type de vote"
        )
    
    try:
        new_voting_type = voting_type.create(db=db, obj_in=voting_type_in)
        return new_voting_type
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("", response_model=List[VotingType])
def read_voting_types(
    *,
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
    voting_level: Optional[str] = Query(None, description="Filtrer par niveau de vote"),
    commission_source: Optional[str] = Query(None, description="Filtrer par source de commission"),
) -> Any:
    """
    Récupérer tous les types de vote avec filtrage optionnel.
    Endpoint public - accessible sans authentification.
    """
    if voting_level:
        try:
            level_enum = VotingLevel(voting_level)
            voting_types = voting_type.get_by_level(db=db, voting_level=level_enum)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Niveau de vote invalide: {voting_level}"
            )
    elif commission_source:
        try:
            source_enum = CommissionSource(commission_source)
            voting_types = voting_type.get_by_source(db=db, commission_source=source_enum)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Source de commission invalide: {commission_source}"
            )
    else:
        voting_types = voting_type.get_multi(db=db, skip=skip, limit=limit)
    
    return voting_types


@router.get("/{voting_type_id}", response_model=VotingType)
def read_voting_type(
    *,
    db: Session = Depends(get_db),
    voting_type_id: int,
) -> Any:
    """
    Récupérer un type de vote par ID.
    Endpoint public - accessible sans authentification.
    """
    voting_type_obj = voting_type.get(db=db, id=voting_type_id)
    if not voting_type_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Type de vote non trouvé"
        )
    return voting_type_obj


@router.put("/{voting_type_id}", response_model=VotingType)
def update_voting_type(
    *,
    db: Session = Depends(get_db),
    voting_type_id: int,
    voting_type_in: VotingTypeUpdate,
    current_user: Any = Depends(get_current_active_user),
) -> Any:
    """
    Mettre à jour un type de vote.
    Seuls les administrateurs peuvent modifier des types de vote.
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission insuffisante"
        )
    
    voting_type_obj = voting_type.get(db=db, id=voting_type_id)
    if not voting_type_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Type de vote non trouvé"
        )
    
    try:
        voting_type_obj = voting_type.update(
            db=db, db_obj=voting_type_obj, obj_in=voting_type_in
        )
        return voting_type_obj
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.delete("/{voting_type_id}", response_model=VotingType)
def delete_voting_type(
    *,
    db: Session = Depends(get_db),
    voting_type_id: int,
    current_user: Any = Depends(get_current_active_user),
) -> Any:
    """
    Supprimer un type de vote.
    Seuls les administrateurs peuvent supprimer des types de vote.
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission insuffisante"
        )
    
    voting_type_obj = voting_type.get(db=db, id=voting_type_id)
    if not voting_type_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Type de vote non trouvé"
        )
    
    voting_type.remove(db=db, id=voting_type_id)
    return voting_type_obj

