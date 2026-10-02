"""Phase 8: voting, TopHigh5 and progression safety (MyHigh5 Child/Teen Safety).

Every user, entry, vote, round, guardian and policy here is SYNTHETIC. No
external service is called and nothing touches a real database, payment,
KYC provider, email or financial record.

Test ids in the docstrings refer to the Phase 8 required matrix (A..AN).
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import update

from app.core.child_safety import (
    ContentRating as CR,
    ContestEntryKind,
    GuardianConsentScope as S,
    NomineeAgeDeclaration as D,
)
from app.models.age_safety import AgeSafetyEvent
from app.models.content_moderation import ContentModeration
from app.models.contest_eligibility import ContestEntrySafety
from app.models.contests import (
    Contestant,
    ContestantSeason,
    ContestSeason,
    ContestSeasonLink,
    SeasonLevel,
    TopHigh5Result,
)
from app.models.progression_safety import ProgressionSafetyHold
from app.models.round import Round, RoundStatus, round_contests
from app.models.voting import ContestantVoting
from app.services import contest_eligibility as ce
from app.services import content_safety as cs
from app.services import participation_safety as ps
from app.services import viewer_access as va
from app.services.age_policy_engine import utc_today
from app.services.season_migration import SeasonMigrationService
from app.services.top_high5_live import _TARGET_MONTH_OFFSET, resolve_live_top_high5, target_cohort_month
from app.services.voting_ranking import (
    RankingRow,
    VotingConflict,
    VotingValidationError,
    aggregate_rankings,
    cast_myhigh5_vote,
    rank_rows,
    reorder_myhigh5_votes,
    replace_fifth_myhigh5_vote,
)
from tests.unit.test_age_gate_registration import auth
from tests.unit.test_phase5_contest_eligibility import (
    EXPOSED,
    accept_admin_review,  # noqa: F401 - fixture
    contest,
    nominate,
    person,
    submit,
    verified_guardian,
)
from tests.unit.test_phase6_content_safety import role_user
from tests.unit.test_phase7_age_safe_delivery import SECRET_TITLE, gov

TODAY = utc_today()
V = ps.VoteUnavailable


# ---------------------------------------------------------------------------
# helpers (synthetic data only)
# ---------------------------------------------------------------------------

def _add_months(d: date, n: int) -> date:
    return SeasonMigrationService._add_months(d, n)


def _month_end(d: date) -> date:
    return _add_months(d, 1) - timedelta(days=1)


def make_round(db, submission_month: date, name="R") -> Round:
    """Canonical PARTICIPATION calendar: City M+1 .. Global M+5."""
    m = [submission_month] + [_add_months(submission_month, i) for i in range(1, 6)]
    rnd = Round(name=f"{name} {submission_month:%Y-%m}", status=RoundStatus.ACTIVE,
                submission_start_date=m[0], submission_end_date=_month_end(m[0]),
                city_season_start_date=m[1], city_season_end_date=_month_end(m[1]),
                country_season_start_date=m[2], country_season_end_date=_month_end(m[2]),
                regional_start_date=m[3], regional_end_date=_month_end(m[3]),
                continental_start_date=m[4], continental_end_date=_month_end(m[4]),
                global_start_date=m[5], global_end_date=_month_end(m[5]))
    db.add(rnd)
    db.flush()
    return rnd


def season(db, rnd, ct, level: SeasonLevel, *, link=True) -> ContestSeason:
    s = ContestSeason(round_id=rnd.id, title=f"S {level.value} {rnd.id}", level=level)
    db.add(s)
    db.flush()
    if link:
        db.add(ContestSeasonLink(contest_id=ct.id, season_id=s.id, is_active=True))
        db.flush()
    return s


def phase5_entry(db, user, ct, rnd, *, decision=None, kind=ContestEntryKind.PERSONAL_SUBMISSION,
                 declaration=None, region="East Africa", country="Tanzania", city="Arusha", title=None):
    """A contestant + Phase 5/6 records created exactly like the submission endpoint."""
    decision = decision or submit(db, user, ct)
    c = Contestant(user_id=user.id, season_id=ct.id, contest_id=ct.id, round_id=rnd.id,
                   title=title or f"Entry {user.id}", description="d", is_active=decision.public, is_deleted=False,
                   is_qualified=True, region=region, country=country, city=city, continent="Africa",
                   entry_type="nomination" if kind == ContestEntryKind.NOMINATION else "participation")
    db.add(c)
    db.flush()
    safety = ce.record_new_entry(db, c, decision, kind=kind, submitted_by=user, contest_id=ct.id,
                                 nominee_age_declaration=declaration, now=datetime.utcnow())
    db.commit()
    return c, safety


def member(db, c, s, active=True):
    db.add(ContestantSeason(contestant_id=c.id, season_id=s.id, is_active=active, joined_at=datetime.utcnow()))
    db.flush()


def votes(db, c, ct, s, points: int, n: int = 1):
    for _ in range(n):
        voter = person(db, 30)
        db.add(ContestantVoting(user_id=voter.id, contestant_id=c.id, contest_id=ct.id, season_id=s.id,
                                vote_bucket_key=SeasonMigrationService._top_high5_bucket_key_for_contest(ct),
                                position=1, points=points))
    db.flush()


def vote_rows(db):
    return sorted((v.id, v.user_id, v.contestant_id, v.season_id, v.position, v.points)
                  for v in db.query(ContestantVoting).all())


def suspend(db, safety):
    """A later safety change: rights disputed -> Phase 5 re-evaluation suspends the entry."""
    admin = person(db, 45, admin=True)
    ce.admin_review(db, safety, action="DISPUTE_RIGHTS", admin_id=admin.id, note="synthetic", today=TODAY)
    db.refresh(safety)
    assert safety.exposure_status == "HELD" and safety.activated_at is not None
    return admin


def resolve(db, safety):
    admin = person(db, 45, admin=True)
    ce.admin_review(db, safety, action="CONFIRM_RIGHTS", admin_id=admin.id, note="synthetic", today=TODAY)
    db.refresh(safety)
    return safety


def cast(db, voter, c, s_id=1, ct_id=None, bucket="ty:beauty:participation"):
    return cast_myhigh5_vote(db, voter_id=voter.id, contestant_id=c.id, nominator_user_id=c.user_id,
                             season_id=s_id, contest_id=ct_id or c.contest_id or 1, bucket_key=bucket)


def events(db, kind):
    return db.query(AgeSafetyEvent).filter(AgeSafetyEvent.event_type == kind).all()


def cohort(db, n=6, *, level=SeasonLevel.REGIONAL, submission_month=None, points=None):
    """A participation cohort at `level` with descending points (entry 0 leads)."""
    submission_month = submission_month or _add_months(date(TODAY.year, TODAY.month, 1), -3)
    rnd = make_round(db, submission_month)
    ct = contest(db)
    db.execute(round_contests.insert().values(round_id=rnd.id, contest_id=ct.id))
    src = season(db, rnd, ct, level)
    entries = []
    for i in range(n):
        user = person(db, 30)
        c, safety = phase5_entry(db, user, ct, rnd)
        member(db, c, src)
        votes(db, c, ct, src, (points or [60, 50, 40, 30, 20, 10, 5, 4])[i])
        entries.append((c, safety))
    db.commit()
    return rnd, ct, src, entries


def promote(db, ct, src, frm=SeasonLevel.REGIONAL, to=SeasonLevel.CONTINENT):
    result = SeasonMigrationService.promote_to_next_level(db, frm, to, ct.id, from_season_id=src.id)
    db.commit()
    return result


def active_in(db, contestant_id, season_id) -> bool:
    return db.query(ContestantSeason).filter(ContestantSeason.contestant_id == contestant_id,
                                             ContestantSeason.season_id == season_id,
                                             ContestantSeason.is_active == True).first() is not None  # noqa: E712


def top_high5(db, level, viewer=None, today=None):
    from app.api.api_v1.endpoints.season_migration import secure_top_high5_payload

    raw = resolve_live_top_high5(db, level=level, selected_country="Tanzania", variants={"tanzania", "tz"},
                                 today=today or TODAY)
    return raw, secure_top_high5_payload(db, viewer, raw)


def rows_of(payload):
    return [r for card in payload["contests"] for r in card["rows"]]


def target_today_for(level: SeasonLevel, submission_month: date) -> date:
    return _add_months(submission_month, _TARGET_MONTH_OFFSET[level])


@pytest.fixture
def open_voting(monkeypatch):
    """Vote windows are not under test here: open every stage (synthetic)."""
    from app.services.contest_status import contest_status_service

    monkeypatch.setattr(contest_status_service, "season_stage_voting_status", lambda *a, **k: (True, None))
    monkeypatch.setattr(contest_status_service, "round_voting_open_at", lambda *a, **k: True)
    monkeypatch.setattr(contest_status_service, "check_voting_allowed", lambda *a, **k: (True, None))


def endpoint_scope(db, *, level=SeasonLevel.GLOBAL, user=None, decision=None, **entry_kw):
    rnd = make_round(db, _add_months(date(TODAY.year, TODAY.month, 1), -2))
    ct = contest(db)
    db.execute(round_contests.insert().values(round_id=rnd.id, contest_id=ct.id))
    s = season(db, rnd, ct, level)
    owner = user or person(db, 30)
    c, safety = phase5_entry(db, owner, ct, rnd, decision=decision, **entry_kw)
    member(db, c, s)
    db.commit()
    return ct, s, c, safety


def post_vote(client, voter, c, ct, replace=False):
    path = f"/api/v1/contestants/{c.id}/vote" + ("/replace" if replace else "")
    return client.post(path, params={"contest_id": ct.id}, headers=auth(voter))


# ===========================================================================
# VOTING (A-K)
# ===========================================================================

def test_A_eligible_adult_contestant_can_receive_a_vote(db):
    voter = person(db, 30)
    for entry in (gov(db, person(db, 30), rating=CR.GENERAL), gov(db, person(db, 30), legacy=True)):
        vote = cast(db, voter, entry)
        assert vote.id and vote.points == 5 - (vote.position - 1)
    db.commit()


def test_A_endpoint_eligible_vote_is_recorded(client, db, open_voting):
    ct, s, c, _ = endpoint_scope(db)
    voter = person(db, 30)
    r = post_vote(client, voter, c, ct)
    assert r.status_code == 201, r.text
    assert db.query(ContestantVoting).filter(ContestantVoting.contestant_id == c.id).count() == 1


@pytest.mark.parametrize("kind", ["HOLD", "REVIEW", "ESCALATED", "PROHIBITED"])
def test_B_G_H_restricted_entries_cannot_receive_votes(db, kind):
    """B (Phase 5 HOLD), G (child-safety escalation), H (PROHIBITED)."""
    from tests.unit.test_phase7_age_safe_delivery import KINDS

    entry = gov(db, person(db, 30), **KINDS[kind])
    before = vote_rows(db)
    with pytest.raises(V):
        cast(db, person(db, 30), entry)
    db.rollback()
    assert vote_rows(db) == before


def test_B_phase5_hold_from_real_submission_blocks_vote(db):
    rnd = make_round(db, date(TODAY.year, TODAY.month, 1))
    ct = contest(db)
    c, safety = phase5_entry(db, person(db, None), ct, rnd)   # missing DOB -> HOLD
    assert safety.exposure_status == "HELD"
    with pytest.raises(V) as exc:
        cast(db, person(db, 30), c)
    assert ps.Reason.HELD in exc.value.reasons and "AGE_REQUIRED" in exc.value.reasons


def test_C_direct_id_vote_on_hidden_contestant_fails_generically(client, db, open_voting):
    ct, s, c, safety = endpoint_scope(db, user=person(db, None), title=SECRET_TITLE)  # held (no DOB)
    voter = person(db, 30)
    for replace in (False, True):
        r = post_vote(client, voter, c, ct, replace=replace)
        assert r.status_code == 404
        body = r.text
        assert SECRET_TITLE not in body and "HELD" not in body and "AGE_REQUIRED" not in body
    assert db.query(ContestantVoting).filter(ContestantVoting.contestant_id == c.id).count() == 0
    audit = events(db, "VOTE_BLOCKED_SAFETY")
    assert audit and all(e.details["contestant_id"] == c.id for e in audit)
    assert "AGE_REQUIRED" in audit[0].details["reason_codes"]
    blob = json.dumps([e.details for e in audit])
    assert SECRET_TITLE not in blob and "date_of_birth" not in blob


def test_C_authoritative_check_runs_in_the_write_transaction(db):
    """Pre-check passed (entry loaded as public); the entry is escalated before
    the write; the stale in-session object must not let the vote through."""
    entry = gov(db, person(db, 30), rating=CR.GENERAL)
    assert ps.can_receive_vote(db, entry, person(db, 30)).eligible
    db.execute(update(ContestEntrySafety).where(ContestEntrySafety.contestant_id == entry.id)
               .values(exposure_status="CHILD_SAFETY_ESCALATED"))
    db.execute(update(ContentModeration).where(ContentModeration.contestant_id == entry.id)
               .values(child_safety_escalated=True, state="CHILD_SAFETY_ESCALATED", rating=None))
    with pytest.raises(V) as exc:
        cast(db, person(db, 30), entry)
    assert ps.Reason.CHILD_SAFETY in exc.value.reasons
    db.rollback()
    assert db.query(ContestantVoting).filter(ContestantVoting.contestant_id == entry.id).count() == 0


def test_C_endpoint_race_returns_generic_404_and_writes_nothing(client, db, open_voting, monkeypatch):
    ct, s, c, safety = endpoint_scope(db)
    real = ps.lock_and_check_vote

    def flip_then_check(db_, **kw):   # a moderator escalates between pre-check and write
        db_.execute(update(ContestEntrySafety).where(ContestEntrySafety.contestant_id == c.id)
                    .values(exposure_status="CHILD_SAFETY_ESCALATED"))
        return real(db_, **kw)

    monkeypatch.setattr(ps, "lock_and_check_vote", flip_then_check)
    r = post_vote(client, person(db, 30), c, ct)
    assert r.status_code == 404 and "CHILD" not in r.text
    assert db.query(ContestantVoting).filter(ContestantVoting.contestant_id == c.id).count() == 0


def test_D_unknown_age_contestant_is_fail_closed(db):
    rnd = make_round(db, date(TODAY.year, TODAY.month, 1))
    c, _ = phase5_entry(db, person(db, None), contest(db), rnd)
    assert not ps.participation_decision(db, c).eligible
    assert not ps.can_progress(db, c).eligible
    with pytest.raises(V):
        cast(db, person(db, 30), c)


def test_E_minor_without_guardian_consent_cannot_receive_vote(db):
    rnd = make_round(db, date(TODAY.year, TODAY.month, 1))
    c, safety = phase5_entry(db, person(db, 15), contest(db), rnd)
    assert "GUARDIAN_CONSENT_REQUIRED" in safety.reason_codes
    with pytest.raises(V) as exc:
        cast(db, person(db, 30), c)
    assert "GUARDIAN_CONSENT_REQUIRED" in exc.value.reasons


def test_F_valid_minor_participates_only_where_policy_allows(db, accept_admin_review):
    minor = person(db, 15)
    verified_guardian(db, minor, scopes=[S(x) for x in EXPOSED])
    rnd = make_round(db, date(TODAY.year, TODAY.month, 1))
    ct = contest(db)
    c, safety = phase5_entry(db, minor, ct, rnd)
    assert safety.exposure_status == "PUBLIC", safety.reason_codes
    assert cast(db, person(db, 30), c).id
    db.commit()
    # A contest whose rules do not allow minors keeps the same minor held.
    adult_only = contest(db, min_age=18)
    c2, safety2 = phase5_entry(db, minor, adult_only, rnd, decision=submit(db, minor, adult_only))
    assert safety2.exposure_status == "HELD"
    with pytest.raises(V):
        cast(db, person(db, 30), c2)


def test_I_duplicate_and_five_vote_limits_are_unchanged(db):
    voter = person(db, 30)
    entries = [gov(db, person(db, 30), rating=CR.GENERAL) for _ in range(6)]
    for e in entries[:5]:
        cast(db, voter, e)
    db.commit()
    with pytest.raises(VotingConflict) as dup:
        cast(db, voter, entries[0])
    assert dup.value.code == "already_voted"
    db.rollback()
    with pytest.raises(VotingConflict) as full:
        cast(db, voter, entries[5])
    assert full.value.code == "max_votes_reached"
    db.rollback()
    vote, removed = replace_fifth_myhigh5_vote(db, voter_id=voter.id, contestant_id=entries[5].id,
                                               nominator_user_id=entries[5].user_id, season_id=1,
                                               contest_id=entries[5].contest_id,
                                               bucket_key="ty:beauty:participation")
    assert vote.position == 5 and vote.points == 1 and removed == entries[4].id


def test_J_K_historical_vote_kept_and_no_new_vote_after_restriction(db):
    rnd, ct, src, entries = cohort(db, n=2)
    c, safety = entries[0]
    before = vote_rows(db)
    suspend(db, safety)
    assert vote_rows(db) == before                      # J: nothing deleted / rewritten
    with pytest.raises(V):                               # K: no new vote
        cast(db, person(db, 30), c, s_id=src.id, ct_id=ct.id)
    db.rollback()
    assert vote_rows(db) == before


def test_reorder_never_moves_points_toward_a_restricted_entry(db):
    voter = person(db, 30)
    a, b, c = (gov(db, person(db, 30), rating=CR.GENERAL) for _ in range(3))
    for e in (a, b, c):
        cast(db, voter, e)
    db.commit()
    db.execute(update(ContestEntrySafety).where(ContestEntrySafety.contestant_id == b.id)
               .values(exposure_status="HELD"))
    kw = dict(voter_id=voter.id, season_id=1, contest_id=a.contest_id, bucket_key="ty:beauty:participation")
    with pytest.raises(VotingValidationError):
        reorder_myhigh5_votes(db, ordered_contestant_ids=[b.id, a.id, c.id], **kw)
    db.rollback()
    db.execute(update(ContestEntrySafety).where(ContestEntrySafety.contestant_id == b.id)
               .values(exposure_status="HELD"))
    held_before = db.query(ContestantVoting).filter(ContestantVoting.contestant_id == b.id).one().points
    reorder_myhigh5_votes(db, ordered_contestant_ids=[c.id, b.id, a.id], **kw)  # b keeps position 2
    assert db.query(ContestantVoting).filter(ContestantVoting.contestant_id == b.id).one().points == held_before


# ===========================================================================
# TOPHIGH5 (L-T, AH, AJ)
# ===========================================================================

def test_L_M_N_Q_W_held_contestant_excluded_without_substitute(db):
    month = _add_months(date(TODAY.year, TODAY.month, 1), -3)
    rnd, ct, src, entries = cohort(db, n=6, submission_month=month)
    today = target_today_for(SeasonLevel.REGIONAL, month)
    raw_before, before = top_high5(db, SeasonLevel.REGIONAL, today=today)
    assert [r["contestant_id"] for r in rows_of(before)] == [e[0].id for e in entries[:5]]
    points_before = {r["contestant_id"]: (r["rank"], r["stars_points"], r["votes_count"]) for r in rows_of(before)}
    votes_before = vote_rows(db)

    suspend(db, entries[1][1])
    raw, after = top_high5(db, SeasonLevel.REGIONAL, today=today)
    ids = [r["contestant_id"] for r in rows_of(after)]
    assert entries[1][0].id not in ids                                    # L
    assert entries[5][0].id not in ids                                    # W / Q: no substitute
    assert ids == [entries[i][0].id for i in (0, 2, 3, 4)]                # Q: fewer than five
    for r in rows_of(after):                                              # N + rank preservation
        assert (r["rank"], r["stars_points"], r["votes_count"]) == points_before[r["contestant_id"]]
    assert [r["rank"] for r in rows_of(after)] == [1, 3, 4, 5]
    assert vote_rows(db) == votes_before                                  # M
    # The raw (pre-output) ranking still holds the slot: ranking maths untouched.
    assert [r["contestant_id"] for r in rows_of(raw)] == [e[0].id for e in entries[:5]]


def test_O_P_exact_cohort_month_and_no_fallback(db):
    month = _add_months(date(TODAY.year, TODAY.month, 1), -3)
    rnd, ct, src, entries = cohort(db, n=2, submission_month=month)
    # A full, fully eligible cohort one month EARLIER must never fill the gap.
    other = make_round(db, _add_months(month, -1), name="Other")
    ct2 = contest(db)
    src2 = season(db, other, ct2, SeasonLevel.REGIONAL)
    others = []
    for _ in range(5):
        c, _s = phase5_entry(db, person(db, 30), ct2, other)
        member(db, c, src2)
        votes(db, c, ct2, src2, 99)
        others.append(c.id)
    db.commit()
    suspend(db, entries[0][1])
    today = target_today_for(SeasonLevel.REGIONAL, month)
    raw, out = top_high5(db, SeasonLevel.REGIONAL, today=today)
    assert out["target_month"] == month.isoformat() and out["mixed_cohorts"] is False
    ids = [r["contestant_id"] for r in rows_of(out)]
    assert ids == [entries[1][0].id] and not set(ids) & set(others)
    assert {c["cohort_round_id"] for c in out["contests"]} == {rnd.id}


def legacy_entry(db, user, ct, rnd, **cols):
    """A historical (pre-Phase 5) entry: no participation/moderation record."""
    c = Contestant(user_id=user.id, season_id=ct.id, contest_id=ct.id, round_id=rnd.id, is_active=True,
                   is_deleted=False, is_qualified=True, entry_type="participation", continent="Africa",
                   **{"title": "Legacy entry", "region": "East Africa", "country": "Tanzania", "city": "Arusha",
                      **cols})
    db.add(c)
    db.flush()
    return c


def test_R_eligible_teen_stays_ranked_with_private_fields_hidden(db):
    """Participation eligibility (a historical teen entry keeps its historical
    treatment) is independent of which profile fields a viewer receives."""
    month = _add_months(date(TODAY.year, TODAY.month, 1), -3)
    rnd, ct, src, entries = cohort(db, n=1, submission_month=month)
    teen = person(db, 15, full_name="Teen Realname")
    c = legacy_entry(db, teen, ct, rnd, title="Teen entry")
    assert ps.can_appear_in_ranking(db, c).eligible
    member(db, c, src)
    votes(db, c, ct, src, 100)
    db.commit()
    raw, out = top_high5(db, SeasonLevel.REGIONAL, today=target_today_for(SeasonLevel.REGIONAL, month))
    row = next(r for r in rows_of(out) if r["contestant_id"] == c.id)
    assert row["rank"] == 1                               # participation: ranked
    assert row["city"] is None and row["country"] is None  # viewer fields: minimized (Phase 7)
    assert row["author_name"] == teen.username and "Teen Realname" not in json.dumps(out)
    assert row["contestant_title"] == "Teen entry"


def test_S_T_adult_rated_entry_viewer_rules(db):
    """S: minors / UNKNOWN / anonymous never receive ADULT_18_PLUS data or vote on it.
    T: an adult viewer receives it and may vote."""
    entry = gov(db, person(db, 30), rating=CR.ADULT_18_PLUS)
    row = {"contestant_id": entry.id, "contestant_title": SECRET_TITLE}
    for u in (None, person(db, None), person(db, 12), person(db, 16)):
        secured = va.secure_entry_refs(db, va.viewer_for(db, u), [dict(row)])[0]
        assert secured["contestant_title"] is None and secured["content_restricted"] is True
        if u is not None:
            with pytest.raises(V) as exc:
                cast(db, u, entry)
            assert exc.value.reasons == (ps.Reason.VIEWER_RESTRICTED,)
            db.rollback()
    adult = person(db, 30)
    assert va.secure_entry_refs(db, va.viewer_for(db, adult), [dict(row)])[0]["contestant_title"] == SECRET_TITLE
    assert cast(db, adult, entry).id
    # Viewer restriction never removes an ELIGIBLE contestant from the ranking.
    assert ps.can_appear_in_ranking(db, entry).eligible


def test_AH_shared_or_stale_result_cannot_expose_newly_restricted_contestant(db):
    from app.api.api_v1.endpoints.season_migration import secure_top_high5_payload

    month = _add_months(date(TODAY.year, TODAY.month, 1), -3)
    rnd, ct, src, entries = cohort(db, n=3, submission_month=month)
    raw, _ = top_high5(db, SeasonLevel.REGIONAL, today=target_today_for(SeasonLevel.REGIONAL, month))
    suspend(db, entries[0][1])              # restricted AFTER the (shared) result was computed
    out = secure_top_high5_payload(db, None, raw)
    assert entries[0][0].id not in [r["contestant_id"] for r in rows_of(out)]


def test_AH_frozen_snapshot_rows_are_filtered_with_stored_ranks_kept(db):
    from app.api.api_v1.endpoints.season_migration import secure_top_high5_payload

    rnd, ct, src, entries = cohort(db, n=3)
    snapshot = {"contests": [{"contest_id": ct.id, "rows": [
        {"rank": i + 1, "contestant_id": e[0].id, "contestant_title": e[0].title, "stars_points": 9}
        for i, e in enumerate(entries)]}]}
    suspend(db, entries[0][1])
    out = secure_top_high5_payload(db, None, snapshot)
    assert [(r["rank"], r["contestant_id"]) for r in rows_of(out)] == [(2, entries[1][0].id), (3, entries[2][0].id)]
    assert db.query(TopHigh5Result).count() == 0   # nothing written


def test_AJ_public_ranking_payload_never_carries_restricted_content(db):
    month = _add_months(date(TODAY.year, TODAY.month, 1), -3)
    rnd, ct, src, entries = cohort(db, n=2, submission_month=month)
    held = entries[0][0]
    held.title = SECRET_TITLE
    db.commit()
    suspend(db, entries[0][1])
    for viewer in (None, person(db, 30), person(db, 14)):
        _, out = top_high5(db, SeasonLevel.REGIONAL, viewer=viewer,
                           today=target_today_for(SeasonLevel.REGIONAL, month))
        blob = json.dumps(out, default=str)
        assert SECRET_TITLE not in blob and f'"contestant_id": {held.id}' not in blob


def test_AJ_vote_conflict_never_names_a_restricted_entry(db):
    voter = person(db, 30)
    entries = [gov(db, person(db, 30), rating=CR.GENERAL) for _ in range(5)]
    for e in entries:
        cast(db, voter, e)
    db.commit()
    db.execute(update(ContestEntrySafety).where(ContestEntrySafety.contestant_id == entries[4].id)
               .values(exposure_status="HELD"))
    db.commit()
    from app.api.api_v1.endpoints.contestant import _safe_entry_title

    assert _safe_entry_title(db, voter, entries[4].id) is None
    assert _safe_entry_title(db, voter, entries[0].id) == SECRET_TITLE


def test_AJ_location_vote_error_does_not_echo_a_minors_place(client, db, open_voting):
    minor = person(db, 15)
    ct, s, c, safety = endpoint_scope(db, level=SeasonLevel.COUNTRY, country="Tanzania")
    c.user_id = minor.id              # a historical minor entry (no Phase 5/6 record)
    db.delete(safety)
    db.query(ContentModeration).filter(ContentModeration.contestant_id == c.id).delete()
    db.commit()
    assert ps.participation_decision(db, c).eligible
    voter = person(db, 30, country="Kenya", continent="Africa")
    r = post_vote(client, voter, c, ct)
    assert r.status_code == 400 and "Tanzania" not in r.text
    # An adult contestant's place is still echoed exactly as before.
    ct2, s2, c2, _ = endpoint_scope(db, level=SeasonLevel.COUNTRY, country="Tanzania")
    assert "Tanzania" in post_vote(client, voter, c2, ct2).text


def test_graphql_lists_only_eligible_anonymous_deliverable_entries(db):
    from app.graphql.schema import public_graphql_contestants
    from tests.unit.test_phase7_age_safe_delivery import KINDS

    owner = person(db, 30)
    made = {k: gov(db, owner, **kw) for k, kw in KINDS.items()}
    kept = {c.id for c in public_graphql_contestants(db, list(made.values()))}
    assert kept == {made["GENERAL"].id, made["LEGACY"].id}


# ===========================================================================
# PROGRESSION (U-AG)
# ===========================================================================

def test_U_V_W_safety_held_qualifier_is_held_not_deleted_not_replaced(db):
    rnd, ct, src, entries = cohort(db, n=6)
    held_c, held_s = entries[1]
    suspend(db, held_s)
    votes_before = vote_rows(db)
    result = promote(db, ct, src)
    dest = result["to_season_id"]
    promoted = set(result["promoted_contestant_ids"])
    assert promoted == {entries[i][0].id for i in (0, 2, 3, 4)}           # U + W (no #6)
    assert result["held_contestant_ids"] == [held_c.id]
    assert not active_in(db, entries[5][0].id, dest)                      # W: no substitute
    db.refresh(held_c)
    assert held_c.is_deleted is False and held_c.is_qualified is True     # V: not deleted, no fabricated loss
    assert active_in(db, held_c.id, src.id) and not active_in(db, held_c.id, dest)
    hold = db.query(ProgressionSafetyHold).one()
    assert (hold.contestant_id, hold.to_season_id, hold.status) == (held_c.id, dest, "HELD")
    assert "ENTRY_HELD" in hold.reason_codes and "RIGHTS_CONFIRMATION_REQUIRED" in hold.reason_codes
    assert vote_rows(db) == votes_before
    assert events(db, "PROGRESSION_HELD_SAFETY")


def test_X_resolved_hold_is_released_into_the_same_stage(db):
    rnd, ct, src, entries = cohort(db, n=3)
    held_c, held_s = entries[0]
    suspend(db, held_s)
    dest = promote(db, ct, src)["to_season_id"]
    resolve(db, held_s)                                       # rights confirmed -> Phase 5 re-evaluation hook
    assert held_s.exposure_status == "PUBLIC"
    hold = db.query(ProgressionSafetyHold).one()
    db.refresh(hold)
    assert hold.status == "RELEASED" and hold.resolution == "RELEASED_AFTER_REEVALUATION"
    assert active_in(db, held_c.id, dest) and not active_in(db, held_c.id, src.id)
    assert events(db, "PROGRESSION_RELEASED_AFTER_REEVALUATION")


def test_Y_release_after_stage_timing_never_skips_or_invents_a_month(db):
    rnd, ct, src, entries = cohort(db, n=2, submission_month=_add_months(date(TODAY.year, TODAY.month, 1), -9))
    held_c, held_s = entries[0]
    suspend(db, held_s)
    dest = promote(db, ct, src)["to_season_id"]
    seasons_before = db.query(ContestSeason).count()
    resolve(db, held_s)
    hold = db.query(ProgressionSafetyHold).one()
    db.refresh(hold)
    assert hold.status == "REVIEW_REQUIRED" and hold.resolution == "STAGE_TIMING_PASSED"
    assert not active_in(db, held_c.id, dest) and active_in(db, held_c.id, src.id)
    assert db.query(ContestSeason).count() == seasons_before
    assert events(db, "PROGRESSION_REVIEW_REQUIRED")


def test_Z_AA_nomination_claim_and_actor_separation_cannot_be_bypassed(db):
    nominator = person(db, 40)          # an adult nominator (also the sponsor / "guardian" by claim)
    rnd = make_round(db, date(TODAY.year, TODAY.month, 1))
    ct = contest(db, mode="nomination")
    for declaration in (D.ADULT, D.MINOR):
        c, safety = phase5_entry(db, nominator, ct, rnd, kind=ContestEntryKind.NOMINATION, declaration=declaration,
                                 decision=nominate(db, nominator, ct, declaration=declaration))
        assert safety.exposure_status == "HELD" and "NOMINEE_UNCLAIMED" in safety.reason_codes
        decision = ps.can_progress(db, c)
        assert not decision.eligible and "NOMINEE_UNCLAIMED" in decision.reasons
        assert not ps.can_appear_in_ranking(db, c).eligible
        with pytest.raises(V):
            cast(db, person(db, 30), c)
        db.rollback()
        with pytest.raises(V):          # the nominator can't vote it through either
            cast(db, nominator, c)
        db.rollback()


def test_AB_guardian_requirement_stays_authoritative_for_progression(db):
    rnd = make_round(db, date(TODAY.year, TODAY.month, 1))
    c, safety = phase5_entry(db, person(db, 14), contest(db), rnd)
    decision = ps.can_progress(db, c)
    assert not decision.eligible and "GUARDIAN_CONSENT_REQUIRED" in decision.reasons
    assert c.is_active is False  # no KYC/admin shortcut made it active


def test_AC_AD_admin_and_moderator_cannot_clear_a_child_safety_block(client, db):
    rnd, ct, src, entries = cohort(db, n=1)
    c, safety = entries[0]
    admin = person(db, 45, admin=True)
    ce.admin_review(db, safety, action="ESCALATE_CHILD_SAFETY", admin_id=admin.id, note="synthetic", today=TODAY)
    moderation = cs.moderation_for(db, c.id)
    for actor in (admin, role_user(db, "moderate_content")):
        with pytest.raises(cs.ModerationError) as exc:
            cs.moderate(db, moderation, action="APPROVE", actor=actor, reason="X_TEST", rating=CR.GENERAL)
        assert exc.value.code == "CHILD_SAFETY_LOCKED"
        db.rollback()
    with pytest.raises(cs.ModerationError):
        cs.resolve_child_safety(db, moderation, resolution=cs.ChildSafetyResolution.NO_CHILD_SAFETY_CONCERN,
                                actor=admin, reason="X_TEST")
    db.rollback()
    # Manual admin progression is refused by the same gate.
    dest = season(db, rnd, ct, SeasonLevel.CONTINENT)
    db.commit()
    r = client.put(f"/api/v1/admin/contestants/{c.id}", json={"season_id": dest.id}, headers=auth(admin))
    assert r.status_code == 409 and "CHILD" not in r.text
    assert not active_in(db, c.id, dest.id)
    # AD: the explicit resolver can only return it to ordinary review - never publish it.
    resolver = role_user(db, "moderate_content", "child_safety_resolve")
    cs.resolve_child_safety(db, cs.moderation_for(db, c.id), resolution=cs.ChildSafetyResolution.NO_CHILD_SAFETY_CONCERN,
                            actor=resolver, reason="X_TEST")
    assert not ps.participation_decision(db, db.query(Contestant).get(c.id)).eligible
    assert ps.Reason.CHILD_SAFETY not in ps.participation_decision(db, db.query(Contestant).get(c.id)).reasons


def test_AE_scheduler_paths_use_the_gate(db, monkeypatch):
    # Entry stage (submission -> City): an ineligible entry is not migrated.
    rnd = make_round(db, _add_months(date(TODAY.year, TODAY.month, 1), -1))
    ct = contest(db)
    ok, _ = phase5_entry(db, person(db, 30), ct, rnd)
    bad = gov(db, person(db, 30), rating=CR.GENERAL, legacy=True)
    bad.round_id, bad.season_id, bad.contest_id = rnd.id, ct.id, ct.id
    db.add(ContentModeration(contestant_id=bad.id, state="REVIEW_REQUIRED", rating="GENERAL",
                             classifier_version="p8-test", evaluated_at=datetime.utcnow()))
    db.commit()
    result = SeasonMigrationService.migrate_to_city_season(db, ct.id, rnd.id)
    assert ok.id in result["migrated_contestant_ids"] and bad.id not in result["migrated_contestant_ids"]
    hold = db.query(ProgressionSafetyHold).filter(ProgressionSafetyHold.contestant_id == bad.id).one()
    assert hold.to_level == "city" and hold.from_season_id is None and "CONTENT_NOT_APPROVED" in hold.reason_codes
    # Promotion (scheduler + admin endpoint + celery all call promote_to_next_level) is covered
    # by the U/V/W test; the scheduler pass also sweeps open holds.
    calls = []
    monkeypatch.setattr(ps, "release_holds", lambda db_, **kw: calls.append(kw) or {"released": 0})
    SeasonMigrationService.check_and_process_migrations(db)
    assert calls


def test_AF_manual_admin_progression_uses_the_gate(client, db):
    rnd, ct, src, entries = cohort(db, n=2)
    held_c, held_s = entries[0]
    suspend(db, held_s)
    dest = season(db, rnd, ct, SeasonLevel.CONTINENT)
    db.commit()
    admin = person(db, 45, admin=True)
    title = held_c.title
    r = client.put(f"/api/v1/admin/contestants/{held_c.id}", json={"season_id": dest.id, "title": "changed"},
                   headers=auth(admin))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "PROGRESSION_SAFETY_HOLD"
    db.expire_all()
    assert not active_in(db, held_c.id, dest.id) and db.query(Contestant).get(held_c.id).title == title
    assert db.query(ProgressionSafetyHold).filter(ProgressionSafetyHold.to_season_id == dest.id).count() == 1
    # An eligible contestant still moves exactly as before.
    ok_c = entries[1][0]
    r = client.put(f"/api/v1/admin/contestants/{ok_c.id}", json={"season_id": dest.id}, headers=auth(admin))
    assert r.status_code == 200, r.text


def test_AG_repeated_progression_is_idempotent(db):
    rnd, ct, src, entries = cohort(db, n=6)
    suspend(db, entries[1][1])
    first = promote(db, ct, src)
    memberships = db.query(ContestantSeason).count()
    link = db.query(ContestSeasonLink).filter(ContestSeasonLink.season_id == src.id).one()
    link.is_active = True   # re-run the same promotion (scheduler retries)
    db.commit()
    second = promote(db, ct, src)
    assert set(second["promoted_contestant_ids"]) == set(first["promoted_contestant_ids"])
    assert second["held_contestant_ids"] == first["held_contestant_ids"]
    assert db.query(ProgressionSafetyHold).count() == 1
    assert db.query(ContestantSeason).count() == memberships
    assert len(events(db, "PROGRESSION_HELD_SAFETY")) == 1


def test_AI_staff_can_review_held_contestant_without_making_it_public(client, db):
    rnd, ct, src, entries = cohort(db, n=2)
    held_c, held_s = entries[0]
    suspend(db, held_s)
    promote(db, ct, src)
    moderator = role_user(db, "moderate_content")
    r = client.get("/api/v1/admin/content-moderation/progression-holds", headers=auth(moderator))
    assert r.status_code == 200
    [item] = r.json()
    assert item["contestant_id"] == held_c.id and item["visibility"] == "VISIBLE_TO_STAFF"
    assert set(item) >= {"reason_codes", "status"} and "title" not in item
    recheck = client.post(f"/api/v1/admin/content-moderation/progression-holds/{item['id']}/recheck",
                          headers=auth(moderator))
    assert recheck.status_code == 200 and recheck.json()["status"] == "HELD"   # not an override
    assert not ps.participation_decision(db, held_c).eligible
    with pytest.raises(V):
        cast(db, person(db, 30), held_c)
    db.rollback()
    for u in (None, person(db, 30)):
        assert client.get("/api/v1/admin/content-moderation/progression-holds",
                          headers=auth(u) if u else {}).status_code in (401, 403)


# ===========================================================================
# LIFECYCLE / RANKING INVARIANTS (AK-AN)
# ===========================================================================

def test_AK_AM_participation_lifecycle_and_cohort_mapping_unchanged():
    assert _TARGET_MONTH_OFFSET == {SeasonLevel.CITY: 1, SeasonLevel.COUNTRY: 2, SeasonLevel.REGIONAL: 3,
                                    SeasonLevel.CONTINENT: 4, SeasonLevel.GLOBAL: 5}
    sep = date(2026, 9, 15)
    assert [target_cohort_month(level, sep) for level in _TARGET_MONTH_OFFSET] == [
        date(2026, 8, 1), date(2026, 7, 1), date(2026, 6, 1), date(2026, 5, 1), date(2026, 4, 1)]


def test_AL_nomination_lifecycle_unchanged(db):
    m = date(2026, 3, 1)
    rnd = make_round(db, m)
    opens = {level: SeasonMigrationService._nomination_vote_open_date_for_level(rnd, level)
             for level in (SeasonLevel.COUNTRY, SeasonLevel.REGIONAL, SeasonLevel.CONTINENT, SeasonLevel.GLOBAL)}
    assert [(d.year, d.month) for d in opens.values()] == [(2026, 4), (2026, 5), (2026, 6), (2026, 7)]


def test_AN_ranking_order_and_tie_behaviour_unchanged(db):
    rows = [RankingRow(contestant_id=9, total_points=5), RankingRow(contestant_id=3, total_points=5),
            RankingRow(contestant_id=4, total_points=7)]
    assert [(r.contestant_id, r.rank) for r in rank_rows(rows)] == [(4, 1), (3, 2), (9, 3)]
    month = _add_months(date(TODAY.year, TODAY.month, 1), -3)
    rnd, ct, src, entries = cohort(db, n=4, submission_month=month, points=[10, 30, 30, 20])
    ranked = aggregate_rankings(db, season_ids=[src.id], contestant_ids=[e[0].id for e in entries], contest_id=ct.id,
                                bucket_key=SeasonMigrationService._top_high5_bucket_key_for_contest(ct))
    assert [r.contestant_id for r in ranked] == [entries[1][0].id, entries[2][0].id, entries[3][0].id,
                                                  entries[0][0].id]           # promotion: lower id wins a tie
    _, out = top_high5(db, SeasonLevel.REGIONAL, today=target_today_for(SeasonLevel.REGIONAL, month))
    # The live TopHigh5 display ranks exactly like promotion (2026-10-02
    # management rule): equal points and engagement -> the earlier entry first.
    assert [r["contestant_id"] for r in rows_of(out)] == [entries[1][0].id, entries[2][0].id, entries[3][0].id,
                                                          entries[0][0].id]
    assert [r["stars_points"] for r in rows_of(out)] == [30, 30, 20, 10]
    assert [r["rank"] for r in rows_of(out)] == [1, 2, 3, 4]


def test_decision_reason_codes_never_contain_personal_data(db):
    rnd = make_round(db, date(TODAY.year, TODAY.month, 1))
    c, _ = phase5_entry(db, person(db, 15), contest(db), rnd, title=SECRET_TITLE)
    reasons = ps.participation_decision(db, c).reasons
    assert all(r.replace("_", "").isalnum() and r.isupper() for r in reasons)
    assert SECRET_TITLE not in json.dumps(reasons)


# ===========================================================================
# ADMIN CONTESTANT CREATION (Phase 8 final fix: A-K)
# ===========================================================================

from app.models.accounting import AuditTrail  # noqa: E402
from app.models.guardian import GuardianConsent, GuardianRelationship  # noqa: E402


def admin_scope(db, mode="participation", *, contests=1):
    rnd = make_round(db, _add_months(date(TODAY.year, TODAY.month, 1), -1))
    cts = [contest(db, mode=mode) for _ in range(contests)]
    # A new entry starts at its initial level: Country for nominations, City for participations.
    s = ContestSeason(round_id=rnd.id, title="Admin season",
                      level=SeasonLevel.COUNTRY if mode == "nomination" else SeasonLevel.CITY)
    db.add(s)
    db.flush()
    for ct in cts:
        db.add(ContestSeasonLink(contest_id=ct.id, season_id=s.id, is_active=True))
    db.commit()
    return cts, s


def admin_create(client, db, entrant, s, **extra):
    admin = person(db, 45, admin=True)
    body = {"user_id": entrant.id, "season_id": s.id, "title": extra.pop("title", "Admin-made entry"),
            "description": "d", **extra}
    return admin, client.post("/api/v1/admin/contestants", json=body, headers=auth(admin))


def created(db, r):
    assert r.status_code == 201, r.text
    c = db.query(Contestant).get(r.json()["id"])
    safety = db.query(ContestEntrySafety).filter(ContestEntrySafety.contestant_id == c.id).one()
    return c, safety


def test_admin_A_B_new_entry_gets_phase5_record_and_missing_dob_holds(client, db):
    cts, s = admin_scope(db)
    admin, r = admin_create(client, db, person(db, None), s)
    c, safety = created(db, r)
    assert safety.exposure_status == "HELD" and "AGE_REQUIRED" in safety.reason_codes      # B
    assert c.is_active is False and r.json()["public"] is False                            # A
    assert safety.submitted_by_user_id == c.user_id != admin.id                            # entrant, not admin
    assert not ps.participation_decision(db, c).eligible


def test_admin_C_guardian_consent_cannot_be_bypassed(client, db):
    cts, s = admin_scope(db)
    minor = person(db, 15)
    admin, r = admin_create(client, db, minor, s)
    c, safety = created(db, r)
    assert safety.exposure_status == "HELD" and "GUARDIAN_CONSENT_REQUIRED" in safety.reason_codes
    assert safety.guardian_relationship_id is None
    assert db.query(GuardianRelationship).filter(GuardianRelationship.minor_user_id == minor.id).count() == 0
    assert db.query(GuardianConsent).filter(GuardianConsent.minor_user_id == minor.id).count() == 0


def test_admin_D_nomination_claim_cannot_be_bypassed(client, db):
    cts, s = admin_scope(db, mode="nomination")
    admin, r = admin_create(client, db, person(db, 40), s)
    c, safety = created(db, r)
    assert safety.entry_kind == "NOMINATION" and c.entry_type == "nomination"
    assert safety.exposure_status == "HELD" and "NOMINEE_UNCLAIMED" in safety.reason_codes
    assert safety.nominee_user_id is None and safety.claim_token_hash is None   # no link handed to the admin
    assert "nominee_claim_token" not in r.text


def test_admin_E_F_content_moderation_still_applies_and_creation_is_not_approval(client, db):
    cts, s = admin_scope(db)
    admin, r = admin_create(client, db, person(db, 30), s, video_media_ids='["https://youtu.be/abc"]')
    c, safety = created(db, r)
    moderation = cs.moderation_for(db, c.id)
    assert moderation.state == "REVIEW_REQUIRED" and safety.exposure_status == "HELD"         # E
    assert "CONTENT_REVIEW_REQUIRED" in safety.reason_codes
    assert moderation.decided_by_user_id is None and moderation.automated_decision is False  # F
    approvals = db.query(AuditTrail).filter(AuditTrail.table_name == "content_moderation",
                                            AuditTrail.action.like("MODERATION_%")).count()
    assert approvals == 0
    assert db.query(AuditTrail).filter(AuditTrail.action == "ENTRY_CREATED_BY_ADMIN",
                                       AuditTrail.user_id == admin.id).count() == 1


def test_admin_created_eligible_adult_text_entry_follows_the_member_pipeline(client, db):
    """Not a blanket block: the same automated rules as a member's own submission."""
    cts, s = admin_scope(db)
    admin, r = admin_create(client, db, person(db, 30), s)
    c, safety = created(db, r)
    moderation = cs.moderation_for(db, c.id)
    assert safety.exposure_status == "PUBLIC" and c.is_active is True
    assert moderation.decided_by_user_id != admin.id   # automated classifier, never the admin


