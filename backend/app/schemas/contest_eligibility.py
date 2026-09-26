"""Schemas for Phase 5 contest/category age rules and entry review (Child/Teen
Safety s.9, s.12, s.17, s.19). The same definition re-validates stored rows, so
invalid stored data fails closed."""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.child_safety import (
    ENFORCEMENT_ALL_JURISDICTIONS,
    AgeTier,
    ContentRating,
    SafetyConcern,
)
from app.core.jurisdictions import ISO_COUNTRY_NAMES


class ContestAgeRuleDefinition(BaseModel):
    """One contest or category age rule. Used for ContestAgeEligibility (s.9)
    and CategoryAgePolicy (s.19; adult_only = ADULT_ONLY_CATEGORY, s.17)."""

    model_config = ConfigDict(extra="forbid")

    jurisdiction: str = Field(default=ENFORCEMENT_ALL_JURISDICTIONS, max_length=10)
    minimum_age: Optional[int] = Field(default=None, ge=0, le=120)
    maximum_age: Optional[int] = Field(default=None, ge=0, le=120)
    eligible_age_tiers: Optional[List[AgeTier]] = None
    minor_participation_allowed: bool = True
    adult_only: bool = False
    parental_consent_required: bool = False
    publicity_consent_required: bool = False
    content_age_rating: Optional[ContentRating] = None
    # Stored for Phase 10; not evaluated in Phase 5.
    prize_restrictions: Optional[dict] = None
    financial_restrictions: Optional[dict] = None
    notes: Optional[str] = Field(default=None, max_length=2000)

    @field_validator("jurisdiction")
    @classmethod
    def _jurisdiction(cls, v: str) -> str:
        code = (v or "").strip().upper() or ENFORCEMENT_ALL_JURISDICTIONS
        if code != ENFORCEMENT_ALL_JURISDICTIONS and code not in ISO_COUNTRY_NAMES:
            raise ValueError("jurisdiction must be '*' or a supported ISO 3166-1 alpha-2 code")
        return code

    @field_validator("eligible_age_tiers")
    @classmethod
    def _tiers(cls, v):
        if v is None:
            return v
        if not v:
            raise ValueError("eligible_age_tiers cannot be empty (use null for every tier)")
        if AgeTier.UNKNOWN in v or AgeTier.UNDER_13 in v:
            # UNKNOWN never gains contest privileges; UNDER_13 membership is prohibited (s.2).
            raise ValueError("eligible_age_tiers cannot include UNKNOWN or UNDER_13")
        if len(set(v)) != len(v):
            raise ValueError("eligible_age_tiers contains duplicates")
        return v

    @model_validator(mode="after")
    def _consistent(self):
        if self.minimum_age is not None and self.maximum_age is not None and self.minimum_age > self.maximum_age:
            raise ValueError("minimum_age cannot be greater than maximum_age")
        if self.content_age_rating == ContentRating.PROHIBITED:
            raise ValueError("PROHIBITED content cannot be a contest rating")
        if self.content_age_rating == ContentRating.ADULT_18_PLUS and not self.adult_only:
            raise ValueError("an ADULT_18_PLUS rating requires adult_only")
        if self.adult_only:
            if self.minor_participation_allowed:
                raise ValueError("adult_only requires minor_participation_allowed=false")
            if self.eligible_age_tiers and set(self.eligible_age_tiers) != {AgeTier.ADULT_18_PLUS}:
                raise ValueError("adult_only allows only ADULT_18_PLUS")
            if self.maximum_age is not None and self.maximum_age < 18:
                raise ValueError("adult_only is inconsistent with a maximum_age below 18")
        return self


class ContestAgeRuleCreate(ContestAgeRuleDefinition):
    reason: str = Field(min_length=5, max_length=500)


class ContestAgeRuleStatusChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=5, max_length=500)


class ContestAgeRuleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    jurisdiction: str
    rule_version: int
    status: str
    minimum_age: Optional[int] = None
    maximum_age: Optional[int] = None
    eligible_age_tiers: Optional[list] = None
    minor_participation_allowed: bool
    adult_only: bool
    parental_consent_required: bool
    publicity_consent_required: bool
    content_age_rating: Optional[str] = None
    prize_restrictions: Optional[dict] = None
    financial_restrictions: Optional[dict] = None
    notes: Optional[str] = None
    activated_at: Optional[datetime] = None
    withdrawn_at: Optional[datetime] = None
    created_at: datetime


class EntryReviewAction(BaseModel):
    """Administrator action on one Phase 5 entry. None of these can manufacture
    guardian consent or guardian authority; those stay in the Phase 4 service."""

    model_config = ConfigDict(extra="forbid")

    action: str = Field(pattern=r"^(CONFIRM_RIGHTS|DISPUTE_RIGHTS|CLEAR_SAFETY_REVIEW|FLAG_CONCERN|BLOCK|"
                                r"ESCALATE_CHILD_SAFETY|LINK_NOMINEE_ACCOUNT|REEVALUATE)$")
    note: str = Field(min_length=5, max_length=1000)
    concern: Optional[SafetyConcern] = None
    nominee_user_id: Optional[int] = Field(default=None, ge=1)

    @model_validator(mode="after")
    def _args(self):
        if self.action == "FLAG_CONCERN" and self.concern is None:
            raise ValueError("FLAG_CONCERN requires concern")
        if self.action == "LINK_NOMINEE_ACCOUNT" and self.nominee_user_id is None:
            raise ValueError("LINK_NOMINEE_ACCOUNT requires nominee_user_id")
        return self
