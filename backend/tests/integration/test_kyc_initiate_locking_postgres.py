"""KYC start / renewal against everything else that touches the same member, on a
real PostgreSQL server.

Opt-in: RUN_POSTGRES_TESTS=1 (see test_payments_postgres.py). Each test runs in ONE
DISPOSABLE database that is dropped afterwards. Everything is SYNTHETIC; the KYC
provider is a fake and nothing leaves the process.

A start locks the member's row, then the verification row. Everything else that
needs both takes them in that same order, and the start's lock on the member is
FOR NO KEY UPDATE: it serialises starts without blocking a row that merely points
at the member (an audit row's foreign key check). The interleaving tests hold a
start exactly between its two locks while the other transaction runs, instead of
hoping the scheduler finds that moment; before the fix each of them ended in
PostgreSQL deadlock 40P01.
"""
from __future__ import annotations

import asyncio
import os
import random
import re
import threading
import time
from datetime import datetime, timedelta

import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import DBAPIError

from app.api.api_v1.endpoints import kyc as kyc_endpoint
from app.crud import crud_kyc
from app.models.kyc import KYCStatus, KYCVerification
from app.models.payment import Deposit
from app.services import kyc_provider_dispatch as dispatch
from app.services import kyc_settings
from tests.integration.test_kaluta_webhook_postgres import open_verification, payload
from tests.integration.test_kyc_decision_race_postgres import approved, assert_consistent, rejected, state
from tests.integration.test_kyc_settings_postgres import fake_provider, initiate, seed_member  # noqa: F401
from tests.integration.test_payments_postgres import in_threads, pg  # noqa: F401

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(os.getenv("RUN_POSTGRES_TESTS", "").lower() not in ("1", "true", "yes"),
                       reason="Set RUN_POSTGRES_TESTS=1 to run against a local PostgreSQL server"),
]

ROUNDS = int(os.getenv("KYC_RACE_ROUNDS", "10"))
_MEMBER_LOCK = re.compile(r"FROM users\s+WHERE users\.id = .*FOR (NO KEY )?UPDATE", re.S)
_local = threading.local()


def outcome(work):
    """What a request ended with; a database error by its SQLSTATE (40P01 = deadlock)."""
    try:
        return work()
    except DBAPIError as exc:
        return f"sqlstate:{getattr(exc.orig, 'pgcode', None)}"
    except Exception as exc:  # noqa: BLE001 - the test shows it
        return f"error:{exc!r}"


@pytest.fixture
def held_member_lock(pg):
    """`hold()` in a thread makes that thread's next start stop right after it
    locked the member's row (before the verification row) until `release` is set."""
    engine, _Session = pg
    holding, release = threading.Event(), threading.Event()

    def after(_conn, _cursor, statement, _params, _context, _many):
        if getattr(_local, "hold", False) and _MEMBER_LOCK.search(statement):
            _local.hold = False
            holding.set()
            assert release.wait(20), "the held start was never released"

    event.listen(engine, "after_cursor_execute", after)

    def hold():
        _local.hold = True

    yield holding, release, hold
    event.remove(engine, "after_cursor_execute", after)


