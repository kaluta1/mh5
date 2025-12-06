"""
Service d'envoi d'emails pour MyHigh5
"""
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, List
import logging

from app.core.config import settings

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
    
    def send_invitation_email(
        self,
        to_email: str,
        inviter_name: str,
        referral_code: str,
        message: Optional[str] = None
    ) -> bool:
        """
        Envoyer un email d'invitation de parrainage
        
        Args:
            to_email: Email du destinataire
            inviter_name: Nom de l'inviteur
            referral_code: Code de parrainage
            message: Message personnalisé (optionnel)
        
        Returns:
            bool: True si envoyé avec succès
        """
        referral_link = f"{self.frontend_url}/?ref={referral_code}"
        
        subject = f"{inviter_name} vous invite à rejoindre MyHigh5 !"
        
        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f4f4f5;">
    <div style="max-width: 600px; margin: 0 auto; padding: 40px 20px;">
        <!-- Header -->
        <div style="text-align: center; margin-bottom: 32px;">
            <div style="display: inline-block; width: 60px; height: 60px; background: linear-gradient(135deg, #8B5CF6, #EC4899); border-radius: 16px; margin-bottom: 16px;">
                <span style="font-size: 32px; line-height: 60px;">💜</span>
            </div>
            <h1 style="margin: 0; color: #18181b; font-size: 28px; font-weight: 700;">MyHigh5</h1>
        </div>
        
        <!-- Content Card -->
        <div style="background-color: white; border-radius: 16px; padding: 32px; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.05);">
            <h2 style="margin: 0 0 16px 0; color: #18181b; font-size: 24px; font-weight: 600;">
                Vous avez reçu une invitation !
            </h2>
            
            <p style="color: #52525b; font-size: 16px; line-height: 1.6; margin: 0 0 24px 0;">
                <strong style="color: #8B5CF6;">{inviter_name}</strong> vous invite à rejoindre MyHigh5, 
                la plateforme où vous pouvez participer à des concours et gagner des prix incroyables !
            </p>
            
            {f'<div style="background-color: #faf5ff; border-left: 4px solid #8B5CF6; padding: 16px; border-radius: 0 8px 8px 0; margin-bottom: 24px;"><p style="margin: 0; color: #6b21a8; font-style: italic;">"{message}"</p></div>' if message else ''}
            
            <!-- CTA Button -->
            <div style="text-align: center; margin: 32px 0;">
                <a href="{referral_link}" 
                   style="display: inline-block; background: linear-gradient(135deg, #8B5CF6, #7C3AED); color: white; text-decoration: none; padding: 16px 40px; border-radius: 12px; font-weight: 600; font-size: 16px; box-shadow: 0 4px 14px rgba(139, 92, 246, 0.4);">
                    Rejoindre MyHigh5
                </a>
            </div>
            
            <!-- Referral Code -->
            <div style="background-color: #f4f4f5; border-radius: 12px; padding: 20px; text-align: center;">
                <p style="margin: 0 0 8px 0; color: #71717a; font-size: 14px;">Votre code de parrainage :</p>
                <p style="margin: 0; font-family: monospace; font-size: 24px; font-weight: 700; color: #8B5CF6; letter-spacing: 2px;">
                    {referral_code}
                </p>
            </div>
            
            <!-- Benefits -->
            <div style="margin-top: 32px;">
                <h3 style="margin: 0 0 16px 0; color: #18181b; font-size: 18px;">Ce qui vous attend :</h3>
                <ul style="margin: 0; padding-left: 20px; color: #52525b;">
                    <li style="margin-bottom: 8px;">🏆 Participez à des concours passionnants</li>
                    <li style="margin-bottom: 8px;">💰 Gagnez des prix et des récompenses</li>
                    <li style="margin-bottom: 8px;">👥 Construisez votre réseau d'affiliés</li>
                    <li style="margin-bottom: 8px;">📈 Générez des revenus passifs</li>
                </ul>
            </div>
        </div>
        
        <!-- Footer -->
        <div style="text-align: center; margin-top: 32px; color: #a1a1aa; font-size: 14px;">
            <p style="margin: 0 0 8px 0;">
                Si vous n'avez pas demandé cette invitation, vous pouvez ignorer cet email.
            </p>
            <p style="margin: 0;">
                © 2024 MyHigh5. Tous droits réservés.
            </p>
        </div>
    </div>
</body>
</html>
"""
        
        text_content = f"""
{inviter_name} vous invite à rejoindre MyHigh5 !

{f'Message de {inviter_name}: {message}' if message else ''}

Rejoignez MyHigh5 et participez à des concours passionnants !

Cliquez ici pour vous inscrire: {referral_link}

Votre code de parrainage: {referral_code}

Ce qui vous attend:
- Participez à des concours passionnants
- Gagnez des prix et des récompenses
- Construisez votre réseau d'affiliés
- Générez des revenus passifs

© 2024 MyHigh5. Tous droits réservés.
"""
        
        return self.send_email(to_email, subject, html_content, text_content)


# Instance singleton
email_service = EmailService()
