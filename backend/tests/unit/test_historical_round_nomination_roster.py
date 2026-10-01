"""Historical round nomination roster: card count, detail roster and Vote-stage exclusion.

"Who was nominated in this round?" (Nominate tab / historical browse, Country only
inferred from filterCountry) and "who can be voted for at Country level right now?"
(Vote flow, contestLevel=country) are different datasets. Nominees promoted above
Country leave the second one only. Every user, entry and round here is SYNTHETIC.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from app import crud
from app.api.api_v1.endpoints.rounds import _cheap_round_entry_count
from app.crud.crud_contest import country_vote_stage_explicitly_requested
from app.models.contests import Contestant, ContestantSeason, ContestSeasonLink, SeasonLevel
from app.models.round import round_contests
from app.services.season_migration import SeasonMigrationService
from tests.unit.test_phase5_contest_eligibility import contest, person
from tests.unit.test_phase8_participation_safety import make_round, season

# Cohort months well in the past, like the reported production rounds.
MAY, JUNE, JULY, AUGUST = date(2026, 5, 1), date(2026, 6, 1), date(2026, 7, 1), date(2026, 8, 1)


@pytest.fixture(autouse=True)
def _quiet_prints(monkeypatch):
    import builtins

    monkeypatch.setattr(builtins, "print", lambda *a, **k: None)


def cohort_round(db, month: date):
    rnd = make_round(db, month)
    rnd.name = f"Round {month:%B %Y}"
    rnd.is_submission_open = False
    db.commit()
    return rnd


def link_round(db, rnd, ct):
    db.execute(round_contests.insert().values(round_id=rnd.id, contest_id=ct.id))
    db.commit()


def nominee(db, ct, rnd, *, k: int, country="Tanzania", origin="nomination"):
    user = person(db, 30, country=country)
    when = datetime.combine(rnd.submission_start_date, datetime.min.time()) + timedelta(days=9)
    c = Contestant(user_id=user.id, season_id=ct.id, contest_id=ct.id, round_id=rnd.id,
                   title=f"N{ct.id}-{rnd.id}-{k}", description="d", entry_type=origin,
                   city="Arusha", country=country, nominator_country=country,
                   region="East Africa", continent="Africa",
                   is_active=True, is_deleted=False, is_qualified=True,
                   registration_date=when, created_at=when)
    db.add(c)
    db.commit()
    return c


def member(db, c, s, *, active=True):
    db.add(ContestantSeason(contestant_id=c.id, season_id=s.id, is_active=active, joined_at=datetime(2026, 9, 1)))
    db.commit()


def promoted_cohort(db, month: date, *, top: SeasonLevel, tz=3, ke=1):
    """A cohort whose nominees ALL advanced above Country (the May/June/July shape):
    Country link deactivated, memberships inactive at every level but ``top``."""
    ct = contest(db, mode="nomination")
    rnd = cohort_round(db, month)
    link_round(db, rnd, ct)
    order = [SeasonLevel.COUNTRY, SeasonLevel.REGIONAL, SeasonLevel.CONTINENT, SeasonLevel.GLOBAL]
    stages = order[: order.index(top) + 1]
    seasons = {lvl: season(db, rnd, ct, lvl) for lvl in stages}
    for lvl in stages[:-1]:
        db.query(ContestSeasonLink).filter(ContestSeasonLink.season_id == seasons[lvl].id).update({"is_active": False})
    nominees = [nominee(db, ct, rnd, k=i) for i in range(tz)]
    nominees += [nominee(db, ct, rnd, k=10 + i, country="Kenya") for i in range(ke)]
    for c in nominees:
        for lvl in stages:
            member(db, c, seasons[lvl], active=(lvl == top))
    db.commit()
    return ct, rnd, nominees


def unpromoted_cohort(db, month: date, *, tz=1):
    """The August shape: Country season only, nobody promoted."""
    ct = contest(db, mode="nomination")
    rnd = cohort_round(db, month)
    link_round(db, rnd, ct)
    s = season(db, rnd, ct, SeasonLevel.COUNTRY)
    nominees = [nominee(db, ct, rnd, k=i) for i in range(tz)]
    for c in nominees:
        member(db, c, s)
    db.commit()
    return ct, rnd, nominees


def card_count(db, ct, rnd, *, country="Tanzania", level=None) -> int:
    return crud.contest.count_nomination_roster_for_card(
        db, contest_id=ct.id, current_user_id=None, filter_country=country,
        entry_type="nomination", round_id=rnd.id, requested_ui_level=level,
    )


def rounds_card(client, rnd, ct, **params) -> dict | None:
    query = {"roundId": rnd.id, "contestMode": "nomination", "contestLimit": 100, **params}
    resp = client.get("/api/v1/rounds/", params=query)
    assert resp.status_code == 200, resp.text
    for row in resp.json():
        for card in row.get("contests") or []:
            if card["id"] == ct.id:
                return card
    return None


# ---------------------------------------------------------------------------
# the semantic rule
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("country", True), ("Country", True), (" country ", True),
    (None, False), ("", False), ("regional", False), ("continental", False), ("global", False), ("city", False),
])
def test_exclusion_applies_only_to_an_explicit_country_stage(raw, expected):
    assert country_vote_stage_explicitly_requested(raw) is expected


# ---------------------------------------------------------------------------
# 1 + 2. fully promoted historical cohort
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("month,top", [
    (JULY, SeasonLevel.REGIONAL),      # July 2026: cohort now at Regional
    (JUNE, SeasonLevel.CONTINENT),     # June 2026: cohort now at Continental
    (MAY, SeasonLevel.GLOBAL),         # May 2026: cohort now at Global
])
def test_history_keeps_promoted_nominees_and_country_vote_excludes_them(db, month, top):
    ct, rnd, nominees = promoted_cohort(db, month, top=top, tz=3, ke=1)
    promoted = SeasonMigrationService.contestant_ids_active_beyond_level(db, ct.id, rnd.id, SeasonLevel.COUNTRY)
    assert promoted == {c.id for c in nominees}  # every nominee advanced

    # Nominate / historical browse: Country only inferred from filterCountry.
    assert card_count(db, ct, rnd, country="Tanzania") == 3
    assert card_count(db, ct, rnd, country="Kenya") == 1

    # Vote flow: explicit Country stage keeps hiding promoted nominees.
    assert card_count(db, ct, rnd, country="Tanzania", level="country") == 0


def test_rounds_endpoint_card_count_for_historical_round(client, db):
    ct, rnd, _ = promoted_cohort(db, JULY, top=SeasonLevel.REGIONAL, tz=3, ke=1)

    card = rounds_card(client, rnd, ct, filterCountry="Tanzania")
    assert card is not None
    assert card["participants_count"] == 3
    assert card["entries_count"] == 3
    assert card["level"] == "regional"  # stage badge is unchanged by this fix

    # A promoted contest is not listed on the Country Vote chip at all (unchanged).
    assert rounds_card(client, rnd, ct, filterCountry="Tanzania", contestLevel="country") is None


def test_cheap_sort_count_follows_the_same_rule(db):
    ct, rnd, _ = promoted_cohort(db, JULY, top=SeasonLevel.REGIONAL, tz=3, ke=1)
    # No ACTIVE pooled link, so the helper reaches its round/contest branch (the one
    # carrying the promoted-exclusion); memberships above Country stay active.
    db.query(ContestSeasonLink).filter(ContestSeasonLink.contest_id == ct.id).update({"is_active": False})
    db.commit()
    assert _cheap_round_entry_count(db, rnd, ct, "nomination", None) == 4
    assert _cheap_round_entry_count(db, rnd, ct, "nomination", "country") == 0


# ---------------------------------------------------------------------------
# 3. August-style cohort (not promoted yet): unchanged
# ---------------------------------------------------------------------------

def test_unpromoted_cohort_count_is_unchanged(client, db):
    ct, rnd, _ = unpromoted_cohort(db, AUGUST, tz=1)
    assert card_count(db, ct, rnd) == 1
    assert card_count(db, ct, rnd, level="country") == 1
    card = rounds_card(client, rnd, ct, filterCountry="Tanzania")
    assert card is not None and card["participants_count"] == 1 and card["level"] == "country"


def test_partially_promoted_cohort(db):
    """Winners advanced, others stayed at Country: history counts all, Country vote the rest."""
    ct = contest(db, mode="nomination")
    rnd = cohort_round(db, JULY)
    link_round(db, rnd, ct)
    country, regional = season(db, rnd, ct, SeasonLevel.COUNTRY), season(db, rnd, ct, SeasonLevel.REGIONAL)
    stayed, advanced = nominee(db, ct, rnd, k=1), nominee(db, ct, rnd, k=2)
    member(db, stayed, country)
    member(db, advanced, country, active=False)
    member(db, advanced, regional)

    assert card_count(db, ct, rnd) == 2
    assert card_count(db, ct, rnd, level="country") == 1


# ---------------------------------------------------------------------------
# 4. contest detail roster
# ---------------------------------------------------------------------------

def test_detail_roster_is_not_emptied_for_a_promoted_cohort(client, db):
    ct, rnd, nominees = promoted_cohort(db, JULY, top=SeasonLevel.REGIONAL, tz=3, ke=1)
    tz_ids = {c.id for c in nominees if c.country == "Tanzania"}

    resp = client.get(f"/api/v1/contests/{ct.id}",
                      params={"roundId": rnd.id, "entryType": "nomination", "filterCountry": "Tanzania"})
    assert resp.status_code == 200, resp.text
    assert {row["id"] for row in resp.json()["contestants"]} == tz_ids

    # Country Vote view of the same contest/round: promoted nominees stay hidden.
    vote = client.get(f"/api/v1/contests/{ct.id}",
                      params={"roundId": rnd.id, "entryType": "nomination", "filterCountry": "Tanzania",
                              "contestLevel": "country"})
    assert vote.status_code == 200, vote.text
    assert vote.json()["contestants"] == []


def test_detail_roster_stays_scoped_to_the_selected_round(client, db):
    """Another round's nominees of the same contest never leak into the selected round."""
    ct, july, _ = promoted_cohort(db, JULY, top=SeasonLevel.REGIONAL, tz=2, ke=0)
    june = cohort_round(db, JUNE)
    link_round(db, june, ct)
    other = nominee(db, ct, june, k=99)

    assert card_count(db, ct, july) == 2
    assert card_count(db, ct, june) == 1
    resp = client.get(f"/api/v1/contests/{ct.id}",
                      params={"roundId": july.id, "entryType": "nomination", "filterCountry": "Tanzania"})
    assert other.id not in {row["id"] for row in resp.json()["contestants"]}


