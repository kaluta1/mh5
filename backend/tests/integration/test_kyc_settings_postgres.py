"""KYC settings, the session limit and migration b3c4d5e6f7a8 on a real
PostgreSQL server.

Opt-in: RUN_POSTGRES_TESTS=1 (admin URL in POSTGRES_ADMIN_URL, default
postgresql://postgres@127.0.0.1:5432/postgres). Each test runs in ONE
DISPOSABLE database that is dropped afterwards. SQLite ignores row locks, so
"requests arriving together open one attempt, use one payment and never pass
the session limit" can only be proven here. Everything is SYNTHETIC; the KYC
provider is a fake and nothing leaves the process.
"""
from __future__ import annotations

import asyncio
import os
import threading
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from app.api.api_v1.endpoints import kyc as kyc_endpoint
from app.models.accounting import AuditTrail
from app.models.kyc import KYCStatus, KYCVerification, KycSettings
from app.models.payment import Deposit, DepositStatus, ProductType
from app.models.user import Permission, Role, User
from app.schemas.kyc import KYCInitiateRequest
from app.services import kyc_settings
from tests.conftest import save_kaluta_settings
from tests.integration.test_payments_postgres import in_threads, migrate, pg  # noqa: F401

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(os.getenv("RUN_POSTGRES_TESTS", "").lower() not in ("1", "true", "yes"),
                       reason="Set RUN_POSTGRES_TESTS=1 to run against a local PostgreSQL server"),
]

WORKERS = 8
MIGRATION = "b3c4d5e6f7a8_kyc_settings_and_session_limit.py"
SESSIONS_MIGRATION = "e6f7a8b9c0d1_kyc_sessions_per_attempt_setting.py"
ADDRESS = "12 Synthetic Road, Arusha"


