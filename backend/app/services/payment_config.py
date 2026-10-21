"""Finance & Payments: the ONE typed configuration of the payment provider and
of the dual cashout. Every payment service reads its thresholds, fees, limits,
switches and provider credentials from here; nothing else holds a copy.

Precedence (deliberate, and the same everywhere)
------------------------------------------------
1. Business settings (thresholds, fees, limits, switches) live in the
   payment_settings row. While that row does not exist the built-in defaults
   apply, seeded from the earlier environment values (CRYPTO_CASHOUT_MIN_USD,
   USD_CASHOUT_MIN_USD, PAYOUT_WALLET_HOLD_HOURS, ...), so a deployment keeps
   the values it ran with. The row is created by the first Admin change; from
   then on those environment values are ignored.
2. Two SERVER master switches stay in the environment and cannot be overridden
   from the Admin Panel: CRYPTO_AUTO_PAYOUT_ENABLED and
   USD_CASHOUT_SETTLEMENT_ENABLED. Money leaves only when the server switch AND
   the Admin switch are both on. NOWPAYMENTS_SANDBOX also stays on the server.
3. Provider credentials come from exactly one place per group (pay-in, payout):
   ENVIRONMENT (the default: what production uses today) or DATABASE (stored
   encrypted, see payment_crypto). The two are never mixed, and a credential
   missing from the selected source is simply missing: there is no fallback
   from one source to the other, and no fallback from the payout key to the
   pay-in key. Nothing is ever copied from the environment into the database.

Every change needs the explicit manage_payment_settings permission (never
implied by is_admin or the 'all' wildcard) AND the administrator's current
password, is validated here, bumps the configuration version and is written to
payment_config_audit without any secret value. A change only writes the
configuration: it reserves nothing, releases nothing and sends nothing.

A change that ACTIVATES a financial operation needs a second explicit
permission as well, activate_financial_operations (see activation_required):
switching automatic payouts or USD settlement on, approving the network fee
limits, confirming the provider fee behaviour, lifting a payout suspension, and
changing what the payout engine sends while automatic payouts are on. That
permission never replaces manage_payment_settings, and switching anything OFF
never needs it.
"""
from __future__ import annotations

import binascii
import logging
import re
import time
from dataclasses import dataclass, fields as dataclass_fields, replace
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlsplit

import pyotp
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.services import super_admin

from app.core.config import settings
from app.core.security import verify_password
from app.models.accounting import ChartOfAccounts
from app.models.payment_config import PaymentConfigAudit, PaymentCredential, PaymentSettings, PaymentWebhookStat
from app.services import payment_crypto
from app.services.financial_integrity import money

logger = logging.getLogger(__name__)

PERMISSION_MANAGE = "manage_payment_settings"
PERMISSION_PROCESS = "process_cashouts"
PERMISSION_ACTIVATE = "activate_financial_operations"
SETTINGS_ROW_ID = 1
PROVIDER = "nowpayments"

SOURCE_ENVIRONMENT, SOURCE_DATABASE = "ENVIRONMENT", "DATABASE"
FEE_COMPANY_PAYS, FEE_MEMBER_PAYS = "COMPANY_PAYS", "MEMBER_PAYS"
# Where the PROVIDER takes the network fee of a payout from. It is a setting of
# the provider account, outside this application, so it is never assumed:
#   UNVERIFIED            not confirmed with the provider: no payout is created
#   DEDUCTED_BY_PROVIDER  the provider takes its fee out of the amount it is
#                         asked to send; the full amount is handed to it and
#                         the beneficiary receives that amount less the fee
#   CHARGED_TO_BALANCE    the provider takes its fee from the MyHigh5 balance.
#                         Defined so that it can be told apart; it cannot be
#                         selected and no payout is created under it.
FEE_MODE_UNVERIFIED, FEE_MODE_DEDUCTED, FEE_MODE_CHARGED = "UNVERIFIED", "DEDUCTED_BY_PROVIDER", "CHARGED_TO_BALANCE"
PROVIDER_FEE_MODES = (FEE_MODE_UNVERIFIED, FEE_MODE_DEDUCTED, FEE_MODE_CHARGED)
# Ledger account for the network fee MyHigh5 pays on a crypto payout
# (approved by the owner 2026-10-10).
NETWORK_FEE_EXPENSE_ACCOUNT = "5005"


def company_fee_payer_values() -> frozenset:
    """The values of the provider's `fee_paid_by` field that mean "the fee was
    taken from OUR balance". The provider does not document that field's
    values, so none is assumed: the list is empty until the values have been
    confirmed with the provider and set in NOWPAYMENTS_FEE_PAID_BY_COMPANY_VALUES
    (comma separated). While it is empty no network fee is posted automatically;
    an administrator records each one from the provider's statement."""
    import os

    raw = os.getenv("NOWPAYMENTS_FEE_PAID_BY_COMPANY_VALUES", "")
    return frozenset(v.strip().lower() for v in raw.split(",") if v.strip())


def receiver_fee_payer_values() -> frozenset:
    """The values of the provider's `fee_paid_by` field that mean "the fee was
    taken out of the amount sent to the beneficiary". Not documented by the
    provider, so empty until confirmed with it and set in
    NOWPAYMENTS_FEE_PAID_BY_RECEIVER_VALUES (comma separated). While it is
    empty the actual fee of a payout is never recorded automatically; an
    administrator records it from the provider's statement."""
    import os

    raw = os.getenv("NOWPAYMENTS_FEE_PAID_BY_RECEIVER_VALUES", "")
    return frozenset(v.strip().lower() for v in raw.split(",") if v.strip())
USD_POLICY_MANUAL = "MANUAL_REVIEW"

# The only payout asset the ledger has a treasury account for (1001).
SUPPORTED_PAYOUT_CURRENCIES: Dict[str, Dict[str, str]] = {
    # USDT BEP20 on BNB Smart Chain (chain id 56), token contract
    # 0x55d398326f99059fF775485246999027B3197955; verified against the provider's
    # own currency data before every payout cycle (cashout_engine.verify_payout_asset).
    "usdtbsc": {"currency": "USDT", "network": "BSC (BEP20)", "treasury_account": "1001",
                "chain_id": "56", "contract": "0x55d398326f99059fF775485246999027B3197955",
                "explorer_tx": "https://bscscan.com/tx/"},
}

CONFIRM_AUTO_PAYOUT = "ENABLE AUTOMATIC PAYOUTS"
CONFIRM_USD_SETTLEMENT = "ENABLE USD SETTLEMENT"
CONFIRM_FEE_MODE = "PROVIDER FEE BEHAVIOUR VERIFIED"
CONFIRM_FEE_LIMITS = "APPROVE NETWORK FEE LIMITS"
CONFIRM_REACTIVATION = "REACTIVATE CRYPTO PAYOUTS"
# Switching the provider back on while automatic payouts are configured on lets payouts resume.
CONFIRM_PROVIDER_RESUME = "RESUME NOWPAYMENTS PAYOUTS"
# A change to any of these withdraws the approval of the network fee limits.
_FEE_TERMS_FIELDS = ("provider_fee_mode", "member_fee_cap_percent", "member_fee_cap_usd", "min_net_payout_usd",
                     "fee_terms_version", "fee_consent_valid_days", "network_fee_policy",
                     "fee_estimate_margin_percent", "max_unreconciled_payouts")
# While automatic payouts are on, these settings decide what the payout engine
# sends, to which network and with which credentials: changing one of them is
# an activation (activation_required). The fee settings are not listed: a
# change to one of them withdraws the approval, which stops payouts.
LIVE_PAYOUT_FIELDS = ("crypto_payout_currency", "payout_credential_source", "provider_balance_reserve_usd",
                      "crypto_min_usd", "max_network_fee_percent", "max_single_payout_usd", "max_daily_payout_usd",
                      "max_daily_payout_count", "min_hours_between_payouts", "payout_interval_seconds",
                      "retry_backoff_hours", "retry_max_attempts")
# Switched off, each of these stops payouts while the automatic payouts switch
# stays on; switching it back on makes them resume.
LIVE_PAYOUT_SWITCHES = ("provider_enabled", "crypto_cashout_enabled")
FEE_GATE_MESSAGES = {
    "FEE_POLICY_NOT_BENEFICIARY_PAID": "The network fee policy must be MEMBER_PAYS: the beneficiary bears the fee.",
    "PROVIDER_FEE_MODE_UNVERIFIED": "The provider fee behaviour is not confirmed as DEDUCTED_BY_PROVIDER.",
    "FEE_LIMITS_NOT_CONFIGURED": "No member network fee limit is set.",
    "FEE_SAFETY_MARGIN_NOT_SET": "The safety margin on the network fee estimate is not set.",
    "FEE_LIMITS_NOT_APPROVED": "The network fee limits have not been approved.",
    "PAYOUTS_SUSPENDED": "Crypto payouts are suspended and need an administrator's review and an explicit "
                         "reactivation.",
    "FEE_RECONCILIATION_PENDING": "An earlier payout's actual network fee has not been verified yet. This lifts "
                                  "by itself once it is verified; it is not a suspension.",
}

# Why crypto payouts were SUSPENDED: a confirmed financial inconsistency. Each
# one means the provider did NOT behave as configured, so its fee behaviour goes
# back to UNVERIFIED as well. A payout whose actual fee is merely missing or not
# verified yet is NOT one of them: that is the temporary recording gate
# (FEE_RECONCILIATION_PENDING), which lifts by itself once the fee is verified.
SUSPEND_MODE_MISMATCH, SUSPEND_AMOUNT_MISMATCH, SUSPEND_CAP_EXCEEDED = (
    "PROVIDER_FEE_MODE_MISMATCH", "PROVIDER_AMOUNT_MISMATCH", "FEE_CAP_EXCEEDED")
SUSPENSION_MESSAGES = {
    SUSPEND_MODE_MISMATCH: "The provider charged a network fee to the MyHigh5 balance instead of taking it out of "
                           "the payout.",
    SUSPEND_AMOUNT_MISMATCH: "The amount the provider reports for a payout does not agree with what it was asked "
                             "to send.",
    SUSPEND_CAP_EXCEEDED: "The network fee the provider took from a payout is higher than the limit the member "
                          "accepted.",
}


def payout_amount_semantics() -> str:
    """What the provider's `amount` on a finished payout means, as CONFIRMED
    with the provider: "REQUESTED" (the amount it was asked to send) or
    "RECEIVED" (what the beneficiary received, after its fee). Not documented
    by the provider, so empty until confirmed and set in
    NOWPAYMENTS_PAYOUT_AMOUNT_MEANS. While it is empty nothing the provider
    reports counts as a verified reconciliation of a payout's fee."""
    import os

    value = os.getenv("NOWPAYMENTS_PAYOUT_AMOUNT_MEANS", "").strip().upper()
    return value if value in ("REQUESTED", "RECEIVED") else ""
# Automatic payouts can only be switched on with a successful connection test this recent.
CONNECTION_TEST_MAX_AGE = timedelta(hours=24)

# Choices that still exist as stored values (rows written before the owner's
# decision) but can no longer be selected. The Admin Panel shows them disabled
# with the reason; update_settings refuses them whatever the client sends.
UNSUPPORTED_CHOICES: Dict[str, Dict[str, str]] = {
    "network_fee_policy": {
        FEE_COMPANY_PAYS: "Retired: the beneficiary bears the network fee. No payout is created under it."},
    "provider_fee_mode": {
        FEE_MODE_CHARGED: "Not available: under it MyHigh5 would bear the network fee. No payout is created "
                          "under it."},
}

# How the Crypto Cashout page of the Admin Panel groups its settings. Every
# crypto setting is in exactly one section (checked below the registry).
CRYPTO_SECTIONS: Tuple[Tuple[str, str, str, Tuple[str, ...]], ...] = (
    ("provider", "A. Provider configuration",
     "What is paid out, who bears the network fee, and where the provider takes that fee from.",
     ("crypto_payout_currency", "network_fee_policy", "provider_fee_mode", "provider_balance_reserve_usd")),
    ("fee_limits", "B. Network fee estimates and limits",
     "The limits a member accepts. They are compared with the provider's ESTIMATE for the payout; the actual "
     "fee is known only afterwards and is not guaranteed by them.",
     ("member_fee_cap_percent", "member_fee_cap_usd", "max_network_fee_percent", "min_net_payout_usd",
      "fee_terms_version", "fee_consent_valid_days")),
    ("safety", "C. Safety margin and recording gate",
     "How far the estimate is raised before it is checked, and how many payouts may be outstanding without a "
     "verified actual fee.",
     ("fee_estimate_margin_percent", "max_unreconciled_payouts")),
    ("activation", "D. Approval and activation",
     "The approval of the settings above, and the switches. Approve in a change of its own, after the values "
     "were saved.",
     ("fee_terms_approved", "crypto_cashout_enabled", "crypto_auto_payout_enabled")),
    ("limits", "Payout limits and schedule",
     "Amounts, daily limits, intervals and retries of the payout engine.",
     ("crypto_min_usd", "max_single_payout_usd", "max_daily_payout_usd", "max_daily_payout_count",
      "min_hours_between_payouts", "payout_interval_seconds", "retry_backoff_hours", "retry_max_attempts")),
)


