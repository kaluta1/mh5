"""
Service for communicating with the main platform
Validates users and retrieves user information
"""
import httpx
import logging
import json
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta

from app.core.config import settings

logger = logging.getLogger(__name__)


class MainPlatformService:
    """Service for main platform API communication"""
    
    def __init__(self):
        self.base_url = settings.MAIN_PLATFORM_API_URL
        self.api_key = settings.MAIN_PLATFORM_API_KEY
        self._cache: Dict[str, tuple] = {}  # Simple in-memory cache (key: (data, expiry))
        self._cache_ttl = 300  # 5 minutes cache TTL
    
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
    
    async def get_user(self, user_id: int, token: str, use_cache: bool = True) -> Optional[Dict[str, Any]]:
        """
        Get user information from main platform
        
        Args:
            user_id: User ID
            token: JWT token
            use_cache: Whether to use cache
        
        Returns:
            User data
        """
        # Check cache
        cache_key = f"user:{user_id}"
        if use_cache and cache_key in self._cache:
            data, expiry = self._cache[cache_key]
            if datetime.now() < expiry:
                return data
            else:
                del self._cache[cache_key]
        
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
                    data = response.json()
                    # Cache the result
                    if use_cache:
                        self._cache[cache_key] = (data, datetime.now() + timedelta(seconds=self._cache_ttl))
                    return data
                
                return None
        
        except Exception as e:
            logger.error(f"❌ Get user error: {e}")
            return None
    
    async def get_followers(self, user_id: int, token: str, use_cache: bool = True) -> List[int]:
        """
        Get list of user IDs that follow the given user
        
        Args:
            user_id: User ID
            token: JWT token
            use_cache: Whether to use cache
        
        Returns:
            List of follower user IDs
        """
        cache_key = f"followers:{user_id}"
        if use_cache and cache_key in self._cache:
            data, expiry = self._cache[cache_key]
            if datetime.now() < expiry:
                return data
            else:
                del self._cache[cache_key]
        
        try:
            async with httpx.AsyncClient() as client:
                headers = {
                    "Authorization": f"Bearer {token}",
                    "X-API-Key": self.api_key
                }
                response = await client.get(
                    f"{self.base_url}/api/v1/users/{user_id}/followers",
                    headers=headers,
                    timeout=5.0
                )
                
                if response.status_code == 200:
                    data = response.json()
                    # Extract user IDs from response
                    # Assuming response format: {"followers": [{"id": 1, ...}, ...]}
                    if isinstance(data, dict) and "followers" in data:
                        follower_ids = [f.get("id") for f in data["followers"] if f.get("id")]
                    elif isinstance(data, list):
                        follower_ids = [f.get("id") for f in data if f.get("id")]
                    else:
                        follower_ids = []
                    
                    # Cache the result
                    if use_cache:
                        self._cache[cache_key] = (follower_ids, datetime.now() + timedelta(seconds=self._cache_ttl))
                    return follower_ids
                
                return []
        
        except Exception as e:
            logger.error(f"❌ Get followers error: {e}")
            return []
    
    async def get_following(self, user_id: int, token: str, use_cache: bool = True) -> List[int]:
        """
        Get list of user IDs that the given user follows
        
        Args:
            user_id: User ID
            token: JWT token
            use_cache: Whether to use cache
        
        Returns:
            List of following user IDs
        """
        cache_key = f"following:{user_id}"
        if use_cache and cache_key in self._cache:
            data, expiry = self._cache[cache_key]
            if datetime.now() < expiry:
                return data
            else:
                del self._cache[cache_key]
        
        try:
            async with httpx.AsyncClient() as client:
                headers = {
                    "Authorization": f"Bearer {token}",
                    "X-API-Key": self.api_key
                }
                response = await client.get(
                    f"{self.base_url}/api/v1/users/{user_id}/following",
                    headers=headers,
                    timeout=5.0
                )
                
                if response.status_code == 200:
                    data = response.json()
                    # Extract user IDs from response
                    if isinstance(data, dict) and "following" in data:
                        following_ids = [f.get("id") for f in data["following"] if f.get("id")]
                    elif isinstance(data, list):
                        following_ids = [f.get("id") for f in data if f.get("id")]
                    else:
                        following_ids = []
                    
                    # Cache the result
                    if use_cache:
                        self._cache[cache_key] = (following_ids, datetime.now() + timedelta(seconds=self._cache_ttl))
                    return following_ids
                
                return []
        
        except Exception as e:
            logger.error(f"❌ Get following error: {e}")
            return []
    
    async def get_users_batch(self, user_ids: List[int], token: str) -> Dict[int, Dict[str, Any]]:
        """
        Get multiple users in a single request
        
        Args:
            user_ids: List of user IDs
            token: JWT token
        
        Returns:
            Dictionary mapping user_id to user data
        """
        if not user_ids:
            return {}
        
        try:
            async with httpx.AsyncClient() as client:
                headers = {
                    "Authorization": f"Bearer {token}",
                    "X-API-Key": self.api_key
                }
                # Try batch endpoint, fallback to individual requests
                response = await client.post(
                    f"{self.base_url}/api/v1/users/batch",
                    headers=headers,
                    json={"user_ids": user_ids},
                    timeout=10.0
                )
                
                if response.status_code == 200:
                    data = response.json()
                    # Assuming response format: {"users": [{"id": 1, ...}, ...]}
                    if isinstance(data, dict) and "users" in data:
                        return {user["id"]: user for user in data["users"] if user.get("id")}
                    elif isinstance(data, list):
                        return {user["id"]: user for user in data if user.get("id")}
                
                # Fallback: fetch individually
                users = {}
                for user_id in user_ids:
                    user_data = await self.get_user(user_id, token, use_cache=False)
                    if user_data:
                        users[user_id] = user_data
                
                return users
        
        except Exception as e:
            logger.error(f"❌ Get users batch error: {e}")
            # Fallback: fetch individually
            users = {}
            for user_id in user_ids:
                try:
                    user_data = await self.get_user(user_id, token, use_cache=False)
                    if user_data:
                        users[user_id] = user_data
                except:
                    continue
            return users
    
    def clear_cache(self, pattern: Optional[str] = None):
        """
        Clear cache entries
        
        Args:
            pattern: Optional pattern to match cache keys (e.g., "user:" to clear all user cache)
        """
        if pattern:
            keys_to_delete = [k for k in self._cache.keys() if k.startswith(pattern)]
            for k in keys_to_delete:
                del self._cache[k]
        else:
            self._cache.clear()


# Global service instance
main_platform_service = MainPlatformService()
