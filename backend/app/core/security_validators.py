"""Shared input validation for auth and user registration."""
from __future__ import annotations

import re

USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9_]{3,30}$")
FORBIDDEN_USERNAMES = frozenset(
    {"admin", "root", "system", "support", "null", "undefined", "moderator", "staff"}
)
COMMON_PASSWORDS = frozenset(
    {
        "password",
        "123456",
        "12345678",
        "qwerty",
        "admin",
        "letmein",
        "password1",
        "welcome",
        "monkey",
        "dragon",
    }
)


def sanitize_username(value: str) -> str:
    """Validate and normalize username; reject HTML/script injection."""
    if not value:
        raise ValueError("Username is required")
    clean = value.strip()
    if "<" in clean or ">" in clean or "&" in clean:
        raise ValueError("Username contains invalid characters")
    if not USERNAME_PATTERN.match(clean):
        raise ValueError(
            "Username must be 3-30 characters (letters, numbers, underscores only)"
        )
    if clean.lower() in FORBIDDEN_USERNAMES:
        raise ValueError("This username is reserved")
    return clean.lower()


def validate_password_strength(value: str) -> str:
    """Enforce minimum password policy (12+ chars, mixed case, digit, special)."""
    if len(value) < 12:
        raise ValueError("Password must be at least 12 characters")
    if not re.search(r"[A-Z]", value):
        raise ValueError("Password must contain at least one uppercase letter")
    if not re.search(r"[a-z]", value):
        raise ValueError("Password must contain at least one lowercase letter")
    if not re.search(r"\d", value):
        raise ValueError("Password must contain at least one digit")
    if not re.search(r'[!@#$%^&*(),.?":{}|<>_\-+=\[\]\\;/]', value):
        raise ValueError("Password must contain at least one special character")
    if value.lower() in COMMON_PASSWORDS:
        raise ValueError("This password is too common. Please choose a unique password.")
    return value