# ---------------------------------------------------------------------------
# 5. open round with zero nominations
# ---------------------------------------------------------------------------

def test_open_round_with_no_nominations_is_zero(client, db):
    today = date.today()
    ct = contest(db, mode="nomination")
    rnd = make_round(db, date(today.year, today.month, 1))
    rnd.name = f"Round {today:%B %Y}"
    rnd.is_submission_open = True
    db.commit()
    link_round(db, rnd, ct)

    assert card_count(db, ct, rnd) == 0
    card = rounds_card(client, rnd, ct, filterCountry="Tanzania")
    assert card is not None and card["participants_count"] == 0


# ---------------------------------------------------------------------------
# 6. participations flow: unchanged
# ---------------------------------------------------------------------------

def test_participation_card_count_is_unchanged(client, db):
    ct = contest(db, mode="participation")
    rnd = cohort_round(db, JULY)
    link_round(db, rnd, ct)
    city = season(db, rnd, ct, SeasonLevel.CITY)
    for k in range(2):
        member(db, nominee(db, ct, rnd, k=k, origin="participation"), city)

    assert _cheap_round_entry_count(db, rnd, ct, "participation", None) == 2
    resp = client.get("/api/v1/rounds/", params={"roundId": rnd.id, "contestMode": "participation",
                                                 "filterCountry": "Tanzania", "contestLimit": 100})
    assert resp.status_code == 200, resp.text
    cards = [c for row in resp.json() for c in (row.get("contests") or []) if c["id"] == ct.id]
    assert cards and cards[0]["participants_count"] == 2
