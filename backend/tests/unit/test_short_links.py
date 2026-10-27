"""Member short links (/s/{code}) with an optional personal invitation.

Creation, destination rules, unwrapping of pasted short links, public resolution (neutral,
invitation, crawler, disabled, unknown), ownership, and attribution through the real registration
endpoint under the existing sponsor rule. Everything is SYNTHETIC (in-memory database).
"""
from __future__ import annotations

from datetime import datetime
from urllib.parse import parse_qs, urlparse

import pytest

from app.core.config import settings
from app.models.affiliate import AffiliateCommission
from app.models.referral_share import ReferralShareClick, ReferralShareConversion, ReferralShareLink
from app.models.user import User
from app.services import referral_shortener as shortener
from tests.unit.test_email2_auth_security import (  # noqa: F401  (ip is a fixture)
    A, PW, bearer, body, ip, login, member,
)

pytestmark = pytest.mark.unit

LINKS = "/api/v1/share-links"
COOKIE = settings.ATTRIBUTION_COOKIE_NAME
SITE = "https://myhigh5.com"


@pytest.fixture(autouse=True)
def production_origin(monkeypatch, db):
    """Production origin and the production sponsor rule (NEW_V2 in force)."""
    from datetime import timedelta

    from app.core import rate_limit as rl
    from app.models.business_model import BusinessModelVersion
    from app.services.new_model_reference_data import seed_new_model_reference_data

    seed_new_model_reference_data(db)
    db.query(BusinessModelVersion).update({BusinessModelVersion.effective_at: datetime.utcnow() - timedelta(days=1)})
    db.commit()
    monkeypatch.setattr(settings, "FRONTEND_URL", SITE)
    monkeypatch.setattr(settings, "SHORT_LINK_ORIGIN", "")
    monkeypatch.setattr(settings, "SHORT_LINK_ALLOWED_HOSTS", "")
    rl._buckets.clear()
    yield
    rl._buckets.clear()


def signed_in(client, db, **extra):
    user = member(db, verified=True, **extra)
    if not user.personal_referral_code:
        user.personal_referral_code = f"INV{user.id:05d}"
        db.commit()
    token = login(client, user).json()["access_token"]
    return user, bearer(token)


def kyc_approved(db, user):
    from app.models.kyc import KYCStatus, KYCVerification, VerificationProvider

    db.add(KYCVerification(user_id=user.id, status=KYCStatus.APPROVED, provider=VerificationProvider.KALUTA,
                           reference_id=f"kyc-test-{user.id}", attempts_count=1, submitted_at=datetime.utcnow(),
                           processed_at=datetime.utcnow(), identity_verified=True, address_verified=True))
    user.identity_verified = user.address_verified = True
    db.commit()
    return user


def attribution_of(response):
    """The attribution cookie a redirect set (read from Set-Cookie: its domain is .myhigh5.com)."""
    from http.cookies import SimpleCookie

    for header in response.headers.get_list("set-cookie"):
        jar = SimpleCookie()
        jar.load(header)
        if COOKIE in jar:
            return jar[COOKIE].value
    return None


def shorten(client, headers, url, invitation=False):
    return client.post(LINKS, headers=headers, json={"url": url, "include_invitation": invitation})


def open_link(client, short_url, **kw):
    code = short_url.rsplit("/", 1)[1]
    return client.get(f"/api/v1/l/{code}", follow_redirects=False, **kw)


# ============================================================================ creation

def test_neutral_link_is_created_on_the_canonical_domain_without_attribution(client, db, ip):
    user, headers = signed_in(client, db)
    r = shorten(client, headers, "https://www.myhigh5.com/feed/12?sort=new&ref=SOMEONE&utm_source=x#comments")
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["short_url"].startswith(f"{SITE}/s/") and len(data["short_code"]) == 7
    assert data["include_invitation"] is False and data["is_active"] is True and data["reused"] is False
    assert data["destination_url"] == f"{SITE}/feed/12?sort=new#comments"     # query + fragment kept, ref dropped
    assert user.personal_referral_code not in data["short_code"] and "feed" not in data["short_code"]
    row = db.query(ReferralShareLink).one()
    assert (row.user_id, row.invitation_enabled) == (user.id, False)


