from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from app.services.wallet_validation import normalize_payout_currency, validate_payout_address


class UserWalletUpdate(BaseModel):
    usdt_wallet_address: str = Field(..., min_length=34, max_length=100)
    payout_currency: Optional[str] = Field(default="usdtbsc", max_length=20)

    @field_validator("payout_currency")
    @classmethod
    def normalize_currency(cls, v: Optional[str]) -> str:
        return normalize_payout_currency(v)

    @model_validator(mode="after")
    def validate_wallet_pair(self) -> "UserWalletUpdate":
        self.usdt_wallet_address = validate_payout_address(
            self.usdt_wallet_address, self.payout_currency
        )
        return self


class UserWalletResponse(BaseModel):
    usdt_wallet_address: Optional[str] = None
    payout_currency: Optional[str] = None
    wallet_configured: bool = False
    pending_commissions_paid: int = 0
    supported_currencies: List[str] = ["usdtbsc", "usdterc20", "usdttrc20"]

    class Config:
        from_attributes = True


class WithdrawRequest(BaseModel):
    amount: Decimal = Field(..., gt=0, description="Gross withdrawal amount in USD (min $100)")

    @field_validator("amount")
    @classmethod
    def validate_minimum(cls, v: Decimal) -> Decimal:
        if v < Decimal("100"):
            raise ValueError("Minimum withdrawal is $100.")
        return v


class WithdrawPreviewResponse(BaseModel):
    available_to_withdraw: float
    minimum_withdrawal: float = 100.0
    fee: float
    net_amount: float
    wallet_configured: bool
    payout_currency: Optional[str] = None


class WithdrawResponse(BaseModel):
    gross_amount: float
    fee: float
    net_amount: float
    payout_reference: Optional[str] = None
    commissions_marked_paid: int = 0
    status: str = "processing"
