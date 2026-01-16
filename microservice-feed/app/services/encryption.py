"""
End-to-End Encryption Service for Chat Messages
Uses PyNaCl (NaCl/libsodium) for encryption
Only sender and receiver can decrypt messages
"""
from nacl.public import PrivateKey, PublicKey, Box
from nacl.encoding import Base64Encoder
from nacl.utils import random
import base64
import json
import logging
from typing import Optional, Tuple
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
import os

from app.core.config import settings

logger = logging.getLogger(__name__)

_encryption_service = None


class EncryptionService:
    """Service for end-to-end message encryption"""
    
    def __init__(self):
        """Initialize encryption service"""
        logger.info("🔐 Initializing Encryption Service")
        self.master_key = settings.MASTER_ENCRYPTION_KEY.encode() if settings.MASTER_ENCRYPTION_KEY else None
        self.salt = settings.ENCRYPTION_KEY_DERIVATION_SALT.encode()
    
    def generate_key_pair(self) -> Tuple[str, str]:
        """
        Generate a new public/private key pair for a user
        
        Returns:
            Tuple of (public_key_base64, private_key_base64)
        """
        private_key = PrivateKey.generate()
        public_key = private_key.public_key
        
        # Encode to base64 for storage
        private_key_b64 = private_key.encode(encoder=Base64Encoder).decode('utf-8')
        public_key_b64 = public_key.encode(encoder=Base64Encoder).decode('utf-8')
        
        return public_key_b64, private_key_b64
    
    def encrypt_private_key_at_rest(self, private_key: str) -> str:
        """
        Encrypt private key at rest using AES-256-GCM
        
        Args:
            private_key: Private key (base64)
        
        Returns:
            Encrypted private key (base64)
        """
        if not self.master_key:
            logger.warning("⚠️ Master encryption key not set. Storing private key unencrypted.")
            return private_key
        
        try:
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=self.salt,
                iterations=100000,
            )
            key = kdf.derive(self.master_key)
            
            aesgcm = AESGCM(key)
            nonce = os.urandom(12)
            encrypted = aesgcm.encrypt(nonce, private_key.encode('utf-8'), None)
            
            combined = nonce + encrypted
            return base64.b64encode(combined).decode('utf-8')
        except Exception as e:
            logger.error(f"❌ Private key encryption error: {e}")
            return private_key
    
    def decrypt_private_key_at_rest(self, encrypted_private_key: str) -> str:
        """
        Decrypt private key at rest
        
        Args:
            encrypted_private_key: Encrypted private key (base64)
        
        Returns:
            Decrypted private key (base64)
        """
        if not self.master_key:
            return encrypted_private_key
        
        try:
            combined = base64.b64decode(encrypted_private_key.encode('utf-8'))
            nonce = combined[:12]
            encrypted = combined[12:]
            
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=self.salt,
                iterations=100000,
            )
            key = kdf.derive(self.master_key)
            
            aesgcm = AESGCM(key)
            decrypted = aesgcm.decrypt(nonce, encrypted, None)
            return decrypted.decode('utf-8')
        except Exception as e:
            logger.warning(f"⚠️ Private key decryption failed, assuming unencrypted: {e}")
            return encrypted_private_key
    
    def encrypt_message(
        self, 
        message: str, 
        recipient_public_key: str,
        sender_private_key: str,
        is_private_key_encrypted: bool = True
    ) -> str:
        """
        Encrypt a message for a recipient
        
        Args:
            message: Plain text message to encrypt
            recipient_public_key: Recipient's public key (base64)
            sender_private_key: Sender's private key (base64, may be encrypted at rest)
            is_private_key_encrypted: Whether the private key is encrypted at rest
        
        Returns:
            Encrypted message (base64)
        """
        try:
            if is_private_key_encrypted:
                sender_private_key = self.decrypt_private_key_at_rest(sender_private_key)
            
            recipient_pub = PublicKey(
                recipient_public_key.encode('utf-8'),
                encoder=Base64Encoder
            )
            sender_priv = PrivateKey(
                sender_private_key.encode('utf-8'),
                encoder=Base64Encoder
            )
            
            box = Box(sender_priv, recipient_pub)
            encrypted = box.encrypt(message.encode('utf-8'))
            
            return base64.b64encode(encrypted).decode('utf-8')
        
        except Exception as e:
            logger.error(f"❌ Encryption error: {e}")
            raise ValueError(f"Failed to encrypt message: {str(e)}")
    
    def decrypt_message(
        self,
        encrypted_message: str,
        sender_public_key: str,
        recipient_private_key: str,
        is_private_key_encrypted: bool = True
    ) -> str:
        """
        Decrypt a message
        
        Args:
            encrypted_message: Encrypted message (base64)
            sender_public_key: Sender's public key (base64)
            recipient_private_key: Recipient's private key (base64, may be encrypted at rest)
            is_private_key_encrypted: Whether the private key is encrypted at rest
        
        Returns:
            Decrypted plain text message
        """
        try:
            if is_private_key_encrypted:
                recipient_private_key = self.decrypt_private_key_at_rest(recipient_private_key)
            
            sender_pub = PublicKey(
                sender_public_key.encode('utf-8'),
                encoder=Base64Encoder
            )
            recipient_priv = PrivateKey(
                recipient_private_key.encode('utf-8'),
                encoder=Base64Encoder
            )
            
            box = Box(recipient_priv, sender_pub)
            encrypted_bytes = base64.b64decode(encrypted_message.encode('utf-8'))
            decrypted = box.decrypt(encrypted_bytes)
            
            return decrypted.decode('utf-8')
        
        except Exception as e:
            logger.error(f"❌ Decryption error: {e}")
            raise ValueError(f"Failed to decrypt message: {str(e)}")
    
    def verify_key_pair(self, public_key: str, private_key: str) -> bool:
        """
        Verify that a public/private key pair matches
        
        Args:
            public_key: Public key (base64)
            private_key: Private key (base64)
        
        Returns:
            True if keys match, False otherwise
        """
        try:
            priv = PrivateKey(
                private_key.encode('utf-8'),
                encoder=Base64Encoder
            )
            pub = priv.public_key
            expected_pub_b64 = pub.encode(encoder=Base64Encoder).decode('utf-8')
            
            return expected_pub_b64 == public_key
        except Exception:
            return False


def init_encryption_service():
    """Initialize the global encryption service"""
    global _encryption_service
    if _encryption_service is None:
        _encryption_service = EncryptionService()
    return _encryption_service


def get_encryption_service() -> EncryptionService:
    """Get the encryption service instance"""
    if _encryption_service is None:
        return init_encryption_service()
    return _encryption_service
