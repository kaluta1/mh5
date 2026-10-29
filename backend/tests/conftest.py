"""Shared pytest fixtures for MH5 backend."""
from __future__ import annotations

import os
import sys
from typing import Generator, Optional

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

# Force test env BEFORE any app import (dotenv must not override these).
os.environ["ENVIRONMENT"] = "test"
os.environ["USE_CELERY"] = "true"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["SECRET_KEY"] = "test-secret-key-minimum-32-characters-long"
os.environ["MASTER_ENCRYPTION_KEY"] = "test-master-encryption-key-32b!"
os.environ["ENCRYPTION_KEY_DERIVATION_SALT"] = "test-encryption-salt-value"
os.environ["KYC_PROVIDER"] = "kaluta"
# Kaluta KYC is configured only in the database (Admin > KYC): tests that need
# it on call save_kaluta_settings(). The KALUTA_* variables are ignored, and are
# cleared so a real deployment .env in the cwd cannot leak into a test.
for _name in ("KALUTA_API_KEY", "KALUTA_WEBHOOK_SECRET", "KALUTA_KYC_ENABLED"):
    os.environ[_name] = ""
# Pin deterministic to "enabled" as the test baseline so existing tests do not
# depend on whichever real deployment .env happens to be in the cwd
# (ANNUALADS_ENABLED). Individual tests may monkeypatch it false.
os.environ["ANNUALADS_ENABLED"] = "true"
os.environ.setdefault("ANNUALADS_WEBHOOK_SECRET", "annualads_test_webhook_secret")
os.environ.setdefault("ANNUALADS_SSO_SECRET", "annualads_test_sso_secret")
os.environ.setdefault("ANNUALADS_TENANT_ID", "test_tenant")
# No test may contact a real video provider: external creative link checking is
# off by default; the dead-link tests enable it with a fake HTTP layer.
os.environ["CREATIVE_LINK_CHECK_ENABLED"] = "false"
# Dedicated email encryption key (synthetic). Tests of the missing-key behaviour
# remove it explicitly.
os.environ["EMAIL_SETTINGS_ENCRYPTION_KEY"] = "synthetic-test-email-settings-encryption-key"

# SQLite compat for PostgreSQL JSONB/ARRAY — MUST run before model import.
from sqlalchemy import JSON, create_engine
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


@compiles(JSONB, "sqlite")
def _compile_jsonb_for_sqlite(_element, compiler, **_kw):  # noqa: ARG001
    return "JSON"


@compiles(ARRAY, "sqlite")
def _compile_array_for_sqlite(_element, compiler, **_kw):  # noqa: ARG001
    return "JSON"


def _patch_metadata_for_sqlite(metadata) -> None:
    for table in metadata.tables.values():
        for column in table.columns:
            col_type = column.type
            if isinstance(col_type, JSONB) or type(col_type).__name__ == "JSONB":
                column.type = JSON()
            elif isinstance(col_type, ARRAY) or type(col_type).__name__ == "ARRAY":
                column.type = JSON()

import pytest
from fastapi.testclient import TestClient

# Fail-closed guard, active in every test: nothing can be sent to the payment
# provider, and a test that tries fails (see tests/provider_network_guard.py).
from tests.provider_network_guard import _no_local_provider_credentials, provider_network  # noqa: E402,F401

import app.models  # noqa: F401 — register all models
from app.db.base_class import Base
from app.db.session import get_db

_patch_metadata_for_sqlite(Base.metadata)

TEST_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

TEST_PASSWORD = "SecurePass123!@"


@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture(autouse=True)
def _nowpayments_machinery_under_test(request, monkeypatch):
    """NOWPayments is discontinued in production (payment_config.NOWPAYMENTS_DISCONTINUED). Its code
    stays for history and reconciliation, so its tests run as if it were not; a test marked
    `discontinued` sees the production value."""
    from app.services import payment_config

    if request.node.get_closest_marker("discontinued") is None:
        monkeypatch.setattr(payment_config, "NOWPAYMENTS_DISCONTINUED", False)
    yield


