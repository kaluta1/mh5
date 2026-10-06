"""Event -> (subject, html, text) rendering for the outbox worker (EMAIL-1).

A delivery is rendered ONCE, when it is first about to be sent, from the small
encrypted context stored with it and from the application state at that
moment. The outbox worker then keeps that exact message with the delivery
(email_outbox): another attempt for the same delivery sends it again and never
renders a second time, so nothing that changes afterwards (the entry, the
account, the language, the templates, the settings, the date) can change it.

One-time links (email verification, password reset) are the exception to
"keep the message": the credential must never be stored. The renderer writes
LINK_CREDENTIAL where it belongs; `link_credential` issues the credential for
each attempt, and it is the delivery's own (app.services.auth_tokens), so it is
the same value every time. Only its digest is stored. Templates are source
controlled; every dynamic value is escaped by the template helpers.
"""
from __future__ import annotations

from typing import Callable, Dict, Optional, Tuple

from sqlalchemy.orm import Session

from app.core.public_urls import public_site_base
from app.services import email_templates as tpl
from app.services.email_events import TEST_EMAIL_KEY, EmailEvent

Rendered = Tuple[str, str, Optional[str]]

# What a rendered message carries in place of a one-time credential. It is
# replaced only for the events that have one (link_credential), and their
# templates take no value from a member, so nobody can plant it in a message.
LINK_CREDENTIAL = "MH5-ONE-TIME-LINK-CREDENTIAL"


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


def _one_time_link(path: str) -> str:
    """The link of a one-time credential, with LINK_CREDENTIAL where the
    credential goes (see link_credential).

    The credential rides in the URL FRAGMENT: a browser never sends a
    fragment to a server, so it is absent from nginx/application access logs,
    from proxies and from the Referer header. The page reads it, removes it
    from the address bar and exchanges it over POST (see the frontend pages
    /verify-email and /reset-password)."""
    return f"{public_site_base()}{path}#token={LINK_CREDENTIAL}"


def _recipient_account(db: Session, to: str, user_id: Optional[int]):
    """The active account this email was queued for, provided the address is
    still that account's address."""
    user = _user(db, user_id)
    if (user.email or "").strip().lower() != (to or "").strip().lower():
        raise RenderError("recipient_changed")
    return user


def _link_account(db: Session, to: str, user_id: Optional[int], purpose: str):
    """The account a one-time link may still be mailed to."""
    from app.models.auth_security import PURPOSE_EMAIL_VERIFICATION

    user = _recipient_account(db, to, user_id)
    if purpose == PURPOSE_EMAIL_VERIFICATION and user.email_verified:
        raise RenderError("already_verified")       # nothing left to verify: no email, no credential
    return user


