"""
Email Templates with Multi-language Support for MYHIGH5
"""
from typing import Optional

# Email translations
EMAIL_TRANSLATIONS = {
    "fr": {
        # Common
        "company_name": "MYHIGH5",
        "support_email": "support@myhigh5.com",
        "all_rights_reserved": "Tous droits réservés",
        "ignore_email": "Si vous n'avez pas demandé cet email, vous pouvez l'ignorer.",
        
        # Welcome / Registration
        "welcome_subject": "Bienvenue sur MYHIGH5 !",
        "welcome_title": "Bienvenue sur MYHIGH5 !",
        "welcome_message": "Nous sommes ravis de vous accueillir dans notre communauté. Votre compte a été créé avec succès.",
        "welcome_verify": "Pour activer votre compte, veuillez vérifier votre adresse email en cliquant sur le bouton ci-dessous.",
        "verify_email_button": "Vérifier mon email",
        "welcome_features_title": "Ce qui vous attend :",
        "welcome_feature_1": "🏆 Participez à des concours passionnants",
        "welcome_feature_2": "💰 Gagnez des prix et des récompenses",
        "welcome_feature_3": "👥 Construisez votre réseau d'affiliés",
        "welcome_feature_4": "📈 Générez des revenus passifs",
        
        # Email Verification
        "verify_subject": "Vérifiez votre adresse email - MYHIGH5",
        "verify_title": "Vérification de votre email",
        "verify_message": "Cliquez sur le bouton ci-dessous pour vérifier votre adresse email.",
        "verify_expiry": "Ce lien expire dans 24 heures.",
        
        # Password Reset
        "reset_subject": "Réinitialisation de votre mot de passe - MYHIGH5",
        "reset_title": "Réinitialisation du mot de passe",
        "reset_message": "Vous avez demandé à réinitialiser votre mot de passe. Cliquez sur le bouton ci-dessous pour créer un nouveau mot de passe.",
        "reset_button": "Réinitialiser mon mot de passe",
        "reset_expiry": "Ce lien expire dans 1 heure.",
        "reset_ignore": "Si vous n'avez pas demandé cette réinitialisation, ignorez cet email. Votre mot de passe ne sera pas modifié.",
        
        # Invitation
        "invitation_subject": "{inviter_name} vous invite à rejoindre MYHIGH5 !",
        "invitation_title": "Vous avez reçu une invitation !",
        "invitation_message": "<strong style='color: #8B5CF6;'>{inviter_name}</strong> vous invite à rejoindre MYHIGH5, la plateforme où vous pouvez participer à des concours et gagner des prix incroyables !",
        "invitation_button": "Rejoindre MYHIGH5",
        "referral_code_label": "Votre code de parrainage :",
        
        # Payment Confirmation
        "payment_subject": "Confirmation de paiement - MYHIGH5",
        "payment_title": "Paiement confirmé !",
        "payment_message": "Votre paiement de <strong>{amount}</strong> pour <strong>{product}</strong> a été confirmé avec succès.",
        "payment_reference": "Référence :",
        "payment_date": "Date :",
        "payment_thank_you": "Merci pour votre confiance !",
        
        # KYC Verification
        "kyc_approved_subject": "Vérification KYC approuvée - MYHIGH5",
        "kyc_approved_title": "Votre identité a été vérifiée !",
        "kyc_approved_message": "Félicitations ! Votre vérification d'identité (KYC) a été approuvée. Vous avez maintenant accès à toutes les fonctionnalités de la plateforme.",
        
        "kyc_rejected_subject": "Vérification KYC refusée - MYHIGH5",
        "kyc_rejected_title": "Vérification KYC non approuvée",
        "kyc_rejected_message": "Malheureusement, votre vérification d'identité n'a pas été approuvée. Veuillez soumettre à nouveau vos documents.",
        "kyc_rejected_reason": "Raison :",
        
        # Commission
        "commission_subject": "Nouvelle commission reçue - MYHIGH5",
        "commission_title": "Vous avez gagné une commission !",
        "commission_message": "Vous avez reçu une commission de <strong>{amount}</strong> grâce à l'activité de votre réseau.",
        "commission_type": "Type :",
        "commission_from": "Source :",
        
        # Contest
        "contest_approved_subject": "Votre candidature a été approuvée - MYHIGH5",
        "contest_approved_title": "Candidature approuvée !",
        "contest_approved_message": "Votre candidature au concours <strong>{contest_name}</strong> a été approuvée. Bonne chance !",
        
        "contest_rejected_subject": "Candidature refusée - MYHIGH5",
        "contest_rejected_title": "Candidature non approuvée",
        "contest_rejected_message": "Votre candidature au concours <strong>{contest_name}</strong> n'a pas été approuvée.",
    },
    "en": {
        # Common
        "company_name": "MYHIGH5",
        "support_email": "support@myhigh5.com",
        "all_rights_reserved": "All rights reserved",
        "ignore_email": "If you did not request this email, you can ignore it.",
        
        # Welcome / Registration
        "welcome_subject": "Welcome to MYHIGH5!",
        "welcome_title": "Welcome to MYHIGH5!",
        "welcome_message": "We are delighted to welcome you to our community. Your account has been created successfully.",
        "welcome_verify": "To activate your account, please verify your email address by clicking the button below.",
        "verify_email_button": "Verify my email",
        "welcome_features_title": "What awaits you:",
        "welcome_feature_1": "🏆 Participate in exciting contests",
        "welcome_feature_2": "💰 Win prizes and rewards",
        "welcome_feature_3": "👥 Build your affiliate network",
        "welcome_feature_4": "📈 Generate passive income",
        
        # Email Verification
        "verify_subject": "Verify your email address - MYHIGH5",
        "verify_title": "Email Verification",
        "verify_message": "Click the button below to verify your email address.",
        "verify_expiry": "This link expires in 24 hours.",
        
        # Password Reset
        "reset_subject": "Password Reset - MYHIGH5",
        "reset_title": "Password Reset",
        "reset_message": "You requested to reset your password. Click the button below to create a new password.",
        "reset_button": "Reset my password",
        "reset_expiry": "This link expires in 1 hour.",
        "reset_ignore": "If you did not request this reset, please ignore this email. Your password will not be changed.",
        
        # Invitation
        "invitation_subject": "{inviter_name} invites you to join MYHIGH5!",
        "invitation_title": "You've received an invitation!",
        "invitation_message": "<strong style='color: #8B5CF6;'>{inviter_name}</strong> invites you to join MYHIGH5, the platform where you can participate in contests and win amazing prizes!",
        "invitation_button": "Join MYHIGH5",
        "referral_code_label": "Your referral code:",
        
        # Payment Confirmation
        "payment_subject": "Payment Confirmation - MYHIGH5",
        "payment_title": "Payment Confirmed!",
        "payment_message": "Your payment of <strong>{amount}</strong> for <strong>{product}</strong> has been successfully confirmed.",
        "payment_reference": "Reference:",
        "payment_date": "Date:",
        "payment_thank_you": "Thank you for your trust!",
        
        # KYC Verification
        "kyc_approved_subject": "KYC Verification Approved - MYHIGH5",
        "kyc_approved_title": "Your identity has been verified!",
        "kyc_approved_message": "Congratulations! Your identity verification (KYC) has been approved. You now have access to all platform features.",
        
        "kyc_rejected_subject": "KYC Verification Rejected - MYHIGH5",
        "kyc_rejected_title": "KYC Verification Not Approved",
        "kyc_rejected_message": "Unfortunately, your identity verification was not approved. Please submit your documents again.",
        "kyc_rejected_reason": "Reason:",
        
        # Commission
        "commission_subject": "New Commission Received - MYHIGH5",
        "commission_title": "You've earned a commission!",
        "commission_message": "You received a commission of <strong>{amount}</strong> from your network's activity.",
        "commission_type": "Type:",
        "commission_from": "Source:",
        
        # Contest
        "contest_approved_subject": "Your application has been approved - MYHIGH5",
        "contest_approved_title": "Application Approved!",
        "contest_approved_message": "Your application for the contest <strong>{contest_name}</strong> has been approved. Good luck!",
        
        "contest_rejected_subject": "Application Rejected - MYHIGH5",
        "contest_rejected_title": "Application Not Approved",
        "contest_rejected_message": "Your application for the contest <strong>{contest_name}</strong> was not approved.",
    },
    "es": {
        # Common
        "company_name": "MYHIGH5",
        "support_email": "support@myhigh5.com",
        "all_rights_reserved": "Todos los derechos reservados",
        "ignore_email": "Si no solicitó este correo electrónico, puede ignorarlo.",
        
        # Welcome / Registration
        "welcome_subject": "¡Bienvenido a MYHIGH5!",
        "welcome_title": "¡Bienvenido a MYHIGH5!",
        "welcome_message": "Estamos encantados de darte la bienvenida a nuestra comunidad. Tu cuenta ha sido creada exitosamente.",
        "welcome_verify": "Para activar tu cuenta, verifica tu dirección de correo electrónico haciendo clic en el botón de abajo.",
        "verify_email_button": "Verificar mi email",
        "welcome_features_title": "Lo que te espera:",
        "welcome_feature_1": "🏆 Participa en concursos emocionantes",
        "welcome_feature_2": "💰 Gana premios y recompensas",
        "welcome_feature_3": "👥 Construye tu red de afiliados",
        "welcome_feature_4": "📈 Genera ingresos pasivos",
        
        # Email Verification
        "verify_subject": "Verifica tu correo electrónico - MYHIGH5",
        "verify_title": "Verificación de email",
        "verify_message": "Haz clic en el botón de abajo para verificar tu dirección de correo electrónico.",
        "verify_expiry": "Este enlace expira en 24 horas.",
        
        # Password Reset
        "reset_subject": "Restablecimiento de contraseña - MYHIGH5",
        "reset_title": "Restablecimiento de contraseña",
        "reset_message": "Solicitaste restablecer tu contraseña. Haz clic en el botón de abajo para crear una nueva contraseña.",
        "reset_button": "Restablecer mi contraseña",
        "reset_expiry": "Este enlace expira en 1 hora.",
        "reset_ignore": "Si no solicitaste este restablecimiento, ignora este correo. Tu contraseña no será modificada.",
        
        # Invitation
        "invitation_subject": "¡{inviter_name} te invita a unirte a MYHIGH5!",
        "invitation_title": "¡Has recibido una invitación!",
        "invitation_message": "<strong style='color: #8B5CF6;'>{inviter_name}</strong> te invita a unirte a MYHIGH5, la plataforma donde puedes participar en concursos y ganar premios increíbles!",
        "invitation_button": "Unirse a MYHIGH5",
        "referral_code_label": "Tu código de referido:",
        
        # Payment Confirmation
        "payment_subject": "Confirmación de pago - MYHIGH5",
        "payment_title": "¡Pago confirmado!",
        "payment_message": "Tu pago de <strong>{amount}</strong> por <strong>{product}</strong> ha sido confirmado exitosamente.",
        "payment_reference": "Referencia:",
        "payment_date": "Fecha:",
        "payment_thank_you": "¡Gracias por tu confianza!",
        
        # KYC Verification
        "kyc_approved_subject": "Verificación KYC aprobada - MYHIGH5",
        "kyc_approved_title": "¡Tu identidad ha sido verificada!",
        "kyc_approved_message": "¡Felicitaciones! Tu verificación de identidad (KYC) ha sido aprobada. Ahora tienes acceso a todas las funciones de la plataforma.",
        
        "kyc_rejected_subject": "Verificación KYC rechazada - MYHIGH5",
        "kyc_rejected_title": "Verificación KYC no aprobada",
        "kyc_rejected_message": "Lamentablemente, tu verificación de identidad no fue aprobada. Por favor, envía tus documentos nuevamente.",
        "kyc_rejected_reason": "Razón:",
        
        # Commission
        "commission_subject": "Nueva comisión recibida - MYHIGH5",
        "commission_title": "¡Has ganado una comisión!",
        "commission_message": "Recibiste una comisión de <strong>{amount}</strong> gracias a la actividad de tu red.",
        "commission_type": "Tipo:",
        "commission_from": "Fuente:",
        
        # Contest
        "contest_approved_subject": "Tu candidatura ha sido aprobada - MYHIGH5",
        "contest_approved_title": "¡Candidatura aprobada!",
        "contest_approved_message": "Tu candidatura al concurso <strong>{contest_name}</strong> ha sido aprobada. ¡Buena suerte!",
        
        "contest_rejected_subject": "Candidatura rechazada - MYHIGH5",
        "contest_rejected_title": "Candidatura no aprobada",
        "contest_rejected_message": "Tu candidatura al concurso <strong>{contest_name}</strong> no fue aprobada.",
    },
    "de": {
        # Common
        "company_name": "MYHIGH5",
        "support_email": "support@myhigh5.com",
        "all_rights_reserved": "Alle Rechte vorbehalten",
        "ignore_email": "Wenn Sie diese E-Mail nicht angefordert haben, können Sie sie ignorieren.",
        
        # Welcome / Registration
        "welcome_subject": "Willkommen bei MYHIGH5!",
        "welcome_title": "Willkommen bei MYHIGH5!",
        "welcome_message": "Wir freuen uns, Sie in unserer Community begrüßen zu dürfen. Ihr Konto wurde erfolgreich erstellt.",
        "welcome_verify": "Um Ihr Konto zu aktivieren, bestätigen Sie bitte Ihre E-Mail-Adresse, indem Sie auf die Schaltfläche unten klicken.",
        "verify_email_button": "E-Mail bestätigen",
        "welcome_features_title": "Was Sie erwartet:",
        "welcome_feature_1": "🏆 Nehmen Sie an spannenden Wettbewerben teil",
        "welcome_feature_2": "💰 Gewinnen Sie Preise und Belohnungen",
        "welcome_feature_3": "👥 Bauen Sie Ihr Affiliate-Netzwerk auf",
        "welcome_feature_4": "📈 Generieren Sie passives Einkommen",
        
        # Email Verification
        "verify_subject": "Bestätigen Sie Ihre E-Mail-Adresse - MYHIGH5",
        "verify_title": "E-Mail-Bestätigung",
        "verify_message": "Klicken Sie auf die Schaltfläche unten, um Ihre E-Mail-Adresse zu bestätigen.",
        "verify_expiry": "Dieser Link läuft in 24 Stunden ab.",
        
        # Password Reset
        "reset_subject": "Passwort zurücksetzen - MYHIGH5",
        "reset_title": "Passwort zurücksetzen",
        "reset_message": "Sie haben angefordert, Ihr Passwort zurückzusetzen. Klicken Sie auf die Schaltfläche unten, um ein neues Passwort zu erstellen.",
        "reset_button": "Passwort zurücksetzen",
        "reset_expiry": "Dieser Link läuft in 1 Stunde ab.",
        "reset_ignore": "Wenn Sie dieses Zurücksetzen nicht angefordert haben, ignorieren Sie bitte diese E-Mail. Ihr Passwort wird nicht geändert.",
        
        # Invitation
        "invitation_subject": "{inviter_name} lädt Sie ein, MYHIGH5 beizutreten!",
        "invitation_title": "Sie haben eine Einladung erhalten!",
        "invitation_message": "<strong style='color: #8B5CF6;'>{inviter_name}</strong> lädt Sie ein, MYHIGH5 beizutreten, die Plattform, auf der Sie an Wettbewerben teilnehmen und tolle Preise gewinnen können!",
        "invitation_button": "MYHIGH5 beitreten",
        "referral_code_label": "Ihr Empfehlungscode:",
        
        # Payment Confirmation
        "payment_subject": "Zahlungsbestätigung - MYHIGH5",
        "payment_title": "Zahlung bestätigt!",
        "payment_message": "Ihre Zahlung von <strong>{amount}</strong> für <strong>{product}</strong> wurde erfolgreich bestätigt.",
        "payment_reference": "Referenz:",
        "payment_date": "Datum:",
        "payment_thank_you": "Vielen Dank für Ihr Vertrauen!",
        
        # KYC Verification
        "kyc_approved_subject": "KYC-Verifizierung genehmigt - MYHIGH5",
        "kyc_approved_title": "Ihre Identität wurde verifiziert!",
        "kyc_approved_message": "Herzlichen Glückwunsch! Ihre Identitätsprüfung (KYC) wurde genehmigt. Sie haben jetzt Zugang zu allen Plattformfunktionen.",
        
        "kyc_rejected_subject": "KYC-Verifizierung abgelehnt - MYHIGH5",
        "kyc_rejected_title": "KYC-Verifizierung nicht genehmigt",
        "kyc_rejected_message": "Leider wurde Ihre Identitätsprüfung nicht genehmigt. Bitte reichen Sie Ihre Dokumente erneut ein.",
        "kyc_rejected_reason": "Grund:",
        
        # Commission
        "commission_subject": "Neue Provision erhalten - MYHIGH5",
        "commission_title": "Sie haben eine Provision verdient!",
        "commission_message": "Sie haben eine Provision von <strong>{amount}</strong> durch die Aktivität Ihres Netzwerks erhalten.",
        "commission_type": "Typ:",
        "commission_from": "Quelle:",
        
        # Contest
        "contest_approved_subject": "Ihre Bewerbung wurde genehmigt - MYHIGH5",
        "contest_approved_title": "Bewerbung genehmigt!",
        "contest_approved_message": "Ihre Bewerbung für den Wettbewerb <strong>{contest_name}</strong> wurde genehmigt. Viel Glück!",
        
        "contest_rejected_subject": "Bewerbung abgelehnt - MYHIGH5",
        "contest_rejected_title": "Bewerbung nicht genehmigt",
        "contest_rejected_message": "Ihre Bewerbung für den Wettbewerb <strong>{contest_name}</strong> wurde nicht genehmigt.",
    }
}


