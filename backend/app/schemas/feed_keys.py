"""
Encryption Keys Schemas for Feed System
"""
from pydantic import BaseModel
from typing import Optional


class KeyPairResponse(BaseModel):
    """Schema for encryption key pair response"""
    user_id: int
    public_key: str
    private_key: Optional[str] = None  # Only returned during generation
    message: Optional[str] = None
