"""
Configuration settings for Feed Microservice
"""
from typing import List
from pydantic_settings import BaseSettings
from pydantic import Field
import os
from dotenv import load_dotenv

load_dotenv()


class Settings(BaseSettings):
    """Application settings"""
    
    # Database Configuration (Neon PostgreSQL)
    DATABASE_URL: str = Field(
        default="postgresql://user:password@localhost:5432/dbname",
        env="DATABASE_URL"
    )
    
    # Legacy Supabase Configuration (for backward compatibility)
    SUPABASE_URL: str = Field(default="", env="SUPABASE_URL")
    SUPABASE_KEY: str = Field(default="", env="SUPABASE_KEY")
    SUPABASE_SERVICE_KEY: str = Field(default="", env="SUPABASE_SERVICE_KEY")
    SUPABASE_DB_URL: str = Field(default="", env="SUPABASE_DB_URL")
    
    # AWS S3 Configuration
    AWS_ACCESS_KEY_ID: str = Field(default="", env="AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY: str = Field(default="", env="AWS_SECRET_ACCESS_KEY")
    AWS_REGION: str = Field(default="us-east-1", env="AWS_REGION")
    AWS_S3_BUCKET: str = Field(default="", env="AWS_S3_BUCKET")
    
    # Storage Configuration
    STORAGE_TYPE: str = Field(default="local", env="STORAGE_TYPE")  # local or s3
    LOCAL_STORAGE_PATH: str = Field(default="./media", env="LOCAL_STORAGE_PATH")
    S3_BUCKET_NAME: str = Field(default="", env="S3_BUCKET_NAME")
    S3_REGION: str = Field(default="us-east-1", env="S3_REGION")
    
    # Main Platform API
    MAIN_PLATFORM_API_URL: str = Field(default="http://localhost:8000", env="MAIN_PLATFORM_API_URL")
    MAIN_PLATFORM_API_KEY: str = Field(default="", env="MAIN_PLATFORM_API_KEY")
    EDEN_API: str = Field(default="", env="EDEN_API")
    
    # Security
    SECRET_KEY: str = Field(default="", env="SECRET_KEY")
    ALGORITHM: str = Field(default="HS256", env="ALGORITHM")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=10080, env="ACCESS_TOKEN_EXPIRE_MINUTES")
    
    # Encryption
    ENCRYPTION_KEY_DERIVATION_SALT: str = Field(
        default="change-this-in-production-min-32-chars-long-salt-value",
        env="ENCRYPTION_KEY_DERIVATION_SALT"
    )
    MASTER_ENCRYPTION_KEY: str = Field(default="", env="MASTER_ENCRYPTION_KEY")  # Base64 encoded 32-byte key
    
    # Email Configuration
    RESEND_API_KEY: str = Field(default="", env="RESEND_API_KEY")
    EMAIL_FROM: str = Field(default="team@myhigh5.com", env="EMAIL_FROM")
    EMAIL_FROM_NAME: str = Field(default="MyHigh5", env="EMAIL_FROM_NAME")
    FRONTEND_URL: str = Field(default="https://myhigh5.com", env="FRONTEND_URL")
    
    # Crypto Payment
    CRYPTO_DEPOSIT_PUBLIC_KEY: str = Field(default="", env="CRYPTO_DEPOSIT_PUBLIC_KEY")
    CRYPTO_DEPOSIT_API_KEY: str = Field(default="", env="CRYPTO_DEPOSIT_API_KEY")
    CRYPTO_PAYMENT_IPN_SECRET: str = Field(default="", env="CRYPTO_PAYMENT_IPN_SECRET")
    
    # Content Moderation
    SIGHTENGINE_API_KEY: str = Field(default="", env="SIGHTENGINE_API_KEY")
    SIGHTENGINE_API_USER: str = Field(default="", env="SIGHTENGINE_API_USER")
    ENABLE_CONTENT_MODERATION: bool = Field(default=False, env="ENABLE_CONTENT_MODERATION")
    
    # OpenAI
    OPENAI_API_KEY: str = Field(default="", env="OPENAI_API_KEY")
    
    # Server Configuration
    HOST: str = Field(default="0.0.0.0", env="HOST")
    PORT: int = Field(default=8001, env="PORT")
    DEBUG: bool = Field(default=False, env="DEBUG")
    ENVIRONMENT: str = Field(default="dev", env="ENVIRONMENT")
    
    # CORS
    CORS_ORIGINS: str = Field(
        default="http://localhost:3000,http://localhost:8000",
        env="CORS_ORIGINS"
    )
    BACKEND_CORS_ORIGINS: str = Field(
        default="http://localhost:3000,http://localhost:8000,https://mh5.vercel.app/",
        env="BACKEND_CORS_ORIGINS"
    )
    
    @property
    def cors_origins_list(self) -> List[str]:
        """Parse CORS_ORIGINS string into a list"""
        # Use BACKEND_CORS_ORIGINS if available, otherwise CORS_ORIGINS
        origins_str = self.BACKEND_CORS_ORIGINS if self.BACKEND_CORS_ORIGINS else self.CORS_ORIGINS
        if isinstance(origins_str, str):
            return [origin.strip() for origin in origins_str.split(",") if origin.strip()]
        return origins_str if isinstance(origins_str, list) else []
    
    @property
    def database_url(self) -> str:
        """Get database URL, preferring DATABASE_URL over SUPABASE_DB_URL"""
        if self.DATABASE_URL and not self.DATABASE_URL.startswith("postgresql://user:password"):
            return self.DATABASE_URL
        elif self.SUPABASE_DB_URL:
            return self.SUPABASE_DB_URL
        else:
            return self.DATABASE_URL
    
    # Redis Configuration
    REDIS_HOST: str = Field(default="localhost", env="REDIS_HOST")
    REDIS_PORT: int = Field(default=6379, env="REDIS_PORT")
    REDIS_URL: str = Field(default="redis://localhost:6379/0", env="REDIS_URL")
    
    # Logging
    LOG_LEVEL: str = Field(default="INFO", env="LOG_LEVEL")
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
