from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Request, Header, BackgroundTasks, Body
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from datetime import datetime
import json

from app.api import deps
from app.core.config import settings
from app.crud import crud_kyc
from app.crud import crud_deposit
from app.models.user import User
from app.models.geography import Country
from app.models.kyc import KYCStatus, DocumentType
from app.schemas.kyc import (
    KYCVerification, KYCVerificationCreate, KYCVerificationUpdate,
    KYCDocument, KYCDocumentCreate, KYCDocumentUpdate,
    KYCAuditLog, KYCSubmissionRequest, KYCStatusResponse,
    KYCStatistics, KYCVerificationWithDocuments, KYCVerificationComplete,
    ShuftiProWebhookData, KYCWebhookResponse, KYCInitiateRequest,
)
from app.services.shufti_pro import (
    shufti_pro_service,
    kyc_flags_from_shufti_payload,
    normalize_country_iso2_for_shufti,
)
from app.services.email import email_service
from app.services.payment_accounting import payment_accounting

router = APIRouter()
KYC_PRICE_USD = 10.00  # keep in sync with product_types.price for code "kyc"


def _shufti_country_iso2_for_user(db: Session, user: User) -> Optional[str]:
    """
    Shufti requires ISO 3166-1 alpha-2. User.country is often a full name; prefer countries.code via country_id.
    """
    if user.country_id:
        row = db.query(Country).filter(Country.id == user.country_id).first()
        if row and row.code:
            iso = normalize_country_iso2_for_shufti(row.code)
            if iso:
                return iso
    return normalize_country_iso2_for_shufti(user.country)


