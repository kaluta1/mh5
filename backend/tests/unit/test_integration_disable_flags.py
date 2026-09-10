"""Tests for KALUTA_KYC_ENABLED / ANNUALADS_ENABLED fail-closed disable flags."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from unittest.mock import patch

from app.core.config import settings
from app.services.kaluta_kyc import KalutaKYCService

pytestmark = pytest.mark.unit

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _enabled_flags_in_fresh_process(overrides: dict[str, str | None]) -> dict[str, bool]:
    """Import app.core.config fresh in an isolated subprocess with a controlled
    environment, to test the real os.getenv(...) default-parsing behavior for
    KALUTA_KYC_ENABLED/ANNUALADS_ENABLED without disturbing the shared
    `settings` singleton this process's other tests already depend on
    (module-level Settings() defaults are baked in once at import time --
    monkeypatching os.environ in-process would not re-evaluate them, and
    importlib.reload would replace the singleton other already-imported
    modules still reference). `overrides[name] = None` means "ensure unset";
    a string value means "set to exactly this"."""
    env = os.environ.copy()
    for name, value in overrides.items():
        if value is None:
            env.pop(name, None)
        else:
            env[name] = value
    code = (
        "import json\n"
        "from app.core.config import settings\n"
        "print(json.dumps({'kaluta': settings.KALUTA_KYC_ENABLED, "
        "'annualads': settings.ANNUALADS_ENABLED}))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(BACKEND_DIR),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    assert result.returncode == 0, f"subprocess failed: {result.stderr}"
    return json.loads(result.stdout.strip().splitlines()[-1])


# 1 & 2. Both flags missing entirely from the environment -> both default False
def test_both_enabled_flags_default_false_when_env_missing():
    flags = _enabled_flags_in_fresh_process(
        {"KALUTA_KYC_ENABLED": None, "ANNUALADS_ENABLED": None}
    )
    assert flags["kaluta"] is False
    assert flags["annualads"] is False


# 3 & 4. Explicit "true" override -> enabled
def test_both_enabled_flags_true_when_env_explicitly_true():
    flags = _enabled_flags_in_fresh_process(
        {"KALUTA_KYC_ENABLED": "true", "ANNUALADS_ENABLED": "true"}
    )
    assert flags["kaluta"] is True
    assert flags["annualads"] is True


# 5. Explicit "false" override -> stays disabled (not just "happens to be" disabled)
def test_both_enabled_flags_false_when_env_explicitly_false():
    flags = _enabled_flags_in_fresh_process(
        {"KALUTA_KYC_ENABLED": "false", "ANNUALADS_ENABLED": "false"}
    )
    assert flags["kaluta"] is False
    assert flags["annualads"] is False


# 6. THE actual future-deployment scenario this whole change exists to prevent:
# a fresh release's .env carries the existing URL-shaped webhook secrets forward
# but has neither _ENABLED flag at all. With the fail-safe default, both must
# resolve to disabled and startup must succeed -- proven end-to-end in a real
# fresh process, not simulated via monkeypatch.
def test_startup_succeeds_when_enabled_flags_missing_even_with_url_shaped_secrets():
    env = os.environ.copy()
    env.pop("KALUTA_KYC_ENABLED", None)
    env.pop("ANNUALADS_ENABLED", None)
    env.update(
        {
            "ENVIRONMENT": "production",
            "BACKEND_CORS_ORIGINS": "https://kalutasociety.com",
            "SECRET_KEY": "test-secret-key-minimum-32-characters-long",
            "MASTER_ENCRYPTION_KEY": "test-master-encryption-key-32b!",
            "ENCRYPTION_KEY_DERIVATION_SALT": "test-salt",
            "FRONTEND_URL": "https://kalutasociety.com",
            "BACKEND_PUBLIC_URL": "https://kalutasociety.com",
            "KYC_PROVIDER": "kaluta",
            "SHUFTI_CLIENT_ID": "shufti_client",
            "SHUFTI_SECRET_KEY": "shufti_secret",
            "NOWPAYMENTS_API_KEY": "np_key",
            "NOWPAYMENTS_IPN_SECRET": "np_ipn_secret",
            "NOWPAYMENTS_SANDBOX": "false",
            "KALUTA_API_KEY": "klt_test_key",
            # The exact real-world condition: secrets present but URL-shaped,
            # carried forward from an old .env, with no _ENABLED override at all.
            "KALUTA_WEBHOOK_SECRET": "https://example.com/webhook/kaluta",
            "ANNUALADS_WEBHOOK_SECRET": "https://api.annualads.example/webhook",
        }
    )
    code = (
        "from main import validate_critical_settings\n"
        "from app.core.config import settings\n"
        "assert settings.KALUTA_KYC_ENABLED is False\n"
        "assert settings.ANNUALADS_ENABLED is False\n"
        "validate_critical_settings()\n"
        "print('OK')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(BACKEND_DIR),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    assert result.returncode == 0, f"startup validation raised unexpectedly: {result.stderr}"
    assert "OK" in result.stdout


# 7. The other side of the same coin: if either integration IS explicitly
# enabled, a URL-shaped secret must still fail startup -- the fail-safe default
# must never weaken the enabled-path validation. (Already directly exercised by
# test_kaluta_enabled_invalid_secret_fails_startup /
# test_annualads_enabled_invalid_secret_fails_startup above via monkeypatch;
# this variant proves it end-to-end through the same fresh-process path used
# for the missing-flag case, for a like-for-like comparison.)
def test_startup_still_fails_when_enabled_explicitly_with_url_shaped_secret():
    env = os.environ.copy()
    env.update(
        {
            "ENVIRONMENT": "production",
            "BACKEND_CORS_ORIGINS": "https://kalutasociety.com",
            "SECRET_KEY": "test-secret-key-minimum-32-characters-long",
            "MASTER_ENCRYPTION_KEY": "test-master-encryption-key-32b!",
            "ENCRYPTION_KEY_DERIVATION_SALT": "test-salt",
            "FRONTEND_URL": "https://kalutasociety.com",
            "BACKEND_PUBLIC_URL": "https://kalutasociety.com",
            "KYC_PROVIDER": "kaluta",
            "SHUFTI_CLIENT_ID": "shufti_client",
            "SHUFTI_SECRET_KEY": "shufti_secret",
            "NOWPAYMENTS_API_KEY": "np_key",
            "NOWPAYMENTS_IPN_SECRET": "np_ipn_secret",
            "NOWPAYMENTS_SANDBOX": "false",
            "KALUTA_API_KEY": "klt_test_key",
            "KALUTA_KYC_ENABLED": "true",
            "ANNUALADS_ENABLED": "true",
            "KALUTA_WEBHOOK_SECRET": "https://example.com/webhook/kaluta",
            "ANNUALADS_WEBHOOK_SECRET": "https://api.annualads.example/webhook",
        }
    )
    code = (
        "from main import validate_critical_settings\n"
        "validate_critical_settings()\n"
        "print('SHOULD NOT REACH HERE')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(BACKEND_DIR),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    assert result.returncode != 0
    assert "Missing required critical secrets" in result.stderr


def _valid_production_baseline(monkeypatch):
    """Set every OTHER critical setting to a passing value, so a test's assertion
    isolates specifically on the Kaluta/AnnualAds behavior under test."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("BACKEND_CORS_ORIGINS", "https://kalutasociety.com")
    monkeypatch.setattr(settings, "SECRET_KEY", "test-secret-key-minimum-32-characters-long")
    monkeypatch.setattr(settings, "MASTER_ENCRYPTION_KEY", "test-master-encryption-key-32b!")
    monkeypatch.setattr(settings, "ENCRYPTION_KEY_DERIVATION_SALT", "test-salt")
    monkeypatch.setattr(settings, "ALGORITHM", "HS256")
    monkeypatch.setattr(settings, "FRONTEND_URL", "https://kalutasociety.com")
    monkeypatch.setattr(settings, "BACKEND_PUBLIC_URL", "https://kalutasociety.com")
    monkeypatch.setattr(settings, "KYC_PROVIDER", "kaluta")
    monkeypatch.setattr(settings, "SHUFTI_CLIENT_ID", "shufti_client")
    monkeypatch.setattr(settings, "SHUFTI_SECRET_KEY", "shufti_secret")
    monkeypatch.setattr(settings, "NOWPAYMENTS_API_KEY", "np_key")
    monkeypatch.setattr(settings, "NOWPAYMENTS_IPN_SECRET", "np_ipn_secret")
    monkeypatch.setattr(settings, "KALUTA_API_KEY", "klt_test_key")
    monkeypatch.setattr(settings, "KALUTA_WEBHOOK_SECRET", "whsec_valid_kaluta_secret")
    monkeypatch.setattr(settings, "KALUTA_KYC_ENABLED", True)
    monkeypatch.setattr(settings, "ANNUALADS_WEBHOOK_SECRET", "annualads_valid_secret")
    monkeypatch.setattr(settings, "ANNUALADS_ENABLED", True)


