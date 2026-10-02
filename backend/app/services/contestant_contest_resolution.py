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

  LEGACY COLLISION (Case E, added 2026-10-02 after the progression audit):
    101 historical rows (DJ, Comedy, Handsome in rounds 21-28) carry no
    contest_id and a legacy season_id that is BOTH their Contest.id and,
    numerically, the id of an unrelated old ContestSeason (contest ids 1..8
    collide with season ids 1..8). Case B's guard therefore rejected them and
    no other case applied, so valid entries -- including a voted July Comedy
    nominee -- could never be ranked or promoted. Case E resolves such a row to
    `contest_id` only when existing evidence proves the legacy reading:
      1. contest_id IS NULL and season_id == contest_id (the legacy convention);
      2. the colliding ContestSeason is not a season of the entry's own
         round: it belongs to a different round, or to no round at all. An
         entry's round is fixed at submission and constant through every
         level, and membership of a season of another or of an unknown round
         is refused everywhere (contestant_season_round_conflict), so that
         season cannot be a genuine season reference for this entry;
      3. the contest genuinely runs in the entry's own round (round_contests),
         or the entry already holds a membership in a season of its own round
         that is linked to this contest;
      4. no vote for the entry names a different contest.
    Anything short of that stays rejected, exactly as before. `season_id ==
    contest_id` alone is never enough.

    Case C is limited by the same round evidence (validated read-only against
    production on 2026-10-02): the only seasons with a single active link
    were two old City seasons of rounds 1 and 2, both linked to one unrelated
    contest, so Case C attributed every legacy DJ/Comedy row to that contest
    although their votes name DJ/Comedy. A season that is not of the entry's
    own round is not the entry's season, so its links say nothing about the
    entry and Case C no longer applies to it.

Nothing in this module writes to the database. contestants.season_id is never
modified. contestants.contest_id is never backfilled here -- Cases C and D are
purely query-time reads; the underlying rows remain exactly as they are today.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.orm import Session, aliased
from sqlalchemy.sql.elements import ColumnElement

from app.models.contests import ContestSeason, ContestSeasonLink, Contestant, ContestantSeason
from app.models.round import round_contests
from app.models.voting import ContestantVoting

# Reason codes returned by explain_contest_resolution (audit / dry-run output).
EXPLICIT_CONTEST_ID = "EXPLICIT_CONTEST_ID"
LEGACY_SEASON_ID_AS_CONTEST = "LEGACY_SEASON_ID_AS_CONTEST"
UNIQUE_SEASON_LINK = "UNIQUE_SEASON_LINK"
VALIDATED_VOTE_HISTORY = "VALIDATED_VOTE_HISTORY"
LEGACY_COLLISION_ROUND_VERIFIED = "LEGACY_COLLISION_ROUND_VERIFIED"
LEGACY_COLLISION_SEASON_WITHOUT_ROUND = "LEGACY_COLLISION_SEASON_WITHOUT_ROUND"
LEGACY_COLLISION_CODES = frozenset({LEGACY_COLLISION_ROUND_VERIFIED, LEGACY_COLLISION_SEASON_WITHOUT_ROUND})