def get_translation(lang: str, key: str, **kwargs) -> str:
    """Get a translated string with optional formatting"""
    translations = EMAIL_TRANSLATIONS.get(lang, EMAIL_TRANSLATIONS["fr"])
    text = translations.get(key, EMAIL_TRANSLATIONS["fr"].get(key, key))
    if kwargs:
        text = text.format(**kwargs)
    return text


def get_base_email_template(lang: str, title: str, content: str, button_text: Optional[str] = None, button_url: Optional[str] = None) -> str:
    """Generate base HTML email template"""
    t = lambda key, **kwargs: get_translation(lang, key, **kwargs)
    
    button_html = ""
    if button_text and button_url:
        button_html = f"""
            <div style="text-align: center; margin: 32px 0;">
                <a href="{button_url}" 
                   style="display: inline-block; background: linear-gradient(135deg, #8B5CF6, #7C3AED); color: white; text-decoration: none; padding: 16px 40px; border-radius: 12px; font-weight: 600; font-size: 16px; box-shadow: 0 4px 14px rgba(139, 92, 246, 0.4);">
                    {button_text}
                </a>
            </div>
        """
    
    return f"""
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
                <span style="font-size: 32px; line-height: 60px;">🖐️</span>
            </div>
            <h1 style="margin: 0; color: #18181b; font-size: 28px; font-weight: 700;">{t('company_name')}</h1>
        </div>
        
        <!-- Content Card -->
        <div style="background-color: white; border-radius: 16px; padding: 32px; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.05);">
            <h2 style="margin: 0 0 16px 0; color: #18181b; font-size: 24px; font-weight: 600;">
                {title}
            </h2>
            
            <div style="color: #52525b; font-size: 16px; line-height: 1.6;">
                {content}
            </div>
            
            {button_html}
        </div>
        
        <!-- Footer -->
        <div style="text-align: center; margin-top: 32px; color: #a1a1aa; font-size: 14px;">
            <p style="margin: 0 0 8px 0;">
                {t('ignore_email')}
            </p>
            <p style="margin: 0 0 8px 0;">
                {t('support_email')}
            </p>
            <p style="margin: 0;">
                © 2024 {t('company_name')}. {t('all_rights_reserved')}.
            </p>
        </div>
    </div>
</body>
</html>
"""