class PaymentConfigError(ValueError):
    """A configuration action that was refused. Nothing was changed."""

    def __init__(self, code: str, message: str, *, field: Optional[str] = None):
        super().__init__(message)
        self.code = code
        self.field = field


# ---------------------------------------------------------------------------
# Field registry (labels are what the Admin Panel shows)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Field:
    name: str
    group: str                      # provider | crypto | security | usd
    kind: str                       # bool | int | money | percent | choice | text | account
    label: str
    help: str
    default: Callable[[], Any]
    minimum: Optional[Decimal] = None
    maximum: Optional[Decimal] = None
    choices: Tuple[str, ...] = ()
    unit: str = ""
    max_length: int = 0
    approval: str = ""              # non-empty: a business policy awaiting the owner's approval
    optional: bool = False          # a number that may be left empty (= not set)


def _env_int(name: str, fallback: int) -> Callable[[], int]:
    return lambda: int(getattr(settings, name, fallback))


def _env_money(name: str, fallback: str) -> Callable[[], Decimal]:
    return lambda: money(getattr(settings, name, fallback))


def _const(value: Any) -> Callable[[], Any]:
    return lambda: value


_D = Decimal
_FIELDS: List[Field] = [
    # ---- provider ------------------------------------------------------------
    Field("provider_display_name", "provider", "text", "Provider display name",
          "Name shown for the crypto payment provider.", _const("NOWPayments"), max_length=80),
    Field("provider_enabled", "provider", "bool", "Provider enabled (emergency stop)",
          "Master switch for NOWPayments in both directions. When off, no new NOWPayments payment is "
          "created and no payout is sent. Callbacks and status checks for payments that already exist "
          "are still processed.", _const(True)),
    Field("checkout_enabled", "provider", "bool", "NOWPayments checkout (new member payments)",
          "Incoming payments only. When off, members cannot start a new NOWPayments payment; automatic "
          "commission payouts are not affected. Existing payments, callbacks and status checks continue. "
          "A new payment also needs the provider switch above to be on.", _const(True)),
    Field("payin_credential_source", "provider", "choice", "Pay-in credential source",
          "Where the pay-in API key and the IPN secret are read from.", _const(SOURCE_ENVIRONMENT),
          choices=(SOURCE_ENVIRONMENT, SOURCE_DATABASE)),
    Field("payout_credential_source", "provider", "choice", "Payout credential source",
          "Where the payout credentials are read from.", _const(SOURCE_ENVIRONMENT),
          choices=(SOURCE_ENVIRONMENT, SOURCE_DATABASE)),
    # ---- crypto cashout ------------------------------------------------------
    Field("crypto_cashout_enabled", "crypto", "bool", "Crypto Cashout available",
          "Members may choose Crypto Cashout. Turning it off stops new crypto payouts; balances are kept.",
          _const(True)),
    Field("crypto_auto_payout_enabled", "crypto", "bool", "Automatic payouts",
          "The payout engine sends eligible balances automatically. Also requires the server master switch.",
          _const(False)),
    Field("crypto_min_usd", "crypto", "money", "Minimum crypto cashout",
          "Smallest balance that is paid out. The provider's own minimum and the network fee still apply: "
          "a balance at this minimum is not necessarily payable.", _env_money("CRYPTO_CASHOUT_MIN_USD", "1.00"),
          minimum=_D("0.01"), maximum=_D("100000"), unit="USD"),
    Field("crypto_payout_currency", "crypto", "choice", "Payout currency and network",
          "Asset and network of crypto payouts.", _const("usdtbsc"), choices=tuple(SUPPORTED_PAYOUT_CURRENCIES)),
    Field("network_fee_policy", "crypto", "choice", "Network fee policy",
          "MEMBER_PAYS: the beneficiary bears the network fee and receives the payout net of it (owner "
          "decision). COMPANY_PAYS is retired: it cannot be selected and no payout is created under it.",
          _const(FEE_MEMBER_PAYS), choices=(FEE_COMPANY_PAYS, FEE_MEMBER_PAYS)),
    Field("provider_fee_mode", "crypto", "choice", "Provider fee behaviour",
          "Where the provider takes its network fee from, as CONFIRMED with the provider. UNVERIFIED: no payout "
          "is created. DEDUCTED_BY_PROVIDER: the full amount is handed to the provider, which takes its fee out "
          "of it. CHARGED_TO_BALANCE cannot be selected.", _const(FEE_MODE_UNVERIFIED), choices=PROVIDER_FEE_MODES),
    Field("member_fee_cap_percent", "crypto", "percent", "Member network fee limit (share of the payout)",
          "Highest network fee a member accepts, as a share of the payout. 0 = this limit is not set. No payout "
          "is created while neither limit is set.", _const(_D("0")), minimum=_D("0"), maximum=_D("100"), unit="%",
          approval="Not set. Awaiting the business owner's decision."),
    Field("member_fee_cap_usd", "crypto", "money", "Member network fee limit (amount)",
          "Highest network fee a member accepts, as an amount per payout. 0 = this limit is not set. When both "
          "limits are set the lower one applies.", _const(_D("0.00")), minimum=_D("0"), maximum=_D("100000"),
          unit="USD", approval="Not set. Awaiting the business owner's decision."),
    Field("min_net_payout_usd", "crypto", "money", "Minimum amount received",
          "A payout is not attempted when the member would receive less than this after the estimated network "
          "fee.", _const(_D("0.01")), minimum=_D("0.01"), maximum=_D("100000"), unit="USD"),
    Field("fee_estimate_margin_percent", "crypto", "percent", "Safety margin on the fee estimate",
          "The provider's fee estimate is raised by this share before it is compared with the member's limit "
          "(estimate x (1 + margin)). It allows for the actual fee being higher than the estimate; it does not "
          "limit the actual fee. Empty = not set: no payout is created.", _const(None), minimum=_D("0"),
          maximum=_D("500"), unit="% of the estimate", optional=True,
          approval="Not set. Awaiting the business owner's decision."),
    Field("max_unreconciled_payouts", "crypto", "int", "Payouts allowed without a verified actual fee",
          "No further payout is created while more payouts than this are still at the provider or completed "
          "without a verified actual network fee. 0 = one payout at a time, each verified before the next.",
          _const(0), minimum=_D(0), maximum=_D(1000)),
    Field("fee_terms_version", "crypto", "int", "Network fee terms version",
          "Raising it makes every member accept the network fee terms again before the next payout.", _const(1),
          minimum=_D(1), maximum=_D(100000)),
    Field("fee_consent_valid_days", "crypto", "int", "Member acceptance lifetime",
          "A member's acceptance of the network fee terms expires after this long. 0 = it does not expire by "
          "time.", _const(0), minimum=_D(0), maximum=_D(3650), unit="days"),
    Field("fee_terms_approved", "crypto", "bool", "Network fee limits approved",
          "The limits above were approved for use. Withdrawn automatically whenever one of them, the provider "
          "fee behaviour or the terms version changes. While it is off no payout is created and no member can "
          "accept the terms.", _const(False)),
    Field("max_network_fee_percent", "crypto", "percent", "Maximum network fee share",
          "A payout is not attempted when the network fee exceeds this share of it.", _const(_D("25.00")),
          minimum=_D("0.10"), maximum=_D("100"), unit="%"),
    Field("payout_interval_seconds", "crypto", "int", "Payout processing interval",
          "Time between two runs of the payout engine.", _env_int("CASHOUT_ENGINE_INTERVAL_SECONDS", 900),
          minimum=_D(60), maximum=_D(86400), unit="seconds"),
    Field("max_single_payout_usd", "crypto", "money", "Maximum single payout",
          "A larger balance is not sent automatically; it is listed for review.", _const(_D("1000.00")),
          minimum=_D("1"), maximum=_D("1000000"), unit="USD",
          approval="Initial safety limit. Awaiting the business owner's approval."),
    Field("max_daily_payout_usd", "crypto", "money", "Maximum daily payout amount",
          "Total sent to all members in any 24 hours.", _const(_D("5000.00")),
          minimum=_D("1"), maximum=_D("10000000"), unit="USD",
          approval="Initial safety limit. Awaiting the business owner's approval."),
    Field("max_daily_payout_count", "crypto", "int", "Maximum daily payout count",
          "Number of payouts sent in any 24 hours.", _const(100), minimum=_D(1), maximum=_D(100000)),
    Field("min_hours_between_payouts", "crypto", "int", "Minimum interval between payouts",
          "Time a member waits between two crypto payouts. 0 (the default since individual payouts, owner "
          "rule 2026-10-18): every commission is paid as soon as it is available.", _const(0), minimum=_D(0),
          maximum=_D(8760),
          unit="hours"),
    Field("retry_backoff_hours", "crypto", "int", "Retry delay after a failed payout",
          "A member whose payout failed is not tried again for this long.",
          _env_int("CASHOUT_RETRY_BACKOFF_HOURS", 24), minimum=_D(1), maximum=_D(720), unit="hours"),
    Field("retry_max_attempts", "crypto", "int", "Maximum failed payouts in 7 days",
          "After this many failed payouts in 7 days the member is no longer retried automatically. "
          "A payout with an unknown outcome is never retried.", _const(3), minimum=_D(1), maximum=_D(20)),
    Field("provider_balance_reserve_usd", "crypto", "money", "Provider balance reserve",
          "Amount always left in the provider balance; payouts stop before it is touched.", _const(_D("0.00")),
          minimum=_D("0"), maximum=_D("10000000"), unit="USD"),
    # ---- payout security -----------------------------------------------------
    Field("wallet_email_verification_required", "security", "bool", "Wallet email verification required",
          "A new or changed payout wallet takes effect only after the member confirms it from a link sent "
          "to the account's email address.", _const(True)),
    Field("wallet_hold_hours", "security", "int", "Wallet security hold",
          "Nothing is paid to a new or changed wallet for this long.", _env_int("PAYOUT_WALLET_HOLD_HOURS", 72),
          minimum=_D(0), maximum=_D(720), unit="hours"),
    Field("wallet_max_changes_per_day", "security", "int", "Wallet changes per 24 hours",
          "Number of wallet changes (and confirmation emails) a member may ask for in 24 hours.",
          _env_int("PAYOUT_WALLET_MAX_CHANGES_PER_DAY", 3), minimum=_D(1), maximum=_D(20)),
    Field("wallet_verification_ttl_minutes", "security", "int", "Confirmation link lifetime",
          "A wallet confirmation link expires after this long.", _const(60), minimum=_D(10), maximum=_D(1440),
          unit="minutes"),
    # ---- USD cashout ---------------------------------------------------------
    Field("usd_cashout_enabled", "usd", "bool", "USD Cashout requests available",
          "Members may submit USD Cashout requests.", _const(True)),
    Field("usd_min_usd", "usd", "money", "Minimum USD cashout", "Smallest balance a member may request.",
          _env_money("USD_CASHOUT_MIN_USD", "100.00"), minimum=_D("1"), maximum=_D("1000000"), unit="USD"),
    Field("usd_fee_percent", "usd", "percent", "Withdrawal fee", "Share of the requested amount.",
          _const(_D("1.000")), minimum=_D("0"), maximum=_D("50"), unit="%"),
    Field("usd_fee_min", "usd", "money", "Minimum withdrawal fee", "Lowest fee charged.", _const(_D("20.00")),
          minimum=_D("0"), maximum=_D("100000"), unit="USD"),
    Field("usd_fee_max", "usd", "money", "Maximum withdrawal fee", "Highest fee charged.", _const(_D("1000.00")),
          minimum=_D("0"), maximum=_D("1000000"), unit="USD"),
    Field("usd_settlement_enabled", "usd", "bool", "USD settlement",
          "An authorized administrator may record that a USD cashout was paid. Also requires the server "
          "master switch and a settlement ledger account.", _const(False)),
    Field("usd_settlement_account", "usd", "account", "Settlement ledger account",
          "Chart-of-accounts code the USD payment leaves from.",
          lambda: (settings.USD_CASHOUT_SETTLEMENT_ACCOUNT or "").strip() or None, max_length=20),
    Field("usd_admin_approval_required", "usd", "bool", "Administrator approval required",
          "Every USD cashout is reviewed and settled by an administrator. Automatic USD settlement does "
          "not exist.", _const(True)),
    Field("usd_processing_policy", "usd", "choice", "Withdrawal processing policy",
          "How USD requests are processed.", _const(USD_POLICY_MANUAL), choices=(USD_POLICY_MANUAL,)),
    Field("usd_member_cancellation_allowed", "usd", "bool", "Member may cancel a request",
          "A member may cancel a request that has not been processed. An administrator always may.",
          _const(True)),
    Field("usd_reference_min_length", "usd", "int", "Settlement reference minimum length",
          "A settlement is recorded only with an external payment reference at least this long.", _const(6),
          minimum=_D(3), maximum=_D(100), unit="characters"),
    Field("usd_destination_required", "usd", "bool", "Payout destination required",
          "The member must give payout destination details with the request. They are stored encrypted "
          "and shown only to administrators who process cashouts.", _const(False)),
    Field("usd_destination_note", "usd", "text", "Payout destination instructions",
          "Shown to the member on the USD Cashout request.", _const(None), max_length=500),
]
FIELDS: Dict[str, Field] = {f.name: f for f in _FIELDS}
GROUPS = ("provider", "crypto", "security", "usd")


