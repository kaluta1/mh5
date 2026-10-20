"""
Endpoints pour les abonnements à la newsletter
"""
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Request
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.newsletter import NewsletterSubscriptionCreate, NewsletterSubscriptionResponse
from app.crud.crud_newsletter import crud_newsletter
from datetime import datetime

from app.core.redaction import mask_email
from app.services.email import email_service
from app.services.email_events import EmailEvent
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


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
        
        logger.info("Abonnement newsletter créé: %s", mask_email(subscription.email))
        
        # The site is English-only: confirmation emails are always in English.
        subscriber_lang = "en"
        
        logger.info(f"Langue détectée pour l'email de confirmation: {subscriber_lang}")
        
        # One confirmation per subscription and day: subscribing the same
        # address again and again cannot be used to flood a mailbox.
        email_service.enqueue(
            db,
            event=EmailEvent.SUPPORT_NEWSLETTER_CONFIRMATION,
            recipient=subscription.email,
            lang=subscriber_lang,
            idempotency_key=f"support.newsletter_confirmation:{subscription.id}:{datetime.utcnow():%Y%m%d}",
        )
        
        return subscription
        
    except Exception as e:
        logger.error(f"Erreur lors de la création de l'abonnement newsletter: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Your subscription could not be saved. Please try again."
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
                detail="Email not found in our subscriptions."
            )
        
        logger.info(f"Abonnement newsletter désactivé: {email}")
        return {"message": "You have been unsubscribed from the newsletter."}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur lors de la désinscription: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unsubscribe failed. Please try again."
        )

