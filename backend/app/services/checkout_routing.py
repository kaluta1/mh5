"""Which gateway takes a NEW member payment, or none.

  1. SoncoPay, when a Super Admin made it the default and it can take a payment
     now (soncopay_settings.default_checkout_provider);
  2. otherwise NOWPayments, but only while its checkout is allowed
     (provider_enabled AND checkout_enabled);
  3. otherwise NONE: the member is told that payments are temporarily
     unavailable. There is no silent fall back to a gateway that is switched off,
     and no deposit is created.

Only NEW payments are decided here. A payment keeps the gateway it was created
with: callbacks, status checks and reconciliation of existing payments never
depend on these switches.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.services import payment_config, soncopay_settings

UNAVAILABLE_MESSAGE = "Payments are temporarily unavailable. Please try again later."


def new_payment_gateway(db: Session) -> Optional[str]:
    """'soncopay', 'nowpayments' or None (no gateway can take a new payment)."""
    if soncopay_settings.default_checkout_provider(db) == soncopay_settings.PROVIDER:
        return soncopay_settings.PROVIDER
    if payment_config.nowpayments_checkout_available(db):
        return soncopay_settings.NOWPAYMENTS
    return None
