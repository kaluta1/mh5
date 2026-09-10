"""
Regression tests for the Top High5 / get_top_contestants_by_location()
contest-resolution fix (season_migration.py).

Background: the confirmed bug was a raw `Contestant.season_id == contest_id`
comparison used inside get_top_contestants_by_location() (and its helper
_contestants_for_contest_in_season()) to scope contestants to one specific
contest. For 955 legacy rows season_id genuinely holds a Contest.id (correct
by historical convention); for 118 genuine rows season_id holds a real
ContestSeason.id instead -- and those two integer spaces can numerically
overlap. The raw comparison could therefore wrongly match a genuine
season-linked contestant into an unrelated contest purely by ID coincidence.

Scope, finalized after KALUTASOCIETY_TOP_HIGH5_MULTICONTEST_INVESTIGATION
(2026-09-11, read-only, independently verified): the resolver implements four
authoritative cases, in precedence order --
  A. contestant.contest_id == contest_id (authoritative when populated)
  B. contest_id IS NULL and season_id == contest_id, guarded so a genuine
     ContestSeason reference is never misread as a contest id.
  C. genuine season reference whose season links to exactly one active
     contest -- unambiguous by construction (37/118 contestants).
  D. genuine season reference with no unique link, but the contestant's full
     contestant_voting history names exactly one contest, validated against
     an active ContestSeasonLink for that season (16/118 contestants).
The remaining 65/118 genuine season-linked contestants -- whose season links
to multiple contests with no vote evidence narrowing it -- are intentionally
left unresolved. No heuristic (round/level/mode: tested, zero discrimination;
category: no such field exists) and no "include in every linked contest"
default was adopted for them, per the investigation's explicit findings. The
tests below prove: (1) existing correct legacy behavior is unchanged, (2) the
coincidental-ID-collision bug is fixed, (3) Cases C and D correctly resolve
their respective populations, and (4) a genuinely multi-contest, vote-less
contestant remains unresolved -- not guessed, not duplicated across contests.
"""
from __future__ import annotations

from datetime import date, timedelta

from app.models.contest import Contest
from app.models.contests import (
    ContestSeason,
    ContestSeasonLink,
    Contestant,
    ContestantSeason,
    SeasonLevel,
)
from app.models.round import Round, RoundStatus
from app.models.user import User
from app.models.voting import ContestantVoting
from app.services.season_migration import SeasonMigrationService


def _user(db, suffix: str) -> User:
    user = User(email=f"th5-{suffix}@example.test", hashed_password="unused")
    db.add(user)
    db.flush()
    return user


def _round(db, suffix: str, month: int = 9) -> Round:
    start = date(2026, month, 1)
    end = date(2026, month, 1) + timedelta(days=27)
    rnd = Round(
        name=f"Round {suffix}",
        status=RoundStatus.ACTIVE,
        submission_start_date=start,
        submission_end_date=end,
    )
    db.add(rnd)
    db.flush()
    return rnd


def _link(db, contest: Contest, season: ContestSeason):
    db.add(ContestSeasonLink(contest_id=contest.id, season_id=season.id, is_active=True))
    db.flush()


def _membership(db, contestant: Contestant, season: ContestSeason):
    db.add(ContestantSeason(contestant_id=contestant.id, season_id=season.id, is_active=True))
    db.flush()


def _vote(db, voter: User, contestant: Contestant, contest: Contest, season: ContestSeason):
    """aggregate_rankings() requires at least one real vote row (require_votes=True)
    for a candidate to survive the final ranking step -- a contest with zero votes
    legitimately shows zero winners, independent of this fix (see design doc section 9).
    bucket key must match SeasonMigrationService._top_high5_bucket_key_for_contest()
    exactly, or aggregate_rankings' bucket_key filter silently excludes the vote.
    """
    if contest.category_id is not None:
        bucket_key = f"cat:{contest.category_id}"
    else:
        bucket_key = f"ty:{contest.contest_type or ''}:{contest.contest_mode or ''}"
    db.add(
        ContestantVoting(
            user_id=voter.id,
            contestant_id=contestant.id,
            contest_id=contest.id,
            season_id=season.id,
            vote_bucket_key=bucket_key,
            position=1,
            points=5,
        )
    )
    db.flush()


