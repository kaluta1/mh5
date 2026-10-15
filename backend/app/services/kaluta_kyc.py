"""
Kaluta KYC integration — session creation, status sync, webhook verification.
Docs: https://kalutakyc.com/docs (API at https://kalutakyc.com/v1)

What the provider documents, and what this module relies on:
  * POST /v1/sessions with the secret key in X-API-Key creates a session and
    returns session_id, verification_url and expires_at (24 hours).
  * The decision arrives on a webhook signed "t=<unix>,v1=<hex>" where v1 is
    HMAC-SHA256 over "<t>.<raw body>"; a timestamp older than five minutes is
    refused. The webhook is the source of truth. Deliveries are retried, so the
    handler must be idempotent and answer within ten seconds.
  * After a rejection the member may retry inside the provider's widget: a new
    session with the SAME external_id.

Whether Kaluta KYC is on, the API key and the webhook secret come ONLY from
the database (Admin > KYC, app.services.kyc_settings; the key and the secret
stored encrypted). The server environment is not read for them. They are never
sent to a browser, logged or returned in an answer.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
import string
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

KALUTA_API_BASE = "https://kalutakyc.com/v1"
KALUTA_APP_HOST = "https://kalutakyc.com"
WEBHOOK_MAX_AGE_SECONDS = 300
WEBHOOK_MAX_BODY_BYTES = 1_000_000

# What a member is told when the provider cannot be used. The provider's own
# words (which may name an account balance or a key) go to the server log only.
UNAVAILABLE_MESSAGE = "Identity verification is temporarily unavailable. Please try again later."
# Stored with a provider rejection, so that an approval the provider sends later
# for the same reference (the member retried in the widget) is recognised as
# following a PROVIDER rejection and never overturns an administrator's decision.
PROVIDER_REJECTION_MARK = "kaluta:session:"

# Raw model output and documents are not needed to decide anything here and are
# not kept (the provider keeps them; the decision, scores and identity are kept).
_NOT_STORED = ("ai_extraction", "extracted_data", "proof_of_address", "images", "image_urls", "document_images")

TERMINAL_APPROVED = {"approved"}
TERMINAL_REJECTED = {"rejected"}
TERMINAL_EXPIRED = {"expired"}
IN_FLIGHT = {"created", "document_submitted", "face_submitted", "in_progress", "pending"}


def active_kyc_provider() -> str:
    raw = (settings.KYC_PROVIDER or "kaluta").strip().lower()
    if raw in ("shufti", "shufti_pro"):
        return "shufti_pro"
    return "kaluta"


def is_kaluta_active() -> bool:
    return active_kyc_provider() == "kaluta"


def resolve_kaluta_urls() -> Tuple[str, str]:
    backend = (settings.BACKEND_PUBLIC_URL or "").strip().rstrip("/")
    frontend = (settings.FRONTEND_URL or "").strip().rstrip("/")
    webhook = (settings.KALUTA_WEBHOOK_URL or "").strip()
    redirect = (settings.KALUTA_REDIRECT_URL or "").strip()
    if not webhook and backend:
        webhook = f"{backend}/api/v1/kyc/webhook/kaluta"
    if not redirect and frontend:
        redirect = f"{frontend}/dashboard/kyc"
    return webhook, redirect


def kyc_flags_from_kaluta_session(session: Dict[str, Any]) -> Dict[str, bool]:
    """Map Kaluta session payload to our verification booleans."""
    status = (session.get("status") or "").lower()
    approved = status in TERMINAL_APPROVED
    scores = session.get("scores") if isinstance(session.get("scores"), dict) else {}
    checks = session.get("checks_required") if isinstance(session.get("checks_required"), dict) else {}

    doc_score = scores.get("document")
    face_score = scores.get("face")
    poa_score = scores.get("poa")

    document_ok = approved if doc_score is None else bool(doc_score and doc_score >= 60)
    face_ok = approved if face_score is None else bool(face_score and face_score >= 60)
    poa_required = bool(checks.get("proof_of_address"))
    poa_ok = bool(poa_score and poa_score >= 60) if poa_required else False

    return {
        "identity_verified": document_ok and face_ok,
        "document_verified": document_ok,
        "face_verified": face_ok,
        "address_verified": poa_ok if poa_required else False,
        "kaluta_poa_complete": poa_required and poa_ok and approved,
    }


def is_provider_verification_url(url: Optional[str]) -> bool:
    """Only an https page of the provider's own host is ever stored or handed to a browser."""
    try:
        parsed = urlparse((url or "").strip())
    except ValueError:
        return False
    return parsed.scheme == "https" and parsed.netloc.lower() == urlparse(KALUTA_APP_HOST).netloc


