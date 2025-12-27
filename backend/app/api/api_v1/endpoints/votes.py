from typing import Any, List
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.crud import crud_contest
from app.db.session import get_db
from app.models.contest import ContestVote, ContestEntry
from app.schemas.contest import VoteCreate, Vote as VoteSchema

router = APIRouter()

@router.post("/{contest_id}", status_code=status.HTTP_201_CREATED)
def cast_vote(
    *,
    db: Session = Depends(get_db),
    contest_id: int,
    entry_id: int,
    score: int = Query(..., ge=1, le=5),  # Score entre 1 et 5
    current_user: Any = Depends(get_current_active_user),
) -> Any:
    """
    Voter pour une participation à un concours avec le système MyHigh5.
    Chaque utilisateur peut voter pour 5 participants max avec des scores de 5 à 1.
    """
    # Vérifier si le concours existe et est en phase de vote
    contest = crud_contest.get(db=db, id=contest_id)
    if not contest:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Concours non trouvé"
        )
    
    # Vérifier si le vote est autorisé
    from app.services.contest_status import contest_status_service
    is_allowed, error_message = contest_status_service.check_voting_allowed(db, contest_id)
    if not is_allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_message
        )
    
    # Vérifier si l'entrée existe et appartient au concours
    entry = db.query(ContestEntry).filter(
        ContestEntry.id == entry_id,
        ContestEntry.contest_id == contest_id
    ).first()
    
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Participation non trouvée dans ce concours"
        )
    
    # Vérifier si l'utilisateur peut voter (max 5 votes)
    existing_votes = db.query(ContestVote).join(ContestEntry).filter(
        ContestEntry.contest_id == contest_id,
        ContestVote.user_id == current_user.id
    ).all()
    
    # Vérifier si l'utilisateur a déjà voté pour cette entrée
    for vote in existing_votes:
        if vote.entry_id == entry_id:
            # Mise à jour du vote existant
            vote.score = score
            db.commit()
            return {"message": "Vote mis à jour avec succès"}
    
    if len(existing_votes) >= 5:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vous avez déjà atteint le nombre maximum de votes (5)"
        )
    
    # Créer un nouveau vote
    new_vote = ContestVote(
        entry_id=entry_id,
        user_id=current_user.id,
        score=score
    )
    
    db.add(new_vote)
    db.commit()
    
    # Mise à jour du score total de la participation
    update_entry_score(db, entry_id)
    
    return {"message": "Vote enregistré avec succès"}


@router.get("/{contest_id}/my", response_model=List[VoteSchema])
def get_my_votes(
    *,
    db: Session = Depends(get_db),
    contest_id: int,
    current_user: Any = Depends(get_current_active_user),
) -> Any:
    """
    Récupérer les votes de l'utilisateur pour un concours spécifique
    """
    votes = db.query(ContestVote).join(ContestEntry).filter(
        ContestEntry.contest_id == contest_id,
        ContestVote.user_id == current_user.id
    ).all()
    
    return votes


# Fonction utilitaire pour mettre à jour le score total d'une participation
def update_entry_score(db: Session, entry_id: int) -> None:
    """
    Calcule et met à jour le score total d'une participation
    """
    # Récupérer tous les votes pour cette participation
    votes = db.query(ContestVote).filter(ContestVote.entry_id == entry_id).all()
    
    # Calculer le score total
    total_score = sum(vote.score for vote in votes)
    
    # Mettre à jour le score de la participation
    entry = db.query(ContestEntry).filter(ContestEntry.id == entry_id).first()
    if entry:
        entry.total_score = total_score
        db.commit()