@router.post("/initiate")
async def initiate_shufti_verification(
    *,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
    language: str = "FR",
    payload: KYCInitiateRequest = Body(default_factory=KYCInitiateRequest),
):
    """
    Initier ou reprendre une vérification KYC avec Shufti Pro.
    
    Règles:
    - UN SEUL enregistrement par utilisateur (jamais de doublons)
    - APPROVED: Bloquer (déjà vérifié)
    - IN_PROGRESS/PENDING: Réutiliser si la référence Shufti Pro est encore valide
    - REJECTED/REQUIRES_REVIEW/EXPIRED: Permettre de reprendre avec nouvelle référence
    """
    # Récupérer l'enregistrement KYC existant (il ne peut y en avoir qu'un par user)
    verification = crud_kyc.kyc_verification.get_by_user(db, user_id=current_user.id)
    
    # Cas 1: Déjà approuvé → Bloquer
    if verification and verification.status == KYCStatus.APPROVED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Votre identité est déjà vérifiée"
        )
    
    # Cas 1b: Nombre max de tentatives atteint → Bloquer
    if verification and verification.attempts_count >= verification.max_attempts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Vous avez atteint le nombre maximum de tentatives ({verification.max_attempts}). Veuillez contacter le support."
        )
    
    # Cas 1c: Vérifier si l'utilisateur a un paiement valide pour le KYC
    # (Seulement si c'est une NOUVELLE tentative, pas si on continue une existante)
    needs_new_payment = False
    if not verification:
        # Première tentative → besoin de paiement
        needs_new_payment = True
    elif verification.status in [KYCStatus.REJECTED, KYCStatus.REQUIRES_REVIEW, KYCStatus.EXPIRED]:
        # Nouvelle tentative après échec → besoin de paiement
        needs_new_payment = True
    
    valid_payment = None
    if needs_new_payment:
        valid_payment = crud_deposit.deposit.get_valid_deposit_for_product(
            db, user_id=current_user.id, product_code="kyc"
        )
        if not valid_payment:
            available_count = crud_deposit.deposit.count_valid_deposits_for_product(
                db, user_id=current_user.id, product_code="kyc"
            )
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail={
                    "message": "Vous devez payer pour effectuer la vérification KYC",
                    "available_attempts": available_count,
                    "price": KYC_PRICE_USD,
                    "currency": "USD"
                }
            )
    
    # Cas 2: Vérification en cours (PENDING/IN_PROGRESS) → Essayer de réutiliser
    if verification and verification.status in [KYCStatus.PENDING, KYCStatus.IN_PROGRESS]:
        reference = verification.reference_id
        
        if reference:
            # Vérifier auprès de Shufti Pro si la référence est toujours valide
            validity_check = await shufti_pro_service.check_reference_validity(reference)
            
            # Si la vérification est terminée côté Shufti Pro, mettre à jour notre statut
            if validity_check.get("is_completed"):
                new_status = KYCStatus.APPROVED if validity_check.get("is_accepted") else KYCStatus.REJECTED
                is_ok = bool(validity_check.get("is_accepted"))
                raw = validity_check.get("data") or {}
                flags = kyc_flags_from_shufti_payload(raw if isinstance(raw, dict) else {}, overall_accepted=is_ok)
                update_data = KYCVerificationUpdate(
                    status=new_status,
                    processed_at=datetime.utcnow(),
                    identity_verified=flags["identity_verified"],
                    document_verified=flags["document_verified"],
                    face_verified=flags["face_verified"],
                )
                crud_kyc.kyc_verification.update(db=db, db_obj=verification, obj_in=update_data)
                
                if validity_check.get("is_accepted"):
                    # Mettre à jour le user aussi
                    current_user.identity_verified = True
                    db.commit()
                    payment_accounting.post_kyc_verification_recognition_for_user(db, verification.user_id)
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Votre identité est déjà vérifiée"
                    )
                # Si rejected, on continue pour créer une nouvelle vérification
            
            elif validity_check.get("is_valid"):
                # La référence est encore valide, réutiliser l'URL existante
                verification_url = validity_check.get("verification_url") or verification.verification_url
                
                if verification_url:
                    return {
                        "verification_url": verification_url,
                        "reference": reference,
                        "verification_id": verification.id,
                        "reused": True,
                        "status": "in_progress",
                        "attempts_count": verification.attempts_count,
                        "max_attempts": verification.max_attempts,
                        "attempts_remaining": verification.max_attempts - verification.attempts_count
                    }
    
    # Cas 3: Pas de vérification, ou statut REJECTED/REQUIRES_REVIEW/EXPIRED → Créer/Mettre à jour
    
    # Générer une nouvelle référence aléatoire
    reference = shufti_pro_service.generate_reference()
    
    if verification:
        # Mettre à jour l'enregistrement existant (pas de doublon)
        # Incrémenter le compteur de tentatives seulement si c'est une nouvelle tentative (après rejet)
        if verification.status in [KYCStatus.REJECTED, KYCStatus.REQUIRES_REVIEW, KYCStatus.EXPIRED]:
            verification.attempts_count += 1
            # Marquer le paiement comme utilisé
            if valid_payment:
                crud_deposit.deposit.mark_as_used(db, deposit=valid_payment)
        
        verification.reference_id = reference
        verification.verification_url = None  # Sera mis à jour après l'appel Shufti
        verification.status = KYCStatus.PENDING
        verification.submitted_at = datetime.utcnow()
        verification.processed_at = None
        verification.rejection_reason = None
        db.commit()
        db.refresh(verification)
    else:
        # Créer le premier enregistrement pour cet utilisateur (première tentative)
        verification_create = KYCVerificationCreate(
            user_id=current_user.id,
            status=KYCStatus.PENDING,
            reference_id=reference
        )
        verification = crud_kyc.kyc_verification.create(db=db, obj_in=verification_create)
        # Incrémenter pour la première tentative
        verification.attempts_count = 1
        # Marquer le paiement comme utilisé
        if valid_payment:
            crud_deposit.deposit.mark_as_used(db, deposit=valid_payment)
        db.commit()
        db.refresh(verification)
    
    # Adresse déclarée : stockée pour le flux interne (justificatif hors Shufti). Optionnelle.
    addr = (payload.residential_address or "").strip()
    if addr and len(addr) < 10:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="If provided, residential address must be at least 10 characters.",
        )
    if addr:
        verification = crud_kyc.kyc_verification.update(
            db,
            db_obj=verification,
            obj_in=KYCVerificationUpdate(verified_address=addr),
        )

    # Appeler Shufti Pro (document + face uniquement)
    result = await shufti_pro_service.initiate_verification(
        reference=reference,
        email=current_user.email,
        country=_shufti_country_iso2_for_user(db, current_user),
        language=language,
    )
    
    if not result.get("success"):
        err = result.get("error", "Erreur lors de l'initialisation de la vérification")
        err_l = (err or "").lower()
        # Shufti misconfiguration / bad credentials — clearer than generic 500
        if (
            "shufti pro is not configured" in err_l
            or "authorization keys" in err_l
            or "shufti_client_id" in err_l
        ):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=err,
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=err,
        )
    
    verification_url = result.get("verification_url")
    
    # Mettre à jour avec l'URL et le statut IN_PROGRESS
    update_data = KYCVerificationUpdate(
        status=KYCStatus.IN_PROGRESS,
        external_verification_id=result.get("reference"),
        verification_url=verification_url
    )
    crud_kyc.kyc_verification.update(db=db, db_obj=verification, obj_in=update_data)
    
    return {
        "verification_url": verification_url,
        "reference": reference,
        "verification_id": verification.id,
        "reused": False,
        "status": "new",
        "attempts_count": verification.attempts_count,
        "max_attempts": verification.max_attempts,
        "attempts_remaining": verification.max_attempts - verification.attempts_count
    }


