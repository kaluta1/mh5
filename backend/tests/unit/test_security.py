"""Unit tests for JWT and password helpers."""
import pytest
from datetime import timedelta
from jose import jwt

from app.core.config import settings
from app.core.security import (
    access_token_security_version,
    create_access_token,
    decode_access_token,
    get_password_hash,
    verify_password,
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
    payload = jwt.decode(
        token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM],
        issuer=settings.JWT_ISSUER, audience=settings.JWT_AUDIENCE,
    )
    assert payload["sub"] == "42"
    assert "exp" in payload


def test_access_token_carries_the_security_version():
    assert access_token_security_version(decode_access_token(create_access_token("42"))) == 0
    assert access_token_security_version(decode_access_token(create_access_token("42", security_version=7))) == 7
    # a token issued before the claim existed counts as version 0
    assert access_token_security_version({"sub": "42", "type": "access"}) == 0
    assert access_token_security_version({"sub": "42", "sv": "garbage"}) == -1


@pytest.mark.parametrize("token_type", ["password_reset", "email_verification", "kyc_document_view", "", None])
def test_a_signed_jwt_of_another_type_is_not_an_access_token(token_type):
    """Email links are no longer JWTs at all (app.services.auth_tokens), and a
    correctly signed token of any other type never authenticates a request."""
    claims = {"sub": "42", "iss": settings.JWT_ISSUER, "aud": settings.JWT_AUDIENCE}
    if token_type is not None:
        claims["type"] = token_type
    forged = jwt.encode(claims, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    assert decode_access_token(forged) == {}


def test_link_tokens_are_not_minted_as_jwts_any_more():
    """The reusable JWT link tokens are gone: nothing can mint one."""
    import app.core.security as security

    for name in ("create_password_reset_token", "create_email_verification_token",
                 "verify_password_reset_token", "verify_email_verification_token"):
        assert not hasattr(security, name)
