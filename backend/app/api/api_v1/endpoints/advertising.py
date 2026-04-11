from typing import List, Optional, Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api import deps
from app.crud import crud_advertising
from app.schemas.advertising import (
    AdCampaign, AdCampaignCreate, AdCampaignUpdate,
    AdCreative, AdCreativeCreate,
    AdPlacement, AdPlacementCreate,
    AdPerformanceMetrics,
    AdRevenueShare
)

router = APIRouter()


@router.post("/campaigns", response_model=AdCampaign, status_code=status.HTTP_201_CREATED)
def create_ad_campaign(
    *,
    db: Session = Depends(deps.get_db),
    campaign_in: AdCampaignCreate,
    current_user = Depends(deps.get_current_active_user)
):
    """
    Créer une nouvelle campagne publicitaire.
    """
    if not (
        current_user.identity_verified and getattr(current_user, "address_verified", False)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vérification d'identité et de domicile requise pour créer des campagnes"
        )
    
    campaign = crud_advertising.ad_campaign.create_with_advertiser(
        db=db, obj_in=campaign_in, advertiser_id=current_user.id
    )
    return campaign


@router.get("/campaigns", response_model=List[AdCampaign])
def get_my_campaigns(
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_active_user),
    skip: int = 0,
    limit: int = 50
):
    """
    Récupérer les campagnes publicitaires de l'utilisateur.
    """
    campaigns = crud_advertising.ad_campaign.get_by_advertiser(
        db=db, advertiser_id=current_user.id, skip=skip, limit=limit
    )
    return campaigns


@router.get("/campaigns/{campaign_id}", response_model=AdCampaign)
def get_campaign(
    campaign_id: int,
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_active_user)
):
    """
    Récupérer une campagne publicitaire par ID.
    """
    campaign = crud_advertising.ad_campaign.get(db=db, id=campaign_id)
    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campagne non trouvée"
        )
    
    if campaign.advertiser_id != current_user.id and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission insuffisante"
        )
    
    return campaign


@router.put("/campaigns/{campaign_id}", response_model=AdCampaign)
def update_campaign(
    *,
    db: Session = Depends(deps.get_db),
    campaign_id: int,
    campaign_in: AdCampaignUpdate,
    current_user = Depends(deps.get_current_active_user)
):
    """
    Mettre à jour une campagne publicitaire.
    """
    campaign = crud_advertising.ad_campaign.get(db=db, id=campaign_id)
    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campagne non trouvée"
        )
    
    if campaign.advertiser_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission insuffisante"
        )
    
    campaign = crud_advertising.ad_campaign.update(db=db, db_obj=campaign, obj_in=campaign_in)
    return campaign


@router.post("/campaigns/{campaign_id}/creatives", response_model=AdCreative, status_code=status.HTTP_201_CREATED)
def create_ad_creative(
    *,
    db: Session = Depends(deps.get_db),
    campaign_id: int,
    creative_in: AdCreativeCreate,
    current_user = Depends(deps.get_current_active_user)
):
    """
    Créer un créatif publicitaire pour une campagne.
    """
    campaign = crud_advertising.ad_campaign.get(db=db, id=campaign_id)
    if not campaign or campaign.advertiser_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission insuffisante"
        )
    
    creative = crud_advertising.ad_creative.create_with_campaign(
        db=db, obj_in=creative_in, campaign_id=campaign_id
    )
    return creative


@router.get("/campaigns/{campaign_id}/creatives", response_model=List[AdCreative])
def get_campaign_creatives(
    campaign_id: int,
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_active_user)
):
    """
    Récupérer les créatifs d'une campagne.
    """
    campaign = crud_advertising.ad_campaign.get(db=db, id=campaign_id)
    if not campaign or campaign.advertiser_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission insuffisante"
        )
    
    creatives = crud_advertising.ad_creative.get_by_campaign(
        db=db, campaign_id=campaign_id
    )
    return creatives


@router.get("/placements", response_model=List[AdPlacement])
def get_available_placements(
    db: Session = Depends(deps.get_db),
    placement_type: Optional[str] = None,
    location: Optional[str] = None
):
    """
    Récupérer les emplacements publicitaires disponibles.
    """
    placements = crud_advertising.ad_placement.get_available_placements(
        db=db, placement_type=placement_type, location=location
    )
    return placements


