from __future__ import annotations

import asyncio
from io import BytesIO
from types import SimpleNamespace

import pytest
from PIL import Image
from starlette.datastructures import Headers, UploadFile

from app.api.api_v1.endpoints.categories import (
    create_category,
    delete_category,
    get_categories,
    get_category,
    update_category,
)
from app.api.api_v1.endpoints.media import delete_media
from app.core import storage
from app.models.category import Category
from app.models.contest import Contest
from app.schemas.category import CategoryCreate, CategoryUpdate
from app.services.contest_category_integrity import category_scope_key, contest_ids_for_category
from app.services.voting_ranking import bucket_key_for_contest
from app.crud import contest as contest_crud
from app.crud.crud_social import CRUDPost
from app.api.api_v1.endpoints.contestant import _canonicalize_social_media_url


def png_bytes() -> bytes:
    output = BytesIO()
    Image.new("RGB", (3, 2), "red").save(output, format="PNG")
    return output.getvalue()


def add_category(db, *, name: str, slug: str, active: bool = True) -> Category:
    row = Category(name=name, slug=slug, is_active=active)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_category_listing_excludes_disabled_and_is_deterministic(db):
    add_category(db, name="Zulu", slug="zulu")
    add_category(db, name="Alpha", slug="alpha")
    add_category(db, name="Hidden", slug="hidden", active=False)
    assert [row.slug for row in get_categories(db=db, active_only=True)] == ["alpha", "zulu"]


def test_category_lookup_by_id_and_case_insensitive_slug(db):
    category = add_category(db, name="Afro Pop", slug="afro-pop")
    assert get_category(str(category.id), db=db, active_only=True).id == category.id
    assert get_category("AFRO-POP", db=db, active_only=True).id == category.id


def test_disabled_category_lookup_fails_closed(db):
    from fastapi import HTTPException

    category = add_category(db, name="Hidden", slug="hidden", active=False)
    with pytest.raises(HTTPException) as exc:
        get_category(str(category.id), db=db, active_only=True)
    assert exc.value.status_code == 404
    assert get_category(str(category.id), db=db, active_only=False).id == category.id


def test_category_create_normalizes_and_blocks_case_space_duplicate(db):
    admin = SimpleNamespace(is_admin=True)
    created = create_category(
        db=db,
        category_in=CategoryCreate(name="  Dance  ", slug="DANCE", is_active=True),
        current_user=admin,
    )
    assert (created.name, created.slug) == ("Dance", "dance")
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        create_category(
            db=db,
            category_in=CategoryCreate(name=" dance ", slug="dance-two", is_active=True),
            current_user=admin,
        )
    assert exc.value.status_code == 409


def test_category_create_rejects_malformed_slug_and_insecure_image(db):
    from fastapi import HTTPException

    admin = SimpleNamespace(is_admin=True)
    with pytest.raises(HTTPException):
        create_category(
            db=db,
            category_in=CategoryCreate(name="Bad", slug="bad-", is_active=True),
            current_user=admin,
        )
    with pytest.raises(HTTPException):
        create_category(
            db=db,
            category_in=CategoryCreate(
                name="Image", slug="image", image_url="javascript:alert(1)", is_active=True
            ),
            current_user=admin,
        )


def test_category_admin_authorization_is_enforced(db):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        create_category(
            db=db,
            category_in=CategoryCreate(name="Dance", slug="dance", is_active=True),
            current_user=SimpleNamespace(is_admin=False),
        )
    assert exc.value.status_code == 403


def test_category_media_reference_can_be_replaced_without_deleting_media(db):
    category = add_category(db, name="Dance", slug="dance")
    updated = update_category(
        db=db,
        category_id=category.id,
        category_in=CategoryUpdate(image_url="/api/v1/media/file/1/category.png"),
        current_user=SimpleNamespace(is_admin=True),
    )
    assert updated.image_url == "/api/v1/media/file/1/category.png"


def test_category_in_use_cannot_be_hard_deleted(db):
    from fastapi import HTTPException

    category = add_category(db, name="Dance", slug="dance")
    db.add(
        Contest(
            name="Dance contest", contest_type="dance", level="country",
            category_id=category.id, contest_mode="nomination", is_active=True, is_deleted=False,
        )
    )
    db.commit()
    with pytest.raises(HTTPException) as exc:
        delete_category(db=db, category_id=category.id, current_user=SimpleNamespace(is_admin=True))
    assert exc.value.status_code == 400


def test_category_scope_prefers_canonical_id():
    assert category_scope_key(SimpleNamespace(category_id=9, contest_type="wrong")) == "cat:9"
    assert bucket_key_for_contest(SimpleNamespace(category_id=9, contest_type="wrong", contest_mode="nomination")) == "cat:9"


def test_category_contest_ids_do_not_leak_across_same_legacy_label(db):
    one = add_category(db, name="One", slug="one")
    two = add_category(db, name="Two", slug="two")
    for category_id in (one.id, two.id):
        db.add(
            Contest(
                name=f"Contest {category_id}", contest_type="shared-label", level="country",
                category_id=category_id, contest_mode="nomination", is_active=True, is_deleted=False,
            )
        )
    db.commit()
    ids = contest_ids_for_category(db, category_id=one.id, contest_type="shared-label")
    assert len(ids) == 1
    assert db.query(Contest).filter(Contest.id == ids[0]).one().category_id == one.id


def test_contest_listing_filter_uses_canonical_category_id(db):
    one = add_category(db, name="One", slug="one")
    two = add_category(db, name="Two", slug="two")
    for category in (one, two):
        db.add(
            Contest(
                name=category.name, contest_type="same-display-label", level="country",
                category_id=category.id, contest_mode="participation", is_active=True, is_deleted=False,
            )
        )
    db.commit()
    rows = contest_crud.get_multi_with_filters(
        db=db, skip=0, limit=20, filters={"category_id": one.id}
    )
    assert [row.category_id for row in rows] == [one.id]


