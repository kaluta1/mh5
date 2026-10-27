"""Member short links (/s/{code}), optionally carrying the creator's personal invitation.

Ported from smarterblogger-referral-shortener and completed:

* destinations are MyHigh5 pages only: an explicit host list and an explicit allowlist of public and
  member pages; sign-in, password, verification, payment, admin and tooling pages, credentials in the
  URL and token-like parameters are refused. The stored destination is rebuilt on the canonical
  origin, so a link can never lead anywhere else (no open redirect), and it is checked again every
  time the link is opened;
* a pasted short link is unwrapped to its own destination (no chains, no loops) and never inherits
  that link's owner or invitation; referral parameters in the pasted URL are always dropped;
* the invitation is the creator's own, taken on the server. Opening an invitation link sets the
  signed attribution cookie and ?ref=<creator code>, which registration hands to the one sponsor
  rule (sponsor_assignment.assign_at_registration: an existing sponsor is never replaced, the
  inviter must be eligible, no self-referral). A neutral link sets nothing and clears nothing;
* social crawlers are sent to the existing Open Graph preview route and never get an attribution.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from datetime import datetime, timedelta
from typing import Optional, Tuple
from urllib.parse import parse_qsl, unquote, urlencode, urlparse, urlunparse

from fastapi import HTTPException, Request, status
from jose import JWTError, jwt
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.referral_share import ReferralShareClick, ReferralShareConversion, ReferralShareLink
from app.models.user import User

_BASE62 = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"

_DASHBOARD_FEED_RE = re.compile(r"^/dashboard/feed/(\d+)$")
_DASHBOARD_CONTESTANT_RE = re.compile(r"^/dashboard/contests/(\d+)/contestant/(\d+)$")
_SHARE_FEED_RE = re.compile(r"^/s/f/(\d+)$")
_SHARE_CONTESTANT_RE = re.compile(r"^/s/c/(\d+)$")
_SHORT_CONTESTANT_RE = re.compile(r"^/c/(\d+)$")
_LEGACY_CONTESTANT_RE = re.compile(r"^/contestants/(\d+)$")


def to_public_share_path(path: str) -> str:
    """Map dashboard or preview paths to public viewer routes (no login required)."""
    dashboard_entry = _DASHBOARD_CONTESTANT_RE.match(path)
    if dashboard_entry:
        return f"/contests/{dashboard_entry.group(1)}/entry/{dashboard_entry.group(2)}"
    if _DASHBOARD_FEED_RE.match(path):
        return _DASHBOARD_FEED_RE.sub(r"/feed/\1", path)
    if _SHARE_FEED_RE.match(path):
        return _SHARE_FEED_RE.sub(r"/feed/\1", path)
    if _SHARE_CONTESTANT_RE.match(path):
        return path
    if _SHORT_CONTESTANT_RE.match(path):
        return path
    if _LEGACY_CONTESTANT_RE.match(path):
        return path
    return path


def to_public_share_url(url: str) -> str:
    parsed = urlparse(url)
    public_path = to_public_share_path(parsed.path)
    if public_path == parsed.path:
        return url
    return urlunparse(
        (parsed.scheme, parsed.netloc, public_path, parsed.params, parsed.query, parsed.fragment)
    )


# Dropped from every destination: tracking noise, and every referral / invitation parameter (the
# link's own invitation choice is the only attribution it can carry).
_TRACKING_PARAMS = frozenset({"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
                              "fbclid", "gclid"})
_ATTRIBUTION_PARAMS = frozenset({"ref", "referral", "referral_code", "referralcode", "invite", "invitation",
                                 "sponsor", "sponsor_code", "sponsorcode", "affiliate", "aff"})
# A destination carrying one of these is refused outright (one-time links, sessions, secrets).
_SENSITIVE_PARAMS = frozenset({"token", "access_token", "refresh_token", "id_token", "auth", "authorization",
                               "jwt", "session", "sessionid", "session_id", "sid", "password", "pass", "pwd",
                               "secret", "client_secret", "api_key", "apikey", "key", "signature", "sig", "otp",
                               "code", "state", "nonce", "credential", "credentials"})

SHORT_CODE_LENGTH = 7
_SHORT_CODE_RE = re.compile(r"^[0-9A-Za-z]{4,16}$")
_SHORT_LINK_PATH_RE = re.compile(r"^/(?:s|l)/([0-9A-Za-z]{4,16})$")
_MAX_URL_LENGTH = 2048

# Pages a short link may lead to. Anything else (sign-in, sign-out, password, verification, guardian
# consent, payout confirmation, admin, wallet, KYC, settings, messages, API, tooling) is refused.
_SEG = r"[0-9A-Za-z_.~-]{1,100}"
_ID = r"\d{1,12}"
_ALLOWED_PATHS = tuple(re.compile(f"^{pattern}$") for pattern in (
    r"/",
    r"/(?:about|clubs|contact|contests|cookies|faq|feed|privacy|terms|pitching|referral-pool|register)",
    rf"/feed/{_ID}",
    rf"/contestants/{_ID}",
    rf"/contests/{_ID}/entry/{_ID}",
    rf"/c/{_ID}",
    rf"/s/c/{_ID}",
    rf"/profile/{_SEG}",
    r"/dashboard",
    r"/dashboard/(?:contests|feed|groups|leaders|top-high5|affiliate-program|referral-pool|founding-member"
    r"|myhigh5|following|favorites)",
    rf"/dashboard/contests/{_ID}",
    rf"/dashboard/contests/{_ID}/contestants",
    rf"/dashboard/contestants/{_ID}",
    rf"/dashboard/groups/{_ID}",
    rf"/dashboard/users/{_ID}",
    rf"/dashboard/users/username/{_SEG}",
))
# The public /{username} profile shortcut: one segment that is not an application route.
_USERNAME_PATH_RE = re.compile(r"^/([A-Za-z0-9_.-]{3,50})$")
_RESERVED_TOP_LEVEL = frozenset({
    "about", "api", "c", "clear-cache", "clubs", "contact", "contestants", "contests", "cookies", "dashboard",
    "faq", "feed", "forgot-password", "guardian", "l", "link-preview", "login", "logout", "maintenance",
    "nominations", "pages_mobile", "payout-wallet", "pitching", "privacy", "profile", "r", "referral-pool",
    "register", "reset-password", "s", "share-debug", "terms", "tiktok-resolve", "ut", "verify-email",
    "admin", "auth", "oauth", "callback", "signout", "sign-out",
})
# A personal referral landing path (someone's own code in the path): only the page is kept, never the
# code; the new link's invitation choice decides attribution.
_REFERRAL_LANDING = ((re.compile(r"^/r/[^/]+$"), "/"),
                     (re.compile(r"^/register/(?!complete$)[^/]+$"), "/register"))

# Crawler targets: pages whose Open Graph tags are served by a dedicated preview route.
_CRAWLER_PREVIEW = (
    (re.compile(rf"^/feed/({_ID})$"), "/s/f/{0}"),
    (re.compile(rf"^/contests/{_ID}/entry/({_ID})$"), "/s/c/{0}"),
)
_CRAWLER_RE = re.compile(
    r"facebookexternalhit|Facebot|Twitterbot|LinkedInBot|WhatsApp|TelegramBot|Slackbot|Discordbot|Googlebot|"
    r"bingbot|Pinterestbot|redditbot|Applebot|SkypeUriPreview|vkShare|Embedly|bot\b|crawler|spider",
    re.IGNORECASE)


class ShortLinkError(ValueError):
    """A refusal whose message is shown to the member as is."""


# Former domains of this site (links shared before the move to myhigh5.com). Accepted as input only:
# every destination is rebuilt on the canonical origin, so nothing ever leads to these hosts.
_FORMER_HOSTS = ("kalutasociety.com", "www.kalutasociety.com", "kalutafoundation.com", "www.kalutafoundation.com")


def _random_base62(length: int = SHORT_CODE_LENGTH) -> str:
    return "".join(secrets.choice(_BASE62) for _ in range(length))


def canonical_origin() -> str:
    return (settings.SHORT_LINK_ORIGIN or settings.FRONTEND_URL or "https://myhigh5.com").rstrip("/")


def _is_local_origin() -> bool:
    return (urlparse(canonical_origin()).hostname or "") in ("localhost", "127.0.0.1")


def allowed_share_hosts() -> set[str]:
    """Hostnames (or host:port) whose pages may be shortened. Local hosts only while the application
    itself runs locally."""
    hosts: set[str] = {"myhigh5.com", "www.myhigh5.com"} | set(_FORMER_HOSTS)
    for raw in (settings.SHORT_LINK_ALLOWED_HOSTS or "").split(","):
        host = raw.strip().lower()
        if host:
            hosts.add(host)
    for origin in (settings.FRONTEND_URL, settings.SHORT_LINK_ORIGIN):
        parsed = urlparse((origin or "").strip())
        if parsed.hostname:
            name = parsed.hostname.lower()
            hosts.add(f"{name}:{parsed.port}" if parsed.port else name)
            if not parsed.port and name not in ("localhost", "127.0.0.1"):
                hosts.add(f"www.{name}")
    if not _is_local_origin():
        hosts = {h for h in hosts if h.split(":")[0] not in ("localhost", "127.0.0.1")}
    return hosts


_INVALID = "This link is not a valid MyHigh5 page link."
_NOT_ALLOWED_PAGE = "This MyHigh5 page cannot be shortened."
_SECRET_IN_URL = "Links that carry access codes or tokens cannot be shortened."


def _clean_path(raw_path: str) -> str:
    """The path as the browser routes it; anything that could be read two ways is refused."""
    path = raw_path or "/"
    decoded = unquote(path)
    if "\\" in decoded or any(ord(ch) < 32 for ch in decoded) or "%2f" in path.lower() or "%5c" in path.lower():
        raise ShortLinkError(_INVALID)
    if "//" in path or "/./" in f"{decoded}/" or "/../" in f"{decoded}/":
        raise ShortLinkError(_INVALID)
    return path.rstrip("/") if len(path) > 1 else path


def _path_allowed(path: str) -> bool:
    if any(pattern.match(path) for pattern in _ALLOWED_PATHS):
        return True
    match = _USERNAME_PATH_RE.match(path)
    return bool(match and match.group(1).lower() not in _RESERVED_TOP_LEVEL)


def _clean_query(query: str) -> str:
    pairs: list[tuple[str, str]] = []
    for key, value in parse_qsl(query, keep_blank_values=True):
        lowered = key.strip().lower()
        if lowered in _SENSITIVE_PARAMS:
            raise ShortLinkError(_SECRET_IN_URL)
        if lowered in _TRACKING_PARAMS or lowered in _ATTRIBUTION_PARAMS:
            continue
        pairs.append((key, value))
    return urlencode(pairs)


def _clean_fragment(fragment: str) -> str:
    lowered = unquote(fragment or "").lower()
    if any(f"{name}=" in lowered for name in _SENSITIVE_PARAMS):
        raise ShortLinkError(_SECRET_IN_URL)
    return fragment or ""


def _short_code_in(path: str) -> Optional[str]:
    match = _SHORT_LINK_PATH_RE.match(path)
    return match.group(1) if match else None


def validate_and_normalize_internal_url(input_url: str, db: Optional[Session] = None, *,
                                        allow_short_link: bool = True) -> tuple[str, str]:
    """(destination, normalized) for a pasted link: the same canonical absolute URL twice.
    Raises ShortLinkError with a message fit for the member. Never fetches the URL."""
    raw = (input_url or "").strip()
    if not raw or len(raw) > _MAX_URL_LENGTH or any(ch.isspace() for ch in raw):
        raise ShortLinkError("Paste a complete MyHigh5 page link.")
    try:
        parsed = urlparse(raw)
        port = parsed.port
    except ValueError:
        raise ShortLinkError(_INVALID) from None
    if parsed.scheme not in ("http", "https"):
        raise ShortLinkError("Only https:// MyHigh5 page links can be shortened.")
    if parsed.username is not None or parsed.password is not None or "@" in parsed.netloc:
        raise ShortLinkError("Links that contain a user name or password cannot be shortened.")
    host = (parsed.hostname or "").lower()
    allowed = allowed_share_hosts()
    host_ok = (f"{host}:{port}" in allowed) if port else (host in allowed)
    if not host or not (host_ok or (port in (80, 443) and host in allowed)):
        raise ShortLinkError("Only MyHigh5 page links can be shortened.")

    path = _clean_path(parsed.path)
    code = _short_code_in(path)
    if code is not None:
        # An existing short link: unwrap it to the page it leads to (one level, never a chain).
        if not allow_short_link or db is None:
            raise ShortLinkError("A short link cannot lead to another short link.")
        inner = find_active_share_link(db, code)
        if inner is None:
            raise ShortLinkError("That short link is disabled or does not exist.")
        return validate_and_normalize_internal_url(inner.destination_url, db, allow_short_link=False)

    for pattern, page in _REFERRAL_LANDING:
        if pattern.match(path):
            path = page
    path = _clean_path(to_public_share_path(path))
    if not _path_allowed(path):
        raise ShortLinkError(_NOT_ALLOWED_PAGE)
    query = _clean_query(parsed.query)
    fragment = _clean_fragment(parsed.fragment)
    destination = urlunparse(urlparse(canonical_origin())._replace(path=path, params="", query=query,
                                                                   fragment=fragment))
    return destination, destination


def short_link_public_url(short_code: str) -> str:
    return f"{canonical_origin()}/s/{short_code}"


def is_crawler(user_agent: Optional[str]) -> bool:
    return bool(user_agent) and bool(_CRAWLER_RE.search(user_agent or ""))


def crawler_destination(destination: str) -> str:
    """Where a social crawler is sent: the page's Open Graph preview route when it has one, else the
    page itself; never with an attribution."""
    parsed = urlparse(destination)
    for pattern, target in _CRAWLER_PREVIEW:
        match = pattern.match(parsed.path)
        if match:
            return f"{canonical_origin()}{target.format(match.group(1))}"
    return urlunparse(parsed._replace(fragment=""))


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


def _active_link_for(db: Session, user_id: int, normalized_url: str, invitation: bool) -> Optional[ReferralShareLink]:
    return (db.query(ReferralShareLink)
            .filter(ReferralShareLink.user_id == user_id, ReferralShareLink.normalized_url == normalized_url,
                    ReferralShareLink.invitation_enabled.is_(bool(invitation)),
                    ReferralShareLink.disabled_at.is_(None))
            .first())


def create_short_link(db: Session, user: User, input_url: str, *, include_invitation: bool,
                      code_factory=None) -> Tuple[ReferralShareLink, bool]:
    """(link, reused). The owner and the invitation come from the signed-in member only. An active
    link for the same page and the same choice is handed back instead of a second one."""
    if include_invitation and not (user.personal_referral_code or "").strip():
        raise ShortLinkError("Your account has no personal invitation code yet, so this link cannot carry one.")
    destination_url, normalized_url = validate_and_normalize_internal_url(input_url, db)

    existing = _active_link_for(db, user.id, normalized_url, include_invitation)
    if existing:
        existing.last_used_at = datetime.utcnow()
        db.commit()
        db.refresh(existing)
        return existing, True

    make_code = code_factory or _random_base62
    for _ in range(8):
        link = ReferralShareLink(user_id=user.id, short_code=make_code(), destination_url=destination_url,
                                 normalized_url=normalized_url, invitation_enabled=bool(include_invitation),
                                 last_used_at=datetime.utcnow())
        db.add(link)
        try:
            db.commit()
            db.refresh(link)
            return link, False
        except IntegrityError:
            db.rollback()
            raced = _active_link_for(db, user.id, normalized_url, include_invitation)
            if raced:
                return raced, True
            # otherwise a short-code collision: draw another code
    raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail="A short link could not be created right now. Please try again.")


INVITATION_MESSAGES = {
    "NO_CODE": "Your account has no personal invitation code yet, so your links cannot carry an invitation.",
    "KYC_NOT_STARTED": "Your identity verification (KYC) is not complete. Until it is approved, new members who "
                       "register through your invitation links will not be attributed to you.",
    "KYC_IN_PROGRESS": "Your identity verification (KYC) is still being reviewed. Until it is approved, new members "
                       "who register through your invitation links will not be attributed to you.",
    "KYC_REJECTED": "Your identity verification (KYC) was not approved. Until it is, new members who register "
                    "through your invitation links will not be attributed to you.",
    "RESTRICTED": "Invitations from your account are currently restricted, so new members who register through "
                  "your invitation links will not be attributed to you. Please contact support.",
}


def invitation_status(db: Session, user: User) -> Tuple[bool, Optional[str]]:
    """(eligible, reason) for the caller's own invitations, by the one inviter rule used at
    registration (sponsor_assignment.inviter_eligible). The reason names only the member's own KYC
    stage; a restriction is never explained further."""
    from app.services.sponsor_assignment import inviter_eligible

    if not (user.personal_referral_code or "").strip():
        return False, "NO_CODE"
    if inviter_eligible(db, user):
        return True, None
    from app.crud import crud_kyc
    from app.models.kyc import KYCStatus

    verification = crud_kyc.kyc_verification.get_by_user(db, user_id=user.id)
    if verification is None or verification.status == KYCStatus.EXPIRED:
        return False, "KYC_NOT_STARTED"
    if verification.status == KYCStatus.REJECTED:
        return False, "KYC_REJECTED"
    if verification.status != KYCStatus.APPROVED or not user.identity_verified:
        return False, "KYC_IN_PROGRESS"
    return False, "RESTRICTED"


def create_or_reuse_share_link(db: Session, user_id: int, input_url: str,
                               include_invitation: bool = True) -> ReferralShareLink:
    user = db.query(User).filter(User.id == user_id).one()
    return create_short_link(db, user, input_url, include_invitation=include_invitation)[0]


def list_member_links(db: Session, user_id: int, *, limit: int = 50, offset: int = 0):
    query = db.query(ReferralShareLink).filter(ReferralShareLink.user_id == user_id)
    total = query.count()
    items = query.order_by(ReferralShareLink.id.desc()).offset(offset).limit(limit).all()
    return items, total


def disable_member_link(db: Session, user_id: int, link_id: int) -> Optional[ReferralShareLink]:
    """Disable one of the member's OWN links (idempotent). None when the link is not theirs."""
    link = (db.query(ReferralShareLink)
            .filter(ReferralShareLink.id == link_id, ReferralShareLink.user_id == user_id)
            .with_for_update().first())
    if link is None:
        return None
    if link.disabled_at is None:
        link.disabled_at = datetime.utcnow()
        db.commit()
        db.refresh(link)
    return link