def test_invitation_link_is_separate_from_the_neutral_one_and_reused_when_repeated(client, db, ip):
    _, headers = signed_in(client, db)
    neutral = shorten(client, headers, f"{SITE}/contests").json()
    invite = shorten(client, headers, f"{SITE}/contests", invitation=True).json()
    again = shorten(client, headers, f"{SITE}/contests?ref=X", invitation=True).json()
    assert invite["include_invitation"] is True and neutral["short_code"] != invite["short_code"]
    assert again["short_code"] == invite["short_code"] and again["reused"] is True
    assert db.query(ReferralShareLink).count() == 2


def test_body_cannot_name_another_owner_or_code(client, db, ip):
    other, _ = signed_in(client, db)
    user, headers = signed_in(client, db)
    r = client.post(LINKS, headers=headers, json={"url": f"{SITE}/faq", "include_invitation": True,
                                                  "user_id": other.id, "referral_code": other.personal_referral_code})
    assert r.status_code == 201
    assert db.query(ReferralShareLink).one().user_id == user.id


def test_invitation_needs_an_invitation_code(client, db, ip):
    user, headers = signed_in(client, db)
    user.personal_referral_code = None
    db.commit()
    assert shorten(client, headers, f"{SITE}/faq", invitation=True).status_code == 400
    assert shorten(client, headers, f"{SITE}/faq").status_code == 201


def test_creation_and_management_need_a_session(client, db, ip):
    assert client.post(LINKS, json={"url": f"{SITE}/faq"}).status_code == 401
    assert client.get(LINKS).status_code == 401
    assert client.post(f"{LINKS}/1/disable").status_code == 401


def test_a_code_collision_is_retried_and_exhaustion_fails_cleanly(db, ip):
    owner = member(db)
    owner.personal_referral_code = "INVCOLL1"
    db.commit()
    first, _ = shortener.create_short_link(db, owner, f"{SITE}/faq", include_invitation=False,
                                           code_factory=lambda: "AAAAAAA")
    codes = iter(["AAAAAAA", "AAAAAAA", "BBBBBBB"])
    second, _ = shortener.create_short_link(db, owner, f"{SITE}/terms", include_invitation=False,
                                            code_factory=lambda: next(codes))
    assert (first.short_code, second.short_code) == ("AAAAAAA", "BBBBBBB")
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        shortener.create_short_link(db, owner, f"{SITE}/privacy", include_invitation=False,
                                    code_factory=lambda: "AAAAAAA")
    assert exc.value.status_code == 503


def test_codes_come_from_the_secure_generator():
    codes = {shortener._random_base62() for _ in range(2000)}
    assert len(codes) == 2000 and all(len(c) == 7 and c.isalnum() for c in codes)


# ============================================================================ destination rules

@pytest.mark.parametrize("url,expected", [
    (f"{SITE}/", f"{SITE}/"),
    (f"{SITE}/feed/12?x=1#c", f"{SITE}/feed/12?x=1#c"),
    (f"{SITE}/contests/3/entry/9?roundId=2&ref=ABC", f"{SITE}/contests/3/entry/9?roundId=2"),
    (f"{SITE}/dashboard/feed/5", f"{SITE}/feed/5"),
    (f"{SITE}/dashboard/contests/4/contestant/8", f"{SITE}/contests/4/entry/8"),
    (f"{SITE}/profile/jane_doe", f"{SITE}/profile/jane_doe"),
    (f"{SITE}/janedoe", f"{SITE}/janedoe"),
    ("https://WWW.MyHigh5.com:443/faq/", f"{SITE}/faq"),
    ("http://myhigh5.com/register?ref=ABC", f"{SITE}/register"),
    (f"{SITE}/r/SOMEONE", f"{SITE}/"),
    (f"{SITE}/register/SOMEONE", f"{SITE}/register"),
    (f"{SITE}/dashboard/groups/7", f"{SITE}/dashboard/groups/7"),
])
def test_supported_pages(url, expected):
    assert shortener.validate_and_normalize_internal_url(url)[0] == expected


