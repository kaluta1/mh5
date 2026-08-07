"""Unit tests for JWT and password helpers."""
import pytest
from datetime import timedelta
from jose import jwt

from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_email_verification_token,
    create_password_reset_token,
    get_password_hash,
    verify_email_verification_token,
    verify_password,
    verify_password_reset_token,
)


pytestmark = pytest.mark.unit


def test_password_hash_and_verify_roundtrip():
    plain = "SecurePass123!@"
    hashed = get_password_hash(plain)
    assert hashed != plain
    assert verify_password(plain, hashed) is True
    assert verify_password("wrong-password", hashed) is False


def test_access_token_encodes_subject():
    token = create_access_token("42", expires_delta=timedelta(minutes=5))
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    assert payload["sub"] == "42"
    assert "exp" in payload


def test_password_reset_token_roundtrip():
    token = create_password_reset_token("user@example.com")
    assert verify_password_reset_token(token) == "user@example.com"


def test_email_verification_token_roundtrip():
    token = create_email_verification_token("user@example.com")
    assert verify_email_verification_token(token) == "user@example.com"


def test_password_reset_token_rejects_wrong_type():
    token = create_access_token("user@example.com")
    assert verify_password_reset_token(token) is None
