"""Phase 7: age-safe delivery, minor-safe profiles and protected media
(MyHigh5 Child/Teen Safety requirements, Sections 1-32 only).

All users, entries, ratings, media files and tokens are SYNTHETIC. No external
service is called. Nothing here touches a real database or real media.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime

import pytest
from starlette.applications import Starlette
from starlette.routing import Mount
from starlette.testclient import TestClient as StarletteTestClient

from app.core.child_safety import ContentRating as CR
from app.core.security import create_access_token
from app.models.accounting import AuditTrail
from app.models.content_moderation import ContentModeration
from app.models.contest_eligibility import ContestEntrySafety
from app.models.contests import Contestant
from app.models.follow import Follow
from app.models.media import Media
from app.models.voting import ContestantReaction, MyFavorites
from app.services import viewer_access as va
from tests.unit.test_age_gate_registration import auth
from tests.unit.test_phase5_contest_eligibility import contest, person
from tests.unit.test_phase6_content_safety import role_user

NOW = datetime.utcnow()
PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
       b"\x00\x00\x00\rIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82")
SECRET_TITLE = "Secret entry title"
SECRET_DESC = "Secret entry description"


# ---------------------------------------------------------------------------
# helpers (synthetic data only)
# ---------------------------------------------------------------------------

def gov(db, owner, *, rating=None, exposure="PUBLIC", state="APPROVED", escalated=False, resolution=None,
        legacy=False, images=None, deleted=False, title=SECRET_TITLE):
    """An entry with exactly the given Phase 5 exposure + Phase 6 moderation state."""
    ct = contest(db)
    c = Contestant(user_id=owner.id, season_id=ct.id, contest_id=ct.id, title=title, description=SECRET_DESC,
                   image_media_ids=json.dumps(images) if images else None, entry_type="participation",
                   is_active=exposure == "PUBLIC", is_deleted=deleted, city="Arusha", country="Tanzania",
                   author_gender="female")
    db.add(c)
    db.flush()
    if not legacy:
        db.add(ContestEntrySafety(contestant_id=c.id, entry_kind="PERSONAL_SUBMISSION", exposure_status=exposure,
                                  outcome="ALLOW" if exposure == "PUBLIC" else "HOLD", last_evaluated_at=NOW))
        db.add(ContentModeration(contestant_id=c.id, state=state, rating=rating.value if rating else None,
                                 classifier_version="p7-test", evaluated_at=NOW, child_safety_escalated=escalated,
                                 child_safety_resolution=resolution))
    db.commit()
    db.refresh(c)
    return c


KINDS = {
    "GENERAL": dict(rating=CR.GENERAL),
    "TEEN13": dict(rating=CR.TEEN_13_PLUS),
    "TEEN16": dict(rating=CR.TEEN_16_PLUS),
    "ADULT": dict(rating=CR.ADULT_18_PLUS),
    "PROHIBITED": dict(rating=CR.PROHIBITED, exposure="BLOCKED", state="PROHIBITED"),
    "HOLD": dict(exposure="HELD", state="PENDING"),
    "REVIEW": dict(exposure="HELD", state="REVIEW_REQUIRED"),
    "ESCALATED": dict(exposure="CHILD_SAFETY_ESCALATED", state="CHILD_SAFETY_ESCALATED", escalated=True),
    "LEGACY": dict(legacy=True),
}


def make_viewer(db, name, owner):
    return {
        "anonymous": lambda: None,
        "unknown": lambda: person(db, None),
        "under13": lambda: person(db, 10),
        "teen13": lambda: person(db, 14),
        "teen16": lambda: person(db, 16),
        "adult": lambda: person(db, 30),
        "owner": lambda: owner,
        "moderator": lambda: role_user(db, "moderate_content"),
        "admin": lambda: person(db, 40, admin=True),
        "resolver": lambda: role_user(db, "moderate_content", "child_safety_resolve"),
    }[name]()


P, OWN, MOD, CSR = "PUBLIC", "OWNER", "MODERATION", "CHILD_SAFETY_REVIEW"
NF, SIGN, AGE_REQ, RESTR = "NOT_FOUND", "SIGN_IN_REQUIRED", "AGE_REQUIRED", "AGE_RESTRICTED"
_STAFF = {"GENERAL": P, "TEEN13": P, "TEEN16": P, "ADULT": P, "PROHIBITED": MOD, "HOLD": MOD, "REVIEW": MOD,
          "ESCALATED": NF, "LEGACY": P}
_HIDDEN = {"PROHIBITED": NF, "HOLD": NF, "REVIEW": NF, "ESCALATED": NF, "LEGACY": P, "GENERAL": P}
EXPECTED = {
    "anonymous": {**_HIDDEN, "TEEN13": SIGN, "TEEN16": SIGN, "ADULT": SIGN},
    "unknown": {**_HIDDEN, "TEEN13": AGE_REQ, "TEEN16": AGE_REQ, "ADULT": AGE_REQ},
    "under13": {**_HIDDEN, "TEEN13": RESTR, "TEEN16": RESTR, "ADULT": RESTR},
    "teen13": {**_HIDDEN, "TEEN13": P, "TEEN16": RESTR, "ADULT": RESTR},
    "teen16": {**_HIDDEN, "TEEN13": P, "TEEN16": P, "ADULT": RESTR},
    "adult": {**_HIDDEN, "TEEN13": P, "TEEN16": P, "ADULT": P},
    "owner": {**_STAFF, "PROHIBITED": OWN, "HOLD": OWN, "REVIEW": OWN},
    "moderator": _STAFF,
    "admin": _STAFF,   # is_admin moderates, but never implies child_safety_resolve
    "resolver": {**_STAFF, "ESCALATED": CSR},
}


def outcome(access: va.EntryAccess) -> str:
    return access.mode if access.allowed else access.denial


@pytest.fixture
def media_root(tmp_path, monkeypatch):
    from app.core import storage

    monkeypatch.setattr(storage, "media_storage_roots", lambda: [str(tmp_path)])
    return tmp_path


def stored_file(root, owner, name=None, data=PNG):
    name = name or f"{uuid.uuid4().hex}.png"
    d = root / str(owner.id)
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_bytes(data)
    return name, f"/api/v1/media/file/{owner.id}/{name}"


def token(owner, name, entry, viewer, **kw):
    return va.sign_media(owner.id, name, contestant_id=entry.id, viewer_id=viewer.id if viewer else None, **kw)


def get_media(client, owner, name, grant=None):
    url = f"/api/v1/media/file/{owner.id}/{name}"
    return client.get(url, params={"g": grant} if grant else None)


def hdr(user):
    return auth(user) if user is not None else {}


# ===========================================================================
# VIEWER MATRIX (entry decision + listing coherence)
# ===========================================================================

@pytest.mark.parametrize("viewer_name", list(EXPECTED))
def test_viewer_matrix(db, viewer_name):
    owner = person(db, 30)
    entries = {k: gov(db, owner, **kw) for k, kw in KINDS.items()}
    user = make_viewer(db, viewer_name, owner)
    viewer = va.viewer_for(db, user)
    got = {k: outcome(va.entry_access(db, viewer, e)) for k, e in entries.items()}
    assert got == EXPECTED[viewer_name]

    # Public listing == exactly the entries delivered in PUBLIC mode (same decision, in SQL).
    listed = {cid for (cid,) in db.query(Contestant.id).filter(Contestant.is_deleted == False,  # noqa: E712
                                                                va.listing_clause(viewer)).all()}
    assert listed == {e.id for k, e in entries.items() if got[k] == P}


def test_adult_18_plus_never_reaches_minor_unknown_or_anonymous(db):
    owner = person(db, 30)
    e = gov(db, owner, rating=CR.ADULT_18_PLUS)
    for u in (None, person(db, None), person(db, 12), person(db, 15), person(db, 17)):
        v = va.viewer_for(db, u)
        assert CR.ADULT_18_PLUS not in v.allowed_ratings
        assert not va.entry_access(db, v, e).allowed


def test_defensive_states_fail_closed(db):
    owner = person(db, 30)
    prohibited_public = gov(db, owner, rating=CR.PROHIBITED, state="PROHIBITED")  # inconsistent: still denied
    unrated_public = gov(db, owner, rating=None, state="PENDING")   # governed, exposed, but no final rating
    deleted = gov(db, owner, rating=CR.GENERAL, deleted=True)
    for u in (None, person(db, 30), owner, role_user(db, "moderate_content", "child_safety_resolve")):
        v = va.viewer_for(db, u)
        assert outcome(va.entry_access(db, v, prohibited_public)) == NF
        assert outcome(va.entry_access(db, v, deleted)) == NF
    assert outcome(va.entry_access(db, va.viewer_for(db, person(db, 30)), unrated_public)) == NF
    assert outcome(va.entry_access(db, va.viewer_for(db, owner), unrated_public)) == OWN


def test_confirmed_child_safety_is_never_delivered_to_owner_or_ordinary_staff(db):
    owner = person(db, 30)
    e = gov(db, owner, exposure="BLOCKED", state="PROHIBITED", rating=CR.PROHIBITED, resolution="CONFIRMED")
    for u in (owner, person(db, 40, admin=True), role_user(db, "moderate_content")):
        assert outcome(va.entry_access(db, va.viewer_for(db, u), e)) == NF


def test_age_is_computed_live_and_unknown_is_never_adult(db):
    v = va.viewer_for(db, person(db, None))
    assert v.tier.value == "UNKNOWN" and v.allowed_ratings == {CR.GENERAL}
    assert va.viewer_for(db, object()) == va.ANONYMOUS  # no identity -> anonymous policy


def test_listing_pagination_is_coherent(db):
    owner = person(db, 30)
    ids = []
    for i in range(12):
        ids.append(gov(db, owner, rating=CR.GENERAL if i % 2 == 0 else CR.TEEN_16_PLUS).id)
    viewer = va.viewer_for(db, person(db, 14))
    q = (db.query(Contestant.id).filter(Contestant.is_deleted == False, va.listing_clause(viewer))  # noqa: E712
         .order_by(Contestant.id))
    pages = [[cid for (cid,) in q.offset(o).limit(3).all()] for o in (0, 3, 6)]
    assert [len(p) for p in pages] == [3, 3, 0]
    flat = pages[0] + pages[1]
    assert flat == [cid for i, cid in enumerate(ids) if i % 2 == 0]


def test_historical_entries_are_not_rewritten(db):
    owner = person(db, 30)
    legacy = gov(db, owner, legacy=True)
    before = (db.query(ContentModeration).count(), db.query(ContestEntrySafety).count())
    for u in (None, person(db, 12), person(db, None)):
        assert outcome(va.entry_access(db, va.viewer_for(db, u), legacy)) == P
    assert (db.query(ContentModeration).count(), db.query(ContestEntrySafety).count()) == before


# ===========================================================================
# DETAIL / WRITE ENDPOINTS
# ===========================================================================

def test_detail_denials_never_carry_content(client, db):
    owner = person(db, 30)
    teen16 = gov(db, owner, rating=CR.TEEN_16_PLUS)
    held = gov(db, owner, exposure="HELD", state="PENDING")
    cases = [(person(db, 14), teen16, 403, RESTR), (None, teen16, 403, SIGN), (person(db, None), teen16, 403, AGE_REQ),
             (person(db, 30), held, 404, None), (None, held, 404, None)]
    for user, entry, code, reason in cases:
        r = client.get(f"/api/v1/contestants/{entry.id}", headers=hdr(user))
        assert r.status_code == code, r.text
        assert SECRET_TITLE not in r.text and SECRET_DESC not in r.text and "/media/" not in r.text
        if reason:
            assert r.json()["detail"] == {"code": "CONTENT_RESTRICTED", "reason": reason,
                                          "message": va.EntryAccess(False, denial=reason).client_error()["message"]}
    ok = client.get(f"/api/v1/contestants/{teen16.id}", headers=auth(person(db, 16)))
    assert ok.status_code == 200 and ok.json()["title"] == SECRET_TITLE
    assert ok.headers["cache-control"] == "private, no-store" and "Authorization" in ok.headers["vary"]
    mine = client.get(f"/api/v1/contestants/{held.id}", headers=auth(owner))
    assert mine.status_code == 200 and mine.json()["title"] == SECRET_TITLE


def test_votes_views_and_interactions_require_public_delivery(client, db):
    owner = person(db, 30)
    teen16 = gov(db, owner, rating=CR.TEEN_16_PLUS)
    held = gov(db, owner, exposure="HELD", state="PENDING")
    t13 = person(db, 14)
    for entry, user in ((teen16, t13), (held, person(db, 30)), (held, owner)):
        h = auth(user)
        assert client.post(f"/api/v1/contestants/{entry.id}/vote", headers=h).status_code == 404
        assert client.post(f"/api/v1/contestants/{entry.id}/view", headers=h, json={"watched_seconds": 40}) \
            .status_code == 404
        assert client.post(f"/api/v1/contestants/{entry.id}/favorite", headers=h).status_code == 404
        assert client.post(f"/api/v1/contestants/{entry.id}/reaction", headers=h,
                           json={"contestant_id": entry.id, "reaction_type": "like"}).status_code == 404
        assert client.post(f"/api/v1/contestants/{entry.id}/share", headers=h,
                           json={"contestant_id": entry.id, "share_link": "x"}).status_code == 404
        assert client.post(f"/api/v1/comments/{entry.id}/comments", headers=h,
                           json={"content": "hi", "target_type": "contest"}).status_code in (403, 404)
    for path in ("shares", "reactions", "reactions/details", "votes/details", "favorites/details"):
        assert client.get(f"/api/v1/contestants/{held.id}/{path}").status_code == 404, path
        r = client.get(f"/api/v1/contestants/{teen16.id}/{path}", headers=auth(t13))
        assert r.status_code == 403 and SECRET_TITLE not in r.text, path
    assert client.get(f"/api/v1/comments/{held.id}/comments").status_code == 404
    assert client.get(f"/api/v1/comments/{held.id}/commenters").status_code == 404


def test_interaction_lists_minimize_minor_and_unknown_people(client, db):
    owner = person(db, 30)
    e = gov(db, owner, rating=CR.GENERAL)
    kid = person(db, 14, full_name="Kid Realname")
    anon_age = person(db, None, full_name="Unknown Realname")
    grown = person(db, 30, full_name="Grown Realname")
    for u in (kid, anon_age, grown):
        db.add(ContestantReaction(user_id=u.id, contestant_id=e.id, reaction_type="like"))
        db.add(MyFavorites(user_id=u.id, contestant_id=e.id))
    db.commit()
    body = client.get(f"/api/v1/contestants/{e.id}/favorites/details").json()
    names = {u["user_id"]: u["full_name"] for u in body["users"]}
    assert names == {kid.id: None, anon_age.id: None, grown.id: "Grown Realname"}
    text = client.get(f"/api/v1/contestants/{e.id}/reactions/details").text
    assert "Kid Realname" not in text and "Unknown Realname" not in text and "Grown Realname" in text


def test_debug_listing_is_admin_only(client, db):
    assert client.get("/api/v1/contestants/debug/all-contestants").status_code == 401
    assert client.get("/api/v1/contestants/debug/all-contestants", headers=auth(person(db, 30))).status_code == 404
    assert client.get("/api/v1/contestants/debug/all-contestants",
                      headers=auth(person(db, 40, admin=True))).status_code == 200


def test_user_entry_lists(client, db):
    owner = person(db, 30)
    pub = gov(db, owner, rating=CR.GENERAL)
    held = gov(db, owner, exposure="HELD", state="PENDING")
    esc = gov(db, owner, exposure="CHILD_SAFETY_ESCALATED", state="CHILD_SAFETY_ESCALATED", escalated=True)
    adult_only = gov(db, owner, rating=CR.ADULT_18_PLUS)
    other = client.get(f"/api/v1/contestants/user/{owner.id}/entries", headers=auth(person(db, 14))).json()
    assert {x["id"] for x in other} == {pub.id}
    mine = client.get(f"/api/v1/contestants/user/{owner.id}/entries", headers=auth(owner)).json()
    assert {x["id"] for x in mine} == {pub.id, held.id, adult_only.id}
    my = client.get("/api/v1/contestants/user/my-entries", headers=auth(owner)).json()
    assert esc.id not in {x["id"] for x in my}


# ===========================================================================
# PROTECTED MEDIA (viewer-bound grant + media session; request-time decision)
# ===========================================================================

def session(client, user):
    """Make `client` behave as a browser signed in as `user` (None = logged out)."""
    client.cookies.clear()
    if user is not None:
        r = client.post("/api/v1/media/session", headers=auth(user))
        assert r.status_code == 204, r.text
        assert va.MEDIA_SESSION_COOKIE in client.cookies


def protected_world(db, media_root, rating=CR.TEEN_16_PLUS, **kw):
    owner = person(db, 30)
    name, url = stored_file(media_root, owner)
    entry = gov(db, owner, rating=rating, images=[url], **kw)
    return owner, name, url, entry


def test_A_B_C_grants_are_bound_to_the_viewer_not_to_the_url(client, db, media_root):
    owner, name, _, entry = protected_world(db, media_root)
    viewer_a, viewer_b = person(db, 16), person(db, 30)       # B is even an ADULT allowed to see the entry
    grant_a = token(owner, name, entry, viewer_a)

    session(client, viewer_a)                                   # A: own session + own grant
    ok = get_media(client, owner, name, grant_a)
    assert ok.status_code == 200 and ok.content == PNG
    session(client, viewer_b)                                   # B: copies A's URL
    assert get_media(client, owner, name, grant_a).status_code == 404
    session(client, None)                                       # C: logged-out copy of A's URL
    assert get_media(client, owner, name, grant_a).status_code == 404
    # Bearer header identities are held to the same rule.
    url = f"/api/v1/media/file/{owner.id}/{name}"
    assert client.get(url, params={"g": grant_a}, headers=auth(viewer_b)).status_code == 404
    assert client.get(url, params={"g": grant_a}, headers=auth(viewer_a)).status_code == 200
    # An invalid bearer never falls back to a (valid) cookie.
    session(client, viewer_a)
    assert client.get(url, params={"g": grant_a}, headers={"Authorization": "Bearer junk"}).status_code == 404
    # No grant at all (the historical public URL) -> refused even for A.
    assert get_media(client, owner, name).status_code == 404


def test_D_E_F_G_grant_integrity(client, db, media_root):
    owner, name, _, entry = protected_world(db, media_root)
    other_name, other_url = stored_file(media_root, owner)
    gov(db, owner, rating=CR.TEEN_16_PLUS, images=[other_url])
    unrelated = gov(db, owner, rating=CR.TEEN_16_PLUS)
    viewer = person(db, 16)
    session(client, viewer)
    good = token(owner, name, entry, viewer)
    body, sig = good.split(".")
    forged_body = va._b64(json.dumps({"u": owner.id, "f": name, "c": entry.id, "v": viewer.id,
                                      "e": int(time.time()) + 99999}, separators=(",", ":"),
                                     sort_keys=True).encode())
    denied = {
        "D expired": token(owner, name, entry, viewer, now=time.time() - 10_000),
        "E tampered signature": body + "." + sig[:-2] + ("AA" if sig[-2:] != "AA" else "BB"),
        "E forged payload": forged_body + "." + sig,
        "F other media": token(owner, other_name, entry, viewer),
        "G other entry": token(owner, name, unrelated, viewer),
        "session value as grant": client.cookies.get(va.MEDIA_SESSION_COOKIE),
        "login token as grant": create_access_token(subject=viewer.id),
    }
    for label, bad in denied.items():
        assert get_media(client, owner, name, bad).status_code == 404, label
    assert get_media(client, owner, name, good).status_code == 200


def test_media_session_cookie_is_scoped_and_unforgeable(client, db, media_root):
    owner, name, _, entry = protected_world(db, media_root)
    viewer = person(db, 16)
    r = client.post("/api/v1/media/session", headers=auth(viewer))
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie and "path=/api/v1/media/file" in cookie
    assert "max-age=3600" in cookie
    assert client.post("/api/v1/media/session").status_code == 401        # needs a real sign-in
    grant = token(owner, name, entry, viewer)
    for forged in (va.sign_media_session(viewer.id, now=time.time() - 10_000),     # expired
                   token(owner, name, entry, viewer),                             # a grant is not a session
                   create_access_token(subject=viewer.id),                         # a login token is not one
                   "e30.AAAA"):
        client.cookies.clear()
        client.cookies.set(va.MEDIA_SESSION_COOKIE, forged, path="/api/v1/media/file")
        assert get_media(client, owner, name, grant).status_code == 404
    assert client.delete("/api/v1/media/session").status_code == 204          # logout clears it
    assert 'max-age=0' in client.delete("/api/v1/media/session").headers["set-cookie"].lower() \
        or 'expires=' in client.delete("/api/v1/media/session").headers["set-cookie"].lower()


def test_viewer_dependent_responses_refresh_the_same_viewers_session(client, db, media_root):
    owner, name, _, entry = protected_world(db, media_root, rating=CR.ADULT_18_PLUS)
    viewer = person(db, 30)
    client.cookies.clear()
    detail = client.get(f"/api/v1/contestants/{entry.id}", headers=auth(viewer))
    assert detail.status_code == 200 and va.MEDIA_SESSION_COOKIE in client.cookies
    assert va.verify_media_session(client.cookies.get(va.MEDIA_SESSION_COOKIE)) == viewer.id
    path, grant = json.loads(detail.json()["image_media_ids"])[0].split("?g=")
    assert client.get(path, params={"g": grant}).status_code == 200     # same browser, no header
    session(client, person(db, 30))
    assert client.get(path, params={"g": grant}).status_code == 404     # another adult's browser


def test_H_I_owner_remediation_links_are_owner_only(client, db, media_root):
    owner, name, _, held = protected_world(db, media_root, rating=None, exposure="HELD", state="REVIEW_REQUIRED")
    grant = token(owner, name, held, owner)
    session(client, owner)
    assert get_media(client, owner, name, grant).status_code == 200            # H
    for other in (person(db, 30), person(db, 40, admin=False)):
        session(client, other)
        assert get_media(client, owner, name, grant).status_code == 404        # I
    # The other user's OWN grant for the held entry is refused too (not public, not theirs).
    stranger = person(db, 30)
    session(client, stranger)
    assert get_media(client, owner, name, token(owner, name, held, stranger)).status_code == 404


def test_J_K_L_moderation_media_is_rechecked_at_request_time(client, db, media_root):
    from app.models.user import Permission

    owner, name, _, held = protected_world(db, media_root, rating=None, exposure="HELD", state="PENDING")
    ename, eurl = stored_file(media_root, owner)
    esc = gov(db, owner, exposure="CHILD_SAFETY_ESCALATED", state="CHILD_SAFETY_ESCALATED", escalated=True,
              images=[eurl])
    mod = role_user(db, "moderate_content")
    resolver = role_user(db, "moderate_content", "child_safety_resolve")
    admin = person(db, 40, admin=True)

    session(client, mod)                                                        # J
    held_grant = token(owner, name, held, mod)
    assert get_media(client, owner, name, held_grant).status_code == 200
    # Permission withdrawn -> the SAME grant stops working immediately.
    mod.role.permissions = [p for p in mod.role.permissions if p.name != "moderate_content"]
    db.commit()
    assert get_media(client, owner, name, held_grant).status_code == 404
    assert db.query(Permission).filter(Permission.name == "moderate_content").count() == 1

    for staff in (role_user(db, "moderate_content"), admin, owner):             # K (+ admin, owner)
        session(client, staff)
        assert get_media(client, owner, ename, token(owner, ename, esc, staff)).status_code == 404
    session(client, resolver)                                                   # L
    assert get_media(client, owner, ename, token(owner, ename, esc, resolver)).status_code == 200
    session(client, admin)                                                      # resolver's link != admin's
    assert get_media(client, owner, ename, token(owner, ename, esc, resolver)).status_code == 404


def test_M_N_kyc_and_traversal_are_never_served(client, db, media_root):
    owner = person(db, 30)
    kyc, url = stored_file(media_root, owner, name="kyc_poa_secret.png")
    entry = gov(db, owner, rating=CR.TEEN_16_PLUS, images=[url])
    session(client, owner)
    assert get_media(client, owner, kyc, token(owner, kyc, entry, owner)).status_code == 404
    public_kyc, _ = stored_file(media_root, owner, name="kyc_id_front.png")        # not even referenced
    assert get_media(client, owner, public_kyc).status_code == 404
    for bad in ("..%2F..%2Fsecret.png", "%2e%2e%2fx.png", "a%5Cb.png", "..", "%00x.png"):
        r = client.get(f"/api/v1/media/file/{owner.id}/{bad}")
        # ".." is normalized by the client to another (auth-required) route: never a file.
        assert r.status_code in (401, 404) and PNG not in r.content, bad


def test_O_database_failure_fails_closed(client, db, media_root, monkeypatch):
    owner, name, _, entry = protected_world(db, media_root, rating=CR.GENERAL)
    assert get_media(client, owner, name).status_code == 200                       # public while healthy

    def boom(*a, **k):
        raise RuntimeError("db down")

    monkeypatch.setattr(va, "entries_using_file", boom)
    assert get_media(client, owner, name).status_code == 404
    session(client, owner)
    assert get_media(client, owner, name, token(owner, name, entry, owner)).status_code == 404


def test_P_protected_responses_are_private_and_not_the_public_cache_key(client, db, media_root):
    owner, name, url, entry = protected_world(db, media_root)
    viewer = person(db, 16)
    session(client, viewer)
    r = get_media(client, owner, name, token(owner, name, entry, viewer))
    assert r.status_code == 200
    assert r.headers["cache-control"] == "private, no-store"
    assert "Cookie" in r.headers["vary"] and "Authorization" in r.headers["vary"]
    assert r.headers["referrer-policy"] == "no-referrer" and r.headers["x-content-type-options"] == "nosniff"
    assert "access-control-allow-origin" not in r.headers
    # The protected delivery URL differs from the historical public URL (distinct cache key).
    detail = client.get(f"/api/v1/contestants/{entry.id}", headers=auth(viewer)).json()
    delivered = json.loads(detail["image_media_ids"])[0]
    assert delivered != url and delivered.startswith(url + "?g=")


def test_Q_public_general_media_needs_no_authentication(client, db, media_root):
    owner, name, url, entry = protected_world(db, media_root, rating=CR.GENERAL)
    client.cookies.clear()
    r = get_media(client, owner, name)
    assert r.status_code == 200 and r.headers["cache-control"] == "public, max-age=86400"
    body = client.get(f"/api/v1/contestants/{entry.id}").json()                   # anonymous
    assert json.loads(body["image_media_ids"]) == [url]                           # plain URL, no grant
    legacy_name, legacy_url = stored_file(media_root, owner)
    gov(db, owner, legacy=True, images=[legacy_url])
    assert get_media(client, owner, legacy_name).status_code == 200


def test_anonymous_grant_only_covers_anonymously_deliverable_content(client, db, media_root):
    """A public GENERAL entry sharing a file with a held entry: anonymous viewers get a
    grant for the PUBLIC entry only; it never unlocks the held entry's context."""
    owner = person(db, 30)
    name, url = stored_file(media_root, owner)
    public = gov(db, owner, rating=CR.GENERAL, images=[url])
    held = gov(db, owner, exposure="HELD", state="PENDING", images=[url])
    client.cookies.clear()
    assert get_media(client, owner, name).status_code == 404                      # file is protected
    assert get_media(client, owner, name, token(owner, name, public, None)).status_code == 200
    assert get_media(client, owner, name, token(owner, name, held, None)).status_code == 404


