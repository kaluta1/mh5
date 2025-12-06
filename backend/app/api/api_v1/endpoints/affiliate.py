from typing import List, Optional, Any
from fastapi import APIRouter, Depends, HTTPException, status, Request, BackgroundTasks
from sqlalchemy.orm import Session

from app.api import deps
from app.crud import (
    affiliate_tree, affiliate_commission, referral_link,
    referral_click, revenue_share, founding_member,
    user as crud_user
)
from app.crud.crud_invitation import invitation as crud_invitation
from app.schemas.affiliate import (
    AffiliateTree, AffiliateTreeResponse,
    AffiliateCommission, AffiliateCommissionResponse,
    ReferralLink, ReferralLinkCreate,
    RevenueShare, RevenueShareResponse,
    AffiliateStats
)
from app.schemas.user import UserSponsorInfo
from app.schemas.invitation import (
    InvitationCreate,
    InvitationBulkCreate,
    InvitationResponse,
    InvitationStats,
    InvitationSendResult
)
from app.services.email import email_service

router = APIRouter()


@router.get("/tree", response_model=AffiliateTreeResponse)
def get_affiliate_tree(
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_active_user)
):
    """
    Récupérer l'arbre d'affiliation de l'utilisateur.
    """
    tree = affiliate_tree.get_user_tree(
        db=db, user_id=current_user.id
    )
    return tree


@router.get("/referrals", response_model=List[UserSponsorInfo])
def get_direct_referrals(
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_active_user),
    skip: int = 0,
    limit: int = 50
):
    """
    Récupérer les filleuls directs de l'utilisateur (via User.sponsor_id).
    """
    referrals = crud_user.get_referrals(
        db=db, user_id=current_user.id, skip=skip, limit=limit
    )
    return referrals


@router.get("/referrals/detailed")
def get_referrals_with_commissions(
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_active_user),
    skip: int = 0,
    limit: int = 50
):
    """
    Récupérer les filleuls avec les commissions générées et statut KYC.
    """
    return crud_user.get_referrals_with_commissions(
        db=db, user_id=current_user.id, skip=skip, limit=limit
    )


@router.get("/referrals/count")
def get_referrals_count(
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_active_user)
):
    """
    Récupérer le nombre de filleuls directs de l'utilisateur.
    """
    count = crud_user.count_referrals(db=db, user_id=current_user.id)
    return {"count": count}


@router.get("/referrals/all")
def get_all_referrals_multilevel(
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_active_user),
    skip: int = 0,
    limit: int = 50,
    level: int = None,
    status: str = None,
    search: str = None,
    kyc_status: str = None
):
    """
    Récupérer tous les filleuls (directs et indirects) jusqu'au niveau 10.
    
    - **level**: Filtrer par niveau (1-10)
    - **status**: Filtrer par statut utilisateur ('active' ou 'inactive')
    - **search**: Rechercher par nom, email ou username
    - **kyc_status**: Filtrer par statut KYC ('none', 'pending', 'in_progress', 'approved', 'rejected', 'expired', 'requires_review')
    
    Retourne les referrals avec:
    - Niveau dans l'arbre (1 = direct, 2-10 = indirect)
    - Commissions générées
    - Statut KYC
    - Nombre de leurs propres filleuls
    """
    return crud_user.get_all_referrals_multilevel(
        db=db,
        user_id=current_user.id,
        skip=skip,
        limit=limit,
        level_filter=level,
        status_filter=status,
        search_query=search,
        kyc_status_filter=kyc_status
    )


@router.get("/sponsor", response_model=Optional[UserSponsorInfo])
def get_my_sponsor(
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_active_user)
):
    """
    Récupérer les informations du parrain de l'utilisateur connecté.
    """
    if not current_user.sponsor_id:
        return None
    
    sponsor = crud_user.get(db=db, id=current_user.sponsor_id)
    return sponsor


@router.get("/commissions", response_model=List[AffiliateCommission])
def get_commissions(
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_active_user),
    skip: int = 0,
    limit: int = 50,
    commission_type: Optional[str] = None
):
    """
    Récupérer les commissions d'affiliation de l'utilisateur.
    """
    commissions = affiliate_commission.get_user_commissions(
        db=db,
        user_id=current_user.id,
        skip=skip,
        limit=limit,
        commission_type=commission_type
    )
    return commissions


