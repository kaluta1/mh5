"""Viewer-level age-safe delivery (Child/Teen Safety Phase 7: s.15, s.16, s.18,
s.21, s.24, s.25, s.27).

ONE backend place decides what a given viewer may RECEIVE. Phase 5/6 decide
whether an entry may be public at all; this module decides, per viewer, whether
the entry, its media and its author's profile data may be transmitted. The
frontend never filters for safety: a denied payload never leaves the backend.

Rating delivery (Phase 2 ratings; viewer age is computed live, UNKNOWN is never
adult):
    GENERAL        -> any viewer (including anonymous / UNKNOWN)
    TEEN_13_PLUS   -> known age >= 13
    TEEN_16_PLUS   -> known age >= 16
    ADULT_18_PLUS  -> known legal adult only (never minors, UNKNOWN or anonymous)
    PROHIBITED     -> never delivered
Historical entries (no Phase 6 moderation record) keep their historical
treatment: they are delivered as before (no rating is invented for them).

Entry access modes:
    PUBLIC                entry is publicly exposed and its rating is allowed
    OWNER                 the submitter may see their own non-public entry (status,
                          remediation) - NEVER a child-safety escalated entry
    MODERATION            an authorized moderator (Phase 6 can_moderate), audited
    CHILD_SAFETY_REVIEW   only an explicit child_safety_resolve holder, audited
Everything else is denied with a generic response (no moderation/child-safety
detail).

Protected media: an uploaded file that belongs to any entry that an anonymous
viewer may not receive is served ONLY with a short-lived signed token issued by
this module after the entry-level decision above (bound to media owner,
filename, entry, viewer and expiry; HMAC-SHA256 with a purpose-specific key).
Files of historical/public GENERAL entries (and files not used by any entry)
keep today's public delivery. Private KYC files are never served (unchanged
Phase 1.5 guard in the resolver).

Author/profile minimization (s.24): the author block of an entry and public
profiles are built from the Phase 4 privacy resolution - a minor's or
UNKNOWN-age user's name, city/country and verification flags are withheld
unless their age is established as adult or verified guardian consent allows
that display (username and avatar only otherwise).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from datetime import date
from typing import Dict, FrozenSet, Iterable, List, Optional, Sequence

from sqlalchemy import and_, exists, or_
from sqlalchemy.orm import Session

from app.core.child_safety import AgeTier, ContentRating, EntryExposureStatus
from app.core.config import settings
from app.models.accounting import AuditTrail
from app.models.age_safety import UserAgeProfile
from app.models.content_moderation import ContentModeration
from app.models.contest_eligibility import ContestEntrySafety
from app.models.contests import Contestant
from app.models.media import Media
from app.models.user import User
from app.services.age_policy_engine import AgeAndContestPolicyEngine, utc_today
from app.services.entry_exposure import public_entry_clause

ALWAYS = frozenset({ContentRating.GENERAL})
MEDIA_TOKEN_TTL_SECONDS = 600
_MEDIA_PREFIX = "/api/v1/media/file/"
_LEGACY_MEDIA_PREFIX = "/media/"   # static mount (relative URLs only)


# ---------------------------------------------------------------------------
# Viewer
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Viewer:
    user_id: Optional[int]
    tier: AgeTier
    allowed_ratings: FrozenSet[ContentRating]
    can_moderate: bool = False
    can_resolve_child_safety: bool = False

    @property
    def anonymous(self) -> bool:
        return self.user_id is None

    @property
    def age_known(self) -> bool:
        return self.tier != AgeTier.UNKNOWN


ANONYMOUS = Viewer(user_id=None, tier=AgeTier.UNKNOWN, allowed_ratings=ALWAYS)


def allowed_ratings_for(tier: AgeTier, legal_adult: bool) -> FrozenSet[ContentRating]:
    allowed = {ContentRating.GENERAL}
    if tier in (AgeTier.TEEN_13_15, AgeTier.TEEN_16_17, AgeTier.ADULT_18_PLUS):
        allowed.add(ContentRating.TEEN_13_PLUS)
    if tier in (AgeTier.TEEN_16_17, AgeTier.ADULT_18_PLUS):
        allowed.add(ContentRating.TEEN_16_PLUS)
    if tier == AgeTier.ADULT_18_PLUS and legal_adult:
        allowed.add(ContentRating.ADULT_18_PLUS)
    return frozenset(allowed)


def viewer_for(db: Session, user: Optional[User], *, on: Optional[date] = None) -> Viewer:
    """Build the viewer context from CURRENT data (age computed live)."""
    if user is None or not getattr(user, "is_active", True) or not isinstance(getattr(user, "id", None), int):
        return ANONYMOUS  # no identity -> anonymous policy (fail closed)
    from app.services import content_safety as cs

    on = on or utc_today()
    profile = db.query(UserAgeProfile).filter(UserAgeProfile.user_id == user.id).first()
    ctx = AgeAndContestPolicyEngine(db).context_for_user(user, on, profile)
    # Without an AgePolicy the platform adult tier is used; with one, its adult_age.
    legal_adult = ctx.age_tier == AgeTier.ADULT_18_PLUS and (not ctx.policy.found or ctx.legal_adult)
    return Viewer(user_id=user.id, tier=ctx.age_tier, allowed_ratings=allowed_ratings_for(ctx.age_tier, legal_adult),
                  can_moderate=cs.can_moderate(user), can_resolve_child_safety=cs.can_resolve_child_safety(user))


# ---------------------------------------------------------------------------
# Listing filter (SQL) and entry decision
# ---------------------------------------------------------------------------

def listing_clause(viewer: Viewer):
    """Entries a viewer may receive in a public listing: publicly exposed
    (Phase 5/6) AND, for governed entries, a rating the viewer may receive.
    Historical entries (no moderation record) are unaffected."""
    restricted = exists().where(and_(
        ContentModeration.contestant_id == Contestant.id,
        or_(ContentModeration.rating.is_(None),
            ~ContentModeration.rating.in_([r.value for r in viewer.allowed_ratings]))))
    return and_(public_entry_clause(), ~restricted)


class Mode:
    PUBLIC = "PUBLIC"
    OWNER = "OWNER"
    MODERATION = "MODERATION"
    CHILD_SAFETY_REVIEW = "CHILD_SAFETY_REVIEW"


class Denial:
    NOT_FOUND = "NOT_FOUND"            # not public / not visible to this viewer (existence not revealed)
    SIGN_IN_REQUIRED = "SIGN_IN_REQUIRED"
    AGE_REQUIRED = "AGE_REQUIRED"      # signed in without a DOB
    AGE_RESTRICTED = "AGE_RESTRICTED"  # known age below the rating


@dataclass(frozen=True)
class EntryAccess:
    allowed: bool
    mode: Optional[str] = None
    denial: Optional[str] = None
    rating: Optional[ContentRating] = None
    anonymous_deliverable: bool = False   # may this entry (and its media) go to anyone?

    def client_error(self) -> dict:
        messages = {
            Denial.SIGN_IN_REQUIRED: "Sign in to view this content.",
            Denial.AGE_REQUIRED: "Add your date of birth to your profile to view this content.",
            Denial.AGE_RESTRICTED: "This content isn't available for your account.",
        }
        return {"code": "CONTENT_RESTRICTED", "reason": self.denial, "message": messages.get(self.denial)}


def _moderation(db: Session, contestant_id: int) -> Optional[ContentModeration]:
    return db.query(ContentModeration).filter(ContentModeration.contestant_id == contestant_id).first()


def _safety(db: Session, contestant_id: int) -> Optional[ContestEntrySafety]:
    return db.query(ContestEntrySafety).filter(ContestEntrySafety.contestant_id == contestant_id).first()


class Governance:
    """Batch-loaded Phase 5/6 records for many entries (avoids N+1 in listings)."""

    def __init__(self, db: Session, contestant_ids: Iterable[int]):
        ids = list({int(i) for i in contestant_ids if i is not None}) or [-1]
        self.safety = {r.contestant_id: r for r in
                       db.query(ContestEntrySafety).filter(ContestEntrySafety.contestant_id.in_(ids)).all()}
        self.moderation = {r.contestant_id: r for r in
                           db.query(ContentModeration).filter(ContentModeration.contestant_id.in_(ids)).all()}


def entry_access(db: Session, viewer: Viewer, contestant: Optional[Contestant],
                 governance: Optional[Governance] = None) -> EntryAccess:
    if contestant is None or getattr(contestant, "is_deleted", False):
        return EntryAccess(False, denial=Denial.NOT_FOUND)
    if governance is not None:
        safety = governance.safety.get(contestant.id)
        moderation = governance.moderation.get(contestant.id)
    else:
        safety = _safety(db, contestant.id)
        moderation = _moderation(db, contestant.id)
    owner = viewer.user_id is not None and viewer.user_id == contestant.user_id
    escalated = bool(
        (safety is not None and safety.exposure_status == EntryExposureStatus.CHILD_SAFETY_ESCALATED.value)
        or (moderation is not None and (moderation.child_safety_escalated
                                        or moderation.child_safety_resolution == "CONFIRMED")))
    if escalated:
        # Strictest: never public, never the owner, never ordinary moderation.
        if viewer.can_resolve_child_safety:
            return EntryAccess(True, Mode.CHILD_SAFETY_REVIEW)
        return EntryAccess(False, denial=Denial.NOT_FOUND)
    public = safety is None or safety.exposure_status == EntryExposureStatus.PUBLIC.value
    rating = ContentRating(moderation.rating) if moderation is not None and moderation.rating else None
    if moderation is not None and public and rating is None:
        public = False  # a governed entry is never public without a final rating (fail closed)
    if not public:
        if owner:
            return EntryAccess(True, Mode.OWNER, rating=rating)
        if viewer.can_moderate:
            return EntryAccess(True, Mode.MODERATION, rating=rating)
        return EntryAccess(False, denial=Denial.NOT_FOUND)
    if rating == ContentRating.PROHIBITED:
        return EntryAccess(False, denial=Denial.NOT_FOUND)
    anonymous_ok = rating is None or rating in ALWAYS
    if rating is None or rating in viewer.allowed_ratings:
        return EntryAccess(True, Mode.PUBLIC, rating=rating, anonymous_deliverable=anonymous_ok)
    if owner:
        return EntryAccess(True, Mode.OWNER, rating=rating)
    if viewer.can_moderate:
        return EntryAccess(True, Mode.MODERATION, rating=rating)
    if viewer.anonymous:
        return EntryAccess(False, denial=Denial.SIGN_IN_REQUIRED, rating=rating)
    if not viewer.age_known:
        return EntryAccess(False, denial=Denial.AGE_REQUIRED, rating=rating)
    return EntryAccess(False, denial=Denial.AGE_RESTRICTED, rating=rating)


def require_entry_access(db: Session, user: Optional[User], contestant: Optional[Contestant], *,
                         public_only: bool = False) -> EntryAccess:
    """Endpoint guard for data about an entry (comments, interactions...).
    Hidden/unknown -> 404 (existence not revealed); age-rated -> 403 with a
    safe CONTENT_RESTRICTED body. public_only: writes/votes need PUBLIC mode."""
    from fastapi import HTTPException, status

    access = entry_access(db, viewer_for(db, user), contestant)
    if access.allowed and (not public_only or access.mode == Mode.PUBLIC):
        return access
    if not access.allowed and access.denial in (Denial.SIGN_IN_REQUIRED, Denial.AGE_REQUIRED, Denial.AGE_RESTRICTED):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=access.client_error())
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found")


# ---------------------------------------------------------------------------
# Protected media authorization (Phase 7 hardening)
#
# Two separate HMAC-signed values, each with its own derived key:
#
# * GRANT (in the URL as ?g=...): binds ONE stored file + ONE entry + ONE viewer
#   + a short expiry. It is NOT a bearer credential: for an authenticated viewer
#   the media route also requires that the REQUESTER is that same viewer, proven
#   by the media-session cookie (or an Authorization bearer). A logged or copied
#   URL is therefore useless to anyone else.
# * MEDIA SESSION (HttpOnly cookie, SameSite=Strict, path-scoped to the media
#   route): carries the viewer identity for <img>/<video> requests, which cannot
#   send an Authorization header. Cookies are not part of the request line, so
#   they are not written by ordinary web-server access logging.
#
# Every request re-runs the authoritative entry decision for the proven viewer.
# ---------------------------------------------------------------------------

MEDIA_SESSION_COOKIE = "mh5_media_session"
MEDIA_SESSION_TTL_SECONDS = 3600
MEDIA_SESSION_PATH = _MEDIA_PREFIX.rstrip("/")   # /api/v1/media/file


def _derived_key(label: bytes) -> bytes:
    base = (getattr(settings, "MEDIA_TOKEN_KEY", "") or settings.SECRET_KEY).encode("utf-8")
    return hmac.new(base, label, hashlib.sha256).digest()


def _media_key() -> bytes:
    return _derived_key(b"mh5-protected-media-grant-v2")


def _session_key() -> bytes:
    return _derived_key(b"mh5-media-session-v1")


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _seal(key: bytes, payload: dict) -> str:
    body = _b64(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    return f"{body}.{_b64(hmac.new(key, body.encode('ascii'), hashlib.sha256).digest())}"


def _open(key: bytes, value: Optional[str], now: Optional[float]) -> Optional[dict]:
    if not value or len(value) > 1024 or value.count(".") != 1:
        return None
    body, sig = value.split(".")
    expected = _b64(hmac.new(key, body.encode("ascii"), hashlib.sha256).digest())
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        payload = json.loads(_unb64(body))
    except (ValueError, TypeError):
        return None
    if not isinstance(payload, dict) or int(payload.get("e", 0)) < int(now or time.time()):
        return None
    return payload


def sign_media(owner_id: int, filename: str, *, contestant_id: int, viewer_id: Optional[int],
               ttl: int = MEDIA_TOKEN_TTL_SECONDS, now: Optional[float] = None) -> str:
    """Viewer-bound grant for one stored file of one entry."""
    return _seal(_media_key(), {"u": int(owner_id), "f": filename, "c": int(contestant_id), "v": viewer_id,
                                "e": int((now or time.time()) + ttl)})


def verify_media_token(token: Optional[str], owner_id: int, filename: str, *,
                       now: Optional[float] = None) -> Optional[dict]:
    """Valid, unexpired, untampered grant bound to exactly this file -> payload.
    (The caller must still prove the requester is the grant's viewer.)"""
    payload = _open(_media_key(), token, now)
    if payload is None or payload.get("u") != owner_id or payload.get("f") != filename:
        return None
    return payload


def sign_media_session(user_id: int, *, ttl: int = MEDIA_SESSION_TTL_SECONDS, now: Optional[float] = None) -> str:
    return _seal(_session_key(), {"s": int(user_id), "e": int((now or time.time()) + ttl)})


def verify_media_session(value: Optional[str], *, now: Optional[float] = None) -> Optional[int]:
    payload = _open(_session_key(), value, now)
    uid = payload.get("s") if payload else None
    return uid if isinstance(uid, int) else None


def requester_user_id(request) -> Optional[int]:
    """The PROVEN identity of the party making a media request: an Authorization
    bearer (access token) if present, otherwise the media-session cookie.
    A viewer id written in a URL is never trusted on its own."""
    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        from app.core.security import decode_access_token

        sub = (decode_access_token(auth[7:].strip()) or {}).get("sub")
        try:
            return int(sub)
        except (TypeError, ValueError):
            return None  # an invalid bearer never falls back to the cookie
    return verify_media_session(request.cookies.get(MEDIA_SESSION_COOKIE))


def media_session_cookie_kwargs(request) -> dict:
    https = (request.url.scheme == "https"
             or (request.headers.get("x-forwarded-proto") or "").lower() == "https"
             or (request.headers.get("x-forwarded-ssl") or "").lower() == "on"
             or str(getattr(settings, "ENVIRONMENT", "")).lower() == "production")
    return {"key": MEDIA_SESSION_COOKIE, "max_age": MEDIA_SESSION_TTL_SECONDS, "path": MEDIA_SESSION_PATH,
            "httponly": True, "samesite": "strict", "secure": https}


def authorize_protected_media(db: Session, request, owner_id: int, filename: str, grant: Optional[str]) -> bool:
    """Request-time decision for a PROTECTED stored file (fail closed)."""
    payload = verify_media_token(grant, owner_id, filename)
    if payload is None:
        return False
    entry = {c.id: c for c in entries_using_file(db, owner_id, filename)}.get(payload.get("c"))
    if entry is None:                       # grant for an entry that does not use this file
        return False
    grant_viewer = payload.get("v")
    if grant_viewer is None:
        # Issued to an anonymous viewer: only content any anonymous viewer may receive.
        access = entry_access(db, ANONYMOUS, entry)
        return access.allowed and access.mode == Mode.PUBLIC and access.anonymous_deliverable
    if requester_user_id(request) != grant_viewer:   # Viewer B / logged-out holder of A's URL
        return False
    user = db.query(User).filter(User.id == grant_viewer).first()
    if user is None or not user.is_active:
        return False
    return entry_access(db, viewer_for(db, user), entry).allowed   # permissions re-checked NOW


# ---------------------------------------------------------------------------
# Media <-> entry binding
# ---------------------------------------------------------------------------

def _refs(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        parsed = [raw]
    if not isinstance(parsed, list):
        parsed = [parsed]
    return [str(x).strip() for x in parsed if str(x).strip()]


def split_media_url(url: Optional[str]):
    """'/api/v1/media/file/{uid}/{name}' (relative or absolute) or the legacy
    relative static path '/media/{uid}/{name}' -> (uid, name)."""
    if not url:
        return None
    url = url.strip()
    if _MEDIA_PREFIX in url:
        tail = url[url.index(_MEDIA_PREFIX) + len(_MEDIA_PREFIX):]
    elif url.startswith(_LEGACY_MEDIA_PREFIX):
        tail = url[len(_LEGACY_MEDIA_PREFIX):]
    else:
        return None
    tail = tail.split("?", 1)[0].split("#", 1)[0]
    parts = tail.split("/")
    if len(parts) != 2 or not parts[0].isdigit() or not parts[1]:
        return None
    return int(parts[0]), parts[1]


def _media_url_for_ref(db: Session, ref: str) -> Optional[str]:
    if ref.isdigit():
        media = db.query(Media).filter(Media.id == int(ref)).first()
        return media.url if media else None
    return ref if split_media_url(ref) is not None else None


def entries_using_file(db: Session, owner_id: int, filename: str) -> List[Contestant]:
    """Entries whose media references this stored file (by media id or URL)."""
    paths = (f"{_MEDIA_PREFIX}{owner_id}/{filename}", f"{_LEGACY_MEDIA_PREFIX}{owner_id}/{filename}")
    media_ids = [str(mid) for (mid, url) in
                 db.query(Media.id, Media.url).filter(or_(*[Media.url.like(f"%{p}%") for p in paths])).all()
                 if split_media_url(url) == (owner_id, filename)]  # exact (LIKE treats "_" as a wildcard)
    conds = [col.like(f"%{p}%") for p in paths for col in (Contestant.image_media_ids, Contestant.video_media_ids)]
    for mid in media_ids:
        for col in (Contestant.image_media_ids, Contestant.video_media_ids):
            conds += [col.like(f'%"{mid}"%'), col.like(f"%[{mid},%"), col.like(f"%,{mid},%"),
                      col.like(f"%,{mid}]%"), col.like(f"%[{mid}]%"), col.like(f"%, {mid}]%"),
                      col.like(f"%, {mid},%")]
    # Deleted entries are included on purpose: their media must not become public
    # (entry_access denies a deleted entry to everyone, so such files are never served).
    candidates = db.query(Contestant).filter(or_(*conds)).all()
    # Confirm exact membership (the LIKE prefilter can over-match).
    result = []
    for c in candidates:
        refs = _refs(c.image_media_ids) + _refs(c.video_media_ids)
        if any(r in media_ids or split_media_url(r) == (owner_id, filename) for r in refs):
            result.append(c)
    return result


def media_is_protected(db: Session, owner_id: int, filename: str) -> bool:
    """A file is protected when ANY entry using it may not go to an anonymous viewer."""
    entries = entries_using_file(db, owner_id, filename)
    governance = Governance(db, [c.id for c in entries])
    return any(not entry_access(db, ANONYMOUS, c, governance).anonymous_deliverable for c in entries)


# ---------------------------------------------------------------------------
# Payload security (entries)
# ---------------------------------------------------------------------------

_MEDIA_LIST_FIELDS = ("image_media_ids", "video_media_ids")
_MEDIA_URL_FIELDS = ("contestant_image_url", "image_url", "thumbnail_url", "video_url")
_AUTHOR_NAME_FIELDS = ("author_name", "full_name", "author_full_name")
_AUTHOR_PLACE_FIELDS = ("author_city", "author_country", "author_continent", "author_region",
                        "city", "country", "region", "continent", "nominator_city", "nominator_country",
                        "author_gender")  # demographic: same floor as place
_WITHHELD_FIELDS = ("title", "description", "contestant_title", "contestant_description",
                    "image_media_ids", "video_media_ids", "contestant_image_url", "image_url", "thumbnail_url",
                    "video_url")


def _audit(db: Session, viewer: Viewer, contestant_id: int, mode: str) -> None:
    db.add(AuditTrail(table_name="protected_content_access", record_id=contestant_id, action=f"ACCESS_{mode}",
                      old_values=None, new_values={"mode": mode}, user_id=viewer.user_id))


def _sign_url(url: str, contestant_id: int, viewer: Viewer) -> Optional[str]:
    parts = split_media_url(url)
    if parts is None:
        return url  # external link (e.g. YouTube): not served by MyHigh5
    token = sign_media(parts[0], parts[1], contestant_id=contestant_id, viewer_id=viewer.user_id)
    return f"{_MEDIA_PREFIX}{parts[0]}/{parts[1]}?g={token}"


def _secure_media_value(db: Session, value, contestant_id: int, viewer: Viewer, protect: bool):
    if not protect or value in (None, ""):
        return value
    if isinstance(value, str) and value.strip().startswith("["):
        refs = _refs(value)
        out = []
        for r in refs:
            url = _media_url_for_ref(db, r) if r.isdigit() or split_media_url(r) is not None else r
            out.append(_sign_url(url, contestant_id, viewer) if url else None)
        return json.dumps([u for u in out if u])
    if isinstance(value, list):
        return [_secure_media_value(db, v, contestant_id, viewer, protect) for v in value]
    if isinstance(value, str):
        return _sign_url(value, contestant_id, viewer)
    return value


class PrivacyCache:
    """Per-request cache of author display permissions (Phase 4 resolution)."""

    def __init__(self, db: Session):
        self.db = db
        self._cache: Dict[int, Dict[str, bool]] = {}

    def display(self, user: Optional[User]) -> Dict[str, bool]:
        if user is None:
            return {"name": False, "place": False, "verification": False}
        if user.id not in self._cache:
            from app.services.teen_privacy import resolve_privacy

            eff = resolve_privacy(self.db, user, on=utc_today())
            adult = eff.age_tier == AgeTier.ADULT_18_PLUS
            self._cache[user.id] = {
                "name": adult or bool(eff.display.get("name_display")),
                "place": adult or bool(eff.display.get("city_country_display")),
                # Verification flags reveal identity checks; shown for adults only.
                "verification": adult,
            }
        return self._cache[user.id]


def minimize_author(item: dict, author: Optional[User], privacy: PrivacyCache,
                    viewer: Optional[Viewer] = None) -> dict:
    if viewer is not None and author is not None and viewer.user_id == author.id:
        return item  # an author always sees their own details
    perm = privacy.display(author)
    if not perm["name"]:
        for f in _AUTHOR_NAME_FIELDS:
            if f in item:
                item[f] = getattr(author, "username", None) if author is not None else None
        for f in ("first_name", "last_name", "author_first_name", "author_last_name"):
            if f in item:
                item[f] = None
    if not perm["place"]:
        for f in _AUTHOR_PLACE_FIELDS:
            if f in item:
                item[f] = None
    if not perm["verification"]:
        for f in ("identity_verified", "address_verified", "author_identity_verified", "author_address_verified"):
            if f in item:
                item[f] = False
    return item


_PERSON_NAME_KEYS = ("full_name", "first_name", "last_name")
_PERSON_PLACE_KEYS = ("city", "country")


def minimize_user_refs(db: Session, obj, privacy: PrivacyCache, viewer: Optional[Viewer] = None):
    """Other users embedded in a payload (voters, commenters, reactors, ...):
    names/places only where that user's age/consent floor allows. Mutates obj."""
    refs = []

    def walk(o):
        if isinstance(o, dict):
            if "user_id" in o and any(k in o for k in _PERSON_NAME_KEYS + _PERSON_PLACE_KEYS):
                refs.append(o)
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(obj)
    ids = {r["user_id"] for r in refs if isinstance(r.get("user_id"), int)}
    if viewer is not None and viewer.user_id is not None:
        ids.discard(viewer.user_id)
    users = {u.id: u for u in db.query(User).filter(User.id.in_(ids))} if ids else {}
    for r in refs:
        uid = r.get("user_id")
        if viewer is not None and uid is not None and uid == viewer.user_id:
            continue
        perm = privacy.display(users.get(uid))
        if not perm["name"]:
            for k in _PERSON_NAME_KEYS:
                if k in r:
                    r[k] = None
        if not perm["place"]:
            for k in _PERSON_PLACE_KEYS:
                if k in r:
                    r[k] = None
    return obj


def secure_entry_item(db: Session, viewer: Viewer, item: dict, contestant: Contestant,
                      access: EntryAccess, privacy: PrivacyCache, *, audit: bool = True) -> dict:
    """Apply media protection and author minimization to one serialized entry
    the viewer is ALLOWED to receive (callers drop denied entries first)."""
    item = dict(item)
    protect = access.mode != Mode.PUBLIC or not access.anonymous_deliverable
    for f in _MEDIA_LIST_FIELDS + _MEDIA_URL_FIELDS:
        if f in item:
            item[f] = _secure_media_value(db, item[f], contestant.id, viewer, protect)
    if access.mode in (Mode.MODERATION, Mode.CHILD_SAFETY_REVIEW) and audit:
        _audit(db, viewer, contestant.id, access.mode)
    item = minimize_author(item, contestant.user, privacy, viewer)
    # nested people only (the author itself was handled above)
    minimize_user_refs(db, [v for v in item.values() if isinstance(v, (list, dict))], privacy, viewer)
    return item


def _contestant_id_of(item: dict) -> Optional[int]:
    for key in ("id", "contestant_id"):
        value = item.get(key)
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    return None


def secure_entry_list(db: Session, viewer: Viewer, items: Sequence[dict], *,
                      allow_modes: Iterable[str] = (Mode.PUBLIC,)) -> List[dict]:
    """Drop entries the viewer may not receive, then secure the rest. Used where
    a listing cannot be filtered in SQL. allow_modes limits non-public access
    (e.g. an owner's own list may include OWNER mode)."""
    allow_modes = set(allow_modes)
    privacy = PrivacyCache(db)
    out = []
    ids = [i for i in (_contestant_id_of(x) for x in items) if i is not None]
    rows = {c.id: c for c in db.query(Contestant).filter(Contestant.id.in_(ids or [-1])).all()}
    governance = Governance(db, rows)
    for item in items:
        cid = _contestant_id_of(item)
        contestant = rows.get(cid)
        if contestant is None:
            continue
        access = entry_access(db, viewer, contestant, governance)
        if not access.allowed or access.mode not in allow_modes:
            continue
        out.append(secure_entry_item(db, viewer, item, contestant, access, privacy, audit=False))
    return out


def secure_entry_refs(db: Session, viewer: Viewer, items: Sequence[dict], *, id_key: str = "contestant_id",
                      author_key: Optional[str] = None) -> List[dict]:
    """For structures that must keep their shape (rankings, vote history): an
    entry the viewer may not receive keeps its position/counters but its
    content fields are withheld (content_restricted=True). Allowed entries get
    media protection and author minimization. Ranking data is never changed."""
    privacy = PrivacyCache(db)
    ids = []
    for it in items:
        v = it.get(id_key)
        if isinstance(v, int) or (isinstance(v, str) and v.isdigit()):
            ids.append(int(v))
    rows = {c.id: c for c in db.query(Contestant).filter(Contestant.id.in_(ids or [-1])).all()}
    governance = Governance(db, rows)
    out = []
    for it in items:
        it = dict(it)
        raw = it.get(id_key)
        contestant = rows.get(int(raw)) if raw is not None and str(raw).isdigit() else None
        access = entry_access(db, viewer, contestant, governance) if contestant is not None else EntryAccess(False)
        if contestant is None or not access.allowed or access.mode not in (Mode.PUBLIC, Mode.OWNER):
            for f in _WITHHELD_FIELDS:
                if f in it:
                    it[f] = None
            it["content_restricted"] = True
            if contestant is not None:
                it = minimize_author(it, contestant.user, privacy, viewer)
            out.append(it)
            continue
        protect = access.mode != Mode.PUBLIC or not access.anonymous_deliverable
        for f in _MEDIA_LIST_FIELDS + _MEDIA_URL_FIELDS:
            if f in it:
                it[f] = _secure_media_value(db, it[f], contestant.id, viewer, protect)
        out.append(minimize_author(it, contestant.user, privacy, viewer))
    return out


def adult_dob_clause():
    """SQL: users whose recorded DOB makes them 18+ today (UNKNOWN is never adult).
    Used where real names/places are matched in search."""
    from datetime import datetime

    today = utc_today()
    try:
        cutoff = today.replace(year=today.year - 18)
    except ValueError:  # 29 February
        cutoff = today.replace(year=today.year - 18, day=28)
    return and_(User.date_of_birth.isnot(None),
                User.date_of_birth <= datetime(cutoff.year, cutoff.month, cutoff.day, 23, 59, 59))


# ---------------------------------------------------------------------------
# Public profiles
# ---------------------------------------------------------------------------

def public_profile(db: Session, user: User, privacy: Optional[PrivacyCache] = None) -> dict:
    """Dedicated safe public-profile representation (built field by field; the
    internal User model is never serialized and trimmed)."""
    privacy = privacy or PrivacyCache(db)
    perm = privacy.display(user)
    return {
        "id": user.id,
        "username": user.username,
        "full_name": user.full_name if perm["name"] else None,
        "first_name": user.first_name if perm["name"] else None,
        "last_name": user.last_name if perm["name"] else None,
        "avatar_url": user.avatar_url,
        "bio": getattr(user, "bio", None) if perm["name"] else None,
        "country": user.country if perm["place"] else None,
        "city": user.city if perm["place"] else None,
        "identity_verified": bool(user.identity_verified) if perm["verification"] else False,
        "address_verified": bool(user.address_verified) if perm["verification"] else False,
    }