@pytest.mark.parametrize("url", [
    "https://evil.com/feed/1",
    "https://myhigh5.com.evil.com/feed/1",
    "https://evilmyhigh5.com/",
    "https://myhigh5.co/",
    "https://user:pass@myhigh5.com/feed/1",
    "https://myhigh5.com@evil.com/",
    "javascript:alert(1)",
    "ftp://myhigh5.com/feed/1",
    "data:text/html,hi",
    "//evil.com/x",
    "not a url",
    "https://myhigh5.com:8443/feed/1",
    "https://localhost/feed/1",
    f"{SITE}/login",
    f"{SITE}/logout",
    f"{SITE}/reset-password#token=abc",
    f"{SITE}/forgot-password",
    f"{SITE}/verify-email",
    f"{SITE}/guardian/consent#token=abc",
    f"{SITE}/register/complete",
    f"{SITE}/payout-wallet/confirm",
    f"{SITE}/dashboard/admin/users",
    f"{SITE}/dashboard/wallet",
    f"{SITE}/dashboard/kyc",
    f"{SITE}/dashboard/settings",
    f"{SITE}/api/v1/users/me",
    f"{SITE}/clear-cache",
    f"{SITE}/feed/1?token=abc",
    f"{SITE}/feed/1?access_token=abc",
    f"{SITE}/feed/1?code=abc&state=x",
    f"{SITE}/feed/1#access_token=abc",
    f"{SITE}//evil.com",
    f"{SITE}/feed/%2e%2e/dashboard/admin",
    f"{SITE}/feed%2f1",
])
def test_refused_destinations(url):
    with pytest.raises(shortener.ShortLinkError):
        shortener.validate_and_normalize_internal_url(url)


def test_refusals_answer_400_with_a_readable_message(client, db, ip):
    _, headers = signed_in(client, db)
    r = shorten(client, headers, "https://evil.com/")
    assert r.status_code == 400 and "MyHigh5" in r.json()["detail"]
    assert db.query(ReferralShareLink).count() == 0


# ============================================================================ pasted short links

def test_a_pasted_short_link_is_unwrapped_and_never_inherits_the_invitation(client, db, ip):
    alice, alice_h = signed_in(client, db)
    inner = shorten(client, alice_h, f"{SITE}/feed/12?sort=new", invitation=True).json()
    bob, bob_h = signed_in(client, db)
    outer = shorten(client, bob_h, inner["short_url"]).json()
    assert outer["destination_url"] == f"{SITE}/feed/12?sort=new"          # the page, not /s/<code>
    assert outer["include_invitation"] is False
    row = db.query(ReferralShareLink).filter(ReferralShareLink.short_code == outer["short_code"]).one()
    assert row.user_id == bob.id and "/s/" not in row.destination_url
    r = open_link(client, outer["short_url"])
    assert r.status_code == 302 and "ref=" not in r.headers["location"] and COOKIE not in r.headers.get("set-cookie", "")
    # the legacy /l/ form is unwrapped too
    legacy = shorten(client, bob_h, f"{SITE}/l/{inner['short_code']}", invitation=True).json()
    assert legacy["destination_url"] == f"{SITE}/feed/12?sort=new"


def test_a_disabled_or_unknown_short_link_cannot_be_shortened_again(client, db, ip):
    _, headers = signed_in(client, db)
    inner = shorten(client, headers, f"{SITE}/faq").json()
    client.post(f"{LINKS}/{inner['id']}/disable", headers=headers)
    assert shorten(client, headers, inner["short_url"]).status_code == 400
    assert shorten(client, headers, f"{SITE}/s/Zz9Zz9Z").status_code == 400


