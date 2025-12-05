from typing import List, Optional, Any
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session

from app.api import deps
from app.crud import (
    affiliate_tree, affiliate_commission, referral_link,
    referral_click, revenue_share, founding_member,
    user as crud_user
)
from app.schemas.affiliate import (
    AffiliateTree, AffiliateTreeResponse,
    AffiliateCommission, AffiliateCommissionResponse,
    ReferralLink, ReferralLinkCreate,
    RevenueShare, RevenueShareResponse,
    AffiliateStats
)
from app.schemas.user import UserSponsorInfo

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