@router.get("/commissions/summary")
def get_commissions_summary(
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_active_user)
):
    """
    Récupérer un résumé des commissions par type et niveau.
    """
    summary = affiliate_commission.get_commissions_summary(
        db=db, user_id=current_user.id
    )
    return summary


@router.get("/referral-links", response_model=List[ReferralLink])
def get_referral_links(
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_active_user)
):
    """
    Récupérer les liens de parrainage de l'utilisateur.
    """
    links = referral_link.get_by_user(
        db=db, user_id=current_user.id
    )
    return links


@router.post("/referral-links", response_model=ReferralLink, status_code=status.HTTP_201_CREATED)
def create_referral_link(
    *,
    db: Session = Depends(deps.get_db),
    link_in: ReferralLinkCreate,
    current_user = Depends(deps.get_current_active_user)
):
    """
    Créer un nouveau lien de parrainage personnalisé.
    """
    link = referral_link.create_with_user(
        db=db, obj_in=link_in, user_id=current_user.id
    )
    return link


@router.get("/revenue-shares", response_model=List[RevenueShare])
def get_revenue_shares(
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_active_user),
    skip: int = 0,
    limit: int = 50
):
    """
    Récupérer les partages de revenus de l'utilisateur.
    """
    shares = revenue_share.get_user_shares(
        db=db, user_id=current_user.id, skip=skip, limit=limit
    )
    return shares


@router.get("/stats", response_model=AffiliateStats)
def get_affiliate_stats(
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_active_user)
):
    """
    Récupérer les statistiques d'affiliation de l'utilisateur.
    Inclut le code de parrainage, les statistiques par niveau, et les taux de conversion.
    """
    stats = affiliate_tree.get_user_stats(
        db=db, user_id=current_user.id
    )
    return stats


@router.post("/join/{referral_code}", status_code=status.HTTP_201_CREATED)
def join_via_referral(
    referral_code: str,
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_active_user)
):
    """
    Rejoindre le programme d'affiliation via un code de parrainage.
    """
    result = affiliate_tree.join_via_referral(
        db=db,
        user_id=current_user.id,
        referral_code=referral_code
    )
    
    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result["error"]
        )
    
    return {"message": "Inscription réussie dans le programme d'affiliation"}


@router.get("/genealogy/{levels}")
def get_genealogy(
    levels: int = 10,
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_active_user)
):
    """
    Récupérer la généalogie d'affiliation sur X niveaux.
    """
    if levels > 10:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum 10 niveaux autorisés"
        )
    
    genealogy = affiliate_tree.get_genealogy(
        db=db, user_id=current_user.id, levels=levels
    )
    return genealogy


@router.get("/founding-member")
def get_founding_member_info(
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_active_user)
):
    """
    Récupérer les informations de membre fondateur.
    """
    info = founding_member.get_member_info(
        db=db, user_id=current_user.id
    )
    return info


@router.post("/track-click/{referral_code}")
def track_referral_click(
    referral_code: str,
    db: Session = Depends(deps.get_db),
    request_info: dict = None  # IP, User-Agent, Referer
):
    """
    Enregistrer un clic sur un lien de parrainage.
    """
    result = referral_click.track_click(
        db=db,
        referral_code=referral_code,
        ip_address=request_info.get("ip") if request_info else None,
        user_agent=request_info.get("user_agent") if request_info else None,
        referer=request_info.get("referer") if request_info else None
    )
    
    return {"tracked": result}


# ============================================
# ENDPOINTS INVITATIONS
# ============================================

@router.post("/invitations", response_model=InvitationSendResult)
def send_invitation(
    *,
    db: Session = Depends(deps.get_db),
    invitation_in: InvitationCreate,
    background_tasks: BackgroundTasks,
    current_user = Depends(deps.get_current_active_user)
):
    """
    Envoyer une invitation de parrainage par email.
    """
    # Vérifier si l'email n'est pas déjà enregistré
    existing_user = crud_user.get_by_email(db, email=invitation_in.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cet email est déjà enregistré sur la plateforme"
        )
    
    # Vérifier si une invitation en attente existe déjà
    existing_invitation = crud_invitation.get_by_email_and_inviter(
        db, email=invitation_in.email, inviter_id=current_user.id
    )
    if existing_invitation:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Une invitation est déjà en attente pour cet email"
        )
    
    # Récupérer le code de parrainage de l'utilisateur
    referral_code = current_user.personal_referral_code
    if not referral_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vous n'avez pas de code de parrainage"
        )
    
    # Créer l'invitation
    invitation_obj = crud_invitation.create_invitation(
        db,
        inviter_id=current_user.id,
        email=invitation_in.email,
        referral_code=referral_code,
        message=invitation_in.message
    )
    
    # Envoyer l'email en arrière-plan
    inviter_name = f"{current_user.first_name or ''} {current_user.last_name or ''}".strip() or current_user.username or "Un ami"
    
    background_tasks.add_task(
        email_service.send_invitation_email,
        to_email=invitation_in.email,
        inviter_name=inviter_name,
        referral_code=referral_code,
        message=invitation_in.message
    )
    
    return InvitationSendResult(
        success=True,
        email=invitation_in.email,
        message="Invitation envoyée avec succès",
        invitation_id=invitation_obj.id
    )