def get_welcome_email(lang: str, verify_url: str) -> tuple[str, str, str]:
    """Generate welcome email content"""
    t = lambda key, **kwargs: get_translation(lang, key, **kwargs)
    
    content = f"""
        <p style="margin: 0 0 24px 0;">
            {t('welcome_message')}
        </p>
        <p style="margin: 0 0 24px 0;">
            {t('welcome_verify')}
        </p>
        
        <div style="margin-top: 32px;">
            <h3 style="margin: 0 0 16px 0; color: #18181b; font-size: 18px;">{t('welcome_features_title')}</h3>
            <ul style="margin: 0; padding-left: 20px; color: #52525b;">
                <li style="margin-bottom: 8px;">{t('welcome_feature_1')}</li>
                <li style="margin-bottom: 8px;">{t('welcome_feature_2')}</li>
                <li style="margin-bottom: 8px;">{t('welcome_feature_3')}</li>
                <li style="margin-bottom: 8px;">{t('welcome_feature_4')}</li>
            </ul>
        </div>
    """
    
    html = get_base_email_template(
        lang=lang,
        title=t('welcome_title'),
        content=content,
        button_text=t('verify_email_button'),
        button_url=verify_url
    )
    
    text = f"""
{t('welcome_title')}

{t('welcome_message')}

{t('welcome_verify')}

{verify_url}

{t('welcome_features_title')}
- {t('welcome_feature_1')}
- {t('welcome_feature_2')}
- {t('welcome_feature_3')}
- {t('welcome_feature_4')}

© 2024 {t('company_name')}. {t('all_rights_reserved')}.
"""
    
    return t('welcome_subject'), html, text