@router.get("/redirect")
async def shufti_redirect(
    status: Optional[str] = None,
    reference: Optional[str] = None
):
    """
    Endpoint de redirection Shufti Pro.
    Redirige vers le frontend après la vérification.
    """
    frontend_url = settings.FRONTEND_URL
    redirect_target = f"{frontend_url}/dashboard/kyc?status={status or 'completed'}"
    if reference:
        redirect_target += f"&reference={reference}"
    return RedirectResponse(url=redirect_target)


@router.get("/status-detailed")
async def get_kyc_status_detailed(
    *,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user)
):
    """
    Récupérer le statut KYC détaillé de l'utilisateur actuel.
    Synchronise avec Shufti Pro si une vérification est en cours.
    """
    verification = crud_kyc.kyc_verification.get_by_user(db, user_id=current_user.id)
    
    if not verification:
        return {
            "status": None,
            "can_start": True,
            "message": "Aucune vérification KYC trouvée"
        }
    
    # Si en cours, vérifier le statut auprès de Shufti Pro
    if verification.status in [KYCStatus.PENDING, KYCStatus.IN_PROGRESS] and verification.reference_id:
        validity_check = await shufti_pro_service.check_reference_validity(verification.reference_id)
        
        # Mettre à jour le statut si terminé
        if validity_check.get("is_completed"):
            new_status = KYCStatus.APPROVED if validity_check.get("is_accepted") else KYCStatus.REJECTED
            is_ok = bool(validity_check.get("is_accepted"))
            raw = validity_check.get("data") or {}
            flags = kyc_flags_from_shufti_payload(raw if isinstance(raw, dict) else {}, overall_accepted=is_ok)
            update_data = KYCVerificationUpdate(
                status=new_status,
                processed_at=datetime.utcnow(),
                identity_verified=flags["identity_verified"],
                document_verified=flags["document_verified"],
                face_verified=flags["face_verified"],
            )
            crud_kyc.kyc_verification.update(db=db, db_obj=verification, obj_in=update_data)
            verification.status = new_status
            
            # Mettre à jour le user si approuvé
            if new_status == KYCStatus.APPROVED:
                current_user.identity_verified = True
                db.commit()
                payment_accounting.post_kyc_verification_recognition_for_user(db, verification.user_id)
    
    # Déterminer si l'utilisateur peut démarrer/reprendre une vérification
    max_attempts_reached = verification.attempts_count >= verification.max_attempts
    can_restart = verification.status in [
        KYCStatus.REJECTED, 
        KYCStatus.REQUIRES_REVIEW, 
        KYCStatus.EXPIRED
    ] and not max_attempts_reached
    can_continue = verification.status in [KYCStatus.PENDING, KYCStatus.IN_PROGRESS]
    
    # Vérifier le statut de paiement pour les tentatives futures
    available_payments = crud_deposit.deposit.count_valid_deposits_for_product(
        db, user_id=current_user.id, product_code="kyc"
    )
    has_valid_payment = available_payments > 0
    
    # Si can_restart mais pas de paiement, indiquer qu'il faut payer
    needs_payment = can_restart and not has_valid_payment
    
    return {
        "status": verification.status.value if verification.status else None,
        "submitted_at": verification.submitted_at,
        "processed_at": verification.processed_at,
        "rejection_reason": verification.rejection_reason,
        "identity_verified": verification.identity_verified,
        "document_verified": verification.document_verified,
        "face_verified": verification.face_verified,
        "address_verified": verification.address_verified,
        "declared_residential_address": verification.verified_address,
        "can_restart": can_restart and has_valid_payment,  # Ne peut reprendre que si payé
        "can_continue": can_continue,
        "verification_url": verification.verification_url if can_continue else None,
        "attempts_count": verification.attempts_count,
        "max_attempts": verification.max_attempts,
        "attempts_remaining": max(0, verification.max_attempts - verification.attempts_count),
        "max_attempts_reached": max_attempts_reached,
        # Informations de paiement
        "available_payments": available_payments,
        "has_valid_payment": has_valid_payment,
        "needs_payment": needs_payment,
        "kyc_price": KYC_PRICE_USD,
        "kyc_currency": "USD"
    }