def lock_waiter_or_done(engine, thread: threading.Thread, timeout: float = 5.0) -> bool:
    """True once a backend of the test database waits for a row lock; False if
    `thread` finished first (it was never blocked)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not thread.is_alive():
            return False
        with engine.connect() as c:
            if c.execute(text("select count(*) from pg_stat_activity where datname = current_database() "
                              "and wait_event_type = 'Lock'")).scalar():
                return True
        time.sleep(0.02)
    raise AssertionError("neither blocked nor finished")


def run(target) -> tuple:
    box: list = []
    t = threading.Thread(target=lambda: box.append(outcome(target)))
    t.start()
    return t, box


def interleave(engine, held_member_lock, start, other) -> tuple:
    """`start` locks the member and stops; `other` runs until it waits for a lock
    (or finishes); then the start goes on. Returns (start result, other result)."""
    holding, release, hold = held_member_lock
    t_start, start_box = run(lambda: (hold(), start())[1])
    assert holding.wait(10), "the start never locked the member"
    t_other, other_box = run(other)
    lock_waiter_or_done(engine, t_other)
    release.set()
    for t in (t_start, t_other):
        t.join(30)
        assert not t.is_alive(), "a transaction is still blocked"
    return start_box[0], other_box[0]


def renewable(Session, name: str, *, sessions_used: int) -> tuple:
    verification_id, reference = open_verification(Session, name)
    with Session() as db:
        row = db.get(KYCVerification, verification_id)
        row.attempt_sessions_count = sessions_used
        row.verified_address = "12 Synthetic Road, Arusha"
        db.commit()
        return verification_id, reference, row.user_id


def sessions(Session, verification_id: int) -> int:
    with Session() as db:
        return db.get(KYCVerification, verification_id).attempt_sessions_count


# ---------------------------------------------------------------------------
# The deadlock found by test_renewals_arriving_together_never_pass_the_session_limit
# ---------------------------------------------------------------------------

def test_a_renewal_holding_the_member_does_not_deadlock_the_audit_row_of_the_session_opened_before_it(
        pg, fake_provider, held_member_lock, monkeypatch):
    """Request A opened the last session and writes its audit row (foreign keys to
    the verification AND the member) while request B holds the member's lock and
    waits for the verification row."""
    engine, Session = pg
    verification_id, _reference, user_id = renewable(Session, "auditgap",
                                                     sessions_used=kyc_settings.SESSIONS_PER_ATTEMPT - 1)
    in_provider, go_on = threading.Event(), threading.Event()
    real_create = kyc_endpoint.initiate_kyc_session

    async def slow_provider(**kwargs):
        in_provider.set()
        assert go_on.wait(20)
        return await real_create(**kwargs)

    monkeypatch.setattr(kyc_endpoint, "initiate_kyc_session", slow_provider)
    t_a, a_box = run(lambda: initiate(Session, user_id, force_new=True))
    assert in_provider.wait(10)                                    # A took the last session and committed it

    def other():                                                   # A writes its session and its audit row
        go_on.set()
        t_a.join(30)
        return a_box[0]

    b, a = interleave(engine, held_member_lock, lambda: initiate(Session, user_id, force_new=True), other)
    assert (a, b) == ("new", "409:KYC_SESSION_LIMIT_REACHED")
    assert sessions(Session, verification_id) == kyc_settings.SESSIONS_PER_ATTEMPT
    assert len(fake_provider) == 1                                 # one provider session opened, by A


# ---------------------------------------------------------------------------
# A start against a provider decision on the same member
# ---------------------------------------------------------------------------

def _deliver(Session, body):
    def deliver():
        with Session() as db:
            return dispatch.handle_kaluta_webhook(db, crud_kyc=crud_kyc, payload=body, ip="203.0.113.9")
    return deliver


@pytest.mark.parametrize("make_event", [rejected, approved], ids=["rejection", "approval"])
def test_a_webhook_decision_during_a_start_waits_for_it_instead_of_deadlocking(pg, fake_provider, held_member_lock,
                                                                                make_event):
    engine, Session = pg
    verification_id, reference, user_id = renewable(Session, f"wh{make_event.__name__}", sessions_used=1)
    started, decided = interleave(engine, held_member_lock, lambda: initiate(Session, user_id, force_new=True),
                                  _deliver(Session, make_event(reference)))
    # The start was first: a new session under a new reference; the decision about
    # the session it replaced changes nothing.
    assert (started, decided) == ("new", dispatch.IGNORED)
    row, user = state(Session, verification_id)
    assert_consistent(row, user)
    assert (row.status, row.attempt_sessions_count) == (KYCStatus.IN_PROGRESS, 2)
    assert row.reference_id != reference


def test_a_polled_decision_during_a_start_waits_for_it_instead_of_deadlocking(pg, fake_provider, held_member_lock,
                                                                               monkeypatch):
    engine, Session = pg
    verification_id, _reference, user_id = renewable(Session, "pollstart", sessions_used=1)

    async def provider_says_rejected(_verification):
        return {"is_valid": True, "is_completed": True, "is_accepted": False,
                "data": {"id": "sess-1", "status": "rejected", "rejection_reason": "Blurred document"}}

    monkeypatch.setattr(dispatch, "check_kyc_session_validity", provider_says_rejected)

    def poll():
        with Session() as db:
            verification = db.get(KYCVerification, verification_id)
            return asyncio.run(dispatch.sync_verification_from_provider(db, crud_kyc=crud_kyc,
                                                                        verification=verification))

    started, polled = interleave(engine, held_member_lock, lambda: initiate(Session, user_id, force_new=True), poll)
    # The start goes first (the poll waits for the member). The poll then still applies
    # what it read about the replaced session: a separate, pre-existing question (see
    # the report); here only that both finish and the decision is whole.
    assert started == "new" and polled == {"status": "rejected"}, (started, polled)
    row, user = state(Session, verification_id)
    assert_consistent(row, user)


def test_a_session_expiry_during_a_start_waits_for_it_instead_of_deadlocking(pg, fake_provider, held_member_lock):
    engine, Session = pg
    verification_id, reference, user_id = renewable(Session, "expstart", sessions_used=1)
    started, expired = interleave(engine, held_member_lock, lambda: initiate(Session, user_id, force_new=True),
                                  _deliver(Session, payload("session.expired", reference, "expired")))
    assert (started, expired) == ("new", dispatch.IGNORED)
    with Session() as db:
        row = db.get(KYCVerification, verification_id)
        assert row.status == KYCStatus.IN_PROGRESS and row.expires_at > datetime.utcnow() + timedelta(hours=1)


# ---------------------------------------------------------------------------
# Everything at once, many rounds
# ---------------------------------------------------------------------------

def test_starts_renewals_and_provider_events_at_once_never_deadlock_or_pass_the_limit(pg, fake_provider):
    """Same member: renewals, duplicate starts, expiries and decisions together.
    Other members at the same time. No deadlock, never past the session limit,
    nobody charged, every decision whole."""
    _engine, Session = pg
    rng = random.Random(20261023)
    limit = kyc_settings.SESSIONS_PER_ATTEMPT
    for round_ in range(ROUNDS):
        verification_id, reference, user_id = renewable(Session, f"mix{round_}", sessions_used=rng.randint(0, limit - 1))
        others = [renewable(Session, f"mix{round_}o{i}", sessions_used=0)[2] for i in range(2)]
        before = sessions(Session, verification_id)
        opened_before = len(fake_provider)
        work = ([lambda: initiate(Session, user_id, force_new=True)] * 3
                + [lambda: initiate(Session, user_id)] * 2
                + [_deliver(Session, payload("session.expired", reference, "expired")),
                   _deliver(Session, rng.choice([rejected, approved])(reference))]
                + [lambda u=u: initiate(Session, u, force_new=True) for u in others])
        rng.shuffle(work)
        results = in_threads(len(work), lambda i: outcome(work[i]))
        assert not [r for r in results if isinstance(r, Exception) or str(r).startswith("sqlstate:")], results
        row, user = state(Session, verification_id)
        assert_consistent(row, user)
        own = len(fake_provider) - opened_before - len(others)
        assert row.attempt_sessions_count == before + own <= limit, (round_, before, own, results)
    with Session() as db:
        assert db.query(Deposit).count() == 0