def get_verify_email(lang: str, verify_url: str) -> tuple[str, str, str]:
    """Generate email verification content"""
    t = lambda key, **kwargs: get_translation(lang, key, **kwargs)
    
    content = f"""
        <p style="margin: 0 0 24px 0;">
            {t('verify_message')}
        </p>
        <p style="margin: 0; color: #a1a1aa; font-size: 14px;">
            {t('verify_expiry')}
        </p>
    """
    
    html = get_base_email_template(
        lang=lang,
        title=t('verify_title'),
        content=content,
        button_text=t('verify_email_button'),
        button_url=verify_url
    )
    
    text = f"""
{t('verify_title')}

{t('verify_message')}

{verify_url}

{t('verify_expiry')}

© 2024 {t('company_name')}. {t('all_rights_reserved')}.
"""
    
    return t('verify_subject'), html, text


def get_password_reset_email(lang: str, reset_url: str) -> tuple[str, str, str]:
    """Generate password reset email content"""
    t = lambda key, **kwargs: get_translation(lang, key, **kwargs)
    
    content = f"""
        <p style="margin: 0 0 24px 0;">
            {t('reset_message')}
        </p>
        <p style="margin: 0 0 16px 0; color: #a1a1aa; font-size: 14px;">
            {t('reset_expiry')}
        </p>
        <p style="margin: 0; color: #a1a1aa; font-size: 14px;">
            {t('reset_ignore')}
        </p>
    """
    
    html = get_base_email_template(
        lang=lang,
        title=t('reset_title'),
        content=content,
        button_text=t('reset_button'),
        button_url=reset_url
    )
    
    text = f"""
{t('reset_title')}

{t('reset_message')}

{reset_url}

{t('reset_expiry')}

{t('reset_ignore')}

© 2024 {t('company_name')}. {t('all_rights_reserved')}.
"""
    
    return t('reset_subject'), html, text


