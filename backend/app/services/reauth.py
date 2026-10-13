"""Re-authentication: "prove it is you, now, with your password".

A privileged action (Finance & Payments changes, administrator management,
a manual payment, a payout wallet change, a password change) asks for the
account's current password in the same request. Whoever holds a signed-in
session could otherwise use those endpoints to GUESS the password, with
nothing to stop them. So the check is made in ONE place, here, and wrong
passwords are counted durably per account (auth_throttle.REAUTH_FAIL), across
every endpoint that asks: after a few wrong ones the account's privileged
actions are refused, with the right password too, until the window ends.

This cannot be used to lock anybody else out: only a request that already
carries the account's own valid session reaches the check. It does not touch
signing in.

Nothing here ever records a password. A wrong one leaves an audit row saying
that it happened, where from, and nothing else.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session, object_session

from app.core.security import verify_password
from app.models.accounting import AuditTrail
from app.services import auth_throttle

logger = logging.getLogger(__name__)

AUDIT_REAUTH_FAILED = "REAUTH_FAILED"
REQUIRED, LOCKED = "REAUTH_REQUIRED", "REAUTH_LOCKED"
REQUIRED_MESSAGE = "Enter your current password to confirm this action."
LOCKED_MESSAGE = ("Too many incorrect passwords. Actions that need your password are paused for a few minutes; "
                  "nothing was changed.")


class ReauthError(Exception):
    """The password was not accepted. Nothing was changed."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def verify(db: Optional[Session], actor, password: Optional[str], *, ip: Optional[str] = None,
           audit: bool = True) -> None:
    """Accept the actor's current password or raise ReauthError.

    A wrong password rolls back whatever the request had started (nothing may
    be half done under a refused confirmation), is counted, and is audited.
    A missing password is refused without being counted: nothing was guessed.
    """
    account_id = getattr(actor, "id", None)
    if db is None and actor is not None:
        try:
            db = object_session(actor)
        except Exception:  # noqa: BLE001 - not a mapped object
            db = None
    limited = db is not None and account_id is not None
    if limited and auth_throttle.blocked(db, auth_throttle.REAUTH_FAIL, account_id):
        raise ReauthError(LOCKED, LOCKED_MESSAGE)
    if not password:
        raise ReauthError(REQUIRED, REQUIRED_MESSAGE)
    if verify_password(password, getattr(actor, "hashed_password", "") or ""):
        return
    if limited:
        try:
            db.rollback()
            auth_throttle.hit(db, auth_throttle.REAUTH_FAIL, account_id)
            if audit:
                db.add(AuditTrail(table_name="users", record_id=int(account_id), action=AUDIT_REAUTH_FAILED,
                                  old_values=None, new_values={"reason": "incorrect password"},
                                  user_id=int(account_id), ip_address=(ip or None), timestamp=datetime.utcnow()))
                db.commit()
        except Exception as exc:  # noqa: BLE001 - the refusal stands whatever happens to its record
            db.rollback()
            logger.error("Could not record a failed re-authentication (%s)", type(exc).__name__)
    raise ReauthError(REQUIRED, REQUIRED_MESSAGE)