@router.post("/submit", response_model=KYCVerification)
def submit_kyc_verification(
    *,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
    kyc_data: KYCSubmissionRequest
) -> KYCVerification:
    """
    Soumettre une nouvelle demande de vérification KYC
    """
    # Vérifier si l'utilisateur a déjà une vérification en cours
    existing_verification = crud_kyc.kyc_verification.get_by_user(db, user_id=current_user.id)
    if existing_verification and existing_verification.status in [KYCStatus.PENDING, KYCStatus.IN_PROGRESS]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Une vérification KYC est déjà en cours pour cet utilisateur"
        )
    
    # Créer la nouvelle vérification
    verification_create = KYCVerificationCreate(
        user_id=current_user.id,
        status=KYCStatus.PENDING,
        verified_first_name=kyc_data.first_name,
        verified_last_name=kyc_data.last_name,
        verified_date_of_birth=kyc_data.date_of_birth,
        verified_nationality=kyc_data.nationality,
        verified_address=kyc_data.address,
        reference_id=f"KYC_{current_user.id}_{int(datetime.utcnow().timestamp())}"
    )
    
    verification = crud_kyc.kyc_verification.create(db=db, obj_in=verification_create)
    
    # Créer le document associé avec les URLs uploadées
    document_create = KYCDocumentCreate(
        verification_id=verification.id,
        document_type=kyc_data.document_type,
        document_number=kyc_data.document_number,
        issuing_country=kyc_data.issuing_country,
        front_image_url=kyc_data.document_front if kyc_data.document_front else None,
        back_image_url=kyc_data.document_back if kyc_data.document_back else None,
        selfie_image_url=kyc_data.selfie if kyc_data.selfie else None
    )
    
    crud_kyc.kyc_document.create(db=db, obj_in=document_create)
    
    return verification


@router.get("/status", response_model=KYCStatusResponse)
def get_kyc_status(
    *,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user)
) -> KYCStatusResponse:
    """
    Récupérer le statut de vérification KYC de l'utilisateur actuel
    Returns 404 if no verification exists (for backward compatibility)
    For a more user-friendly response, use /status-detailed instead
    """
    verification = crud_kyc.kyc_verification.get_by_user(db, user_id=current_user.id)
    if not verification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Aucune vérification KYC trouvée pour cet utilisateur"
        )
    
    return KYCStatusResponse(
        verification_id=verification.id,
        status=verification.status,
        identity_verified=verification.identity_verified,
        address_verified=verification.address_verified,
        document_verified=verification.document_verified,
        face_verified=verification.face_verified,
        submitted_at=verification.submitted_at,
        processed_at=verification.processed_at,
        rejection_reason=verification.rejection_reason,
        expires_at=verification.expires_at
    )