# 1. Kaluta enabled + invalid (URL-shaped) secret => startup validation fails
def test_kaluta_enabled_invalid_secret_fails_startup(monkeypatch):
    from main import validate_critical_settings

    _valid_production_baseline(monkeypatch)
    monkeypatch.setattr(settings, "KALUTA_KYC_ENABLED", True)
    monkeypatch.setattr(settings, "KALUTA_WEBHOOK_SECRET", "https://example.com/webhook/kaluta")

    with pytest.raises(RuntimeError, match="Missing required critical secrets"):
        validate_critical_settings()


# 2. Kaluta disabled + invalid/missing secret => main application can start
def test_kaluta_disabled_invalid_secret_allows_startup(monkeypatch):
    from main import validate_critical_settings

    _valid_production_baseline(monkeypatch)
    monkeypatch.setattr(settings, "KALUTA_KYC_ENABLED", False)
    monkeypatch.setattr(settings, "KALUTA_WEBHOOK_SECRET", "https://example.com/webhook/kaluta")
    monkeypatch.setattr(settings, "KALUTA_API_KEY", "")

    validate_critical_settings()  # must not raise


# 5. AnnualAds enabled + invalid (URL-shaped) secret => startup validation fails
def test_annualads_enabled_invalid_secret_fails_startup(monkeypatch):
    from main import validate_critical_settings

    _valid_production_baseline(monkeypatch)
    monkeypatch.setattr(settings, "ANNUALADS_ENABLED", True)
    monkeypatch.setattr(settings, "ANNUALADS_WEBHOOK_SECRET", "https://api.annualads.example/webhook")

    with pytest.raises(RuntimeError, match="Missing required critical secrets"):
        validate_critical_settings()


