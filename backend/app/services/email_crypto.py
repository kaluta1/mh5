"""Authenticated encryption for the email system (AES-256-GCM).

Everything here is keyed by ONE secret, the dedicated
EMAIL_SETTINGS_ENCRYPTION_KEY environment variable. Per-purpose keys are
derived from it with HKDF-SHA256:

* Admin-managed secrets stored in email_settings (the Resend API-key override,
  a future webhook secret);
* the short-lived delivery payload (recipient + template values) of a queued
  email, deleted when the delivery reaches a terminal state;
* the keyed recipient hash used to count deliveries per address.

There is NO fallback to SECRET_KEY or to any other application secret. Without
the dedicated key nothing can be encrypted or decrypted: the email subsystem
reports "configuration required", no email is queued and no sensitive
plaintext is stored. The rest of the application is unaffected.

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
    return _encrypt(_settings_key(PURPOSE_OUTBOX), json.dumps(payload, separators=(",", ":")), PURPOSE_OUTBOX)


def decrypt_payload(token: str) -> Any:
    return json.loads(_decrypt(_settings_key(PURPOSE_OUTBOX), token, PURPOSE_OUTBOX))


def recipient_hash(address: Optional[str]) -> Optional[str]:
    """Keyed hash of a normalized address: lets the system count and look up
    deliveries per recipient without keeping the address. None when the
    dedicated key is not configured (nothing is queued then anyway)."""
    normalized = (address or "").strip().lower()
    if not normalized or not settings_key_configured():
        return None
    key = _settings_key(_PURPOSE_RECIPIENT_HASH)
    return hmac.new(key, normalized.encode("utf-8"), hashlib.sha256).hexdigest()
