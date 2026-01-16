"""
Service for communicating with the main platform
Validates users and retrieves user information
"""
import httpx
import logging
from typing import Optional, Dict, Any

from app.core.config import settings

logger = logging.getLogger(__name__)


class MainPlatformService:
    """Service for main platform API communication"""
    
    def __init__(self):
        self.base_url = settings.MAIN_PLATFORM_API_URL
        self.api_key = settings.MAIN_PLATFORM_API_KEY
    
    async def validate_user(self, user_id: int, token: str) -> Optional[Dict[str, Any]]:
        """
        Validate a user token with the main platform
        
        Args:
            user_id: User ID
            token: JWT token
        
        Returns:
            User data if valid, None otherwise
        """
        try:
            async with httpx.AsyncClient() as client:
                headers = {
                    "Authorization": f"Bearer {token}",
                    "X-API-Key": self.api_key
                }
                response = await client.get(
                    f"{self.base_url}/api/v1/auth/validate-token",
                    headers=headers,
                    params={"token": token},
                    timeout=5.0
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get("valid") and data.get("user_id") == user_id:
                        return await self.get_user(user_id, token)
                    return None
                
                return None
        
        except Exception as e:
            logger.error(f"❌ User validation error: {e}")
            return None
    
    async def get_user(self, user_id: int, token: str) -> Optional[Dict[str, Any]]:
        """
        Get user information from main platform
        
        Args:
            user_id: User ID
            token: JWT token
        
        Returns:
            User data
        """
        try:
            async with httpx.AsyncClient() as client:
                headers = {
                    "Authorization": f"Bearer {token}",
                    "X-API-Key": self.api_key
                }
                response = await client.get(
                    f"{self.base_url}/api/v1/users/{user_id}",
                    headers=headers,
                    timeout=5.0
                )
                
                if response.status_code == 200:
                    return response.json()
                
                return None
        
        except Exception as e:
            logger.error(f"❌ Get user error: {e}")
            return None


# Global service instance
main_platform_service = MainPlatformService()