@router.get("/submission", response_model=KYCSubmissionRequest)
def get_kyc_submission(
    *,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user)
) -> KYCSubmissionRequest:
    """
    Récupérer les données de soumission KYC de l'utilisateur actuel
    """
    verification = crud_kyc.kyc_verification.get_by_user(db, user_id=current_user.id)
    if not verification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Aucune vérification KYC trouvée pour cet utilisateur"
        )
    
    # Récupérer le document associé
    documents = crud_kyc.kyc_document.get_by_verification(db, verification_id=verification.id)
    document = documents[0] if documents else None
    
    return KYCSubmissionRequest(
        first_name=verification.verified_first_name or "",
        last_name=verification.verified_last_name or "",
        date_of_birth=verification.verified_date_of_birth or datetime.utcnow(),
        nationality=verification.verified_nationality or "",
        address=verification.verified_address or "",
        document_type=document.document_type if document else DocumentType.PASSPORT,
        document_number=document.document_number or "" if document else "",
        issuing_country=document.issuing_country or "" if document else "",
        document_front=document.front_image_url or "" if document else "",
        document_back=document.back_image_url or "" if document else "",
        selfie=document.selfie_image_url or "" if document else ""
    )


@router.get("/verification/{verification_id}", response_model=KYCVerificationWithDocuments)
def get_kyc_verification(
    *,
    db: Session = Depends(deps.get_db),
    verification_id: int,
    current_user: User = Depends(deps.get_current_active_user)
) -> KYCVerificationWithDocuments:
    """
    Récupérer les détails d'une vérification KYC avec ses documents
    """
    verification = crud_kyc.kyc_verification.get(db, id=verification_id)
    if not verification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vérification KYC non trouvée"
        )
    
    # Vérifier que l'utilisateur peut accéder à cette vérification
    if verification.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès non autorisé à cette vérification"
        )
    
    # Récupérer les documents associés
    documents = crud_kyc.kyc_document.get_by_verification(db, verification_id=verification_id)
    
    return KYCVerificationWithDocuments(
        **verification.__dict__,
        documents=documents
    )


@router.post("/verification/{verification_id}/upload-document")
def upload_kyc_document(
    *,
    db: Session = Depends(deps.get_db),
    verification_id: int,
    current_user: User = Depends(deps.get_current_active_user),
    document_type: DocumentType = Form(...),
    front_image: UploadFile = File(...),
    back_image: Optional[UploadFile] = File(None),
    selfie_image: Optional[UploadFile] = File(None)
):
    """
    Télécharger des documents pour une vérification KYC
    """
    verification = crud_kyc.kyc_verification.get(db, id=verification_id)
    if not verification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vérification KYC non trouvée"
        )
    
    if verification.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès non autorisé à cette vérification"
        )
    
    if verification.status not in [KYCStatus.PENDING, KYCStatus.IN_PROGRESS]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Impossible de télécharger des documents pour cette vérification"
        )
    
    # TODO: Implémenter le stockage des fichiers (S3, local, etc.)
    # Pour l'instant, on simule les URLs
    front_url = f"/uploads/kyc/{verification_id}/{document_type.value}_front_{front_image.filename}"
    back_url = f"/uploads/kyc/{verification_id}/{document_type.value}_back_{back_image.filename}" if back_image else None
    selfie_url = f"/uploads/kyc/{verification_id}/selfie_{selfie_image.filename}" if selfie_image else None
    
    # Mettre à jour ou créer le document
    existing_document = crud_kyc.kyc_document.get_by_type(
        db, verification_id=verification_id, document_type=document_type
    )
    
    if existing_document:
        document_update = KYCDocumentUpdate(
            front_image_url=front_url,
            back_image_url=back_url,
            selfie_image_url=selfie_url
        )
        crud_kyc.kyc_document.update(db=db, db_obj=existing_document, obj_in=document_update)
    else:
        document_create = KYCDocumentCreate(
            verification_id=verification_id,
            document_type=document_type,
            front_image_url=front_url,
            back_image_url=back_url,
            selfie_image_url=selfie_url
        )
        crud_kyc.kyc_document.create(db=db, obj_in=document_create)
    
    # Mettre à jour le statut de la vérification
    if verification.status == KYCStatus.PENDING:
        verification_update = KYCVerificationUpdate(status=KYCStatus.IN_PROGRESS)
        crud_kyc.kyc_verification.update(db=db, db_obj=verification, obj_in=verification_update)
    
    return {"message": "Documents téléchargés avec succès"}


