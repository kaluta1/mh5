"""Shared pytest fixtures for MH5 backend."""
from __future__ import annotations

import os
import sys
from typing import Generator

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
os.environ["KALUTA_API_KEY"] = "klt_test_key"
os.environ["KALUTA_WEBHOOK_SECRET"] = "whsec_test_webhook_secret"

# SQLite compat for PostgreSQL JSONB/ARRAY — MUST run before model import.
from sqlalchemy import JSON, create_engine, event
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


@pytest.fixture(scope="function")
def db() -> Generator[Session, None, None]:
    """DB session with SAVEPOINT so API commits roll back after each test."""
    connection = engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)
    connection.begin_nested()

    @event.listens_for(session, "after_transaction_end")
    def restart_savepoint(sess, trans):  # noqa: ARG001
        if connection.in_transaction() and not connection.in_nested_transaction():
            connection.begin_nested()

    yield session

    session.close()
    transaction.rollback()
    connection.close()


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
    with TestClient(app, raise_server_exceptions=False) as test_client:
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
    }


@pytest.fixture
def auth_headers(client: TestClient, test_user_data: dict) -> dict:
    reg = client.post("/api/v1/auth/register", json=test_user_data)
    assert reg.status_code == 201, reg.text
    login = client.post(
        "/api/v1/auth/login",
        data={"username": test_user_data["email"], "password": test_user_data["password"]},
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


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
