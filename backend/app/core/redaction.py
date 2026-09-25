"""Redaction of sensitive values before they are echoed back to clients.

Used by the global request-validation handler: Pydantic puts the submitted
value (and, for a "missing field" error, the WHOLE request body) into each
error's ``input``, so sensitive values must be removed recursively.

A field name is split into tokens across camelCase, snake_case, kebab-case,
dots and spaces, so ``currentPassword``, ``client_secret``, ``refresh-token``
and ``card_pin`` all match. Tokens are compared whole, so ordinary names such as
``shipping``, ``opinion``, ``pinned`` or ``tokenizer`` are not redacted.
"""
from __future__ import annotations

import re
from typing import Any

REDACTED = "[REDACTED]"

# A single token that is sensitive on its own.
_SENSITIVE_TOKENS = frozenset({
    "password", "passwd", "pwd", "passcode", "passphrase",
    "secret", "token", "otp", "totp", "pin", "cvv", "cvc", "seed", "mnemonic",
})
# Sensitive only in combination (checked on the joined, separator-free name).
_SENSITIVE_COMPOUNDS = ("apikey", "privatekey", "secretkey", "accesskey", "signingkey")

_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
_SEPARATORS = re.compile(r"[^A-Za-z0-9]+")


def field_tokens(name: str) -> list[str]:
    return [t.lower() for t in _SEPARATORS.split(_CAMEL_BOUNDARY.sub(" ", name)) if t]


def is_sensitive_field(name: Any) -> bool:
    if not isinstance(name, str) or not name:
        return False
    tokens = field_tokens(name)
    if any(t in _SENSITIVE_TOKENS for t in tokens):
        return True
    joined = "".join(tokens)
    return any(compound in joined for compound in _SENSITIVE_COMPOUNDS)


def redact_sensitive(value: Any) -> Any:
    """Recursively replace values stored under sensitive keys (dicts inside lists too)."""
    if isinstance(value, dict):
        return {k: (REDACTED if is_sensitive_field(k) else redact_sensitive(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_sensitive(v) for v in value]
    return value


def redact_validation_errors(errors: list) -> list:
    """Validation errors with sensitive inputs redacted (errors must be JSON-safe already)."""
    safe = []
    for err in errors:
        if isinstance(err, dict) and "input" in err:
            if any(is_sensitive_field(part) for part in (err.get("loc") or [])):
                err["input"] = REDACTED
            else:
                err["input"] = redact_sensitive(err["input"])
        safe.append(err)
    return safe


def mask_email(address: Any) -> str:
    """Log-safe form of an email address, e.g. 'j***@e***.com'. Never the raw value."""
    text = str(address or "").strip()
    if "@" not in text:
        return "***"
    local, _, domain = text.partition("@")
    host, dot, tld = domain.rpartition(".")
    host = host or domain
    return f"{local[:1]}***@{host[:1]}***{dot}{tld if dot else ''}"