def get_invitation_email(lang: str, inviter_name: str, referral_code: str, referral_link: str, message: Optional[str] = None) -> tuple[str, str, str]:
    """Generate invitation email content"""
    t = lambda key, **kwargs: get_translation(lang, key, **kwargs)
    
    message_html = ""
    if message:
        message_html = f"""
            <div style="background-color: #faf5ff; border-left: 4px solid #8B5CF6; padding: 16px; border-radius: 0 8px 8px 0; margin: 24px 0;">
                <p style="margin: 0; color: #6b21a8; font-style: italic;">"{message}"</p>
            </div>
        """
    
    content = f"""
        <p style="margin: 0 0 24px 0;">
            {t('invitation_message', inviter_name=inviter_name)}
        </p>
        
        {message_html}
        
        <div style="background-color: #f4f4f5; border-radius: 12px; padding: 20px; text-align: center; margin-top: 24px;">
            <p style="margin: 0 0 8px 0; color: #71717a; font-size: 14px;">{t('referral_code_label')}</p>
            <p style="margin: 0; font-family: monospace; font-size: 24px; font-weight: 700; color: #8B5CF6; letter-spacing: 2px;">
                {referral_code}
            </p>
        </div>
        
        <div style="margin-top: 32px;">
            <h3 style="margin: 0 0 16px 0; color: #18181b; font-size: 18px;">{t('welcome_features_title')}</h3>
            <ul style="margin: 0; padding-left: 20px; color: #52525b;">
                <li style="margin-bottom: 8px;">{t('welcome_feature_1')}</li>
                <li style="margin-bottom: 8px;">{t('welcome_feature_2')}</li>
                <li style="margin-bottom: 8px;">{t('welcome_feature_3')}</li>
                <li style="margin-bottom: 8px;">{t('welcome_feature_4')}</li>
            </ul>
        </div>
    """
    
    html = get_base_email_template(
        lang=lang,
        title=t('invitation_title'),
        content=content,
        button_text=t('invitation_button'),
        button_url=referral_link
    )
    
    text = f"""
{t('invitation_subject', inviter_name=inviter_name)}

{inviter_name} {t('invitation_message', inviter_name=inviter_name)}

{f'Message: {message}' if message else ''}

{t('referral_code_label')} {referral_code}

{referral_link}

{t('welcome_features_title')}
- {t('welcome_feature_1')}
- {t('welcome_feature_2')}
- {t('welcome_feature_3')}
- {t('welcome_feature_4')}

© 2024 {t('company_name')}. {t('all_rights_reserved')}.
"""
    
    return t('invitation_subject', inviter_name=inviter_name), html, text


