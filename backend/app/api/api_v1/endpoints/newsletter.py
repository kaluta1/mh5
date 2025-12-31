"""
Endpoints pour les abonnements à la newsletter
"""
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Request
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.newsletter import NewsletterSubscriptionCreate, NewsletterSubscriptionResponse
from app.crud.crud_newsletter import crud_newsletter
from app.services.email import email_service
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


def send_newsletter_subscription_email(
    email: str,
    lang: str = "en"
):
    """Envoyer un email de confirmation de souscription à la newsletter"""
    try:
        email_service.send_newsletter_subscription_email(
            to_email=email,
            lang=lang
        )
        logger.info(f"Email de confirmation newsletter envoyé à {email}")
    except Exception as e:
        logger.error(f"Erreur lors de l'envoi de l'email de confirmation newsletter à {email}: {e}")


@router.post("/subscribe", response_model=NewsletterSubscriptionResponse, status_code=status.HTTP_201_CREATED)
def subscribe_to_newsletter(
    *,
    db: Session = Depends(get_db),
    subscription_in: NewsletterSubscriptionCreate,
    background_tasks: BackgroundTasks,
    request: Request
) -> Any:
    """
    S'abonner à la newsletter
    
    Enregistre l'email, les informations de l'appareil et de localisation,
    puis envoie un email de confirmation.
    """
    try:
        # Créer l'abonnement
        subscription = crud_newsletter.create(
            db,
            obj_in=subscription_in.dict()
        )
        
        logger.info(f"Abonnement newsletter créé: {subscription.email}")
        
        # Déterminer la langue depuis les headers Accept-Language
        subscriber_lang = "en"  # Par défaut
        accept_language = request.headers.get("Accept-Language", "")
        if accept_language:
            # Extraire la première langue (ex: "fr-FR,fr;q=0.9" -> "fr")
            lang_code = accept_language.split(",")[0].split(";")[0].split("-")[0].lower()
            if lang_code in ["fr", "en", "es", "de"]:
                subscriber_lang = lang_code
        
        logger.info(f"Langue détectée pour l'email de confirmation: {subscriber_lang}")
        
        # Envoyer l'email de confirmation en arrière-plan
        background_tasks.add_task(
            send_newsletter_subscription_email,
            email=subscription.email,
            lang=subscriber_lang
        )
        
        return subscription
        
    except Exception as e:
        logger.error(f"Erreur lors de la création de l'abonnement newsletter: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Une erreur est survenue lors de l'enregistrement de votre abonnement. Veuillez réessayer."
        )


@router.post("/unsubscribe", status_code=status.HTTP_200_OK)
def unsubscribe_from_newsletter(
    *,
    db: Session = Depends(get_db),
    email: str
) -> Any:
    """
    Se désinscrire de la newsletter
    """
    try:
        subscription = crud_newsletter.unsubscribe(db, email=email)
        if not subscription:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Email non trouvé dans nos abonnements."
            )
        
        logger.info(f"Abonnement newsletter désactivé: {email}")
        return {"message": "Vous avez été désinscrit de la newsletter avec succès."}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur lors de la désinscription: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Une erreur est survenue lors de la désinscription. Veuillez réessayer."
        )