@dataclass(frozen=True)
class PaymentConfig:
    provider_display_name: str
    provider_enabled: bool
    checkout_enabled: bool
    payin_credential_source: str
    payout_credential_source: str
    crypto_cashout_enabled: bool
    crypto_auto_payout_enabled: bool
    crypto_min_usd: Decimal
    crypto_payout_currency: str
    network_fee_policy: str
    provider_fee_mode: str
    member_fee_cap_percent: Decimal
    member_fee_cap_usd: Decimal
    min_net_payout_usd: Decimal
    fee_estimate_margin_percent: Optional[Decimal]
    max_unreconciled_payouts: int
    fee_terms_version: int
    fee_consent_valid_days: int
    fee_terms_approved: bool
    max_network_fee_percent: Decimal
    payout_interval_seconds: int
    max_single_payout_usd: Decimal
    max_daily_payout_usd: Decimal
    max_daily_payout_count: int
    min_hours_between_payouts: int
    retry_backoff_hours: int
    retry_max_attempts: int
    provider_balance_reserve_usd: Decimal
    wallet_email_verification_required: bool
    wallet_hold_hours: int
    wallet_max_changes_per_day: int
    wallet_verification_ttl_minutes: int
    usd_cashout_enabled: bool
    usd_min_usd: Decimal
    usd_fee_percent: Decimal
    usd_fee_min: Decimal
    usd_fee_max: Decimal
    usd_settlement_enabled: bool
    usd_settlement_account: Optional[str]
    usd_admin_approval_required: bool
    usd_processing_policy: str
    usd_member_cancellation_allowed: bool
    usd_reference_min_length: int
    usd_destination_required: bool
    usd_destination_note: Optional[str]
    version: int = 0
    persisted: bool = False
    # Not settings: set by the engine when a payout did not add up, cleared only
    # by an administrator's explicit reactivation.
    suspended_reason: Optional[str] = None
    suspended_at: Optional[datetime] = None
    suspended_cashout_id: Optional[int] = None

    # ---- derived ----------------------------------------------------------
    @property
    def wallet_hold(self) -> timedelta:
        return timedelta(hours=max(0, int(self.wallet_hold_hours)))

    @property
    def treasury_account(self) -> str:
        return SUPPORTED_PAYOUT_CURRENCIES[self.crypto_payout_currency]["treasury_account"]

    def usd_fee(self, gross: Any) -> Tuple[Decimal, Decimal]:
        """(fee, net) of a USD cashout: percentage of the amount, bounded by the
        minimum and maximum fee. Always computed here, on the server."""
        amount = money(gross)
        raw = money(amount * self.usd_fee_percent / Decimal("100"))
        fee = money(max(self.usd_fee_min, min(raw, self.usd_fee_max)))
        return fee, money(amount - fee)

    def usd_fee_rule(self) -> str:
        return (f"{_plain(self.usd_fee_percent)}% of the amount, minimum {_dollars(self.usd_fee_min)}, "
                f"maximum {_dollars(self.usd_fee_max)}")

    def fee_rules_gate(self) -> Optional[str]:
        """Why the network fee RULES are not in force (None = they are). Fail
        closed: the beneficiary-paid policy, a provider fee behaviour confirmed
        as deducted from the amount, at least one member fee limit, a safety
        margin on the estimate, and the approval of all of them are required."""
        if self.network_fee_policy != FEE_MEMBER_PAYS:
            return "FEE_POLICY_NOT_BENEFICIARY_PAID"
        if self.provider_fee_mode != FEE_MODE_DEDUCTED:
            return "PROVIDER_FEE_MODE_UNVERIFIED"
        if Decimal(self.member_fee_cap_percent) <= 0 and Decimal(self.member_fee_cap_usd) <= 0:
            return "FEE_LIMITS_NOT_CONFIGURED"
        if self.fee_estimate_margin_percent is None:
            return "FEE_SAFETY_MARGIN_NOT_SET"
        if not self.fee_terms_approved:
            return "FEE_LIMITS_NOT_APPROVED"
        return None

    def fee_gate(self) -> Optional[str]:
        """Why NO crypto payout may be created (None = one may): a suspension
        that an administrator has not lifted, or rules that are not in force.
        Restoring the rules never lifts a suspension."""
        if self.suspended_reason:
            return "PAYOUTS_SUSPENDED"
        return self.fee_rules_gate()

    @property
    def checkout_allowed(self) -> bool:
        """A NEW NOWPayments checkout may be created: the provider (master emergency stop) AND checkout on.
        Payouts never read this."""
        return bool(self.provider_enabled and self.checkout_enabled)

    @property
    def auto_payout_allowed(self) -> bool:
        """Every SWITCH that must be on for the engine (credentials are checked separately)."""
        return bool(crypto_master_switch() and self.provider_enabled and self.crypto_cashout_enabled
                    and self.crypto_auto_payout_enabled)

    @property
    def usd_settlement_allowed(self) -> bool:
        return bool(usd_settlement_master_switch() and self.usd_settlement_enabled
                    and (self.usd_settlement_account or "").strip())


_STATE_FIELDS = ("version", "persisted", "suspended_reason", "suspended_at", "suspended_cashout_id")
_CONFIG_FIELDS = tuple(f.name for f in dataclass_fields(PaymentConfig) if f.name not in _STATE_FIELDS)
if set(_CONFIG_FIELDS) != set(FIELDS):
    raise RuntimeError("payment configuration registry is inconsistent")
_SECTIONED = [name for _key, _title, _note, names in CRYPTO_SECTIONS for name in names]
if sorted(_SECTIONED) != sorted(f.name for f in _FIELDS if f.group == "crypto"):
    raise RuntimeError("the Crypto Cashout sections do not cover every crypto setting exactly once")


def _dollars(value: Decimal) -> str:
    text = f"{Decimal(value):,.2f}"
    return "$" + (text[:-3] if text.endswith(".00") else text)


def _plain(value: Decimal) -> str:
    text = format(Decimal(value).normalize(), "f")
    return text if "." not in text else text.rstrip("0").rstrip(".") or "0"


def crypto_master_switch() -> bool:
    return bool(settings.CRYPTO_AUTO_PAYOUT_ENABLED)


def usd_settlement_master_switch() -> bool:
    return bool(settings.USD_CASHOUT_SETTLEMENT_ENABLED)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _coerce(field: Field, value: Any) -> Any:
    """One value, typed and inside its bounds, or PaymentConfigError."""
    def bad(message: str) -> PaymentConfigError:
        return PaymentConfigError("INVALID_VALUE", f"{field.label}: {message}", field=field.name)

    if field.kind == "bool":
        if not isinstance(value, bool):
            raise bad("must be on or off.")
        return value
    if field.kind == "choice":
        text = str(value or "").strip()
        match = next((c for c in field.choices if c.lower() == text.lower()), None)
        if match is None:
            raise bad("is not a supported value (" + ", ".join(field.choices) + ").")
        return match
    if field.kind in ("text", "account"):
        text = str(value or "").strip()
        if not text:
            if field.name == "provider_display_name":
                raise bad("is required.")
            return None
        if len(text) > field.max_length or any(ord(ch) < 32 and ch not in "\n" for ch in text):
            raise bad(f"must be at most {field.max_length} characters.")
        if field.kind == "account" and not re.fullmatch(r"[A-Za-z0-9._-]+", text):
            raise bad("is not a valid account code.")
        if field.name == "provider_display_name" and any(ch in text for ch in "<>\"\n"):
            raise bad("contains characters that are not allowed.")
        return text
    if field.optional and (value is None or (isinstance(value, str) and not value.strip())):
        return None
    if isinstance(value, bool) or value is None or (isinstance(value, str) and not value.strip()):
        raise bad("a number is required.")
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        raise bad("is not a number.") from None
    if not number.is_finite():
        raise bad("is not a number.")
    if field.kind == "int":
        if number != number.to_integral_value():
            raise bad("must be a whole number.")
    elif field.kind == "money":
        if number != number.quantize(Decimal("0.01")):
            raise bad("may have at most two decimal places.")
    elif number != number.quantize(Decimal("0.001")):
        raise bad("may have at most three decimal places.")
    if field.minimum is not None and number < field.minimum:
        raise bad(f"must be at least {_plain(field.minimum)}.")
    if field.maximum is not None and number > field.maximum:
        raise bad(f"must be at most {_plain(field.maximum)}.")
    return int(number) if field.kind == "int" else number


def defaults() -> Dict[str, Any]:
    """Built-in safe defaults. A broken environment value never makes a default
    unsafe: it is replaced by the registry's own floor."""
    out: Dict[str, Any] = {}
    for field in _FIELDS:
        try:
            value = field.default()
            out[field.name] = _coerce(field, value) if value is not None else None
        except Exception:  # noqa: BLE001 - e.g. an out-of-range environment value
            out[field.name] = _FALLBACK.get(field.name)
    return out


_FALLBACK: Dict[str, Any] = {
    "crypto_min_usd": Decimal("1.00"), "usd_min_usd": Decimal("100.00"), "wallet_hold_hours": 72,
    "wallet_max_changes_per_day": 3, "payout_interval_seconds": 900, "retry_backoff_hours": 24,
    "usd_settlement_account": None,
}


def _from_values(values: Dict[str, Any], *, version: int, persisted: bool,
                 state: Optional[Dict[str, Any]] = None) -> PaymentConfig:
    typed = {}
    for name in _CONFIG_FIELDS:
        field, value = FIELDS[name], values[name]
        if field.kind in ("money", "percent") and value is not None:
            value = Decimal(str(value))
        elif field.kind == "int" and value is not None:
            value = int(value)
        elif field.kind == "bool":
            value = bool(value)
        typed[name] = value
    return PaymentConfig(**typed, version=version, persisted=persisted, **(state or {}))


def default_config() -> PaymentConfig:
    return _from_values(defaults(), version=0, persisted=False)


def load(db: Session) -> PaymentConfig:
    """The configuration in force. Read-only."""
    row = db.query(PaymentSettings).filter(PaymentSettings.id == SETTINGS_ROW_ID).first()
    if row is None:
        return _from_values(defaults(), version=0, persisted=False)
    return _from_values({name: getattr(row, name) for name in _CONFIG_FIELDS}, version=int(row.version),
                        persisted=True, state=_suspension_state(row))


def _suspension_state(row: PaymentSettings) -> Dict[str, Any]:
    return {"suspended_reason": row.payout_suspended_reason or None, "suspended_at": row.payout_suspended_at,
            "suspended_cashout_id": row.payout_suspended_cashout_id}


def lock_settings(db: Session) -> PaymentConfig:
    """Lock the settings row and return the configuration in force. Engine
    workers take this lock immediately before they reserve a payout, so the
    checks that count payouts across ALL members (the recording gate) and the
    suspension are decided by one worker at a time. Released by the caller's
    commit or rollback."""
    row = _row_for_update(db)
    return _from_values({name: getattr(row, name) for name in _CONFIG_FIELDS}, version=int(row.version),
                        persisted=True, state=_suspension_state(row))


def load_shared(db: Session) -> PaymentConfig:
    """The configuration in force, read under a SHARE lock on the settings row: a change to it
    (switching the provider off, for instance) waits until the caller commits or rolls back.
    Used by the checkout-gateway settings (soncopay_settings.update), which lock their own row
    FIRST and this one second; nothing here ever locks the gateway row, so there is no cycle."""
    row = (db.query(PaymentSettings).filter(PaymentSettings.id == SETTINGS_ROW_ID)
           .with_for_update(read=True).populate_existing().first())
    if row is None:
        return default_config()
    return _from_values({name: getattr(row, name) for name in _CONFIG_FIELDS}, version=int(row.version),
                        persisted=True, state=_suspension_state(row))


def _row_for_update(db: Session) -> PaymentSettings:
    row = db.query(PaymentSettings).filter(PaymentSettings.id == SETTINGS_ROW_ID).with_for_update().first()
    if row is None:
        row = PaymentSettings(id=SETTINGS_ROW_ID, version=0, **defaults())
        db.add(row)
        db.flush()
    return row


# ---------------------------------------------------------------------------
# Permission, re-authentication, audit
# ---------------------------------------------------------------------------

