"""
Kaluta KYC integration — session creation, status sync, webhook verification.
Docs: https://kalutakyc.com (API at https://kalutakyc.com/v1)
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import random
import string
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

KALUTA_API_BASE = "https://kalutakyc.com/v1"
KALUTA_APP_HOST = "https://kalutakyc.com"
WEBHOOK_MAX_AGE_SECONDS = 300

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


def _parse_dob(user_dob: Optional[datetime]) -> Optional[str]:
    if not user_dob:
        return None
    try:
        return user_dob.strftime("%Y-%m-%d")
    except Exception:
        return None


class KalutaKYCService:
    def __init__(self) -> None:
        self.api_key = (settings.KALUTA_API_KEY or "").strip()
        self.webhook_secret = (settings.KALUTA_WEBHOOK_SECRET or "").strip()
        self.webhook_url, self.redirect_url = resolve_kaluta_urls()

    def configured(self) -> bool:
        return bool(self.api_key)

    def generate_reference(self, user_id: int) -> str:
        suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
        return f"mh5_{user_id}_{suffix}"

    def verify_webhook_signature(self, raw_body: bytes, signature_header: str) -> bool:
        if not self.webhook_secret:
            logger.warning("KALUTA_WEBHOOK_SECRET not set — webhook signature not verified")
            return settings.ENVIRONMENT.lower() in ("development", "dev", "local")

        if not signature_header:
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
            age = abs(int(datetime.utcnow().timestamp()) - int(ts))
            if age > WEBHOOK_MAX_AGE_SECONDS:
                return False
            signed = f"{ts}.".encode() + raw_body
            expected = hmac.new(
                self.webhook_secret.encode(),
                signed,
                hashlib.sha256,
            ).hexdigest()
            return hmac.compare_digest(expected, v1)
        except Exception:
            logger.exception("Kaluta webhook signature parse failed")
            return False

    async def create_session(
        self,
        *,
        external_id: str,
        user,
        country_iso: Optional[str] = None,
        residential_address: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not self.configured():
            return {"success": False, "error": "Kaluta KYC is not configured (KALUTA_API_KEY missing)."}

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
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(f"{KALUTA_API_BASE}/sessions", headers=headers, json=body)
            if resp.status_code >= 400:
                detail = resp.text[:500]
                try:
                    detail = resp.json().get("detail", detail)
                except Exception:
                    pass
                return {"success": False, "error": f"Kaluta POST /sessions -> {resp.status_code}: {detail}"}

            data = resp.json()
            session_id = str(data.get("session_id") or data.get("id") or "")
            verification_url = data.get("verification_url") or (
                f"{KALUTA_APP_HOST}/verify/{session_id}" if session_id else None
            )
            if not session_id or not verification_url:
                return {"success": False, "error": "Kaluta session response missing session_id or verification_url"}

            return {
                "success": True,
                "session_id": session_id,
                "verification_url": verification_url,
                "expires_at": data.get("expires_at"),
                "reference": external_id,
            }
        except httpx.HTTPError as exc:
            logger.exception("Kaluta create_session HTTP error")
            return {"success": False, "error": f"Kaluta API error: {exc}"}

    async def get_session(self, session_id: str) -> Dict[str, Any]:
        if not self.configured():
            return {"success": False, "error": "Kaluta not configured"}

        headers = {"X-API-Key": self.api_key, "Content-Type": "application/json"}
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.get(f"{KALUTA_API_BASE}/sessions/{session_id}", headers=headers)
            if resp.status_code >= 400:
                return {"success": False, "error": resp.text[:300], "status_code": resp.status_code}
            return {"success": True, "data": resp.json()}
        except httpx.HTTPError as exc:
            return {"success": False, "error": str(exc)}

    async def check_reference_validity(self, verification) -> Dict[str, Any]:
        """
        Poll Kaluta for session state. Uses external_verification_id (Kaluta session_id).
        Falls back to reference_id as external_id lookup via list if needed.
        """
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
        status = (data.get("status") or "").lower()
        verification_url = data.get("verification_url") or verification.verification_url

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
