"""
Service d'envoi d'emails pour MYHIGH5
"""
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, List
import logging

from app.core.config import settings
from app.services.email_templates import (
    get_welcome_email,
    get_verify_email,
    get_password_reset_email,
    get_invitation_email,
    get_payment_confirmation_email,
    get_kyc_approved_email,
    get_kyc_rejected_email,
    get_commission_email
)

logger = logging.getLogger(__name__)


class EmailService:
    """Service pour l'envoi d'emails"""
    
    def __init__(self):
        self.smtp_host = settings.SMTP_HOST
        self.smtp_port = settings.SMTP_PORT
        self.smtp_user = settings.SMTP_USER
        self.smtp_password = settings.SMTP_PASSWORD
        self.from_email = settings.SMTP_FROM_EMAIL
        self.from_name = settings.SMTP_FROM_NAME
        self.frontend_url = settings.FRONTEND_URL
    
    def _create_connection(self):
        """Créer une connexion SMTP"""
        try:
            server = smtplib.SMTP(self.smtp_host, self.smtp_port)
            server.starttls()
            if self.smtp_user and self.smtp_password:
                server.login(self.smtp_user, self.smtp_password)
            return server
        except Exception as e:
            logger.error(f"Erreur connexion SMTP: {e}")
            raise
    
    def send_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None
    ) -> bool:
        """
        Envoyer un email
        
        Args:
            to_email: Adresse email du destinataire
            subject: Sujet de l'email
            html_content: Contenu HTML
            text_content: Contenu texte brut (optionnel)
        
        Returns:
            bool: True si envoyé avec succès
        """
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"{self.from_name} <{self.from_email}>"
            msg["To"] = to_email
            
            # Version texte
            if text_content:
                part1 = MIMEText(text_content, "plain")
                msg.attach(part1)
            
            # Version HTML
            part2 = MIMEText(html_content, "html")
            msg.attach(part2)
            
            # Envoyer
            with self._create_connection() as server:
                server.sendmail(self.from_email, to_email, msg.as_string())
            
            logger.info(f"Email envoyé à {to_email}")
            return True
            
        except Exception as e:
            logger.error(f"Erreur envoi email à {to_email}: {e}")
            return False
    
    def send_welcome_email(
        self,
        to_email: str,
        verify_url: str,
        lang: str = "fr"
    ) -> bool:
        """Send welcome email with verification link"""
        subject, html_content, text_content = get_welcome_email(lang, verify_url)
        return self.send_email(to_email, subject, html_content, text_content)
    
    def send_verification_email(
        self,
        to_email: str,
        verify_url: str,
        lang: str = "fr"
    ) -> bool:
        """Send email verification link"""
        subject, html_content, text_content = get_verify_email(lang, verify_url)
        return self.send_email(to_email, subject, html_content, text_content)
    
    def send_password_reset_email(
        self,
        to_email: str,
        reset_url: str,
        lang: str = "fr"
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
        lang: str = "fr"
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
        lang: str = "fr"
    ) -> bool:
        """Send payment confirmation email"""
        subject, html_content, text_content = get_payment_confirmation_email(
            lang, amount, product, reference, date
        )
        return self.send_email(to_email, subject, html_content, text_content)
    
    def send_kyc_approved_email(
        self,
        to_email: str,
        lang: str = "fr"
    ) -> bool:
        """Send KYC approved notification email"""
        subject, html_content, text_content = get_kyc_approved_email(lang)
        return self.send_email(to_email, subject, html_content, text_content)
    
    def send_kyc_rejected_email(
        self,
        to_email: str,
        reason: Optional[str] = None,
        lang: str = "fr"
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
        lang: str = "fr"
    ) -> bool:
        """Send commission notification email"""
        subject, html_content, text_content = get_commission_email(
            lang, amount, commission_type, source_name
        )
        return self.send_email(to_email, subject, html_content, text_content)


# Instance singleton
email_service = EmailService()