def test_R_no_reusable_credential_in_the_request_line_or_logs(client, db, media_root, caplog):
    """The Apache-facing request target (method + path + query) is exactly what an
    access log records. Replaying it from any other browser gets nothing."""
    owner, name, _, entry = protected_world(db, media_root)
    viewer = person(db, 16)
    session(client, viewer)
    session_value = client.cookies.get(va.MEDIA_SESSION_COOKIE)
    detail = client.get(f"/api/v1/contestants/{entry.id}", headers=auth(viewer)).json()
    request_target = json.loads(detail["image_media_ids"])[0]                     # what <img src> requests
    assert "?g=" in request_target and session_value not in request_target
    with caplog.at_level(logging.DEBUG):
        assert client.get(request_target).status_code == 200                      # the viewer's own browser
    logged_line = f'1.2.3.4 - - [x] "GET {request_target} HTTP/1.1" 200 68 "-" "UA"'   # Apache "combined"
    replay_target = logged_line.split('"GET ', 1)[1].split(" HTTP/1.1", 1)[0]
    for replayer in (None, person(db, 16), person(db, 30)):                       # log reader / other users
        session(client, replayer)
        assert client.get(replay_target).status_code == 404
    server_side = [r.getMessage() for r in caplog.records if not r.name.startswith(("httpx", "httpcore"))]
    assert not any(session_value in m for m in server_side)
    assert not any(request_target.split("?g=")[1] in m for m in server_side)
    import main  # noqa: F401 - installs the access-log filters
    record = logging.LogRecord("uvicorn.access", logging.INFO, __file__, 1, '%s - "%s %s HTTP/%s" %d',
                               ("1.2.3.4:1", "GET", request_target, "1.1", 200), None)
    for f in logging.getLogger("uvicorn.access").filters:
        f.filter(record)
    assert "g=[REDACTED]" in record.getMessage()