@router.post("/invitations/bulk", response_model=List[InvitationSendResult])
def send_bulk_invitations(
    *,
    db: Session = Depends(deps.get_db),
    invitations_in: InvitationBulkCreate,
    background_tasks: BackgroundTasks,
    current_user = Depends(deps.get_current_active_user)
):
    """
    Envoyer plusieurs invitations de parrainage.
    """
    referral_code = current_user.personal_referral_code
    if not referral_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vous n'avez pas de code de parrainage"
        )
    
    inviter_name = f"{current_user.first_name or ''} {current_user.last_name or ''}".strip() or current_user.username or "Un ami"
    
    results = []
    for email in invitations_in.emails:
        # Vérifier si l'email n'est pas déjà enregistré
        existing_user = crud_user.get_by_email(db, email=email)
        if existing_user:
            results.append(InvitationSendResult(
                success=False,
                email=email,
                message="Email déjà enregistré"
            ))
            continue
        
        # Vérifier si une invitation en attente existe
        existing_invitation = crud_invitation.get_by_email_and_inviter(
            db, email=email, inviter_id=current_user.id
        )
        if existing_invitation:
            results.append(InvitationSendResult(
                success=False,
                email=email,
                message="Invitation déjà envoyée"
            ))
            continue
        
        # Créer l'invitation
        invitation_obj = crud_invitation.create_invitation(
            db,
            inviter_id=current_user.id,
            email=email,
            referral_code=referral_code,
            message=invitations_in.message
        )
        
        # Envoyer l'email en arrière-plan
        background_tasks.add_task(
            email_service.send_invitation_email,
            to_email=email,
            inviter_name=inviter_name,
            referral_code=referral_code,
            message=invitations_in.message
        )
        
        results.append(InvitationSendResult(
            success=True,
            email=email,
            message="Invitation envoyée",
            invitation_id=invitation_obj.id
        ))
    
    return results


@router.get("/invitations", response_model=List[InvitationResponse])
def get_my_invitations(
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_active_user),
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 50
):
    """
    Récupérer les invitations envoyées par l'utilisateur.
    """
    return crud_invitation.get_user_invitations(
        db, user_id=current_user.id, status=status, skip=skip, limit=limit
    )


@router.get("/invitations/pending", response_model=List[InvitationResponse])
def get_pending_invitations(
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_active_user),
    skip: int = 0,
    limit: int = 50
):
    """
    Récupérer les invitations en attente.
    """
    return crud_invitation.get_pending_invitations(
        db, user_id=current_user.id, skip=skip, limit=limit
    )


@router.get("/invitations/accepted", response_model=List[InvitationResponse])
def get_accepted_invitations(
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_active_user),
    skip: int = 0,
    limit: int = 50
):
    """
    Récupérer les invitations acceptées.
    """
    return crud_invitation.get_accepted_invitations(
        db, user_id=current_user.id, skip=skip, limit=limit
    )


@router.get("/invitations/stats", response_model=InvitationStats)
def get_invitation_stats(
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_active_user)
):
    """
    Récupérer les statistiques d'invitation.
    """
    return crud_invitation.get_invitation_stats(db, user_id=current_user.id)


@router.delete("/invitations/{invitation_id}")
def cancel_invitation(
    invitation_id: int,
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_active_user)
):
    """
    Annuler une invitation en attente.
    """
    invitation = crud_invitation.cancel_invitation(
        db, invitation_id=invitation_id, user_id=current_user.id
    )
    
    if not invitation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation non trouvée ou déjà traitée"
        )
    
    return {"message": "Invitation annulée"}
