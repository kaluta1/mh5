"""EMAIL-2: one-time credentials and durable rate limits on a real PostgreSQL
server.

Opt-in: RUN_POSTGRES_TESTS=1 (admin URL in POSTGRES_ADMIN_URL, default
postgresql://postgres@127.0.0.1:5432/postgres). Each run creates one DISPOSABLE
database and drops it. SQLite (the default test database) serialises every
write, so the guarantees under real concurrency can only be proven here.
"""
from __future__ import annotations

import os
import threading
import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.db.base_class import Base
from app.models.auth_security import AuthRateLimit, AuthToken
from app.services import auth_throttle, auth_tokens

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(os.getenv("RUN_POSTGRES_TESTS", "").lower() not in ("1", "true", "yes"),
                       reason="Set RUN_POSTGRES_TESTS=1 to run against a local PostgreSQL server"),
]

ADMIN_URL = os.getenv("POSTGRES_ADMIN_URL", "postgresql://postgres@127.0.0.1:5432/postgres")
TABLES = ("auth_tokens", "auth_rate_limits")
WORKERS = 12


@pytest.fixture
def pg():
    name = f"mh5_auth_test_{uuid.uuid4().hex[:10]}"
    admin = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    engine = create_engine(ADMIN_URL.rsplit("/", 1)[0] + f"/{name}", pool_size=WORKERS + 2)
    try:
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE users (id SERIAL PRIMARY KEY)"))
            conn.execute(text("INSERT INTO users DEFAULT VALUES"))
        Base.metadata.create_all(engine, tables=[Base.metadata.tables[t] for t in TABLES])
        yield sessionmaker(bind=engine, autoflush=False)
    finally:
        engine.dispose()
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


def _together(count, work):
    """Run `work(i)` in `count` threads released at the same instant."""
    barrier, results, errors = threading.Barrier(count), [None] * count, []

    def run(i):
        try:
            barrier.wait(timeout=10)
            results[i] = work(i)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)
    threads = [threading.Thread(target=run, args=(i,)) for i in range(count)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert not errors, errors
    return results


def test_a_credential_is_used_exactly_once_under_concurrency(pg):
    now = datetime.utcnow()
    with pg() as db:
        db.add(AuthToken(user_id=1, purpose="password_reset", token_hash="a" * 64, email_hash="b" * 64,
                         security_version=0, expires_at=now + timedelta(minutes=30)))
        db.commit()
        token_id = db.query(AuthToken.id).scalar()

    def use(_):
        with pg() as db:
            won = auth_tokens.mark_used(db, token_id, datetime.utcnow())
            db.commit()
            return won
    assert sorted(_together(WORKERS, use)) == [False] * (WORKERS - 1) + [True]


def test_a_revoked_credential_cannot_be_used(pg):
    now = datetime.utcnow()
    with pg() as db:
        db.add(AuthToken(user_id=1, purpose="email_verification", token_hash="c" * 64, email_hash="b" * 64,
                         security_version=0, expires_at=now + timedelta(minutes=30)))
        db.commit()
        assert auth_tokens.revoke(db, 1, "email_verification") == 1
        db.commit()
        assert auth_tokens.mark_used(db, db.query(AuthToken.id).scalar(), now) is False


def test_the_limit_holds_under_concurrency_and_across_connections(pg):
    rule = (auth_throttle.Limit("pg:scope", 5, 3600),)
    now = datetime(2026, 10, 5, 12, 30)

    def hit(_):
        with pg() as db:
            return auth_throttle.hit(db, rule, "198.51.100.7", now=now)
    results = _together(WORKERS, hit)
    assert results.count(True) == 5 and results.count(False) == WORKERS - 5      # never more than the limit
    with pg() as db:
        row = db.query(AuthRateLimit).one()                                     # one row per key and window
        assert (row.count, row.window_start) == (5, datetime(2026, 10, 5, 12, 0))
        assert "198.51.100.7" not in row.key_hash
        # a fresh connection (a restarted process) still sees the limit ...
        assert auth_throttle.hit(db, rule, "198.51.100.7", now=now) is False
        # ... and the next window starts clean
        assert auth_throttle.hit(db, rule, "198.51.100.7", now=now + timedelta(hours=1)) is True


def test_database_constraints(pg):
    from sqlalchemy.exc import IntegrityError

    now = datetime.utcnow()
    with pg() as db:
        db.add(AuthToken(user_id=1, purpose="password_reset", token_hash="d" * 64, email_hash="b" * 64,
                         security_version=0, expires_at=now))
        db.commit()
        for bad in (dict(purpose="password_reset", token_hash="d" * 64),            # same digest twice
                    dict(purpose="something_else", token_hash="e" * 64)):           # unknown purpose
            db.add(AuthToken(user_id=1, email_hash="b" * 64, security_version=0, expires_at=now, **bad))
            with pytest.raises(IntegrityError):
                db.commit()
            db.rollback()
        db.execute(text("DELETE FROM users"))                                       # account deleted ...
        db.commit()
        assert db.query(AuthToken).count() == 0                                     # ... its credentials go with it