def test_escalated_and_deleted_media(client, db, media_root):
    owner = person(db, 30)
    dname, durl = stored_file(media_root, owner)
    gone = gov(db, owner, exposure="HELD", state="PENDING", images=[durl], deleted=True)
    session(client, owner)
    assert get_media(client, owner, dname).status_code == 404
    assert get_media(client, owner, dname, token(owner, dname, gone, owner)).status_code == 404


def test_media_referenced_by_media_id_is_protected(client, db, media_root):
    owner = person(db, 30)
    name, url = stored_file(media_root, owner)
    m = Media(title="i", media_type="image", path="p", url=url, user_id=owner.id)
    db.add(m)
    db.commit()
    entry = gov(db, owner, rating=CR.ADULT_18_PLUS, images=[str(m.id)])
    assert get_media(client, owner, name).status_code == 404
    detail = client.get(f"/api/v1/contestants/{entry.id}", headers=auth(person(db, 30))).json()
    signed = json.loads(detail["image_media_ids"])[0]
    path, grant = signed.split("?g=")
    assert client.get(path, params={"g": grant}).status_code == 200


def test_payload_media_is_signed_only_when_needed(client, db, media_root):
    owner = person(db, 30)
    _, gurl = stored_file(media_root, owner)
    _, turl = stored_file(media_root, owner)
    general = gov(db, owner, rating=CR.GENERAL, images=[gurl])
    teen = gov(db, owner, rating=CR.TEEN_16_PLUS, images=[turl])
    t16 = person(db, 16)
    g = client.get(f"/api/v1/contestants/{general.id}", headers=auth(t16)).json()
    assert json.loads(g["image_media_ids"]) == [gurl]
    t = client.get(f"/api/v1/contestants/{teen.id}", headers=auth(t16)).json()
    assert json.loads(t["image_media_ids"])[0].startswith(turl + "?g=")
    denied = client.get(f"/api/v1/contestants/{teen.id}", headers=auth(person(db, 14)))
    assert turl not in denied.text


