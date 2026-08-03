from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.core.config import settings
from app.core.rate_limit import _client_ip, _is_rate_limited
from app.db.session import get_db
from app.models.user import User
from app.schemas.referral_share import (
    ReferralConversionCreate,
    ReferralConversionResponse,
    ShareLinkCreate,
    ShareLinkResponse,
)
from app.services import referral_shortener as shortener

router = APIRouter()


def _enforce_share_link_rate_limit(request: Request, user_id: int) -> None:
    ip = _client_ip(request)
    if _is_rate_limited(f"{ip}:share-links:{user_id}", 60, 60):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many link requests.")


@router.post("/share-links", response_model=ShareLinkResponse, status_code=status.HTTP_201_CREATED)
def create_share_link(
    *,
    db: Session = Depends(get_db),
    request: Request,
    body: ShareLinkCreate,
    current_user: User = Depends(get_current_active_user),
) -> ShareLinkResponse:
    _enforce_share_link_rate_limit(request, current_user.id)
    try:
        link = shortener.create_or_reuse_share_link(db, current_user.id, str(body.url))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return ShareLinkResponse(
        short_code=link.short_code,
        short_url=shortener.short_link_public_url(link.short_code),
        destination_url=link.destination_url,
    )


@router.get("/l/{short_code}")
def redirect_short_link(
    short_code: str,
    request: Request,
    db: Session = Depends(get_db),
) -> Response:
    link = shortener.find_active_share_link(db, short_code)
    if not link:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="This share link is invalid or no longer available.",
        )

    token = shortener.sign_attribution(
        referrer_user_id=link.user_id,
        share_link_id=link.id,
        short_code=link.short_code,
    )
    landing_url = shortener.destination_with_referrer_ref(db, link)
    shortener.record_click(db, link=link, request=request, landing_url=landing_url)

    response = Response(status_code=status.HTTP_302_FOUND, headers={"Cache-Control": "no-store"})
    response.headers["Location"] = landing_url
    cookie = shortener.attribution_cookie_settings(token)
    response.set_cookie(**cookie)
    return response


@router.post("/referrals/convert", response_model=ReferralConversionResponse)
def record_referral_conversion(
    *,
    db: Session = Depends(get_db),
    request: Request,
    body: ReferralConversionCreate,
    current_user: User = Depends(get_current_active_user),
) -> ReferralConversionResponse | Response:
    token = request.cookies.get(settings.ATTRIBUTION_COOKIE_NAME)
    if not token:
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    try:
        attribution = shortener.verify_attribution(token)
    except Exception:
        response = Response(status_code=status.HTTP_204_NO_CONTENT)
        cookie_domain = shortener._attribution_cookie_domain()
        response.delete_cookie(
            key=settings.ATTRIBUTION_COOKIE_NAME,
            path="/",
            domain=cookie_domain,
        )
        return response

    recorded = shortener.record_conversion(
        db,
        converted_user_id=current_user.id,
        conversion_type=body.conversion_type,
        attribution=attribution,
        conversion_reference=body.conversion_reference,
        metadata=body.metadata,
    )
    if not recorded:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    return ReferralConversionResponse(recorded=True)
