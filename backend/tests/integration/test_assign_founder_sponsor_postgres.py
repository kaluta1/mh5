"""The one-time founder sponsor assignment (owner rule 2026-10-26), on a real PostgreSQL server (opt-in
RUN_POSTGRES_TESTS=1; one DISPOSABLE database per test; SYNTHETIC).

Proved: only genuinely sponsorless, active, plain pre-existing members are placed under the founder;
existing sponsors, DSM-imported and DSM-unresolved accounts, staff, the founder's own upline (a cycle)
and members registered after the cut-off are left exactly as they are; every change has an audit row
with the previous value; a second run changes nothing; a founder without an eligible ACTIVE unit
changes nothing at all.
"""
from __future__ import annotations

import os
from datetime import datetime

import pytest
from sqlalchemy import text

from app.models.accounting import AuditTrail
from app.models.user import User
from app.scripts import assign_founder_sponsor as script
from tests.integration.test_payments_postgres import pg  # noqa: F401
from tests.integration.test_referral_pool_allocation_postgres import holder, sponsor_of  # noqa: F401
from tests.integration.test_referral_pool_units_postgres import NOW, member, world  # noqa: F401

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(os.getenv("RUN_POSTGRES_TESTS", "").lower() not in ("1", "true", "yes"),
                       reason="Set RUN_POSTGRES_TESTS=1 to run against a local PostgreSQL server"),
]

CUTOFF = datetime(2030, 1, 1)
NEVER = "(?!x)x"
REAL_TEST_ACCOUNT_RE = script.TEST_ACCOUNT_RE


@pytest.fixture(autouse=True)
def synthetic_addresses_are_not_test_accounts(monkeypatch):
    """The synthetic members use @example.com; the test-account rule is proved on its own below."""
    monkeypatch.setattr(script, "TEST_ACCOUNT_RE", NEVER)


def username(Session, user_id: int) -> str:
    with Session() as db:
        return db.get(User, user_id).username


def edit(Session, user_id: int, **values) -> None:
    with Session() as db:
        u = db.get(User, user_id)
        for k, v in values.items():
            setattr(u, k, v)
        db.commit()


def run(Session, founder: int, *, before: datetime = CUTOFF) -> dict:
    with Session() as db:
        result = script.run(db, username(Session, founder), before, run_id="T1", actor_id=None, now=NOW)
        db.commit()
        return result


def test_only_genuinely_sponsorless_pre_existing_members_go_under_the_founder(world):
    _e, Session = world
    founder = holder(Session, 1)
    root = member(Session)                                     # the founder's own sponsor: a cycle if moved
    edit(Session, founder, sponsor_id=root, sponsor_source="PERSONAL_REFERRAL")
    plain, other_plain = member(Session), member(Session)
    sponsored = member(Session)
    edit(Session, sponsored, sponsor_id=plain, sponsor_source="DSM_IMPORT")
    imported, ambiguous = member(Session), member(Session)
    staff, gone, late = member(Session), member(Session), member(Session)
    edit(Session, staff, is_admin=True)
    edit(Session, gone, is_deleted=True)
    with Session() as db:
        db.execute(text("CREATE SCHEMA legacy_import"))
        db.execute(text("CREATE TABLE legacy_import.dsm_members (dsm_id int PRIMARY KEY, mh5_user_id int, "
                        "email_norm text NOT NULL, import_status text NOT NULL)"))
        db.execute(text("INSERT INTO legacy_import.dsm_members VALUES (1, :i, 'x@dsm', 'CREATED'), "
                        "(2, NULL, lower(:e), 'REVIEW_AMBIGUOUS_EMAIL')"),
                   {"i": imported, "e": db.get(User, ambiguous).email.upper()})
        late_at = db.get(User, late).created_at
        db.commit()
    result = run(Session, founder, before=late_at)

    assert result["assigned_ids"] == [plain, other_plain]
    assert sponsor_of(Session, plain) == (founder, "FOUNDER_ASSIGNED")
    assert sponsor_of(Session, sponsored) == (plain, "DSM_IMPORT")
    for untouched in (root, imported, ambiguous, staff, gone, late):
        assert sponsor_of(Session, untouched)[0] is None, untouched
    assert result["sponsorless_by_outcome"]["FOUNDER_UPLINE"] == 1
    assert result["sponsorless_by_outcome"]["DSM_IMPORT_OR_UNRESOLVED"] == 2
    with Session() as db:
        audits = db.query(AuditTrail).filter_by(action=script.AUDIT_ACTION).order_by(AuditTrail.record_id).all()
        assert [a.record_id for a in audits] == [plain, other_plain]
        assert audits[0].old_values["sponsor_id"] is None
        assert audits[0].new_values["sponsor_id"] == founder and audits[0].new_values["reason"] == script.REASON

    again = run(Session, founder, before=late_at)              # one time: nothing left to do
    assert again["assigned"] == 0