def test_a_stored_short_link_destination_never_resolves_into_a_chain(client, db, ip):
    user, _ = signed_in(client, db)
    db.add(ReferralShareLink(user_id=user.id, short_code="Loop001", destination_url=f"{SITE}/s/Loop001",
                             normalized_url=f"{SITE}/s/Loop001", invitation_enabled=False))
    db.commit()
    r = client.get("/api/v1/l/Loop001", follow_redirects=False)
    assert r.status_code == 404 and r.json()["code"] == "SHORT_LINK_UNAVAILABLE"


# ============================================================================ resolution

def test_a_neutral_link_redirects_without_setting_or_clearing_anything(client, db, ip):
    _, headers = signed_in(client, db)
    link = shorten(client, headers, f"{SITE}/feed/12#top").json()
    client.cookies.set(COOKIE, "visitor-existing-attribution")
    r = open_link(client, link["short_url"])
    assert r.status_code == 302 and r.headers["location"] == f"{SITE}/feed/12#top"
    assert "no-store" in r.headers["cache-control"]
    assert "set-cookie" not in r.headers                                    # existing attribution untouched
    assert db.query(ReferralShareClick).count() == 0                         # nothing stored about the visitor


def test_an_invitation_link_sets_the_signed_attribution_and_ref(client, db, ip):
    user, headers = signed_in(client, db)
    link = shorten(client, headers, f"{SITE}/feed/12?sort=new", invitation=True).json()
    r = open_link(client, link["short_url"])
    assert r.status_code == 302
    target = urlparse(r.headers["location"])
    assert (target.netloc, target.path) == ("myhigh5.com", "/feed/12")
    assert parse_qs(target.query) == {"sort": ["new"], "ref": [user.personal_referral_code]}
    assert "no-store" in r.headers["cache-control"] and f"{COOKIE}=" in r.headers["set-cookie"]
    assert "httponly" in r.headers["set-cookie"].lower()
    assert db.query(ReferralShareClick).count() == 1


def test_a_crawler_gets_the_preview_route_and_no_attribution(client, db, ip):
    _, headers = signed_in(client, db)
    post = shorten(client, headers, f"{SITE}/feed/12", invitation=True).json()
    entry = shorten(client, headers, f"{SITE}/contests/3/entry/9?roundId=2", invitation=True).json()
    page = shorten(client, headers, f"{SITE}/faq", invitation=True).json()
    ua = {"user-agent": "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)"}
    expected = {post["short_url"]: f"{SITE}/s/f/12", entry["short_url"]: f"{SITE}/s/c/9",
                page["short_url"]: f"{SITE}/faq"}
    for short_url, target in expected.items():
        r = open_link(client, short_url, headers=ua)
        assert r.status_code == 302 and r.headers["location"] == target
        assert "set-cookie" not in r.headers
    assert db.query(ReferralShareClick).count() == 0


@pytest.mark.parametrize("code", ["Zz9Zz9Z", "bad-code", "x" * 40])
def test_unknown_codes_are_reported_unavailable(client, db, ip, code):
    r = client.get(f"/api/v1/l/{code}", follow_redirects=False)
    assert r.status_code == 404 and r.json()["code"] == "SHORT_LINK_UNAVAILABLE"
    assert "no-store" in r.headers["cache-control"]


def test_a_link_stops_resolving_when_disabled_or_its_creator_is_deactivated(client, db, ip):
    user, headers = signed_in(client, db)
    a = shorten(client, headers, f"{SITE}/faq").json()
    b = shorten(client, headers, f"{SITE}/terms").json()
    assert client.post(f"{LINKS}/{a['id']}/disable", headers=headers).json()["is_active"] is False
    assert open_link(client, a["short_url"]).status_code == 404
    assert open_link(client, b["short_url"]).status_code == 302
    user.is_active = False
    db.commit()
    assert open_link(client, b["short_url"]).status_code == 404


def test_a_short_link_grants_no_access_to_member_pages(client, db, ip):
    _, headers = signed_in(client, db)
    link = shorten(client, headers, f"{SITE}/dashboard/groups/7").json()
    client.headers.pop("authorization", None)
    r = open_link(client, link["short_url"])
    # a plain redirect: the destination page applies its own sign-in / membership rules
    assert r.status_code == 302 and r.headers["location"] == f"{SITE}/dashboard/groups/7"
    assert "set-cookie" not in r.headers