def test_static_media_mount_refuses_protected_files(db, media_root, monkeypatch):
    from app.core import storage
    from app.db import session as session_module
    from tests.conftest import TestingSessionLocal

    monkeypatch.setattr(session_module, "SessionLocal", TestingSessionLocal)
    owner = person(db, 30)
    pname, purl = stored_file(media_root, owner)
    gname, gurl = stored_file(media_root, owner)
    gov(db, owner, rating=CR.TEEN_13_PLUS, images=[purl])
    gov(db, owner, rating=CR.GENERAL, images=[gurl])
    lname, _ = stored_file(media_root, owner)
    gov(db, owner, exposure="HELD", state="PENDING", images=[f"/media/{owner.id}/{lname}"])  # legacy URL form
    kname, _ = stored_file(media_root, owner, name="kyc_poa_static.png")
    mini = Starlette(routes=[Mount("/media", app=storage.PublicMediaStaticFiles(directory=str(media_root)))])
    with StarletteTestClient(mini) as c:
        assert c.get(f"/media/{owner.id}/{gname}").status_code == 200
        for path in (f"/media/{owner.id}/{pname}", f"/media/{owner.id}/{lname}",
                     # alternate spellings resolve to the same protected file
                     f"/media/{owner.id}/./{pname}", f"/media/{owner.id}//{pname}",
                     f"/media/./{owner.id}/{pname}", f"/media/{owner.id}/x/../{pname}",
                     f"/media/{owner.id}/%2e/{pname}",
                     f"/media/{owner.id}/{kname}", f"/media/{owner.id}/../{owner.id}/{kname}",
                     "/media/../../etc/passwd", f"/media/{owner.id}/..%2f..%2fsecret"):
            assert c.get(path).status_code == 404, path

        def boom(*a, **k):
            raise RuntimeError("db down")

        monkeypatch.setattr(va, "media_is_protected", boom)                     # O: DB failure
        assert c.get(f"/media/{owner.id}/{gname}").status_code == 404
        assert c.get(f"/media/{owner.id}/{pname}").status_code == 404


