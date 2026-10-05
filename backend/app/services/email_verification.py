"""Email verification: retired GET entry points.

Verification itself is POST /api/v1/auth/verify-email with a one-time
credential (app.services.auth_tokens). GET links from emails sent before
EMAIL-2 carried a reusable token in the query string; they are no longer
honoured. They are answered with a redirect to the sign-in page, which tells
the member the link is no longer valid and where to get a new one.
"""
from fastapi import status
from fastapi.responses import RedirectResponse

from app.core.public_urls import public_site_base


def legacy_verify_redirect() -> RedirectResponse:
    """Never verifies anything and never reads the query string."""
    return RedirectResponse(
        url=f"{public_site_base()}/verify-email",
        status_code=status.HTTP_302_FOUND,
    )
