from typing import List, Union, Optional
from pathlib import Path
from pydantic import BaseModel, field_validator, ConfigDict
import os
from dotenv import load_dotenv

# Always load backend/.env (this file lives in backend/app/core/). Using load_dotenv()
# without a path only reads from the process cwd, so starting uvicorn from the repo
# root would skip DATABASE_URL and other vars — wrong DB / login appears "broken".
_BACKEND_DIR = Path(__file__).resolve().parents[2]
# utf-8-sig strips BOM from Windows Notepad–saved .env files
load_dotenv(_BACKEND_DIR / ".env", encoding="utf-8-sig")
load_dotenv(_BACKEND_DIR / ".env.local", override=True, encoding="utf-8-sig")


def _first_nonempty_env(*keys: str) -> str:
    """First set env var among keys (common aliases); strip whitespace from value."""
    for k in keys:
        v = os.getenv(k)
        if v is not None and str(v).strip() != "":
            return str(v).strip()
    return ""


class Settings(BaseModel):
    model_config = ConfigDict(
        extra="ignore"
    )
    
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "High5 API"
    
    # SECURITY
    SECRET_KEY: str = os.getenv("SECRET_KEY", "c7d9fbef58c5ac4fe7d31e32a89e2c336468843c1c307177ab0ee55f54063115")
    ALGORITHM: str = os.getenv("ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", str(60 * 24 * 7)))  # Default: 7 jours
    PASSWORD_RESET_TOKEN_EXPIRE_MINUTES: int = 30  # 30 minutes
    
    # CORS - Read from env, fallback to defaults
    _cors_origins_env: str = os.getenv("BACKEND_CORS_ORIGINS", "")
    BACKEND_CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:8000",
        "https://myhigh5.vercel.app",
        "https://frontend-rho-eight-72.vercel.app",  # Vercel frontend
        "https://mh5-rx4z.onrender.com",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8000"
    ] if not _cors_origins_env else [origin.strip() for origin in _cors_origins_env.split(",") if origin.strip()]
    
    # DATABASE - URL complète depuis .env
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://user:password@localhost/myhigh5")
    
    @property
    def SQLALCHEMY_DATABASE_URI(self) -> str:
        return self.DATABASE_URL
    
    # REDIS
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_URL: Optional[str] = os.getenv("REDIS_URL", None)
    
    # Parse REDIS_HOST if it contains port (format: host:port)
    @property
    def REDIS_HOST_ONLY(self) -> str:
        """Extract host from REDIS_HOST if it contains port"""
        if ":" in self.REDIS_HOST:
            return self.REDIS_HOST.split(":")[0]
        return self.REDIS_HOST
    
    @property
    def REDIS_PORT_FROM_HOST(self) -> int:
        """Extract port from REDIS_HOST if it contains port"""
        if ":" in self.REDIS_HOST:
            try:
                return int(self.REDIS_HOST.split(":")[1])
            except (ValueError, IndexError):
                return self.REDIS_PORT
        return self.REDIS_PORT
    
    # STORAGE
    STORAGE_TYPE: str = os.getenv("STORAGE_TYPE", "local")  # "local", "s3", "azure"
    LOCAL_STORAGE_PATH: str = os.getenv("LOCAL_STORAGE_PATH", "./media")
    S3_BUCKET_NAME: str = os.getenv("AWS_S3_BUCKET", "")
    S3_REGION: str = os.getenv("AWS_REGION", "us-east-1")
    AWS_ACCESS_KEY_ID: str = os.getenv("AWS_ACCESS_KEY_ID", "")
    AWS_SECRET_ACCESS_KEY: str = os.getenv("AWS_SECRET_ACCESS_KEY", "")
    AWS_S3_BUCKET: str = os.getenv("AWS_S3_BUCKET", "")
    
    # EMAIL - Resend API
    RESEND_API_KEY: str = os.getenv("RESEND_API_KEY", "")
    EMAIL_FROM: str = os.getenv("EMAIL_FROM", "MyHigh5 <infos@myhigh5.com>")
    EMAIL_FROM_NAME: str = os.getenv("EMAIL_FROM_NAME", "MyHigh5")
    
    # SMTP (fallback - deprecated)
    SMTP_HOST: str = os.getenv("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER: str = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    SMTP_FROM_EMAIL: str = os.getenv("SMTP_FROM_EMAIL", "infos@myhigh5.com")
    SMTP_FROM_NAME: str = os.getenv("SMTP_FROM_NAME", "MyHigh5")
    
    # FRONTEND
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:3000")
    
    # SHUFTI PRO KYC (accept UPPER_SNAKE and lowercase aliases from .env)
    SHUFTI_CLIENT_ID: str = _first_nonempty_env("SHUFTI_CLIENT_ID", "shufti_client_id")
    SHUFTI_SECRET_KEY: str = _first_nonempty_env("SHUFTI_SECRET_KEY", "shufti_secret_key")
    SHUFTI_CALLBACK_URL: str = _first_nonempty_env("SHUFTI_CALLBACK_URL", "shufti_callback_url")
    SHUFTI_REDIRECT_URL: str = _first_nonempty_env("SHUFTI_REDIRECT_URL", "shufti_redirect_url")
    
    # ============================================
    # Reown/WalletConnect Configuration
    # ============================================
    REOWN_PROJECT_ID: str = os.getenv("REOWN_PROJECT_ID", "")
    
    # ============================================
    # BSC On-chain Payment Configuration
    # ============================================
    BSC_RPC_URL: str = os.getenv("BSC_RPC_URL", "https://bsc-dataseed.binance.org")
    BSC_CHAIN_ID: int = int(os.getenv("BSC_CHAIN_ID", "56"))
    BSC_PAYMENT_CONTRACT: str = os.getenv("BSC_PAYMENT_CONTRACT", "0x12Ccb74E7A8B8f0fDc14e55A82C8693145e36EdA")
    BSC_CONFIRMATIONS: int = int(os.getenv("BSC_CONFIRMATIONS", "1"))
    BSC_EXPLORER_URL: str = os.getenv("BSC_EXPLORER_URL", "https://bscscan.com")
    BSC_USDT_ADDRESS: str = os.getenv("BSC_USDT_ADDRESS", "0x55d398326f99059fF775485246999027B3197955")
    BSC_USDT_DECIMALS: int = int(os.getenv("BSC_USDT_DECIMALS", "18"))
    
    # CONTENT MODERATION (Sightengine)
    ENABLE_CONTENT_MODERATION: bool = os.getenv("ENABLE_CONTENT_MODERATION", "false").lower() == "true"
    SIGHTENGINE_API_USER: str = os.getenv("SIGHTENGINE_API_USER", "")
    SIGHTENGINE_API_KEY: str = os.getenv("SIGHTENGINE_API_KEY", "")
    
    # CONTENT RELEVANCE (OpenAI - optionnel pour analyse IA)
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    
    # EDEN API (if needed)
    EDEN_API: str = os.getenv("EDEN_API", "")
    
    # ENCRYPTION (E2E Messaging)
    MASTER_ENCRYPTION_KEY: str = os.getenv("MASTER_ENCRYPTION_KEY", "")
    ENCRYPTION_KEY_DERIVATION_SALT: str = os.getenv("ENCRYPTION_KEY_DERIVATION_SALT", "default-salt-change-in-production")
    
    # Validation des origines CORS
    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str) and not v.startswith("["):
            # Split by comma and strip whitespace
            origins = [i.strip() for i in v.split(",") if i.strip()]
            return origins
        elif isinstance(v, list):
            return [str(i).strip() for i in v if str(i).strip()]
        elif isinstance(v, str) and v.startswith("["):
            # Handle JSON-like string
            import json
            try:
                return json.loads(v)
            except:
                return [v]
        return v if isinstance(v, list) else [v]

# Initialize settings - will load from .env file via load_dotenv() at top
settings = Settings()