def _verification(db: Session, to: str, user_id: Optional[int], ctx: dict, lang: str) -> Rendered:
    from app.models.auth_security import PURPOSE_EMAIL_VERIFICATION
    from app.services import auth_tokens

    _link_account(db, to, user_id, PURPOSE_EMAIL_VERIFICATION)
    minutes = int(auth_tokens.lifetime(PURPOSE_EMAIL_VERIFICATION).total_seconds() // 60)
    return tpl.get_verify_email(lang, _one_time_link("/verify-email"), minutes,
                                new_account=bool(ctx.get("new_account")))


def _welcome(db: Session, to: str, user_id: Optional[int], ctx: dict, lang: str) -> Rendered:
    _recipient_account(db, to, user_id)
    return tpl.get_welcome_email(lang, f"{public_site_base()}/dashboard")


def _password_reset(db: Session, to: str, user_id: Optional[int], ctx: dict, lang: str) -> Rendered:
    from app.models.auth_security import PURPOSE_PASSWORD_RESET
    from app.services import auth_tokens

    _link_account(db, to, user_id, PURPOSE_PASSWORD_RESET)
    minutes = int(auth_tokens.lifetime(PURPOSE_PASSWORD_RESET).total_seconds() // 60)
    return tpl.get_password_reset_email(lang, _one_time_link("/reset-password"), minutes)


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


def _kyc_action_required(db, to, user_id, ctx, lang) -> Rendered:
    """Identity accepted, proof of address still expected. Not sent if the
    verification has moved on since the email was queued."""
    from app.models.kyc import KYCStatus, KYCVerification

    user = _recipient_account(db, to, user_id)
    latest = (db.query(KYCVerification).filter(KYCVerification.user_id == user.id)
              .order_by(KYCVerification.id.desc()).first())
    if latest is None or latest.status != KYCStatus.PENDING_PROOF_OF_ADDRESS:
        raise RenderError("state_changed")
    return tpl.get_status_email(lang, "kyc_action", button_key="kyc_action_button",
                                button_url=f"{public_site_base()}/dashboard/kyc")


# ---- contest entry status (EMAIL-3) -----------------------------------------
# The email is rendered when it is first SENT, from the entry's state at that
# moment. If the state it was queued for is no longer true, it is not sent at
# all. A later attempt for the same delivery repeats that first message.

def _entry(db: Session, to: str, user_id: Optional[int], ctx: dict):
    from app.models.contest import Contest
    from app.models.contest_eligibility import ContestEntrySafety
    from app.models.contests import Contestant

    _recipient_account(db, to, user_id)
    try:
        contestant_id = int(ctx.get("contestant_id"))
    except (TypeError, ValueError):
        raise RenderError("entry_missing")
    contestant = db.query(Contestant).filter(Contestant.id == contestant_id).first()
    if contestant is None or getattr(contestant, "is_deleted", False):
        raise RenderError("entry_gone")
    row = db.query(ContestEntrySafety).filter(ContestEntrySafety.contestant_id == contestant_id).first()
    owner_id = (row.submitted_by_user_id if row is not None else None) or contestant.user_id
    if owner_id != user_id:
        raise RenderError("recipient_changed")
    contest_id = (row.contest_id if row is not None else None) or contestant.contest_id
    contest = db.query(Contest).filter(Contest.id == contest_id).first() if contest_id else None
    title = (contestant.title or "").strip() or f"#{contestant.id}"
    return contestant, row, title, (getattr(contest, "name", None) or "MyHigh5")


def _entry_email(prefix: str, expected):
    """Renderer for one entry status. `expected(contestant, row)` says whether
    the entry is still in the state the email announces."""
    def renderer(db, to, user_id, ctx, lang) -> Rendered:
        contestant, row, title, contest_name = _entry(db, to, user_id, ctx)
        if not expected(contestant, row):
            raise RenderError("state_changed")
        return tpl.get_status_email(lang, prefix, entry=title, contest=contest_name, note_key=f"{prefix}_note",
                                    button_key="entries_button",
                                    button_url=f"{public_site_base()}/dashboard/my-applications")
    return renderer


def _is_public(contestant, row) -> bool:
    return row is not None and row.exposure_status == "PUBLIC"


def _is_held(contestant, row) -> bool:
    return row is not None and row.exposure_status == "HELD"


def _is_removed(contestant, row) -> bool:
    return (row is not None and row.exposure_status == "BLOCKED") or (contestant.verification_status or "") == "rejected"


def _update_wanted(contestant, row) -> bool:
    return row is None or row.exposure_status in ("PUBLIC", "HELD")


def _link_dead(contestant, row) -> bool:
    return (contestant.verification_status or "") == "creative_unavailable"


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
    EmailEvent.AUTH_WELCOME.value: _welcome,
    EmailEvent.AUTH_PASSWORD_RESET.value: _password_reset,
    EmailEvent.AUTH_PASSWORD_CHANGED.value: _password_changed,
    EmailEvent.GUARDIAN_CONSENT_REQUEST.value: _guardian_request,
    EmailEvent.GUARDIAN_REGISTRATION_COMPLETION.value: _guardian_completion,
    EmailEvent.KYC_APPROVED.value: _kyc_approved,
    EmailEvent.KYC_REJECTED.value: _kyc_rejected,
    EmailEvent.KYC_ACTION_REQUIRED.value: _kyc_action_required,
    EmailEvent.CONTEST_NOMINATION_PUBLISHED.value: _entry_email("nomination_published", _is_public),
    EmailEvent.CONTEST_NOMINATION_ACTION_REQUIRED.value: _entry_email("nomination_action", _update_wanted),
    EmailEvent.CONTEST_NOMINATION_REMOVED.value: _entry_email("nomination_removed", _is_removed),
    EmailEvent.CONTEST_PARTICIPATION_PENDING_REVIEW.value: _entry_email("participation_pending", _is_held),
    EmailEvent.CONTEST_PARTICIPATION_PUBLISHED.value: _entry_email("participation_published", _is_public),
    EmailEvent.CONTEST_PARTICIPATION_ACTION_REQUIRED.value: _entry_email("participation_action", _update_wanted),
    EmailEvent.CONTEST_PARTICIPATION_REJECTED.value: _entry_email("participation_rejected", _is_removed),
    EmailEvent.CONTEST_CREATIVE_UNAVAILABLE.value: _entry_email("creative_unavailable", _link_dead),
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


def _link_purposes() -> Dict[str, str]:
    from app.models.auth_security import PURPOSE_EMAIL_VERIFICATION, PURPOSE_PASSWORD_RESET

    return {EmailEvent.AUTH_EMAIL_VERIFICATION.value: PURPOSE_EMAIL_VERIFICATION,
            EmailEvent.AUTH_PASSWORD_RESET.value: PURPOSE_PASSWORD_RESET}


def link_credential(db: Session, *, event_key: str, to: str, user_id: Optional[int],
                    delivery_ref: str) -> Optional[str]:
    """The one-time credential of a delivery, for the attempt about to be made
    (None for an event without one).

    It is issued on EVERY attempt and never read back from storage: the value
    is derived from the delivery's own identity (auth_tokens.delivery_credential),
    so each attempt gets the same one and only its digest exists in the
    database. Unlike the message, the right to send it is checked each time:
    a link is not mailed again once the account or its address changed, the
    address was verified, or the link was used or replaced by a newer one."""
    from app.services import auth_tokens

    purpose = _link_purposes().get(event_key)
    if purpose is None:
        return None
    user = _link_account(db, to, user_id, purpose)
    try:
        return auth_tokens.issue(db, user, purpose, delivery_ref=delivery_ref)
    except auth_tokens.AuthTokenError as exc:
        # The link of this delivery was already used, or replaced by a newer one.
        raise RenderError(f"link_{exc.reason}") from None


def with_credential(value: Optional[str], credential: Optional[str]) -> Optional[str]:
    """`value` with the one-time credential in its place."""
    if value is None or credential is None:
        return value
    return value.replace(LINK_CREDENTIAL, credential)


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