@pytest.fixture(autouse=True)
def _crypto_minimum_under_test(request, monkeypatch):
    """The minimum crypto cashout is $10 (owner decision 2026-10-30). The older payout tests were written
    for the $1 rule and test other things with small commissions, so they keep it; a test marked
    `ten_dollar_minimum` sees the production default."""
    from decimal import Decimal

    from app.core.config import settings

    if request.node.get_closest_marker("ten_dollar_minimum") is None:
        monkeypatch.setattr(settings, "CRYPTO_CASHOUT_MIN_USD", Decimal("1.00"))
    yield


@pytest.fixture(autouse=True)
def _no_kyc_admin_values_between_tests():
    """Kaluta settings saved in the Admin Panel reach the shared service object;
    no test may see the values another test saved."""
    from app.services.kaluta_kyc import kaluta_kyc_service

    kaluta_kyc_service.use_settings({})
    yield
    kaluta_kyc_service.use_settings({})


TEST_PAYMENT_SETTINGS_ENCRYPTION_KEY = "synthetic-test-payment-settings-encryption-key"


def save_kaluta_settings(db: Session, *, enabled: bool = True, api_key: Optional[str] = "klt_test_key_synthetic_01",
                         webhook_secret: Optional[str] = "whsec_test_webhook_secret_01",
                         sessions_per_attempt: Optional[int] = None) -> None:
    """Kaluta KYC settings as Admin > KYC stores them (the only source): the
    kyc_settings row and the key / secret as ciphertext. Synthetic values only.
    Needs PAYMENT_SETTINGS_ENCRYPTION_KEY in the environment (kaluta_settings_key)."""
    from app.models.kyc import KycSettings
    from app.models.payment_config import PaymentCredential
    from app.services import kyc_settings, payment_crypto

    row = db.query(KycSettings).filter(KycSettings.id == kyc_settings.ROW_ID).first()
    if row is None:
        row = KycSettings(id=kyc_settings.ROW_ID, version=0)
        db.add(row)
    row.kaluta_enabled = enabled
    row.sessions_per_attempt = sessions_per_attempt
    for name, value in (("API_KEY", api_key), ("WEBHOOK_SECRET", webhook_secret)):
        stored = (db.query(PaymentCredential)
                  .filter(PaymentCredential.provider == kyc_settings.PROVIDER, PaymentCredential.name == name).first())
        if value is None:
            if stored is not None:
                db.delete(stored)
            continue
        ciphertext = payment_crypto.encrypt(value, kyc_settings._PURPOSE + name)
        if stored is None:
            db.add(PaymentCredential(provider=kyc_settings.PROVIDER, name=name, ciphertext=ciphertext))
        else:
            stored.ciphertext = ciphertext
    db.commit()


@pytest.fixture
def kaluta_settings_key(monkeypatch):
    monkeypatch.setenv("PAYMENT_SETTINGS_ENCRYPTION_KEY", TEST_PAYMENT_SETTINGS_ENCRYPTION_KEY)


@pytest.fixture(scope="function")
def db() -> Generator[Session, None, None]:
    """Provide an empty database even when endpoint code commits transactions."""
    # SQLite savepoints can be invalidated by endpoint-level commits/rollbacks.
    # Clearing rows before each test is deterministic and keeps the schema built
    # once for the session, while still exercising normal commit behaviour.
    # Some endpoint-only models are registered when the FastAPI app is first
    # imported, after the session-scoped schema setup has run.
    Base.metadata.create_all(bind=engine)
    from app.core.rate_limit import _buckets

    _buckets.clear()
    with engine.begin() as connection:
        for table in reversed(list(Base.metadata.tables.values())):
            connection.execute(table.delete())

    session = TestingSessionLocal()

    yield session

    session.rollback()
    session.close()


@pytest.fixture(scope="module")
def app():
    from main import app as fastapi_app

    return fastapi_app


@pytest.fixture
def client(app, db: Session) -> Generator[TestClient, None, None]:
    import app.db.session as session_module

    original_engine = session_module.engine
    original_session_local = session_module.SessionLocal
    session_module.engine = engine
    session_module.SessionLocal = TestingSessionLocal

    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=True) as test_client:
        yield test_client
    app.dependency_overrides.pop(get_db, None)
    session_module.engine = original_engine
    session_module.SessionLocal = original_session_local


