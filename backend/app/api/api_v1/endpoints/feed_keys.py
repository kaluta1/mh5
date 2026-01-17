"""
Encryption Keys API Endpoints for Feed System
Generate and manage user encryption keys
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from sqlalchemy.exc import OperationalError, ProgrammingError

from app.db.session import get_db
from app.api.deps import get_current_active_user
from app.models.user import User
from app.models.user_encryption_keys import UserEncryptionKeys
from app.services.feed_encryption import get_encryption_service
from app.schemas.feed_keys import KeyPairResponse

router = APIRouter()


@router.post("/generate", response_model=KeyPairResponse, status_code=status.HTTP_201_CREATED)
def generate_keys(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Generate encryption key pair for the user
    
    This should be called once when the user first uses messaging.
    The private key should be stored securely (encrypted at rest).
    """
    user_id = current_user.id
    
    # Check if keys already exist
    try:
        existing = db.query(UserEncryptionKeys).filter(
            UserEncryptionKeys.user_id == user_id,
            UserEncryptionKeys.is_active == True
        ).first()
    except (OperationalError, ProgrammingError):
        # Table might not exist yet; create it and retry
        UserEncryptionKeys.__table__.create(db.bind, checkfirst=True)
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
    
    # Encrypt private key at rest
    encrypted_private_key = encryption_service.encrypt_private_key_at_rest(private_key)
    
    # Store keys
    next_id = db.query(func.coalesce(func.max(UserEncryptionKeys.id), 0)).scalar() + 1
    user_keys = UserEncryptionKeys(
        id=next_id,
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
def get_public_key(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get a user's public key (safe to share)"""
    try:
        user_keys = db.query(UserEncryptionKeys).filter(
            UserEncryptionKeys.user_id == user_id,
            UserEncryptionKeys.is_active == True
        ).first()
    except (OperationalError, ProgrammingError):
        # Table might not exist yet; create it and retry
        UserEncryptionKeys.__table__.create(db.bind, checkfirst=True)
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
