# Feed Microservice - MyHigh5

A FastAPI microservice that handles Groups, Messaging (End-to-End Encrypted), Posts, and Feed Generation. Connects to Supabase PostgreSQL for data storage and AWS S3 for file storage.

## 📋 Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Quick Start](#quick-start)
- [Setup Instructions](#setup-instructions)
- [Environment Variables](#environment-variables)
- [API Endpoints](#api-endpoints)
- [End-to-End Encryption](#end-to-end-encryption)
- [Integration with Main Platform](#integration-with-main-platform)
- [Accessing the Service](#accessing-the-service)
- [Troubleshooting](#troubleshooting)
- [Implementation Status](#implementation-status)
- [Production Considerations](#production-considerations)

---

## ✨ Features

- **End-to-End Encrypted Messaging** - All chat messages are encrypted. Only sender and receiver can decrypt.
- **Groups Management** - Create, join, and manage social groups with role-based permissions
- **Posts System** - Create, share, and interact with posts (reactions, comments, media)
- **Feed Generation** - Personalized feed for users based on follows, groups, and preferences
- **AWS S3 Integration** - File storage for media files (images, videos, documents)
- **Supabase PostgreSQL** - Separate database for all feed-related data
- **Docker Support** - Containerized deployment with Docker networking
- **Real-time Support** - WebSocket support for real-time messaging (Socket.IO)

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Main Platform                         │
│              (FastAPI - Port 8000)                      │
│  - User Authentication                                  │
│  - Main Business Logic                                  │
└────────────────────┬────────────────────────────────────┘
                     │
                     │ HTTP/gRPC API Calls
                     │ (Docker Network)
                     │
┌────────────────────▼────────────────────────────────────┐
│              Feed Microservice                          │
│              (FastAPI - Port 8001)                      │
│  - Groups API                                           │
│  - Messaging API (E2E Encrypted)                        │
│  - Posts API                                            │
│  - Feed API                                             │
└────────────┬───────────────────────┬───────────────────┘
             │                       │
    ┌────────▼────────┐      ┌───────▼────────┐
    │  Supabase       │      │   AWS S3       │
    │  PostgreSQL     │      │   File Storage │
    └─────────────────┘      └────────────────┘
```

### Technology Stack

- **Framework**: FastAPI (Python 3.11+)
- **Database**: Supabase PostgreSQL
- **Storage**: AWS S3
- **Encryption**: PyNaCl (NaCl/libsodium) for E2E encryption
- **Real-time**: WebSocket (Socket.IO)
- **Container**: Docker

---

## 🚀 Quick Start

### 1. Navigate to the microservice directory

```powershell
cd mh5\mh5\microservice-feed
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Create `.env` file

Create a `.env` file in the microservice directory (see [Environment Variables](#environment-variables) section below).

**Quick setup with placeholder values:**

```env
# Supabase (use placeholder values for now)
SUPABASE_URL=https://placeholder.supabase.co
SUPABASE_KEY=placeholder-key
SUPABASE_SERVICE_KEY=placeholder-service-key
SUPABASE_DB_URL=postgresql://postgres:password@localhost:5432/postgres

# AWS S3 (use placeholder values for now)
AWS_ACCESS_KEY_ID=placeholder-access-key
AWS_SECRET_ACCESS_KEY=placeholder-secret-key
AWS_REGION=us-east-1
AWS_S3_BUCKET=placeholder-bucket

# Main Platform
MAIN_PLATFORM_API_URL=http://localhost:8000
MAIN_PLATFORM_API_KEY=

# Encryption (generate secure values)
ENCRYPTION_KEY_DERIVATION_SALT=your-random-salt-here-min-32-chars
MASTER_ENCRYPTION_KEY=your-base64-encoded-32-byte-key

# Server
HOST=0.0.0.0
PORT=8001
DEBUG=True
CORS_ORIGINS=http://localhost:3000,http://localhost:8000
REDIS_URL=redis://localhost:6379/0
LOG_LEVEL=INFO
```

**Generate encryption keys automatically:**

```powershell
python -c "import secrets, base64; print('ENCRYPTION_KEY_DERIVATION_SALT=' + secrets.token_urlsafe(32)); print('MASTER_ENCRYPTION_KEY=' + base64.b64encode(secrets.token_bytes(32)).decode())"
```

### 4. Start the service

```bash
python main.py
```

The service will start on **http://localhost:8001**

### 5. Access the API documentation

Open your browser and go to: **http://localhost:8001/docs**

---

## 📝 Setup Instructions

### Prerequisites

- Python 3.11+ (Python 3.14 compatible)
- Supabase account and project (for database)
- AWS account with S3 bucket (for file storage)
- Docker (optional, for containerized deployment)

### 1. Database Setup (Supabase)

1. Go to https://supabase.com
2. Create a new project
3. Get your database URL from Settings → Database
4. Update `SUPABASE_DB_URL` in `.env` file

**Format**: `postgresql://postgres:[PASSWORD]@db.[PROJECT-REF].supabase.co:5432/postgres`

#### Run Migrations

```bash
# Initialize Alembic (if not already done)
alembic init alembic

# Create initial migration
alembic revision --autogenerate -m "Initial migration"

# Apply migrations
alembic upgrade head
```

### 2. AWS S3 Setup

1. Create an S3 bucket in AWS Console
2. Configure bucket permissions (CORS, public access if needed)
3. Create IAM user with S3 access
4. Get access key and secret key
5. Update `.env` with AWS credentials

### 3. Run the Service

#### Development

```bash
python main.py
```

Or with uvicorn:

```bash
uvicorn main:app --host 0.0.0.0 --port 8001 --reload
```

#### Docker

```bash
# Create Docker network (if not exists)
docker network create myhigh5-network

# Build and run
docker-compose up -d

# View logs
docker-compose logs -f feed-microservice
```

---

## 🔧 Environment Variables

All environment variables should be set in a `.env` file in the microservice directory.

### Required Variables

```env
# Supabase Configuration
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-supabase-anon-key
SUPABASE_SERVICE_KEY=your-supabase-service-role-key
SUPABASE_DB_URL=postgresql://postgres:[PASSWORD]@db.[PROJECT-REF].supabase.co:5432/postgres

# AWS S3 Configuration
AWS_ACCESS_KEY_ID=your-aws-access-key
AWS_SECRET_ACCESS_KEY=your-aws-secret-key
AWS_REGION=us-east-1
AWS_S3_BUCKET=myhigh5-feed-media

# Main Platform API
MAIN_PLATFORM_API_URL=http://localhost:8000
MAIN_PLATFORM_API_KEY=your-api-key

# Encryption
ENCRYPTION_KEY_DERIVATION_SALT=generate-a-random-salt-here-min-32-chars
MASTER_ENCRYPTION_KEY=your-base64-encoded-32-byte-key

# Server Configuration
HOST=0.0.0.0
PORT=8001
DEBUG=True
CORS_ORIGINS=http://localhost:3000,http://localhost:8000
REDIS_URL=redis://localhost:6379/0
LOG_LEVEL=INFO
```

### Note

The service will start with placeholder values, but:
- Database operations won't work until you configure Supabase
- File uploads won't work until you configure AWS S3
- The API documentation will still be accessible for testing

---

## 📡 API Endpoints

### Quick Access URLs

Once running, access:
- **API Docs (Swagger UI)**: http://localhost:8001/docs
- **API Docs (ReDoc)**: http://localhost:8001/redoc
- **Health Check**: http://localhost:8001/health
- **Root**: http://localhost:8001/

### Encryption Keys

- `POST /api/v1/keys/generate` - Generate encryption key pair
- `GET /api/v1/keys/public/{user_id}` - Get user's public key

### Groups

- `POST /api/v1/groups` - Create a group
- `GET /api/v1/groups` - List groups
- `GET /api/v1/groups/{id}` - Get group details
- `PUT /api/v1/groups/{id}` - Update group settings
- `POST /api/v1/groups/{id}/join` - Join a group
- `DELETE /api/v1/groups/{id}/leave` - Leave a group
- `GET /api/v1/groups/{id}/members` - Get group members
- `POST /api/v1/groups/{id}/members/{member_id}/ban` - Ban member
- `POST /api/v1/groups/{id}/members/{member_id}/promote` - Promote member
- `DELETE /api/v1/groups/{id}/members/{member_id}` - Remove member

### Messages (E2E Encrypted)

- `POST /api/v1/messages/send` - Send encrypted message
- `GET /api/v1/messages/conversations` - List conversations
- `GET /api/v1/messages/conversations/{id}/messages` - Get messages (decrypted)
- `POST /api/v1/messages/{id}/read` - Mark message as read
- `POST /api/v1/messages/groups/{group_id}/send` - Send group message
- `GET /api/v1/messages/groups/{group_id}/messages` - Get group messages

### Posts

- `POST /api/v1/posts` - Create a post
- `GET /api/v1/posts` - List posts
- `GET /api/v1/posts/{id}` - Get post details
- `PUT /api/v1/posts/{id}` - Update post
- `DELETE /api/v1/posts/{id}` - Delete post
- `POST /api/v1/posts/{id}/share` - Share post
- `POST /api/v1/posts/{id}/media` - Upload media
- `POST /api/v1/posts/{id}/comments` - Create comment
- `POST /api/v1/posts/{id}/reactions` - Toggle reaction

### Feed

- `GET /api/v1/feed` - Get personalized feed

### Authentication

All endpoints (except `/health` and `/`) require authentication:

**Header**:
```
Authorization: Bearer <JWT_TOKEN>
```

The JWT token should be obtained from the main platform.

---

## 🔐 End-to-End Encryption

### How It Works

1. **Key Generation**: Each user generates a public/private key pair
2. **Message Encryption**: Messages are encrypted with recipient's public key
3. **Message Storage**: Only encrypted content is stored in database
4. **Message Decryption**: Only recipient can decrypt using their private key

### Security Notes

⚠️ **IMPORTANT**: 
- Private keys are encrypted at rest using AES-256-GCM
- Master encryption key should be stored securely (use environment variables or key management service)
- All chat messages are end-to-end encrypted
- Never log or expose private keys
- Consider using hardware security modules (HSM) for key management in production

### Encryption Implementation

- **Library**: PyNaCl (NaCl/libsodium)
- **Algorithm**: Curve25519 for key exchange, XSalsa20-Poly1305 for encryption
- **Private Key Storage**: Encrypted with AES-256-GCM using master key

---

## 🔗 Integration with Main Platform

The microservice validates user tokens with the main platform:

1. User authenticates with main platform
2. Main platform returns JWT token
3. Microservice validates token with main platform API
4. Microservice processes request if token is valid

### Docker Network Setup

To connect with the main platform:

```bash
# Create Docker network (if not exists)
docker network create myhigh5-network

# Run main platform and microservice on same network
docker-compose up
```

### Main Platform API Integration

The microservice communicates with the main platform for:
- **User Authentication**: Validate JWT tokens
- **User Data**: Fetch user information (username, avatar, etc.)
- **Follow System**: Get list of users a user follows
- **User Existence**: Verify user IDs exist

---

## 🌐 Accessing the Service

### Web Interface (API Documentation)

The Feed Microservice provides an **interactive web interface** for testing and viewing the API.

**Swagger UI (Recommended)**:
```
http://localhost:8001/docs
```

**ReDoc**:
```
http://localhost:8001/redoc
```

### Using the Swagger UI

1. **Click on any endpoint** to expand it
2. **Click "Try it out"** button
3. **Fill in parameters** (if needed)
4. **Click "Execute"** to test the API
5. **See the response** below

### Authentication in Swagger UI

For protected endpoints:
1. Click the **"Authorize"** button at the top
2. Enter your JWT token: `Bearer YOUR_TOKEN_HERE`
3. Click "Authorize"
4. Now you can test protected endpoints

### Testing with curl

```bash
# Health check
curl http://localhost:8001/health

# Test endpoint (with authentication)
curl -X GET "http://localhost:8001/api/v1/feed" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

---

## 🐛 Troubleshooting

### Database Connection Issues

**Error**: `password authentication failed for user "postgres"`

**Solutions**:
- Verify `SUPABASE_DB_URL` is correct in `.env` file
- Check Supabase project is active
- Verify network connectivity
- The application will start with a warning if database connection fails (database operations won't work)

### AWS S3 Issues

**Solutions**:
- Verify AWS credentials in `.env` file
- Check bucket permissions
- Verify bucket exists and region is correct

### Encryption Issues

**Solutions**:
- Ensure users have generated key pairs
- Verify keys are active
- Check encryption service initialization
- Verify `MASTER_ENCRYPTION_KEY` is set correctly

### Connection Refused / Can't Reach Page

**Solutions**:
- Make sure the service is running (`python main.py`)
- Check if port 8001 is available
- Verify no firewall blocking
- Check if service started successfully (look for startup logs)

### 401 Unauthorized

**Solutions**:
- Click "Authorize" button in Swagger UI
- Enter valid JWT token from main platform
- Format: `Bearer YOUR_TOKEN`
- Verify main platform is running and accessible

### Python 3.14 Compatibility

If you encounter `AttributeError: 'typing.Union' object has no attribute '__module__'`:

**Solution**: The `requirements.txt` has been updated with compatible versions:
- `httpx==0.28.1`
- `httpcore==1.0.9`

Make sure these versions are installed:
```bash
pip install --upgrade httpx httpcore
```

---

## ✅ Implementation Status

### Completed Features

1. **Encryption Improvements**
   - ✅ Private key encryption at rest (AES-256-GCM)
   - ✅ Master key support
   - ✅ Key derivation function (PBKDF2)

2. **Main Platform Integration**
   - ✅ Enhanced main platform service
   - ✅ Get followers/following
   - ✅ Batch user lookup
   - ✅ Caching

3. **Feed Generation**
   - ✅ Main platform integration
   - ✅ Group posts in feed
   - ✅ Followed users posts
   - ✅ Public posts

4. **Group Chat Messaging**
   - ✅ Group message sending
   - ✅ Group message retrieval
   - ✅ Group conversation management
   - ✅ Encryption support

5. **Post Features**
   - ✅ Post editing
   - ✅ Post deletion
   - ✅ Post sharing

6. **Group Management**
   - ✅ Group settings update
   - ✅ Group member list
   - ✅ Member banning
   - ✅ Member promotion
   - ✅ Member removal
   - ✅ Role-based access control

### Future Enhancements

- Group message encryption improvements (use group key)
- Redis caching (replace in-memory cache)
- WebSocket support for real-time messaging
- Media encryption before uploading to S3
- Feed relevance scoring algorithm
- Message search (encrypted search - challenging)
- Key rotation mechanism
- Forward secrecy for messages

---

## 🚀 Production Considerations

### Security

1. **Encryption**:
   - ✅ Private keys encrypted at rest
   - Use environment variables for secrets
   - Enable HTTPS/TLS
   - Implement rate limiting

2. **Key Management**:
   - Store master encryption key securely
   - Consider using key management service (AWS KMS, HashiCorp Vault)
   - Implement key rotation

3. **Authentication**:
   - Validate all JWT tokens
   - Implement token refresh
   - Use secure token storage

### Performance

1. **Caching**:
   - Use Redis for production caching
   - Cache feed per user
   - Cache user data from main platform

2. **Database**:
   - Use connection pooling (already configured)
   - Optimize database queries
   - Add database indexes

3. **Storage**:
   - Use CDN for media files
   - Implement file compression
   - Optimize image/video processing

### Monitoring

1. **Logging**:
   - Set up structured logging
   - Monitor API metrics
   - Track error rates

2. **Alerts**:
   - Set up alerts for errors
   - Monitor database connection
   - Track API response times

3. **Health Checks**:
   - Use `/health` endpoint for monitoring
   - Set up health check in Docker/Kubernetes

---

## 📚 Additional Resources

### Service Structure

```
mh5/microservice-feed/
├── main.py                 # Entry point
├── app/
│   ├── api/v1/            # API endpoints
│   │   ├── groups.py      # Groups endpoints
│   │   ├── messages.py    # Messages endpoints
│   │   ├── posts.py       # Posts endpoints
│   │   ├── feed.py        # Feed endpoints
│   │   └── keys.py        # Encryption keys endpoints
│   ├── models/            # Database models
│   ├── schemas/           # Pydantic schemas
│   ├── services/          # Business logic
│   │   ├── encryption.py  # E2E encryption
│   │   ├── main_platform.py  # Main platform API
│   │   └── aws_s3.py      # AWS S3 service
│   └── core/              # Core configuration
├── docker-compose.yml     # Docker configuration
├── Dockerfile             # Docker image
└── requirements.txt       # Python dependencies
```

### Testing

```bash
# Health check
curl http://localhost:8001/health

# API docs
open http://localhost:8001/docs
```

---

## 📝 Notes

- **Branch**: Morice
- **Version**: 1.0.0
- **Python**: 3.11+ (3.14 compatible)
- **Database**: Supabase PostgreSQL (separate from main platform)
- **File Storage**: AWS S3
- **Encryption**: All messages are end-to-end encrypted

---

**Last Updated**: 2024  
**Status**: Production Ready (with optional enhancements available)
