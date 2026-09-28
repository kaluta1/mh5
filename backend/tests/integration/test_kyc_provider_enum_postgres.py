"""VerificationProvider enum contract on REAL PostgreSQL (SQLite cannot prove it).

Opt-in: RUN_POSTGRES_TESTS=1 (and optionally POSTGRES_ADMIN_URL, default
postgresql://postgres@127.0.0.1:5432/postgres). Each run creates two DISPOSABLE
databases (never an existing one), builds the model schema, puts the enum in the
pre-fix production state (labels SHUFTI_PRO, JUMIO, ONFIDO, MANUAL, 'kaluta'), and drops
both databases afterwards. No KYC provider is contacted (network transports are guarded
and provider boundaries are stubbed).
"""
from __future__ import annotations

import importlib.util
import os
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DataError
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import get_db
from app.db.base_class import Base
from app.models.kyc import KYCStatus, KYCVerification, VerificationProvider
from app.services import kaluta_kyc
from tests.unit.test_kyc_initiation_dispatch import (  # noqa: F401  (fixtures + helpers)
    ADDRESS,
    INITIATE,
    adult,
    dispatcher_spy,
    kyc_paid,
    kyc_rows,
    no_real_network,
    providers,
)
from tests.unit.test_age_gate_registration import auth

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(os.getenv("RUN_POSTGRES_TESTS", "").lower() not in ("1", "true", "yes"),
                       reason="Set RUN_POSTGRES_TESTS=1 to run against a local PostgreSQL server"),
]

ADMIN_URL = os.getenv("POSTGRES_ADMIN_URL", "postgresql://postgres@127.0.0.1:5432/postgres")
MIGRATION = Path(__file__).resolve().parents[2] / "migrations" / "versions" / "a8b9c0d1e2f3_kyc_provider_kaluta_canonical_label.py"
PRE_FIX_LABELS = ["SHUFTI_PRO", "JUMIO", "ONFIDO", "MANUAL", "kaluta"]


def _labels(engine) -> list[str]:
    with engine.connect() as c:
        return [r[0] for r in c.execute(text(
            "select e.enumlabel from pg_type t join pg_enum e on e.enumtypid = t.oid "
            "where t.typname = 'verificationprovider' order by e.enumsortorder"))]


def _run_migration(engine) -> None:
    spec = importlib.util.spec_from_file_location("mig_a8b9c0d1e2f3", MIGRATION)
    mig = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mig)
    with engine.begin() as conn:
        class _Op:
            @staticmethod
            def execute(sql):
                conn.execute(text(sql))
        mig.op = _Op()
        mig.upgrade()


def _disposable_db(pre_fix: bool):
    """Model schema on a brand-new database; optionally in the pre-fix production enum state."""
    admin = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    name = f"kyc_enum_test_{uuid.uuid4().hex[:10]}"
    with admin.connect() as c:
        c.execute(text(f'CREATE DATABASE "{name}"'))
    url = make_url(ADMIN_URL).set(database=name)
    engine = create_engine(url)
    with engine.begin() as c:  # declared create_type=False in the models (created by an old migration)
        c.execute(text("CREATE TYPE accounttype AS ENUM ('ASSET','LIABILITY','EQUITY','REVENUE','EXPENSE')"))
    Base.metadata.create_all(engine)
    if pre_fix:
        # Production contract before the fix: the model name 'KALUTA' is absent, the value 'kaluta' present.
        with engine.begin() as c:
            c.execute(text("ALTER TYPE verificationprovider RENAME VALUE 'KALUTA' TO 'kaluta'"))
        assert sorted(_labels(engine)) == sorted(PRE_FIX_LABELS)
    return admin, name, engine


def _drop(admin, name, engine):
    engine.dispose()
    with admin.connect() as c:
        c.execute(text(f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '{name}' "
                       "AND pid <> pg_backend_pid()"))
        c.execute(text(f'DROP DATABASE IF EXISTS "{name}"'))
    admin.dispose()


@pytest.fixture(scope="module")
def prefix_engine():
    admin, name, engine = _disposable_db(pre_fix=True)
    yield engine
    _drop(admin, name, engine)


@pytest.fixture(scope="module")
def fixed_engine():
    admin, name, engine = _disposable_db(pre_fix=True)
    _run_migration(engine)
    yield engine
    _drop(admin, name, engine)


def _user_id(db: Session) -> int:
    from app.models.user import User

    u = User(email=f"enum_{uuid.uuid4().hex[:8]}@example.com", hashed_password="x",
             username=f"enum_{uuid.uuid4().hex[:8]}", is_active=True)
    db.add(u)
    db.flush()
    return u.id


def _persist(engine, provider):
    with Session(engine) as db:
        row = KYCVerification(user_id=_user_id(db), status=KYCStatus.PENDING, provider=provider)
        db.add(row)
        db.flush()
        rid = row.id
        db.expire_all()
        back = db.query(KYCVerification).filter_by(id=rid).one().provider
        raw = db.execute(text("select provider::text from kyc_verifications where id = :i"), {"i": rid}).scalar()
        db.rollback()
    return back, raw


# ---------------------------------------------------------------- enum contract

def test_pre_fix_state_reproduces_the_production_error(prefix_engine):
    with pytest.raises(DataError, match='invalid input value for enum verificationprovider: "KALUTA"'):
        _persist(prefix_engine, VerificationProvider.KALUTA)


