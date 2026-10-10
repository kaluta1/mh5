from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from app.services.wallet_validation import normalize_payout_currency, validate_payout_address


class UserWalletUpdate(BaseModel):
    usdt_wallet_address: str = Field(..., min_length=34, max_length=100)
    payout_currency: Optional[str] = Field(default="usdtbsc", max_length=20)
    # The member's current password authorises a payout destination change.
    current_password: str = Field(default="", max_length=256)

    @field_validator("payout_currency")
    @classmethod
    def normalize_currency(cls, v: Optional[str]) -> str:
        normalized = normalize_payout_currency(v)
        if normalized != "usdtbsc":
            raise ValueError(
                "Only USDT on BSC (BEP20) is enabled until separate network ledger accounts are configured."
            )
        return normalized

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
    pending_commissions_paid: int = 0      # always 0: saving a wallet never pays anything
    supported_currencies: List[str] = ["usdtbsc"]
    # MISSING / INVALID / UNVERIFIED / ON_HOLD / VERIFIED (cashout_service.wallet_state)
    wallet_status: Optional[str] = None
    payable_from: Optional[str] = None
    # A change waiting for its email confirmation (masked), if any.
    pending_wallet: Optional[dict] = None
    # Set by a save: the change needs the emailed link / whether that email was queued.
    confirmation_required: bool = False
    confirmation_email_sent: Optional[bool] = None
    hold_hours: Optional[int] = None

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


class CashoutMethodUpdate(BaseModel):
    method: str = Field(..., max_length=10, description="CRYPTO or USD")


class UsdCashoutRequest(BaseModel):
    # Optional: USD Cashout pays the whole available balance; a different amount is refused.
    amount: Optional[Decimal] = Field(default=None, gt=0)
    # Where the member wants to be paid (required when the administrator asks for it).
    destination: Optional[str] = Field(default=None, max_length=500)


class PayoutWalletConfirm(BaseModel):
    token: str = Field(..., min_length=20, max_length=200)


class CashoutCancel(BaseModel):
    reason: str = Field(default="", max_length=500)


class CashoutSettle(BaseModel):
    reference: str = Field(..., min_length=3, max_length=200)


class CashoutNetworkFee(BaseModel):
    # The fee read from the provider's statement, in the payout currency. Zero = none was charged.
    amount: Decimal = Field(..., ge=0, max_digits=18, decimal_places=8)
    reference: str = Field(..., min_length=3, max_length=200)


class CashoutResolve(BaseModel):
    outcome: str = Field(..., max_length=10, description="SENT or NOT_SENT")
    reference: Optional[str] = Field(default=None, max_length=200)


class WithdrawPreviewResponse(BaseModel):
    available_to_withdraw: float
    minimum_withdrawal: float = 100.0
    fee: float
    net_amount: float
    wallet_configured: bool
    payout_currency: Optional[str] = None
    # Phase 10: the member's OWN withdrawal eligibility (ALLOWED / HOLD /
    # REVIEW_REQUIRED) and a safe next step; never a reason code.
    eligibility_status: Optional[str] = None
    eligibility_next_step: Optional[str] = None
    cashout_method: Optional[str] = None


class WithdrawResponse(BaseModel):
    gross_amount: float
    fee: float
    net_amount: float
    payout_reference: Optional[str] = None
    commissions_marked_paid: int = 0
    status: str = "processing"