def test_only_one_static_media_mount_and_it_is_authorization_aware(app):
    from app.core import storage
    from starlette.staticfiles import StaticFiles

    static_mounts = [r for r in app.routes if isinstance(getattr(r, "app", None), StaticFiles)]
    assert [m.path for m in static_mounts] == ["/media"]
    assert all(isinstance(m.app, storage.PublicMediaStaticFiles) for m in static_mounts)


def test_grant_keys_are_purpose_separated(db):
    viewer = person(db, 16)
    grant = va.sign_media(1, "a.png", contestant_id=2, viewer_id=viewer.id)
    sess = va.sign_media_session(viewer.id)
    assert va.verify_media_session(grant) is None and va.verify_media_token(sess, 1, "a.png") is None
    assert va._media_key() != va._session_key()
    payload = va.verify_media_token(grant, 1, "a.png")
    assert payload["e"] - time.time() <= va.MEDIA_TOKEN_TTL_SECONDS <= 900
    assert len(grant.split(".")[1]) >= 43                                        # HMAC-SHA256


# ===========================================================================
# MODERATION ACCESS AUDIT
# ===========================================================================

def test_protected_access_is_audited(client, db):
    owner = person(db, 30)
    held = gov(db, owner, exposure="HELD", state="REVIEW_REQUIRED")
    esc = gov(db, owner, exposure="CHILD_SAFETY_ESCALATED", state="CHILD_SAFETY_ESCALATED", escalated=True)
    pub = gov(db, owner, rating=CR.GENERAL)
    mod = role_user(db, "moderate_content")
    resolver = role_user(db, "moderate_content", "child_safety_resolve")

    def audits():
        return [(a.record_id, a.action, a.user_id) for a in
                db.query(AuditTrail).filter(AuditTrail.table_name == "protected_content_access").all()]

    assert client.get(f"/api/v1/contestants/{pub.id}", headers=auth(mod)).status_code == 200
    assert client.get(f"/api/v1/contestants/{held.id}", headers=auth(owner)).status_code == 200
    assert audits() == []
    assert client.get(f"/api/v1/contestants/{held.id}", headers=auth(mod)).status_code == 200
    assert client.get(f"/api/v1/contestants/{esc.id}", headers=auth(mod)).status_code == 404
    assert client.get(f"/api/v1/contestants/{esc.id}", headers=auth(resolver)).status_code == 200
    db.expire_all()
    assert sorted(audits()) == sorted([(held.id, "ACCESS_MODERATION", mod.id),
                                       (esc.id, "ACCESS_CHILD_SAFETY_REVIEW", resolver.id)])


