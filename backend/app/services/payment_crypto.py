"""Authenticated encryption for Finance & Payments secrets (AES-256-GCM).

Keyed by ONE secret, the dedicated PAYMENT_SETTINGS_ENCRYPTION_KEY environment
variable, which is never stored in the database. A per-purpose key is derived
from it with HKDF-SHA256; the purpose is also the GCM associated data, so a
ciphertext stored for one credential cannot be decrypted as another.

There is NO fallback to SECRET_KEY, to the email encryption key or to any other
application secret. Without the dedicated key nothing can be stored or read:
credentials kept in the database are then "not readable" and are never used.

Ciphertext format: "v1:" + base64url(nonce(12) || ciphertext+tag).
"""
from __future__ import annotations

import base64
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.core.config import settings

_VERSION = "v1"
MIN_KEY_LENGTH = 32
PURPOSE_CREDENTIAL = "mh5-payments:credential:"
PURPOSE_USD_DESTINATION = "mh5-payments:usd-destination"


class PaymentCryptoError(Exception):
    """Encryption is unavailable or a ciphertext could not be authenticated."""


def _secret() -> str:
    return (os.getenv("PAYMENT_SETTINGS_ENCRYPTION_KEY") or settings.PAYMENT_SETTINGS_ENCRYPTION_KEY or "").strip()


def key_configured() -> bool:
    return len(_secret()) >= MIN_KEY_LENGTH


def _key(purpose: str) -> bytes:
    secret = _secret()
    if len(secret) < MIN_KEY_LENGTH:
        raise PaymentCryptoError("PAYMENT_SETTINGS_ENCRYPTION_KEY is not configured")
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None,
                info=purpose.encode("utf-8")).derive(secret.encode("utf-8"))


def encrypt(plaintext: str, purpose: str) -> str:
    nonce = os.urandom(12)
    sealed = AESGCM(_key(purpose)).encrypt(nonce, plaintext.encode("utf-8"), purpose.encode("utf-8"))
    return f"{_VERSION}:{base64.urlsafe_b64encode(nonce + sealed).decode('ascii')}"


def decrypt(token: str, purpose: str) -> str:
    key = _key(purpose)
    try:
        version, _, body = (token or "").partition(":")
        if version != _VERSION:
            raise ValueError("unsupported version")
        raw = base64.urlsafe_b64decode(body.encode("ascii"))
        return AESGCM(key).decrypt(raw[:12], raw[12:], purpose.encode("utf-8")).decode("utf-8")
    except (InvalidTag, ValueError, TypeError) as exc:
        raise PaymentCryptoError("ciphertext could not be decrypted") from exc
