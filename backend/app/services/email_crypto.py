"""Authenticated encryption for the email system (AES-256-GCM).

Two separate keys, each derived with HKDF-SHA256 and bound to its purpose:

* SETTINGS key: protects Admin-managed secrets stored in email_settings (the
  Resend API-key override, a future webhook secret). It is derived ONLY from
  the dedicated EMAIL_SETTINGS_ENCRYPTION_KEY environment secret. Without that
  variable no secret can be stored or read back; nothing falls back to another
  application key.

* OUTBOX key: protects the short-lived delivery payload (recipient + template
  values) of a queued email until it reaches a terminal state, at which point
  the payload is deleted. Derived from EMAIL_SETTINGS_ENCRYPTION_KEY when set,
  otherwise from SECRET_KEY, so that queueing email keeps working on a
  deployment that has not configured the dedicated secret yet.

Ciphertext format: "v1:" + base64url(nonce(12) || ciphertext+tag). The purpose
string is also the GCM associated data, so a value encrypted for one purpose
cannot be decrypted as another.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from typing import Any, Optional

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.core.config import settings

_VERSION = "v1"
PURPOSE_API_KEY = "mh5-email:resend-api-key"
PURPOSE_WEBHOOK_SECRET = "mh5-email:webhook-secret"
PURPOSE_OUTBOX = "mh5-email:outbox-payload"
_PURPOSE_RECIPIENT_HASH = "mh5-email:recipient-hash"

MIN_KEY_LENGTH = 32


class EmailCryptoError(Exception):
    """Encryption is unavailable or a ciphertext could not be authenticated."""


def _settings_secret() -> str:
    return (os.getenv("EMAIL_SETTINGS_ENCRYPTION_KEY") or settings.EMAIL_SETTINGS_ENCRYPTION_KEY or "").strip()


def settings_key_configured() -> bool:
    return len(_settings_secret()) >= MIN_KEY_LENGTH


def _derive(secret: str, purpose: str) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None,
                info=purpose.encode("utf-8")).derive(secret.encode("utf-8"))


def _settings_key(purpose: str) -> bytes:
    secret = _settings_secret()
    if len(secret) < MIN_KEY_LENGTH:
        raise EmailCryptoError("EMAIL_SETTINGS_ENCRYPTION_KEY is not configured")
    return _derive(secret, purpose)


def _outbox_secret() -> str:
    secret = _settings_secret()
    if len(secret) >= MIN_KEY_LENGTH:
        return secret
    return settings.SECRET_KEY or ""


def _encrypt(key: bytes, plaintext: str, purpose: str) -> str:
    nonce = os.urandom(12)
    sealed = AESGCM(key).encrypt(nonce, plaintext.encode("utf-8"), purpose.encode("utf-8"))
    return f"{_VERSION}:{base64.urlsafe_b64encode(nonce + sealed).decode('ascii')}"


def _decrypt(key: bytes, token: str, purpose: str) -> str:
    try:
        version, _, body = (token or "").partition(":")
        if version != _VERSION:
            raise ValueError("unsupported version")
        raw = base64.urlsafe_b64decode(body.encode("ascii"))
        return AESGCM(key).decrypt(raw[:12], raw[12:], purpose.encode("utf-8")).decode("utf-8")
    except (InvalidTag, ValueError, TypeError) as exc:
        raise EmailCryptoError("ciphertext could not be decrypted") from exc


def encrypt_secret(plaintext: str, purpose: str = PURPOSE_API_KEY) -> str:
    return _encrypt(_settings_key(purpose), plaintext, purpose)


def decrypt_secret(token: str, purpose: str = PURPOSE_API_KEY) -> str:
    return _decrypt(_settings_key(purpose), token, purpose)


def encrypt_payload(payload: Any) -> str:
    secret = _outbox_secret()
    if not secret:
        raise EmailCryptoError("no key available for the delivery payload")
    return _encrypt(_derive(secret, PURPOSE_OUTBOX), json.dumps(payload, separators=(",", ":")), PURPOSE_OUTBOX)


def decrypt_payload(token: str) -> Any:
    secret = _outbox_secret()
    if not secret:
        raise EmailCryptoError("no key available for the delivery payload")
    return json.loads(_decrypt(_derive(secret, PURPOSE_OUTBOX), token, PURPOSE_OUTBOX))


def recipient_hash(address: Optional[str]) -> Optional[str]:
    """Keyed hash of a normalized address: lets the system count and look up
    deliveries per recipient without keeping the address."""
    normalized = (address or "").strip().lower()
    if not normalized:
        return None
    key = _derive(settings.SECRET_KEY or "email", _PURPOSE_RECIPIENT_HASH)
    return hmac.new(key, normalized.encode("utf-8"), hashlib.sha256).hexdigest()
