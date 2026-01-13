# Feed Microservice Integration Guide

This guide explains how to integrate the Feed Microservice into the main backend.

## ✅ Step 1: Dependencies Added

**Updated `requirements.txt`:**
- ✅ `httpx==0.28.1` (upgraded from 0.25.0)
- ✅ `httpcore==1.0.9` (upgraded from 0.18.0)
- ✅ `pynacl==1.6.2` (for E2E encryption)
- ✅ `cryptography==41.0.7` (for encryption)

**Note:** The backend already has:
- ✅ `psycopg2-binary==2.9.11` (this version works, no pg_config needed)
- ✅ All other required dependencies

## 📋 Integration Steps

### Step 2: Copy Feed Models

Copy feed-related models from microservice to backend:
- `app/models/feed_group.py` (SocialGroup, GroupMember)
- `app/models/feed_message.py` (PrivateMessage, PrivateConversation)
- `app/models/feed_post.py` (Post, PostMedia, PostComment, PostReaction)
- `app/models/user_encryption_keys.py` (UserEncryptionKeys)

### Step 3: Copy Feed Schemas

Copy schemas to `app/schemas/`:
- `feed_group.py`
- `feed_message.py`
- `feed_post.py`
- `feed_keys.py`

### Step 4: Copy Feed Services

Copy services to `app/services/`:
- `encryption.py` (E2E encryption service)
- `feed_aws_s3.py` (if using S3, or adapt existing storage service)

### Step 5: Create Feed Endpoints

Create `app/api/api_v1/endpoints/feed.py` with:
- Groups endpoints
- Messages endpoints (E2E encrypted)
- Posts endpoints
- Feed generation endpoint
- Encryption keys endpoints

### Step 6: Register Feed Router

Add to `app/api/api_v1/api.py`:
```python
from app.api.api_v1.endpoints import feed

api_router.include_router(feed.router, prefix="/feed", tags=["Feed"])
```

## 🔧 Adaptations Needed

1. **Database Session**: Use backend's existing `app.db.session.get_db()`
2. **Authentication**: Use backend's existing `app.api.deps.get_current_user()`
3. **Configuration**: Use backend's `app.core.config.settings`
4. **Storage**: Use backend's existing storage service or adapt

## ⚠️ Important Notes

- The backend already uses the same database (Neon PostgreSQL)
- Authentication is already integrated
- Configuration is already set up
- Just need to add the feed-specific code

## 🚀 Quick Integration

The easiest approach is to:
1. Copy feed models, schemas, services
2. Create feed endpoints that use backend's existing infrastructure
3. Register the feed router

This avoids duplication and uses existing backend infrastructure.