def get_payment_confirmation_email(lang: str, amount: str, product: str, reference: str, date: str) -> tuple[str, str, str]:
    """Generate payment confirmation email content"""
    t = lambda key, **kwargs: get_translation(lang, key, **kwargs)
    
    content = f"""
        <p style="margin: 0 0 24px 0;">
            {t('payment_message', amount=amount, product=product)}
        </p>
        
        <div style="background-color: #f4f4f5; border-radius: 12px; padding: 20px; margin: 24px 0;">
            <p style="margin: 0 0 8px 0; color: #52525b;">
                <strong>{t('payment_reference')}</strong> {reference}
            </p>
            <p style="margin: 0; color: #52525b;">
                <strong>{t('payment_date')}</strong> {date}
            </p>
        </div>
        
        <p style="margin: 0; color: #8B5CF6; font-weight: 600; text-align: center; font-size: 18px;">
            {t('payment_thank_you')}
        </p>
    """
    
    html = get_base_email_template(
        lang=lang,
        title=t('payment_title'),
        content=content
    )
    
    text = f"""
{t('payment_title')}

{t('payment_message', amount=amount, product=product)}

{t('payment_reference')} {reference}
{t('payment_date')} {date}

{t('payment_thank_you')}

© 2024 {t('company_name')}. {t('all_rights_reserved')}.
"""
    
    return t('payment_subject'), html, text


