"""Nomination calendar constants — official launch and cohort rules."""
from __future__ import annotations

import calendar
from datetime import date

from sqlalchemy import func

# First month users could nominate (Round March 2026). Earlier rounds are ignored for Vote UI.
OFFICIAL_NOMINATION_START = date(2026, 3, 1)


def round_month_start_from_name(round_name: str) -> date | None:
    name = (round_name or "").strip()
    if name.lower().startswith("round "):
        name = name[6:].strip()
    try:
        from datetime import datetime

        parsed = datetime.strptime(name[:20].strip(), "%B %Y")
        return date(parsed.year, parsed.month, 1)
    except ValueError:
        return None


def cohort_submission_bounds(cohort_round) -> tuple[date | None, date | None]:
    """
    Inclusive calendar bounds for nomination cohort month M (submission month only).

    Does not extend into the next month via voting_start_date — April nominees must
    never match the March cohort even when Contestant.round_id was stored incorrectly.
    """
    if cohort_round is None:
        return None, None

    start = getattr(cohort_round, "submission_start_date", None)
    end = getattr(cohort_round, "submission_end_date", None)

    if start is None:
        start = round_month_start_from_name(getattr(cohort_round, "name", "") or "")

    if start is not None and end is None:
        last_day = calendar.monthrange(start.year, start.month)[1]
        end = date(start.year, start.month, last_day)

    if start is not None and end is not None and end < start:
        return None, None

    return start, end


def is_official_nomination_cohort_round(round_obj) -> bool:
    """False for January/February 2026 placeholder rounds before launch."""
    if round_obj is None:
        return False
    sub = getattr(round_obj, "submission_start_date", None)
    if sub is not None:
        month_start = date(sub.year, sub.month, 1)
        return month_start >= OFFICIAL_NOMINATION_START
    name_start = round_month_start_from_name(getattr(round_obj, "name", "") or "")
    if name_start is not None:
        return name_start >= OFFICIAL_NOMINATION_START
    return True


def nomination_vote_list_blocked(
    round_obj,
    contest_mode: str | None,
    wanted_level: str | None,
) -> bool:
    """
    True when a nomination Vote list/detail request must return an empty roster.

    Blocks pre-March placeholder rounds and pooled stages before their vote month opens.
    """
    if (contest_mode or "").strip().lower() != "nomination":
        return False
    level = (wanted_level or "").strip().lower()
    if level not in {"country", "regional", "continental", "global", "continent", "region"}:
        return False
    if not is_official_nomination_cohort_round(round_obj):
        return True

    if level in {"regional", "region", "continental", "continent", "global"}:
        from app.models.contests import SeasonLevel
        from app.services.season_migration import SeasonMigrationService

        level_map = {
            "regional": SeasonLevel.REGIONAL,
            "region": SeasonLevel.REGIONAL,
            "continental": SeasonLevel.CONTINENT,
            "continent": SeasonLevel.CONTINENT,
            "global": SeasonLevel.GLOBAL,
        }
        target = level_map.get(level)
        if target is not None:
            vote_open = SeasonMigrationService._nomination_vote_open_date_for_level(
                round_obj, target
            )
            if vote_open and date.today() < vote_open:
                return True
    return False


def nomination_cohort_created_at_filters(cohort_round):
    """
    SQLAlchemy clauses: nominee belongs to this cohort submission month.

    Uses ``registration_date`` (shown in UI) with ``created_at`` fallback.
    Strict submission month bounds — no grace extension into the next month.
    """
    from app.models.contests import Contestant

    start, end = cohort_submission_bounds(cohort_round)
    if not start or not end:
        return []

    submitted_on = func.coalesce(Contestant.registration_date, Contestant.created_at)
    return [
        submitted_on.isnot(None),
        func.date(submitted_on) >= start,
        func.date(submitted_on) <= end,
    ]