def has_permission(user, permission: str) -> bool:
    """Only a role that EXPLICITLY holds the permission, or a Super Admin
    (app.services.super_admin). Never implied by is_admin or by the 'all'
    wildcard, and never assigned automatically."""
    if user is None or not getattr(user, "is_active", True):
        return False
    if super_admin.is_super_admin(user):
        return True
    role = getattr(user, "role", None)
    if role is None:
        return False
    names = {p.name for p in (role.permissions or [])}
    if getattr(role, "inherit_from", None) is not None:
        names |= set(role.inherit_from.get_all_permissions())
    return permission in names


def require_reauth(actor, password: Optional[str]) -> None:
    """The administrator proves it is them, now, with the account password.
    Wrong passwords are counted per administrator across every endpoint that
    asks (app.services.reauth): after a few, REAUTH_LOCKED until the window
    ends, with the right password too."""
    from app.services import reauth

    try:
        reauth.verify(None, actor, password)
    except reauth.ReauthError as exc:
        if exc.code == reauth.LOCKED:
            raise PaymentConfigError(reauth.LOCKED, str(exc)) from None
        raise PaymentConfigError("REAUTH_REQUIRED", "Enter your current password to confirm this change.") from None


def can_activate(user) -> bool:
    """May this administrator activate a financial operation? BOTH permissions:
    activate_financial_operations alone opens nothing."""
    return has_permission(user, PERMISSION_MANAGE) and has_permission(user, PERMISSION_ACTIVATE)


def require_activation(actor, what: str, *, field: Optional[str] = None) -> None:
    """Refuse an activation asked for by somebody who may only configure."""
    if not can_activate(actor):
        raise PaymentConfigError(
            "ACTIVATION_PERMISSION_REQUIRED",
            f"The {PERMISSION_ACTIVATE} permission is required, in addition to {PERMISSION_MANAGE}, to {what}. "
            "Nothing was changed.", field=field)


def activation_required(current: Dict[str, Any], changed: Dict[str, Any]) -> List[Tuple[str, str]]:
    """The parts of a settings change that activate a financial operation, as
    (setting, what it does). Empty for an ordinary configuration change, and
    for every change that only switches something off.

    `current` is the configuration in force, `changed` the settings that would
    get a new value."""
    out: List[Tuple[str, str]] = []
    if changed.get("crypto_auto_payout_enabled") is True:
        out.append(("crypto_auto_payout_enabled", "switch automatic payouts on"))
    if changed.get("checkout_enabled") is True:
        out.append(("checkout_enabled", "switch NOWPayments checkout on"))
    if changed.get("usd_settlement_enabled") is True:
        out.append(("usd_settlement_enabled", "switch USD settlement on"))
    if changed.get("fee_terms_approved") is True:
        out.append(("fee_terms_approved", "approve the network fee limits"))
    if changed.get("provider_fee_mode") == FEE_MODE_DEDUCTED:
        out.append(("provider_fee_mode", "confirm the provider fee behaviour"))
    # Automatic payouts are on and stay on: what the engine sends is being changed.
    if current.get("crypto_auto_payout_enabled") and changed.get("crypto_auto_payout_enabled") is not False:
        for name in LIVE_PAYOUT_FIELDS:
            if name in changed:
                out.append((name, f'change "{FIELDS[name].label}" while automatic payouts are on'))
        for name in LIVE_PAYOUT_SWITCHES:
            if changed.get(name) is True:
                out.append((name, f'switch "{FIELDS[name].label}" back on while automatic payouts are on'))
    return out


def _authorize(actor, password: Optional[str], *, activation: Optional[str] = None) -> None:
    """Who is asking comes first. `activation` names an act that also needs
    the activation permission."""
    if not has_permission(actor, PERMISSION_MANAGE):
        raise PaymentConfigError("FORBIDDEN", f"The {PERMISSION_MANAGE} permission is required.")
    if activation:
        require_activation(actor, activation)
    require_reauth(actor, password)


_FORBIDDEN_AUDIT_PARTS = ("secret", "cipher", "token", "password", "api_key", "value")


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _audit(db: Session, row: PaymentSettings, *, actor_id: Optional[int], action: str, old: Optional[dict] = None,
           new: Optional[dict] = None, ip: Optional[str] = None) -> None:
    for values in (old or {}), (new or {}):
        for name in values:
            if any(part in name.lower() for part in _FORBIDDEN_AUDIT_PARTS):
                raise ValueError(f"refusing to audit a sensitive field: {name}")
    db.add(PaymentConfigAudit(
        version=int(row.version), action=action, actor_id=actor_id,
        changed_fields=sorted(set(old or {}) | set(new or {})) or None,
        old_values={k: _jsonable(v) for k, v in (old or {}).items()} or None,
        new_values={k: _jsonable(v) for k, v in (new or {}).items()} or None,
        ip_address=(ip or None)))


# ---------------------------------------------------------------------------
# Credentials
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CredentialSpec:
    name: str
    group: str            # payin | payout
    label: str
    env: str
    min_length: int


CREDENTIALS: Dict[str, CredentialSpec] = {c.name: c for c in (
    CredentialSpec("PAYIN_API_KEY", "payin", "Pay-in API key", "NOWPAYMENTS_API_KEY", 10),
    CredentialSpec("IPN_SECRET", "payin", "IPN secret", "NOWPAYMENTS_IPN_SECRET", 8),
    CredentialSpec("PAYOUT_API_KEY", "payout", "Payout API key", "NOWPAYMENTS_PAYOUT_API_KEY", 10),
    CredentialSpec("PAYOUT_EMAIL", "payout", "Payout login email", "NOWPAYMENTS_EMAIL", 5),
    CredentialSpec("PAYOUT_PASSWORD", "payout", "Payout login password", "NOWPAYMENTS_PASSWORD", 6),
    CredentialSpec("PAYOUT_TOTP_SECRET", "payout", "Payout authenticator (TOTP) secret",
                   "NOWPAYMENTS_PAYOUT_TOTP_SECRET", 16),
)}
PAYOUT_CREDENTIALS = tuple(n for n, c in CREDENTIALS.items() if c.group == "payout")
PAYIN_CREDENTIALS = tuple(n for n, c in CREDENTIALS.items() if c.group == "payin")


@dataclass(frozen=True, repr=False)
class ProviderCredentials:
    """Resolved credentials for one use. Never logged, never serialized."""
    payin_source: str
    payout_source: str
    values: Dict[str, Optional[str]]

    def __repr__(self) -> str:  # a credential must never reach a log through repr()
        present = sorted(n for n, v in self.values.items() if v)
        return f"ProviderCredentials(payin={self.payin_source}, payout={self.payout_source}, present={present})"

    def get(self, name: str) -> Optional[str]:
        return self.values.get(name) or None

    @property
    def payout_missing(self) -> List[str]:
        return [CREDENTIALS[n].label for n in PAYOUT_CREDENTIALS if not self.values.get(n)]

    @property
    def payout_ready(self) -> bool:
        return not self.payout_missing


def _env_value(spec: CredentialSpec) -> Optional[str]:
    value = str(getattr(settings, spec.env, "") or "").strip()
    if spec.name == "PAYOUT_TOTP_SECRET":
        value = value.replace(" ", "")
    return value or None


def _stored(db: Session) -> Dict[str, PaymentCredential]:
    return {r.name: r for r in db.query(PaymentCredential).filter(PaymentCredential.provider == PROVIDER).all()}


def _decrypt(row: PaymentCredential) -> Optional[str]:
    try:
        return payment_crypto.decrypt(row.ciphertext, payment_crypto.PURPOSE_CREDENTIAL + row.name)
    except payment_crypto.PaymentCryptoError:
        return None


def resolve_credentials(db: Session, config: Optional[PaymentConfig] = None) -> ProviderCredentials:
    """The credentials in force, each group from its ONE selected source."""
    config = config or load(db)
    stored: Optional[Dict[str, PaymentCredential]] = None
    values: Dict[str, Optional[str]] = {}
    for name, spec in CREDENTIALS.items():
        source = config.payin_credential_source if spec.group == "payin" else config.payout_credential_source
        if source == SOURCE_DATABASE:
            if stored is None:
                stored = _stored(db)
            values[name] = _decrypt(stored[name]) if name in stored else None
        else:
            values[name] = _env_value(spec)
    return ProviderCredentials(config.payin_credential_source, config.payout_credential_source, values)


def credential_status(db: Session, config: Optional[PaymentConfig] = None) -> List[dict]:
    """What the Admin Panel may know about each credential: never a value."""
    config = config or load(db)
    stored = _stored(db)
    out = []
    for name, spec in CREDENTIALS.items():
        row = stored.get(name)
        source = config.payin_credential_source if spec.group == "payin" else config.payout_credential_source
        readable = row is not None and _decrypt(row) is not None
        environment = _env_value(spec) is not None
        out.append({
            "name": name, "label": spec.label, "group": spec.group, "source": source,
            "stored": "CONFIGURED" if row is not None else "NOT CONFIGURED",
            "stored_readable": readable if row is not None else None,
            "stored_updated_at": row.set_at.isoformat() if row is not None and row.set_at else None,
            "stored_updated_by": row.set_by if row is not None else None,
            "environment": "CONFIGURED" if environment else "NOT CONFIGURED",
            "in_use": "CONFIGURED" if (readable if source == SOURCE_DATABASE else environment) else "NOT CONFIGURED",
        })
    return out


# Zero-width characters that come along when a value is copied from a web page or a password manager.
_INVISIBLE = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u2060\ufeff"))
# What the payout signing (nowpayments_service, pyotp.TOTP) produces codes with.
_TOTP_SIGNING = {"algorithm": "SHA1", "digits": "6", "period": "30"}


def _totp_secret(spec: CredentialSpec, text: str) -> str:
    """The base32 secret exactly as the payout signing will use it, or
    INVALID_VALUE. Only presentation is removed (grouping, case, the link
    around it): the decoded key bytes are never changed."""
    def bad(why: str) -> PaymentConfigError:
        return PaymentConfigError("INVALID_VALUE", f"{spec.label}: {why}", field=spec.name)

    if text.lower().startswith("otpauth://"):
        # The whole authenticator link (QR code contents). Its secret is used only when the link asks for
        # the codes MyHigh5 signs with; other settings would give codes the provider refuses.
        link = urlsplit(text)
        query = parse_qs(link.query)
        if link.netloc.lower() != "totp":
            raise bad("the authenticator link is not a time-based (TOTP) key.")
        if any((query.get(name) or [value])[0].strip().upper() != value for name, value in _TOTP_SIGNING.items()):
            raise bad("the authenticator link uses settings MyHigh5 cannot sign with (SHA1, 6 digits, 30 seconds).")
        text = (query.get("secret") or [""])[0]
    # Shown in groups by authenticator apps and password managers: whitespace or hyphens between the groups.
    # Base32 is case-insensitive, so neither changes the key.
    text = re.sub(r"[\s-]+", "", text).upper()
    if not re.fullmatch(r"[A-Z2-7]+=*", text):
        raise bad("must be a base32 authenticator secret (letters A-Z and digits 2-7 only).")
    try:
        pyotp.TOTP(text).byte_secret()            # the decoding the payout signing does
    except (binascii.Error, ValueError):
        raise bad("is not a complete base32 authenticator secret.") from None
    return text


def _clean_credential(spec: CredentialSpec, value: Optional[str]) -> str:
    text = str(value or "")
    if spec.name != "PAYOUT_PASSWORD":            # a password is kept exactly as typed (apart from the ends)
        text = text.translate(_INVISIBLE)
    text = text.strip()
    if spec.name == "PAYOUT_TOTP_SECRET":
        text = _totp_secret(spec, text)
    elif spec.name == "PAYOUT_EMAIL":
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", text):
            raise PaymentConfigError("INVALID_VALUE", f"{spec.label}: is not a valid email address.",
                                     field=spec.name)
    elif spec.name != "PAYOUT_PASSWORD" and any(ch.isspace() for ch in text):
        raise PaymentConfigError("INVALID_VALUE", f"{spec.label}: must not contain spaces.", field=spec.name)
    if len(text) < spec.min_length or len(text) > 512:
        raise PaymentConfigError("INVALID_VALUE", f"{spec.label}: the value is too short or too long.",
                                 field=spec.name)
    return text


def _reset_connection_test(row: PaymentSettings) -> None:
    # A test result describes the credentials it was made with.
    row.last_connection_test_status = None
    row.last_connection_ok_at = None
    row.last_connection_test_detail = None