def test_admin_G_H_I_held_new_entry_not_votable_rankable_or_progressable(client, db):
    from app.api.api_v1.endpoints.season_migration import secure_top_high5_payload

    cts, s = admin_scope(db)
    admin, r = admin_create(client, db, person(db, None), s, title=SECRET_TITLE)
    c, safety = created(db, r)
    with pytest.raises(V):                                                          # G
        cast(db, person(db, 30), c, s_id=s.id, ct_id=cts[0].id)
    db.rollback()
    payload = {"contests": [{"contest_id": cts[0].id, "rows": [
        {"rank": 1, "contestant_id": c.id, "contestant_title": c.title}]}]}
    out = secure_top_high5_payload(db, None, payload)                               # H
    assert out["contests"] == [] and SECRET_TITLE not in json.dumps(out)
    dest = season(db, make_round(db, date(TODAY.year, TODAY.month, 1)), cts[0], SeasonLevel.COUNTRY)
    db.commit()
    assert not ps.gate_progression(db, c, to_season=dest, contest_id=cts[0].id)      # I
    db.commit()
    assert not active_in(db, c.id, dest.id)
    assert db.query(ProgressionSafetyHold).filter(ProgressionSafetyHold.contestant_id == c.id).count() == 1


def test_admin_J_genuine_historical_entries_keep_legacy_compatibility(db):
    legacy = gov(db, person(db, 30), legacy=True)
    assert db.query(ContestEntrySafety).filter(ContestEntrySafety.contestant_id == legacy.id).count() == 0
    assert ps.participation_decision(db, legacy).eligible
    assert cast(db, person(db, 30), legacy).id


