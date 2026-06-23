"""Nomination calendar constants — official launch and cohort rules."""
from __future__ import annotations

from datetime import date

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

    Blocks pre-March placeholder rounds (Jan/Feb 2026) even if legacy seasons exist.
    """
    if (contest_mode or "").strip().lower() != "nomination":
        return False
    level = (wanted_level or "").strip().lower()
    if level not in {"country", "regional", "continental", "global", "continent", "region"}:
        return False
    return not is_official_nomination_cohort_round(round_obj)