def set_credentials(db: Session, actor, values: Dict[str, Optional[str]], *, password: Optional[str],
                    ip: Optional[str] = None, now: Optional[datetime] = None) -> List[str]:
    """Store or REPLACE credentials. A blank or absent value means KEEP the
    existing one; nothing is ever deleted here. Commits. Returns the names
    that were written."""
    now = now or datetime.utcnow()
    _authorize(actor, password)
    unknown = sorted(set(values) - set(CREDENTIALS))
    if unknown:
        raise PaymentConfigError("INVALID_FIELD", "Unknown credential: " + ", ".join(unknown))
    cleaned = {name: _clean_credential(CREDENTIALS[name], value) for name, value in values.items()
               if str(value or "").strip()}
    if not cleaned:
        return []
    if not payment_crypto.key_configured():
        raise PaymentConfigError("ENCRYPTION_KEY_MISSING",
                                 "PAYMENT_SETTINGS_ENCRYPTION_KEY is not configured on the server, so a "
                                 "credential cannot be stored securely.")
    row = _row_for_update(db)
    if row.crypto_auto_payout_enabled and any(CREDENTIALS[n].group == "payout" for n in cleaned):
        # The engine would send the next payout with them.
        try:
            require_activation(actor, "replace a payout credential while automatic payouts are on")
        except PaymentConfigError:
            db.rollback()
            raise
    stored = _stored(db)
    added, replaced = [], []
    for name, value in cleaned.items():
        ciphertext = payment_crypto.encrypt(value, payment_crypto.PURPOSE_CREDENTIAL + name)
        existing = stored.get(name)
        if existing is None:
            db.add(PaymentCredential(provider=PROVIDER, name=name, ciphertext=ciphertext, set_at=now,
                                     set_by=actor.id))
            added.append(name)
        else:
            existing.ciphertext, existing.set_at, existing.set_by = ciphertext, now, actor.id
            replaced.append(name)
    row.version = int(row.version) + 1
    row.updated_by = actor.id
    _reset_connection_test(row)
    _audit(db, row, actor_id=actor.id, action="CREDENTIALS_STORED", ip=ip,
           new={"credentials_added": sorted(added), "credentials_replaced": sorted(replaced)})
    db.commit()
    invalidate_runtime()
    return sorted(cleaned)


def delete_credential(db: Session, actor, name: str, *, password: Optional[str], ip: Optional[str] = None) -> bool:
    """Explicitly delete ONE stored credential. Commits. Refused while the
    database is the source in use for its group and automatic payouts are on."""
    _authorize(actor, password)
    spec = CREDENTIALS.get(str(name or "").strip().upper())
    if spec is None:
        raise PaymentConfigError("INVALID_FIELD", "Unknown credential.")
    row = _row_for_update(db)
    if spec.group == "payout" and row.crypto_auto_payout_enabled:
        try:
            require_activation(actor, "delete a payout credential while automatic payouts are on")
        except PaymentConfigError:
            db.rollback()
            raise
    existing = _stored(db).get(spec.name)
    if existing is None:
        db.rollback()
        return False
    if (spec.group == "payout" and row.payout_credential_source == SOURCE_DATABASE
            and row.crypto_auto_payout_enabled):
        db.rollback()
        raise PaymentConfigError("IN_USE", "Switch automatic payouts off before deleting a payout credential.")
    db.delete(existing)
    row.version = int(row.version) + 1
    row.updated_by = actor.id
    _reset_connection_test(row)
    _audit(db, row, actor_id=actor.id, action="CREDENTIAL_DELETED", ip=ip, new={"credential": spec.name})
    db.commit()
    invalidate_runtime()
    return True


# ---------------------------------------------------------------------------
# Settings update
# ---------------------------------------------------------------------------

def _validate_combination(db: Session, row: PaymentSettings, merged: Dict[str, Any], changed: Dict[str, Any],
                          confirmation: Optional[str], now: datetime) -> None:
    def refuse(code: str, message: str, field: Optional[str] = None) -> PaymentConfigError:
        return PaymentConfigError(code, message, field=field)

    if merged["usd_fee_min"] > merged["usd_fee_max"]:
        raise refuse("INVALID_VALUE", "The minimum withdrawal fee cannot exceed the maximum withdrawal fee.",
                     "usd_fee_min")
    config = _from_values(merged, version=0, persisted=False)
    fee, net = config.usd_fee(merged["usd_min_usd"])
    if net <= 0:
        raise refuse("INVALID_VALUE",
                     f"At the minimum USD cashout (${merged['usd_min_usd']:.2f}) the fee (${fee:.2f}) would "
                     "leave nothing for the member. Raise the minimum or lower the fee.", "usd_min_usd")
    if merged["crypto_min_usd"] > merged["max_single_payout_usd"]:
        raise refuse("INVALID_VALUE", "The minimum crypto cashout cannot exceed the maximum single payout.",
                     "crypto_min_usd")
    if merged["max_single_payout_usd"] > merged["max_daily_payout_usd"]:
        raise refuse("INVALID_VALUE", "The maximum single payout cannot exceed the maximum daily payout amount.",
                     "max_single_payout_usd")

    stored: Optional[Dict[str, PaymentCredential]] = None
    for group, names, key in (("pay-in", PAYIN_CREDENTIALS, "payin_credential_source"),
                              ("payout", PAYOUT_CREDENTIALS, "payout_credential_source")):
        if key in changed and merged[key] == SOURCE_DATABASE:
            stored = _stored(db) if stored is None else stored
            missing = [CREDENTIALS[n].label for n in names if n not in stored or _decrypt(stored[n]) is None]
            if missing:
                raise refuse("CREDENTIALS_INCOMPLETE",
                             f"Store every {group} credential before switching its source to the database. "
                             "Missing or unreadable: " + ", ".join(missing) + ".", key)

    account = (merged["usd_settlement_account"] or "").strip()
    if account and ("usd_settlement_account" in changed or changed.get("usd_settlement_enabled")):
        if not db.query(ChartOfAccounts.id).filter(ChartOfAccounts.account_code == account).first():
            raise refuse("INVALID_VALUE", f"Ledger account {account} does not exist.", "usd_settlement_account")
    if changed.get("usd_settlement_enabled") is True:
        if not account:
            raise refuse("UNSAFE_ACTIVATION", "Choose the settlement ledger account before enabling USD "
                                              "settlement.", "usd_settlement_enabled")
        if (confirmation or "").strip() != CONFIRM_USD_SETTLEMENT:
            raise refuse("CONFIRMATION_REQUIRED", f'Type "{CONFIRM_USD_SETTLEMENT}" to confirm.',
                         "usd_settlement_enabled")

    if changed.get("network_fee_policy") == FEE_COMPANY_PAYS:
        raise refuse("POLICY_RETIRED", "Network fees are paid by the beneficiary. COMPANY_PAYS is retired and "
                                       "cannot be selected.", "network_fee_policy")
    if changed.get("provider_fee_mode") == FEE_MODE_CHARGED:
        raise refuse("NOT_AVAILABLE", "CHARGED_TO_BALANCE is not available: under it MyHigh5 would bear the "
                                      "network fee.", "provider_fee_mode")
    if changed.get("provider_fee_mode") == FEE_MODE_DEDUCTED and (confirmation or "").strip() != CONFIRM_FEE_MODE:
        raise refuse("CONFIRMATION_REQUIRED",
                     "Select this only after the provider confirmed that it takes its fee out of the amount "
                     f'sent. Type "{CONFIRM_FEE_MODE}" to confirm.', "provider_fee_mode")
    if changed.get("fee_terms_approved") is True:
        field = "fee_terms_approved"
        if any(name in changed for name in _FEE_TERMS_FIELDS):
            raise refuse("UNSAFE_ACTIVATION", "Save the network fee settings first, then approve them in a "
                                              "separate change.", field)
        gate = replace(config, fee_terms_approved=True).fee_rules_gate()
        if gate is not None:
            raise refuse("UNSAFE_ACTIVATION", FEE_GATE_MESSAGES[gate], field)
        if (confirmation or "").strip() != CONFIRM_FEE_LIMITS:
            raise refuse("CONFIRMATION_REQUIRED", f'Type "{CONFIRM_FEE_LIMITS}" to confirm.', field)

    if changed.get("crypto_auto_payout_enabled") is True:
        field = "crypto_auto_payout_enabled"
        if not merged["provider_enabled"] or not merged["crypto_cashout_enabled"]:
            raise refuse("UNSAFE_ACTIVATION", "Enable the provider and Crypto Cashout first.", field)
        gate = replace(config, **_suspension_state(row)).fee_gate()
        if gate is not None:
            raise refuse("UNSAFE_ACTIVATION", FEE_GATE_MESSAGES[gate], field)
        credentials = resolve_credentials(db, config)
        if not credentials.payout_ready:
            raise refuse("UNSAFE_ACTIVATION", "Payout credentials are incomplete: "
                         + ", ".join(credentials.payout_missing) + ".", field)
        tested = row.last_connection_ok_at
        if row.last_connection_test_status != "OK" or tested is None or now - tested > CONNECTION_TEST_MAX_AGE:
            raise refuse("UNSAFE_ACTIVATION", "Run a successful connection test (provider reachable, payout "
                         "key accepted, custody balance readable) in the last 24 hours first.", field)
        if (confirmation or "").strip() != CONFIRM_AUTO_PAYOUT:
            raise refuse("CONFIRMATION_REQUIRED", f'Type "{CONFIRM_AUTO_PAYOUT}" to confirm.', field)

    if _resumes_payouts(changed, merged):
        # Automatic payouts are configured on: the provider switch is the last thing holding them.
        # Same proof as switching automatic payouts on (the activation permission is required by
        # activation_required): a recent successful connection test and the typed phrase.
        field = "provider_enabled"
        tested = row.last_connection_ok_at
        if row.last_connection_test_status != "OK" or tested is None or now - tested > CONNECTION_TEST_MAX_AGE:
            raise refuse("UNSAFE_ACTIVATION", "Automatic payouts would resume: run a successful connection test "
                         "(provider reachable, payout key accepted, custody balance readable) in the last 24 hours "
                         "first.", field)
        if (confirmation or "").strip() != CONFIRM_PROVIDER_RESUME:
            raise refuse("CONFIRMATION_REQUIRED", "Automatic payouts would resume at the next cycle. "
                         f'Type "{CONFIRM_PROVIDER_RESUME}" to confirm.', field)


def _resumes_payouts(changed: Dict[str, Any], merged: Dict[str, Any]) -> bool:
    """Does this change switch the provider back on while automatic payouts stay configured on?
    (Switching automatic payouts on in the same change has its own, stricter check.)"""
    return (changed.get("provider_enabled") is True and bool(merged.get("crypto_auto_payout_enabled"))
            and "crypto_auto_payout_enabled" not in changed)


def _activates(changed: Dict[str, Any], merged: Optional[Dict[str, Any]] = None) -> bool:
    """Does this change approve or switch on something on the strength of the
    OTHER values in force? Such a change must name the configuration version
    the administrator was looking at."""
    return (changed.get("fee_terms_approved") is True or changed.get("crypto_auto_payout_enabled") is True
            or changed.get("usd_settlement_enabled") is True
            or changed.get("provider_fee_mode") == FEE_MODE_DEDUCTED
            or (merged is not None and _resumes_payouts(changed, merged)))


def update_settings(db: Session, actor, changes: Dict[str, Any], *, password: Optional[str],
                    confirmation: Optional[str] = None, ip: Optional[str] = None,
                    now: Optional[datetime] = None, expected_version: Optional[int] = None) -> PaymentConfig:
    """Validate and store a set of setting changes. Commits. Reserves, releases
    and sends nothing: the engine reads the new values on its next run.

    `expected_version` is the configuration version the administrator was
    shown. When it is given and the configuration has changed since, nothing is
    stored (STALE_CONFIGURATION). An approval or an activation is refused
    without it, so nobody approves values they were not shown."""
    now = now or datetime.utcnow()
    _authorize(actor, password)
    unknown = sorted(set(changes) - set(FIELDS))
    if unknown:
        raise PaymentConfigError("INVALID_FIELD", "Unknown setting: " + ", ".join(unknown))
    typed = {name: _coerce(FIELDS[name], value) for name, value in changes.items()}
    row = _row_for_update(db)
    current = {name: getattr(row, name) for name in _CONFIG_FIELDS}
    current = {k: (Decimal(str(v)) if isinstance(v, (Decimal, float)) else v) for k, v in current.items()}
    changed = {name: value for name, value in typed.items() if current[name] != value}
    if not changed:
        db.rollback()
        return load(db)
    activating = activation_required(current, changed)
    if activating:
        try:
            require_activation(actor, "; ".join(what for _name, what in activating), field=activating[0][0])
        except PaymentConfigError:
            db.rollback()
            raise
    if expected_version is not None and int(expected_version) != int(row.version):
        db.rollback()
        raise PaymentConfigError("STALE_CONFIGURATION",
                                 "The configuration was changed by someone else since this page was loaded. "
                                 "Nothing was saved. Reload, review the values in force and try again.")
    if (current["fee_terms_approved"] and "fee_terms_approved" not in changed
            and any(name in changed for name in _FEE_TERMS_FIELDS)):
        # The approval covered the values as they were; changed values need a new one.
        changed["fee_terms_approved"] = False
    merged = {**current, **changed}
    try:
        _validate_combination(db, row, merged, changed, confirmation, now)
        if expected_version is None and _activates(changed, merged):
            raise PaymentConfigError("VERSION_REQUIRED",
                                     "An approval or an activation must name the configuration version it was "
                                     "decided on. Reload the page and try again.")
    except PaymentConfigError:
        db.rollback()
        raise
    old = {name: current[name] for name in changed}
    audited = dict(changed)
    if _resumes_payouts(changed, merged):
        # Said in the audit record: this change let automatic payouts resume, on the strength of that test.
        audited["payouts_may_resume"] = True
        audited["connection_test_ok_at"] = row.last_connection_ok_at
    for name, value in changed.items():
        setattr(row, name, value)
    if "payin_credential_source" in changed or "payout_credential_source" in changed:
        _reset_connection_test(row)
    row.version = int(row.version) + 1
    row.updated_by = actor.id
    _audit(db, row, actor_id=actor.id, action="SETTINGS_UPDATED", old=old, new=audited, ip=ip)
    db.commit()
    invalidate_runtime()
    return load(db)