# ===========================================================================
# AUTHOR / PROFILE PRIVACY
# ===========================================================================

def test_entry_author_minimization(db):
    kid = person(db, 14, full_name="Kid Realname")
    grown = person(db, 30, full_name="Grown Realname")
    item = lambda c: {"id": c.id, "user_id": c.user_id, "author_name": c.user.full_name, "author_city": "Arusha",  # noqa: E731
                      "author_country": "Tanzania", "author_gender": "female", "nominator_city": "Arusha",
                      "title": c.title}
    ek, eg = gov(db, kid, rating=CR.GENERAL), gov(db, grown, rating=CR.GENERAL)
    out = {x["id"]: x for x in va.secure_entry_list(db, va.viewer_for(db, person(db, 30)), [item(ek), item(eg)])}
    assert out[ek.id]["author_name"] == kid.username
    assert out[ek.id]["author_city"] is None and out[ek.id]["author_gender"] is None
    assert out[ek.id]["nominator_city"] is None and out[ek.id]["title"] == SECRET_TITLE
    assert out[eg.id]["author_name"] == "Grown Realname" and out[eg.id]["author_city"] == "Arusha"
    self_view = va.secure_entry_list(db, va.viewer_for(db, kid), [item(ek)])[0]
    assert self_view["author_name"] == "Kid Realname"                       # an author sees their own details


