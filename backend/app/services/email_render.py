"""Event -> (subject, html, text) rendering for the outbox worker (EMAIL-1).

Rendering happens when a delivery is SENT, not when it is queued, from the
small encrypted context stored with the delivery. Stateless links (email
verification, password reset) are created here, at send time, so those tokens
are never stored anywhere. Templates are source controlled; every dynamic
value is escaped by the template helpers.
"""
from __future__ import annotations

from typing import Callable, Dict, Optional, Tuple

from sqlalchemy.orm import Session

from app.core.public_urls import public_site_base
from app.services import email_templates as tpl
from app.services.email_events import TEST_EMAIL_KEY, EmailEvent

Rendered = Tuple[str, str, Optional[str]]


class RenderError(Exception):
    """The delivery can no longer be rendered (e.g. the account is gone)."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _simple(lang: str, title: str, paragraphs, *, button_text: Optional[str] = None,
            button_url: Optional[str] = None, subject: Optional[str] = None) -> Rendered:
    """Layout for messages without a dedicated template. `paragraphs` are plain
    strings; they are escaped here."""
    content = "".join(f'<p style="margin: 0 0 16px 0;">{tpl.esc_multiline(p)}</p>' for p in paragraphs if p)
    html = tpl.get_base_email_template(lang=lang, title=title, content=content, button_text=button_text,
                                       button_url=button_url)
    lines = [title, ""] + [str(p) for p in paragraphs if p]
    if button_url:
        lines += ["", str(button_url)]
    lines += ["", f"© {tpl.current_year()} MyHigh5."]
    return subject or title, html, "\n".join(lines) + "\n"


def _user(db: Session, user_id: Optional[int]):
    from app.models.user import User

    user = db.query(User).filter(User.id == user_id).first() if user_id else None
    if user is None or not user.is_active:
        raise RenderError("recipient_gone")
    return user


def _verification(db: Session, to: str, user_id: Optional[int], ctx: dict, lang: str) -> Rendered:
    from app.core.security import create_email_verification_token

    verify_url = f"{public_site_base()}/verify-email?token={create_email_verification_token(to)}"
    return tpl.get_welcome_email(lang, verify_url)


def _password_reset(db: Session, to: str, user_id: Optional[int], ctx: dict, lang: str) -> Rendered:
    from app.core.security import create_password_reset_token

    user = _user(db, user_id)
    reset_url = f"{public_site_base()}/reset-password?token={create_password_reset_token(user.email, user.hashed_password)}"
    return tpl.get_password_reset_email(lang, reset_url)


def _password_changed(db: Session, to: str, user_id: Optional[int], ctx: dict, lang: str) -> Rendered:
    return tpl.get_password_change_security_email(lang, f"{public_site_base()}/contact", ctx.get("ip_address"), None)


def _guardian_request(db: Session, to: str, user_id: Optional[int], ctx: dict, lang: str) -> Rendered:
    # The single-use token rides in the URL fragment, which browsers never send
    # to a server. No password, DOB or age: only the chosen username.
    link = f"{public_site_base()}/guardian/consent#token={ctx['token']}"
    who = ctx.get("username") or "a young person"
    return _simple("en", "Parent or guardian approval requested", [
        f"Someone using the username {who} asked to create a MyHigh5 account and named you as their parent "
        "or legal guardian.",
        "If this is correct, you can review the request and choose exactly what you consent to. If you do not "
        "recognise this request, you can decline it or simply ignore this email.",
        "This link can be used once and expires automatically.",
    ], button_text="Review the request", button_url=link, subject="MyHigh5: parent or guardian approval requested")


def _guardian_completion(db: Session, to: str, user_id: Optional[int], ctx: dict, lang: str) -> Rendered:
    link = f"{public_site_base()}/register/complete#token={ctx['token']}"
    return _simple("en", "Finish creating your account", [
        "Your parent or guardian approval for your MyHigh5 account request has been recorded and verified.",
        "This link can be used once and expires automatically.",
    ], button_text="Finish creating your account", button_url=link,
        subject="MyHigh5: finish creating your account")


def _kyc_approved(db, to, user_id, ctx, lang) -> Rendered:
    return tpl.get_kyc_approved_email(lang)


def _kyc_rejected(db, to, user_id, ctx, lang) -> Rendered:
    return tpl.get_kyc_rejected_email(lang, ctx.get("reason"))


def _payment_confirmed(db, to, user_id, ctx, lang) -> Rendered:
    return tpl.get_payment_confirmation_email(lang, ctx.get("amount", ""), ctx.get("product", ""),
                                              ctx.get("reference", ""), ctx.get("date", ""))


def _invitation(db, to, user_id, ctx, lang) -> Rendered:
    code = ctx.get("referral_code", "")
    from urllib.parse import quote

    return tpl.get_invitation_email(lang, ctx.get("inviter_name", ""), code,
                                    f"{public_site_base()}/r/{quote(str(code), safe='')}", ctx.get("message"))


def _content_report(db, to, user_id, ctx, lang) -> Rendered:
    report_id = ctx.get("report_id")
    return tpl.get_contestant_report_email(
        lang=lang, contestant_title=ctx.get("contestant_title", ""),
        contestant_author_name=ctx.get("author_name", ""), contest_name=ctx.get("contest_name", ""),
        reporter_name=ctx.get("reporter_name", ""), reason=ctx.get("reason", ""),
        description=ctx.get("description") or "", report_id=report_id,
        admin_url=f"{public_site_base()}/admin/reports/{int(report_id)}" if report_id is not None else None)


_CONTACT_CATEGORIES = {"general": "General help", "billing": "Billing", "account": "Account",
                       "technical": "Technical support", "partnership": "Partnership", "other": "Other"}


def _contact_message(db, to, user_id, ctx, lang) -> Rendered:
    category = _CONTACT_CATEGORIES.get(ctx.get("category"), ctx.get("category") or "")
    subject = str(ctx.get("subject") or "").replace("\r", " ").replace("\n", " ")
    return _simple("en", "New contact message", [
        f"Name: {ctx.get('name', '')}",
        f"Email: {ctx.get('email', '')}",
        f"Category: {category}",
        f"Subject: {subject}",
        f"Message:\n{ctx.get('message', '')}",
        "This message was sent from the MyHigh5 contact form.",
    ], subject=f"[MyHigh5 Contact] {subject}"[:200])


def _contact_confirmation(db, to, user_id, ctx, lang) -> Rendered:
    return tpl.get_contact_confirmation_email(lang, ctx.get("name", ""), ctx.get("subject", ""),
                                              ctx.get("category", ""), ctx.get("message", ""))


def _newsletter(db, to, user_id, ctx, lang) -> Rendered:
    return tpl.get_newsletter_subscription_email(lang, None)


def _test_email(db, to, user_id, ctx, lang) -> Rendered:
    return _simple("en", "MyHigh5 test email", [
        "This is a TEST message sent from Admin > Email Settings to check the email configuration.",
        "It is not related to any account activity. No action is needed.",
    ], subject="[TEST] MyHigh5 email configuration test")


RENDERERS: Dict[str, Callable[..., Rendered]] = {
    EmailEvent.AUTH_EMAIL_VERIFICATION.value: _verification,
    EmailEvent.AUTH_PASSWORD_RESET.value: _password_reset,
    EmailEvent.AUTH_PASSWORD_CHANGED.value: _password_changed,
    EmailEvent.GUARDIAN_CONSENT_REQUEST.value: _guardian_request,
    EmailEvent.GUARDIAN_REGISTRATION_COMPLETION.value: _guardian_completion,
    EmailEvent.KYC_APPROVED.value: _kyc_approved,
    EmailEvent.KYC_REJECTED.value: _kyc_rejected,
    EmailEvent.BILLING_PAYMENT_CONFIRMED.value: _payment_confirmed,
    EmailEvent.AFFILIATE_INVITATION.value: _invitation,
    EmailEvent.ADMIN_CONTENT_REPORT.value: _content_report,
    EmailEvent.ADMIN_CONTACT_MESSAGE.value: _contact_message,
    EmailEvent.SUPPORT_CONTACT_CONFIRMATION.value: _contact_confirmation,
    EmailEvent.SUPPORT_NEWSLETTER_CONFIRMATION.value: _newsletter,
    TEST_EMAIL_KEY: _test_email,
}


def has_renderer(event_key: str) -> bool:
    return event_key in RENDERERS


def render(db: Session, *, event_key: str, to: str, user_id: Optional[int], context: Optional[dict], lang: str,
           support_email: Optional[str] = None) -> Rendered:
    renderer = RENDERERS.get(event_key)
    if renderer is None:
        raise RenderError("no_template")
    token = tpl.set_branding(support_email=support_email, logo_url=f"{public_site_base()}/logo.png")
    try:
        subject, html, text = renderer(db, to, user_id, context or {}, tpl.normalize_lang(lang))
    finally:
        tpl.reset_branding(token)
    # A subject is a header: never let a value break out of it.
    return str(subject).replace("\r", " ").replace("\n", " ").strip()[:250], html, text