def get_kyc_approved_email(lang: str) -> tuple[str, str, str]:
    """Generate KYC approved email content"""
    t = lambda key, **kwargs: get_translation(lang, key, **kwargs)
    
    content = f"""
        <p style="margin: 0 0 24px 0;">
            {t('kyc_approved_message')}
        </p>
        
        <div style="text-align: center; margin: 24px 0;">
            <span style="font-size: 64px;">✅</span>
        </div>
    """
    
    html = get_base_email_template(
        lang=lang,
        title=t('kyc_approved_title'),
        content=content
    )
    
    text = f"""
{t('kyc_approved_title')}

{t('kyc_approved_message')}

© 2024 {t('company_name')}. {t('all_rights_reserved')}.
"""
    
    return t('kyc_approved_subject'), html, text


def get_kyc_rejected_email(lang: str, reason: Optional[str] = None) -> tuple[str, str, str]:
    """Generate KYC rejected email content"""
    t = lambda key, **kwargs: get_translation(lang, key, **kwargs)
    
    reason_html = ""
    if reason:
        reason_html = f"""
            <div style="background-color: #fef2f2; border-left: 4px solid #ef4444; padding: 16px; border-radius: 0 8px 8px 0; margin: 24px 0;">
                <p style="margin: 0; color: #991b1b;">
                    <strong>{t('kyc_rejected_reason')}</strong> {reason}
                </p>
            </div>
        """
    
    content = f"""
        <p style="margin: 0 0 24px 0;">
            {t('kyc_rejected_message')}
        </p>
        
        {reason_html}
    """
    
    html = get_base_email_template(
        lang=lang,
        title=t('kyc_rejected_title'),
        content=content
    )
    
    text = f"""
{t('kyc_rejected_title')}

{t('kyc_rejected_message')}

{f"{t('kyc_rejected_reason')} {reason}" if reason else ""}

© 2024 {t('company_name')}. {t('all_rights_reserved')}.
"""
    
    return t('kyc_rejected_subject'), html, text


