"""Unit tests for E2E message encryption service."""
import pytest

from app.services.feed_encryption import EncryptionService


pytestmark = pytest.mark.unit


@pytest.fixture
def encryption_service():
    return EncryptionService()


def test_generate_key_pair_roundtrip(encryption_service):
    pub, priv = encryption_service.generate_key_pair()
    assert pub
    assert priv
    assert pub != priv


def test_encrypt_decrypt_message(encryption_service):
    alice_pub, alice_priv = encryption_service.generate_key_pair()
    bob_pub, bob_priv = encryption_service.generate_key_pair()

    plaintext = "Hello, secure world!"
    encrypted = encryption_service.encrypt_message(
        plaintext, bob_pub, alice_priv, is_private_key_encrypted=False
    )
    decrypted = encryption_service.decrypt_message(
        encrypted, alice_pub, bob_priv, is_private_key_encrypted=False
    )
    assert decrypted == plaintext


def test_private_key_at_rest_roundtrip(encryption_service):
    _, priv = encryption_service.generate_key_pair()
    encrypted = encryption_service.encrypt_private_key_at_rest(priv)
    restored = encryption_service.decrypt_private_key_at_rest(encrypted)
    assert restored == priv
