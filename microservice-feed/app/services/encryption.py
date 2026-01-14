"""
End-to-End Encryption Service for Chat Messages
Uses PyNaCl (NaCl/libsodium) for encryption
Only sender and receiver can decrypt messages
"""
from nacl.public import PrivateKey, PublicKey, Box
from nacl.encoding import Base64Encoder
from nacl.utils import random
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend
import base64
import json
import logging
import os
import secrets
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

_encryption_service = None


class EncryptionService:
    """Service for end-to-end message encryption"""
    
    def __init__(self, master_key: Optional[bytes] = None):
        """
        Initialize encryption service
        
        Args:
            master_key: Master key for encrypting private keys at rest.
                       If None, will use environment variable or generate one.
        """
        logger.info("🔐 Initializing Encryption Service")
        
        # Master key for encrypting private keys at rest
        # In production, this should come from secure key management
        if master_key:
            self.master_key = master_key
        else:
            # Try to get from environment, or use a default (NOT SECURE FOR PRODUCTION)
            master_key_env = os.getenv("MASTER_ENCRYPTION_KEY")
            if master_key_env:
                self.master_key = base64.b64decode(master_key_env.encode())
            else:
                # Generate a key (should be set in production)
                logger.warning("⚠️ Using generated master key. Set MASTER_ENCRYPTION_KEY in production!")
                self.master_key = secrets.token_bytes(32)  # 256-bit key
        
        # AES-GCM for encrypting private keys
        self.aesgcm = AESGCM(self.master_key)
    
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
            sender_private_key: Sender's private key (base64, may be encrypted)
            is_private_key_encrypted: Whether the private key is encrypted at rest
        
        Returns:
            Encrypted message (base64)
        """
        try:
            # Decrypt private key if needed
            if is_private_key_encrypted and self._is_encrypted(sender_private_key):
                decrypted_private_key = self.decrypt_private_key_at_rest(sender_private_key)
            else:
                decrypted_private_key = sender_private_key
            
            # Decode keys from base64
            recipient_pub = PublicKey(
                recipient_public_key.encode('utf-8'),
                encoder=Base64Encoder
            )
            sender_priv = PrivateKey(
                decrypted_private_key.encode('utf-8'),
                encoder=Base64Encoder
            )
            
            # Create encryption box
            box = Box(sender_priv, recipient_pub)
            
            # Encrypt message
            encrypted = box.encrypt(message.encode('utf-8'))
            
            # Return base64 encoded encrypted message
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
            recipient_private_key: Recipient's private key (base64, may be encrypted)
            is_private_key_encrypted: Whether the private key is encrypted at rest
        
        Returns:
            Decrypted plain text message
        """
        try:
            # Decrypt private key if needed
            if is_private_key_encrypted and self._is_encrypted(recipient_private_key):
                decrypted_private_key = self.decrypt_private_key_at_rest(recipient_private_key)
            else:
                decrypted_private_key = recipient_private_key
            
            # Decode keys from base64
            sender_pub = PublicKey(
                sender_public_key.encode('utf-8'),
                encoder=Base64Encoder
            )
            recipient_priv = PrivateKey(
                decrypted_private_key.encode('utf-8'),
                encoder=Base64Encoder
            )
            
            # Create decryption box
            box = Box(recipient_priv, sender_pub)
            
            # Decode encrypted message from base64
            encrypted_bytes = base64.b64decode(encrypted_message.encode('utf-8'))
            
            # Decrypt message
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
            private_key: Private key (base64, may be encrypted)
        
        Returns:
            True if keys match, False otherwise
        """
        try:
            # Decrypt private key if needed
            if self._is_encrypted(private_key):
                decrypted_private_key = self.decrypt_private_key_at_rest(private_key)
            else:
                decrypted_private_key = private_key
            
            priv = PrivateKey(
                decrypted_private_key.encode('utf-8'),
                encoder=Base64Encoder
            )
            pub = priv.public_key
            expected_pub_b64 = pub.encode(encoder=Base64Encoder).decode('utf-8')
            
            return expected_pub_b64 == public_key
        except Exception:
            return False
    
    def encrypt_private_key_at_rest(self, private_key: str) -> str:
        """
        Encrypt a private key for storage at rest
        
        Args:
            private_key: Plain private key (base64)
        
        Returns:
            Encrypted private key (base64)
        """
        try:
            # Generate nonce
            nonce = secrets.token_bytes(12)  # 96-bit nonce for AES-GCM
            
            # Encrypt private key
            private_key_bytes = private_key.encode('utf-8')
            encrypted = self.aesgcm.encrypt(nonce, private_key_bytes, None)
            
            # Combine nonce + encrypted data
            encrypted_with_nonce = nonce + encrypted
            
            # Return base64 encoded
            return base64.b64encode(encrypted_with_nonce).decode('utf-8')
        
        except Exception as e:
            logger.error(f"❌ Private key encryption error: {e}")
            raise ValueError(f"Failed to encrypt private key: {str(e)}")
    
    def decrypt_private_key_at_rest(self, encrypted_private_key: str) -> str:
        """
        Decrypt a private key from storage
        
        Args:
            encrypted_private_key: Encrypted private key (base64)
        
        Returns:
            Decrypted private key (base64)
        """
        try:
            # Decode from base64
            encrypted_data = base64.b64decode(encrypted_private_key.encode('utf-8'))
            
            # Extract nonce (first 12 bytes) and encrypted data
            nonce = encrypted_data[:12]
            encrypted = encrypted_data[12:]
            
            # Decrypt
            decrypted = self.aesgcm.decrypt(nonce, encrypted, None)
            
            return decrypted.decode('utf-8')
        
        except Exception as e:
            logger.error(f"❌ Private key decryption error: {e}")
            raise ValueError(f"Failed to decrypt private key: {str(e)}")
    
    def _is_encrypted(self, private_key: str) -> bool:
        """
        Check if a private key is encrypted
        
        Args:
            private_key: Private key string
        
        Returns:
            True if encrypted, False if plain
        """
        # Simple heuristic: encrypted keys are longer and have different structure
        # In production, use a prefix or flag
        try:
            # Try to decode as base64 and check length
            decoded = base64.b64decode(private_key.encode('utf-8'))
            # Encrypted keys with nonce are longer (nonce + encrypted data)
            return len(decoded) > 64  # Encrypted keys are typically longer
        except:
            return False
    
    def derive_key_from_password(self, password: str, salt: bytes) -> bytes:
        """
        Derive encryption key from password using PBKDF2
        
        Args:
            password: User password
            salt: Salt bytes
        
        Returns:
            Derived key (32 bytes)
        """
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,  # OWASP recommended minimum
            backend=default_backend()
        )
        return kdf.derive(password.encode('utf-8'))


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
