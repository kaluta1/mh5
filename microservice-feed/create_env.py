#!/usr/bin/env python
"""
Script to create .env file for Feed Microservice
"""
import secrets
import base64
import os

def generate_env_file():
    """Generate .env file with secure random values"""
    
    # Generate secure random values
    salt = secrets.token_urlsafe(32)
    master_key = base64.b64encode(secrets.token_bytes(32)).decode()
    
    env_content = f"""# Feed Microservice Environment Variables
# IMPORTANT: Replace placeholder values with your actual credentials

# ============================================
# Database Configuration (Neon PostgreSQL)
# ============================================
DATABASE_URL=postgresql://neondb_owner:npg_Pqpdik54DZNa@ep-noisy-violet-adh359sw-pooler.c-2.us-east-1.aws.neon.tech/neondb?sslmode=require

# ============================================
# Legacy Supabase Configuration (Optional)
# ============================================
SUPABASE_URL=
SUPABASE_KEY=
SUPABASE_SERVICE_KEY=
SUPABASE_DB_URL=

# ============================================
# Storage Configuration
# ============================================
STORAGE_TYPE=local
LOCAL_STORAGE_PATH=./media
S3_BUCKET_NAME=
S3_REGION=us-east-1

# ============================================
# AWS S3 Configuration (Optional, if using S3)
# ============================================
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_REGION=us-east-1
AWS_S3_BUCKET=

# ============================================
# Main Platform API
# ============================================
MAIN_PLATFORM_API_URL=http://localhost:8000
MAIN_PLATFORM_API_KEY=
EDEN_API=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoiOTM2NWNkNDctYmU0Ny00NjMzLWI4NmEtOTkwMzA4ZDc4ZDc1IiwidHlwZSI6ImFwaV90b2tlbiJ9.iHSKGMvrshfMK8pEO64g948NJtJEUUwuMtIph5mMOcM

# ============================================
# Security
# ============================================
SECRET_KEY=wHuIbYWlqwiysmnwhYR4X18PRxWVdi71fkBs30Pb908zHVGmZN1724468801des9DFase22d1azfrdd
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=10080

# ============================================
# Encryption (Auto-generated secure values)
# ============================================
ENCRYPTION_KEY_DERIVATION_SALT={salt}
MASTER_ENCRYPTION_KEY={master_key}

# ============================================
# Email Configuration
# ============================================
RESEND_API_KEY=re_7y8kUpGM_A4cLUDkS3mmrYXkrNKnH2zsa
EMAIL_FROM=team@myhigh5.com
EMAIL_FROM_NAME=MyHigh5
FRONTEND_URL=https://myhigh5.com

# ============================================
# Crypto Payment
# ============================================
CRYPTO_DEPOSIT_PUBLIC_KEY=b585e113-343b-4979-ac17-f5b9251fc90b
CRYPTO_DEPOSIT_API_KEY=3KGE8AJ-FAK4KYD-P37KBW7-H43NVDG
CRYPTO_PAYMENT_IPN_SECRET=naMkUM45d1Do3WOtdj7N5ELM6vXReogz

# ============================================
# Content Moderation
# ============================================
SIGHTENGINE_API_KEY=KooPXryN4W57sHR7hDaiHoTTAtkGss8x
SIGHTENGINE_API_USER=1643677412
ENABLE_CONTENT_MODERATION=True
OPENAI_API_KEY=

# ============================================
# Server Configuration
# ============================================
HOST=0.0.0.0
PORT=8001
DEBUG=True
ENVIRONMENT=dev

# ============================================
# CORS
# ============================================
CORS_ORIGINS=http://localhost:3000,http://localhost:8000
BACKEND_CORS_ORIGINS=http://localhost:3000,http://localhost:8000,https://mh5.vercel.app/

# ============================================
# Redis
# ============================================
REDIS_HOST=redis-12349.c100.us-east-1-4.ec2.cloud.redislabs.com:12349
REDIS_PORT=12349
REDIS_URL=redis://default:1TiGEGEkCuYcOfM80XQgU8jltWrrCPea@redis-12349.c100.us-east-1-4.ec2.cloud.redislabs.com:12349

# ============================================
# Logging
# ============================================
LOG_LEVEL=INFO
"""
    
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    
    if os.path.exists(env_path):
        print(f"WARNING: .env file already exists at: {env_path}")
        response = input("Do you want to overwrite it? (yes/no): ")
        if response.lower() != 'yes':
            print("Cancelled. Existing .env file preserved.")
            return
    
    with open(env_path, 'w') as f:
        f.write(env_content)
    
    print(f"SUCCESS: .env file created successfully at: {env_path}")
    print("\n✅ Configuration includes:")
    print("   - Neon PostgreSQL database connection")
    print("   - Redis connection (RedisLabs)")
    print("   - Main platform API integration")
    print("   - Email service (Resend)")
    print("   - Content moderation (Sightengine)")
    print("   - Crypto payment integration")
    print("\n✅ Encryption keys have been auto-generated and are secure.")
    print("\n⚠️  NOTE: Some sensitive values are pre-filled. Review and update as needed.")

if __name__ == "__main__":
    generate_env_file()