def find_active_share_link(db: Session, short_code: str) -> Optional[ReferralShareLink]:
    if not short_code or not _SHORT_CODE_RE.match(short_code):
        return None
    return (
        db.query(ReferralShareLink)
        .filter(
            ReferralShareLink.short_code == short_code,
            ReferralShareLink.disabled_at.is_(None),
        )
        .first()
    )


def _account_usable(user: Optional[User]) -> bool:
    return user is not None and user.is_active is not False and user.is_deleted is not True


def resolve_short_link(db: Session, short_code: str) -> Optional[Tuple[ReferralShareLink, str, Optional[str]]]:
    """(link, destination, invitation code or None) for an active link whose destination passes
    today's rules and whose creator still has an account; else None."""
    link = find_active_share_link(db, short_code)
    if link is None:
        return None
    creator = db.query(User).filter(User.id == link.user_id).first()
    if not _account_usable(creator):
        return None
    try:
        destination, _ = validate_and_normalize_internal_url(link.destination_url, db, allow_short_link=False)
    except ShortLinkError:
        return None
    code = (creator.personal_referral_code or "").strip() if link.invitation_enabled else ""
    return link, destination, (code or None)


def with_referrer_ref(destination: str, ref_code: str) -> str:
    parsed = urlparse(destination)
    params = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)
              if k.lower() not in _ATTRIBUTION_PARAMS]
    params.append(("ref", ref_code))
    return urlunparse(parsed._replace(query=urlencode(params)))


