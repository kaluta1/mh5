from datetime import datetime
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, Field


class ShareLinkCreate(BaseModel):
    url: str = Field(..., min_length=8, max_length=2048)
    # Older share buttons omit it and always shared an invitation link; the Shorten a Link form
    # always sends it (default OFF there). Never an id or a code: the invitation is the caller's own.
    include_invitation: bool = True


class ShareLinkResponse(BaseModel):
    short_code: str
    short_url: str
    destination_url: str
    id: Optional[int] = None
    include_invitation: bool = True
    is_active: bool = True
    created_at: Optional[datetime] = None
    disabled_at: Optional[datetime] = None
    reused: bool = False


class ShareLinkList(BaseModel):
    items: List[ShareLinkResponse]
    total: int


class InvitationStatus(BaseModel):
    """Whether the caller's invitation links can sponsor new members now (the registration rule)."""
    eligible: bool
    # null when eligible; NO_CODE, KYC_NOT_STARTED, KYC_IN_PROGRESS, KYC_REJECTED or RESTRICTED
    reason: Optional[str] = None
    message: Optional[str] = None


class ReferralConversionCreate(BaseModel):
    conversion_type: Literal["signup", "subscription", "purchase", "newsletter", "other"]
    conversion_reference: Optional[str] = Field(default=None, max_length=255)
    metadata: Optional[dict[str, Any]] = None


class ReferralConversionResponse(BaseModel):
    recorded: bool = True