def test_admin_K_failure_rolls_back_contestant_and_safety_state(client, db, monkeypatch):
    from app.api.api_v1.endpoints import admin as admin_endpoints

    cts, s = admin_scope(db)
    counts = lambda: (db.query(Contestant).count(), db.query(ContestEntrySafety).count(),  # noqa: E731
                      db.query(ContentModeration).count(), db.query(AgeSafetyEvent).count(),
                      db.query(AuditTrail).count(), db.query(ContestantSeason).count())
    before = counts()

    def boom(**kw):
        raise RuntimeError("synthetic failure after safety state")

    monkeypatch.setattr(admin_endpoints, "ContestantSeason", boom)
    admin, r = admin_create(client, db, person(db, 30), s, title="Doomed entry")
    assert r.status_code == 400
    db.expire_all()
    after = counts()
    # Only the admin user created by the helper exists additionally; no entry state at all.
    assert after == before
    assert db.query(Contestant).filter(Contestant.title == "Doomed entry").count() == 0


def test_admin_contest_must_be_identified_for_shared_seasons(client, db):
    cts, s = admin_scope(db, contests=2)
    entrant = person(db, 30)
    _, r = admin_create(client, db, entrant, s)
    assert r.status_code == 422 and db.query(Contestant).filter(Contestant.user_id == entrant.id).count() == 0
    other = contest(db)
    _, r = admin_create(client, db, entrant, s, contest_id=other.id)
    assert r.status_code == 422
    _, r = admin_create(client, db, entrant, s, contest_id=cts[1].id)
    c, safety = created(db, r)
    assert c.contest_id == safety.contest_id == cts[1].id


