"""Operational security defaults for age-gate circumvention and DOB-change controls.

These are NOT legal or jurisdiction rules. The Child/Teen Safety requirement
(s.5, s.6) asks for "retry controls", "rate limiting", "age-change tracking" and
"risk assessment" but gives no numbers, so these values are MyHigh5's own
operational choices. They are deliberately kept out of AgePolicy (which holds
only the jurisdiction fields defined in s.3) and are never sent to clients.

Override per deployment with environment variables (AGE_SAFETY_<FIELD_NAME>,
e.g. AGE_SAFETY_RETRY_EMAIL_MAX=5). Invalid values are rejected at load time.
Tests use override_age_safety_config().
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AgeSafetyOperationalConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    # Retry controls (s.6 "retry controls", "rate limiting")
    retry_email_window_hours: int = Field(24, ge=1, le=24 * 30)
    retry_email_max: int = Field(5, ge=1, le=1000)
    retry_ip_window_minutes: int = Field(60, ge=1, le=24 * 60)
    retry_ip_max: int = Field(20, ge=1, le=10000)

    # Correlation windows for "rejected, then claims an older age" (s.6)
    email_correlation_days: int = Field(30, ge=1, le=365)
    ip_immediate_window_minutes: int = Field(60, ge=1, le=24 * 60)
    ip_correlation_hours: int = Field(24, ge=1, le=24 * 30)
    ip_repeated_probe_min: int = Field(2, ge=1, le=100)
    tier_hopping_distinct_tiers: int = Field(3, ge=2, le=4)  # only 4 real tiers exist

    # DOB change tracking (s.5 "repeated DOB manipulation")
    dob_change_window_days: int = Field(365, ge=1, le=3650)
    dob_max_self_changes_in_window: int = Field(1, ge=0, le=20)

    # Guardian consent workflow lifetimes and pending-data retention (operational)
    pending_registration_ttl_hours: int = Field(168, ge=1, le=24 * 60)
    guardian_token_ttl_hours: int = Field(168, ge=1, le=24 * 60)
    completion_token_ttl_hours: int = Field(72, ge=1, le=24 * 30)
    pending_data_retention_days: int = Field(30, ge=1, le=365)

    @model_validator(mode="after")
    def _consistent(self):
        if self.ip_immediate_window_minutes > self.ip_correlation_hours * 60:
            raise ValueError("ip_immediate_window_minutes cannot exceed ip_correlation_hours")
        return self


def _from_env() -> AgeSafetyOperationalConfig:
    values = {}
    for name in AgeSafetyOperationalConfig.model_fields:
        raw = os.getenv(f"AGE_SAFETY_{name.upper()}")
        if raw is not None and raw.strip() != "":
            values[name] = int(raw)
    return AgeSafetyOperationalConfig(**values)


_active: Optional[AgeSafetyOperationalConfig] = None


def get_age_safety_config() -> AgeSafetyOperationalConfig:
    global _active
    if _active is None:
        _active = _from_env()
    return _active


@contextmanager
def override_age_safety_config(**changes) -> Iterator[AgeSafetyOperationalConfig]:
    """Temporarily replace the active config (tests). Values are validated."""
    global _active
    previous = get_age_safety_config()
    _active = AgeSafetyOperationalConfig(**{**previous.model_dump(), **changes})
    try:
        yield _active
    finally:
        _active = previous