PAUSE_REASON_MIN_LENGTH = 10


def pause_payouts(db: Session, actor, *, password: Optional[str], reason: str, ip: Optional[str] = None,
                  now: Optional[datetime] = None) -> PaymentConfig:
    """Emergency stop: switch automatic payouts OFF at once. Commits.

    Allowed to an administrator who processes cashouts (or manages payment
    settings), with their current password and a reason. Nothing new is reserved
    or sent from the next payout step on; payouts already handed to the provider
    keep being reconciled. Resuming is the ordinary activation of automatic
    payouts (Finance & Payments, activation permission and confirmation)."""
    now = now or datetime.utcnow()
    if not (has_permission(actor, PERMISSION_PROCESS) or has_permission(actor, PERMISSION_MANAGE)):
        raise PaymentConfigError("FORBIDDEN", f"The {PERMISSION_PROCESS} permission is required.")
    require_reauth(actor, password)
    reason = " ".join(str(reason or "").split())
    if len(reason) < PAUSE_REASON_MIN_LENGTH:
        raise PaymentConfigError("REASON_REQUIRED", f"Say why (at least {PAUSE_REASON_MIN_LENGTH} characters).")
    row = _row_for_update(db)
    if not row.crypto_auto_payout_enabled:
        db.rollback()
        return load(db)
    row.crypto_auto_payout_enabled = False
    row.version = int(row.version) + 1
    row.updated_by = actor.id
    _audit(db, row, actor_id=actor.id, action="PAYOUTS_PAUSED", old={"crypto_auto_payout_enabled": True},
           new={"crypto_auto_payout_enabled": False, "reason": reason[:300]}, ip=ip)
    db.commit()
    invalidate_runtime()
    return load(db)


def suspend_payouts(db: Session, *, reason: str, cashout_id: Optional[int] = None,
                    now: Optional[datetime] = None) -> bool:
    """A payout showed a confirmed financial inconsistency. Stop ALL further
    crypto payouts and keep the reason until an administrator reviews it and
    reactivates them explicitly (reactivate_payouts). No commit: it is part of
    the caller's transaction. True when something changed.

    Every reason shows that the provider did not behave as configured, so the
    provider fee behaviour also goes back to UNVERIFIED and the approval of the
    limits is withdrawn. Restoring those never lifts the suspension, and
    neither does recording a fee afterwards."""
    if reason not in SUSPENSION_MESSAGES:
        raise ValueError(f"unknown suspension reason: {reason}")
    now = now or datetime.utcnow()
    row = _row_for_update(db)
    current = row.payout_suspended_reason or None
    old = {"payout_suspended_reason": current, "provider_fee_mode": row.provider_fee_mode,
           "fee_terms_approved": bool(row.fee_terms_approved)}
    if current is None:                             # the first finding is the one to review first
        row.payout_suspended_reason = reason
        row.payout_suspended_at = now
        row.payout_suspended_cashout_id = cashout_id
    row.provider_fee_mode = FEE_MODE_UNVERIFIED
    row.fee_terms_approved = False
    new = {"payout_suspended_reason": row.payout_suspended_reason, "provider_fee_mode": row.provider_fee_mode,
           "fee_terms_approved": bool(row.fee_terms_approved)}
    if new == old:
        return False
    row.version = int(row.version) + 1
    _audit(db, row, actor_id=None, action="PAYOUTS_SUSPENDED", old=old,
           new={**new, "reason": reason, "cashout_id": cashout_id})
    logger.error("Crypto payouts suspended: %s (cashout %s)", reason, cashout_id)
    return True


def suspension_view(db: Session) -> Optional[dict]:
    row = load_row(db)
    if row is None or not row.payout_suspended_reason:
        return None
    reason = row.payout_suspended_reason
    return {"reason": reason, "message": SUSPENSION_MESSAGES.get(reason, reason),
            "since": row.payout_suspended_at.isoformat() if row.payout_suspended_at else None,
            "cashout_id": row.payout_suspended_cashout_id,
            "rules_gate": load(db).fee_rules_gate()}


def reactivate_payouts(db: Session, actor, *, password: Optional[str], confirmation: Optional[str],
                       note: Optional[str], ip: Optional[str] = None) -> PaymentConfig:
    """An administrator who reviewed the suspension lifts it. Commits. A
    separate, deliberate act: the permission, the current password, the typed
    phrase and a written note of what was found are all required, and it is
    refused while the network fee rules are not in force again. It changes no
    setting, sends nothing, and does not switch automatic payouts on."""
    _authorize(actor, password, activation="lift a payout suspension")
    text = " ".join(str(note or "").split())
    if len(text) < 20:
        raise PaymentConfigError("REVIEW_NOTE_REQUIRED",
                                 "Describe what was reviewed and how it was resolved (at least 20 characters).")
    if any(ord(ch) < 32 for ch in text) or len(text) > 500:
        raise PaymentConfigError("REVIEW_NOTE_REQUIRED", "The review note may have at most 500 characters.")
    if (confirmation or "").strip() != CONFIRM_REACTIVATION:
        raise PaymentConfigError("CONFIRMATION_REQUIRED", f'Type "{CONFIRM_REACTIVATION}" to confirm.')
    row = _row_for_update(db)
    reason = row.payout_suspended_reason or None
    if reason is None:
        db.rollback()
        raise PaymentConfigError("NOT_SUSPENDED", "Crypto payouts are not suspended.")
    gate = _from_values({name: getattr(row, name) for name in _CONFIG_FIELDS}, version=0,
                        persisted=True).fee_rules_gate()
    if gate is not None:
        db.rollback()
        raise PaymentConfigError("UNSAFE_ACTIVATION", "Resolve this first: " + FEE_GATE_MESSAGES[gate])
    old = {"payout_suspended_reason": reason, "payout_suspended_cashout_id": row.payout_suspended_cashout_id,
           "payout_suspended_at": row.payout_suspended_at}
    row.payout_suspended_reason = None
    row.payout_suspended_at = None
    row.payout_suspended_cashout_id = None
    row.version = int(row.version) + 1
    row.updated_by = actor.id
    _audit(db, row, actor_id=actor.id, action="PAYOUTS_REACTIVATED", old=old,
           new={"payout_suspended_reason": None, "review_note": text}, ip=ip)
    db.commit()
    return load(db)


# ---------------------------------------------------------------------------
# Runtime view for code that has no database session (pay-in HTTP helpers)
# ---------------------------------------------------------------------------

@dataclass(frozen=True, repr=False)
class PayinRuntime:
    provider_enabled: bool
    source: str
    api_key: Optional[str]
    # NOWPayments checkout switch (default on: an older caller keeps today's behaviour).
    checkout_enabled: bool = True

    @property
    def checkout_allowed(self) -> bool:
        return bool(self.provider_enabled and self.checkout_enabled)

    def __repr__(self) -> str:
        return (f"PayinRuntime(enabled={self.provider_enabled}, checkout={self.checkout_enabled}, "
                f"source={self.source}, key={'set' if self.api_key else 'none'})")


_RUNTIME_TTL_SECONDS = 30.0
_runtime: Dict[str, Any] = {"at": 0.0, "value": None}


def invalidate_runtime() -> None:
    _runtime["at"], _runtime["value"] = 0.0, None
    try:
        from app.services import nowpayments_service

        nowpayments_service.forget_payout_session()
    except Exception:  # noqa: BLE001
        pass


def build_payin_runtime(db: Session) -> PayinRuntime:
    config = load(db)
    return PayinRuntime(config.provider_enabled, config.payin_credential_source,
                        resolve_credentials(db, config).get("PAYIN_API_KEY"), config.checkout_enabled)


def nowpayments_checkout_problem(db: Session, config: Optional[PaymentConfig] = None) -> Optional[str]:
    """Why a NEW NOWPayments checkout cannot be created now (None = it can). Read from the
    database, never from a cache: the provider and checkout switches, then the pay-in API key
    and the IPN secret in force (without the secret no payment could ever be confirmed)."""
    config = config or load(db)
    if not config.provider_enabled:
        return "NOWPayments is switched off."
    if not config.checkout_enabled:
        return "NOWPayments checkout is switched off."
    credentials = resolve_credentials(db, config)
    missing = [CREDENTIALS[name].label for name in PAYIN_CREDENTIALS if not credentials.get(name)]
    if missing:
        return "Missing or unreadable: " + ", ".join(missing) + "."
    return None


def nowpayments_checkout_available(db: Session) -> bool:
    """A NEW NOWPayments checkout may be created now."""
    return nowpayments_checkout_problem(db) is None


def payin_runtime() -> PayinRuntime:
    """Pay-in settings for helpers called without a session, cached briefly.

    If the configuration store cannot be read, the last value that WAS read is
    kept; if none ever was (the store has never been reachable in this
    process), pay-ins use the environment exactly as before this module
    existed. Payouts never take this path: they resolve their credentials from
    the engine's own session and stop when that fails."""
    now = time.monotonic()
    cached = _runtime["value"]
    if cached is not None and now - float(_runtime["at"]) < _RUNTIME_TTL_SECONDS:
        return cached
    try:
        from app.db.session import SessionLocal

        db = SessionLocal()
        try:
            value = build_payin_runtime(db)
        finally:
            db.close()
    except Exception:  # noqa: BLE001
        if cached is not None:
            logger.error("Payment configuration could not be read; keeping the last known pay-in settings")
            value = cached
        else:
            value = PayinRuntime(True, SOURCE_ENVIRONMENT, _env_value(CREDENTIALS["PAYIN_API_KEY"]))
    _runtime["at"], _runtime["value"] = now, value
    return value


def ipn_secret(db: Session) -> Optional[str]:
    """The IPN secret in force, from the caller's session. Read failures fall
    back to the environment secret only when the store has no configuration."""
    try:
        with db.begin_nested():
            return resolve_credentials(db).get("IPN_SECRET")
    except Exception:  # noqa: BLE001
        logger.error("Payment configuration could not be read while verifying an IPN; using the environment secret")
        return _env_value(CREDENTIALS["IPN_SECRET"])


# ---------------------------------------------------------------------------
# Connection test. Read-only: documented GET requests, plus the provider's
# login request (POST /v1/auth), which only returns a five-minute session
# token that is discarded at once. It creates no payment, starts no payout,
# confirms nothing and moves nothing.
# ---------------------------------------------------------------------------

HttpGet = Callable[[str, Dict[str, str]], Tuple[int, str]]
PayoutLogin = Callable[["ProviderCredentials"], None]


def _http_get(url: str, headers: Dict[str, str]) -> Tuple[int, str]:
    import httpx

    with httpx.Client(timeout=httpx.Timeout(15.0, connect=5.0)) as client:
        response = client.get(url, headers=headers)
    return response.status_code, response.text or ""


def _classify(status_code: int, body: str) -> str:
    if 200 <= status_code < 300:
        return "OK"
    if status_code == 401:
        return "AUTH_FAILED"
    if status_code == 403:
        return "IP_NOT_WHITELISTED" if re.search(r"\bip\b", body or "", re.IGNORECASE) else "PERMISSION_DENIED"
    if status_code == 404:
        return "ENDPOINT_NOT_AVAILABLE"
    if status_code == 429:
        return "RATE_LIMITED"
    return "PROVIDER_ERROR" if status_code >= 500 else "REFUSED"


def _payout_login(credentials: "ProviderCredentials") -> None:
    from app.services import nowpayments_service

    nowpayments_service.payout_login_check_sync(credentials)