# 6. AnnualAds disabled + invalid/missing secret => main application can start
def test_annualads_disabled_invalid_secret_allows_startup(monkeypatch):
    from main import validate_critical_settings

    _valid_production_baseline(monkeypatch)
    monkeypatch.setattr(settings, "ANNUALADS_ENABLED", False)
    monkeypatch.setattr(settings, "ANNUALADS_WEBHOOK_SECRET", "https://api.annualads.example/webhook")

    validate_critical_settings()  # must not raise


# both disabled simultaneously should also allow startup (matches actual deployment config)
def test_both_disabled_together_allows_startup(monkeypatch):
    from main import validate_critical_settings

    _valid_production_baseline(monkeypatch)
    monkeypatch.setattr(settings, "KALUTA_KYC_ENABLED", False)
    monkeypatch.setattr(settings, "KALUTA_WEBHOOK_SECRET", "https://example.com/webhook/kaluta")
    monkeypatch.setattr(settings, "ANNUALADS_ENABLED", False)
    monkeypatch.setattr(settings, "ANNUALADS_WEBHOOK_SECRET", "https://api.annualads.example/webhook")

    validate_critical_settings()  # must not raise


# 3. Disabled Kaluta webhook => no mutation (returns 503, verification untouched)
def test_kaluta_webhook_disabled_returns_503_no_mutation(client, monkeypatch, db):
    monkeypatch.setattr(settings, "KALUTA_KYC_ENABLED", False)
    from app.crud import crud_kyc

    before_count = len(crud_kyc.kyc_verification.get_multi(db))

    resp = client.post(
        "/api/v1/kyc/webhook/kaluta",
        content=b'{"event":"session.approved","session":{"external_id":"mh5_1_fake","id":"sess_1"}}',
        headers={"X-Kaluta-Signature": "t=1,v1=deadbeef"},
    )
    assert resp.status_code == 503

    after_count = len(crud_kyc.kyc_verification.get_multi(db))
    assert after_count == before_count