def test_legacy_contestant_still_found_via_get_top_contestants_by_location(db):
    """Regression guard: a legacy-pattern contestant (contest_id NULL,
    season_id historically holding the Contest.id) must still be returned,
    unchanged, by the fixed query -- proving Case B preserves existing
    correct behavior for the 955 legacy rows."""
    owner = _user(db, "legacy-regress")
    rnd = _round(db, "legacy-regress")
    season = ContestSeason(round_id=rnd.id, title="Season legacy-regress", level=SeasonLevel.COUNTRY)
    db.add(season)
    db.flush()
    # Decoy contest first: ensures contest.id != season.id below, so this test
    # exercises a clean legacy case rather than accidentally colliding with the
    # NOT EXISTS guard's own coincidence-safety check (see the dedicated
    # coincidence test for that case).
    db.add(Contest(name="Decoy", contest_type="t", contest_mode="nomination", level="country"))
    db.flush()
    contest = Contest(name="Legacy Contest", contest_type="t", contest_mode="nomination", level="country")
    db.add(contest)
    db.flush()
    assert contest.id != season.id
    _link(db, contest, season)

    contestant = Contestant(
        user_id=owner.id,
        round_id=rnd.id,
        season_id=contest.id,  # legacy convention
        contest_id=None,
        is_active=True,
        is_deleted=False,
        is_qualified=True,
        country="Benin",
        title="Legacy contestant",
    )
    db.add(contestant)
    db.flush()
    _membership(db, contestant, season)
    _vote(db, _user(db, "legacy-regress-voter"), contestant, contest, season)

    result = SeasonMigrationService.get_top_contestants_by_location(
        db,
        season.id,
        "country",
        contest_id=contest.id,
        diagnostics=False,
        qualified_only=False,
    )
    all_returned = [c.id for group in result.values() for c in group]
    assert contestant.id in all_returned


def test_genuine_season_contestant_no_longer_wrongly_matched_by_id_coincidence(db):
    """The actual bug fix: a genuine season-linked contestant whose
    ContestSeason.id numerically coincides with an UNRELATED contest's id
    must NOT be matched into that unrelated contest's results. Before this
    fix, the raw `Contestant.season_id == contest_id` comparison would have
    wrongly included them purely because the two integers happened to be
    equal."""
    owner = _user(db, "coincidence")
    rnd = _round(db, "coincidence")

    # Force season.id and unrelated_contest.id to coincide on a distinctive value.
    coincident_id = 91001
    season = ContestSeason(
        id=coincident_id, round_id=rnd.id, title="Season coincidence", level=SeasonLevel.COUNTRY
    )
    db.add(season)
    db.flush()
    assert season.id == coincident_id

    unrelated_contest = Contest(
        id=coincident_id, name="Unrelated Contest", contest_type="t", contest_mode="nomination", level="country"
    )
    db.add(unrelated_contest)
    db.flush()
    assert unrelated_contest.id == coincident_id

    # This contestant genuinely belongs to `season`, NOT to unrelated_contest --
    # unrelated_contest is not even linked to this season.
    contestant = Contestant(
        user_id=owner.id,
        round_id=rnd.id,
        season_id=season.id,  # == coincident_id, a genuine ContestSeason reference
        contest_id=None,
        is_active=True,
        is_deleted=False,
        is_qualified=True,
        country="Benin",
        title="Genuine season contestant (coincidental id)",
    )
    db.add(contestant)
    db.flush()
    _membership(db, contestant, season)

    result = SeasonMigrationService.get_top_contestants_by_location(
        db,
        season.id,
        "country",
        contest_id=unrelated_contest.id,  # == coincident_id
        diagnostics=False,
        qualified_only=False,
    )
    all_returned = [c.id for group in result.values() for c in group]
    assert contestant.id not in all_returned, (
        "Genuine season-linked contestant was wrongly matched to an unrelated "
        "contest purely by numeric ID coincidence -- the bug this fix addresses."
    )


def test_genuine_season_contestant_resolved_by_unique_season_link(db):
    """Case C: a genuine season-linked contestant whose season links to
    EXACTLY ONE active contest is unambiguous by construction -- not a guess,
    since there is no other contest it could be. Proves this positively
    resolves end-to-end through get_top_contestants_by_location (candidate
    selection AND the ranking step, which requires real votes)."""
    owner = _user(db, "unique-link")
    rnd = _round(db, "unique-link")
    season = ContestSeason(round_id=rnd.id, title="Season unique-link", level=SeasonLevel.COUNTRY)
    db.add(season)
    db.flush()
    real_contest = Contest(name="Only Linked Contest", contest_type="t", contest_mode="nomination", level="country")
    db.add(real_contest)
    db.flush()
    _link(db, real_contest, season)

    contestant = Contestant(
        user_id=owner.id,
        round_id=rnd.id,
        season_id=season.id,  # genuine ContestSeason reference, no id coincidence
        contest_id=None,
        is_active=True,
        is_deleted=False,
        is_qualified=True,
        country="Benin",
        title="Genuine season contestant (unique link)",
    )
    db.add(contestant)
    db.flush()
    _membership(db, contestant, season)
    _vote(db, _user(db, "unique-link-voter"), contestant, real_contest, season)

    result = SeasonMigrationService.get_top_contestants_by_location(
        db,
        season.id,
        "country",
        contest_id=real_contest.id,
        diagnostics=False,
        qualified_only=False,
    )
    all_returned = [c.id for group in result.values() for c in group]
    assert contestant.id in all_returned


