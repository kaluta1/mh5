# Feed Microservice - Production Deployment Guide

This document outlines all the critical configurations, security measures, and optimizations needed for production deployment.

---

## 🔒 Security Enhancements

### 1. Environment Variables & Secrets Management

**❌ DO NOT:**
- Hardcode secrets in code
- Commit `.env` files to git
- Use placeholder values

**✅ DO:**
- Use a secrets management service:
  - **AWS Secrets Manager** (if using AWS)
  - **HashiCorp Vault**
  - **Azure Key Vault** (if using Azure)
  - **Google Secret Manager** (if using GCP)
  - **Environment variables** (for containerized deployments)

**Required Secrets:**
```env
# Supabase - Use production credentials
SUPABASE_URL=https://your-production-project.supabase.co
SUPABASE_KEY=production-anon-key
SUPABASE_SERVICE_KEY=production-service-role-key
SUPABASE_DB_URL=postgresql://postgres:[STRONG_PASSWORD]@db.[PROJECT-REF].supabase.co:5432/postgres

# AWS S3 - Use production credentials
AWS_ACCESS_KEY_ID=production-access-key
AWS_SECRET_ACCESS_KEY=production-secret-key
AWS_REGION=us-east-1
AWS_S3_BUCKET=production-bucket-name

# Encryption - MUST be unique and secure
ENCRYPTION_KEY_DERIVATION_SALT=generate-unique-32-char-salt
MASTER_ENCRYPTION_KEY=generate-unique-base64-32-byte-key

# Main Platform
MAIN_PLATFORM_API_URL=https://api.yourdomain.com
MAIN_PLATFORM_API_KEY=production-api-key

# Server
HOST=0.0.0.0
PORT=8001
DEBUG=False  # CRITICAL: Must be False in production
CORS_ORIGINS=https://yourdomain.com,https://www.yourdomain.com
REDIS_URL=redis://production-redis:6379/0
LOG_LEVEL=WARNING  # Reduce verbosity in production
```

### 2. HTTPS/TLS Configuration

**✅ Required:**
- Enable HTTPS/TLS for all API endpoints
- Use reverse proxy (Nginx, Traefik, or AWS ALB) with SSL certificates
- Redirect all HTTP traffic to HTTPS
- Use Let's Encrypt or commercial SSL certificates

**Example Nginx Configuration:**
```nginx
server {
    listen 443 ssl http2;
    server_name api.yourdomain.com;
    
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
    
    location / {
        proxy_pass http://localhost:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### 3. Authentication & Authorization

**✅ Add:**
- Rate limiting (prevent brute force attacks)
- API key rotation mechanism
- Token expiration and refresh
- IP whitelisting for admin endpoints (optional)
- Request signing for sensitive operations

**Rate Limiting Example:**
```python
# Add to main.py
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Apply to endpoints
@router.post("/send")
@limiter.limit("10/minute")
async def send_message(...):
    ...
```

### 4. Encryption Key Management

**✅ Production Requirements:**
- Store `MASTER_ENCRYPTION_KEY` in secure key management service
- Implement key rotation policy
- Never log encryption keys
- Use hardware security modules (HSM) for critical deployments
- Implement key backup and recovery procedures

**Key Rotation Strategy:**
- Rotate master key quarterly
- Support multiple key versions during transition
- Re-encrypt all private keys when rotating master key

---

## 🗄️ Database Configuration

### 1. Supabase Production Setup

**✅ Required:**
- Use production Supabase project (separate from development)
- Enable connection pooling (Supabase provides this)
- Configure database backups
- Set up read replicas for high availability (if needed)
- Monitor database performance

**Connection String:**
```env
# Use connection pooler for better performance
SUPABASE_DB_URL=postgresql://postgres.[PROJECT-REF]:[PASSWORD]@aws-0-[REGION].pooler.supabase.com:6543/postgres
```

**Database Optimizations:**
- Add indexes on frequently queried columns:
  ```sql
  CREATE INDEX idx_messages_conversation_id ON private_messages(conversation_id);
  CREATE INDEX idx_messages_sender_id ON private_messages(sender_id);
  CREATE INDEX idx_posts_user_id ON posts(user_id);
  CREATE INDEX idx_posts_created_at ON posts(created_at DESC);
  CREATE INDEX idx_group_members_user_id ON group_members(user_id);
  ```

### 2. Database Migrations

**✅ Production Process:**
- Test migrations in staging first
- Use migration versioning
- Create database backups before migrations
- Have rollback plan ready

```bash
# Production migration process
1. Backup database
2. Test migration in staging
3. Schedule maintenance window
4. Run migration: alembic upgrade head
5. Verify application functionality
6. Monitor for issues
```

---

## ☁️ AWS S3 Configuration

### 1. Production S3 Setup

**✅ Required:**
- Use separate production bucket
- Enable versioning for important files
- Configure lifecycle policies (archive old files)
- Set up cross-region replication (for disaster recovery)
- Enable server-side encryption (SSE-S3 or SSE-KMS)

**Bucket Policy Example:**
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::ACCOUNT:user/s3-service-user"
      },
      "Action": [
        "s3:PutObject",
        "s3:GetObject",
        "s3:DeleteObject"
      ],
      "Resource": "arn:aws:s3:::production-bucket/*"
    }
  ]
}
```