@router.post("/campaigns/{campaign_id}/placements", status_code=status.HTTP_201_CREATED)
def book_ad_placement(
    *,
    db: Session = Depends(deps.get_db),
    campaign_id: int,
    placement_data: dict,  # {"placement_id": int, "start_date": str, "end_date": str}
    current_user = Depends(deps.get_current_active_user)
):
    """
    Réserver un emplacement publicitaire pour une campagne.
    """
    campaign = crud_advertising.ad_campaign.get(db=db, id=campaign_id)
    if not campaign or campaign.advertiser_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission insuffisante"
        )
    
    result = crud_advertising.ad_placement.book_placement(
        db=db,
        campaign_id=campaign_id,
        placement_id=placement_data["placement_id"],
        start_date=placement_data["start_date"],
        end_date=placement_data["end_date"]
    )
    
    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result["error"]
        )
    
    return result


@router.get("/campaigns/{campaign_id}/metrics", response_model=AdPerformanceMetrics)
def get_campaign_metrics(
    campaign_id: int,
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_active_user),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
):
    """
    Récupérer les métriques de performance d'une campagne.
    """
    campaign = crud_advertising.ad_campaign.get(db=db, id=campaign_id)
    if not campaign or campaign.advertiser_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission insuffisante"
        )
    
    metrics = crud_advertising.ad_performance_metrics.get_campaign_metrics(
        db=db,
        campaign_id=campaign_id,
        start_date=start_date,
        end_date=end_date
    )
    return metrics


@router.get("/revenue-shares", response_model=List[AdRevenueShare])
def get_my_ad_revenue(
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_active_user),
    skip: int = 0,
    limit: int = 50
):
    """
    Récupérer les partages de revenus publicitaires de l'utilisateur.
    """
    revenue_shares = crud_advertising.ad_revenue_share.get_user_shares(
        db=db, user_id=current_user.id, skip=skip, limit=limit
    )
    return revenue_shares


@router.post("/track-impression", status_code=status.HTTP_201_CREATED)
def track_ad_impression(
    *,
    db: Session = Depends(deps.get_db),
    impression_data: dict  # {"creative_id": int, "placement_id": int, "user_id": int, "metadata": dict}
):
    """
    Enregistrer une impression publicitaire.
    """
    result = crud_advertising.ad_impression.track_impression(
        db=db,
        creative_id=impression_data["creative_id"],
        placement_id=impression_data["placement_id"],
        user_id=impression_data.get("user_id"),
        metadata=impression_data.get("metadata", {})
    )
    
    return {"tracked": result}


@router.post("/track-click", status_code=status.HTTP_201_CREATED)
def track_ad_click(
    *,
    db: Session = Depends(deps.get_db),
    click_data: dict  # {"creative_id": int, "placement_id": int, "user_id": int, "metadata": dict}
):
    """
    Enregistrer un clic publicitaire.
    """
    result = crud_advertising.ad_click.track_click(
        db=db,
        creative_id=click_data["creative_id"],
        placement_id=click_data["placement_id"],
        user_id=click_data.get("user_id"),
        metadata=click_data.get("metadata", {})
    )
    
    return {"tracked": result}


@router.get("/dashboard")
def get_advertiser_dashboard(
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_active_user)
):
    """
    Récupérer le tableau de bord publicitaire de l'utilisateur.
    """
    dashboard = crud_advertising.ad_campaign.get_advertiser_dashboard(
        db=db, advertiser_id=current_user.id
    )
    return dashboard


@router.get("/native-ads")
def get_native_ads(
    db: Session = Depends(deps.get_db),
    placement_type: str = "native",
    location: Optional[str] = None,
    user_id: Optional[int] = None
):
    """
    Récupérer les publicités natives pour affichage.
    """
    ads = crud_advertising.ad_creative.get_native_ads(
        db=db,
        placement_type=placement_type,
        location=location,
        user_id=user_id
    )
    return ads


@router.post("/budget/add", status_code=status.HTTP_201_CREATED)
def add_campaign_budget(
    *,
    db: Session = Depends(deps.get_db),
    budget_data: dict,  # {"campaign_id": int, "amount": float, "currency": str}
    current_user = Depends(deps.get_current_active_user)
):
    """
    Ajouter du budget à une campagne publicitaire.
    """
    campaign = crud_advertising.ad_campaign.get(db=db, id=budget_data["campaign_id"])
    if not campaign or campaign.advertiser_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission insuffisante"
        )
    
    result = crud_advertising.ad_budget_transaction.add_budget(
        db=db,
        campaign_id=budget_data["campaign_id"],
        amount=budget_data["amount"],
        currency=budget_data["currency"]
    )
    
    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result["error"]
        )
    
    return result