def contestant_belongs_to_contest_clause(contest_id: int) -> ColumnElement:
    """
    SQLAlchemy boolean expression, usable directly inside `.filter(...)` on any
    query that already has `Contestant` in scope. True when a contestant row
    is known, without ambiguity, to belong to `contest_id`, via one of the
    authoritative cases documented above (A-E). Set-based -- no per-row Python
    loop, no additional query round-trip. Returns False (excluded, not
    mis-included) for contestants no authoritative signal resolves.
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

    # A season of another round, or of no round, can never be this entry's
    # own season: an entry's round is fixed at submission and membership of
    # any other season is refused (contestant_season_round_conflict). Aliased
    # and correlated to Contestant only, so the clause means the same thing
    # whatever the enclosing query already joins.
    referenced_season = aliased(ContestSeason)
    referenced_season_round = (
        select(referenced_season.round_id)
        .where(referenced_season.id == Contestant.season_id)
        .correlate(Contestant)
        .scalar_subquery()
    )
    season_outside_own_round = and_(
        Contestant.round_id.isnot(None),
        or_(referenced_season_round.is_(None), referenced_season_round != Contestant.round_id),
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
        ~season_outside_own_round,
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

    # Case E: legacy row whose season_id numerically collides with an
    # unrelated ContestSeason id. Resolved only on the evidence listed in the
    # module docstring; `season_id == contest_id` alone is never enough.
    round_link = round_contests.alias()
    contest_runs_in_own_round = exists(
        select(round_link.c.id)
        .where(
            round_link.c.round_id == Contestant.round_id,
            round_link.c.contest_id == contest_id,
        )
        .correlate(Contestant)
    )
    own_membership = aliased(ContestantSeason)
    own_round_season = aliased(ContestSeason)
    own_round_link = aliased(ContestSeasonLink)
    membership_in_own_round_contest_season = exists(
        select(own_membership.id)
        .join(own_round_season, own_round_season.id == own_membership.season_id)
        .join(own_round_link, own_round_link.season_id == own_round_season.id)
        .where(
            own_membership.contestant_id == Contestant.id,
            own_round_season.round_id == Contestant.round_id,
            own_round_link.contest_id == contest_id,
        )
        .correlate(Contestant)
    )
    other_vote = aliased(ContestantVoting)
    vote_names_other_contest = exists(
        select(other_vote.id)
        .where(
            other_vote.contestant_id == Contestant.id,
            other_vote.contest_id.isnot(None),
            other_vote.contest_id != contest_id,
        )
        .correlate(Contestant)
    )
    legacy_collision_match = and_(
        Contestant.contest_id.is_(None),
        Contestant.season_id == contest_id,
        is_genuine_season_ref,
        season_outside_own_round,
        or_(contest_runs_in_own_round, membership_in_own_round_contest_season),
        ~vote_names_other_contest,
    )

    return (
        new_field_match
        | legacy_match
        | unique_link_match
        | validated_vote_match
        | legacy_collision_match
    )


@dataclass(frozen=True)
class ContestResolution:
    """Why one entry does (or does not) belong to one contest. Read-only."""

    belongs: bool
    code: str


def explain_contest_resolution(
    db: Session, contestant: Contestant, contest_id: int
) -> ContestResolution:
    """Per-entry mirror of contestant_belongs_to_contest_clause, with the reason.

    Used by audits and the progression dry-run so every legacy decision is
    visible. It never decides anything the SQL clause would not: the two are
    kept in agreement by tests.
    """
    contest_id = int(contest_id)
    if contestant.contest_id is not None:
        if int(contestant.contest_id) == contest_id:
            return ContestResolution(True, EXPLICIT_CONTEST_ID)
        return ContestResolution(False, "EXPLICIT_CONTEST_ID_NAMES_ANOTHER_CONTEST")
    if contestant.season_id is None:
        return ContestResolution(False, "NO_CONTEST_OR_SEASON_REFERENCE")

    season_id = int(contestant.season_id)
    season = db.query(ContestSeason).filter(ContestSeason.id == season_id).first()
    if season is None:
        if season_id == contest_id:
            return ContestResolution(True, LEGACY_SEASON_ID_AS_CONTEST)
        return ContestResolution(False, "LEGACY_SEASON_ID_NAMES_ANOTHER_CONTEST")

    active_links = (
        db.query(ContestSeasonLink.contest_id)
        .filter(ContestSeasonLink.season_id == season_id, ContestSeasonLink.is_active.is_(True))
        .all()
    )
    linked_here = any(int(row[0]) == contest_id for row in active_links)
    outside_own_round = contestant.round_id is not None and (
        season.round_id is None or int(season.round_id) != int(contestant.round_id)
    )
    if len(active_links) == 1 and linked_here and not outside_own_round:
        return ContestResolution(True, UNIQUE_SEASON_LINK)

    voted_contests = {
        int(row[0])
        for row in db.query(ContestantVoting.contest_id)
        .filter(ContestantVoting.contestant_id == contestant.id)
        .distinct()
        .all()
        if row[0] is not None
    }
    if voted_contests == {contest_id} and linked_here:
        return ContestResolution(True, VALIDATED_VOTE_HISTORY)

    if season_id != contest_id:
        return ContestResolution(False, "SEASON_REFERENCE_NOT_RESOLVED_TO_THIS_CONTEST")
    if contestant.round_id is None:
        return ContestResolution(False, "AMBIGUOUS_COLLISION_ENTRY_ROUND_UNKNOWN")
    if season.round_id is not None and int(season.round_id) == int(contestant.round_id):
        return ContestResolution(False, "AMBIGUOUS_COLLISION_SAME_ROUND")
    runs_in_round = (
        db.query(round_contests.c.id)
        .filter(
            round_contests.c.round_id == contestant.round_id,
            round_contests.c.contest_id == contest_id,
        )
        .first()
        is not None
    )
    has_membership = (
        db.query(ContestantSeason.id)
        .join(ContestSeason, ContestSeason.id == ContestantSeason.season_id)
        .join(ContestSeasonLink, ContestSeasonLink.season_id == ContestSeason.id)
        .filter(
            ContestantSeason.contestant_id == contestant.id,
            ContestSeason.round_id == contestant.round_id,
            ContestSeasonLink.contest_id == contest_id,
        )
        .first()
        is not None
    )
    if not (runs_in_round or has_membership):
        return ContestResolution(False, "AMBIGUOUS_COLLISION_CONTEST_NOT_IN_ENTRY_ROUND")
    if voted_contests - {contest_id}:
        return ContestResolution(False, "AMBIGUOUS_COLLISION_VOTES_NAME_ANOTHER_CONTEST")
    if season.round_id is None:
        return ContestResolution(True, LEGACY_COLLISION_SEASON_WITHOUT_ROUND)
    return ContestResolution(True, LEGACY_COLLISION_ROUND_VERIFIED)
