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
# Supabase Configuration
# ============================================
# Get these from your Supabase project: https://supabase.com
SUPABASE_URL=https://placeholder.supabase.co
SUPABASE_KEY=placeholder-anon-key
SUPABASE_SERVICE_KEY=placeholder-service-role-key
SUPABASE_DB_URL=postgresql://postgres:password@localhost:5432/postgres

# ============================================
# AWS S3 Configuration
# ============================================
# Get these from your AWS account
AWS_ACCESS_KEY_ID=placeholder-access-key-id
AWS_SECRET_ACCESS_KEY=placeholder-secret-access-key
AWS_REGION=us-east-1
AWS_S3_BUCKET=placeholder-bucket-name

# ============================================
# Main Platform API
# ============================================
MAIN_PLATFORM_API_URL=http://localhost:8000
MAIN_PLATFORM_API_KEY=

# ============================================
# Encryption (Auto-generated secure values)
# ============================================
ENCRYPTION_KEY_DERIVATION_SALT={salt}
MASTER_ENCRYPTION_KEY={master_key}

# ============================================
# Server Configuration
# ============================================
HOST=0.0.0.0
PORT=8001
DEBUG=True

# ============================================
# CORS
# ============================================
CORS_ORIGINS=http://localhost:3000,http://localhost:8000

# ============================================
# Redis
# ============================================
REDIS_URL=redis://localhost:6379/0

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
    print("\nIMPORTANT: Update the placeholder values with your actual credentials:")
    print("   - SUPABASE_URL, SUPABASE_KEY, SUPABASE_DB_URL")
    print("   - AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_S3_BUCKET")
    print("\nSUCCESS: Encryption keys have been auto-generated and are secure.")

if __name__ == "__main__":
    generate_env_file()

