"""Referral-aware URL shortener (ported from smarterblogger-referral-shortener)."""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from fastapi import HTTPException, Request, status
from jose import JWTError, jwt
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.referral_share import ReferralShareClick, ReferralShareConversion, ReferralShareLink
from app.models.user import User

_BASE62 = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"

_DASHBOARD_FEED_RE = re.compile(r"^/dashboard/feed/(\d+)$")
_DASHBOARD_CONTESTANT_RE = re.compile(r"^/dashboard/contests/\d+/contestant/(\d+)$")
_SHARE_FEED_RE = re.compile(r"^/s/f/(\d+)$")
_SHARE_CONTESTANT_RE = re.compile(r"^/s/c/(\d+)$")
_SHORT_CONTESTANT_RE = re.compile(r"^/c/(\d+)$")


def to_public_share_path(path: str) -> str:
    """Map dashboard or preview paths to public viewer routes (no login required)."""
    if _DASHBOARD_FEED_RE.match(path):
        return _DASHBOARD_FEED_RE.sub(r"/feed/\1", path)
    if _DASHBOARD_CONTESTANT_RE.match(path):
        return _DASHBOARD_CONTESTANT_RE.sub(r"/contestants/\1", path)
    if _SHARE_FEED_RE.match(path):
        return _SHARE_FEED_RE.sub(r"/feed/\1", path)
    if _SHARE_CONTESTANT_RE.match(path):
        return _SHARE_CONTESTANT_RE.sub(r"/contestants/\1", path)
    if _SHORT_CONTESTANT_RE.match(path):
        return _SHORT_CONTESTANT_RE.sub(r"/contestants/\1", path)
    return path


def to_public_share_url(url: str) -> str:
    parsed = urlparse(url)
    public_path = to_public_share_path(parsed.path)
    if public_path == parsed.path:
        return url
    return urlunparse(
        (parsed.scheme, parsed.netloc, public_path, parsed.params, parsed.query, parsed.fragment)
    )


_TRACKING_PARAMS = frozenset(
    {
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_term",
        "utm_content",
        "fbclid",
        "gclid",
        "ref",
        "referral",
        "invite",
    }
)


def _random_base62(length: int = 7) -> str:
    return "".join(secrets.choice(_BASE62) for _ in secrets.token_bytes(length))


def allowed_share_hosts() -> set[str]:
    hosts: set[str] = set()
    for raw in (settings.SHORT_LINK_ALLOWED_HOSTS or "").split(","):
        host = raw.strip().lower()
        if host:
            hosts.add(host)
    for origin in (settings.FRONTEND_URL, settings.BACKEND_PUBLIC_URL):
        parsed = urlparse(origin.strip())
        if parsed.hostname:
            hosts.add(parsed.hostname.lower())
            if not parsed.port and parsed.hostname not in ("localhost", "127.0.0.1"):
                hosts.add(f"www.{parsed.hostname.lower()}")
    hosts.update({"localhost", "127.0.0.1", "myhigh5.com", "www.myhigh5.com"})
    return hosts


def validate_and_normalize_internal_url(input_url: str) -> tuple[str, str]:
    parsed = urlparse(input_url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Only HTTP and HTTPS URLs are allowed.")

    host = (parsed.hostname or "").lower()
    port = parsed.port
    host_key = f"{host}:{port}" if port else host
    allowed = allowed_share_hosts()

    if host not in allowed and host_key not in allowed:
        raise ValueError("Only MyHigh5 URLs may be shortened.")

    # Rebuild without fragment; strip tracking query params.
    query_pairs: list[tuple[str, str]] = []
    if parsed.query:
        for key, value in parse_qsl(parsed.query, keep_blank_values=True):
            if key.lower() not in _TRACKING_PARAMS:
                query_pairs.append((key, value))
    query_pairs.sort(key=lambda item: item[0].lower())

    normalized = urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            urlencode(query_pairs),
            "",
        )
    )
    public = to_public_share_url(normalized)
    return public, public


def short_link_public_url(short_code: str) -> str:
    origin = (settings.SHORT_LINK_ORIGIN or settings.FRONTEND_URL).rstrip("/")
    return f"{origin}/l/{short_code}"


def _attribution_cookie_domain() -> Optional[str]:
    origin = settings.FRONTEND_URL or settings.SHORT_LINK_ORIGIN
    host = urlparse(origin).hostname
    if not host or host in ("localhost", "127.0.0.1"):
        return None
    parts = host.split(".")
    if len(parts) >= 2:
        return "." + ".".join(parts[-2:])
    return None


