"""Which gateway takes a NEW member payment, or none. The one place that decides it.

  * Each gateway is READY for new payments or not, with the reason:
      NOWPayments: provider switch on, checkout switch on, pay-in API key and
                   IPN secret in force (payment_config.nowpayments_checkout_problem);
      SoncoPay:    switched on, and the key + signing secret of its environment
                   saved and readable (soncopay_settings.checkout_problem).
  * The STORED default (checkout_gateway_settings.default_provider, chosen by a
    Super Admin) is kept as it is, whatever happens to the gateways.
  * The EFFECTIVE default is the stored default while that gateway is ready,
    otherwise NONE. There is no fall back to the other gateway, ever: when the
    default gateway is off or not ready, members are told that payments are
    temporarily unavailable and no deposit is created, until a Super Admin
    explicitly chooses a ready gateway or makes the default one ready again.

Only NEW payments are decided here. A payment keeps the gateway it was created
with: callbacks, status checks, resumes and reconciliation of existing payments
never depend on these switches. Outgoing payouts are not decided here either
(NOWPayments automatic payouts: app.services.cashout_engine; SoncoPay has none).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.services import payment_config, soncopay_settings

UNAVAILABLE_MESSAGE = "Payments are temporarily unavailable. Please try again later."
NOWPAYMENTS, SONCOPAY = soncopay_settings.NOWPAYMENTS, soncopay_settings.PROVIDER
GATEWAYS = (NOWPAYMENTS, SONCOPAY)
LABELS = {NOWPAYMENTS: "NOWPayments", SONCOPAY: "SoncoPay"}


@dataclass(frozen=True)
class GatewayState:
    gateway: str
    enabled: bool                  # the gateway's master switch
    ready: bool                    # may take a NEW member payment now
    reason: Optional[str]          # why not (None when ready)
    environment: str               # NOWPayments: the server's; SoncoPay: the one selected


def nowpayments_state(db: Session, config: Optional[payment_config.PaymentConfig] = None) -> GatewayState:
    config = config or payment_config.load(db)
    problem = payment_config.nowpayments_checkout_problem(db, config)
    environment = "sandbox" if settings.NOWPAYMENTS_SANDBOX else "live"
    return GatewayState(NOWPAYMENTS, bool(config.provider_enabled), problem is None, problem, environment)


def soncopay_state(db: Session) -> GatewayState:
    state = soncopay_settings.current_state(db)
    problem = soncopay_settings.checkout_problem(db)
    return GatewayState(SONCOPAY, bool(state["enabled"]), problem is None, problem, state["environment"])


def states(db: Session, *, nowpayments_config: Optional[payment_config.PaymentConfig] = None) -> Dict[str, GatewayState]:
    return {NOWPAYMENTS: nowpayments_state(db, nowpayments_config), SONCOPAY: soncopay_state(db)}


def stored_default(db: Session) -> str:
    """The default gateway a Super Admin chose (kept even while that gateway cannot take payments)."""
    return soncopay_settings.current_state(db)["default_provider"]


@dataclass(frozen=True)
class EffectiveDefault:
    stored: str
    gateway: Optional[str]         # the stored default while it is ready, else None
    reason: Optional[str]          # why there is none


def effective_default(db: Session) -> EffectiveDefault:
    stored = stored_default(db)
    state = nowpayments_state(db) if stored == NOWPAYMENTS else soncopay_state(db)
    if state.ready:
        return EffectiveDefault(stored, stored, None)
    return EffectiveDefault(stored, None, f"The default gateway {LABELS[stored]} cannot take new payments: "
                                          f"{state.reason}")


def new_payment_gateway(db: Session) -> Optional[str]:
    """'soncopay', 'nowpayments' or None (no gateway may take a new payment). Never the other gateway."""
    return effective_default(db).gateway
