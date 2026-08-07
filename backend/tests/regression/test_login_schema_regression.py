"""Regression tests for login 503 / schema drift issues."""
import pytest
from sqlalchemy import inspect

from app.models.user import User


pytestmark = pytest.mark.regression


def test_user_wallet_columns_exist_on_model():
    col_names = {c.key for c in User.__table__.columns}
    assert "usdt_wallet_address" in col_names
    assert "payout_currency" in col_names


def test_wallet_columns_are_deferred():
    """Login must not SELECT wallet columns until migration is applied in prod."""
    user_mapper = inspect(User)
    assert user_mapper.attrs.usdt_wallet_address.deferred is True
    assert user_mapper.attrs.payout_currency.deferred is True


def test_sqlite_test_db_has_wallet_columns(db):
    insp = inspect(db.get_bind())
    db_cols = {c["name"] for c in insp.get_columns("users")}
    assert "usdt_wallet_address" in db_cols
    assert "payout_currency" in db_cols


def test_health_db_schema_reports_ok(client):
    """Regression: prod login 503 when columns missing — health must detect it."""
    resp = client.get("/api/v1/health/db-schema")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["missing_users_columns"] == []
