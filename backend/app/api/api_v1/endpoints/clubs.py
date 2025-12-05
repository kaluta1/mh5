from typing import List, Optional, Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api import deps
from app.crud import crud_clubs
from app.schemas.clubs import (
    FanClub, FanClubCreate, FanClubUpdate,
    ClubMembership, ClubMembershipCreate,
    ClubContent, ClubContentCreate,
    ClubWallet, ClubTransaction,
    ClubAdmin, ClubAdminCreate
)

router = APIRouter()


@router.post("/", response_model=FanClub, status_code=status.HTTP_201_CREATED)
def create_club(
    *,
    db: Session = Depends(deps.get_db),
    club_in: FanClubCreate,
    current_user = Depends(deps.get_current_active_user)
):
    """
    Créer un nouveau club de fans (utilisateurs vérifiés seulement).
    """
    if not current_user.identity_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vérification d'identité requise pour créer un club"
        )
    
    club = crud_clubs.fan_club.create_with_owner(
        db=db, obj_in=club_in, owner_id=current_user.id
    )
    return club


@router.get("/", response_model=List[FanClub])
def get_clubs(
    db: Session = Depends(deps.get_db),
    skip: int = 0,
    limit: int = 50,
    search: Optional[str] = None
):
    """
    Récupérer tous les clubs publics.
    """
    clubs = crud_clubs.fan_club.get_public_clubs(
        db=db, skip=skip, limit=limit, search=search
    )
    return clubs


@router.get("/{club_id}", response_model=FanClub)
def get_club(
    club_id: int,
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_active_user)
):
    """
    Récupérer un club par ID.
    """
    club = crud_clubs.fan_club.get(db=db, id=club_id)
    if not club:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Club non trouvé"
        )
    
    # Vérifier les permissions d'accès
    access = crud_clubs.fan_club.check_access_permissions(
        db=db, club_id=club_id, user_id=current_user.id
    )
    
    if not access["can_view"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès refusé"
        )
    
    return club


@router.put("/{club_id}", response_model=FanClub)
def update_club(
    *,
    db: Session = Depends(deps.get_db),
    club_id: int,
    club_in: FanClubUpdate,
    current_user = Depends(deps.get_current_active_user)
):
    """
    Mettre à jour un club (propriétaire ou admin seulement).
    """
    club = crud_clubs.fan_club.get(db=db, id=club_id)
    if not club:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Club non trouvé"
        )
    
    if not crud_clubs.fan_club.can_manage(db=db, club_id=club_id, user_id=current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission insuffisante"
        )
    
    club = crud_clubs.fan_club.update(db=db, db_obj=club, obj_in=club_in)
    return club


@router.post("/{club_id}/join", response_model=ClubMembership, status_code=status.HTTP_201_CREATED)
def join_club(
    *,
    db: Session = Depends(deps.get_db),
    club_id: int,
    membership_in: ClubMembershipCreate,
    current_user = Depends(deps.get_current_active_user)
):
    """
    Rejoindre un club payant.
    """
    result = crud_clubs.club_membership.create_membership(
        db=db,
        club_id=club_id,
        member_id=current_user.id,
        membership_type=membership_in.membership_type,
        payment_info=membership_in.payment_info
    )
    
    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result["error"]
        )
    
    return result["membership"]


@router.get("/{club_id}/members", response_model=List[dict])
def get_club_members(
    club_id: int,
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_active_user),
    skip: int = 0,
    limit: int = 50
):
    """
    Récupérer les membres d'un club.
    """
    # Vérifier l'accès
    if not crud_clubs.fan_club.can_view_members(db=db, club_id=club_id, user_id=current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission insuffisante"
        )
    
    members = crud_clubs.club_membership.get_club_members(
        db=db, club_id=club_id, skip=skip, limit=limit
    )
    return members


@router.post("/{club_id}/content", response_model=ClubContent, status_code=status.HTTP_201_CREATED)
def create_club_content(
    *,
    db: Session = Depends(deps.get_db),
    club_id: int,
    content_in: ClubContentCreate,
    current_user = Depends(deps.get_current_active_user)
):
    """
    Créer du contenu dans un club (admins seulement).
    """
    if not crud_clubs.fan_club.can_create_content(db=db, club_id=club_id, user_id=current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission insuffisante pour créer du contenu"
        )
    
    content = crud_clubs.club_content.create_with_author(
        db=db, obj_in=content_in, club_id=club_id, author_id=current_user.id
    )
    return content