# ============================================================================ management

def test_members_see_and_disable_only_their_own_links(client, db, ip):
    alice, alice_h = signed_in(client, db)
    mine = shorten(client, alice_h, f"{SITE}/faq", invitation=True).json()
    _, bob_h = signed_in(client, db)
    theirs = shorten(client, bob_h, f"{SITE}/terms").json()

    listing = client.get(LINKS, headers=alice_h).json()
    assert listing["total"] == 1 and [i["short_code"] for i in listing["items"]] == [mine["short_code"]]
    assert listing["items"][0]["include_invitation"] is True and listing["items"][0]["created_at"]

    assert client.post(f"{LINKS}/{theirs['id']}/disable", headers=alice_h).status_code == 404
    assert open_link(client, theirs["short_url"]).status_code == 302          # untouched
    again = client.post(f"{LINKS}/{mine['id']}/disable", headers=alice_h)
    assert again.status_code == 200 and client.post(f"{LINKS}/{mine['id']}/disable", headers=alice_h).status_code == 200
    # a new link for the same page can be created after disabling; the old one stays dead
    fresh = shorten(client, alice_h, f"{SITE}/faq", invitation=True).json()
    assert fresh["short_code"] != mine["short_code"] and fresh["reused"] is False
    assert open_link(client, mine["short_url"]).status_code == 404


def test_there_is_no_way_to_edit_a_link(client, db, ip):
    _, headers = signed_in(client, db)
    link = shorten(client, headers, f"{SITE}/faq").json()
    for method in ("put", "patch"):
        r = getattr(client, method)(f"{LINKS}/{link['id']}", headers=headers,
                                    json={"url": f"{SITE}/terms", "include_invitation": True})
        assert r.status_code in (404, 405)
    row = db.query(ReferralShareLink).one()
    assert (row.destination_url, row.invitation_enabled) == (f"{SITE}/faq", False)


# ============================================================================ attribution at registration

def register_after_visit(client, visit_response=None, *, sponsor_code=None, **over):
    """A visitor who opened a link and then registers. The attribution cookie travels as the browser
    would send it; the page's ?ref= is what the register page passes as sponsor_code."""
    client.cookies.clear()
    client.headers.pop("authorization", None)
    if visit_response is not None:
        token = attribution_of(visit_response)
        if token:
            client.cookies.set(COOKIE, token)
    url = f"{A}/register" + (f"?sponsor_code={sponsor_code}" if sponsor_code else "")
    data = body(**over)
    assert client.post(url, json=data).status_code == 201
    return data


def new_user(db, data):
    return db.query(User).filter(User.email == data["email"]).one()


def test_an_invitation_link_sponsors_an_eligible_new_member(client, db, ip):
    inviter, headers = signed_in(client, db)
    kyc_approved(db, inviter)
    link = shorten(client, headers, f"{SITE}/register", invitation=True).json()

    by_cookie = new_user(db, register_after_visit(client, open_link(client, link["short_url"])))
    assert (by_cookie.sponsor_id, by_cookie.sponsor_source) == (inviter.id, "PERSONAL_REFERRAL")

    visit = open_link(client, link["short_url"])
    ref = parse_qs(urlparse(visit.headers["location"]).query)["ref"][0]
    by_ref = new_user(db, register_after_visit(client, None, sponsor_code=ref))
    assert (by_ref.sponsor_id, by_ref.sponsor_source) == (inviter.id, "PERSONAL_REFERRAL")

    assert db.query(ReferralShareConversion).filter_by(converted_user_id=by_cookie.id).count() == 1
    assert db.query(AffiliateCommission).count() == 0                      # registration pays nothing


def test_a_neutral_link_creates_no_attribution(client, db, ip):
    creator, headers = signed_in(client, db)
    kyc_approved(db, creator)
    link = shorten(client, headers, f"{SITE}/register").json()
    joined = new_user(db, register_after_visit(client, open_link(client, link["short_url"])))
    assert joined.sponsor_id is None and joined.sponsor_source == "NONE"   # organic: the pool decides later
    assert db.query(ReferralShareConversion).count() == 0


