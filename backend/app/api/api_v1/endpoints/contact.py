"""
Endpoints pour les messages de contact
"""
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Request
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.contact_message import ContactMessageCreate, ContactMessageResponse
from app.crud.crud_contact_message import crud_contact_message
from app.services.email import email_service
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


def send_contact_email_notification(
    name: str,
    email: str,
    subject: str,
    category: str,
    message: str
):
    """Envoyer un email de notification pour un nouveau message de contact (toujours en anglais)"""
    try:
        # Email destinataire
        recipient_email = "enquiries@digitalshoppingmall.net"
        
        # Traduire la catégorie en anglais
        category_translations = {
            "general": "General help",
            "billing": "Billing",
            "account": "Account",
            "technical": "Technical support",
            "partnership": "Partnership",
            "other": "Other"
        }
        category_display = category_translations.get(category, category)
        
        # Construire le contenu HTML de l'email (toujours en anglais)
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background-color: #4F46E5; color: white; padding: 20px; border-radius: 5px 5px 0 0; }}
                .content {{ background-color: #f9f9f9; padding: 20px; border: 1px solid #ddd; }}
                .field {{ margin-bottom: 15px; }}
                .label {{ font-weight: bold; color: #555; }}
                .value {{ margin-top: 5px; padding: 10px; background-color: white; border-radius: 3px; }}
                .footer {{ margin-top: 20px; padding-top: 20px; border-top: 1px solid #ddd; font-size: 12px; color: #777; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>New Contact Message - MyHigh5</h2>
                </div>
                <div class="content">
                    <div class="field">
                        <div class="label">Name:</div>
                        <div class="value">{name}</div>
                    </div>
                    <div class="field">
                        <div class="label">Email:</div>
                        <div class="value">{email}</div>
                    </div>
                    <div class="field">
                        <div class="label">Category:</div>
                        <div class="value">{category_display}</div>
                    </div>
                    <div class="field">
                        <div class="label">Subject:</div>
                        <div class="value">{subject}</div>
                    </div>
                    <div class="field">
                        <div class="label">Message:</div>
                        <div class="value">{message.replace(chr(10), '<br>')}</div>
                    </div>
                </div>
                <div class="footer">
                    <p>This message was sent from the MyHigh5 contact form.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Contenu texte brut (toujours en anglais)
        text_content = f"""
New Contact Message - MyHigh5

Name: {name}
Email: {email}
Category: {category_display}
Subject: {subject}

Message:
{message}

---
This message was sent from the MyHigh5 contact form.
        """
        
        # Envoyer l'email
        email_service.send_email(
            to_email=recipient_email,
            subject=f"[MyHigh5 Contact] {subject}",
            html_content=html_content,
            text_content=text_content
        )
        
        logger.info(f"Email de notification de contact envoyé à {recipient_email} pour le message de {email}")
        
    except Exception as e:
        logger.error(f"Erreur lors de l'envoi de l'email de notification de contact: {e}")


def send_contact_confirmation_to_sender(
    name: str,
    email: str,
    subject: str,
    category: str,
    message: str,
    lang: str = "en"
):
    """Envoyer un email de confirmation à l'expéditeur du message de contact"""
    try:
        email_service.send_contact_confirmation_email(
            to_email=email,
            name=name,
            subject=subject,
            category=category,
            message=message,
            lang=lang
        )
        
        logger.info(f"Email de confirmation de contact envoyé à {email}")
        
    except Exception as e:
        logger.error(f"Erreur lors de l'envoi de l'email de confirmation de contact: {e}")


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
    sera envoyé à enquiries@digitalshoppingmall.net
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
        
        # Envoyer l'email de notification à enquiries@digitalshoppingmall.net en arrière-plan
        background_tasks.add_task(
            send_contact_email_notification,
            name=message_in.name,
            email=message_in.email,
            subject=message_in.subject,
            category=message_in.category,
            message=message_in.message
        )
        
        # Envoyer l'email de confirmation à l'expéditeur en arrière-plan
        background_tasks.add_task(
            send_contact_confirmation_to_sender,
            name=message_in.name,
            email=message_in.email,
            subject=message_in.subject,
            category=message_in.category,
            message=message_in.message,
            lang=sender_lang
        )
        
        return message
        
    except Exception as e:
        logger.error(f"Erreur lors de la création du message de contact: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Une erreur est survenue lors de l'enregistrement de votre message. Veuillez réessayer."
        )

