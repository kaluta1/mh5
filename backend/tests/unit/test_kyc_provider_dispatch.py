"""Unit tests for KYC provider routing."""
import pytest

from app.models.kyc import VerificationProvider
from app.services import kyc_provider_dispatch as dispatch
from app.services import kaluta_kyc as kaluta_module


pytestmark = pytest.mark.unit


def test_verification_provider_enum_kaluta(monkeypatch):
    monkeypatch.setattr(kaluta_module.settings, "KYC_PROVIDER", "kaluta")
    assert dispatch.verification_provider_enum() == VerificationProvider.KALUTA


def test_verification_provider_enum_shufti(monkeypatch):
    monkeypatch.setattr(kaluta_module.settings, "KYC_PROVIDER", "shufti_pro")
    assert dispatch.verification_provider_enum() == VerificationProvider.SHUFTI_PRO


def test_generate_kyc_reference_routes_to_kaluta(monkeypatch):
    monkeypatch.setattr(kaluta_module.settings, "KYC_PROVIDER", "kaluta")
    ref = dispatch.generate_kyc_reference(7)
    assert ref.startswith("mh5_7_")


def test_provider_for_verification_respects_stored_provider(monkeypatch):
    class FakeVerification:
        provider = VerificationProvider.SHUFTI_PRO

    monkeypatch.setattr(kaluta_module.settings, "KYC_PROVIDER", "kaluta")
    assert dispatch.provider_for_verification(FakeVerification()) == "shufti_pro"
