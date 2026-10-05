"""
Endpoints pour les messages de contact
"""
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Request
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.contact_message import ContactMessageCreate, ContactMessageResponse
from app.crud.crud_contact_message import crud_contact_message

from app.services import email_settings_service
from app.services.email import email_service
from app.services.email_events import EmailEvent
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/contact", response_model=ContactMessageResponse, status_code=status.HTTP_201_CREATED)
def create_contact_message(
    *,
    db: Session = Depends(get_db),
    message_in: ContactMessageCreate,
    background_tasks: BackgroundTasks,
    request: Request
) -> Any:
    """
    Créer un nouveau message de contact
    
    Le message sera stocké en base de données et un email de notification
    sera envoyé à infos@myhigh5.com
    """
    # Valider la catégorie
    valid_categories = ["general", "billing", "account", "technical", "partnership", "other"]
    if message_in.category not in valid_categories:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Catégorie invalide. Catégories valides: {', '.join(valid_categories)}"
        )
    
    try:
        # Créer le message en base de données
        message = crud_contact_message.create(
            db,
            obj_in=message_in.dict()
        )
        
        logger.info(f"Message de contact créé avec succès: ID {message.id}")
        
        # Déterminer la langue depuis les headers Accept-Language
        sender_lang = "en"  # Par défaut
        accept_language = request.headers.get("Accept-Language", "")
        if accept_language:
            # Extraire la première langue (ex: "fr-FR,fr;q=0.9" -> "fr")
            lang_code = accept_language.split(",")[0].split(";")[0].split("-")[0].lower()
            if lang_code in ["fr", "en", "es", "de"]:
                sender_lang = lang_code
        
        logger.info(f"Langue détectée pour l'email de confirmation: {sender_lang}")
        
        details = {
            "name": message_in.name,
            "email": str(message_in.email),
            "subject": message_in.subject,
            "category": message_in.category,
            "message": message_in.message,
        }
        # Notification to the support address (Admin > Email Settings; the
        # platform address by default). Always in English.
        email_service.enqueue(
            db,
            event=EmailEvent.ADMIN_CONTACT_MESSAGE,
            recipient=email_settings_service.support_address(email_settings_service.get_settings(db)),
            context=details,
            idempotency_key=f"admin.contact_message:{message.id}",
        )
        # Confirmation to the sender.
        email_service.enqueue(
            db,
            event=EmailEvent.SUPPORT_CONTACT_CONFIRMATION,
            recipient=str(message_in.email),
            lang=sender_lang,
            context=details,
            idempotency_key=f"support.contact_confirmation:{message.id}",
        )

        return message
        
    except Exception as e:
        logger.error(f"Erreur lors de la création du message de contact: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Une erreur est survenue lors de l'enregistrement de votre message. Veuillez réessayer."
        )