def parse_provider_time(value: Any) -> Optional[datetime]:
    """An ISO 8601 instant from the provider as a naive UTC datetime (how this database stores time)."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(timezone.utc).replace(tzinfo=None) if parsed.tzinfo else parsed


def storable_session(session: Dict[str, Any]) -> Dict[str, Any]:
    """The part of a provider session that is kept in the verification record."""
    return {k: v for k, v in session.items() if k not in _NOT_STORED} if isinstance(session, dict) else {}


def _parse_dob(user_dob: Optional[datetime]) -> Optional[str]:
    if not user_dob:
        return None
    try:
        return user_dob.strftime("%Y-%m-%d")
    except Exception:
        return None


class KalutaKYCService:
    """`enabled`, `api_key` and `webhook_secret` are the database settings in
    force: app.services.kyc_settings.apply() hands them over before every KYC
    request (use_settings). Until then, and whenever they cannot be read,
    Kaluta KYC is off and has no key or secret."""

    def __init__(self) -> None:
        self.enabled = False
        self.api_key = ""
        self.webhook_secret = ""
        self.webhook_url, self.redirect_url = resolve_kaluta_urls()

    def use_settings(self, values: Dict[str, Any]) -> None:
        """REPLACE the settings in force. A name that is absent means off / not set."""
        self.enabled = bool(values.get("enabled"))
        self.api_key = str(values.get("api_key") or "")
        self.webhook_secret = str(values.get("webhook_secret") or "")

    def __repr__(self) -> str:  # a key or a secret must never reach a log through repr()
        return (f"KalutaKYCService(enabled={self.enabled}, api_key={'set' if self.api_key else 'missing'}, "
                f"webhook_secret={'set' if self.webhook_secret else 'missing'})")

    def configured(self) -> bool:
        return self.enabled and bool(self.api_key)

    def generate_reference(self, user_id: int) -> str:
        alphabet = string.ascii_lowercase + string.digits
        suffix = "".join(secrets.choice(alphabet) for _ in range(16))      # not guessable
        return f"mh5_{user_id}_{suffix}"

    def verify_webhook_signature(self, raw_body: bytes, signature_header: str) -> bool:
        if not self.enabled:
            logger.warning("Kaluta KYC is switched off in Admin > KYC — webhook rejected, not verified")
            return False
        if not self.webhook_secret:
            # Never accepted unsigned, in any environment.
            logger.warning("No Kaluta webhook secret is saved in Admin > KYC — webhook rejected")
            return False

        if not signature_header or len(signature_header) > 512 or len(raw_body) > WEBHOOK_MAX_BODY_BYTES:
            return False

        try:
            parts = {}
            for piece in signature_header.split(","):
                if "=" in piece:
                    k, v = piece.split("=", 1)
                    parts[k.strip()] = v.strip()
            ts = parts.get("t")
            v1 = parts.get("v1")
            if not ts or not v1:
                return False
            # time.time() is the real epoch. datetime.utcnow().timestamp() reads a UTC
            # wall clock as LOCAL time, which shifts it by the server's UTC offset
            # and refused every genuine delivery on a server not set to UTC.
            age = abs(int(time.time()) - int(ts))
            if age > WEBHOOK_MAX_AGE_SECONDS:
                return False
            signed = f"{ts}.".encode() + raw_body
            expected = hmac.new(
                self.webhook_secret.encode(),
                signed,
                hashlib.sha256,
            ).hexdigest()
            return hmac.compare_digest(expected.encode("ascii"), v1.encode("utf-8"))
        except Exception as exc:  # noqa: BLE001 - a malformed header is simply not a signature
            logger.warning("Kaluta webhook signature could not be read (%s)", type(exc).__name__)
            return False

    async def create_session(
        self,
        *,
        external_id: str,
        user,
        country_iso: Optional[str] = None,
        residential_address: Optional[str] = None,
    ) -> Dict[str, Any]:
        # "no_session_created": the provider certainly opened nothing (it was not
        # asked, or it refused the request), so nothing can have been charged.
        if not self.enabled:
            return {"success": False, "no_session_created": True, "error": "Kaluta KYC is temporarily disabled."}
        if not self.configured():
            return {"success": False, "no_session_created": True,
                    "error": "Kaluta KYC is not configured (no API key saved in Admin > KYC)."}

        body: Dict[str, Any] = {
            "external_id": external_id,
            "redirect_url": self.redirect_url,
            "webhook_url": self.webhook_url,
            "metadata": {"user_id": user.id, "platform": "myhigh5"},
        }

        if user.first_name:
            body["first_name"] = str(user.first_name).strip()
        if user.last_name:
            body["last_name"] = str(user.last_name).strip()
        dob = _parse_dob(getattr(user, "date_of_birth", None))
        if dob:
            body["date_of_birth"] = dob
        if country_iso:
            body["country"] = country_iso
        if residential_address and len(residential_address.strip()) >= 2:
            body["metadata"]["declared_address"] = residential_address.strip()

        headers = {"X-API-Key": self.api_key, "Content-Type": "application/json"}

        try:
            timeout = httpx.Timeout(30.0, connect=5.0, read=20.0, write=10.0, pool=5.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(f"{KALUTA_API_BASE}/sessions", headers=headers, json=body)
            if resp.status_code >= 400:
                # 401 key refused, 402 no balance, 429 rate limit, 5xx provider fault: none of
                # them is the member's doing and none of the provider's wording is shown to them.
                reason = {400: "request refused", 401: "API key refused", 402: "insufficient balance",
                          403: "not allowed", 429: "rate limited"}.get(resp.status_code, "provider error")
                logger.error("Kaluta POST /sessions answered %s (%s)", resp.status_code, reason)
                # A 4xx refusal opened nothing. After a 5xx it is not known, so it counts.
                return {"success": False, "unavailable": True, "provider_status": resp.status_code,
                        "no_session_created": resp.status_code < 500, "error": UNAVAILABLE_MESSAGE}

            try:
                data = resp.json()
            except ValueError:
                data = None
            if not isinstance(data, dict):
                logger.error("Kaluta POST /sessions answered %s without a JSON object", resp.status_code)
                return {"success": False, "unavailable": True, "error": UNAVAILABLE_MESSAGE}
            session_id = str(data.get("session_id") or data.get("id") or "")
            verification_url = data.get("verification_url") or (
                f"{KALUTA_APP_HOST}/verify/{session_id}" if session_id else None
            )
            if not session_id or not is_provider_verification_url(verification_url):
                logger.error("Kaluta POST /sessions answer had no usable session id or verification URL")
                return {"success": False, "unavailable": True, "error": UNAVAILABLE_MESSAGE}

            return {
                "success": True,
                "session_id": session_id,
                "verification_url": verification_url,
                "expires_at": data.get("expires_at"),
                "reference": external_id,
            }
        except httpx.HTTPError as exc:
            # Not retried here: a session may have been created, and a second call would make a second one.
            logger.error("Kaluta create_session failed (%s)", type(exc).__name__)
            return {"success": False, "unavailable": True, "error": UNAVAILABLE_MESSAGE}

    async def get_session(self, session_id: str) -> Dict[str, Any]:
        if not self.enabled:
            return {"success": False, "error": "Kaluta KYC is temporarily disabled."}
        if not self.configured():
            return {"success": False, "error": "Kaluta not configured"}

        headers = {"X-API-Key": self.api_key, "Content-Type": "application/json"}
        try:
            timeout = httpx.Timeout(20.0, connect=5.0, read=15.0, write=10.0, pool=5.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.get(f"{KALUTA_API_BASE}/sessions/{session_id}", headers=headers)
            if resp.status_code >= 400:
                return {"success": False, "error": "provider answered an error", "status_code": resp.status_code}
            data = resp.json()
            if not isinstance(data, dict):
                return {"success": False, "error": "unreadable answer"}
            return {"success": True, "data": data}
        except (httpx.HTTPError, ValueError) as exc:
            return {"success": False, "error": type(exc).__name__}

    async def check_reference_validity(self, verification) -> Dict[str, Any]:
        """
        Poll Kaluta for session state. Uses external_verification_id (Kaluta session_id).
        Falls back to reference_id as external_id lookup via list if needed.
        """
        if not self.enabled:
            return {"is_valid": False, "is_completed": False, "data": {}}
        session_id = (verification.external_verification_id or "").strip()
        if not session_id:
            url = (verification.verification_url or "").strip()
            if url and "/verify/" in url:
                session_id = url.rsplit("/verify/", 1)[-1].split("?")[0].strip()

        if not session_id:
            if verification.verification_url:
                return {
                    "is_valid": True,
                    "is_completed": False,
                    "verification_url": verification.verification_url,
                    "data": {},
                }
            return {"is_valid": False, "is_completed": False, "data": {}}

        fetched = await self.get_session(session_id)
        if not fetched.get("success"):
            if verification.verification_url:
                return {
                    "is_valid": True,
                    "is_completed": False,
                    "verification_url": verification.verification_url,
                    "data": {},
                }
            return {"is_valid": False, "is_completed": False, "data": {}}

        data = fetched.get("data") or {}
        # The answer must be about THIS verification: the reference it was created for.
        answered_for = data.get("external_id")
        if answered_for is not None and str(answered_for) != str(verification.reference_id or ""):
            logger.warning("Kaluta session answer is for another reference; ignored (verification %s)", verification.id)
            return {"is_valid": bool(verification.verification_url), "is_completed": False,
                    "verification_url": verification.verification_url, "data": {}}
        status = (data.get("status") or "").lower()
        verification_url = data.get("verification_url")
        if not is_provider_verification_url(verification_url):
            verification_url = verification.verification_url

        if status in TERMINAL_APPROVED:
            return {
                "is_valid": False,
                "is_completed": True,
                "is_accepted": True,
                "verification_url": verification_url,
                "data": data,
            }
        if status in TERMINAL_REJECTED:
            return {
                "is_valid": False,
                "is_completed": True,
                "is_accepted": False,
                "verification_url": verification_url,
                "data": data,
            }
        if status in TERMINAL_EXPIRED:
            return {
                "is_valid": False,
                "is_completed": True,
                "is_accepted": False,
                "expired": True,
                "verification_url": verification_url,
                "data": data,
            }

        return {
            "is_valid": True,
            "is_completed": False,
            "verification_url": verification_url,
            "data": data,
        }


kaluta_kyc_service = KalutaKYCService()
