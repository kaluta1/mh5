"""Guardian-consent emails, sent through the existing email service.

Links carry the single-use token in the URL fragment (#token=...), which
browsers never send to servers, so it cannot appear in web-server or proxy
logs. The emails never include a password, DOB, age or other minor PII beyond
the chosen username.
"""
from __future__ import annotations

import html
from typing import Optional

from app.core.public_urls import public_site_base
from app.services.email import email_service


def send_guardian_request_email(guardian_email: str, raw_token: str, minor_username: Optional[str]) -> bool:
    link = f"{public_site_base()}/guardian/consent#token={raw_token}"
    who = html.escape(minor_username or "a young person")
    body = (
        f"<p>Someone using the username <strong>{who}</strong> asked to create a MyHigh5 account "
        "and named you as their parent or legal guardian.</p>"
        "<p>If this is correct, you can review the request and choose exactly what you consent to. "
        "If you do not recognise this request, you can decline it or simply ignore this email.</p>"
        f'<p><a href="{link}">Review the request</a></p>'
        "<p>This link can be used once and expires automatically.</p>"
    )
    return email_service.send_email(guardian_email, "MyHigh5: parent or guardian approval requested", body)


def send_completion_email(minor_email: str, raw_token: str) -> bool:
    link = f"{public_site_base()}/register/complete#token={raw_token}"
    body = (
        "<p>Your parent or guardian approval for your MyHigh5 account request has been recorded and verified.</p>"
        f'<p><a href="{link}">Finish creating your account</a></p>'
        "<p>This link can be used once and expires automatically.</p>"
    )
    return email_service.send_email(minor_email, "MyHigh5: finish creating your account", body)