@pytest.fixture
def test_user_data():
    import uuid

    uid = uuid.uuid4().hex[:8]
    return {
        "email": f"test_{uid}@example.com",
        "password": TEST_PASSWORD,
        "username": f"user_{uid}",
        "first_name": "Test",
        "last_name": "User",
        # Phase 3: registration requires a server-validated DOB and explicit terms
        # acceptance. Synthetic adult DOB.
        "date_of_birth": "1990-01-15",
        "accept_terms": True,
    }


def confirm_email(db: Session, email: str) -> None:
    """The member has confirmed the address (test shortcut for the emailed
    link). An account created by public registration cannot sign in before
    that. The link flow itself is covered in tests/unit/test_email2_*.py."""
    from app.models.user import User

    user = db.query(User).filter(User.email == email).one()
    user.email_verified = True
    db.commit()


@pytest.fixture
def auth_headers(client: TestClient, db: Session, test_user_data: dict) -> dict:
    reg = client.post("/api/v1/auth/register", json=test_user_data)
    assert reg.status_code == 201, reg.text
    confirm_email(db, test_user_data["email"])
    login = client.post(
        "/api/v1/auth/login",
        data={"username": test_user_data["email"], "password": test_user_data["password"]},
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


class EmailTestOutbox:
    """Emails the application queued, as a fake provider received them.

    Reading it (indexing, len, truthiness, iteration) first drains the email
    outbox through the real worker, so a test sees exactly what would have
    been sent. Items are dicts: to, subject, html, text."""

    def __init__(self, db, provider):
        self.db = db
        self.provider = provider

    def drain(self, **kwargs):
        from app.services.email_outbox import process_outbox

        return process_outbox(self.db, provider=self.provider, **kwargs)

    @property
    def messages(self):
        self.drain()
        return [{"to": m.to, "subject": m.subject, "html": m.html, "text": m.text} for m in self.provider.sent]

    def __getitem__(self, index):
        return self.messages[index]

    def __len__(self):
        return len(self.messages)

    def __bool__(self):
        return bool(self.messages)

    def __iter__(self):
        return iter(self.messages)


@pytest.fixture
def email_outbox(db: Session, monkeypatch):
    """A usable (fake) email provider: a synthetic API key, no network."""
    from app.services import email_providers

    monkeypatch.setenv("RESEND_API_KEY", "re_synthetic_test_key_not_real")
    provider = email_providers.FakeEmailProvider()
    email_providers.set_provider_factory(lambda: provider)
    try:
        yield EmailTestOutbox(db, provider)
    finally:
        email_providers.set_provider_factory(None)


def pytest_collection_modifyitems(config, items):  # noqa: ARG001
    """Auto-mark tests by directory and legacy filenames."""
    legacy_unit = (
        "test_nomination",
        "test_distribution",
        "test_founding_pool",
        "test_enrich_country",
        "test_pooled_roster",
        "test_season_pair",
        "test_nowpayments",
        "test_config_security",
    )
    legacy_integration = ("test_admin_", "test_accounting_flow")

    for item in items:
        path = str(item.fspath).replace("\\", "/")
        if "/unit/" in path:
            item.add_marker(pytest.mark.unit)
        elif "/integration/" in path:
            item.add_marker(pytest.mark.integration)
        elif "/regression/" in path:
            item.add_marker(pytest.mark.regression)
        elif "/functional/" in path:
            item.add_marker(pytest.mark.functional)
        elif "/e2e/" in path:
            item.add_marker(pytest.mark.e2e)
        elif any(name in path for name in legacy_unit):
            item.add_marker(pytest.mark.unit)
        elif any(name in path for name in legacy_integration):
            item.add_marker(pytest.mark.integration)

        if "test_accounting_flow" in path:
            item.add_marker(pytest.mark.postgres)
            item.add_marker(
                pytest.mark.skipif(
                    os.getenv("RUN_POSTGRES_TESTS", "").lower() not in ("1", "true", "yes"),
                    reason="Set RUN_POSTGRES_TESTS=1 to run against live PostgreSQL",
                )
            )
