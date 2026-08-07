"""Unit tests for auth input validators."""
import pytest

from app.core.security_validators import sanitize_username, validate_password_strength


pytestmark = pytest.mark.unit


def test_sanitize_username_normalizes_case():
    assert sanitize_username("MyUser_01") == "myuser_01"


def test_sanitize_username_rejects_html():
    with pytest.raises(ValueError, match="invalid"):
        sanitize_username("<script>")


def test_sanitize_username_rejects_reserved():
    with pytest.raises(ValueError, match="reserved"):
        sanitize_username("admin")


def test_validate_password_strength_accepts_strong_password():
    assert validate_password_strength("SecurePass123!@") == "SecurePass123!@"


def test_validate_password_strength_rejects_short():
    with pytest.raises(ValueError, match="12 characters"):
        validate_password_strength("Short1!")