def test_a_neutral_link_keeps_an_earlier_valid_invitation(client, db, ip):
    first, first_h = signed_in(client, db)
    kyc_approved(db, first)
    invite = shorten(client, first_h, f"{SITE}/register", invitation=True).json()
    other, other_h = signed_in(client, db)
    kyc_approved(db, other)
    neutral = shorten(client, other_h, f"{SITE}/feed/3").json()

    earlier = open_link(client, invite["short_url"])
    client.cookies.set(COOKIE, attribution_of(earlier))
    later = client.get(f"/api/v1/l/{neutral['short_code']}", follow_redirects=False)
    assert "set-cookie" not in later.headers
    joined = new_user(db, register_after_visit(client, earlier))
    assert joined.sponsor_id == first.id


def test_an_ineligible_inviter_creates_no_sponsor(client, db, ip):
    _, headers = signed_in(client, db)                                     # not KYC-approved
    link = shorten(client, headers, f"{SITE}/register", invitation=True).json()
    joined = new_user(db, register_after_visit(client, open_link(client, link["short_url"])))
    assert joined.sponsor_id is None and joined.sponsor_source == "NONE"


@pytest.mark.parametrize("source", ["PERSONAL_REFERRAL", "DSM_IMPORT"])
def test_an_existing_sponsor_is_never_replaced(client, db, ip, source):
    original = member(db, verified=True)
    existing = member(db, verified=True)
    existing.sponsor_id, existing.sponsor_source = original.id, source
    db.commit()
    inviter, headers = signed_in(client, db)
    kyc_approved(db, inviter)
    link = shorten(client, headers, f"{SITE}/register", invitation=True).json()

    register_after_visit(client, open_link(client, link["short_url"]), email=existing.email)
    db.refresh(existing)
    assert (existing.sponsor_id, existing.sponsor_source) == (original.id, source)
    assert db.query(User).filter(User.email == existing.email).count() == 1
    assert db.query(ReferralShareConversion).count() == 0


def test_no_self_referral_and_one_signup_conversion(client, db, ip):
    inviter, headers = signed_in(client, db)
    link = shorten(client, headers, f"{SITE}/register", invitation=True).json()
    row = db.query(ReferralShareLink).one()
    attribution = {"referrerMemberId": str(inviter.id), "shareLinkId": str(row.id)}
    assert shortener.record_conversion(db, converted_user_id=inviter.id, conversion_type="signup",
                                       attribution=attribution) is False
    from starlette.requests import Request

    token = attribution_of(open_link(client, link["short_url"]))
    req = Request({"type": "http", "headers": [(b"cookie", f"{COOKIE}={token}".encode())]})
    newcomer = member(db)
    assert shortener.record_signup_conversion_from_request(req, db, newcomer.id) is True
    assert shortener.record_signup_conversion_from_request(req, db, newcomer.id) is False
    assert db.query(ReferralShareConversion).count() == 1


def test_a_cookie_from_a_link_that_is_not_an_invitation_is_ignored(db):
    from starlette.requests import Request

    owner = member(db)
    owner.personal_referral_code = "INVNEUT1"
    link = ReferralShareLink(user_id=owner.id, short_code="Neut001", destination_url=f"{SITE}/faq",
                             normalized_url=f"{SITE}/faq", invitation_enabled=False)
    db.add(link)
    db.commit()
    forged = shortener.sign_attribution(referrer_user_id=owner.id, share_link_id=link.id, short_code="Neut001")
    req = Request({"type": "http", "headers": [(b"cookie", f"{COOKIE}={forged}".encode())]})
    assert shortener.get_sponsor_referral_code_from_request(req, db) is None


# ============================================================================ invitation eligibility (KYC)

STATUS = f"{LINKS}/invitation-status"