def test_valid_png_is_verified_from_bytes():
    result = storage.validate_media_content("photo.png", "image/png", png_bytes())
    assert result["media_type"] == "image"
    assert (result["width"], result["height"]) == (3, 2)


@pytest.mark.parametrize(
    "url,canonical",
    [
        ("https://youtube.com/watch?v=dQw4w9WgXcQ", "youtube:dQw4w9WgXcQ"),
        ("https://vimeo.com/123456", "vimeo:123456"),
        ("https://tiktok.com/@user/video/123456", "tiktok:123456"),
        ("https://cdn.example/video.mp4", "direct:cdn.example/video.mp4"),
    ],
)
def test_backend_video_url_canonicalization(url, canonical):
    assert _canonicalize_social_media_url(url) == canonical


@pytest.mark.parametrize(
    "url",
    [
        "https://youtube.com.evil.test/watch?v=dQw4w9WgXcQ",
        "https://youtube.com/watch?v=short",
        "javascript:alert(1)",
        "http://cdn.example/video.mp4",
    ],
)
def test_backend_video_url_validation_rejects_spoofed_or_unsafe_urls(url):
    assert _canonicalize_social_media_url(url) is None


@pytest.mark.parametrize(
    "name,mime,content,message",
    [
        ("../photo.png", "image/png", b"x", "filename"),
        ("photo.svg", "image/svg+xml", b"<svg><script/></svg>", "Unsupported"),
        ("photo.jpg", "image/jpeg", png_bytes(), "extension"),
        ("photo.png", "image/jpeg", png_bytes(), "MIME"),
        ("photo.png", "image/png", b"not-an-image", "Unsupported"),
    ],
)
def test_invalid_uploads_fail_closed(name, mime, content, message):
    with pytest.raises(ValueError, match=message):
        storage.validate_media_content(name, mime, content)


def test_oversized_upload_is_rejected_before_image_decode():
    content = b"\x89PNG\r\n\x1a\n" + (b"0" * storage.MEDIA_IMAGE_MAX_BYTES)
    with pytest.raises(ValueError, match="too large"):
        storage.validate_media_content("large.png", "image/png", content)


def test_serving_rejects_traversal_filename():
    assert storage.resolve_media_for_serving(1, "..\\secret.png")[0] is None


def test_media_delete_requires_owner_or_admin(monkeypatch):
    from fastapi import HTTPException

    monkeypatch.setattr(
        "app.api.api_v1.endpoints.media.crud_media.get",
        lambda **_kwargs: SimpleNamespace(id=5, user_id=10),
    )
    with pytest.raises(HTTPException) as exc:
        delete_media(
            db=SimpleNamespace(), media_id=5,
            current_user=SimpleNamespace(id=11, is_admin=False),
        )
    assert exc.value.status_code == 403


def test_post_cannot_attach_media_owned_by_another_user():
    from unittest.mock import MagicMock

    db = MagicMock()
    db.query.return_value.filter.return_value.count.return_value = 0
    payload = SimpleNamespace(
        media_ids=[9], content="post", post_type="image", visibility="public",
        group_id=None, location=None, tags=None,
    )
    with pytest.raises(ValueError, match="not owned"):
        CRUDPost().create(db, payload, author_id=1)
    db.add.assert_not_called()


def test_unauthorized_upload_is_rejected_before_storage(client, monkeypatch):
    called = False

    async def forbidden_store(*_args, **_kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr("app.api.api_v1.endpoints.media.store_media", forbidden_store)
    response = client.post(
        "/api/v1/media/upload",
        files={"file": ("photo.png", png_bytes(), "image/png")},
    )
    assert response.status_code in (401, 403)
    assert called is False


def test_media_file_route_is_registered_once(app):
    matching_routes = [
        route
        for route in app.routes
        if getattr(route, "path", None) == "/api/v1/media/file/{user_id}/{filename}"
        and "GET" in getattr(route, "methods", set())
    ]
    assert len(matching_routes) == 1


def test_local_store_uses_canonical_extension_and_metadata(tmp_path, monkeypatch):
    monkeypatch.setattr(storage.settings, "STORAGE_TYPE", "local")
    monkeypatch.setattr(storage.settings, "LOCAL_STORAGE_PATH", str(tmp_path))
    monkeypatch.setattr(storage, "_mirror_local_media_file", lambda *_args: None)
    upload = UploadFile(
        BytesIO(png_bytes()),
        filename="photo.png",
        headers=Headers({"content-type": "image/png"}),
    )
    result = asyncio.run(storage.store_media(upload, 42))
    assert result["url"].startswith("/api/v1/media/file/42/")
    assert result["url"].endswith(".png")
    assert result["metadata"]["file_size"] == len(png_bytes())


def test_production_s3_failure_does_not_fall_back_local(monkeypatch):
    monkeypatch.setattr(storage.settings, "STORAGE_TYPE", "s3")
    monkeypatch.setenv("ENVIRONMENT", "production")

    async def fail_s3(*_args, **_kwargs):
        raise RuntimeError("s3 unavailable")

    async def forbidden_local(*_args, **_kwargs):
        raise AssertionError("must not fall back")

    monkeypatch.setattr(storage, "store_in_s3", fail_s3)
    monkeypatch.setattr(storage, "store_locally", forbidden_local)
    upload = UploadFile(
        BytesIO(png_bytes()), filename="photo.png", headers=Headers({"content-type": "image/png"})
    )
    with pytest.raises(RuntimeError, match="s3 unavailable"):
        asyncio.run(storage.store_media(upload, 1))
