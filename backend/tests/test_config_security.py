import os


def test_secret_key_must_come_from_env():
    """SECRET_KEY must not use a hard-coded fallback in production."""
    secret = os.getenv("SECRET_KEY", "")
    if os.getenv("ENVIRONMENT", "development").lower() == "production":
        assert secret, "SECRET_KEY is required in production"
        assert len(secret) >= 32, "SECRET_KEY must be at least 32 characters"
    else:
        # In development the test is informational.
        assert isinstance(secret, str)


def test_master_encryption_key_from_env_in_production():
    key = os.getenv("MASTER_ENCRYPTION_KEY", "")
    if os.getenv("ENVIRONMENT", "development").lower() == "production":
        assert key, "MASTER_ENCRYPTION_KEY is required in production"