def destination_with_referrer_ref(db: Session, link: ReferralShareLink) -> str:
    """Landing URL: ?ref=<creator code> for an invitation link, the bare destination otherwise."""
    destination = to_public_share_url(link.destination_url)
    if not link.invitation_enabled:
        return destination
    referrer = db.query(User).filter(User.id == link.user_id).first()
    ref_code = (referrer.personal_referral_code or "").strip() if referrer else ""
    return with_referrer_ref(destination, ref_code) if ref_code else destination


def _client_ip(request: Request) -> Optional[str]:
    from app.core.client_ip import client_ip

    return client_ip(request)


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
    """The invitation code a signed attribution cookie names, if it came from an invitation link of
    that same member. Registration still applies the sponsor rules to it."""
    attribution = _read_attribution_cookie(request)
    if not attribution:
        return None
    try:
        referrer_id = int(attribution.get("referrerMemberId") or 0)
    except (TypeError, ValueError):
        return None
    if not referrer_id:
        return None
    link_id = attribution.get("shareLinkId")
    if link_id is not None:
        try:
            link = db.query(ReferralShareLink).filter(ReferralShareLink.id == int(link_id)).first()
        except (TypeError, ValueError):
            return None
        if link is None or not link.invitation_enabled or int(link.user_id) != referrer_id:
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
    """Analytics only (no commission reads this table): one signup row per new member, and only for
    a cookie that came from a still-valid invitation link."""
    attribution = _read_attribution_cookie(request)
    if not attribution or get_sponsor_referral_code_from_request(request, db) is None:
        return False
    already = db.query(ReferralShareConversion.id).filter(
        ReferralShareConversion.converted_user_id == converted_user_id,
        ReferralShareConversion.conversion_type == "signup").first()
    if already is not None:
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
