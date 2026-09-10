"""
Shared, set-based contestant-to-contest resolution clause.

Background: `Contestant.season_id` is historically overloaded -- for 955 legacy
rows it actually holds a `Contest.id` (see KALUTASOCIETY_ORPHAN_SEASON_INVESTIGATION.md),
while for 118 genuine rows it holds a real `contest_seasons.id`. The dedicated
`Contestant.contest_id` field (added 2026-09-10) removes that ambiguity going
forward; this module gives every query-level (not per-row) call site the same
validated resolution rule already used by
`app.api.api_v1.endpoints.contestant._contestant_belongs_to_contest` /
`_resolve_contest_for_contestant_vote`, instead of each site re-deriving it
(or, as found in `season_migration.py`, getting it wrong).

A follow-up investigation (KALUTASOCIETY_TOP_HIGH5_MULTICONTEST_INVESTIGATION,
2026-09-11, read-only, independently verified) profiled all 118 genuine
season-linked contestants and classified the available signals:

  AUTHORITATIVE (adopted below, in precedence order):
    A. contestant.contest_id == contest_id -- authoritative when present.
    B. contest_id IS NULL and season_id == contest_id, guarded so a genuine
       ContestSeason reference is never misread as a contest id.
    C. contest_id IS NULL, season_id is a genuine ContestSeason reference, and
       that season has EXACTLY ONE active ContestSeasonLink -- unambiguous by
       construction (37/118 contestants). Not a guess: if there is only one
       linked contest, there is no other contest it could be.
    D. contest_id IS NULL, season_id is a genuine ContestSeason reference, and
       the contestant's entire ContestantVoting history points at exactly one
       contest_id, AND that contest has an active ContestSeasonLink for the
       contestant's season (validated, not just "happened to vote once") --
       16/118 contestants. contestant_voting remains the canonical voting
       source; this only reads it, never mutates it.

  REJECTED as non-authoritative (deliberately NOT used, tested and found to
  provide zero discrimination or no schema support):
    - round_id / contest level / contest mode / round_contests intersection --
      tested directly; in every case checked, the round-intersected contest
      count was identical to the raw season-link count. Zero narrowing power,
      not a partial signal.
    - category -- `contestants` has no category field at all.

  STILL UNRESOLVED, LEFT UNRESOLVED (65/118): when none of A-D match, this
  clause returns False for every contest_id. These contestants are NOT
  attached to any contest, NOT duplicated across every contest linked to
  their season, and NOT guessed at. This is intentional, documented behavior,
  not a bug -- resolving them requires either a new authoritative data source
  or an explicit product decision (see the multi-contest investigation doc),
  neither of which exists today. Do not extend this clause to cover them
  without that decision.

Nothing in this module writes to the database. contestants.season_id is never
modified. contestants.contest_id is never backfilled here -- Cases C and D are
purely query-time reads; the underlying rows remain exactly as they are today.
"""
from __future__ import annotations

from sqlalchemy import and_, exists, func, select
from sqlalchemy.sql.elements import ColumnElement

from app.models.contests import ContestSeason, ContestSeasonLink, Contestant
from app.models.voting import ContestantVoting


def contestant_belongs_to_contest_clause(contest_id: int) -> ColumnElement:
    """
    SQLAlchemy boolean expression, usable directly inside `.filter(...)` on any
    query that already has `Contestant` in scope. True when a contestant row
    is known, without ambiguity, to belong to `contest_id`, via one of the four
    authoritative cases documented above (A-D). Set-based -- no per-row Python
    loop, no additional query round-trip. Returns False (excluded, not
    mis-included) for the 65 contestants no authoritative signal resolves.
    """
    # Case A: the dedicated field, authoritative when present.
    new_field_match = Contestant.contest_id == contest_id

    # Case B: legacy rows -- contest_id NULL, season_id stands in for Contest.id.
    # Guarded: never true if season_id is actually a genuine ContestSeason id,
    # even where the two id spaces numerically overlap.
    is_genuine_season_ref = exists(
        select(ContestSeason.id).where(ContestSeason.id == Contestant.season_id)
    )
    legacy_match = and_(
        Contestant.contest_id.is_(None),
        Contestant.season_id == contest_id,
        ~is_genuine_season_ref,
    )

    # Case C: genuine season reference whose season links to exactly one
    # active contest -- unambiguous by construction, not a guess.
    active_links_for_season = (
        select(func.count(ContestSeasonLink.id))
        .where(
            ContestSeasonLink.season_id == Contestant.season_id,
            ContestSeasonLink.is_active.is_(True),
        )
        .scalar_subquery()
    )
    unique_link_match = and_(
        Contestant.contest_id.is_(None),
        is_genuine_season_ref,
        active_links_for_season == 1,
        exists(
            select(ContestSeasonLink.id).where(
                ContestSeasonLink.season_id == Contestant.season_id,
                ContestSeasonLink.contest_id == contest_id,
                ContestSeasonLink.is_active.is_(True),
            )
        ),
    )

    # Case D: genuine season reference with no unique link, but the
    # contestant's full contestant_voting history names exactly one
    # contest_id, and that contest is genuinely linked (active) to the
    # contestant's season -- validated, not merely "voted once somewhere".
    distinct_voted_contests = (
        select(func.count(func.distinct(ContestantVoting.contest_id)))
        .where(ContestantVoting.contestant_id == Contestant.id)
        .scalar_subquery()
    )
    validated_vote_match = and_(
        Contestant.contest_id.is_(None),
        is_genuine_season_ref,
        distinct_voted_contests == 1,
        exists(
            select(ContestantVoting.id).where(
                ContestantVoting.contestant_id == Contestant.id,
                ContestantVoting.contest_id == contest_id,
            )
        ),
        exists(
            select(ContestSeasonLink.id).where(
                ContestSeasonLink.season_id == Contestant.season_id,
                ContestSeasonLink.contest_id == contest_id,
                ContestSeasonLink.is_active.is_(True),
            )
        ),
    )

    return new_field_match | legacy_match | unique_link_match | validated_vote_match
