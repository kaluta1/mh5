"""
Phase 1.5 critical privacy/security hotfixes:

1. GET /users/by-username/{username} must not leak the private User schema.
2. TopHigh5 payloads (served anonymously) must never contain an email.
3. KYC documents must never be retrievable through public media delivery;
   only an admin holding a short-lived signed view token can read them.

All data is synthetic; files live under pytest's tmp_path.
"""
from __future__ import annotations

import asyncio
import json
from datetime import date, datetime, timedelta
from io import BytesIO
from types import SimpleNamespace
from urllib.parse import urlparse

import pytest
from fastapi import UploadFile
from starlette.applications import Starlette
from starlette.datastructures import Headers
from starlette.routing import Mount
from starlette.testclient import TestClient as StarletteTestClient

from app.core import security, storage
from app.core.security import create_access_token, create_kyc_document_view_token
from app.models.contests import SeasonLevel
from app.models.kyc import DocumentType, KYCDocument, KYCStatus, KYCVerification
from app.models.user import User
from app.services.top_high5_live import _row_dict, public_author_name, resolve_live_top_high5
from app.api.api_v1.endpoints.season_migration import _top_high5_row_dict
from tests.unit.test_top_high5_derived import (
    _contest,
    _contestant,
    _member,
    _month_start,
    _round_for_month,
    _season,
    _vote,
)

# High ids so fixture files can never collide with real local media folders.
OWNER_ID_BASE = 987_000

PRIVATE_USER_FIELDS = (
    "email",
    "phone_number",
    "date_of_birth",
    "usdt_wallet_address",
    "payout_currency",
    "sponsor_id",
    "personal_referral_code",
    "is_admin",
    "role",
    "role_id",
    "affiliate_agreement_accepted",
    "affiliate_agreement_accepted_at",
)