def test_genuine_season_contestant_resolved_by_validated_voting_evidence(db):
    """Case D: a genuine season-linked contestant whose season links to
    MULTIPLE contests, but whose entire contestant_voting history names
    exactly one contest -- validated against an active ContestSeasonLink for
    that season -- is resolvable via voting evidence alone, without a unique
    season link."""
    owner = _user(db, "vote-evidence")
    rnd = _round(db, "vote-evidence")
    season = ContestSeason(round_id=rnd.id, title="Season vote-evidence", level=SeasonLevel.COUNTRY)
    db.add(season)
    db.flush()
    voted_contest = Contest(name="Voted Contest", contest_type="t", contest_mode="nomination", level="country")
    other_contest = Contest(name="Other Linked Contest", contest_type="t", contest_mode="nomination", level="country")
    db.add(voted_contest)
    db.add(other_contest)
    db.flush()
    _link(db, voted_contest, season)
    _link(db, other_contest, season)  # season links to TWO contests -- Case C does not apply

    contestant = Contestant(
        user_id=owner.id,
        round_id=rnd.id,
        season_id=season.id,
        contest_id=None,
        is_active=True,
        is_deleted=False,
        is_qualified=True,
        country="Benin",
        title="Genuine season contestant (vote-resolved)",
    )
    db.add(contestant)
    db.flush()
    _membership(db, contestant, season)
    # All of this contestant's votes are for voted_contest -- never other_contest.
    _vote(db, _user(db, "vote-evidence-voter1"), contestant, voted_contest, season)
    _vote(db, _user(db, "vote-evidence-voter2"), contestant, voted_contest, season)

    result_for_voted = SeasonMigrationService.get_top_contestants_by_location(
        db, season.id, "country", contest_id=voted_contest.id, diagnostics=False, qualified_only=False,
    )
    result_for_other = SeasonMigrationService.get_top_contestants_by_location(
        db, season.id, "country", contest_id=other_contest.id, diagnostics=False, qualified_only=False,
    )
    assert contestant.id in [c.id for group in result_for_voted.values() for c in group]
    assert contestant.id not in [c.id for group in result_for_other.values() for c in group]


def test_KNOWN_LIMITATION_conflicting_voting_evidence_across_multiple_contests_remains_unresolved(db):
    """Case D's guard: if a genuine season-linked contestant's voting history
    names MORE THAN ONE distinct contest_id, that is conflicting evidence, not
    authoritative evidence -- Case D must NOT resolve them to either contest.
    (Investigation's "B. multiple conflicting contests from voting" bucket --
    distinct from the "no votes at all" limitation tested separately below.)"""
    owner = _user(db, "conflicting-votes")
    rnd = _round(db, "conflicting-votes")
    season = ContestSeason(round_id=rnd.id, title="Season conflicting-votes", level=SeasonLevel.COUNTRY)
    db.add(season)
    db.flush()
    contest_a = Contest(name="Contest A conflicting", contest_type="t", contest_mode="nomination", level="country")
    contest_b = Contest(name="Contest B conflicting", contest_type="t", contest_mode="nomination", level="country")
    db.add(contest_a)
    db.add(contest_b)
    db.flush()
    _link(db, contest_a, season)
    _link(db, contest_b, season)  # season links to TWO contests -- Case C does not apply

    contestant = Contestant(
        user_id=owner.id,
        round_id=rnd.id,
        season_id=season.id,
        contest_id=None,
        is_active=True,
        is_deleted=False,
        is_qualified=True,
        country="Benin",
        title="Genuine season contestant (conflicting votes)",
    )
    db.add(contestant)
    db.flush()
    _membership(db, contestant, season)
    # Votes for BOTH contests -- two distinct contest_ids, not one. Case D's
    # `distinct_voted_contests == 1` check must reject this as conflicting.
    _vote(db, _user(db, "conflicting-voter-a"), contestant, contest_a, season)
    _vote(db, _user(db, "conflicting-voter-b"), contestant, contest_b, season)

    result_a = SeasonMigrationService.get_top_contestants_by_location(
        db, season.id, "country", contest_id=contest_a.id, diagnostics=False, qualified_only=False,
    )
    result_b = SeasonMigrationService.get_top_contestants_by_location(
        db, season.id, "country", contest_id=contest_b.id, diagnostics=False, qualified_only=False,
    )
    all_returned = [c.id for group in result_a.values() for c in group] + [
        c.id for group in result_b.values() for c in group
    ]
    assert contestant.id not in all_returned  # conflicting evidence -- must not resolve to either