def kyc_row(db, user, status):
    from app.models.kyc import KYCVerification, VerificationProvider

    db.add(KYCVerification(user_id=user.id, status=status, provider=VerificationProvider.KALUTA,
                           reference_id=f"kyc-test-{user.id}", attempts_count=1, submitted_at=datetime.utcnow()))
    db.commit()


def test_invitation_status_follows_the_registration_inviter_rule(client, db, ip, monkeypatch):
    from app.models.kyc import KYCStatus

    user, headers = signed_in(client, db)
    r = client.get(STATUS, headers=headers).json()
    assert r["eligible"] is False and r["reason"] == "KYC_NOT_STARTED" and "KYC" in r["message"]

    kyc_row(db, user, KYCStatus.PENDING_PROOF_OF_ADDRESS)
    assert client.get(STATUS, headers=headers).json()["reason"] == "KYC_IN_PROGRESS"

    from app.models.kyc import KYCVerification
    db.query(KYCVerification).filter_by(user_id=user.id).update({KYCVerification.status: KYCStatus.REJECTED})
    db.commit()
    assert client.get(STATUS, headers=headers).json()["reason"] == "KYC_REJECTED"

    db.query(KYCVerification).filter_by(user_id=user.id).delete()
    db.commit()
    kyc_approved(db, user)
    assert client.get(STATUS, headers=headers).json() == {"eligible": True, "reason": None, "message": None}

    import app.services.referral_pool_risk as risk
    monkeypatch.setattr(risk, "is_blocked", lambda _db, _uid: True)
    blocked = client.get(STATUS, headers=headers).json()
    assert blocked["reason"] == "RESTRICTED" and "review" not in blocked["message"].lower()   # no detail leaked


def test_invitation_status_without_a_code_and_without_a_session(client, db, ip):
    user, headers = signed_in(client, db)
    user.personal_referral_code = None
    db.commit()
    assert client.get(STATUS, headers=headers).json()["reason"] == "NO_CODE"
    client.headers.pop("authorization", None)
    assert client.get(STATUS).status_code == 401


def test_an_ineligible_member_still_creates_neutral_and_invitation_links(client, db, ip):
    _, headers = signed_in(client, db)                                     # no KYC
    assert client.get(STATUS, headers=headers).json()["eligible"] is False
    assert shorten(client, headers, f"{SITE}/faq").status_code == 201
    assert shorten(client, headers, f"{SITE}/faq", invitation=True).status_code == 201


# ============================================================================ roles, money, pool

def test_a_super_admin_uses_the_member_tool_like_anyone_else(client, db, ip):
    from tests.unit.test_super_admin import super_role

    admin, headers = signed_in(client, db)
    admin.is_admin, admin.role_id = True, super_role(db).id
    db.commit()
    from app.services.super_admin import is_super_admin
    assert is_super_admin(admin)
    link = shorten(client, headers, f"{SITE}/feed/3", invitation=True)
    assert link.status_code == 201
    assert client.get(LINKS, headers=headers).json()["total"] == 1
    assert client.get(STATUS, headers=headers).status_code == 200
    assert client.post(f"{LINKS}/{link.json()['id']}/disable", headers=headers).status_code == 200


def test_links_and_visits_touch_no_money_and_no_pool_state(client, db, ip):
    from app.models.accounting import JournalEntry
    from app.models.payment import Deposit

    from sqlalchemy import inspect, text

    tables = ("referral_pool_units", "referral_pool_purchases", "referral_pool_assignments", "referral_pool_config")
    present = [t for t in tables if inspect(db.get_bind()).has_table(t)]

    def snapshot():
        return {t: [tuple(r) for r in db.execute(text(f"select * from {t} order by 1"))] for t in present}

    before = snapshot()
    inviter, headers = signed_in(client, db)
    kyc_approved(db, inviter)
    link = shorten(client, headers, f"{SITE}/register", invitation=True).json()
    register_after_visit(client, open_link(client, link["short_url"]))
    assert snapshot() == before                                            # pool switches, limits, units untouched
    assert db.query(AffiliateCommission).count() == 0
    assert db.query(JournalEntry).count() == 0 and db.query(Deposit).count() == 0