**CORS Configuration:**
```json
[
  {
    "AllowedHeaders": ["*"],
    "AllowedMethods": ["GET", "PUT", "POST", "DELETE"],
    "AllowedOrigins": ["https://yourdomain.com"],
    "ExposeHeaders": ["ETag"],
    "MaxAgeSeconds": 3000
  }
]
```

### 2. CDN Integration

**✅ Recommended:**
- Use CloudFront (AWS) or similar CDN
- Cache static media files
- Reduce S3 costs and improve performance
- Configure proper cache headers

---

## 🐳 Docker & Containerization

### 1. Production Dockerfile

**✅ Enhancements:**
```dockerfile
# Use specific Python version (not latest)
FROM python:3.11-slim

# Create non-root user
RUN useradd -m -u 1000 appuser && \
    mkdir -p /app && \
    chown -R appuser:appuser /app

WORKDIR /app

# Install only production dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY --chown=appuser:appuser . .

# Switch to non-root user
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8001/health', timeout=5)"

# Run as non-root
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "4"]
```

### 2. Docker Compose Production

**✅ Add:**
- Resource limits
- Restart policies
- Health checks
- Logging configuration
- Network security

```yaml
version: '3.8'

services:
  feed-microservice:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: feed-microservice-prod
    restart: always
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G
        reservations:
          cpus: '1'
          memory: 1G
    environment:
      - SUPABASE_URL=${SUPABASE_URL}
      # ... other env vars from secrets
    healthcheck:
      test: ["CMD", "python", "-c", "import requests; requests.get('http://localhost:8001/health')"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
    networks:
      - myhigh5-network
```

---

## 📊 Monitoring & Logging

### 1. Application Logging

**✅ Add:**
- Structured logging (JSON format)
- Log aggregation service:
  - **AWS CloudWatch**
  - **Datadog**
  - **Sentry** (for error tracking)
  - **ELK Stack** (Elasticsearch, Logstash, Kibana)
- Log levels: WARNING in production (reduce noise)
- Sensitive data filtering (never log passwords, keys, tokens)

**Structured Logging Example:**
```python
import structlog

logger = structlog.get_logger()
logger.info("message_sent", 
    user_id=user_id, 
    recipient_id=recipient_id,
    message_id=message.id,
    timestamp=datetime.utcnow().isoformat()
)
```

### 2. Application Monitoring

**✅ Required:**
- Health check endpoint monitoring
- API response time monitoring
- Error rate tracking
- Database connection pool monitoring
- Memory and CPU usage
- Request rate monitoring

**Tools:**
- **Prometheus** + **Grafana**
- **New Relic**
- **Datadog APM**
- **AWS CloudWatch Metrics**

### 3. Error Tracking

**✅ Add:**
- Sentry integration for error tracking
- Alert on critical errors
- Error rate thresholds
- Stack trace collection

**Sentry Integration:**
```python
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration

sentry_sdk.init(
    dsn="your-sentry-dsn",
    integrations=[FastApiIntegration()],
    traces_sample_rate=0.1,  # 10% of transactions
    environment="production"
)
```

---

## ⚡ Performance Optimizations

