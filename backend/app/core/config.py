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
