from typing import Any, List
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.api import deps
from app.crud import favorite as crud_favorite
from app.db.session import get_db
from app.models.user import User
from app.models.voting import MyFavorites
from app.schemas.contest import Contest

router = APIRouter()


# Modèles Pydantic
class FavoritePositionUpdate(BaseModel):
    contestant_id: int
    position: int


class FavoriteOrderUpdate(BaseModel):
    favorites: List[FavoritePositionUpdate]


# Contest Favorites
@router.post("/contests/{contest_id}", status_code=status.HTTP_201_CREATED)
def add_contest_favorite(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
    contest_id: int,
) -> Any:
    """Add a contest to user's favorites"""
    # Check if already favorited
    if crud_favorite.is_contest_favorite(db, current_user.id, contest_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This contest is already in your favorites"
        )
    
    # Check if user has reached the 5 favorite limit
    count = crud_favorite.get_contest_favorites_count(db, current_user.id)
    if count >= 5:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You can only have 5 favorite contests"
        )
    
    favorite = crud_favorite.add_contest_favorite(db, current_user.id, contest_id)
    return {"message": "Contest added to favorites", "id": favorite.id}


@router.delete("/contests/{contest_id}")
def remove_contest_favorite(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
    contest_id: int,
) -> Any:
    """Remove a contest from user's favorites"""
    if not crud_favorite.remove_contest_favorite(db, current_user.id, contest_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="This contest is not in your favorites"
        )
    return {"message": "Contest removed from favorites"}


@router.get("/contests", response_model=List[Contest])
def get_contest_favorites(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
) -> Any:
    """Get user's favorite contests"""
    favorites = crud_favorite.get_contest_favorites(db, current_user.id, skip, limit)
    # Return the contests from the favorites
    return [fav.contest for fav in favorites]


@router.get("/contests/{contest_id}/is-favorite")
def is_contest_favorite(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
    contest_id: int,
) -> Any:
    """Check if a contest is in user's favorites"""
    is_fav = crud_favorite.is_contest_favorite(db, current_user.id, contest_id)
    return {"is_favorite": is_fav}


# Contestant Favorites - Routes spécifiques AVANT les routes génériques

# Test endpoint
@router.get("/test")
def test_endpoint() -> Any:
    """Test endpoint to verify API is working"""
    return {"message": "Favorites API is working"}

# Debug endpoint - List all favorites with positions
@router.get("/debug/contestants")
def debug_contestant_favorites(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """Debug endpoint to list all favorites with positions"""
    favorites = db.query(MyFavorites).filter(
        MyFavorites.user_id == current_user.id
    ).all()
    
    result = []
    for fav in favorites:
        result.append({
            "id": fav.id,
            "contestant_id": fav.contestant_id,
            "position": fav.position,
            "added_date": fav.added_date
        })
    
    return {"total": len(result), "favorites": result}

# Reorder Favorites (DOIT venir AVANT /contestants/{contestant_id})
@router.put("/contestants/reorder", name="reorder_contestants")
def reorder_contestant_favorites(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
    order_update: FavoriteOrderUpdate,
) -> Any:
    """Update the order of contestant favorites"""
    try:
        print(f"[REORDER] User {current_user.id} reordering {len(order_update.favorites)} favorites")
        
        # Mettre à jour la position de chaque favori
        for fav_update in order_update.favorites:
            print(f"[REORDER] Updating contestant {fav_update.contestant_id} to position {fav_update.position}")
            
            favorite = db.query(MyFavorites).filter(
                MyFavorites.user_id == current_user.id,
                MyFavorites.contestant_id == fav_update.contestant_id
            ).first()
            
            if not favorite:
                print(f"[REORDER] ERROR: Favorite not found for contestant {fav_update.contestant_id}")
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Favorite contestant {fav_update.contestant_id} not found"
                )
            
            print(f"[REORDER] Found favorite: id={favorite.id}, old_position={favorite.position}")
            favorite.position = fav_update.position
            db.add(favorite)
        
        db.commit()
        print(f"[REORDER] Successfully reordered favorites for user {current_user.id}")
        return {"message": "Favorites reordered successfully"}
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        print(f"[REORDER] ERROR: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error updating favorites: {str(e)}"
        )


# Routes génériques après les routes spécifiques
@router.post("/contestants/{contestant_id}", status_code=status.HTTP_201_CREATED)
def add_contestant_favorite(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
    contestant_id: int,
    contest_type_id: int = Query(...),
    stage_id: int = Query(...),
    position: int = Query(default=1, ge=1, le=5),
) -> Any:
    """Add a contestant to user's favorites"""
    # Check if already favorited
    if crud_favorite.is_contestant_favorite(db, current_user.id, contestant_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This contestant is already in your favorites"
        )
    
    favorite = crud_favorite.add_contestant_favorite(
        db, current_user.id, contestant_id, contest_type_id, stage_id, position
    )
    return {"message": "Contestant added to favorites", "id": favorite.id}


@router.delete("/contestants/{contestant_id}")
def remove_contestant_favorite(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
    contestant_id: int,
) -> Any:
    """Remove a contestant from user's favorites"""
    if not crud_favorite.remove_contestant_favorite(db, current_user.id, contestant_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="This contestant is not in your favorites"
        )
    return {"message": "Contestant removed from favorites"}


@router.get("/contestants", response_model=List[Any])
def get_contestant_favorites(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
) -> Any:
    """Get user's favorite contestants"""
    favorites = crud_favorite.get_contestant_favorites(db, current_user.id, skip, limit)
    # Return the contestants from the favorites
    return [fav.contestant for fav in favorites]


@router.get("/contestants/{contestant_id}/is-favorite")
def is_contestant_favorite(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.get_current_active_user),
    contestant_id: int,
) -> Any:
    """Check if a contestant is in user's favorites"""
    is_fav = crud_favorite.is_contestant_favorite(db, current_user.id, contestant_id)
    return {"is_favorite": is_fav}
