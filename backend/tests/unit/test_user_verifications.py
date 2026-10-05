"""User verifications (contest entry media verification: selfie, voice, video,
brand, content).

Regression for the production defect: GET /api/v1/verifications/me answered
503 because the user_verifications table had never been created (the model is
registered only when the API module is imported, so databases bootstrapped
from the model registry and stamped never got it).

This feature is NOT email verification, KYC, guardian or nominee-claim
verification. All data here is SYNTHETIC.
"""
from __future__ import annotations

import pytest

import app.models  # noqa: F401
from app.db.base_class import Base
from app.models.verification import MediaType, UserVerification, VerificationStatus, VerificationType
from tests.unit.test_age_gate_registration import auth, make_user

ME = "/api/v1/verifications/me"
EMPTY = {"has_selfie": False, "has_voice": False, "has_video": False, "has_brand": False, "has_content": False,
         "selfie_status": None, "voice_status": None, "video_status": None, "brand_status": None,
         "content_status": None}


def add(db, user, vtype, status=VerificationStatus.PENDING, media=MediaType.IMAGE, url="https://cdn.example/m.jpg"):
    row = UserVerification(user_id=user.id, verification_type=vtype.value, media_url=url, media_type=media.value,
                           status=status.value)
    db.add(row)
    db.commit()
    return row


def test_model_is_part_of_the_model_registry():
    """The root cause: a model that is only imported by its endpoint module is
    invisible to anything that builds the schema from app.models."""
    import app.models as registry

    assert "user_verifications" in Base.metadata.tables
    assert registry.UserVerification is UserVerification and "UserVerification" in registry.__all__


def test_anonymous_is_rejected(client):
    assert client.get(ME).status_code == 401


def test_user_without_any_record_gets_the_empty_state(client, db):
    r = client.get(ME, headers=auth(make_user(db)))
    assert r.status_code == 200, r.text
    body = r.json()
    assert {k: body[k] for k in EMPTY} == EMPTY
    assert client.get(f"{ME}/all", headers=auth(make_user(db))).json() == []


def test_records_are_reported_per_kind_and_only_for_their_owner(client, db):
    owner, other = make_user(db), make_user(db)
    add(db, owner, VerificationType.SELFIE, VerificationStatus.APPROVED)
    add(db, owner, VerificationType.VOICE, VerificationStatus.PENDING, MediaType.AUDIO, "https://cdn.example/v.mp3")
    add(db, owner, VerificationType.BRAND, VerificationStatus.REJECTED)
    body = client.get(ME, headers=auth(owner)).json()
    assert (body["has_selfie"], body["selfie_status"]) == (True, "approved")
    assert (body["has_voice"], body["voice_status"], body["voice_url"]) == (True, "pending", "https://cdn.example/v.mp3")
    assert (body["has_brand"], body["brand_status"]) == (True, "rejected")
    assert body["has_video"] is False and body["has_content"] is False
    rows = client.get(f"{ME}/all", headers=auth(owner)).json()
    assert sorted(r["verification_type"] for r in rows) == ["brand", "selfie", "voice"]
    assert client.get(f"{ME}/all?verification_type=voice", headers=auth(owner)).json()[0]["status"] == "pending"
    # another member sees nothing of it
    assert {k: client.get(ME, headers=auth(other)).json()[k] for k in EMPTY} == EMPTY
    assert client.get(f"/api/v1/verifications/{rows[0]['id']}", headers=auth(other)).status_code in (403, 404)


def test_stored_values_are_the_lowercase_api_values(client, db):
    """What is stored is exactly what the API and the frontend exchange."""
    from sqlalchemy import text

    user = make_user(db)
    add(db, user, VerificationType.SELFIE_WITH_DOCUMENT, VerificationStatus.APPROVED)
    raw = db.execute(text("select verification_type, media_type, status from user_verifications")).one()
    assert tuple(raw) == ("selfie_with_document", "image", "approved")
    db.expire_all()
    row = db.query(UserVerification).one()
    assert (row.verification_type, row.media_type, row.status) == ("selfie_with_document", "image", "approved")


def test_submission_flow_and_contest_entry_requirement(client, db, monkeypatch):
    from app.api.api_v1.endpoints import verifications as endpoint
    from app.services.contest_entry_eligibility import _has_approved

    class Approved:
        is_approved = True
        flags = []

    monkeypatch.setattr(endpoint.content_moderation_service, "moderate_image", lambda url: Approved())
    user = make_user(db)
    visual = (VerificationType.SELFIE.value, VerificationType.SELFIE_WITH_PET.value,
              VerificationType.SELFIE_WITH_DOCUMENT.value)
    assert _has_approved(db, user.id, visual) is False                 # no record: requirement not met, no error
    r = client.post("/api/v1/verifications/", headers=auth(user), json={
        "verification_type": "selfie", "media_url": "https://cdn.example/s.jpg", "media_type": "image"})
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "approved"                            # selfie: auto-approved once moderation passes
    assert _has_approved(db, user.id, visual) is True
    r = client.post("/api/v1/verifications/", headers=auth(user), json={
        "verification_type": "brand", "media_url": "https://cdn.example/b.jpg", "media_type": "image"})
    assert r.status_code == 201 and r.json()["status"] == "pending"    # brand: waits for an admin
    body = client.get(ME, headers=auth(user)).json()
    assert (body["selfie_status"], body["brand_status"]) == ("approved", "pending")
    assert client.post("/api/v1/verifications/", headers=auth(user), json={
        "verification_type": "not-a-kind", "media_url": "https://cdn.example/x.jpg",
        "media_type": "image"}).status_code == 422


def test_admin_review(client, db):
    member, admin = make_user(db), make_user(db, admin=True)
    row = add(db, member, VerificationType.CONTENT)
    assert client.get("/api/v1/verifications/admin/pending", headers=auth(member)).status_code == 403
    pending = client.get("/api/v1/verifications/admin/pending", headers=auth(admin))
    assert pending.status_code == 200, pending.text
    r = client.put(f"/api/v1/verifications/admin/{row.id}", headers=auth(admin),
                   json={"status": "rejected", "rejection_reason": "unreadable"})
    assert r.status_code == 200, r.text
    assert client.get(ME, headers=auth(member)).json()["content_status"] == "rejected"


@pytest.mark.parametrize("column", ["verification_type", "media_type", "status"])
def test_columns_are_plain_strings_like_the_migrated_schema(column):
    """The migration creates VARCHAR columns; the model must describe the same
    thing (a database enum type here would not match the migrated table)."""
    from sqlalchemy import String

    assert isinstance(UserVerification.__table__.c[column].type, String)
    assert not hasattr(UserVerification.__table__.c[column].type, "enums")
