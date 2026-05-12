"""Shared email verification logic (registration welcome link, GET redirects)."""
from typing import Optional, Tuple

from fastapi import status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import verify_email_verification_token
from app.crud import user as crud_user


def verify_user_email_from_token(db: Session, token: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Validate token and set user.email_verified.

    Returns:
        (success, error_code, email) where error_code is one of:
        invalid_token, user_not_found, or None on success.
    """
    email = verify_email_verification_token(token)
    if not email:
        return False, "invalid_token", None

    user = crud_user.get_by_email(db, email=email)
    if not user:
        return False, "user_not_found", None

    if not getattr(user, "email_verified", False):
        user.email_verified = True
        db.commit()
        db.refresh(user)

    return True, None, email


def build_email_verify_redirect(db: Session, token: str) -> RedirectResponse:
    """GET-friendly verification: redirect to frontend login with outcome in query string."""
    base = (settings.FRONTEND_URL or "").rstrip("/") or "http://localhost:3000"
    ok, err, _email = verify_user_email_from_token(db, token)
    if ok:
        return RedirectResponse(
            url=f"{base}/login?email_verified=1",
            status_code=status.HTTP_302_FOUND,
        )
    code = err or "invalid_token"
    return RedirectResponse(
        url=f"{base}/login?email_verify_error={code}",
        status_code=status.HTTP_302_FOUND,
    )
