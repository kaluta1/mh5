from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.crud import user as crud_user
from app.db.session import get_db
from app.schemas.user import User, UserUpdate

router = APIRouter()

@router.get("/me", response_model=User)
def read_user_me(
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Récupérer les détails de l'utilisateur courant.
    """
    return current_user

@router.put("/me", response_model=User)
def update_user_me(
    *,
    db: Session = Depends(get_db),
    user_in: UserUpdate,
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Mettre à jour les informations de l'utilisateur courant.
    """
    user = crud_user.update(db, db_obj=current_user, obj_in=user_in)
    return user

@router.get("/{user_id}", response_model=User)
def read_user_by_id(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Récupérer un utilisateur par ID.
    """
    user = crud_user.get(db, id=user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Utilisateur non trouvé"
        )
    return user

@router.get("/", response_model=List[User])
def read_users(
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Récupérer tous les utilisateurs.
    Accessible uniquement par les administrateurs.
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission insuffisante"
        )
    users = crud_user.get_users(db, skip=skip, limit=limit)
    return users