# Endpoints administrateur
@router.get("/admin/verifications", response_model=List[KYCVerification])
def list_kyc_verifications(
    *,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin_user),
    status_filter: Optional[KYCStatus] = None,
    skip: int = 0,
    limit: int = 10
) -> List[KYCVerification]:
    """
    Lister toutes les vérifications KYC (admin seulement)
    """
    if status_filter:
        return crud_kyc.kyc_verification.get_by_status(
            db, status=status_filter, skip=skip, limit=limit
        )
    else:
        return crud_kyc.kyc_verification.get_multi(db, skip=skip, limit=limit)


@router.get("/admin/pending", response_model=List[KYCVerification])
def get_pending_verifications(
    *,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin_user),
    skip: int = 0,
    limit: int = 10
) -> List[KYCVerification]:
    """
    Récupérer les vérifications en attente (admin seulement)
    """
    return crud_kyc.kyc_verification.get_pending_verifications(db, skip=skip, limit=limit)


@router.post("/admin/verification/{verification_id}/approve", response_model=KYCVerification)
def approve_kyc_verification(
    *,
    db: Session = Depends(deps.get_db),
    verification_id: int,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(deps.get_current_admin_user)
) -> KYCVerification:
    """
    Approuver une vérification KYC (admin seulement)
    """
    verification = crud_kyc.kyc_verification.get(db, id=verification_id)
    if not verification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vérification KYC non trouvée"
        )
    
    if verification.status not in [KYCStatus.PENDING, KYCStatus.IN_PROGRESS]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cette vérification ne peut pas être approuvée"
        )
    
    result = crud_kyc.kyc_verification.approve_verification(
        db, verification_id=verification_id, admin_user_id=current_user.id
    )
    payment_accounting.post_kyc_verification_recognition_for_user(db, result.user_id)
    
    # Envoyer l'email de confirmation KYC approuvé
    verified_user = db.query(User).filter(User.id == verification.user_id).first()
    if verified_user:
        user_lang = getattr(verified_user, 'preferred_language', 'fr') or 'fr'
        background_tasks.add_task(
            email_service.send_kyc_approved_email,
            to_email=verified_user.email,
            lang=user_lang
        )
    
    return result


@router.post("/admin/verification/{verification_id}/reject", response_model=KYCVerification)
def reject_kyc_verification(
    *,
    db: Session = Depends(deps.get_db),
    verification_id: int,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(deps.get_current_admin_user),
    reason: str = Form(...),
    details: Optional[str] = Form(None)
) -> KYCVerification:
    """
    Rejeter une vérification KYC (admin seulement)
    """
    verification = crud_kyc.kyc_verification.get(db, id=verification_id)
    if not verification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vérification KYC non trouvée"
        )
    
    if verification.status not in [KYCStatus.PENDING, KYCStatus.IN_PROGRESS]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cette vérification ne peut pas être rejetée"
        )
    
    result = crud_kyc.kyc_verification.reject_verification(
        db, verification_id=verification_id, reason=reason, 
        details=details, admin_user_id=current_user.id
    )
    
    # Envoyer l'email de notification KYC rejeté
    rejected_user = db.query(User).filter(User.id == verification.user_id).first()
    if rejected_user:
        user_lang = getattr(rejected_user, 'preferred_language', 'fr') or 'fr'
        background_tasks.add_task(
            email_service.send_kyc_rejected_email,
            to_email=rejected_user.email,
            reason=reason,
            lang=user_lang
        )
    
    return result


