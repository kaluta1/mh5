from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.crud import suggested_contest
from app.db.session import get_db
from app.schemas.contest import SuggestedContest, SuggestedContestCreate, SuggestedContestUpdate
from app.models.contest import SuggestedContestStatus

router = APIRouter()


@router.post("", response_model=SuggestedContest, status_code=status.HTTP_201_CREATED)
def create_suggested_contest(
    *,
    db: Session = Depends(get_db),
    suggested_contest_in: SuggestedContestCreate,
    current_user: Any = Depends(get_current_active_user),
) -> Any:
    """
    Créer une nouvelle suggestion de concours.
    Accessible à tous les utilisateurs authentifiés.
    """
    # Validation des champs requis
    if not suggested_contest_in.name or not suggested_contest_in.name.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The contest name is required and cannot be empty"
        )
    
    if not suggested_contest_in.category or not suggested_contest_in.category.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The category is required and cannot be empty"
        )
    
    # Validation de la longueur du nom
    if len(suggested_contest_in.name.strip()) > 255:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The contest name cannot exceed 255 characters"
        )
    
    # Validation de la longueur de la catégorie
    if len(suggested_contest_in.category.strip()) > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The category cannot exceed 100 characters"
        )
    
    try:
        new_suggestion = suggested_contest.create(db=db, obj_in=suggested_contest_in)
        return new_suggestion
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        # Gestion des erreurs inattendues
        print(f"Erreur lors de la création d'une suggestion de concours: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The suggestion could not be created. Please try again later."
        )


@router.get("", response_model=List[SuggestedContest])
def read_suggested_contests(
    *,
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 10,
    status: Optional[str] = Query(None, description="Filtrer par statut (pending, approved, rejected)"),
    category: Optional[str] = Query(None, description="Filtrer par catégorie"),
) -> Any:
    """
    Récupérer toutes les suggestions de concours avec filtrage optionnel.
    Endpoint public - accessible sans authentification.
    """
    status_enum = None
    if status:
        try:
            status_enum = SuggestedContestStatus(status)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status: {status}. Allowed values: pending, approved, rejected"
            )
    
    suggestions = suggested_contest.get_multi(
        db=db,
        skip=skip,
        limit=limit,
        status=status_enum,
        category=category
    )
    
    return suggestions


@router.get("/{suggested_contest_id}", response_model=SuggestedContest)
def read_suggested_contest(
    *,
    db: Session = Depends(get_db),
    suggested_contest_id: int,
) -> Any:
    """
    Récupérer une suggestion de concours par ID.
    Endpoint public - accessible sans authentification.
    """
    suggestion = suggested_contest.get(db=db, id=suggested_contest_id)
    if not suggestion:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contest suggestion not found"
        )
    return suggestion


@router.put("/{suggested_contest_id}", response_model=SuggestedContest)
def update_suggested_contest(
    *,
    db: Session = Depends(get_db),
    suggested_contest_id: int,
    suggested_contest_in: SuggestedContestUpdate,
    current_user: Any = Depends(get_current_active_user),
) -> Any:
    """
    Mettre à jour une suggestion de concours.
    Seuls les administrateurs peuvent modifier les suggestions.
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permission. Only administrators can edit suggestions."
        )
    
    suggestion = suggested_contest.get(db=db, id=suggested_contest_id)
    if not suggestion:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contest suggestion not found"
        )
    
    try:
        suggestion = suggested_contest.update(
            db=db, db_obj=suggestion, obj_in=suggested_contest_in
        )
        return suggestion
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.delete("/{suggested_contest_id}", response_model=SuggestedContest)
def delete_suggested_contest(
    *,
    db: Session = Depends(get_db),
    suggested_contest_id: int,
    current_user: Any = Depends(get_current_active_user),
) -> Any:
    """
    Supprimer une suggestion de concours.
    Seuls les administrateurs peuvent supprimer les suggestions.
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permission. Only administrators can delete suggestions."
        )
    
    suggestion = suggested_contest.get(db=db, id=suggested_contest_id)
    if not suggestion:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contest suggestion not found"
        )
    
    suggested_contest.remove(db=db, id=suggested_contest_id)
    return suggestion