# 7. Disabled AnnualAds webhook => no mutation (returns 503, no journal entry created)
def test_annualads_webhook_disabled_returns_503_no_mutation(client, monkeypatch, db):
    monkeypatch.setattr(settings, "ANNUALADS_ENABLED", False)
    from app.models.accounting import JournalEntry

    before_count = db.query(JournalEntry).count()

    resp = client.post(
        "/api/v1/webhooks/sponsor-payment",
        content=b'{"event":"sponsor_payment_confirmed","payment":{"amount":"100","tx_hash":"abc123"}}',
        headers={
            "X-Webhook-Signature": "deadbeef",
            "X-Webhook-Timestamp": "9999999999",
            "X-Webhook-Event": "sponsor_payment_confirmed",
        },
    )
    assert resp.status_code == 503

    after_count = db.query(JournalEntry).count()
    assert after_count == before_count


# 4. Disabled Kaluta outbound action => no provider call
async def test_kaluta_disabled_create_session_makes_no_provider_call(monkeypatch):
    svc = KalutaKYCService()
    svc.enabled = False
    svc.api_key = "klt_test_key"

    with patch("app.services.kaluta_kyc.httpx.AsyncClient") as mock_client_cls:
        class _FakeUser:
            id = 1
            first_name = "Test"
            last_name = "User"
            date_of_birth = None

        result = await svc.create_session(external_id="ref1", user=_FakeUser())

    assert result["success"] is False
    assert "disabled" in result["error"].lower()
    mock_client_cls.assert_not_called()


async def test_kaluta_disabled_check_reference_validity_makes_no_provider_call(monkeypatch):
    svc = KalutaKYCService()
    svc.enabled = False

    class _FakeVerification:
        external_verification_id = "sess_123"
        verification_url = None

    with patch("app.services.kaluta_kyc.httpx.AsyncClient") as mock_client_cls:
        result = await svc.check_reference_validity(_FakeVerification())

    assert result["is_valid"] is False
    assert result["is_completed"] is False
    mock_client_cls.assert_not_called()


def test_kaluta_disabled_webhook_signature_always_rejected():
    svc = KalutaKYCService()
    svc.enabled = False
    svc.webhook_secret = "whsec_valid"
    # Even a well-formed signature must be rejected outright when disabled —
    # disabled must never fall through to "accept because dev bypass" logic.
    assert svc.verify_webhook_signature(b"{}", "t=1,v1=anything") is False


# 8. Disabled AnnualAds outbound action (SSO token issuance) => no token issued, no provider-facing action
def test_annualads_disabled_sso_token_blocked(client, monkeypatch, auth_headers):
    monkeypatch.setattr(settings, "ANNUALADS_ENABLED", False)
    resp = client.get("/api/v1/sponsor-embed/sso-token", headers=auth_headers)
    assert resp.status_code == 503
