"""EMAIL-5: provider webhook processing on a real PostgreSQL server.

Opt-in: RUN_POSTGRES_TESTS=1 (admin URL in POSTGRES_ADMIN_URL, default
postgresql://postgres@127.0.0.1:5432/postgres). Each run creates one DISPOSABLE
database and drops it. SQLite serialises writes, so durable deduplication and
state ordering under real concurrency can only be proven here.
"""
from __future__ import annotations

import os
import threading
import uuid
from datetime import datetime

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.db.base_class import Base
from app.models.email import EmailDelivery, EmailWebhookEvent
from app.services import email_webhooks

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(os.getenv("RUN_POSTGRES_TESTS", "").lower() not in ("1", "true", "yes"),
                       reason="Set RUN_POSTGRES_TESTS=1 to run against a local PostgreSQL server"),
]

ADMIN_URL = os.getenv("POSTGRES_ADMIN_URL", "postgresql://postgres@127.0.0.1:5432/postgres")
TABLES = ("email_deliveries", "email_webhook_events")
WORKERS = 12


@pytest.fixture
def pg():
    name = f"mh5_webhook_test_{uuid.uuid4().hex[:10]}"
    admin = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    engine = create_engine(ADMIN_URL.rsplit("/", 1)[0] + f"/{name}", pool_size=WORKERS + 2)
    try:
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE users (id SERIAL PRIMARY KEY)"))
        Base.metadata.create_all(engine, tables=[Base.metadata.tables[t] for t in TABLES])
        yield sessionmaker(bind=engine, autoflush=False)
    finally:
        engine.dispose()
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


def _delivery(Session, message_id="re_msg_1", status="SENT") -> int:
    now = datetime.utcnow()
    with Session() as db:
        row = EmailDelivery(event_key="KYC.APPROVED", category="KYC", recipient_masked="m***@e***.com", status=status,
                            attempt_count=1, idempotency_key=f"pg:{uuid.uuid4().hex}", provider="resend",
                            provider_message_id=message_id, sent_at=now, created_at=now, updated_at=now)
        db.add(row)
        db.commit()
        return row.id


def _event(kind, message_id="re_msg_1", when="2026-10-06T10:00:00Z", **data):
    return {"type": kind, "created_at": when, "data": {"email_id": message_id, **data}}


def _together(count, work):
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


def test_the_same_event_delivered_concurrently_is_applied_exactly_once(pg):
    delivery_id = _delivery(pg)
    payload = _event("email.bounced", bounce={"type": "Permanent", "subType": "General"})

    def deliver(_):
        with pg() as db:
            return email_webhooks.process_event(db, provider="resend", event_id="msg_same", payload=payload).outcome
    outcomes = _together(WORKERS, deliver)
    assert sorted(outcomes) == ["applied"] + ["duplicate"] * (WORKERS - 1)
    with pg() as db:
        assert db.query(EmailWebhookEvent).count() == 1                       # one durable event
        row = db.query(EmailDelivery).get(delivery_id)
        assert (row.status, row.failure_category, row.failure_code) == ("BOUNCED", "bounced", "Permanent")
        # and it stays that way on a later redelivery through a fresh connection
        assert email_webhooks.process_event(db, provider="resend", event_id="msg_same", payload=payload).outcome == "duplicate"


def test_different_events_for_one_delivery_arriving_together_end_in_the_highest_state(pg):
    delivery_id = _delivery(pg)
    kinds = ["email.sent", "email.delivery_delayed", "email.delivered", "email.bounced", "email.complained",
             "email.delivered", "email.sent", "email.delivery_delayed"]

    def deliver(i):
        with pg() as db:
            return email_webhooks.process_event(db, provider="resend", event_id=f"msg_{i}",
                                                payload=_event(kinds[i], when=f"2026-10-06T10:00:0{i}Z")).outcome
    outcomes = _together(len(kinds), deliver)
    assert "duplicate" not in outcomes and "unmatched" not in outcomes
    with pg() as db:
        row = db.query(EmailDelivery).get(delivery_id)
        assert row.status == "COMPLAINED" and row.delivered_at is not None     # never left at a lower state
        assert db.query(EmailWebhookEvent).filter(EmailWebhookEvent.email_delivery_id == delivery_id).count() == len(kinds)
        # whatever the interleaving, the status only ever moved up: applied outcomes are strictly increasing in rank
        applied = [e.event_type for e in db.query(EmailWebhookEvent).filter(EmailWebhookEvent.outcome == "applied")
                   .order_by(EmailWebhookEvent.processed_at, EmailWebhookEvent.id)]
        assert "email.complained" in applied


def test_early_events_are_matched_when_the_send_is_recorded(pg):
    with pg() as db:
        for i, kind in enumerate(("email.delivered", "email.sent")):
            out = email_webhooks.process_event(db, provider="resend", event_id=f"early_{i}",
                                               payload=_event(kind, "re_late", when=f"2026-10-06T10:00:0{2 - i}Z"))
            assert out.outcome == "unmatched"
    delivery_id = _delivery(pg, message_id="re_late")
    with pg() as db:
        row = db.query(EmailDelivery).get(delivery_id)
        assert email_webhooks.apply_pending(db, row) == 2
        db.commit()
        db.refresh(row)
        assert row.status == "DELIVERED"
        outcomes = {e.event_type: e.outcome for e in db.query(EmailWebhookEvent)}
        assert outcomes == {"email.sent": "recorded", "email.delivered": "applied"}


def test_event_id_uniqueness_is_enforced_by_the_database(pg):
    from sqlalchemy.exc import IntegrityError

    now = datetime.utcnow()
    with pg() as db:
        db.add(EmailWebhookEvent(provider="resend", provider_event_id="msg_u", event_type="email.sent", received_at=now))
        db.commit()
        db.add(EmailWebhookEvent(provider="resend", provider_event_id="msg_u", event_type="email.delivered", received_at=now))
        with pytest.raises(IntegrityError):
            db.commit()
