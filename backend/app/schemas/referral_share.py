from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class ShareLinkCreate(BaseModel):
    url: str = Field(..., min_length=8, max_length=2048)


class ShareLinkResponse(BaseModel):
    short_code: str
    short_url: str
    destination_url: str


class ReferralConversionCreate(BaseModel):
    conversion_type: Literal["signup", "subscription", "purchase", "newsletter", "other"]
    conversion_reference: Optional[str] = Field(default=None, max_length=255)
    metadata: Optional[dict[str, Any]] = None


class ReferralConversionResponse(BaseModel):
    recorded: bool = True