def test_nested_people_are_minimized(db):
    kid = person(db, 13, full_name="Kid Voter", city="Moshi")
    grown = person(db, 30, full_name="Grown Voter")
    owner = person(db, 30)
    e = gov(db, owner, rating=CR.GENERAL)
    item = {"id": e.id, "votes": [{"user_id": kid.id, "full_name": "Kid Voter", "city": "Moshi"},
                                  {"user_id": grown.id, "full_name": "Grown Voter"}],
            "reactions": {"like": [{"user_id": kid.id, "full_name": "Kid Voter"}]}}
    out = va.secure_entry_list(db, va.viewer_for(db, owner), [item])[0]
    assert out["votes"][0]["full_name"] is None and out["votes"][0]["city"] is None
    assert out["votes"][1]["full_name"] == "Grown Voter"
    assert out["reactions"]["like"][0]["full_name"] is None


@pytest.mark.parametrize("target_age", [14, 10, None])
def test_public_profile_floor_for_minor_and_unknown(client, db, target_age):
    target = person(db, target_age, full_name="Real Person", first_name="Real", last_name="Person", city="Arusha",
                    avatar_url="/a.png", identity_verified=True, address_verified=True)
    for path in (f"/api/v1/users/{target.id}", f"/api/v1/users/by-username/{target.username}"):
        body = client.get(path, headers=auth(person(db, 30))).json()
        assert body["username"] == target.username and body["avatar_url"] == "/a.png"
        for field in ("full_name", "first_name", "last_name", "city", "country", "bio"):
            assert body.get(field) is None, field
        assert body["identity_verified"] is False and body["address_verified"] is False
        assert "Real Person" not in json.dumps(body)
    assert client.get(f"/api/v1/users/{target.id}", headers=auth(target)).json()["full_name"] == "Real Person"
    admin_view = client.get(f"/api/v1/users/{target.id}", headers=auth(person(db, 40, admin=True))).json()
    assert admin_view["full_name"] == "Real Person"


def test_adult_public_profile_unchanged(client, db):
    target = person(db, 30, full_name="Adult Person", city="Arusha", identity_verified=True)
    body = client.get(f"/api/v1/users/{target.id}", headers=auth(person(db, 30))).json()
    assert body["full_name"] == "Adult Person" and body["city"] == "Arusha" and body["identity_verified"] is True
    assert body["country"] == "Tanzania"


def test_follow_lists_and_user_search_respect_the_floor(client, db):
    star = person(db, 30)
    kid = person(db, 14, full_name="Kid Follower", bio="about me")
    grown = person(db, 30, full_name="Grown Follower")
    for u in (kid, grown):
        db.add(Follow(follower_id=u.id, following_id=star.id))
    db.commit()
    viewer = person(db, 30)
    rows = {r["id"]: r for r in client.get(f"/api/v1/users/{star.id}/followers", headers=auth(viewer)).json()}
    assert rows[kid.id]["full_name"] is None and rows[kid.id]["bio"] is None
    assert rows[grown.id]["full_name"] == "Grown Follower"
    found = lambda q: {r["id"] for r in client.get("/api/v1/users/search", params={"q": q},  # noqa: E731
                                                     headers=auth(viewer)).json()}
    assert kid.id not in found("Kid Follower")        # a minor's real name is not searchable
    assert kid.id in found(kid.username)
    assert grown.id in found("Grown Follower")


def test_search_is_age_safe(client, db):
    kid = person(db, 14, full_name="Kidname Searchable", city="Kidtown")
    grown = person(db, 30, full_name="Adultname Searchable")
    k_entry = gov(db, kid, rating=CR.GENERAL, title="Kid song")
    a_entry = gov(db, grown, rating=CR.GENERAL, title="Adult song")
    gov(db, grown, exposure="HELD", state="PENDING", title="Held hiddenword")
    gov(db, grown, rating=CR.TEEN_16_PLUS, title="Teen sixteen word")
    viewer, t13 = person(db, 30), person(db, 14)

    def ids(q, user=viewer):
        return {int(r["id"]) for r in client.get("/api/v1/search/contestants", params={"q": q},
                                                 headers=auth(user)).json()}

    assert k_entry.id not in ids("Kidname") and k_entry.id not in ids("Kidtown")
    assert a_entry.id in ids("Adultname")
    assert k_entry.id in ids("Kid song") and k_entry.id in ids(kid.username)
    assert ids("hiddenword") == set()
    assert ids("sixteen word", t13) == set() and len(ids("sixteen word")) == 1
    combined = client.get("/api/v1/search", params={"q": "Kid song"}, headers=auth(viewer)).json()["contestant"]
    row = next(r for r in combined if int(r["id"]) == k_entry.id)
    assert row["full_name"] == kid.username and row["city"] is None


# ===========================================================================
# SHAPE-PRESERVING SURFACES (vote history, TopHigh5, favorites)
# ===========================================================================

def test_vote_history_keeps_slots_but_withholds_restricted_content(db):
    owner = person(db, 30)
    teen16 = gov(db, owner, rating=CR.TEEN_16_PLUS)
    pub = gov(db, owner, rating=CR.GENERAL)
    rows = [{"position": 1, "points": 5, "contestant_id": teen16.id, "contestant_title": SECRET_TITLE,
             "contestant_description": SECRET_DESC, "votes_count": 9},
            {"position": 2, "points": 4, "contestant_id": pub.id, "contestant_title": "Public", "votes_count": 3}]
    out = va.secure_entry_refs(db, va.viewer_for(db, person(db, 14)), rows)
    assert [r["position"] for r in out] == [1, 2] and [r["votes_count"] for r in out] == [9, 3]
    assert out[0]["content_restricted"] is True and out[0]["contestant_title"] is None
    assert out[0]["contestant_description"] is None
    assert "content_restricted" not in out[1] and out[1]["contestant_title"] == "Public"


