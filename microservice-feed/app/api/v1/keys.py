"""
Encryption Keys API Endpoints
Generate and manage user encryption keys
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.dependencies import get_current_user
from app.models.user_keys import UserEncryptionKeys
from app.services.encryption import get_encryption_service
from app.schemas.keys import KeyPairResponse

router = APIRouter()


@router.post("/generate", response_model=KeyPairResponse, status_code=status.HTTP_201_CREATED)
async def generate_keys(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Generate encryption key pair for the user
    
    This should be called once when the user first uses messaging.
    The private key should be stored securely (encrypted at rest).
    """
    user_id = current_user["user_id"]
    
    # Check if keys already exist
    existing = db.query(UserEncryptionKeys).filter(
        UserEncryptionKeys.user_id == user_id,
        UserEncryptionKeys.is_active == True
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Encryption keys already exist. Use /regenerate to create new keys."
        )
    
    # Generate key pair
    encryption_service = get_encryption_service()
    public_key, private_key = encryption_service.generate_key_pair()
    
    # Encrypt private key at rest using master key (if configured)
    encrypted_private_key = encryption_service.encrypt_private_key_at_rest(private_key)
    
    # Store keys
    user_keys = UserEncryptionKeys(
        user_id=user_id,
        public_key=public_key,
        encrypted_private_key=encrypted_private_key,
        is_active=True
    )
    
    db.add(user_keys)
    db.commit()
    db.refresh(user_keys)
    
    return KeyPairResponse(
        user_id=user_id,
        public_key=public_key,
        # Private key should only be returned once during generation
        private_key=private_key,
        message="Store your private key securely. It will not be shown again."
    )


@router.get("/public/{user_id}", response_model=KeyPairResponse)
async def get_public_key(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get a user's public key (safe to share)"""
    user_keys = db.query(UserEncryptionKeys).filter(
        UserEncryptionKeys.user_id == user_id,
        UserEncryptionKeys.is_active == True
    ).first()
    
    if not user_keys:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User encryption keys not found"
        )
    
    return KeyPairResponse(
        user_id=user_id,
        public_key=user_keys.public_key,
        private_key=None  # Never return private key
    )
