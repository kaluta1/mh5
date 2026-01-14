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
    
    # Supabase Configuration
    SUPABASE_URL: str = Field(default="https://placeholder.supabase.co", env="SUPABASE_URL")
    SUPABASE_KEY: str = Field(default="placeholder-key", env="SUPABASE_KEY")
    SUPABASE_SERVICE_KEY: str = Field(default="placeholder-service-key", env="SUPABASE_SERVICE_KEY")
    SUPABASE_DB_URL: str = Field(default="postgresql://user:password@localhost:5432/dbname", env="SUPABASE_DB_URL")
    
    # AWS S3 Configuration
    AWS_ACCESS_KEY_ID: str = Field(default="placeholder-access-key", env="AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY: str = Field(default="placeholder-secret-key", env="AWS_SECRET_ACCESS_KEY")
    AWS_REGION: str = Field(default="us-east-1", env="AWS_REGION")
    AWS_S3_BUCKET: str = Field(default="placeholder-bucket", env="AWS_S3_BUCKET")
    
    # Main Platform API
    MAIN_PLATFORM_API_URL: str = Field(default="http://localhost:8000", env="MAIN_PLATFORM_API_URL")
    MAIN_PLATFORM_API_KEY: str = Field(default="", env="MAIN_PLATFORM_API_KEY")
    
    # Encryption
    ENCRYPTION_KEY_DERIVATION_SALT: str = Field(default="change-this-in-production-min-32-chars-long-salt-value", env="ENCRYPTION_KEY_DERIVATION_SALT")
    MASTER_ENCRYPTION_KEY: str = Field(default="", env="MASTER_ENCRYPTION_KEY")  # Base64 encoded 32-byte key
    
    # Server Configuration
    HOST: str = Field(default="0.0.0.0", env="HOST")
    PORT: int = Field(default=8001, env="PORT")
    DEBUG: bool = Field(default=False, env="DEBUG")
    
    # CORS
    CORS_ORIGINS: str = Field(
        default="http://localhost:3000,http://localhost:8000",
        env="CORS_ORIGINS"
    )
    
    @property
    def cors_origins_list(self) -> List[str]:
        """Parse CORS_ORIGINS string into a list"""
        if isinstance(self.CORS_ORIGINS, str):
            return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]
        return self.CORS_ORIGINS if isinstance(self.CORS_ORIGINS, list) else []
    
    # Redis
    REDIS_URL: str = Field(default="redis://localhost:6379/0", env="REDIS_URL")
    
    # Logging
    LOG_LEVEL: str = Field(default="INFO", env="LOG_LEVEL")
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
