from typing import List, Optional, Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api import deps
from app.crud import crud_voting
from app.schemas.voting import (
    Vote, VoteCreate, VoteUpdate, VoteWithDetails,
    VotingStats, VotingStatsWithContestant,
    VoteRanking, VoteRankingWithContestant,
    VotingSession, VotingSessionCreate,
    StageLeaderboard, ContestantVotingProfile,
    VotingAnalytics, UserVotingHistory
)

router = APIRouter()


@router.post("/cast", response_model=Vote, status_code=status.HTTP_201_CREATED)
def cast_vote(
    *,
    db: Session = Depends(deps.get_db),
    vote_in: VoteCreate,
    current_user = Depends(deps.get_current_active_user)
):
    """
    Voter pour un participant dans un concours.
    Système de vote avec points 1-5 (5=excellent, 1=faible).
    """
    from app.models.contests import ContestStage, Contestant
    from app.models.contests import ContestStatus
    from app.services.contest_status import contest_status_service
    
    # Vérifier que le stage existe et est en phase de vote
    stage = db.query(ContestStage).filter(ContestStage.id == vote_in.stage_id).first()
    if not stage:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Étape de concours non trouvée"
        )
    
    if stage.status != ContestStatus.VOTING_ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Le vote n'est pas ouvert pour cette étape"
        )
    
    # Vérifier si le contest associé permet le vote
    from app.models.contests import ContestSeasonLink
    from app.models.contest import Contest as MyfavContest
    
    contest_link = db.query(ContestSeasonLink).filter(
        ContestSeasonLink.season_id == stage.season_id,
        ContestSeasonLink.is_active == True
    ).first()
    
    if contest_link:
        contest = db.query(MyfavContest).filter(MyfavContest.id == contest_link.contest_id).first()
        if contest:
            is_allowed, error_message = contest_status_service.check_voting_allowed(db, contest.id)
            if not is_allowed:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=error_message
                )
    
    # Vérifier si l'utilisateur peut voter
    existing_vote = crud_voting.get_user_vote_for_contestant(
        db=db, 
        voter_id=current_user.id,
        contestant_id=vote_in.contestant_id,
        stage_id=vote_in.stage_id
    )
    
    if existing_vote:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vous avez déjà voté pour ce participant"
        )
    
    # Créer le vote
    vote = crud_voting.create_vote(
        db=db, 
        obj_in=vote_in,
        voter_id=current_user.id
    )
    
    # Mettre à jour les statistiques
    crud_voting.update_voting_stats(db=db, contestant_id=vote_in.contestant_id)
    
    return vote


@router.get("/user-history", response_model=UserVotingHistory)
def get_user_voting_history(
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_active_user),
    skip: int = 0,
    limit: int = 20
):
    """
    Récupérer l'historique de vote de l'utilisateur.
    """
    history = crud_voting.get_user_voting_history(
        db=db,
        user_id=current_user.id,
        skip=skip,
        limit=limit
    )
    return history


@router.put("/update/{vote_id}", response_model=Vote)
def update_vote(
    *,
    db: Session = Depends(deps.get_db),
    vote_id: int,
    vote_update: VoteUpdate,
    current_user = Depends(deps.get_current_active_user)
):
    """
    Modifier un vote existant (si autorisé).
    """
    vote = crud_voting.get_vote(db=db, vote_id=vote_id)
    if not vote:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vote non trouvé"
        )
    
    if vote.voter_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vous ne pouvez modifier que vos propres votes"
        )
    
    updated_vote = crud_voting.update_vote(
        db=db, 
        vote_id=vote_id, 
        obj_in=vote_update
    )
    
    # Mettre à jour les statistiques
    crud_voting.update_voting_stats(db=db, contestant_id=vote.contestant_id)
    
    return updated_vote


@router.get("/session/{stage_id}", response_model=VotingSession)
def get_voting_session(
    stage_id: int,
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_active_user)
):
    """
    Récupérer ou créer une session de vote pour une étape.
    """
    session = crud_voting.get_or_create_voting_session(
        db=db,
        user_id=current_user.id,
        stage_id=stage_id
    )
    return session


@router.get("/leaderboard/{stage_id}", response_model=StageLeaderboard)
def get_stage_leaderboard(
    stage_id: int,
    db: Session = Depends(deps.get_db),
    skip: int = 0,
    limit: int = 50
):
    """
    Récupérer le classement complet d'une étape de concours.
    """
    leaderboard = crud_voting.get_stage_leaderboard(
        db=db, stage_id=stage_id, skip=skip, limit=limit
    )
    return leaderboard


@router.get("/stats/{contestant_id}", response_model=VotingStatsWithContestant)
def get_contestant_voting_stats(
    contestant_id: int,
    db: Session = Depends(deps.get_db)
):
    """
    Récupérer les statistiques de vote d'un participant.
    """
    stats = crud_voting.get_contestant_voting_stats(
        db=db, contestant_id=contestant_id
    )
    if not stats:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Statistiques non trouvées pour ce participant"
        )
    return stats


@router.get("/contestant-profile/{contestant_id}", response_model=ContestantVotingProfile)
def get_contestant_voting_profile(
    contestant_id: int,
    db: Session = Depends(deps.get_db)
):
    """
    Récupérer le profil de vote complet d'un participant.
    """
    profile = crud_voting.get_contestant_voting_profile(
        db=db, contestant_id=contestant_id
    )
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profil non trouvé pour ce participant"
        )
    return profile


@router.get("/analytics/{stage_id}", response_model=VotingAnalytics)
def get_voting_analytics(
    stage_id: int,
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_active_user)
):
    """
    Récupérer les analytiques de vote pour une étape (admin seulement).
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé aux administrateurs"
        )
    
    analytics = crud_voting.get_voting_analytics(
        db=db, stage_id=stage_id
    )
    return analytics


@router.delete("/delete/{vote_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_vote(
    *,
    db: Session = Depends(deps.get_db),
    vote_id: int,
    current_user = Depends(deps.get_current_active_user)
) -> None:
    """
    Supprimer un vote (si autorisé).
    """
    vote = crud_voting.get_vote(db=db, vote_id=vote_id)
    if not vote:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vote non trouvé"
        )
    
    if vote.voter_id != current_user.id and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission insuffisante"
        )
    
    crud_voting.delete_vote(db=db, vote_id=vote_id)
    
    # Mettre à jour les statistiques
    crud_voting.update_voting_stats(db=db, contestant_id=vote.contestant_id)


@router.get("/can-vote/{stage_id}")
def check_voting_eligibility(
    stage_id: int,
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_active_user)
):
    """
    Vérifier si l'utilisateur peut voter dans cette étape.
    """
    eligibility = crud_voting.check_voting_eligibility(
        db=db,
        user_id=current_user.id,
        stage_id=stage_id
    )
    return eligibility


@router.get("/my-votes/{stage_id}", response_model=List[VoteWithDetails])
def get_my_votes_for_stage(
    stage_id: int,
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_active_user)
):
    """
    Récupérer tous les votes de l'utilisateur pour une étape.
    """
    votes = crud_voting.get_user_votes_for_stage(
        db=db,
        user_id=current_user.id,
        stage_id=stage_id
    )
    return votes
