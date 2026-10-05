"""EMAIL-1: the outbox claim on a real PostgreSQL server (FOR UPDATE SKIP LOCKED).

Opt-in: RUN_POSTGRES_TESTS=1 (admin URL in POSTGRES_ADMIN_URL, default
postgresql://postgres@127.0.0.1:5432/postgres). Each run creates one DISPOSABLE
database and drops it. SQLite (the default test database) ignores row locks, so
the concurrency guarantee can only be proven here.
"""
from __future__ import annotations

import os
import threading
import uuid
from datetime import datetime

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.db.base_class import Base
from app.models.email import EmailDelivery
from app.core.config import settings
from app.services.email_outbox import STALE_PROCESSING_AFTER, _requeue_stale, claim_batch

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(os.getenv("RUN_POSTGRES_TESTS", "").lower() not in ("1", "true", "yes"),
                       reason="Set RUN_POSTGRES_TESTS=1 to run against a local PostgreSQL server"),
]

ADMIN_URL = os.getenv("POSTGRES_ADMIN_URL", "postgresql://postgres@127.0.0.1:5432/postgres")
EMAIL_TABLES = ("email_settings", "email_event_settings", "email_deliveries", "email_webhook_events")


@pytest.fixture
def pg():
    name = f"mh5_email_test_{uuid.uuid4().hex[:10]}"
    admin = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    engine = create_engine(ADMIN_URL.rsplit("/", 1)[0] + f"/{name}")
    try:
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE users (id SERIAL PRIMARY KEY)"))
        Base.metadata.create_all(engine, tables=[Base.metadata.tables[t] for t in EMAIL_TABLES])
        yield sessionmaker(bind=engine, autoflush=False)
    finally:
        engine.dispose()
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


def _seed(Session, count: int) -> None:
    now = datetime.utcnow()
    with Session() as db:
        for i in range(count):
            db.add(EmailDelivery(event_key="KYC.APPROVED", category="KYC", recipient_masked="m***@e***.com",
                                 status="QUEUED", idempotency_key=f"pg:{i}", next_attempt_at=now, created_at=now,
                                 updated_at=now))
        db.commit()


def test_rows_locked_by_one_worker_are_skipped_by_another(pg):
    _seed(pg, 6)
    now = datetime.utcnow()
    holder, other = pg(), pg()
    try:
        # Worker A is in the middle of claiming the first three rows (locks held, not committed).
        locked = (holder.query(EmailDelivery).filter(EmailDelivery.status == "QUEUED").order_by(EmailDelivery.id)
                  .limit(3).with_for_update(skip_locked=True).all())
        assert len(locked) == 3
        # Worker B does not wait and does not take them: it gets the other three.
        taken = claim_batch(other, now=now, batch_size=10)
        assert len(taken) == 3 and not set(taken) & {r.id for r in locked}
        holder.rollback()
    finally:
        holder.close()
        other.close()


def test_concurrent_workers_claim_every_row_exactly_once(pg):
    _seed(pg, 60)
    now = datetime.utcnow()
    barrier = threading.Barrier(4)
    claimed, errors = [], []

    def worker():
        db = pg()
        try:
            barrier.wait(timeout=10)
            while True:
                ids = claim_batch(db, now=now, batch_size=7)
                if not ids:
                    break
                claimed.extend(ids)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)
        finally:
            db.close()

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert errors == []
    assert len(claimed) == 60 and len(set(claimed)) == 60            # no row claimed twice
    with pg() as db:
        rows = db.query(EmailDelivery).all()
        assert all(r.status == "PROCESSING" and r.attempt_count == 1 for r in rows)


def test_idempotency_key_is_unique_in_postgres(pg):
    _seed(pg, 1)
    now = datetime.utcnow()
    with pg() as db:
        db.add(EmailDelivery(event_key="KYC.APPROVED", category="KYC", recipient_masked="x", status="QUEUED",
                             idempotency_key="pg:0", created_at=now, updated_at=now))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        with pytest.raises(IntegrityError):                          # status is constrained as well
            db.add(EmailDelivery(event_key="KYC.APPROVED", category="KYC", recipient_masked="x", status="NOPE",
                                 idempotency_key="pg:other", created_at=now, updated_at=now))
            db.commit()


def test_stale_claims_are_recovered_once_and_bounded(pg, monkeypatch):
    """A worker that died after claiming leaves rows PROCESSING: they are taken
    back after the stale window, by one recovery pass only, and end FAILED when
    the attempts are used up."""
    monkeypatch.setattr(settings, "EMAIL_MAX_ATTEMPTS", 2)
    _seed(pg, 4)
    t0 = datetime.utcnow()
    with pg() as db:
        assert len(claim_batch(db, now=t0, batch_size=10)) == 4
        assert _requeue_stale(db, t0 + STALE_PROCESSING_AFTER / 2) == 0          # not stale yet
    later = t0 + STALE_PROCESSING_AFTER * 2
    a, b = pg(), pg()
    try:
        # recovery pass A holds the rows; a concurrent pass B skips them instead of double-recovering
        held = (a.query(EmailDelivery).filter(EmailDelivery.status == "PROCESSING")
                .with_for_update(skip_locked=True).all())
        assert len(held) == 4 and _requeue_stale(b, later) == 0
        a.rollback()
        assert _requeue_stale(b, later) == 4
    finally:
        a.close()
        b.close()
    with pg() as db:
        assert {r.status for r in db.query(EmailDelivery).all()} == {"QUEUED"}
        assert len(claim_batch(db, now=later, batch_size=10)) == 4               # second attempt, worker dies again
        assert _requeue_stale(db, later + STALE_PROCESSING_AFTER * 2) == 4
        rows = db.query(EmailDelivery).all()
        assert all((r.status, r.failure_category, r.attempt_count) == ("FAILED", "stale_claim", 2) for r in rows)