@router.get("/{club_id}/content", response_model=List[ClubContent])
def get_club_content(
    club_id: int,
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_active_user),
    skip: int = 0,
    limit: int = 20
):
    """
    Récupérer le contenu d'un club.
    """
    # Vérifier l'accès au contenu premium
    access = crud_clubs.fan_club.check_content_access(
        db=db, club_id=club_id, user_id=current_user.id
    )
    
    content = crud_clubs.club_content.get_club_content(
        db=db,
        club_id=club_id,
        skip=skip,
        limit=limit,
        include_premium=access["can_view_premium"]
    )
    return content


@router.get("/{club_id}/wallet", response_model=ClubWallet)
def get_club_wallet(
    club_id: int,
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_active_user)
):
    """
    Récupérer le portefeuille du club (admins seulement).
    """
    if not crud_clubs.fan_club.can_manage_finances(db=db, club_id=club_id, user_id=current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission insuffisante"
        )
    
    wallet = crud_clubs.club_wallet.get_by_club(db=db, club_id=club_id)
    return wallet


@router.get("/{club_id}/transactions", response_model=List[ClubTransaction])
def get_club_transactions(
    club_id: int,
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_active_user),
    skip: int = 0,
    limit: int = 50
):
    """
    Récupérer les transactions du club (admins seulement).
    """
    if not crud_clubs.fan_club.can_manage_finances(db=db, club_id=club_id, user_id=current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission insuffisante"
        )
    
    transactions = crud_clubs.club_transaction.get_by_club(
        db=db, club_id=club_id, skip=skip, limit=limit
    )
    return transactions


@router.post("/{club_id}/withdraw", status_code=status.HTTP_201_CREATED)
def request_withdrawal(
    *,
    db: Session = Depends(deps.get_db),
    club_id: int,
    withdrawal_data: dict,  # {"amount": float, "currency": str, "destination": str}
    current_user = Depends(deps.get_current_active_user)
):
    """
    Demander un retrait de fonds (avec multi-signature si requis).
    """
    if not crud_clubs.fan_club.can_manage_finances(db=db, club_id=club_id, user_id=current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission insuffisante"
        )
    
    result = crud_clubs.club_transaction.request_withdrawal(
        db=db,
        club_id=club_id,
        requester_id=current_user.id,
        amount=withdrawal_data["amount"],
        currency=withdrawal_data["currency"],
        destination=withdrawal_data["destination"]
    )
    
    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result["error"]
        )
    
    return result


@router.post("/{club_id}/admins", response_model=ClubAdmin, status_code=status.HTTP_201_CREATED)
def add_club_admin(
    *,
    db: Session = Depends(deps.get_db),
    club_id: int,
    admin_in: ClubAdminCreate,
    current_user = Depends(deps.get_current_active_user)
):
    """
    Ajouter un administrateur au club (propriétaire seulement).
    """
    club = crud_clubs.fan_club.get(db=db, id=club_id)
    if not club or club.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seul le propriétaire peut ajouter des administrateurs"
        )
    
    admin = crud_clubs.club_admin.create_with_club(
        db=db, obj_in=admin_in, club_id=club_id
    )
    return admin


@router.get("/my-clubs", response_model=List[FanClub])
def get_my_clubs(
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_active_user)
):
    """
    Récupérer tous les clubs de l'utilisateur (propriétaire, admin, membre).
    """
    clubs = crud_clubs.fan_club.get_user_clubs(
        db=db, user_id=current_user.id
    )
    return clubs


@router.get("/my-memberships", response_model=List[ClubMembership])
def get_my_memberships(
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_active_user)
):
    """
    Récupérer tous les abonnements de l'utilisateur.
    """
    memberships = crud_clubs.club_membership.get_user_memberships(
        db=db, user_id=current_user.id
    )
    return memberships