def sign_attribution(*, referrer_user_id: int, share_link_id: int, short_code: str) -> str:
    expires = datetime.utcnow() + timedelta(days=settings.ATTRIBUTION_DAYS)
    payload = {
        "referrerMemberId": str(referrer_user_id),
        "shareLinkId": str(share_link_id),
        "shortCode": short_code,
        "iss": "mh5-shortener",
        "aud": "myhigh5",
        "exp": expires,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def verify_attribution(token: str) -> dict:
    return jwt.decode(
        token,
        settings.SECRET_KEY,
        algorithms=[settings.ALGORITHM],
        audience="myhigh5",
        issuer="mh5-shortener",
    )


def hash_ip(ip: Optional[str]) -> Optional[str]:
    if not ip:
        return None
    return hmac.new(settings.SECRET_KEY.encode(), ip.encode(), hashlib.sha256).hexdigest()


def create_or_reuse_share_link(db: Session, user_id: int, input_url: str) -> ReferralShareLink:
    destination_url, normalized_url = validate_and_normalize_internal_url(input_url)

    existing = (
        db.query(ReferralShareLink)
        .filter(
            ReferralShareLink.user_id == user_id,
            ReferralShareLink.normalized_url == normalized_url,
            ReferralShareLink.disabled_at.is_(None),
        )
        .first()
    )
    if existing:
        existing.last_used_at = datetime.utcnow()
        db.commit()
        db.refresh(existing)
        return existing

    for _ in range(5):
        short_code = _random_base62(7)
        link = ReferralShareLink(
            user_id=user_id,
            short_code=short_code,
            destination_url=destination_url,
            normalized_url=normalized_url,
            last_used_at=datetime.utcnow(),
        )
        db.add(link)
        try:
            db.commit()
            db.refresh(link)
            return link
        except IntegrityError:
            db.rollback()
            raced = (
                db.query(ReferralShareLink)
                .filter(
                    ReferralShareLink.user_id == user_id,
                    ReferralShareLink.normalized_url == normalized_url,
                    ReferralShareLink.disabled_at.is_(None),
                )
                .first()
            )
            if raced:
                return raced

    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unable to generate a unique short code.")


def find_active_share_link(db: Session, short_code: str) -> Optional[ReferralShareLink]:
    return (
        db.query(ReferralShareLink)
        .filter(
            ReferralShareLink.short_code == short_code,
            ReferralShareLink.disabled_at.is_(None),
        )
        .first()
    )


def destination_with_referrer_ref(db: Session, link: ReferralShareLink) -> str:
    """Landing URL with ?ref= so legacy frontends still pick up the referral code."""
    destination = to_public_share_url(link.destination_url)
    referrer = db.query(User).filter(User.id == link.user_id).first()
    ref_code = (referrer.personal_referral_code or "").strip() if referrer else ""
    if not ref_code:
        return destination

    parsed = urlparse(destination)
    params = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True) if k.lower() != "ref"]
    params.append(("ref", ref_code))
    return urlunparse(
        (parsed.scheme, parsed.netloc, parsed.path, parsed.params, urlencode(params), parsed.fragment)
    )


def _client_ip(request: Request) -> Optional[str]:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None


def record_click(
    db: Session,
    *,
    link: ReferralShareLink,
    request: Request,
    landing_url: Optional[str] = None,
) -> None:
    click = ReferralShareClick(
        share_link_id=link.id,
        referrer_user_id=link.user_id,
        ip_hash=hash_ip(_client_ip(request)),
        user_agent=(request.headers.get("user-agent") or "")[:1000] or None,
        referer=(request.headers.get("referer") or "")[:2048] or None,
        landing_url=landing_url or link.destination_url,
    )
    db.add(click)
    db.commit()


def _read_attribution_cookie(request: Request) -> Optional[dict]:
    token = request.cookies.get(settings.ATTRIBUTION_COOKIE_NAME)
    if not token:
        return None
    try:
        return verify_attribution(token)
    except JWTError:
        return None


def get_sponsor_referral_code_from_request(request: Request, db: Session) -> Optional[str]:
    attribution = _read_attribution_cookie(request)
    if not attribution:
        return None
    try:
        referrer_id = int(attribution.get("referrerMemberId") or 0)
    except (TypeError, ValueError):
        return None
    if not referrer_id:
        return None
    referrer = db.query(User).filter(User.id == referrer_id).first()
    if not referrer or not referrer.personal_referral_code:
        return None
    return referrer.personal_referral_code


def record_conversion(
    db: Session,
    *,
    converted_user_id: int,
    conversion_type: str,
    attribution: dict,
    conversion_reference: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> bool:
    try:
        referrer_id = int(attribution.get("referrerMemberId") or 0)
    except (TypeError, ValueError):
        return False
    if not referrer_id or referrer_id == converted_user_id:
        return False

    share_link_id = None
    raw_link_id = attribution.get("shareLinkId")
    if raw_link_id is not None:
        try:
            share_link_id = int(raw_link_id)
        except (TypeError, ValueError):
            share_link_id = None

    row = ReferralShareConversion(
        referrer_user_id=referrer_id,
        converted_user_id=converted_user_id,
        conversion_type=conversion_type,
        conversion_reference=conversion_reference,
        share_link_id=share_link_id,
        metadata_json=metadata or {},
    )
    db.add(row)
    db.commit()
    return True


def record_signup_conversion_from_request(request: Request, db: Session, converted_user_id: int) -> bool:
    attribution = _read_attribution_cookie(request)
    if not attribution:
        return False
    return record_conversion(
        db,
        converted_user_id=converted_user_id,
        conversion_type="signup",
        attribution=attribution,
    )


def attribution_cookie_settings(token: str) -> dict:
    secure = not (settings.FRONTEND_URL or "").startswith("http://localhost")
    cookie: dict = {
        "key": settings.ATTRIBUTION_COOKIE_NAME,
        "value": token,
        "httponly": True,
        "secure": secure,
        "samesite": "lax",
        "max_age": settings.ATTRIBUTION_DAYS * 24 * 60 * 60,
        "path": "/",
    }
    domain = _attribution_cookie_domain()
    if domain:
        cookie["domain"] = domain
    return cookie
