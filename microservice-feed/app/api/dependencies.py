"""
API Dependencies
Authentication and authorization
"""
from fastapi import Depends, HTTPException, status, Header
from typing import Optional
import httpx
import logging

from app.core.config import settings
from app.services.main_platform import main_platform_service

logger = logging.getLogger(__name__)


async def verify_token(
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None)
) -> dict:
    """
    Verify JWT token with main platform
    
    Args:
        authorization: Bearer token from Authorization header
        x_api_key: API key for microservice authentication
    
    Returns:
        User data dict with user_id
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing"
        )
    
    # Extract token from "Bearer <token>"
    try:
        scheme, token = authorization.split()
        if scheme.lower() != "bearer":
            raise ValueError("Invalid authorization scheme")
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format"
        )
    
    # Verify API key if required
    if settings.MAIN_PLATFORM_API_KEY and x_api_key != settings.MAIN_PLATFORM_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key"
        )
    
    # Validate token with main platform
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{settings.MAIN_PLATFORM_API_URL}/api/v1/auth/validate-token",
                headers={"Authorization": f"Bearer {token}"},
                params={"token": token},
                timeout=5.0
            )
            
            if response.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid or expired token"
                )
            
            data = response.json()
            if not data.get("valid"):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token"
                )
            
            user_id = data.get("user_id")
            if not user_id:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="User ID not found in token"
                )
            
            return {
                "user_id": user_id,
                "token": token
            }
    
    except httpx.RequestError as e:
        logger.error(f"Error validating token: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Main platform unavailable"
        )


async def get_current_user(
    auth_data: dict = Depends(verify_token)
) -> dict:
    """
    Get current authenticated user
    
    Returns:
        User data dict
    """
    return auth_data