def test_a_founder_without_an_eligible_active_unit_changes_nothing(world):
    _e, Session = world
    founder = member(Session)                                  # KYC-approved, no unit
    waiting = member(Session)
    with Session() as db, pytest.raises(script.Refused):
        script.run(db, username(Session, founder), CUTOFF, run_id="T2")
    assert sponsor_of(Session, waiting)[0] is None


def test_only_the_reviewed_ids_change_and_every_rule_still_applies(world):
    _e, Session = world
    founder = holder(Session, 1)
    legit, doubtful, sponsored = member(Session), member(Session), member(Session)
    edit(Session, sponsored, sponsor_id=doubtful, sponsor_source="PERSONAL_REFERRAL")
    with Session() as db:
        result = script.run(db, username(Session, founder), CUTOFF, run_id="T3", now=NOW,
                            only_ids=[legit, sponsored, founder])
        db.commit()
    assert result["assigned_ids"] == [legit] and doubtful in result["not_selected"]
    assert sponsor_of(Session, legit) == (founder, "FOUNDER_ASSIGNED")
    assert sponsor_of(Session, doubtful)[0] is None
    assert sponsor_of(Session, sponsored) == (doubtful, "PERSONAL_REFERRAL")


def test_risk_ambiguous_test_and_waiting_accounts_are_excluded_and_the_dry_run_writes_nothing(world, monkeypatch):
    _e, Session = world
    founder = holder(Session, 1)
    ok, risky, dup_a, dup_b, tester, waiting = (member(Session) for _ in range(6))
    with Session() as db:
        db.get(User, dup_b).email = db.get(User, dup_a).email.upper()        # same address, other case
        db.get(User, tester).username = "probe_account"
        from app.models.business_model import ReferralPoolPending, ReferralPoolRiskReview

        db.add(ReferralPoolRiskReview(user_id=risky, signal="DUPLICATE_KYC_IDENTITY", evidence_hash="h" * 64,
                                      blocking=True, status="OPEN"))
        db.add(ReferralPoolPending(referred_user_id=waiting, status="WAITING", enqueued_at=NOW))
        db.commit()
    monkeypatch.setattr(script, "TEST_ACCOUNT_RE", r"(^|[._+-])(test|probe)([0-9._+-]|@|$)")

    with Session() as db:                                       # DRY RUN: read-only, nothing written
        db.execute(text("SET TRANSACTION READ ONLY"))
        dry = script.run(db, username(Session, founder), CUTOFF, run_id="DRY", now=NOW, apply=False)
        db.rollback()
    assert dry["applied"] is False and dry["assigned_ids"] == [ok]
    assert dry["eligible_detail"][0]["id"] == ok and "username" in dry["eligible_detail"][0]
    assert dry["excluded_ids"] == {"FOUNDER": [founder], "RISK_REVIEW": [risky], "AMBIGUOUS_EMAIL": [dup_a, dup_b],
                                   "LIKELY_TEST": [tester], "POOL_WAITING": [waiting]}
    assert sponsor_of(Session, ok)[0] is None
    with Session() as db:
        assert db.query(AuditTrail).filter_by(action=script.AUDIT_ACTION).count() == 0

    applied = run(Session, founder)
    assert applied["assigned_ids"] == [ok]
    for untouched in (risky, dup_a, dup_b, tester, waiting):
        assert sponsor_of(Session, untouched)[0] is None, untouched


def test_the_test_account_pattern():
    import re

    rx = re.compile(REAL_TEST_ACCOUNT_RE, re.I)
    for name in ("test1", "probe-x", "qa_user", "demo", "john@example.com", "a@b.test", "x.test@gmail.com"):
        assert rx.search(name), name
    for name in ("mlenzi123", "latest99", "contest_fan", "protester", "anna@gmail.com", "testimony"):
        assert not rx.search(name), name