@router.get("/admin/statistics", response_model=KYCStatistics)
def get_kyc_statistics(
    *,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin_user),
    days: int = 30
) -> KYCStatistics:
    """
    Récupérer les statistiques KYC (admin seulement)
    """
    return crud_kyc.kyc_verification.get_statistics(db, days=days)


@router.get("/admin/verification/{verification_id}/audit", response_model=List[KYCAuditLog])
def get_verification_audit_logs(
    *,
    db: Session = Depends(deps.get_db),
    verification_id: int,
    current_user: User = Depends(deps.get_current_admin_user)
) -> List[KYCAuditLog]:
    """
    Récupérer les logs d'audit d'une vérification (admin seulement)
    """
    verification = crud_kyc.kyc_verification.get(db, id=verification_id)
    if not verification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vérification KYC non trouvée"
        )
    
    return crud_kyc.kyc_audit_log.get_by_verification(db, verification_id=verification_id)


# Webhook pour Shufti Pro
@router.post("/webhook/shufti-pro", response_model=KYCWebhookResponse)
def shufti_pro_webhook(
    *,
    db: Session = Depends(deps.get_db),
    webhook_data: ShuftiProWebhookData
):
    """
    Webhook pour recevoir les résultats de Shufti Pro
    """
    # Trouver la vérification par référence
    verification = crud_kyc.kyc_verification.get_by_reference(
        db, reference_id=webhook_data.reference
    )
    
    if not verification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vérification non trouvée"
        )
    
    # Traiter les résultats selon l'événement
    if webhook_data.event == "verification.accepted":
        # Approuver automatiquement
        crud_kyc.kyc_verification.approve_verification(db, verification_id=verification.id)

        wh_raw = webhook_data.model_dump()
        flags = kyc_flags_from_shufti_payload(wh_raw, overall_accepted=True)
        # Mettre à jour avec les données du webhook
        update_data = KYCVerificationUpdate(
            external_verification_id=webhook_data.reference,
            provider_response=str(webhook_data.verification_result),
            webhook_data=str(webhook_data.model_dump()),
            identity_verified=flags["identity_verified"],
            document_verified=flags["document_verified"],
            face_verified=flags["face_verified"],
        )
        crud_kyc.kyc_verification.update(db=db, db_obj=verification, obj_in=update_data)
        payment_accounting.post_kyc_verification_recognition_for_user(db, verification.user_id)
        
    elif webhook_data.event == "verification.declined":
        # Rejeter automatiquement
        reason = webhook_data.declined_reason or "Vérification échouée"
        crud_kyc.kyc_verification.reject_verification(
            db, verification_id=verification.id, reason=reason
        )

        wh_raw = webhook_data.model_dump()
        flags = kyc_flags_from_shufti_payload(wh_raw, overall_accepted=False)
        # Mettre à jour avec les données du webhook
        update_data = KYCVerificationUpdate(
            external_verification_id=webhook_data.reference,
            provider_response=str(webhook_data.verification_result),
            webhook_data=str(webhook_data.model_dump()),
            rejection_reason=reason,
            identity_verified=flags["identity_verified"],
            document_verified=flags["document_verified"],
            face_verified=flags["face_verified"],
        )
        crud_kyc.kyc_verification.update(db=db, db_obj=verification, obj_in=update_data)
        u = db.query(User).filter(User.id == verification.user_id).first()
        if u:
            u.identity_verified = False
            db.add(u)
            db.commit()
    
    return KYCWebhookResponse(
        success=True,
        message="Webhook traité avec succès",
        verification_id=verification.id
    )