def get_commission_email(lang: str, amount: str, commission_type: str, source_name: str) -> tuple[str, str, str]:
    """Generate commission notification email content"""
    t = lambda key, **kwargs: get_translation(lang, key, **kwargs)
    
    content = f"""
        <p style="margin: 0 0 24px 0;">
            {t('commission_message', amount=amount)}
        </p>
        
        <div style="background-color: #f0fdf4; border-radius: 12px; padding: 20px; margin: 24px 0; text-align: center;">
            <p style="margin: 0; font-size: 36px; font-weight: 700; color: #16a34a;">
                +{amount}
            </p>
        </div>
        
        <div style="background-color: #f4f4f5; border-radius: 12px; padding: 20px;">
            <p style="margin: 0 0 8px 0; color: #52525b;">
                <strong>{t('commission_type')}</strong> {commission_type}
            </p>
            <p style="margin: 0; color: #52525b;">
                <strong>{t('commission_from')}</strong> {source_name}
            </p>
        </div>
    """
    
    html = get_base_email_template(
        lang=lang,
        title=t('commission_title'),
        content=content
    )
    
    text = f"""
{t('commission_title')}

{t('commission_message', amount=amount)}

{t('commission_type')} {commission_type}
{t('commission_from')} {source_name}

© 2024 {t('company_name')}. {t('all_rights_reserved')}.
"""
    
    return t('commission_subject'), html, text
