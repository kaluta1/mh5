"""Unit tests for Kaluta KYC helpers."""
import hashlib
import hmac
import json
import time

import pytest

from app.services import kaluta_kyc as kaluta_module
from app.services.kaluta_kyc import (
    KalutaKYCService,
    kyc_flags_from_kaluta_session,
    active_kyc_provider,
)


pytestmark = pytest.mark.unit


def test_kyc_flags_approved_session():
    flags = kyc_flags_from_kaluta_session({"status": "approved", "checks_required": {}})
    assert flags["identity_verified"] is True
    assert flags["document_verified"] is True
    assert flags["face_verified"] is True


def test_kyc_flags_with_poa_required():
    flags = kyc_flags_from_kaluta_session(
        {
            "status": "approved",
            "checks_required": {"proof_of_address": True},
            "scores": {"document": 80, "face": 80, "poa": 70},
        }
    )
    assert flags["kaluta_poa_complete"] is True
    assert flags["address_verified"] is True


def test_generate_reference_format():
    svc = KalutaKYCService()
    ref = svc.generate_reference(99)
    assert ref.startswith("mh5_99_")


def test_the_service_is_off_with_no_key_or_secret_until_settings_are_applied():
    svc = KalutaKYCService()
    assert (svc.enabled, svc.api_key, svc.webhook_secret, svc.configured()) == (False, "", "", False)
    svc.use_settings({"enabled": True, "api_key": "k" * 20, "webhook_secret": "s" * 20})
    assert svc.configured() is True
    svc.use_settings({})                     # replaced, never merged: absent = off / not set
    assert (svc.enabled, svc.api_key, svc.webhook_secret) == (False, "", "")


@pytest.mark.parametrize("environment", ["development", "dev", "local", "test", "production", ""])
def test_a_webhook_is_never_accepted_unsigned_without_a_saved_secret(monkeypatch, environment):
    monkeypatch.setenv("ENVIRONMENT", environment)
    svc = KalutaKYCService()
    svc.use_settings({"enabled": True, "api_key": "k" * 20})
    assert svc.verify_webhook_signature(b"{}", "") is False
    assert svc.verify_webhook_signature(b"{}", "t=1,v1=00") is False


def test_webhook_signature_valid():
    svc = KalutaKYCService()
    svc.enabled = True
    svc.webhook_secret = "test-secret"
    body = b'{"event":"session.approved"}'
    ts = str(int(time.time()))          # the real epoch, as the provider sends it
    signed = f"{ts}.".encode() + body
    sig = hmac.new(b"test-secret", signed, hashlib.sha256).hexdigest()
    header = f"t={ts},v1={sig}"
    assert svc.verify_webhook_signature(body, header) is True


def test_webhook_signature_rejects_tampered_body():
    svc = KalutaKYCService()
    svc.enabled = True
    svc.webhook_secret = "test-secret"
    body = b'{"event":"session.approved"}'
    ts = str(int(time.time()))          # the real epoch, as the provider sends it
    signed = f"{ts}.".encode() + body
    sig = hmac.new(b"test-secret", signed, hashlib.sha256).hexdigest()
    header = f"t={ts},v1={sig}"
    assert svc.verify_webhook_signature(b'{"event":"session.rejected"}', header) is False


def test_active_kyc_provider_defaults_kaluta(monkeypatch):
    monkeypatch.setattr(kaluta_module.settings, "KYC_PROVIDER", "kaluta")
    assert active_kyc_provider() == "kaluta"


def test_active_kyc_provider_shufti_alias(monkeypatch):
    monkeypatch.setattr(kaluta_module.settings, "KYC_PROVIDER", "shufti_pro")
    assert active_kyc_provider() == "shufti_pro"