def _login_result(credentials: "ProviderCredentials", login: PayoutLogin) -> str:
    """One code for the payout login check; never the provider's message."""
    from app.services import nowpayments_service

    if not (credentials.get("PAYOUT_EMAIL") and credentials.get("PAYOUT_PASSWORD")):
        return "NOT_CONFIGURED"
    try:
        login(credentials)
    except nowpayments_service.NowPaymentsError as exc:
        if exc.status_code is None:
            return "INVALID_RESPONSE" if exc.stage == "auth" else "UNREACHABLE"
        if exc.ip_refused:
            return "IP_NOT_WHITELISTED"
        code = int(exc.status_code)
        # Any other 4xx answer to a login is a refused login (the provider
        # answers an unknown account with 404).
        return "AUTH_FAILED" if 400 <= code < 500 and code != 429 else _classify(code, "")
    except Exception:  # noqa: BLE001 - no answer
        return "UNREACHABLE"
    return "OK"


CONNECTION_MESSAGES = {
    "OK": "Successful.",
    "PARTIAL": "Pay-in is working. Payout credentials are not configured.",
    "NOT_CONFIGURED": "The credential is not configured.",
    "AUTH_FAILED": "The provider rejected the credential (authentication failed).",
    "IP_NOT_WHITELISTED": "The provider refused this server's IP address. Add the server's IPv4 and IPv6 "
                          "addresses to the provider's IP whitelist.",
    "PERMISSION_DENIED": "The credential is valid but is not permitted to do this (custody or payouts may "
                         "not be enabled on the provider account).",
    "ENDPOINT_NOT_AVAILABLE": "The provider does not offer this endpoint for the account.",
    "RATE_LIMITED": "The provider is rate limiting requests. Try again later.",
    "PROVIDER_ERROR": "The provider reported an internal error.",
    "REFUSED": "The provider refused the request.",
    "UNREACHABLE": "The provider could not be reached.",
    "INVALID_RESPONSE": "The provider's answer could not be read.",
    "NOT_TESTED": "Not tested (an earlier check has to succeed first).",
}


def run_connection_test(db: Session, actor, *, http: Optional[HttpGet] = None, ip: Optional[str] = None,
                        now: Optional[datetime] = None, login: Optional[PayoutLogin] = None) -> dict:
    """Check the provider with documented read-only requests and record a
    sanitized result (codes and numbers; never a credential or a response
    body). Commits."""
    import json

    from app.services import nowpayments_service

    now = now or datetime.utcnow()
    if not has_permission(actor, PERMISSION_MANAGE):
        raise PaymentConfigError("FORBIDDEN", f"The {PERMISSION_MANAGE} permission is required.")
    http = http or _http_get
    config = load(db)
    credentials = resolve_credentials(db, config)
    base = nowpayments_service.api_base()
    currency = config.crypto_payout_currency
    checks: Dict[str, str] = {}
    facts: Dict[str, str] = {}

    def get(name: str, path: str, key: Optional[str], *, needs_key: bool = True):
        if needs_key and not key:
            checks[name] = "NOT_CONFIGURED"
            return None
        try:
            status_code, body = http(f"{base}/{path}", {"x-api-key": key} if key else {})
        except Exception:  # noqa: BLE001 - no answer
            checks[name] = "UNREACHABLE"
            return None
        checks[name] = _classify(int(status_code), body)
        if checks[name] != "OK":
            return None
        try:
            return json.loads(body or "null")
        except ValueError:
            checks[name] = "INVALID_RESPONSE"
            return None

    def number(value: Any) -> Optional[str]:
        try:
            parsed = Decimal(str(value))
            return str(parsed) if parsed.is_finite() else None
        except (InvalidOperation, ValueError, TypeError):
            return None

    get("api_status", "status", None, needs_key=False)
    get("payin_api_key", "currencies", credentials.get("PAYIN_API_KEY"))
    payout_key = credentials.get("PAYOUT_API_KEY")
    balance = get("custody_balance", "balance", payout_key)
    if isinstance(balance, dict):
        entry = next((v for k, v in balance.items() if str(k).lower() == currency), None)
        facts["custody_balance"] = number((entry or {}).get("amount") if isinstance(entry, dict) else 0) or "0"
        if isinstance(entry, dict) and number(entry.get("pendingAmount")):
            facts["custody_pending"] = number(entry.get("pendingAmount"))
    minimum = get("payout_minimum", f"payout-withdrawal/min-amount/{currency}", payout_key)
    if isinstance(minimum, dict):
        value = number(minimum.get("result") or minimum.get("min_amount"))
        if value:
            facts["payout_minimum"] = value
    fee = get("payout_network_fee", f"payout/fee?currency={currency}&amount={config.crypto_min_usd}", payout_key)
    if isinstance(fee, dict):
        value = number(fee.get("fee"))
        if value:
            facts["network_fee"] = value

    # The payout login is tried only when the payout key itself was accepted:
    # a wrong password is never sent again and again to a provider that is
    # already refusing this server.
    if checks["custody_balance"] == "OK":
        checks["payout_login"] = _login_result(credentials, login or _payout_login)
    elif checks["custody_balance"] == "NOT_CONFIGURED":
        checks["payout_login"] = "NOT_CONFIGURED"
    else:
        checks["payout_login"] = "NOT_TESTED"

    payin_ok = checks["api_status"] == "OK" and checks["payin_api_key"] == "OK"
    payout_names = ("custody_balance", "payout_minimum", "payout_network_fee", "payout_login")
    if all(code == "OK" for code in checks.values()):
        overall = "OK"
    elif payin_ok and all(checks[n] == "NOT_CONFIGURED" for n in payout_names):
        overall = "PARTIAL"
    else:
        overall = next(code for code in checks.values() if code != "OK")

    detail = {"checks": checks, "facts": facts, "environment": "sandbox" if settings.NOWPAYMENTS_SANDBOX else "production",
              "payin_source": credentials.payin_source, "payout_source": credentials.payout_source,
              "payout_login": checks["payout_login"]}
    row = _row_for_update(db)
    row.last_connection_test_at = now
    row.last_connection_test_status = overall
    row.last_connection_test_detail = detail
    if overall == "OK":
        row.last_connection_ok_at = now
    _audit(db, row, actor_id=actor.id, action="CONNECTION_TESTED", ip=ip,
           new={"result": overall, "checks": dict(checks)})
    db.commit()
    return connection_view(load_row(db))


def load_row(db: Session) -> Optional[PaymentSettings]:
    return db.query(PaymentSettings).filter(PaymentSettings.id == SETTINGS_ROW_ID).first()


def connection_view(row: Optional[PaymentSettings]) -> dict:
    detail = (row.last_connection_test_detail if row is not None else None) or {}
    status = row.last_connection_test_status if row is not None else None
    checks = detail.get("checks") or {}
    return {
        "status": status or "NOT_TESTED",
        "message": CONNECTION_MESSAGES.get(status or "", "No connection test has been run with the current credentials."),
        "tested_at": row.last_connection_test_at.isoformat() if row is not None and row.last_connection_test_at else None,
        "last_success_at": row.last_connection_ok_at.isoformat() if row is not None and row.last_connection_ok_at else None,
        "checks": [{"name": name, "status": code, "message": CONNECTION_MESSAGES.get(code, code)}
                   for name, code in checks.items()],
        "facts": detail.get("facts") or {},
        "payout_login": detail.get("payout_login") or "NOT_TESTED",
    }


# ---------------------------------------------------------------------------
# Webhook (IPN) health: bounded daily counters, never a request body
# ---------------------------------------------------------------------------

WEBHOOK_OUTCOMES = ("ACCEPTED", "REJECTED_SIGNATURE", "INVALID_JSON", "UNKNOWN_ORDER", "IDENTITY_REJECTED", "ERROR",
                    "PAYOUT_NOTICE")


SIGNED_WEBHOOK_OUTCOMES = ("ACCEPTED", "UNKNOWN_ORDER", "IDENTITY_REJECTED", "ERROR", "PAYOUT_NOTICE")


def record_webhook(db: Session, outcome: str, *, now: Optional[datetime] = None) -> None:
    """Count one provider callback. Written in a savepoint and never raises:
    a failure to count must not affect the callback itself. No commit."""
    now = now or datetime.utcnow()
    if outcome not in WEBHOOK_OUTCOMES:
        outcome = "ERROR"
    for _attempt in range(2):
        try:
            with db.begin_nested():
                row = (db.query(PaymentWebhookStat)
                       .filter(PaymentWebhookStat.provider == PROVIDER, PaymentWebhookStat.day == now.date(),
                               PaymentWebhookStat.outcome == outcome).with_for_update().first())
                if row is None:
                    db.add(PaymentWebhookStat(provider=PROVIDER, day=now.date(), outcome=outcome, count=1,
                                              last_at=now))
                else:
                    row.count, row.last_at = int(row.count) + 1, now
                db.flush()
            return
        except IntegrityError:
            continue                                   # another request created today's row first
        except Exception:  # noqa: BLE001
            logger.warning("Payment webhook outcome could not be counted")
            return


def webhook_health(db: Session, *, now: Optional[datetime] = None) -> dict:
    from app.services import nowpayments_service

    now = now or datetime.utcnow()
    rows = (db.query(PaymentWebhookStat)
            .filter(PaymentWebhookStat.provider == PROVIDER,
                    PaymentWebhookStat.day >= (now - timedelta(days=7)).date()).all())
    totals = {o: 0 for o in WEBHOOK_OUTCOMES}
    last: Dict[str, Optional[datetime]] = {o: None for o in WEBHOOK_OUTCOMES}
    for row in rows:
        totals[row.outcome] = totals.get(row.outcome, 0) + int(row.count)
        if last.get(row.outcome) is None or row.last_at > last[row.outcome]:
            last[row.outcome] = row.last_at
    url = nowpayments_service.ipn_callback_url()
    accepted, rejected = last["ACCEPTED"], last["REJECTED_SIGNATURE"]
    # Every outcome below was reached only AFTER the signature had verified.
    signed = [last[o] for o in SIGNED_WEBHOOK_OUTCOMES if last.get(o) is not None]
    verified = max(signed) if signed else None
    if not rows:
        status = "NO_CALLBACKS_RECORDED"
    elif rejected is not None and (verified is None or rejected > verified):
        status = "SIGNATURE_REJECTIONS"
    elif verified is not None:
        status = "HEALTHY"
    else:
        status = "ATTENTION"
    return {
        "callback_url": url,
        "callback_url_secure": url.startswith("https://"),
        "callback_url_editable": False,
        "status": status,
        "last_7_days": totals,
        "last_accepted_at": accepted.isoformat() if accepted else None,
        "last_verified_signature_at": verified.isoformat() if verified else None,
        "last_signature_rejection_at": rejected.isoformat() if rejected else None,
        "payout_notices_7_days": totals.get("PAYOUT_NOTICE", 0),
        "signature_verification": "HMAC-SHA512 over the sorted JSON body (x-nowpayments-sig). Never bypassed.",
    }


# ---------------------------------------------------------------------------
# Admin read models
# ---------------------------------------------------------------------------

def _field_view(field: Field, value: Any, default: Any) -> dict:
    return {
        "name": field.name, "group": field.group, "kind": field.kind, "label": field.label, "help": field.help,
        "value": _jsonable(value), "default": _jsonable(default),
        "minimum": _plain(field.minimum) if field.minimum is not None else None,
        "maximum": _plain(field.maximum) if field.maximum is not None else None,
        "choices": list(field.choices), "unit": field.unit, "max_length": field.max_length or None,
        "approval_note": field.approval or None,
        "disabled_choices": [{"value": choice, "reason": reason}
                             for choice, reason in UNSUPPORTED_CHOICES.get(field.name, {}).items()],
        "optional": bool(field.optional),
    }


def activation_view(config: PaymentConfig) -> dict:
    """What the Admin Panel needs to tell an administrator, before they try,
    which changes also need the activation permission. The server decides
    (activation_required); this only describes it."""
    return {
        "permission": PERMISSION_ACTIVATE,
        # setting -> the value that activates
        "values": {"crypto_auto_payout_enabled": True, "checkout_enabled": True, "usd_settlement_enabled": True,
                   "fee_terms_approved": True, "provider_fee_mode": FEE_MODE_DEDUCTED},
        "automatic_payouts_on": bool(config.crypto_auto_payout_enabled),
        "while_automatic_payouts_on": {"fields": list(LIVE_PAYOUT_FIELDS), "switches": list(LIVE_PAYOUT_SWITCHES),
                                       "credential_group": "payout"},
    }


