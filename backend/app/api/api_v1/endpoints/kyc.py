from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.orm import Session
from datetime import datetime

from app.api import deps
from app.crud import crud_kyc
from app.models.user import User
from app.models.kyc import KYCStatus, DocumentType
from app.schemas.kyc import (
    KYCVerification, KYCVerificationCreate, KYCVerificationUpdate,
    KYCDocument, KYCDocumentCreate, KYCDocumentUpdate,
    KYCAuditLog, KYCSubmissionRequest, KYCStatusResponse,
    KYCStatistics, KYCVerificationWithDocuments, KYCVerificationComplete,
    ShuftiProWebhookData, KYCWebhookResponse
)

router = APIRouter()


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
    limit: int = 100
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
    limit: int = 100
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
    
    return crud_kyc.kyc_verification.approve_verification(
        db, verification_id=verification_id, admin_user_id=current_user.id
    )


@router.post("/admin/verification/{verification_id}/reject", response_model=KYCVerification)
def reject_kyc_verification(
    *,
    db: Session = Depends(deps.get_db),
    verification_id: int,
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
    
    return crud_kyc.kyc_verification.reject_verification(
        db, verification_id=verification_id, reason=reason, 
        details=details, admin_user_id=current_user.id
    )


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
        
        # Mettre à jour avec les données du webhook
        update_data = KYCVerificationUpdate(
            external_verification_id=webhook_data.reference,
            provider_response=str(webhook_data.verification_result),
            webhook_data=str(webhook_data.dict()),
            identity_verified=True,
            document_verified=True,
            face_verified=True
        )
        crud_kyc.kyc_verification.update(db=db, db_obj=verification, obj_in=update_data)
        
    elif webhook_data.event == "verification.declined":
        # Rejeter automatiquement
        reason = webhook_data.declined_reason or "Vérification échouée"
        crud_kyc.kyc_verification.reject_verification(
            db, verification_id=verification.id, reason=reason
        )
        
        # Mettre à jour avec les données du webhook
        update_data = KYCVerificationUpdate(
            external_verification_id=webhook_data.reference,
            provider_response=str(webhook_data.verification_result),
            webhook_data=str(webhook_data.dict()),
            rejection_reason=reason
        )
        crud_kyc.kyc_verification.update(db=db, db_obj=verification, obj_in=update_data)
    
    return KYCWebhookResponse(
        success=True,
        message="Webhook traité avec succès",
        verification_id=verification.id
    )
