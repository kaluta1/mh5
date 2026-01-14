"""
Main API Router
"""
from fastapi import APIRouter

from app.api.v1 import groups, messages, posts, feed, keys

api_router = APIRouter()

# Include all route modules
api_router.include_router(groups.router, prefix="/groups", tags=["Groups"])
api_router.include_router(messages.router, prefix="/messages", tags=["Messages"])
api_router.include_router(posts.router, prefix="/posts", tags=["Posts"])
api_router.include_router(feed.router, prefix="/feed", tags=["Feed"])
api_router.include_router(keys.router, prefix="/keys", tags=["Encryption Keys"])
