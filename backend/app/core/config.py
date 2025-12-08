from typing import List, Union, Optional
from pydantic import BaseModel, field_validator, ConfigDict
import os
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseModel):
    model_config = ConfigDict(
        extra="ignore"
    )
    
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "MyFav API"
    
    # SECURITY
    SECRET_KEY: str = "c7d9fbef58c5ac4fe7d31e32a89e2c336468843c1c307177ab0ee55f54063115"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 jours
    PASSWORD_RESET_TOKEN_EXPIRE_MINUTES: int = 30  # 30 minutes
    
    # CORS
    BACKEND_CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:8000",
        "https://myhigh5.vercel.app",
        "https://mh5-rx4z.onrender.com",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8000"
    ]
    
    # DATABASE - URL complète depuis .env
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://user:password@localhost/myhigh5")
    
    @property
    def SQLALCHEMY_DATABASE_URI(self) -> str:
        return self.DATABASE_URL
    
    # REDIS
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    
    # STORAGE
    STORAGE_TYPE: str = "local"  # "local", "s3", "azure"
    LOCAL_STORAGE_PATH: str = "./media"
    S3_BUCKET_NAME: str = ""
    S3_REGION: str = ""
    
    # EMAIL
    SMTP_HOST: str = os.getenv("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER: str = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    SMTP_FROM_EMAIL: str = os.getenv("SMTP_FROM_EMAIL", "noreply@myhigh5.com")
    SMTP_FROM_NAME: str = os.getenv("SMTP_FROM_NAME", "MyHigh5")
    
    # FRONTEND
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:3000")
    
    # SHUFTI PRO KYC
    SHUFTI_CLIENT_ID: str = os.getenv("SHUFTI_CLIENT_ID", "")
    SHUFTI_SECRET_KEY: str = os.getenv("SHUFTI_SECRET_KEY", "")
    SHUFTI_CALLBACK_URL: str = os.getenv("SHUFTI_CALLBACK_URL", "")  # Webhook URL
    SHUFTI_REDIRECT_URL: str = os.getenv("SHUFTI_REDIRECT_URL", "")  # Redirect URL après vérification
    
    # CRYPTO PAYMENT
    CRYPTO_PAYMENT_API_KEY: str = os.getenv("CRYPTO_DEPOSIT_API_KEY", "")
    CRYPTO_PAYMENT_PUBLIC_KEY: str = os.getenv("CRYPTO_DEPOSIT_PUBLIC_KEY", "")
    CRYPTO_PAYMENT_IPN_SECRET: str = os.getenv("CRYPTO_PAYMENT_IPN_SECRET", "")  # Pour vérifier les webhooks
    CRYPTO_PAYMENT_API_URL: str = "https://api.nowpayments.io/v1"
    
    # CONTENT MODERATION (Sightengine)
    ENABLE_CONTENT_MODERATION: bool = os.getenv("ENABLE_CONTENT_MODERATION", "false").lower() == "true"
    SIGHTENGINE_API_USER: str = os.getenv("SIGHTENGINE_API_USER", "")
    SIGHTENGINE_API_KEY: str = os.getenv("SIGHTENGINE_API_KEY", "")
    
    # CONTENT RELEVANCE (OpenAI - optionnel pour analyse IA)
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    
    # Validation des origines CORS
    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, (list, str)):
            return v
        raise ValueError(v)

settings = Settings(
    DATABASE_URL=os.getenv("DATABASE_URL", "postgresql://user:password@localhost/myhigh5")
)
