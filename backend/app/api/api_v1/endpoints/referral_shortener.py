from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.core.config import settings
from app.core.rate_limit import _client_ip, _is_rate_limited
from app.db.session import get_db
from app.models.user import User
from app.models.referral_share import ReferralShareLink
from app.schemas.referral_share import (
    ReferralConversionCreate,
    ReferralConversionResponse,
    ShareLinkCreate,
    ShareLinkList,
    ShareLinkResponse,
)
from app.services import referral_shortener as shortener

router = APIRouter()

UNAVAILABLE_MESSAGE = "This short link is invalid or no longer available."


def _enforce_share_link_rate_limit(request: Request, user_id: int) -> None:
    ip = _client_ip(request)
    if _is_rate_limited(f"{ip}:share-links:{user_id}", 60, 60):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many link requests.")


def _link_response(link: ReferralShareLink, *, reused: bool = False) -> ShareLinkResponse:
    return ShareLinkResponse(
        id=link.id,
        short_code=link.short_code,
        short_url=shortener.short_link_public_url(link.short_code),
        destination_url=link.destination_url,
        include_invitation=bool(link.invitation_enabled),
        is_active=link.disabled_at is None,
        created_at=link.created_at,
        disabled_at=link.disabled_at,
        reused=reused,
    )


@router.post("/share-links", response_model=ShareLinkResponse, status_code=status.HTTP_201_CREATED)
def create_share_link(
    *,
    db: Session = Depends(get_db),
    request: Request,
    body: ShareLinkCreate,
    current_user: User = Depends(get_current_active_user),
) -> ShareLinkResponse:
    """Shorten a MyHigh5 page link for the signed-in member. The owner and the invitation are the
    caller's own; nothing in the body can name another member or code."""
    _enforce_share_link_rate_limit(request, current_user.id)
    try:
        link, reused = shortener.create_short_link(db, current_user, body.url,
                                                   include_invitation=body.include_invitation)
    except shortener.ShortLinkError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _link_response(link, reused=reused)


@router.get("/share-links", response_model=ShareLinkList)
def list_share_links(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> ShareLinkList:
    """The signed-in member's own short links, newest first."""
    items, total = shortener.list_member_links(db, current_user.id, limit=limit, offset=offset)
    return ShareLinkList(items=[_link_response(link) for link in items], total=total)


@router.post("/share-links/{link_id}/disable", response_model=ShareLinkResponse)
def disable_share_link(
    link_id: int,
    *,
    db: Session = Depends(get_db),
    request: Request,
    current_user: User = Depends(get_current_active_user),
) -> ShareLinkResponse:
    """Disable one of the member's own links (it stops resolving at once). Another member's link
    answers exactly like a missing one."""
    _enforce_share_link_rate_limit(request, current_user.id)
    link = shortener.disable_member_link(db, current_user.id, link_id)
    if link is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Short link not found.")
    return _link_response(link)


def _unavailable() -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, headers={"Cache-Control": "no-store"},
                        content={"detail": UNAVAILABLE_MESSAGE, "code": "SHORT_LINK_UNAVAILABLE"})


@router.get("/l/{short_code}")
def redirect_short_link(
    short_code: str,
    request: Request,
    db: Session = Depends(get_db),
) -> Response:
    """Resolve a short link (public, no sign-in). 302 to the destination, never cached. An
    invitation link also sets the signed attribution cookie and ?ref=<creator code>; a neutral link
    sets and clears nothing. Social crawlers go to the page's preview route with no attribution.
    The destination page applies its own access rules: a short link grants no access."""
    ip = _client_ip(request)
    if _is_rate_limited(f"{ip}:short-link-resolve", 120, 60):
        return JSONResponse(status_code=status.HTTP_429_TOO_MANY_REQUESTS, headers={"Cache-Control": "no-store"},
                            content={"detail": "Too many requests. Please try again shortly."})
    resolved = shortener.resolve_short_link(db, short_code)
    if resolved is None:
        return _unavailable()
    link, destination, invitation_code = resolved

    headers = {"Cache-Control": "no-store, private", "Referrer-Policy": "strict-origin-when-cross-origin",
               "X-Robots-Tag": "noindex"}
    if shortener.is_crawler(request.headers.get("user-agent")):
        return RedirectResponse(shortener.crawler_destination(destination), status_code=status.HTTP_302_FOUND,
                                headers=headers)
    if invitation_code is None:
        return RedirectResponse(destination, status_code=status.HTTP_302_FOUND, headers=headers)

    landing_url = shortener.with_referrer_ref(destination, invitation_code)
    shortener.record_click(db, link=link, request=request, landing_url=landing_url)
    response = RedirectResponse(landing_url, status_code=status.HTTP_302_FOUND, headers=headers)
    response.set_cookie(**shortener.attribution_cookie_settings(shortener.sign_attribution(
        referrer_user_id=link.user_id, share_link_id=link.id, short_code=link.short_code)))
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
