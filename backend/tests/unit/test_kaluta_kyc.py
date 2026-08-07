"""Unit tests for Kaluta KYC helpers."""
import hashlib
import hmac
import json
from datetime import datetime

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


def test_webhook_signature_valid():
    svc = KalutaKYCService()
    svc.webhook_secret = "test-secret"
    body = b'{"event":"session.approved"}'
    ts = str(int(datetime.utcnow().timestamp()))
    signed = f"{ts}.".encode() + body
    sig = hmac.new(b"test-secret", signed, hashlib.sha256).hexdigest()
    header = f"t={ts},v1={sig}"
    assert svc.verify_webhook_signature(body, header) is True


def test_webhook_signature_rejects_tampered_body():
    svc = KalutaKYCService()
    svc.webhook_secret = "test-secret"
    body = b'{"event":"session.approved"}'
    ts = str(int(datetime.utcnow().timestamp()))
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