@pytest.fixture
def fake_provider(monkeypatch, pg):
    """The provider boundary of the endpoint: every session opened is recorded.
    A small delay keeps the requests overlapping. Kaluta KYC is switched on in
    Admin > KYC (the database, its only source) with synthetic values."""
    opened, guard = [], threading.Lock()

    async def create(*, db, user, reference, **_kwargs):
        await asyncio.sleep(0.05)
        with guard:
            opened.append(reference)
            number = len(opened)
        return {"success": True, "session_id": f"sess-{number}", "verification_url": f"https://kalutakyc.com/verify/sess-{number}",
                "expires_at": (datetime.utcnow() + timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "reference": reference}

    async def validity(verification):
        return {"is_valid": bool(verification.verification_url), "is_completed": False,
                "verification_url": verification.verification_url, "data": {}}

    monkeypatch.setattr(kyc_endpoint, "initiate_kyc_session", create)
    monkeypatch.setattr(kyc_endpoint, "check_kyc_session_validity", validity)
    monkeypatch.setattr(kyc_endpoint, "_guard_kyc_initiation", lambda *_a, **_k: None)
    monkeypatch.setenv("PAYMENT_SETTINGS_ENCRYPTION_KEY", "synthetic-test-payment-settings-encryption-key")
    with pg[1]() as db:
        save_kaluta_settings(db, enabled=True)
    return opened


def seed_member(Session, name: str, *, paid: int = 1, fee: str = "10.00") -> int:
    with Session() as db:
        product = db.query(ProductType).filter(ProductType.code == "kyc").first()
        if product is None:
            product = ProductType(code="kyc", name="KYC", price=Decimal(fee), currency="USD", is_active=True)
            db.add(product)
            db.flush()
        user = User(email=f"{name}@example.com", username=name, hashed_password="x", is_active=True, is_deleted=False,
                    date_of_birth=datetime(1990, 1, 1), personal_referral_code=name.upper(), email_verified=True)
        db.add(user)
        db.flush()
        for i in range(paid):
            db.add(Deposit(user_id=user.id, product_type_id=product.id, amount=Decimal("10.00"), currency="USD",
                           order_id=f"kyc-{name}-{i}", status=DepositStatus.VALIDATED,
                           validated_at=datetime.utcnow() - timedelta(minutes=1)))
        db.commit()
        return user.id


def initiate(Session, user_id: int, *, force_new: bool = False):
    with Session() as db:
        user = db.get(User, user_id)
        try:
            answer = asyncio.run(kyc_endpoint.initiate_shufti_verification(
                db=db, current_user=user, language="en", force_new=force_new,
                payload=KYCInitiateRequest(residential_address=ADDRESS)))
            return answer["status"]
        except HTTPException as exc:
            db.rollback()
            detail = exc.detail if isinstance(exc.detail, dict) else {}
            return f"{exc.status_code}:{detail.get('code', '')}"


def test_first_requests_arriving_together_open_one_attempt_and_use_one_payment(pg, fake_provider):
    _engine, Session = pg
    user_id = seed_member(Session, "first", paid=2)                  # two payments held: only one may be used

    results = in_threads(WORKERS, lambda _i: initiate(Session, user_id))
    assert not [r for r in results if isinstance(r, Exception)], results
    with Session() as db:
        rows = db.query(KYCVerification).filter(KYCVerification.user_id == user_id).all()
        assert len(rows) == 1
        row = rows[0]
        used = db.query(Deposit).filter(Deposit.user_id == user_id, Deposit.is_used.is_(True)).count()
        assert (row.attempts_count, used) == (1, 1)                    # one attempt, one payment
        # Every provider session opened is counted, and the count never passes the limit.
        assert row.attempt_sessions_count == len(fake_provider) <= kyc_settings.SESSIONS_PER_ATTEMPT
        assert set(results) <= {"new", "in_progress", "409:KYC_SESSION_LIMIT_REACHED"}


def test_renewals_arriving_together_never_pass_the_session_limit(pg, fake_provider):
    _engine, Session = pg
    user_id = seed_member(Session, "renew", paid=0)
    with Session() as db:
        db.add(KYCVerification(user_id=user_id, status=KYCStatus.IN_PROGRESS, reference_id=f"mh5_{user_id}_old",
                               external_verification_id="sess-old", verification_url="https://kalutakyc.com/verify/sess-old",
                               attempts_count=1, attempt_sessions_count=kyc_settings.SESSIONS_PER_ATTEMPT - 1,
                               expires_at=datetime.utcnow() - timedelta(minutes=1), verified_address=ADDRESS))
        db.commit()

    results = in_threads(WORKERS, lambda _i: initiate(Session, user_id, force_new=True))
    assert not [r for r in results if isinstance(r, Exception)], results
    assert sorted(results) == ["409:KYC_SESSION_LIMIT_REACHED"] * (WORKERS - 1) + ["new"]
    assert len(fake_provider) == 1                                       # one provider session: one possible charge
    with Session() as db:
        row = db.query(KYCVerification).filter(KYCVerification.user_id == user_id).one()
        assert (row.attempts_count, row.attempt_sessions_count) == (1, kyc_settings.SESSIONS_PER_ATTEMPT)
        assert db.query(Deposit).count() == 0                           # nobody was charged


def test_free_kyc_requests_arriving_together_never_touch_a_paid_payment(pg, fake_provider):
    _engine, Session = pg
    user_id = seed_member(Session, "free", paid=1, fee="0.00")
    results = in_threads(WORKERS, lambda _i: initiate(Session, user_id))
    assert not [r for r in results if isinstance(r, Exception)], results
    with Session() as db:
        row = db.query(KYCVerification).filter(KYCVerification.user_id == user_id).one()
        assert row.attempts_count == 1
        assert db.query(Deposit).filter(Deposit.user_id == user_id).one().is_used is False


def test_administrators_allowing_a_session_at_once_allow_exactly_one(pg, monkeypatch):
    _engine, Session = pg
    user_id = seed_member(Session, "grant", paid=0)
    with Session() as db:
        row = KYCVerification(user_id=user_id, status=KYCStatus.IN_PROGRESS, reference_id=f"mh5_{user_id}_g",
                              attempts_count=1, attempt_sessions_count=kyc_settings.SESSIONS_PER_ATTEMPT,
                              expires_at=datetime.utcnow() - timedelta(minutes=1))
        db.add(row)
        db.commit()
        verification_id = row.id

    class Admin:                                                          # authorisation is covered by the unit tests
        id = None

    monkeypatch.setattr(kyc_settings, "authorize", lambda *_a, **_k: None)

    def work(_i):
        with Session() as db:
            try:
                return kyc_settings.grant_session(db, Admin(), verification_id, password="x")["attempt_sessions_granted"]
            except kyc_settings.KycSettingsError as exc:
                db.rollback()
                return exc.code

    results = in_threads(WORKERS, work)
    assert not [r for r in results if isinstance(r, Exception)], results
    assert sorted(results, key=str) == [1] + ["NOT_NEEDED"] * (WORKERS - 1)
    with Session() as db:
        assert db.get(KYCVerification, verification_id).attempt_sessions_granted == 1
        assert db.query(AuditTrail).filter(AuditTrail.action == kyc_settings.AUDIT_SESSION_GRANTED).count() == 1


def test_settings_saved_at_once_by_two_administrators_are_one_change_each_or_refused_as_stale(pg, monkeypatch):
    _engine, Session = pg
    monkeypatch.setenv("PAYMENT_SETTINGS_ENCRYPTION_KEY", "synthetic-test-payment-settings-encryption-key")
    monkeypatch.setattr(kyc_settings, "has_permission", lambda *_a, **_k: True)
    monkeypatch.setattr(kyc_settings, "authorize", lambda *_a, **_k: None)

    class Admin:
        id = None

    def work(i):
        with Session() as db:
            try:
                kyc_settings.update(db, Admin(), password="x", enabled=bool(i % 2), expected_version=0,
                                    credentials={"API_KEY": f"klt_synthetic_concurrent_key_{i:04d}",
                                                 "WEBHOOK_SECRET": f"whsec_synthetic_concurrent_{i:04d}"})
                return "saved"
            except kyc_settings.KycSettingsError as exc:
                db.rollback()
                return exc.code

    results = in_threads(WORKERS, work)
    assert not [r for r in results if isinstance(r, Exception)], results
    # The single row is created by one of them; every other one waited and found a newer version:
    # refused, so nobody's change is silently overwritten.
    assert sorted(results) == ["STALE"] * (WORKERS - 1) + ["saved"]
    with Session() as db:
        assert db.query(KycSettings).one().version == 1
        assert db.query(AuditTrail).filter(AuditTrail.action == kyc_settings.AUDIT_SETTINGS).count() == 1
        assert db.execute(text("select count(*) from payment_credentials where provider = 'kaluta'")).scalar() == 2


# ---------------------------------------------------------------------------
# b3c4d5e6f7a8
# ---------------------------------------------------------------------------

def kyc_schema(engine) -> dict:
    with engine.connect() as c:
        columns = c.execute(text(
            "select table_name, column_name, data_type, is_nullable, coalesce(column_default, '') "
            "from information_schema.columns where table_schema = 'public' and (table_name = 'kyc_settings' or "
            "(table_name = 'kyc_verifications' and column_name like 'attempt_sessions_%')) order by 1, 2")).fetchall()
        checks = c.execute(text(
            "select pg_get_constraintdef(oid) from pg_constraint where conrelid = to_regclass('public.kyc_settings') "
            "and contype in ('c', 'f') order by 1")).fetchall()
    return {"columns": [tuple(r[:4]) for r in columns],
            "defaults": [(r[1], r[4]) for r in columns if r[1] != "id"], "constraints": [r[0] for r in checks]}


def kyc_permission(engine) -> list:
    with engine.connect() as c:
        return [tuple(r) for r in c.execute(text(
            "select p.name, p.category, (select count(*) from role_permissions rp where rp.permission_id = p.id) "
            "from permissions p where p.name = 'manage_kyc_settings'")).fetchall()]


def access_and_money(engine) -> tuple:
    with engine.connect() as c:
        return (tuple(c.execute(text("select id, role_id, is_admin, is_active from users order by id")).fetchall()),
                tuple(c.execute(text("select role_id, permission_id from role_permissions order by 1, 2")).fetchall()),
                tuple(c.execute(text("select id, status, is_used, amount from deposits order by id")).fetchall()),
                tuple(c.execute(text("select id, status, attempts_count from kyc_verifications order by id")).fetchall()))


def test_the_migration_is_additive_held_by_nobody_repeatable_and_reversible(pg):
    engine, Session = pg
    user_id = seed_member(Session, "existing", paid=1)
    with Session() as db:
        db.add(KYCVerification(user_id=user_id, status=KYCStatus.IN_PROGRESS, reference_id="mh5_x", attempts_count=2))
        db.commit()
    migrate(engine, SESSIONS_MIGRATION, "downgrade")                     # the later revision first
    built = kyc_schema(engine)                                           # what the models define, up to it
    migrate(engine, MIGRATION, "downgrade")                              # the production schema before it
    assert kyc_schema(engine)["columns"] == [] and kyc_permission(engine) == []
    before = access_and_money(engine)

    for _ in range(2):                                                   # a re-run is a no-op
        migrate(engine, MIGRATION, "upgrade")
        assert kyc_schema(engine)["columns"] == built["columns"]
        assert kyc_permission(engine) == [("manage_kyc_settings", "admin", 0)]    # held by nobody
        assert access_and_money(engine) == before                        # nobody's role, no payment, no attempt
    with engine.connect() as c:
        assert c.execute(text("select count(*) from kyc_settings")).scalar() == 0                       # env decides
        assert c.execute(text("select count(*) from payment_credentials where provider = 'kaluta'")).scalar() == 0
        assert c.execute(text("select attempt_sessions_count, attempt_sessions_granted from kyc_verifications")
                         ).fetchall() == [(0, 0)]
        with pytest.raises(Exception):
            with c.begin():
                c.execute(text("insert into kyc_settings (id, version) values (2, 0)"))              # one row only

    # A downgrade keeps the permission when a role was given it.
    with Session() as db:
        permission = db.query(Permission).filter(Permission.name == "manage_kyc_settings").one()
        db.add(Role(name="kyc_manager_test", permissions=[permission]))
        db.commit()
    migrate(engine, MIGRATION, "downgrade")
    assert kyc_permission(engine) == [("manage_kyc_settings", "admin", 1)]
    assert kyc_schema(engine)["columns"] == []
    migrate(engine, MIGRATION, "upgrade")
    assert kyc_schema(engine)["columns"] == built["columns"]
    migrate(engine, SESSIONS_MIGRATION, "upgrade")


# ---------------------------------------------------------------------------
# e6f7a8b9c0d1: sessions per attempt as a setting
# ---------------------------------------------------------------------------


def kyc_settings_columns(engine) -> list:
    with engine.connect() as c:
        return [r[0] for r in c.execute(text(
            "select column_name from information_schema.columns where table_name = 'kyc_settings' order by 1"))]


def test_the_sessions_setting_migration_is_additive_repeatable_reversible_and_switches_nothing_on(pg):
    engine, Session = pg
    with Session() as db:                               # a row saved before the migration (Kaluta off)
        db.add(KycSettings(id=1, kaluta_enabled=False, version=2))
        db.commit()
    migrate(engine, SESSIONS_MIGRATION, "downgrade")
    assert "sessions_per_attempt" not in kyc_settings_columns(engine)
    for _ in range(2):
        migrate(engine, SESSIONS_MIGRATION, "upgrade")
        assert "sessions_per_attempt" in kyc_settings_columns(engine)
        with engine.connect() as c:
            assert tuple(c.execute(text("select kaluta_enabled, version, sessions_per_attempt from kyc_settings")).one()) \
                == (False, 2, None)
            assert c.execute(text("select count(*) from payment_credentials")).scalar() == 0
    with Session() as db:
        assert kyc_settings.sessions_per_attempt(db) == 3 and kyc_settings.kaluta_enabled(db) is False
    with engine.connect() as c:
        for bad in (0, 11, -1):
            with pytest.raises(Exception):
                with c.begin():
                    c.execute(text("update kyc_settings set sessions_per_attempt = :v"), {"v": bad})
        with c.begin():
            c.execute(text("update kyc_settings set sessions_per_attempt = 7"))
    with Session() as db:
        assert kyc_settings.sessions_per_attempt(db) == 7
    migrate(engine, SESSIONS_MIGRATION, "downgrade")
    assert "sessions_per_attempt" not in kyc_settings_columns(engine)
    with engine.connect() as c:
        assert tuple(c.execute(text("select kaluta_enabled, version from kyc_settings")).one()) == (False, 2)
    migrate(engine, SESSIONS_MIGRATION, "upgrade")


def test_one_save_of_every_setting_is_one_transaction_on_postgres(pg, monkeypatch):
    """A save refused at its last step (switching on without a secret) leaves
    the key, the fee and the sessions exactly as they were."""
    engine, Session = pg
    monkeypatch.setenv("PAYMENT_SETTINGS_ENCRYPTION_KEY", "synthetic-test-payment-settings-encryption-key")
    with Session() as db:
        db.add(ProductType(code="kyc", name="KYC", price=Decimal("10.00"), currency="USD", is_active=True))
        role = Role(name="kyc_settings_pg", description="test", is_system=False)
        permission = db.query(Permission).filter(Permission.name == kyc_settings.PERMISSION).first()
        if permission is None:
            permission = Permission(name=kyc_settings.PERMISSION, description="test", category="admin")
            db.add(permission)
        role.permissions.append(permission)
        db.add(role)
        db.flush()
        from app.core.security import get_password_hash

        admin = User(email="kycpg@example.com", username="kycpg", hashed_password=get_password_hash("Synthetic-Pass-123!"),
                     is_active=True, is_deleted=False, is_admin=True, role_id=role.id, personal_referral_code="KYCPG",
                     email_verified=True, date_of_birth=datetime(1990, 1, 1))
        db.add(admin)
        db.commit()
        admin_id = admin.id
    with Session() as db:
        admin = db.get(User, admin_id)
        with pytest.raises(kyc_settings.KycSettingsError) as refused:
            kyc_settings.update(db, admin, password="Synthetic-Pass-123!", enabled=True,
                                credentials={"API_KEY": "klt_pg_synthetic_key_000001"}, member_fee="20",
                                sessions="6", expected_version=0)
        assert refused.value.code == "NOT_READY"
    with engine.connect() as c:
        assert c.execute(text("select count(*) from kyc_settings")).scalar() == 0
        assert c.execute(text("select count(*) from payment_credentials")).scalar() == 0
        assert c.execute(text("select price from product_types where code = 'kyc'")).scalar() == Decimal("10.00")
        assert c.execute(text("select count(*) from audit_trails")).scalar() == 0
    with Session() as db:
        view = kyc_settings.update(db, db.get(User, admin_id), password="Synthetic-Pass-123!", member_fee="20",
                                   sessions=6, expected_version=0)
        assert (view["member_fee"]["amount"], view["sessions_per_attempt"], view["enabled"]) == ("20.00", 6, False)