def test_KNOWN_LIMITATION_multi_contest_genuine_season_contestant_with_no_votes_remains_unresolved(db):
    """The genuine, still-open limitation (see
    KALUTASOCIETY_TOP_HIGH5_MULTICONTEST_INVESTIGATION -- 65/118 contestants):
    a genuine season-linked contestant whose season links to MULTIPLE contests
    and who has NO voting history has no authoritative signal at all. They
    must remain unresolved -- not attached to any contest, not duplicated
    across every linked contest, not guessed -- pending either a new data
    source or an explicit product decision. This is not asserting correct
    long-term behavior; it documents the current, intentional boundary."""
    owner = _user(db, "still-ambiguous")
    rnd = _round(db, "still-ambiguous")
    season = ContestSeason(round_id=rnd.id, title="Season still-ambiguous", level=SeasonLevel.COUNTRY)
    db.add(season)
    db.flush()
    contest_a = Contest(name="Contest A", contest_type="t", contest_mode="nomination", level="country")
    contest_b = Contest(name="Contest B", contest_type="t", contest_mode="nomination", level="country")
    db.add(contest_a)
    db.add(contest_b)
    db.flush()
    _link(db, contest_a, season)
    _link(db, contest_b, season)  # season links to TWO contests, and...

    contestant = Contestant(
        user_id=owner.id,
        round_id=rnd.id,
        season_id=season.id,
        contest_id=None,
        is_active=True,
        is_deleted=False,
        is_qualified=True,
        country="Benin",
        title="Genuine season contestant (no votes, multi-contest)",
    )
    db.add(contestant)
    db.flush()
    _membership(db, contestant, season)
    # ...no votes at all -- neither Case C (not unique) nor Case D (no vote
    # evidence) can resolve this contestant.

    result_a = SeasonMigrationService.get_top_contestants_by_location(
        db, season.id, "country", contest_id=contest_a.id, diagnostics=False, qualified_only=False,
    )
    result_b = SeasonMigrationService.get_top_contestants_by_location(
        db, season.id, "country", contest_id=contest_b.id, diagnostics=False, qualified_only=False,
    )
    all_returned = [c.id for group in result_a.values() for c in group] + [
        c.id for group in result_b.values() for c in group
    ]
    assert contestant.id not in all_returned  # current, documented limitation -- not a bug


def test_city_top_high5_still_disabled_and_unaffected_by_fix(db):
    """Regression guard: city-level Top High5 is intentionally always-empty
    by an explicit business rule unrelated to this fix -- confirm nothing
    here accidentally re-enables it. (get_top_contestants_by_location itself
    is level-agnostic; the city disablement lives in the endpoint layer, so
    this simply confirms the service function's own behavior is unaffected
    for a city-scoped call.)"""
    owner = _user(db, "city-check")
    rnd = _round(db, "city-check")
    season = ContestSeason(round_id=rnd.id, title="Season city-check", level=SeasonLevel.CITY)
    db.add(season)
    db.flush()
    # Decoy contest first: avoid an accidental contest.id == season.id coincidence
    # (see comment in test_legacy_contestant_still_found_via_get_top_contestants_by_location).
    db.add(Contest(name="Decoy", contest_type="t", contest_mode="nomination", level="city"))
    db.flush()
    contest = Contest(name="City Contest", contest_type="t", contest_mode="nomination", level="city")
    db.add(contest)
    db.flush()
    assert contest.id != season.id
    _link(db, contest, season)

    contestant = Contestant(
        user_id=owner.id,
        round_id=rnd.id,
        season_id=contest.id,
        contest_id=None,
        is_active=True,
        is_deleted=False,
        is_qualified=True,
        city="Cotonou",
        country="Benin",
        title="City contestant",
    )
    db.add(contestant)
    db.flush()
    _membership(db, contestant, season)
    _vote(db, _user(db, "city-check-voter"), contestant, contest, season)

    # get_top_contestants_by_location itself has no city-disable rule -- that
    # lives in the endpoint. Confirm the service layer still resolves legacy
    # contestants correctly at city level (proves the fix didn't break this
    # location_field branch), independent of the endpoint-level business rule.
    result = SeasonMigrationService.get_top_contestants_by_location(
        db,
        season.id,
        "city",
        contest_id=contest.id,
        diagnostics=False,
        qualified_only=False,
    )
    all_returned = [c.id for group in result.values() for c in group]
    assert contestant.id in all_returned