def test_E_upgrade_renames_to_one_canonical_label_and_keeps_the_others(fixed_engine):
    labels = _labels(fixed_engine)
    assert labels.count("KALUTA") == 1 and "kaluta" not in labels                       # D
    assert sorted(labels) == sorted(m.name for m in VerificationProvider)


@pytest.mark.parametrize("provider", list(VerificationProvider))
def test_A_B_C_every_provider_persists_and_reads_back_as_its_python_member(fixed_engine, provider):
    back, raw = _persist(fixed_engine, provider)
    assert back is provider and raw == provider.name


def test_G_rerunning_the_migration_is_a_no_op(fixed_engine):
    before = _labels(fixed_engine)
    _run_migration(fixed_engine)
    assert _labels(fixed_engine) == before


def test_F_fresh_model_schema_already_matches_and_the_migration_leaves_it_alone():
    admin, name, engine = _disposable_db(pre_fix=False)
    try:
        fresh = _labels(engine)
        _run_migration(engine)
        assert _labels(engine) == fresh and "kaluta" not in fresh and fresh.count("KALUTA") == 1
        back, raw = _persist(engine, VerificationProvider.KALUTA)
        assert back is VerificationProvider.KALUTA and raw == "KALUTA"
    finally:
        _drop(admin, name, engine)


def test_existing_lowercase_row_is_preserved_and_becomes_readable():
    """A row written as 'kaluta' before the fix (raw SQL) keeps its identity: RENAME VALUE is in place."""
    admin, name, engine = _disposable_db(pre_fix=True)
    try:
        with Session(engine) as db:
            uid = _user_id(db)
            db.commit()
        with engine.begin() as c:
            c.execute(text("insert into kyc_verifications (user_id, status, provider, attempts_count, max_attempts, "
                           "identity_verified, address_verified, document_verified, face_verified, submitted_at, "
                           "created_at, updated_at) values (:u, 'PENDING', 'kaluta', 0, 3, false, false, false, "
                           "false, now(), now(), now())"), {"u": uid})
        _run_migration(engine)
        with Session(engine) as db:
            row = db.query(KYCVerification).filter_by(user_id=uid).one()
            assert row.provider is VerificationProvider.KALUTA
    finally:
        _drop(admin, name, engine)


# ---------------------------------------------------------------- mounted /kyc/initiate on PostgreSQL

def _client(app, engine):
    import app.db.session as session_module

    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = session_factory()
    original = (session_module.engine, session_module.SessionLocal)
    session_module.engine, session_module.SessionLocal = engine, session_factory

    def override():
        yield db

    app.dependency_overrides[get_db] = override
    client = TestClient(app, raise_server_exceptions=False)

    def close():
        app.dependency_overrides.pop(get_db, None)
        session_module.engine, session_module.SessionLocal = original
        db.rollback()
        db.close()

    return client, db, close


def test_pre_fix_database_turns_disabled_kaluta_into_a_500(app, prefix_engine, monkeypatch):
    """The production symptom, reproduced through the mounted route (contrast for I)."""
    monkeypatch.setattr(kaluta_kyc.kaluta_kyc_service, "enabled", False)
    client, db, close = _client(app, prefix_engine)
    try:
        a = adult(db)
        kyc_paid(db, a)
        with client:
            r = client.post(INITIATE, json=ADDRESS, headers=auth(a))
        assert r.status_code == 500
    finally:
        close()


def test_I_disabled_kaluta_reaches_the_intended_503_without_network_or_db_error(app, fixed_engine, monkeypatch):
    monkeypatch.setattr(kaluta_kyc.kaluta_kyc_service, "enabled", False)  # the default (KALUTA_KYC_ENABLED off)
    client, db, close = _client(app, fixed_engine)
    try:
        a = adult(db)
        kyc_paid(db, a)
        with client:
            r = client.post(INITIATE, json=ADDRESS, headers=auth(a))
        assert r.status_code == 503 and "disabled" in r.text
        row = kyc_rows(db, a)[0]
        assert row.provider is VerificationProvider.KALUTA and row.status == KYCStatus.PENDING
        assert not row.identity_verified and not row.verification_url
    finally:
        close()


def test_H_K_kaluta_selected_persists_kaluta_and_passes_the_live_session(app, fixed_engine, providers, dispatcher_spy):
    client, db, close = _client(app, fixed_engine)
    try:
        a = adult(db)
        kyc_paid(db, a)
        with client:
            r = client.post(INITIATE, json=ADDRESS, headers=auth(a))
        assert r.status_code == 200, r.text
        assert r.json()["provider"] == "kaluta" and len(providers["kaluta"]) == 1 and providers["shufti"] == []
        assert dispatcher_spy[0]["db"] is db                                               # K: db=db intact
        db.expire_all()
        assert kyc_rows(db, a)[0].provider is VerificationProvider.KALUTA
    finally:
        close()


def test_J_shufti_path_unchanged_on_postgres(app, fixed_engine, providers, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "KYC_PROVIDER", "shufti_pro")
    client, db, close = _client(app, fixed_engine)
    try:
        a = adult(db)
        kyc_paid(db, a)
        with client:
            r = client.post(INITIATE, json=ADDRESS, headers=auth(a))
        assert r.status_code == 200 and r.json()["provider"] == "shufti_pro"
        assert len(providers["shufti"]) == 1 and providers["kaluta"] == []
        assert kyc_rows(db, a)[0].provider is VerificationProvider.SHUFTI_PRO
    finally:
        close()