def test_top_high5_is_secured_per_viewer_without_changing_ranking(db):
    from app.api.api_v1.endpoints.season_migration import secure_top_high5_payload

    kid = person(db, 14, full_name="Kid Star")
    grown = person(db, 30, full_name="Grown Star")
    k = gov(db, kid, rating=CR.GENERAL, title="Kid entry")
    g = gov(db, grown, rating=CR.TEEN_16_PLUS, title="Teen16 entry")
    shared = {"contests": [{"contest_id": 1, "rows": [
        {"rank": 1, "contestant_id": g.id, "contestant_title": "Teen16 entry", "author_name": "Grown Star",
         "city": "Arusha", "stars_points": 50, "votes_count": 10},
        {"rank": 2, "contestant_id": k.id, "contestant_title": "Kid entry", "author_name": "Kid Star",
         "city": "Moshi", "stars_points": 40, "votes_count": 8}]}]}
    snapshot = json.dumps(shared, sort_keys=True)
    out = secure_top_high5_payload(db, person(db, 14), shared)
    assert json.dumps(shared, sort_keys=True) == snapshot                 # shared singleflight result untouched
    rows = out["contests"][0]["rows"]
    assert [(r["rank"], r["contestant_id"], r["stars_points"]) for r in rows] == [(1, g.id, 50), (2, k.id, 40)]
    assert rows[0]["content_restricted"] is True and rows[0]["contestant_title"] is None
    assert rows[1]["contestant_title"] == "Kid entry"
    assert rows[1]["author_name"] == kid.username and rows[1]["city"] is None
    adult_rows = secure_top_high5_payload(db, person(db, 30), shared)["contests"][0]["rows"]
    assert adult_rows[0]["contestant_title"] == "Teen16 entry" and adult_rows[0]["author_name"] == "Grown Star"


def test_favorites_list_withholds_entries_no_longer_deliverable(client, db):
    owner = person(db, 30)
    t13 = person(db, 14)
    pub = gov(db, owner, rating=CR.GENERAL)
    later = gov(db, owner, rating=CR.GENERAL)
    for e in (pub, later):
        db.add(MyFavorites(user_id=t13.id, contestant_id=e.id))
    db.commit()
    db.query(ContentModeration).filter(ContentModeration.contestant_id == later.id).update(
        {"rating": CR.TEEN_16_PLUS.value})
    db.commit()
    rows = {r["id"]: r for r in client.get("/api/v1/favorites/contestants", headers=auth(t13)).json()}
    assert rows[pub.id]["title"] == SECRET_TITLE
    assert rows[later.id]["content_restricted"] is True and rows[later.id]["title"] is None


# ===========================================================================
# SHARE PREVIEWS / SSR METADATA / CACHE
# ===========================================================================

def test_share_previews_use_the_anonymous_policy(client, db, media_root):
    kid = person(db, 14, full_name="Kid Realname")
    grown = person(db, 30)
    teen = gov(db, grown, rating=CR.TEEN_13_PLUS)
    held = gov(db, grown, exposure="HELD", state="PENDING")
    for e in (teen, held):
        body = client.get(f"/api/v1/share/preview/contestant/{e.id}").json()
        assert SECRET_TITLE not in json.dumps(body) and body["title"] == "Entry on MyHigh5"
        page = client.get(f"/api/v1/share/contestant/{e.id}").text
        assert SECRET_TITLE not in page and SECRET_DESC not in page
    k = gov(db, kid, rating=CR.GENERAL, title="Kid entry")
    body = client.get(f"/api/v1/share/preview/contestant/{k.id}").json()
    assert "Kid Realname" not in json.dumps(body) and kid.username in body["title"]
    assert "Kid Realname" not in client.get(f"/api/v1/share/profile/{kid.username}").text

    # A public entry whose image is also used by a restricted entry never exposes it as og:image.
    name, url = stored_file(media_root, grown)
    public_e = gov(db, grown, rating=CR.GENERAL, images=[url])
    gov(db, grown, exposure="HELD", state="PENDING", images=[url])
    assert name not in client.get(f"/api/v1/share/preview/contestant/{public_e.id}").json()["image_url"]


def test_share_username_link_skips_non_public_entries(client, db):
    kid = person(db, 14)
    gov(db, kid, exposure="HELD", state="PENDING")
    r = client.get(f"/api/v1/share/u/{kid.username}", follow_redirects=False)
    assert r.status_code == 404


def test_viewer_dependent_responses_are_not_shared_cacheable(client, db):
    target = person(db, 30)
    for path in (f"/api/v1/users/{target.id}", "/api/v1/contestants/user/my-entries", "/api/v1/favorites/contestants"):
        r = client.get(path, headers=auth(target))
        assert r.headers.get("cache-control") == "private, no-store", path
        assert "Authorization" in r.headers.get("vary", ""), path


# ===========================================================================
# CONTEST ROSTERS (both listing endpoints)
# ===========================================================================

def test_contest_rosters_are_filtered_per_viewer(client, db):
    from datetime import timedelta

    from app.models.round import Round
    from tests.unit.test_phase5_contest_eligibility import TODAY

    ct = contest(db)
    month = TODAY.replace(day=1)
    rnd = Round(name=f"R {uuid.uuid4().hex[:4]}", contest_id=ct.id, submission_start_date=month,
                submission_end_date=month + timedelta(days=40))
    db.add(rnd)
    db.commit()
    held_owner = person(db, 30)
    made = {}
    for key, owner, kw in (("general", person(db, 30), dict(rating=CR.GENERAL)),
                           ("teen16", person(db, 30), dict(rating=CR.TEEN_16_PLUS)),
                           ("held", held_owner, dict(exposure="HELD", state="PENDING"))):
        e = gov(db, owner, **kw)
        row = db.get(Contestant, e.id)
        row.season_id, row.contest_id, row.round_id = ct.id, ct.id, rnd.id
        made[key] = e.id
    db.commit()

    def roster(user):
        a = client.get(f"/api/v1/contests/{ct.id}", headers=hdr(user))
        b = client.get(f"/api/v1/contestants/contest/{ct.id}", headers=hdr(user))
        assert a.status_code == 200 and b.status_code == 200
        return a.json(), {x["id"] for x in a.json()["contestants"]}, {x["id"] for x in b.json()}

    _, detail, listing = roster(person(db, 30))
    assert detail == listing == {made["general"], made["teen16"]}
    _, detail, listing = roster(person(db, 14))
    assert detail == listing == {made["general"]}
    _, detail, listing = roster(None)
    assert detail == listing == {made["general"]}
    _, detail, listing = roster(held_owner)
    assert made["held"] not in detail | listing                         # never in the PUBLIC roster, even for its owner
