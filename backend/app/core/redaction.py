"""Redaction of sensitive values before they are echoed back to clients or logged.

Logging: describe_exception() / safe_traceback() give log-safe exception
diagnostics (types, SQLSTATE, constraint/table names, field paths) without the
exception messages, which can carry SQL bound parameters or submitted input.

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


_SQL_TARGET = re.compile(r"\b(?:INTO|UPDATE|FROM)\s+\"?([A-Za-z_][A-Za-z0-9_.]*)\"?", re.IGNORECASE)
_QUOTED = re.compile(r"\"[^\"]*\"|'[^']*'")
# Credentials that may appear UNQUOTED in a connection error: DSN userinfo
# (a whole scheme://user:pass@host/db URL) and libpq key=value options.
_DSN_URL = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://\S+")
_CONN_OPTIONS = re.compile(r"\b(user|username|password|passwd|pwd|dbname|host|hostaddr|sslkey|sslpassword)\s*=\s*\S+",
                           re.IGNORECASE)
_SAFE_LOC = re.compile(r"[^A-Za-z0-9_]")
_MAX_CHAIN = 5


def _exception_chain(exc: BaseException) -> list:
    chain, current = [], exc
    while current is not None and current not in chain and len(chain) < _MAX_CHAIN:
        chain.append(current)
        current = current.__cause__ or (None if current.__suppress_context__ else current.__context__)
    return chain


def _describe_one(exc: BaseException) -> str:
    parts = [type(exc).__name__]
    errors = getattr(exc, "errors", None)
    if callable(errors) and type(exc).__name__ in ("RequestValidationError", "ValidationError"):
        # Field paths and error types only; the submitted input is never included.
        try:
            items = list(errors())
            locs = [".".join(_SAFE_LOC.sub("", str(p))[:40] for p in (e.get("loc") or ())) + ":" + str(e.get("type"))
                    for e in items[:10]]
            parts.append(f"errors={len(items)} [{', '.join(locs)}]")
        except Exception:
            pass
    statement = getattr(exc, "statement", None)
    if isinstance(statement, str) and statement.strip():
        # SQL verb and target table identifier only: bound parameters, and any
        # literal that may have been interpolated into the text, are dropped.
        verb = statement.strip().split(None, 1)[0].upper()[:12]
        target = _SQL_TARGET.search(_QUOTED.sub("''", statement))   # never read inside literals
        parts.append(f"sql={verb}{' ' + target.group(1) if target else ''}")
    orig = getattr(exc, "orig", None)
    if orig is not None and orig is not exc:
        parts.append(f"driver={type(orig).__name__}")
        code = getattr(orig, "pgcode", None) or getattr(orig, "sqlite_errorname", None)
        if code:
            parts.append(f"sqlstate={code}")
        diag = getattr(orig, "diag", None)
        for attr in ("schema_name", "table_name", "column_name", "constraint_name"):
            value = getattr(diag, attr, None) if diag is not None else None
            if value:
                parts.append(f"{attr}={value}")
        if not code and type(exc).__name__ == "OperationalError":
            # Connection-level failures (DNS, refused, timeout) carry no row data;
            # quoted parts (host/user names), DSN credentials and key=value
            # connection options are still removed; only the first line is kept.
            text = str(orig).strip().splitlines()[0] if str(orig).strip() else ""
            text = _CONN_OPTIONS.sub(r"\1=[..]", _DSN_URL.sub("[dsn]", _QUOTED.sub("[..]", text)))
            parts.append(f"reason={text[:160]}")
    return " ".join(parts)


def describe_exception(exc: BaseException) -> str:
    """Log-safe one-line description of an exception (and its cause chain).

    Exception MESSAGES are never included: SQLAlchemy messages embed the SQL bound
    parameters, driver messages embed row values (e.g. "Key (email)=(...)"), and
    validation errors embed the submitted input (passwords, tokens). Only type
    names and structured, non-user-controlled metadata (SQLSTATE, constraint/table/
    column names, field paths) are kept."""
    return " <- ".join(_describe_one(e) for e in _exception_chain(exc))


def safe_traceback(exc: BaseException, limit: int = 15) -> str:
    """Traceback frames (file, line, function) for the exception chain WITHOUT the
    exception messages, so it can be logged without leaking submitted values."""
    import traceback

    blocks = []
    for e in reversed(_exception_chain(exc)):
        frames = traceback.extract_tb(e.__traceback__)[-limit:]
        lines = [f'  File "{f.filename}", line {f.lineno}, in {f.name}' for f in frames]
        blocks.append("\n".join(lines + [f"{_describe_one(e)}"]))
    return "Traceback (values omitted):\n" + "\n-- caused --\n".join(blocks)


def mask_email(address: Any) -> str:
    """Log-safe form of an email address, e.g. 'j***@e***.com'. Never the raw value."""
    text = str(address or "").strip()
    if "@" not in text:
        return "***"
    local, _, domain = text.partition("@")
    host, dot, tld = domain.rpartition(".")
    host = host or domain
    return f"{local[:1]}***@{host[:1]}***{dot}{tld if dot else ''}"


# Child/Teen Safety Phase 7: protected media URLs carry a viewer-bound grant
# (?g=). A grant is NOT a bearer credential (the media route also requires the
# grant's own viewer session), but it is still kept out of application logs as
# defense in depth.
_MEDIA_TOKEN_RE = re.compile(r"(/media/file/[^?\s]*\?(?:[^\s#]*&)?[gt]=)[^&\s#\"]+")


def redact_media_tokens(text: Any) -> Any:
    if not isinstance(text, str) or ("g=" not in text and "t=" not in text):
        return text
    return _MEDIA_TOKEN_RE.sub(lambda m: m.group(1) + REDACTED, text)


class MediaTokenLogFilter:
    """logging filter: redact media tokens in a record's message and args."""

    def filter(self, record) -> bool:  # noqa: A003 - logging API
        record.msg = redact_media_tokens(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(redact_media_tokens(a) for a in record.args)
        elif isinstance(record.args, dict):
            record.args = {k: redact_media_tokens(v) for k, v in record.args.items()}
        return True