def test_admin_season_contests_endpoint_lists_only_valid_contests(client, db):
    cts, s = admin_scope(db, contests=2)
    deleted = contest(db)
    deleted.is_deleted = True
    db.add(ContestSeasonLink(contest_id=deleted.id, season_id=s.id, is_active=True))
    unrelated = contest(db)
    db.commit()
    admin = person(db, 45, admin=True)
    r = client.get(f"/api/v1/admin/seasons/{s.id}/contests", headers=auth(admin))
    assert r.status_code == 200
    assert sorted(c["id"] for c in r.json()) == sorted(c.id for c in cts)
    assert deleted.id not in {c["id"] for c in r.json()} and unrelated.id not in {c["id"] for c in r.json()}
    one_cts, one_s = admin_scope(db)
    assert [c["id"] for c in client.get(f"/api/v1/admin/seasons/{one_s.id}/contests",
                                        headers=auth(admin)).json()] == [one_cts[0].id]
    assert client.get(f"/api/v1/admin/seasons/{s.id}/contests", headers=auth(person(db, 30))).status_code == 403
    assert client.get("/api/v1/admin/seasons/999999/contests", headers=auth(admin)).status_code == 404


def test_admin_forged_or_deleted_contest_id_is_rejected_and_writes_nothing(client, db):
    cts, s = admin_scope(db, contests=2)
    deleted = contest(db)
    deleted.is_deleted = True
    db.add(ContestSeasonLink(contest_id=deleted.id, season_id=s.id, is_active=True))
    db.commit()
    entrant = person(db, 30)
    before = (db.query(Contestant).count(), db.query(ContestEntrySafety).count())
    for forged in (contest(db).id, deleted.id, 999999):
        _, r = admin_create(client, db, entrant, s, contest_id=forged)
        assert r.status_code == 422, r.text
    assert (db.query(Contestant).count(), db.query(ContestEntrySafety).count()) == before


def test_admin_chosen_contest_creates_safety_records_and_cannot_bypass(client, db):
    cts, s = admin_scope(db, contests=2)
    admin, r = admin_create(client, db, person(db, None), s, contest_id=cts[0].id, title=SECRET_TITLE)
    c, safety = created(db, r)
    assert c.contest_id == safety.contest_id == cts[0].id
    assert cs.moderation_for(db, c.id) is not None                       # Phase 6 record
    assert safety.exposure_status == "HELD" and c.is_active is False     # Phase 5 hold (no DOB)
    assert not ps.participation_decision(db, c).eligible
    with pytest.raises(V):
        cast(db, person(db, 30), c, s_id=s.id, ct_id=cts[0].id)
