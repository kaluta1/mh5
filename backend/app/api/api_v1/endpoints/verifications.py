from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.api.deps import get_current_user, get_current_admin_user
from app.models.user import User
from app.models.verification import VerificationStatus
from app.schemas.verification import (
    VerificationCreate,
    VerificationUpdate,
    VerificationResponse,
    VerificationListResponse,
    UserVerificationsResponse,
    MediaType
)
from app.crud.crud_verification import verification_crud
from app.services.content_moderation import content_moderation_service

router = APIRouter()


@router.post("/", response_model=VerificationResponse, status_code=status.HTTP_201_CREATED)
async def create_verification(
    verification_in: VerificationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Créer une nouvelle vérification.
    L'utilisateur soumet un média (selfie, audio, vidéo) pour vérification.
    """
    # ============================================
    # MODÉRATION DU CONTENU AVANT CRÉATION
    # ============================================
    if verification_in.media_url:
        moderation_result = None
        
        # Modérer selon le type de média
        if verification_in.media_type == MediaType.IMAGE:
            moderation_result = content_moderation_service.moderate_image(verification_in.media_url)
        elif verification_in.media_type == MediaType.VIDEO:
            moderation_result = content_moderation_service.moderate_video(verification_in.media_url)
        # Note: L'audio n'est pas modéré par Sightengine
        
        if moderation_result and not moderation_result.is_approved:
            flags_desc = ", ".join([f.description for f in moderation_result.flags])
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Média rejeté par la modération: {flags_desc}"
            )
    
    verification = verification_crud.create(db, current_user.id, verification_in)
    return verification


@router.get("/me", response_model=UserVerificationsResponse)
async def get_my_verifications(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Récupérer le statut de mes vérifications.
    """
    return verification_crud.get_user_verification_status(db, current_user.id)


@router.get("/me/all", response_model=list[VerificationResponse])
async def get_all_my_verifications(
    verification_type: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Récupérer toutes mes vérifications.
    """
    verifications = verification_crud.get_by_user(db, current_user.id, verification_type)
    return verifications


@router.get("/{verification_id}", response_model=VerificationResponse)
async def get_verification(
    verification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Récupérer une vérification par ID.
    """
    verification = verification_crud.get(db, verification_id)
    if not verification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vérification non trouvée"
        )
    
    # Vérifier que l'utilisateur a accès
    if verification.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès non autorisé"
        )
    
    return verification


@router.delete("/{verification_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_verification(
    verification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Supprimer une vérification.
    """
    verification = verification_crud.get(db, verification_id)
    if not verification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vérification non trouvée"
        )
    
    # Seul le propriétaire ou un admin peut supprimer
    if verification.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès non autorisé"
        )
    
    verification_crud.delete(db, verification_id)
    return None


# ============== Admin Endpoints ==============

@router.get("/admin/pending", response_model=VerificationListResponse)
async def get_pending_verifications(
    page: int = 1,
    per_page: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """
    [Admin] Récupérer les vérifications en attente.
    """
    skip = (page - 1) * per_page
    verifications = verification_crud.get_pending(db, skip=skip, limit=per_page)
    total = verification_crud.count_pending(db)
    
    return VerificationListResponse(
        verifications=verifications,
        total=total,
        page=page,
        per_page=per_page
    )


@router.put("/admin/{verification_id}", response_model=VerificationResponse)
async def update_verification_status(
    verification_id: int,
    update_in: VerificationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """
    [Admin] Mettre à jour le statut d'une vérification (approuver/rejeter).
    """
    verification = verification_crud.get(db, verification_id)
    if not verification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vérification non trouvée"
        )
    
    updated = verification_crud.update_status(
        db,
        verification_id,
        VerificationStatus(update_in.status),
        current_user.id,
        update_in.rejection_reason
    )
    
    return updated


@router.get("/admin/user/{user_id}", response_model=UserVerificationsResponse)
async def get_user_verifications_admin(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """
    [Admin] Récupérer le statut des vérifications d'un utilisateur.
    """
    return verification_crud.get_user_verification_status(db, user_id)