def _user(db, suffix: str, **kwargs) -> User:
    user = User(
        email=f"p15-{suffix}@example.com",
        hashed_password="unused",
        is_active=True,
        **kwargs,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _neutral_404(response, path: str) -> str:
    """The global 404 handler echoes the requested path; strip it before comparing bodies."""
    return response.text.replace(path, "<path>")


def _bearer(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(subject=user.id)}"}


# ===========================================================================
# HOTFIX 1: username lookup
# ===========================================================================

def test_username_lookup_of_other_user_returns_public_profile_only(client, db):
    viewer = _user(db, "viewer", username="p15viewer")
    target = _user(
        db,
        "target",
        username="p15target",
        full_name="Target Person",
        phone_number="+10000000000",
        date_of_birth=datetime(2000, 1, 2),
        personal_referral_code="P15REFCODE",
        country="Testland",
        city="Testcity",
    )

    response = client.get("/api/v1/users/by-username/p15target", headers=_bearer(viewer))

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == target.id  # the only field the mention redirect needs
    assert body["username"] == "p15target"
    assert body["full_name"] == "Target Person"
    for field in PRIVATE_USER_FIELDS:
        assert field not in body, field
    raw = response.text
    assert target.email not in raw
    assert "+10000000000" not in raw
    assert "2000-01-02" not in raw
    assert "P15REFCODE" not in raw


def test_username_lookup_is_case_insensitive_and_still_scrubbed(client, db):
    viewer = _user(db, "viewer2", username="p15viewer2")
    target = _user(db, "target2", username="P15Mixed")
    response = client.get("/api/v1/users/by-username/p15mixed", headers=_bearer(viewer))
    assert response.status_code == 200
    assert response.json()["id"] == target.id
    assert "email" not in response.json()


def test_username_lookup_self_and_admin_still_get_full_profile(client, db):
    owner = _user(db, "self", username="p15self", phone_number="+19999999999")
    admin = _user(db, "admin", username="p15admin", is_admin=True)

    own = client.get("/api/v1/users/by-username/p15self", headers=_bearer(owner))
    assert own.status_code == 200
    assert own.json()["email"] == owner.email

    as_admin = client.get("/api/v1/users/by-username/p15self", headers=_bearer(admin))
    assert as_admin.status_code == 200
    assert as_admin.json()["phone_number"] == "+19999999999"


def test_username_lookup_unknown_is_404_and_requires_auth(client, db):
    viewer = _user(db, "viewer3", username="p15viewer3")
    assert client.get("/api/v1/users/by-username/p15-nobody", headers=_bearer(viewer)).status_code == 404
    assert client.get("/api/v1/users/by-username/p15viewer3").status_code == 401


# ===========================================================================
# HOTFIX 2: TopHigh5 serialization
# ===========================================================================

def _fake_user(**kwargs):
    base = {"full_name": None, "username": None, "email": "secret-p15@example.test"}
    base.update(kwargs)
    return SimpleNamespace(**base)


def _fake_contestant(user):
    return SimpleNamespace(
        id=1, title="Entry", user=user, city="C", country="K", region="R",
        continent="Africa", registration_date=datetime(2026, 6, 1),
    )


def _fake_ranking():
    return SimpleNamespace(total_points=10, total_votes=2, shares=0, likes=0, comments=0, views=0)


@pytest.mark.parametrize(
    "user, expected",
    [
        (_fake_user(full_name="Full Name", username="uname"), "Full Name"),
        (_fake_user(username="uname"), "uname"),
        (_fake_user(), None),  # previously fell back to the email
        (None, None),
    ],
)
def test_public_author_name_never_uses_email(user, expected):
    assert public_author_name(user) == expected


def test_live_row_dict_has_no_email():
    row = _row_dict(None, _fake_contestant(_fake_user()), 1, _fake_ranking(), False)
    assert "author_email" not in row
    assert row["author_name"] is None
    assert "secret-p15@example.test" not in json.dumps(row, default=str)


def test_frozen_row_dict_has_no_email():
    frozen = SimpleNamespace(
        contestant=_fake_contestant(_fake_user(username="uname")), rank=1, migrated=True,
        total_points=10, total_votes=2, shares=0, likes=0, comments=0, views=0,
    )
    row = _top_high5_row_dict(frozen)
    assert "author_email" not in row
    assert row["author_name"] == "uname"
    assert "secret-p15@example.test" not in json.dumps(row, default=str)


def test_live_top_high5_ranking_unchanged_and_email_free(db):
    """Fixture owners have only an email (no name/username): the old code
    exposed it twice per row. Order/points must be exactly the vote order."""
    july = _month_start(date(2026, 7, 1))
    rnd = _round_for_month(db, "p15", submission_month_start=july)
    contest = _contest(db, "p15", mode="participation")
    season = _season(db, rnd, level=SeasonLevel.REGIONAL, suffix="p15")
    entries = []
    for idx, points in enumerate((30, 10, 20)):
        c = _contestant(db, suffix=f"p15-{idx}", rnd=rnd, contest=contest, country="Tanzania", region="East Africa")
        _member(db, contestant=c, season=season)
        _vote(db, contestant=c, contest=contest, season=season, suffix=f"p15-{idx}", points=points)
        entries.append((c, points))
    db.commit()

    result = resolve_live_top_high5(
        db, level=SeasonLevel.REGIONAL, selected_country="Tanzania",
        variants={"tanzania", "tz"}, today=date(2026, 10, 1),
    )
    rows = [r for group in result["contests"] for r in group["rows"]]
    expected_order = [c.id for c, _ in sorted(entries, key=lambda e: -e[1])]
    assert [r["contestant_id"] for r in rows] == expected_order
    assert [r["rank"] for r in rows] == [1, 2, 3]
    assert [r["stars_points"] for r in rows] == [30, 20, 10]
    for row in rows:
        assert "author_email" not in row
        assert row["author_name"] is None
    assert "@" not in json.dumps(result, default=str)


# ===========================================================================
# HOTFIX 3: KYC documents
# ===========================================================================

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32  # served from disk, never decoded
PDF_BYTES = b"%PDF-1.4 synthetic test document\n%%EOF"


@pytest.fixture
def media_env(tmp_path, monkeypatch):
    """Isolated local storage: tmp media root + tmp private KYC root, no S3."""
    media_root = tmp_path / "media"
    private_root = tmp_path / "private_kyc"
    media_root.mkdir()
    monkeypatch.setattr(storage.settings, "STORAGE_TYPE", "local")
    monkeypatch.setattr(storage.settings, "LOCAL_STORAGE_PATH", str(media_root))
    monkeypatch.setattr(storage.settings, "KYC_PRIVATE_STORAGE_PATH", str(private_root))
    monkeypatch.setattr(storage.settings, "S3_BUCKET_NAME", "")
    monkeypatch.setattr(storage.settings, "AWS_S3_BUCKET", "", raising=False)
    monkeypatch.setattr(storage, "media_storage_roots", lambda: [str(media_root)])
    return SimpleNamespace(media_root=media_root, private_root=private_root)


def _write(root, user_id: int, name: str, content: bytes):
    folder = root / str(user_id)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_bytes(content)


def test_ordinary_public_media_still_served_publicly(client, media_env):
    _write(media_env.media_root, OWNER_ID_BASE + 1, "0f0e0d0c-aaaa-bbbb-cccc-000000000001.png", PNG_BYTES)
    response = client.get(f"/api/v1/media/file/{OWNER_ID_BASE + 1}/0f0e0d0c-aaaa-bbbb-cccc-000000000001.png")
    assert response.status_code == 200
    assert response.content == PNG_BYTES
    assert response.headers["cache-control"] == "public, max-age=86400"


@pytest.mark.parametrize("name", ["kyc_poa_11111111-2222-3333-4444-555555555555.png", "KYC_POA_ABC.PNG"])
def test_legacy_kyc_file_denied_on_public_media_route(client, db, media_env, name):
    owner = OWNER_ID_BASE + 2
    _write(media_env.media_root, owner, name, PNG_BYTES)
    unrelated = _user(db, "unrelated-media", username="p15unrelated")

    anon = client.get(f"/api/v1/media/file/{owner}/{name}")
    authed = client.get(f"/api/v1/media/file/{owner}/{name}", headers=_bearer(unrelated))
    missing = client.get(f"/api/v1/media/file/{owner}/kyc_poa_does-not-exist.png")
    missing_ordinary = client.get(f"/api/v1/media/file/{owner}/not-there.png")

    for resp in (anon, authed, missing):
        assert resp.status_code == 404
        assert resp.content != PNG_BYTES
    # A real KYC file is indistinguishable from a missing one.
    assert (
        _neutral_404(anon, f"/api/v1/media/file/{owner}/{name}")
        == _neutral_404(missing, f"/api/v1/media/file/{owner}/kyc_poa_does-not-exist.png")
        == _neutral_404(missing_ordinary, f"/api/v1/media/file/{owner}/not-there.png")
    )
    assert "public" not in anon.headers.get("cache-control", "")


def test_resolver_denies_kyc_even_if_present_in_s3(monkeypatch):
    calls = []

    class FakeS3:
        def head_object(self, **kwargs):
            calls.append(kwargs)
            return {}

    monkeypatch.setattr(storage.settings, "S3_BUCKET_NAME", "bucket")
    monkeypatch.setattr(storage.settings, "AWS_ACCESS_KEY_ID", "x")
    monkeypatch.setattr(storage.settings, "AWS_SECRET_ACCESS_KEY", "y")
    monkeypatch.setattr(storage, "_s3_client", lambda: FakeS3())
    monkeypatch.setattr(storage, "media_storage_roots", lambda: [])

    assert storage.resolve_media_for_serving(5, "kyc_poa_x.pdf")[0] is None
    assert calls == []  # never even looked up
    assert storage.resolve_media_for_serving(5, "ordinary.png")[0] == "s3"


def test_static_media_mount_denies_kyc(tmp_path, app, db, monkeypatch):
    # Phase 7: the static mount also consults the DB (protected entry media), so
    # it must use the test database like every other request path.
    from app.db import session as session_module
    from tests.conftest import TestingSessionLocal

    monkeypatch.setattr(session_module, "SessionLocal", TestingSessionLocal)
    owner = OWNER_ID_BASE + 3
    _write(tmp_path, owner, "kyc_poa_static.png", PNG_BYTES)
    _write(tmp_path, owner, "public-static.png", PNG_BYTES)
    mini = Starlette(routes=[Mount("/media", app=storage.PublicMediaStaticFiles(directory=str(tmp_path)))])
    with StarletteTestClient(mini) as c:
        assert c.get(f"/media/{owner}/public-static.png").status_code == 200
        assert c.get(f"/media/{owner}/kyc_poa_static.png").status_code == 404
        assert c.get(f"/media/{owner}/KYC_POA_STATIC.PNG").status_code == 404
        assert c.get(f"/media/{owner}/./kyc_poa_static.png").status_code == 404
        assert c.get(f"/media/{owner}/kyc_poa_static.png/").status_code == 404

    # And the real application mounts /media with the protected class.
    mounts = [r for r in app.routes if getattr(r, "path", None) == "/media"]
    for mount in mounts:
        assert isinstance(mount.app, storage.PublicMediaStaticFiles)


def test_new_kyc_upload_goes_to_private_storage(client, media_env):
    owner = OWNER_ID_BASE + 4
    upload = UploadFile(BytesIO(PDF_BYTES), filename="bill.pdf", headers=Headers({"content-type": "application/pdf"}))
    result = asyncio.run(storage.store_kyc_proof_file(upload, owner))

    assert result["url"].startswith(f"kyc-private://{owner}/kyc_poa_")
    stored = result["path"]
    assert stored.startswith(str(media_env.private_root))
    assert not stored.startswith(str(media_env.media_root))
    filename = result["url"].rsplit("/", 1)[1]
    assert client.get(f"/api/v1/media/file/{owner}/{filename}").status_code == 404


def test_new_kyc_upload_uses_private_s3_prefix(monkeypatch):
    puts = []

    class FakeS3:
        def put_object(self, **kwargs):
            puts.append(kwargs)

    monkeypatch.setattr(storage.settings, "STORAGE_TYPE", "s3")
    monkeypatch.setattr(storage.settings, "S3_BUCKET_NAME", "bucket")
    monkeypatch.setattr(storage, "_s3_client", lambda: FakeS3())
    upload = UploadFile(BytesIO(PDF_BYTES), filename="bill.pdf", headers=Headers({"content-type": "application/pdf"}))
    result = asyncio.run(storage.store_kyc_proof_file(upload, 77))

    assert puts[0]["Key"].startswith("private/kyc/77/kyc_poa_")
    assert not puts[0]["Key"].startswith("uploads/")
    assert result["url"].startswith("kyc-private://77/")
    assert "amazonaws" not in result["url"]


@pytest.mark.parametrize(
    "stored, expected",
    [
        ("kyc-private://12/kyc_poa_a.png", ("private", 12, "kyc_poa_a.png")),
        ("/api/v1/media/file/12/kyc_poa_a.png", ("legacy", 12, "kyc_poa_a.png")),
        ("https://api.example.test/api/v1/media/file/12/kyc_poa_a.png", ("legacy", 12, "kyc_poa_a.png")),
        ("https://bucket.s3.amazonaws.com/uploads/12/kyc_poa_a.pdf", ("legacy", 12, "kyc_poa_a.pdf")),
        ("/api/v1/media/file/12/ordinary.png", None),  # not a KYC file
        ("kyc-private://12/../kyc_poa_a.png", None),
        ("kyc-private://x/kyc_poa_a.png", None),
        ("", None),
        (None, None),
    ],
)
def test_kyc_reference_parsing(stored, expected):
    assert storage.parse_kyc_document_reference(stored) == expected


def _kyc_fixture(db, suffix: str, owner_id_offset: int, front: str, back=None):
    owner = _user(db, f"kycowner-{suffix}")
    verification = KYCVerification(user_id=owner.id, status=KYCStatus.APPROVED)
    db.add(verification)
    db.commit()
    document = KYCDocument(
        verification_id=verification.id,
        document_type=DocumentType.UTILITY_BILL,
        front_image_url=front.format(uid=owner.id),
        back_image_url=back.format(uid=owner.id) if back else None,
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    return owner, verification, document


def _path_and_query(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.path}?{parsed.query}"


def test_admin_can_view_kyc_documents_via_signed_url(client, db, media_env):
    owner, verification, document = _kyc_fixture(
        db, "admin-ok", 0,
        front="kyc-private://{uid}/kyc_poa_front.png",
        back="/api/v1/media/file/{uid}/kyc_poa_back.pdf",  # legacy, still in the public root
    )
    _write(media_env.private_root, owner.id, "kyc_poa_front.png", PNG_BYTES)
    _write(media_env.media_root, owner.id, "kyc_poa_back.pdf", PDF_BYTES)
    admin = _user(db, "kycadmin", is_admin=True)

    detail = client.get(f"/api/v1/kyc/admin/verification/{verification.id}/detail", headers=_bearer(admin))
    assert detail.status_code == 200, detail.text
    doc = detail.json()["documents"][0]
    assert "/kyc/admin/documents/" in doc["front_public_url"]
    assert "token=" in doc["front_public_url"]

    front = client.get(_path_and_query(doc["front_public_url"]), headers={"Origin": "https://evil.example"})
    assert front.status_code == 200
    assert front.content == PNG_BYTES
    assert front.headers["content-type"] == "image/png"
    assert "no-store" in front.headers["cache-control"]
    assert "public" not in front.headers["cache-control"]
    assert front.headers["x-content-type-options"] == "nosniff"
    assert "access-control-allow-origin" not in front.headers

    back = client.get(_path_and_query(doc["back_public_url"]))
    assert back.status_code == 200
    assert back.content == PDF_BYTES
    assert back.headers["content-type"] == "application/pdf"

    # The legacy file is still unreachable publicly.
    assert client.get(f"/api/v1/media/file/{owner.id}/kyc_poa_back.pdf").status_code == 404


def test_signed_url_rejections_are_uniform_404(client, db, media_env):
    owner, verification, document = _kyc_fixture(
        db, "reject", 0, front="kyc-private://{uid}/kyc_poa_r.png", back="kyc-private://{uid}/kyc_poa_rb.png",
    )
    _write(media_env.private_root, owner.id, "kyc_poa_r.png", PNG_BYTES)
    _write(media_env.private_root, owner.id, "kyc_poa_rb.png", PNG_BYTES)
    admin = _user(db, "kycadmin2", is_admin=True)
    member = _user(db, "kycmember")
    base = f"/api/v1/kyc/admin/documents/{document.id}"

    good = create_kyc_document_view_token(admin.id, document.id, "front")
    assert client.get(f"{base}/front?token={good}").status_code == 200

    expired = security.jwt.encode(
        {
            "exp": datetime.utcnow() - timedelta(minutes=1), "iat": datetime.utcnow() - timedelta(minutes=10),
            "sub": str(admin.id), "type": "kyc_document_view", "doc": document.id, "side": "front",
            "iss": security.settings.JWT_ISSUER, "aud": security.settings.JWT_AUDIENCE,
        },
        security.settings.SECRET_KEY, algorithm=security.settings.ALGORITHM,
    )
    cases = [
        f"{base}/front",                                                   # no token
        f"{base}/front?token=garbage",                                     # malformed
        f"{base}/front?token={good[:-2]}xx",                               # tampered signature
        f"{base}/front?token={expired}",                                   # expired
        f"{base}/back?token={good}",                                       # wrong side
        f"/api/v1/kyc/admin/documents/{document.id + 999}/front?token={good}",  # wrong document
        f"{base}/selfie?token={good}",                                     # unknown side
        f"{base}/front?token={create_kyc_document_view_token(member.id, document.id, 'front')}",  # non-admin
        f"{base}/front?token={create_access_token(subject=admin.id)}",     # access token is not a view token
    ]
    bodies = set()
    for url in cases:
        resp = client.get(url)
        assert resp.status_code == 404, url
        assert resp.content != PNG_BYTES
        bodies.add(_neutral_404(resp, url.split("?", 1)[0]))
    assert len(bodies) == 1  # nothing distinguishes the failure reasons

    # Admin rights revoked after the token was issued -> denied.
    admin.is_admin = False
    db.commit()
    assert client.get(f"{base}/front?token={good}").status_code == 404


def test_view_token_cannot_authenticate_api_calls(client, db):
    admin = _user(db, "kycadmin3", is_admin=True)
    view_token = create_kyc_document_view_token(admin.id, 1, "front")
    assert client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {view_token}"}).status_code == 401


def test_non_admin_cannot_get_kyc_admin_detail(client, db, media_env):
    _, verification, _ = _kyc_fixture(db, "nonadmin", 0, front="kyc-private://{uid}/kyc_poa_n.png")
    member = _user(db, "kycmember2")
    resp = client.get(f"/api/v1/kyc/admin/verification/{verification.id}/detail", headers=_bearer(member))
    assert resp.status_code == 403


def test_kyc_reference_for_another_users_folder_is_refused(client, db, media_env):
    """A document row pointing into someone else's folder must not be served."""
    owner, verification, document = _kyc_fixture(
        db, "crossuser", 0, front=f"kyc-private://{OWNER_ID_BASE + 9}/kyc_poa_other.png",
    )
    _write(media_env.private_root, OWNER_ID_BASE + 9, "kyc_poa_other.png", PNG_BYTES)
    admin = _user(db, "kycadmin4", is_admin=True)
    token = create_kyc_document_view_token(admin.id, document.id, "front")
    assert client.get(f"/api/v1/kyc/admin/documents/{document.id}/front?token={token}").status_code == 404


def test_unknown_extension_is_served_as_attachment_not_html(client, db, media_env):
    owner, verification, document = _kyc_fixture(db, "html", 0, front="kyc-private://{uid}/kyc_poa_x.html")
    _write(media_env.private_root, owner.id, "kyc_poa_x.html", b"<script>alert(1)</script>")
    admin = _user(db, "kycadmin5", is_admin=True)
    token = create_kyc_document_view_token(admin.id, document.id, "front")
    resp = client.get(f"/api/v1/kyc/admin/documents/{document.id}/front?token={token}")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/octet-stream")
    assert resp.headers["content-disposition"] == "attachment"


# ---------------------------------------------------------------------------
# Persistent storage outside immutable release directories
# ---------------------------------------------------------------------------

def test_absolute_persistent_storage_paths_are_used(tmp_path, monkeypatch):
    shared = tmp_path / "shared"
    media_root = shared / "media"
    private_root = shared / "private_kyc"
    media_root.mkdir(parents=True)
    monkeypatch.setattr(storage.settings, "STORAGE_TYPE", "local")
    monkeypatch.setattr(storage.settings, "LOCAL_STORAGE_PATH", str(media_root))
    monkeypatch.setattr(storage.settings, "KYC_PRIVATE_STORAGE_PATH", str(private_root))
    monkeypatch.setattr(storage, "_mirror_local_media_file", lambda *_args: None)

    assert storage.media_storage_roots()[0] == str(media_root)
    assert storage.kyc_private_storage_root() == str(private_root)

    kyc = UploadFile(BytesIO(PDF_BYTES), filename="bill.pdf", headers=Headers({"content-type": "application/pdf"}))
    stored = asyncio.run(storage.store_kyc_proof_file(kyc, OWNER_ID_BASE + 20))
    assert stored["path"].startswith(str(private_root / str(OWNER_ID_BASE + 20)))


def test_default_private_root_is_sibling_of_absolute_media_root(tmp_path, monkeypatch):
    media_root = tmp_path / "shared" / "media"
    monkeypatch.setattr(storage.settings, "LOCAL_STORAGE_PATH", str(media_root))
    monkeypatch.setattr(storage.settings, "KYC_PRIVATE_STORAGE_PATH", "")
    assert storage.kyc_private_storage_root() == str(tmp_path / "shared" / "private_kyc")


@pytest.mark.parametrize("inside", ["", "private_kyc", "nested/deeper"])
def test_private_kyc_root_inside_public_media_fails_closed(tmp_path, monkeypatch, inside):
    media_root = tmp_path / "media"
    monkeypatch.setattr(storage.settings, "STORAGE_TYPE", "local")
    monkeypatch.setattr(storage.settings, "LOCAL_STORAGE_PATH", str(media_root))
    monkeypatch.setattr(storage.settings, "KYC_PRIVATE_STORAGE_PATH", str(media_root / inside) if inside else str(media_root))
    with pytest.raises(RuntimeError):
        storage.kyc_private_storage_root()
    kyc = UploadFile(BytesIO(PDF_BYTES), filename="bill.pdf", headers=Headers({"content-type": "application/pdf"}))
    with pytest.raises(RuntimeError):
        asyncio.run(storage.store_kyc_proof_file(kyc, OWNER_ID_BASE + 21))
    assert not any(p.name.startswith("kyc_") for p in media_root.rglob("*")) if media_root.exists() else True