### 1. Caching

**✅ Production Caching:**
- Use Redis for production (not in-memory cache)
- Cache user data from main platform
- Cache feed results (with TTL)
- Cache encryption keys (with invalidation)
- Implement cache warming strategies

**Redis Configuration:**
```python
import redis
from redis import ConnectionPool

redis_pool = ConnectionPool(
    host='production-redis',
    port=6379,
    db=0,
    max_connections=50,
    decode_responses=True
)
redis_client = redis.Redis(connection_pool=redis_pool)
```

### 2. Database Connection Pooling

**✅ Already Configured:**
- Connection pooling in SQLAlchemy
- Adjust pool size based on load:
  ```python
  pool_size=20,  # Increase for production
  max_overflow=40,  # Increase for production
  ```

### 3. Async Operations

**✅ Optimize:**
- Use async database operations
- Implement background tasks for heavy operations
- Use message queues (Celery, RabbitMQ) for long-running tasks

### 4. API Response Optimization

**✅ Add:**
- Response compression (gzip)
- Pagination for list endpoints
- Field selection (only return needed fields)
- Response caching headers

---

## 🔄 High Availability & Scalability

### 1. Load Balancing

**✅ Required:**
- Use load balancer (AWS ALB, Nginx, Traefik)
- Multiple application instances
- Health checks for instance removal
- Session stickiness (if needed)

### 2. Auto-Scaling

**✅ Configure:**
- Horizontal scaling based on CPU/memory
- Auto-scaling groups (AWS, Kubernetes)
- Minimum 2 instances for high availability
- Scale based on request rate

### 3. Database High Availability

**✅ Configure:**
- Supabase provides high availability
- Set up read replicas if needed
- Database connection failover
- Regular backups

---

## 🔐 Security Best Practices

### 1. Input Validation

**✅ Add:**
- Validate all user inputs
- Sanitize file uploads
- Check file types and sizes
- Prevent SQL injection (SQLAlchemy handles this)
- Prevent XSS attacks

### 2. API Security

**✅ Implement:**
- Rate limiting per user/IP
- Request size limits
- Timeout configurations
- CORS properly configured
- API versioning

### 3. Data Protection

**✅ Ensure:**
- All messages encrypted (already implemented)
- Private keys encrypted at rest (already implemented)
- Secure key storage
- Regular security audits
- Penetration testing

---

## 📦 Deployment Strategy

### 1. CI/CD Pipeline

**✅ Set Up:**
- Automated testing before deployment
- Build Docker images
- Push to container registry
- Deploy to staging first
- Automated deployment to production
- Rollback capability

**Example GitHub Actions:**
```yaml
name: Deploy to Production

on:
  push:
    branches: [Morice]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Build Docker image
        run: docker build -t feed-microservice:${{ github.sha }} .
      - name: Push to registry
        run: docker push feed-microservice:${{ github.sha }}
      - name: Deploy
        run: |
          # Deployment commands
```

### 2. Blue-Green Deployment

**✅ Recommended:**
- Deploy new version alongside old
- Switch traffic gradually
- Easy rollback if issues occur
- Zero-downtime deployments

### 3. Canary Deployment

**✅ Alternative:**
- Deploy to small percentage of users first
- Monitor for issues
- Gradually increase traffic
- Full rollout if successful

---

## 🗄️ Backup & Disaster Recovery

### 1. Database Backups

**✅ Configure:**
- Automated daily backups
- Point-in-time recovery
- Test backup restoration regularly
- Store backups in separate region

### 2. Disaster Recovery Plan

**✅ Document:**
- Recovery time objective (RTO)
- Recovery point objective (RPO)
- Backup restoration procedures
- Failover procedures
- Communication plan

---

## 📋 Production Checklist

### Pre-Deployment

- [ ] All environment variables configured
- [ ] Secrets stored in secure management service
- [ ] Database migrations tested and ready
- [ ] SSL certificates configured
- [ ] Monitoring and logging set up
- [ ] Error tracking configured
- [ ] Load balancer configured
- [ ] Auto-scaling configured
- [ ] Backup strategy in place
- [ ] Disaster recovery plan documented

### Security

