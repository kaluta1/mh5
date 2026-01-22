from typing import Any, List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import crud, models
from app.schemas import round as round_schema
from app.api import deps
from app.models.round import Round

router = APIRouter()

@router.get("/", response_model=List[round_schema.Round])
def read_rounds(
    db: Session = Depends(deps.get_db),
    skip: int = 0,
    limit: int = 100,
    contest_id: int = None
) -> Any:
    """
    Retrieve rounds.
    """
    if contest_id:
        rounds = db.query(Round).filter(Round.contest_id == contest_id).offset(skip).limit(limit).all()
    else:
        # CRUDRound does not have get_multi, implement it or use raw query
        rounds = db.query(Round).offset(skip).limit(limit).all()
    return rounds

@router.post("/", response_model=round_schema.Round)
def create_round(
    *,
    db: Session = Depends(deps.get_db),
    round_in: round_schema.RoundCreate,
    current_user: models.User = Depends(deps.get_current_admin_user),
) -> Any:
    """
    Create new round.
    """
    round = crud.round.create_with_contest(db=db, obj_in=round_in)
    return round

@router.put("/{id}", response_model=round_schema.Round)
def update_round(
    *,
    db: Session = Depends(deps.get_db),
    id: int,
    round_in: round_schema.RoundUpdate,
    current_user: models.User = Depends(deps.get_current_admin_user),
) -> Any:
    """
    Update a round.
    """
    round = crud.round.get(db=db, id=id)
    if not round:
        raise HTTPException(status_code=404, detail="Round not found")
    round = crud.round.update(db=db, db_obj=round, obj_in=round_in)
    return round

@router.delete("/{id}", response_model=round_schema.Round)
def delete_round(
    *,
    db: Session = Depends(deps.get_db),
    id: int,
    current_user: models.User = Depends(deps.get_current_admin_user),
) -> Any:
    """
    Delete a round.
    """
    round = crud.round.get(db=db, id=id)
    if not round:
        raise HTTPException(status_code=404, detail="Round not found")
        
    # CRUDRound needs remove method? For now manually delete
    db.delete(round)
    db.commit()
    return round
