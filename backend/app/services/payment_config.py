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
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, fields as dataclass_fields
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Dict, List, Optional, Tuple

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import verify_password
from app.models.accounting import ChartOfAccounts
from app.models.payment_config import PaymentConfigAudit, PaymentCredential, PaymentSettings, PaymentWebhookStat
from app.services import payment_crypto
from app.services.financial_integrity import money

logger = logging.getLogger(__name__)

PERMISSION_MANAGE = "manage_payment_settings"
PERMISSION_PROCESS = "process_cashouts"
SETTINGS_ROW_ID = 1
PROVIDER = "nowpayments"

SOURCE_ENVIRONMENT, SOURCE_DATABASE = "ENVIRONMENT", "DATABASE"
FEE_COMPANY_PAYS, FEE_MEMBER_PAYS = "COMPANY_PAYS", "MEMBER_PAYS"
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
USD_POLICY_MANUAL = "MANUAL_REVIEW"

# The only payout asset the ledger has a treasury account for (1001).
SUPPORTED_PAYOUT_CURRENCIES: Dict[str, Dict[str, str]] = {
    "usdtbsc": {"currency": "USDT", "network": "BSC (BEP20)", "treasury_account": "1001"},
}

CONFIRM_AUTO_PAYOUT = "ENABLE AUTOMATIC PAYOUTS"
CONFIRM_USD_SETTLEMENT = "ENABLE USD SETTLEMENT"
# Automatic payouts can only be switched on with a successful connection test this recent.
CONNECTION_TEST_MAX_AGE = timedelta(hours=24)


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
    Field("provider_enabled", "provider", "bool", "Provider enabled",
          "When off, no new crypto payment is created and no payout is sent. Callbacks for payments "
          "that already exist are still processed.", _const(True)),
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
          "COMPANY_PAYS: the member receives the full amount. MEMBER_PAYS: the estimated network fee is "
          "deducted from the amount sent.", _const(FEE_COMPANY_PAYS), choices=(FEE_COMPANY_PAYS, FEE_MEMBER_PAYS),
          approval="Default for development. Awaiting the business owner's approval."),
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
          "Time a member waits between two crypto payouts.", _const(24), minimum=_D(0), maximum=_D(8760),
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
    payin_credential_source: str
    payout_credential_source: str
    crypto_cashout_enabled: bool
    crypto_auto_payout_enabled: bool
    crypto_min_usd: Decimal
    crypto_payout_currency: str
    network_fee_policy: str
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

    @property
    def auto_payout_allowed(self) -> bool:
        """Every SWITCH that must be on for the engine (credentials are checked separately)."""
        return bool(crypto_master_switch() and self.provider_enabled and self.crypto_cashout_enabled
                    and self.crypto_auto_payout_enabled)

    @property
    def usd_settlement_allowed(self) -> bool:
        return bool(usd_settlement_master_switch() and self.usd_settlement_enabled
                    and (self.usd_settlement_account or "").strip())


_CONFIG_FIELDS = tuple(f.name for f in dataclass_fields(PaymentConfig) if f.name not in ("version", "persisted"))
if set(_CONFIG_FIELDS) != set(FIELDS):
    raise RuntimeError("payment configuration registry is inconsistent")


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


def _from_values(values: Dict[str, Any], *, version: int, persisted: bool) -> PaymentConfig:
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
    return PaymentConfig(**typed, version=version, persisted=persisted)


def default_config() -> PaymentConfig:
    return _from_values(defaults(), version=0, persisted=False)


def load(db: Session) -> PaymentConfig:
    """The configuration in force. Read-only."""
    row = db.query(PaymentSettings).filter(PaymentSettings.id == SETTINGS_ROW_ID).first()
    if row is None:
        return _from_values(defaults(), version=0, persisted=False)
    return _from_values({name: getattr(row, name) for name in _CONFIG_FIELDS}, version=int(row.version),
                        persisted=True)


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
    """Only a role that EXPLICITLY holds the permission. Never implied by
    is_admin or by the 'all' wildcard, and never assigned automatically."""
    if user is None or not getattr(user, "is_active", True):
        return False
    role = getattr(user, "role", None)
    if role is None:
        return False
    names = {p.name for p in (role.permissions or [])}
    if getattr(role, "inherit_from", None) is not None:
        names |= set(role.inherit_from.get_all_permissions())
    return permission in names


def require_reauth(actor, password: Optional[str]) -> None:
    """The administrator proves it is them, now, with the account password."""
    if not password or not verify_password(password, getattr(actor, "hashed_password", "") or ""):
        raise PaymentConfigError("REAUTH_REQUIRED", "Enter your current password to confirm this change.")


def _authorize(actor, password: Optional[str]) -> None:
    if not has_permission(actor, PERMISSION_MANAGE):
        raise PaymentConfigError("FORBIDDEN", f"The {PERMISSION_MANAGE} permission is required.")
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


def _clean_credential(spec: CredentialSpec, value: Optional[str]) -> str:
    text = str(value or "").strip()
    if spec.name == "PAYOUT_TOTP_SECRET":
        text = text.replace(" ", "").upper()
        if not re.fullmatch(r"[A-Z2-7]+=*", text):
            raise PaymentConfigError("INVALID_VALUE", f"{spec.label}: must be a base32 authenticator secret.",
                                     field=spec.name)
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

    if changed.get("crypto_auto_payout_enabled") is True:
        field = "crypto_auto_payout_enabled"
        if not merged["provider_enabled"] or not merged["crypto_cashout_enabled"]:
            raise refuse("UNSAFE_ACTIVATION", "Enable the provider and Crypto Cashout first.", field)
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


def update_settings(db: Session, actor, changes: Dict[str, Any], *, password: Optional[str],
                    confirmation: Optional[str] = None, ip: Optional[str] = None,
                    now: Optional[datetime] = None) -> PaymentConfig:
    """Validate and store a set of setting changes. Commits. Reserves, releases
    and sends nothing: the engine reads the new values on its next run."""
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
    merged = {**current, **changed}
    try:
        _validate_combination(db, row, merged, changed, confirmation, now)
    except PaymentConfigError:
        db.rollback()
        raise
    old = {name: current[name] for name in changed}
    for name, value in changed.items():
        setattr(row, name, value)
    if "payin_credential_source" in changed or "payout_credential_source" in changed:
        _reset_connection_test(row)
    row.version = int(row.version) + 1
    row.updated_by = actor.id
    _audit(db, row, actor_id=actor.id, action="SETTINGS_UPDATED", old=old, new=changed, ip=ip)
    db.commit()
    invalidate_runtime()
    return load(db)


# ---------------------------------------------------------------------------
# Runtime view for code that has no database session (pay-in HTTP helpers)
# ---------------------------------------------------------------------------

@dataclass(frozen=True, repr=False)
class PayinRuntime:
    provider_enabled: bool
    source: str
    api_key: Optional[str]

    def __repr__(self) -> str:
        return f"PayinRuntime(enabled={self.provider_enabled}, source={self.source}, key={'set' if self.api_key else 'none'})"


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
                        resolve_credentials(db, config).get("PAYIN_API_KEY"))


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
                          "usd_settlement_enabled": CONFIRM_USD_SETTLEMENT},
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