- [ ] HTTPS/TLS enabled
- [ ] Rate limiting configured
- [ ] Input validation implemented
- [ ] CORS properly configured
- [ ] API authentication working
- [ ] Encryption keys secured
- [ ] No debug mode enabled
- [ ] Sensitive data not logged

### Performance

- [ ] Redis caching configured
- [ ] Database indexes created
- [ ] Connection pooling optimized
- [ ] CDN configured (if applicable)
- [ ] Response compression enabled
- [ ] Load testing completed

### Monitoring

- [ ] Health checks configured
- [ ] Metrics collection set up
- [ ] Log aggregation working
- [ ] Error tracking active
- [ ] Alerting configured
- [ ] Dashboard created

### Documentation

- [ ] API documentation updated
- [ ] Runbook created
- [ ] Incident response plan
- [ ] Contact information documented

---

## 🚀 Deployment Commands

### Initial Production Deployment

```bash
# 1. Set environment variables (from secrets manager)
export SUPABASE_DB_URL="..."
export AWS_ACCESS_KEY_ID="..."
# ... etc

# 2. Run database migrations
alembic upgrade head

# 3. Build Docker image
docker build -t feed-microservice:latest .

# 4. Tag and push to registry
docker tag feed-microservice:latest registry.example.com/feed-microservice:v1.0.0
docker push registry.example.com/feed-microservice:v1.0.0

# 5. Deploy (example with docker-compose)
docker-compose -f docker-compose.prod.yml up -d

# 6. Verify deployment
curl https://api.yourdomain.com/health
```

### Update Deployment

```bash
# 1. Pull latest code
git pull origin Morice

# 2. Run migrations (if any)
alembic upgrade head

# 3. Build new image
docker build -t feed-microservice:latest .

# 4. Deploy with zero downtime
docker-compose -f docker-compose.prod.yml up -d --no-deps feed-microservice

# 5. Verify
curl https://api.yourdomain.com/health
```

---

## 📊 Production Metrics to Monitor

### Application Metrics
- Request rate (requests/second)
- Response time (p50, p95, p99)
- Error rate (4xx, 5xx)
- Active connections
- Memory usage
- CPU usage

### Database Metrics
- Connection pool usage
- Query performance
- Database size
- Replication lag (if applicable)

### Infrastructure Metrics
- Server CPU/Memory
- Network throughput
- Disk I/O
- Container health

---

## 🔧 Production Environment Variables Summary

```env
# CRITICAL: All values must be production-ready

# Supabase (Production Project)
SUPABASE_URL=https://production-project.supabase.co
SUPABASE_KEY=production-anon-key
SUPABASE_SERVICE_KEY=production-service-key
SUPABASE_DB_URL=postgresql://postgres:[PASSWORD]@db.[PROJECT-REF].supabase.co:5432/postgres

# AWS S3 (Production Bucket)
AWS_ACCESS_KEY_ID=production-access-key
AWS_SECRET_ACCESS_KEY=production-secret-key
AWS_REGION=us-east-1
AWS_S3_BUCKET=production-bucket

# Main Platform (Production URL)
MAIN_PLATFORM_API_URL=https://api.yourdomain.com
MAIN_PLATFORM_API_KEY=production-api-key

# Encryption (Unique Production Keys)
ENCRYPTION_KEY_DERIVATION_SALT=unique-production-salt-32-chars
MASTER_ENCRYPTION_KEY=unique-production-master-key-base64

# Server (Production Settings)
HOST=0.0.0.0
PORT=8001
DEBUG=False  # MUST be False
CORS_ORIGINS=https://yourdomain.com,https://www.yourdomain.com
REDIS_URL=redis://production-redis:6379/0
LOG_LEVEL=WARNING  # Reduce verbosity
```

---

## ⚠️ Critical Production Warnings

1. **NEVER** set `DEBUG=True` in production
2. **NEVER** commit `.env` files or secrets
3. **ALWAYS** use HTTPS in production
4. **ALWAYS** enable rate limiting
5. **ALWAYS** monitor error rates
6. **ALWAYS** have backup and recovery plan
7. **ALWAYS** test migrations in staging first
8. **ALWAYS** use production-grade secrets management

---

**Last Updated**: 2024  
**Branch**: Morice  
**Version**: 1.0.0

