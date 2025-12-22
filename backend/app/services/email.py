"""
Service d'envoi d'emails pour MYHIGH5 via Resend API
"""
import resend
from typing import Optional, List
import logging

from app.core.config import settings
from app.services.email_templates import (
    get_welcome_email,
    get_verify_email,
    get_password_reset_email,
    get_password_change_security_email,
    get_invitation_email,
    get_payment_confirmation_email,
    get_kyc_approved_email,
    get_kyc_rejected_email,
    get_commission_email
)

logger = logging.getLogger(__name__)


class EmailService:
    """Service pour l'envoi d'emails via Resend API"""
    
    def __init__(self):
        self.api_key = settings.RESEND_API_KEY
        self.from_email = settings.EMAIL_FROM
        self.from_name = settings.EMAIL_FROM_NAME
        self.frontend_url = settings.FRONTEND_URL
        
        # Configurer Resend
        if self.api_key:
            resend.api_key = self.api_key
    
    def send_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None
    ) -> bool:
        """
        Envoyer un email via Resend API
        
        Args:
            to_email: Adresse email du destinataire
            subject: Sujet de l'email
            html_content: Contenu HTML
            text_content: Contenu texte brut (optionnel)
        
        Returns:
            bool: True si envoyé avec succès
        """
        if not self.api_key:
            logger.warning("RESEND_API_KEY non configurée - email non envoyé")
            return False
            
        try:
            params = {
                "from": self.from_email,
                "to": [to_email],
                "subject": subject,
                "html": html_content,
            }
            
            # Ajouter le texte brut si fourni
            if text_content:
                params["text"] = text_content
            
            # Envoyer via Resend
            response = resend.Emails.send(params)
            
            logger.info(f"Email envoyé à {to_email} - ID: {response.get('id', 'N/A')}")
            return True
            
        except Exception as e:
            logger.error(f"Erreur envoi email à {to_email}: {e}")
            return False
    
    def send_batch_emails(
        self,
        emails: List[dict]
    ) -> bool:
        """
        Envoyer plusieurs emails en batch via Resend API
        
        Args:
            emails: Liste de dictionnaires avec to, subject, html, text (optionnel)
        
        Returns:
            bool: True si tous envoyés avec succès
        """
        if not self.api_key:
            logger.warning("RESEND_API_KEY non configurée - emails non envoyés")
            return False
            
        try:
            batch_params = []
            for email in emails:
                param = {
                    "from": self.from_email,
                    "to": [email["to"]],
                    "subject": email["subject"],
                    "html": email["html"],
                }
                if email.get("text"):
                    param["text"] = email["text"]
                batch_params.append(param)
            
            # Envoyer en batch
            response = resend.Batch.send(batch_params)
            
            logger.info(f"Batch de {len(emails)} emails envoyé")
            return True
            
        except Exception as e:
            logger.error(f"Erreur envoi batch emails: {e}")
            return False
    
    def send_welcome_email(
        self,
        to_email: str,
        verify_url: str,
        lang: str = "en"
    ) -> bool:
        """Send welcome email with verification link"""
        subject, html_content, text_content = get_welcome_email(lang, verify_url)
        return self.send_email(to_email, subject, html_content, text_content)
    
    def send_verification_email(
        self,
        to_email: str,
        verify_url: str,
        lang: str = "en"
    ) -> bool:
        """Send email verification link"""
        subject, html_content, text_content = get_verify_email(lang, verify_url)
        return self.send_email(to_email, subject, html_content, text_content)
    
    def send_password_reset_email(
        self,
        to_email: str,
        reset_url: str,
        lang: str = "en"
    ) -> bool:
        """Send password reset email"""
        subject, html_content, text_content = get_password_reset_email(lang, reset_url)
        return self.send_email(to_email, subject, html_content, text_content)
    
    def send_invitation_email(
        self,
        to_email: str,
        inviter_name: str,
        referral_code: str,
        message: Optional[str] = None,
        lang: str = "en"
    ) -> bool:
        """Send referral invitation email"""
        referral_link = f"{self.frontend_url}/?ref={referral_code}"
        subject, html_content, text_content = get_invitation_email(
            lang, inviter_name, referral_code, referral_link, message
        )
        return self.send_email(to_email, subject, html_content, text_content)
    
    def send_payment_confirmation_email(
        self,
        to_email: str,
        amount: str,
        product: str,
        reference: str,
        date: str,
        lang: str = "en"
    ) -> bool:
        """Send payment confirmation email"""
        subject, html_content, text_content = get_payment_confirmation_email(
            lang, amount, product, reference, date
        )
        return self.send_email(to_email, subject, html_content, text_content)
    
    def send_kyc_approved_email(
        self,
        to_email: str,
        lang: str = "en"
    ) -> bool:
        """Send KYC approved notification email"""
        subject, html_content, text_content = get_kyc_approved_email(lang)
        return self.send_email(to_email, subject, html_content, text_content)
    
    def send_kyc_rejected_email(
        self,
        to_email: str,
        reason: Optional[str] = None,
        lang: str = "en"
    ) -> bool:
        """Send KYC rejected notification email"""
        subject, html_content, text_content = get_kyc_rejected_email(lang, reason)
        return self.send_email(to_email, subject, html_content, text_content)
    
    def send_commission_email(
        self,
        to_email: str,
        amount: str,
        commission_type: str,
        source_name: str,
        lang: str = "en"
    ) -> bool:
        """Send commission notification email"""
        subject, html_content, text_content = get_commission_email(
            lang, amount, commission_type, source_name
        )
        return self.send_email(to_email, subject, html_content, text_content)
    
    def send_password_change_security_email(
        self,
        to_email: str,
        support_url: Optional[str] = None,
        lang: str = "en",
        ip_address: Optional[str] = None,
        location: Optional[str] = None
    ) -> bool:
        """Send password change security notification email"""
        subject, html_content, text_content = get_password_change_security_email(
            lang, support_url, ip_address, location
        )
        return self.send_email(to_email, subject, html_content, text_content)


# Instance singleton
email_service = EmailService()
