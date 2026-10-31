"""Seller verification provider adapters.

Two checks use capabilities MyHigh5 already has:
  IDENTITY            the member's APPROVED MyHigh5 KYC (no second fee), with a name comparison
  PAYOUT_BENEFICIARY  the member's own password-confirmed payout destination

BUSINESS_REGISTRY, REPRESENTATIVE and LICENCE have no connected provider. An external provider (for
example an authorised ACRA UEN integration) is added by registering an adapter; none is invented here
and no registry is scraped. Without a provider a check is UNAVAILABLE and the application goes to a
person: a missing or failing provider never produces PASSED.

Callbacks from an asynchronous provider are signed (HMAC-SHA256 over the raw body with the adapter's
server-side secret) and recorded once per provider event id.
"""
from __future__ import annotations

import hashlib
import hmac
import unicodedata
from dataclasses import dataclass
from typing import Optional, Protocol

from sqlalchemy.orm import Session

from app.models.seller_verification import SellerApplication

IDENTITY, BUSINESS_REGISTRY, REPRESENTATIVE, LICENCE, PAYOUT_BENEFICIARY = (
    "IDENTITY", "BUSINESS_REGISTRY", "REPRESENTATIVE", "LICENCE", "PAYOUT_BENEFICIARY")
CHECK_TYPES = (IDENTITY, BUSINESS_REGISTRY, REPRESENTATIVE, LICENCE, PAYOUT_BENEFICIARY)

PENDING, PASSED, FAILED, UNAVAILABLE, MANUAL = "PENDING", "PASSED", "FAILED", "UNAVAILABLE", "MANUAL"


@dataclass
class ProviderResult:
    status: str                       # PASSED | FAILED | PENDING (awaiting a signed callback) | UNAVAILABLE
    result_code: str
    external_reference: Optional[str] = None


class SellerCheckProvider(Protocol):
    name: str
    check_type: str
    # Server-side secret for callbacks (None = this provider never calls back).
    callback_secret: Optional[str]

    def run(self, db: Session, app: SellerApplication) -> ProviderResult: ...


def normalise_name(value: Optional[str]) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(c for c in text if not unicodedata.combining(c)).casefold()
    return " ".join("".join(c if c.isalnum() else " " for c in text).split())


def names_match(declared: Optional[str], first: Optional[str], last: Optional[str]) -> bool:
    """Same words regardless of order, accents, case and punctuation (no fuzzy guessing)."""
    a, b = normalise_name(declared).split(), normalise_name(f"{first or ''} {last or ''}").split()
    return bool(a) and sorted(a) == sorted(b)


class MemberKycIdentityProvider:
    """Reuses the member's APPROVED MyHigh5 KYC. It never starts a KYC or charges a fee."""

    name, check_type, callback_secret = "MYHIGH5_MEMBER_KYC", IDENTITY, None

    def run(self, db: Session, app: SellerApplication) -> ProviderResult:
        from app.models.kyc import KYCStatus, KYCVerification

        kyc = db.query(KYCVerification).filter(KYCVerification.user_id == app.user_id) \
            .order_by(KYCVerification.id.desc()).first()
        if kyc is None or kyc.status != KYCStatus.APPROVED:
            return ProviderResult(FAILED, "MEMBER_KYC_NOT_APPROVED")
        declared = (app.representative or {}).get("full_name") if app.seller_category == "ORGANISATION" else app.legal_name
        if not names_match(declared, kyc.verified_first_name, kyc.verified_last_name):
            return ProviderResult(FAILED, "IDENTITY_NAME_MISMATCH", f"kyc:{kyc.id}")
        return ProviderResult(PASSED, "MEMBER_KYC_APPROVED", f"kyc:{kyc.id}")


class MemberPayoutDestinationProvider:
    """The member's own payout destination, set with their password (existing MyHigh5 rule). It does not
    prove a bank account holder's name: that limitation is shown to reviewers by its result code."""

    name, check_type, callback_secret = "MYHIGH5_PAYOUT_DESTINATION", PAYOUT_BENEFICIARY, None

    def run(self, db: Session, app: SellerApplication) -> ProviderResult:
        from app.models.user import User

        user = db.query(User).filter(User.id == app.user_id).first()
        if user is None or not user.usdt_wallet_address or not user.payout_wallet_verified_at:
            return ProviderResult(FAILED, "PAYOUT_DESTINATION_MISSING")
        return ProviderResult(PASSED, "MEMBER_DESTINATION_CONFIRMED_NOT_NAME_MATCHED")


_PROVIDERS: dict[str, SellerCheckProvider] = {}


def register(provider: SellerCheckProvider) -> None:
    _PROVIDERS[provider.check_type] = provider


def unregister(check_type: str) -> None:
    _PROVIDERS.pop(check_type, None)


def provider_for(check_type: str) -> Optional[SellerCheckProvider]:
    return _PROVIDERS.get(check_type)


def provider_named(name: str) -> Optional[SellerCheckProvider]:
    return next((p for p in _PROVIDERS.values() if p.name == name), None)


def connected() -> dict[str, str]:
    return {check_type: p.name for check_type, p in _PROVIDERS.items()}


def verify_signature(provider: SellerCheckProvider, body: bytes, signature: Optional[str]) -> bool:
    secret = getattr(provider, "callback_secret", None)
    if not secret or not signature:
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature.strip().lower())


register(MemberKycIdentityProvider())
register(MemberPayoutDestinationProvider())