def settings_view(db: Session) -> dict:
    config = load(db)
    base = defaults()
    row = load_row(db)
    return {
        "version": config.version,
        "persisted": config.persisted,
        "updated_at": row.updated_at.isoformat() if row is not None and row.updated_at else None,
        "updated_by": row.updated_by if row is not None else None,
        "fields": [_field_view(f, getattr(config, f.name), base[f.name]) for f in _FIELDS],
        "server_switches": {
            "crypto_auto_payout": crypto_master_switch(),
            "usd_settlement": usd_settlement_master_switch(),
            "environment": "sandbox" if settings.NOWPAYMENTS_SANDBOX else "production",
            "encryption_key_configured": payment_crypto.key_configured(),
        },
        "effective": {
            "automatic_crypto_payouts": config.auto_payout_allowed and resolve_credentials(db, config).payout_ready,
            "usd_settlement": config.usd_settlement_allowed,
        },
        "usd_fee_rule": config.usd_fee_rule(),
        "supported_payout_currencies": [{"code": code, **meta} for code, meta in SUPPORTED_PAYOUT_CURRENCIES.items()],
        "confirmations": {"crypto_auto_payout_enabled": CONFIRM_AUTO_PAYOUT,
                          "usd_settlement_enabled": CONFIRM_USD_SETTLEMENT,
                          "provider_fee_mode": CONFIRM_FEE_MODE,
                          "fee_terms_approved": CONFIRM_FEE_LIMITS,
                          "payout_reactivation": CONFIRM_REACTIVATION,
                          # Asked only while switching the provider on would let automatic payouts resume.
                          **({"provider_enabled": CONFIRM_PROVIDER_RESUME}
                             if config.crypto_auto_payout_enabled and not config.provider_enabled else {})},
        "activation": activation_view(config),
        "payout_suspension": suspension_view(db),
        "network_fee_gate": ({"code": config.fee_gate(), "message": FEE_GATE_MESSAGES[config.fee_gate()]}
                             if config.fee_gate() is not None else None),
        "crypto_sections": [{"key": key, "title": title, "note": note, "fields": list(names)}
                            for key, title, note, names in CRYPTO_SECTIONS],
    }


def provider_view(db: Session) -> dict:
    config = load(db)
    row = load_row(db)
    statuses = credential_status(db, config)
    in_use = {s["name"]: s["in_use"] == "CONFIGURED" for s in statuses}
    connection = connection_view(row)
    facts = connection["facts"]
    meta = SUPPORTED_PAYOUT_CURRENCIES[config.crypto_payout_currency]
    return {
        "provider": PROVIDER,
        "display_name": config.provider_display_name,
        "enabled": config.provider_enabled,
        "checkout_enabled": config.checkout_enabled,
        "checkout_available": nowpayments_checkout_problem(db, config) is None,
        "checkout_problem": nowpayments_checkout_problem(db, config),
        "environment": "sandbox" if settings.NOWPAYMENTS_SANDBOX else "production",
        "environment_editable": False,
        "payin_status": "CONFIGURED" if all(in_use[n] for n in PAYIN_CREDENTIALS) else "NOT CONFIGURED",
        "payout_status": "CONFIGURED" if all(in_use[n] for n in PAYOUT_CREDENTIALS) else "NOT CONFIGURED",
        "custody_status": ("VERIFIED" if "custody_balance" in facts and connection["status"] == "OK"
                           else "NOT VERIFIED"),
        "payout_currency": meta["currency"],
        "payout_network": meta["network"],
        "payout_currency_code": config.crypto_payout_currency,
        "credential_sources": {"payin": config.payin_credential_source, "payout": config.payout_credential_source},
        "credentials": statuses,
        "encryption_key_configured": payment_crypto.key_configured(),
        "connection": connection,
        "readiness": readiness_view(db, config=config, statuses=statuses, connection=connection),
        "last_configuration_update": row.updated_at.isoformat() if row is not None and row.updated_at else None,
        "configuration_version": config.version,
    }


# One vocabulary for every provider capability:
#   DISABLED     switched off here (provider, feature or server switch)
#   UNVERIFIED   not configured, or configured but never proven
#   CONFIGURED   the credentials are present; nothing has proven that they work
#   BLOCKED      a check ran and the provider refused (the reason is given)
#   VERIFIED     a check against the provider succeeded with the current credentials
# Nothing is VERIFIED because a credential is present.
READINESS_STATES = ("DISABLED", "UNVERIFIED", "CONFIGURED", "BLOCKED", "VERIFIED")


def _check_state(configured: bool, code: Optional[str]) -> str:
    if not configured:
        return "UNVERIFIED"
    if code == "OK":
        return "VERIFIED"
    if code in (None, "NOT_TESTED", "NOT_CONFIGURED"):
        return "CONFIGURED"
    return "BLOCKED"


def readiness_view(db: Session, *, config: Optional[PaymentConfig] = None, statuses: Optional[List[dict]] = None,
                   connection: Optional[dict] = None, webhook: Optional[dict] = None) -> dict:
    """What is proven, what is only configured and what the provider refused,
    per capability, with the outstanding requirements in plain words. Built
    only from the stored result of the last connection test, the webhook
    counters and the configuration: it calls nobody."""
    config = config or load(db)
    statuses = statuses if statuses is not None else credential_status(db, config)
    connection = connection or connection_view(load_row(db))
    webhook = webhook or webhook_health(db)
    in_use = {s["name"]: s["in_use"] == "CONFIGURED" for s in statuses}
    codes = {c["name"]: c["status"] for c in connection["checks"]}
    items: List[dict] = []
    todo: List[str] = []

    def item(key: str, label: str, state: str, detail: str) -> None:
        items.append({"key": key, "label": label, "state": state, "detail": detail})

    def explain(code: Optional[str]) -> str:
        return CONNECTION_MESSAGES.get(code or "", "No connection test has been run with the current credentials.")

    if not config.provider_enabled:
        item("provider", "Provider", "DISABLED", "The provider is switched off in Payment Providers.")
        todo.append("Switch the provider on in Payment Providers.")
    else:
        item("provider", "Provider", "CONFIGURED", "The provider is switched on.")
    checkout_problem = nowpayments_checkout_problem(db, config)
    if checkout_problem is None:
        item("checkout", "NOWPayments checkout", "CONFIGURED", "Members can start new NOWPayments payments.")
    else:
        item("checkout", "NOWPayments checkout", "DISABLED",
             f"No new NOWPayments payment can be started: {checkout_problem} "
             "Existing payments are not affected, and the checkout switch does not affect automatic payouts.")

    state = _check_state(in_use["PAYIN_API_KEY"], codes.get("payin_api_key"))
    item("api_authentication", "API authentication (pay-in key)", state,
         explain(codes.get("payin_api_key")) if in_use["PAYIN_API_KEY"] else "The pay-in API key is not configured.")
    if state != "VERIFIED":
        todo.append("Configure the pay-in API key and run the connection test." if not in_use["PAYIN_API_KEY"]
                    else "Run the connection test to prove the pay-in API key.")

    if not in_use["IPN_SECRET"]:
        item("ipn", "Payment notifications (IPN)", "UNVERIFIED", "The IPN secret is not configured.")
        todo.append("Generate an IPN secret in the provider dashboard and configure the same value here.")
    elif not webhook["callback_url_secure"]:
        item("ipn", "Payment notifications (IPN)", "BLOCKED", "The callback URL is not an https address.")
        todo.append("Set BACKEND_PUBLIC_URL to the public https address of the API.")
    elif webhook["status"] == "HEALTHY":
        item("ipn", "Payment notifications (IPN)", "VERIFIED",
             "The most recent signed callback from the provider verified with the configured IPN secret.")
    elif webhook["status"] == "SIGNATURE_REJECTIONS":
        item("ipn", "Payment notifications (IPN)", "BLOCKED",
             "The most recent callbacks were rejected: their signature did not verify.")
        todo.append("Check that the IPN secret configured here is the one shown in the provider dashboard "
                    "(it is displayed in full only when it is generated).")
    else:
        item("ipn", "Payment notifications (IPN)", "CONFIGURED",
             "The IPN secret is configured. No signed callback has been accepted yet, so it is not proven.")
        todo.append("Make one test payment and confirm that its callback is accepted.")

    payout_key = in_use["PAYOUT_API_KEY"]
    custody_code = codes.get("custody_balance")
    custody = _check_state(payout_key, custody_code)
    item("custody", "Custody balance access", custody,
         explain(custody_code) if payout_key else "The payout API key is not configured.")
    whitelist = ("BLOCKED" if "IP_NOT_WHITELISTED" in codes.values()
                 else "VERIFIED" if custody == "VERIFIED" else "UNVERIFIED")
    item("ip_whitelist", "Server IP whitelist", whitelist,
         CONNECTION_MESSAGES["IP_NOT_WHITELISTED"] if whitelist == "BLOCKED"
         else "The provider answered a request that needs a whitelisted address." if whitelist == "VERIFIED"
         else "Not determinable until the payout API key is tested.")
    if whitelist == "BLOCKED":
        todo.append("Whitelist this server's IPv4 and IPv6 addresses in the provider dashboard "
                    "(Settings > Whitelist).")
    elif custody != "VERIFIED":
        todo.append("Configure the payout API key and run the connection test." if not payout_key
                    else "Run the connection test to prove custody access.")

    login_configured = in_use["PAYOUT_EMAIL"] and in_use["PAYOUT_PASSWORD"]
    login = _check_state(login_configured, codes.get("payout_login"))
    item("payout_login", "Payout login", login,
         explain(codes.get("payout_login")) if login_configured
         else "The payout login email and password are not configured.")
    if login != "VERIFIED":
        todo.append("Configure the payout login email and password." if not login_configured
                    else "Run the connection test to prove the payout login.")

    # The second factor can only be proven by confirming a real payout.
    item("payout_2fa", "Payout second factor (authenticator)",
         "CONFIGURED" if in_use["PAYOUT_TOTP_SECRET"] else "UNVERIFIED",
         "The authenticator secret is configured. It can be proven only by confirming a real payout, so it is "
         "never shown as verified here." if in_use["PAYOUT_TOTP_SECRET"]
         else "The authenticator (TOTP) secret is not configured.")
    if not in_use["PAYOUT_TOTP_SECRET"]:
        todo.append("Enable authenticator-app two-step verification on the provider account and configure its "
                    "secret here (email codes cannot be automated).")

    credentials_ready = all(in_use[n] for n in PAYOUT_CREDENTIALS)
    if not crypto_master_switch():
        payouts, detail = "DISABLED", "The server master switch CRYPTO_AUTO_PAYOUT_ENABLED is off."
    elif not (config.provider_enabled and config.crypto_cashout_enabled and config.crypto_auto_payout_enabled):
        payouts, detail = "DISABLED", "Automatic payouts are switched off in Crypto Cashout."
    elif config.fee_gate() is not None:
        payouts, detail = "UNVERIFIED", FEE_GATE_MESSAGES[config.fee_gate()]
    elif not credentials_ready:
        payouts, detail = "UNVERIFIED", "A payout credential is missing."
    elif "BLOCKED" in (custody, login, whitelist):
        payouts, detail = "BLOCKED", "The provider refused a payout check (see above)."
    elif custody == "VERIFIED" and login == "VERIFIED":
        payouts, detail = "CONFIGURED", ("Custody access and the payout login are proven. Creating and "
                                         "confirming a payout is proven only by the first real payout.")
    else:
        payouts, detail = "CONFIGURED", "The payout credentials are present but have not been tested."
    item("automatic_payouts", "Automatic crypto payouts", payouts, detail)

    gate = config.fee_gate()
    item("network_fee_terms", "Network fee paid by the beneficiary", "CONFIGURED" if gate is None else "UNVERIFIED",
         "An administrator confirmed the provider fee behaviour and the member fee limits are approved. Neither "
         "can be checked from here." if gate is None else FEE_GATE_MESSAGES[gate])
    if gate is not None:
        todo.append("Confirm with the provider that it takes its network fee out of the amount sent, set the "
                    "member network fee limits and have them approved (Crypto Cashout).")
    todo.append("Provider side, cannot be checked from here: custody enabled on the account, the payout "
                "wallet addresses whitelisted (or address whitelisting switched off by the provider), and "
                "the custody balance funded in the payout currency.")
    return {"states": list(READINESS_STATES), "items": items, "outstanding": todo,
            "last_test_at": connection["tested_at"], "last_success_at": connection["last_success_at"],
            "last_error": _last_error(connection)}


def _last_error(connection: dict) -> Optional[dict]:
    """The first check of the last connection test that did not succeed, as a
    code and a fixed sentence. Never a provider response."""
    for check in connection["checks"]:
        if check["status"] not in ("OK", "NOT_CONFIGURED", "NOT_TESTED"):
            return {"check": check["name"], "code": check["status"], "message": check["message"],
                    "at": connection["tested_at"]}
    return None


def audit_view(db: Session, *, skip: int = 0, limit: int = 50) -> dict:
    query = db.query(PaymentConfigAudit)
    total = query.count()
    rows = query.order_by(PaymentConfigAudit.id.desc()).offset(skip).limit(limit).all()
    return {"total": total, "items": [{
        "id": r.id, "version": r.version, "action": r.action, "actor_id": r.actor_id,
        "changed_fields": r.changed_fields or [], "old_values": r.old_values or {}, "new_values": r.new_values or {},
        "ip_address": r.ip_address, "created_at": r.created_at.isoformat() if r.created_at else None,
    } for r in rows]}
