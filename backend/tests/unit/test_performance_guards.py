from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import threading
import time

from fastapi import Response
from sqlalchemy import event

from app.core.cache import CacheService
from app.api.api_v1.endpoints.categories import get_categories, update_category
from app.api.api_v1.endpoints.season_migration import _singleflight_top_high5
from app.core.cache import cache_service
from app.models.category import Category
from app.models.contest import Contest
from app.schemas.category import CategoryUpdate
from types import SimpleNamespace


class _ScanRedis:
    def __init__(self):
        self.deleted = []

    def scan_iter(self, *, match, count):
        assert match == "cache:ranking:*"
        assert count == 200
        yield from (f"key:{index}" for index in range(450))

    def delete(self, *keys):
        self.deleted.append(keys)
        return len(keys)


def test_cache_pattern_invalidation_uses_bounded_scan_batches():
    cache = CacheService.__new__(CacheService)
    cache.redis = _ScanRedis()

    assert cache.delete_pattern("cache:ranking:*") == 450
    assert [len(batch) for batch in cache.redis.deleted] == [200, 200, 50]


def test_redis_unavailable_falls_back_without_affecting_correctness():
    cache = CacheService.__new__(CacheService)
    cache.redis = None
    assert cache.get("missing") is None
    assert cache.set("key", {"value": 1}, ttl=1) is False
    assert cache.delete_pattern("cache:*") == 0


def test_concurrent_top_high5_requests_share_one_backend_calculation():
    started = threading.Event()
    release = threading.Event()
    calls = 0
    calls_lock = threading.Lock()

    @_singleflight_top_high5
    def calculate(*, response, round_id=None, country=None, level=None, current_user=None):
        nonlocal calls
        with calls_lock:
            calls += 1
        started.set()
        assert release.wait(timeout=2)
        return {"round_id": round_id, "country": country, "level": level}

    first_response = Response()
    second_response = Response()
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(
            calculate,
            response=first_response,
            round_id=12,
            country="TZ",
            level="country",
        )
        assert started.wait(timeout=1)
        second = executor.submit(
            calculate,
            response=second_response,
            round_id=12,
            country="tz",
            level="country",
        )
        deadline = time.monotonic() + 1
        while "Cache-Control" not in second_response.headers and time.monotonic() < deadline:
            time.sleep(0.005)
        assert "Cache-Control" in second_response.headers
        release.set()

        assert first.result(timeout=2) == second.result(timeout=2)

    assert calls == 1
    assert first_response.headers["Cache-Control"].startswith("no-store")
    assert second_response.headers["Cache-Control"].startswith("no-store")


def test_category_cache_hit_skips_database_and_mutation_invalidates(db, monkeypatch):
    cached = {
        "id": 7,
        "name": "Cached",
        "slug": "cached",
        "description": None,
        "image_url": None,
        "is_active": True,
        "created_at": "2026-09-09T00:00:00",
    }
    monkeypatch.setattr(cache_service, "get", lambda _key: [cached])
    rows = get_categories(db=db, active_only=True)
    assert [row.id for row in rows] == [7]

    category = Category(name="Live", slug="live", is_active=True)
    db.add(category)
    db.commit()
    invalidated = []
    monkeypatch.setattr(cache_service, "delete_pattern", invalidated.append)
    update_category(
        db=db,
        category_id=category.id,
        category_in=CategoryUpdate(description="changed"),
        current_user=SimpleNamespace(is_admin=True),
    )
    assert invalidated == ["cache:categories:*"]


def test_public_contest_list_query_count_is_constant(client, db):
    db.add_all(
        [
            Contest(
                name=f"Performance contest {index}",
                contest_type="general",
                level="country",
                contest_mode="participation",
                is_active=True,
                is_deleted=False,
            )
            for index in range(12)
        ]
    )
    db.commit()

    selects = []

    def count_selects(_conn, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().upper().startswith("SELECT"):
            selects.append(statement)

    event.listen(db.get_bind(), "before_cursor_execute", count_selects)
    try:
        response = client.get("/api/v1/contests/?limit=12")
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", count_selects)

    assert response.status_code == 200, response.text
    assert len(response.json()) == 12
    print(f"contest_list_selects={len(selects)}")
    assert len(selects) <= 5


def test_high_volume_list_limits_are_rejected(client):
    assert client.get("/api/v1/contests/?limit=101").status_code == 422
