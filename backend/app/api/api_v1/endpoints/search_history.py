from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api import deps
from app.db.session import get_db
from app.models.user import User
from app.crud.crud_search_history import search_history
from app.schemas.search_history import SearchHistoryCreate, SearchHistoryRead

router = APIRouter()


@router.get("/search-history", response_model=List[SearchHistoryRead])
def get_my_search_history(
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
    limit: int = 20,
):
    """Récupérer l'historique de recherche de l'utilisateur connecté."""
    return search_history.get_by_user(db, user_id=current_user.id, limit=limit)


@router.post("/search-history", response_model=SearchHistoryRead, status_code=status.HTTP_201_CREATED)
def create_search_history(
    payload: SearchHistoryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Enregistrer une nouvelle recherche pour l'utilisateur connecté."""
    term = payload.term.strip()
    if not term:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Term is required")
    return search_history.create(db, user_id=current_user.id, term=term)
