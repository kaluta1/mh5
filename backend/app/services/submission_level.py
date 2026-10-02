"""Initial competition level of a NEW submission (management rule, 2026-10-02).

    nomination     -> COUNTRY
    participation  -> CITY

The level is decided by the contest's mode, on the server. A submitter never
chooses it: Regional, Continental and Global are reached only through the
progression system. This module is the one place that states the rule; every
path that creates an entry (public submission, the /participate alias, admin
creation) goes through it.

Chosen API behaviour: a request that names a level explicitly is REJECTED
(HTTP 422) unless it names exactly the initial level of the contest's mode.
Silently normalising a wrong level would hide client bugs; a correct explicit
level is harmless and accepted. A request that names no level is the normal
case and simply gets the initial level.

Geography is never invented: a nomination needs the country its Country stage
is grouped by, a participation needs the city its City stage is grouped by. A
missing value is a clear validation error, not a silent entry that can never
be ranked.
"""
from __future__ import annotations

from typing import Any, Iterable, List, Mapping, Optional

from app.models.contests import SeasonLevel

# Keys a client might use to name a competition level in a submission body.
REQUESTED_LEVEL_KEYS = (
    "level",
    "contest_level",
    "contestLevel",
    "season_level",
    "seasonLevel",
    "stage",
    "stage_level",
    "stageLevel",
    "requested_level",
    "requestedLevel",
)

_LEVEL_ALIASES = {
    "city": SeasonLevel.CITY,
    "country": SeasonLevel.COUNTRY,
    "regional": SeasonLevel.REGIONAL,
    "region": SeasonLevel.REGIONAL,
    "continent": SeasonLevel.CONTINENT,
    "continental": SeasonLevel.CONTINENT,
    "global": SeasonLevel.GLOBAL,
}

_LEVEL_LABEL = {
    SeasonLevel.CITY: "City",
    SeasonLevel.COUNTRY: "Country",
    SeasonLevel.REGIONAL: "Regional",
    SeasonLevel.CONTINENT: "Continental",
    SeasonLevel.GLOBAL: "Global",
}


class SubmissionLevelError(ValueError):
    """The submission names a level it may not start at, or lacks the
    geography its initial level is grouped by. Message is user-facing."""


def submission_mode(contest_mode: Any) -> str:
    """'nomination' or 'participation' (the default for anything else)."""
    from app.services.contest_category_integrity import normalize_contest_mode

    return "nomination" if normalize_contest_mode(contest_mode) == "nomination" else "participation"


def initial_submission_level(contest_mode: Any) -> SeasonLevel:
    return SeasonLevel.COUNTRY if submission_mode(contest_mode) == "nomination" else SeasonLevel.CITY


def level_label(level: SeasonLevel) -> str:
    return _LEVEL_LABEL[level]


def requested_levels_from_payload(payload: Any) -> List[str]:
    """Every non-empty level a raw request body names, in a stable order."""
    if not isinstance(payload, Mapping):
        return []
    found: List[str] = []
    for key in REQUESTED_LEVEL_KEYS:
        value = payload.get(key)
        if value is None or str(value).strip() == "":
            continue
        found.append(str(value))
    return found


def enforce_initial_submission_level(
    contest_mode: Any,
    requested_levels: Optional[Iterable[Any]] = None,
) -> SeasonLevel:
    """The level a new submission of this mode starts at. Raises
    SubmissionLevelError when the request names any other level."""
    initial = initial_submission_level(contest_mode)
    mode = submission_mode(contest_mode)
    for raw in requested_levels or ():
        key = str(getattr(raw, "value", raw)).strip().lower()
        requested = _LEVEL_ALIASES.get(key)
        if requested is None:
            raise SubmissionLevelError(
                f"Unknown competition level '{raw}'. New {mode} submissions always start at "
                f"{level_label(initial)} level; do not send a level."
            )
        if requested != initial:
            raise SubmissionLevelError(
                f"A new {mode} always starts at {level_label(initial)} level. It cannot be submitted at "
                f"{level_label(requested)} level: higher levels are reached only through voting."
            )
    return initial


def require_submission_geography(
    contest_mode: Any,
    *,
    city: Optional[str],
    country: Optional[str],
) -> None:
    """Raise SubmissionLevelError when the entry would have no group at its
    initial level. Nothing is defaulted or guessed."""
    has_country = bool(country and str(country).strip())
    has_city = bool(city and str(city).strip())
    if submission_mode(contest_mode) == "nomination":
        if not has_country:
            raise SubmissionLevelError(
                "Nominations start at Country level, and your profile has no country. "
                "Add your country to your profile, then nominate again."
            )
        return
    if not has_city or not has_country:
        missing = "city" if has_country else ("country" if has_city else "city and country")
        raise SubmissionLevelError(
            f"Participations start at City level, and your profile has no {missing}. "
            f"Add your {missing} to your profile, then submit again."
        )
