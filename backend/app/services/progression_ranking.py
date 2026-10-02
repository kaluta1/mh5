"""Canonical MyHigh5 ranking for stage progression and Top High5.

Management-confirmed rule (2026-10-02):

* A voter ranks up to five creatives; positions 1..5 earn 5..1 voting points
  (``voting_ranking.points_for_position``).
* Creatives are ranked by TOTAL VOTING POINTS, never by raw vote count.
* Voting points are CUMULATIVE across phases: the score a creative competes
  with at a stage is everything earned in the completed previous stages of the
  same cohort plus the points earned in that stage.
* Equal points are separated, in this exact order, by shares, likes, comments,
  views, then the earlier submission. The entry id is only the last, purely
  technical, fallback that keeps the order stable.
* A creative needs no vote to be ranked. The top five of each competition
  group advance; fewer than five means all of them, one means that one.

How the cumulative score is derived (no schema, no copied votes)
----------------------------------------------------------------
An entry's cohort round is fixed at submission and never changes, and every
level of that round has its own ``ContestSeason``. Each vote row already
records the season it was cast in. The points of one stage are therefore the
entry's vote rows in that cohort's season for that level, and the cumulative
score is the sum over the cohort's seasons from the first level up to the
stage being ranked. Vote rows are only read: they keep their voter, season,
position and timestamp, and nothing is written to the destination season.
Votes sitting in a season of another round are not part of the cohort and are
never counted.

Engagement is the entry's own shares/likes/comments/views from the tables the
rest of the application already counts (``voting_ranking``), up to the close of
the stage being ranked, so a late retry ranks exactly like an on-time run.
Engagement only breaks ties; it is never turned into voting points.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Dict, Iterable, List, Optional, Sequence

from sqlalchemy.orm import Session

from app.models.contest import Contest
from app.models.contests import Contestant, ContestSeason, SeasonLevel
from app.models.round import Round
from app.services.voting_ranking import entry_engagement, points_by_season

LEVEL_ORDER: List[SeasonLevel] = [
    SeasonLevel.CITY,
    SeasonLevel.COUNTRY,
    SeasonLevel.REGIONAL,
    SeasonLevel.CONTINENT,
    SeasonLevel.GLOBAL,
]

# Lower bound for "the entry's whole life"; engagement tables hold nothing older.
_ENGAGEMENT_EPOCH = datetime(2000, 1, 1)

_PARTICIPATION_END_ATTR = {
    SeasonLevel.CITY: "city_season_end_date",
    SeasonLevel.COUNTRY: "country_season_end_date",
    SeasonLevel.REGIONAL: "regional_end_date",
    SeasonLevel.CONTINENT: "continental_end_date",
    SeasonLevel.GLOBAL: "global_end_date",
}


@dataclass(frozen=True)
class ProgressionScore:
    """One entry's auditable score at one stage."""

    contestant_id: int
    stage_level: str
    carried_points: int = 0      # A. completed previous stages
    stage_points: int = 0        # B. the stage being ranked
    cumulative_points: int = 0   # C. A + B, the ranking score
    stage_votes: int = 0
    cumulative_votes: int = 0
    points_by_level: Dict[str, int] = field(default_factory=dict)
    shares: int = 0
    likes: int = 0
    comments: int = 0
    views: int = 0
    submitted_at: Optional[datetime] = None
    rank: int = 0

    # RankingRow-compatible names, so existing consumers read the cumulative score.
    @property
    def total_points(self) -> int:
        return self.cumulative_points

    @property
    def total_votes(self) -> int:
        return self.cumulative_votes


def level_of(value) -> SeasonLevel:
    return value if isinstance(value, SeasonLevel) else SeasonLevel(str(value).lower())


def levels_through(level: SeasonLevel) -> List[SeasonLevel]:
    """The stages whose points count at ``level``: first level up to it."""
    return LEVEL_ORDER[: LEVEL_ORDER.index(level_of(level)) + 1]


def progression_sort_key(score: ProgressionScore) -> tuple:
    """points, shares, likes, comments, views (all descending), earlier
    submission, then the entry id as the deterministic last resort."""
    return (
        -int(score.cumulative_points),
        -int(score.shares),
        -int(score.likes),
        -int(score.comments),
        -int(score.views),
        score.submitted_at or datetime.max,
        int(score.contestant_id),
    )


def submission_time(contestant: Contestant) -> Optional[datetime]:
    """Canonical submission timestamp: registration_date, the field stamped at
    submission/nomination and shown in the UI, with created_at as fallback."""
    return getattr(contestant, "registration_date", None) or getattr(contestant, "created_at", None)


def stage_close_at(round_obj: Optional[Round], level: SeasonLevel, contest_mode: Optional[str]) -> Optional[datetime]:
    """Last instant of the stage's voting window (inclusive end day), or None."""
    if round_obj is None:
        return None
    level = level_of(level)
    if (contest_mode or "").strip().lower() == "nomination":
        from app.services.season_migration import SeasonMigrationService

        close = SeasonMigrationService._nomination_vote_close_date_for_level(round_obj, level)
    else:
        close = getattr(round_obj, _PARTICIPATION_END_ATTR[level], None)
    if close is None:
        return None
    if isinstance(close, datetime):
        close = close.date()
    return datetime.combine(close, time.max) if isinstance(close, date) else None


def cohort_season_ids_by_level(db: Session, round_id: int, through: SeasonLevel) -> Dict[SeasonLevel, List[int]]:
    """Season ids of one cohort round, per level, for the levels that count at ``through``."""
    wanted = levels_through(through)
    rows = (
        db.query(ContestSeason.id, ContestSeason.level)
        .filter(
            ContestSeason.round_id == round_id,
            ContestSeason.is_deleted == False,  # noqa: E712
            ContestSeason.level.in_(wanted),
        )
        .order_by(ContestSeason.id.asc())
        .all()
    )
    by_level: Dict[SeasonLevel, List[int]] = {lvl: [] for lvl in wanted}
    for season_id, level in rows:
        by_level[level_of(level)].append(int(season_id))
    return by_level


def score_candidates(
    db: Session,
    *,
    contest: Contest,
    round_obj: Optional[Round],
    level: SeasonLevel,
    contestants: Sequence[Contestant],
    bucket_key: Optional[str] = None,
    engagement_end_at: Optional[datetime] = None,
) -> Dict[int, ProgressionScore]:
    """Score every given entry at ``level`` of its cohort. Read-only.

    Every entry gets a score, voted or not. ``rank`` is left at 0: ranks only
    exist inside a competition group (see ``rank_group``).
    """
    level = level_of(level)
    by_id = {int(c.id): c for c in contestants if c.id is not None}
    ids = sorted(by_id)
    if not ids:
        return {}
    if bucket_key is None:
        from app.services.season_migration import SeasonMigrationService

        bucket_key = SeasonMigrationService._top_high5_bucket_key_for_contest(contest)

    points: Dict[int, Dict[str, int]] = {cid: {} for cid in ids}
    votes: Dict[int, Dict[str, int]] = {cid: {} for cid in ids}
    if round_obj is not None:
        seasons = cohort_season_ids_by_level(db, int(round_obj.id), level)
        level_of_season = {
            season_id: stage_level.value
            for stage_level, season_ids in seasons.items()
            for season_id in season_ids
        }
        per_season = points_by_season(
            db,
            season_ids=list(level_of_season),
            contestant_ids=ids,
            contest_id=int(contest.id),
            bucket_key=bucket_key,
        )
        for cid, by_season in per_season.items():
            for season_id, (season_points, season_votes) in by_season.items():
                stage = level_of_season[season_id]
                points[cid][stage] = points[cid].get(stage, 0) + season_points
                votes[cid][stage] = votes[cid].get(stage, 0) + season_votes

    if engagement_end_at is None:
        engagement_end_at = stage_close_at(round_obj, level, getattr(contest, "contest_mode", None))
    engagement = entry_engagement(
        db, ids, start_at=_ENGAGEMENT_EPOCH, end_at=engagement_end_at or datetime.utcnow()
    )

    scores: Dict[int, ProgressionScore] = {}
    for cid in ids:
        per_level = {lvl.value: points[cid].get(lvl.value, 0) for lvl in levels_through(level)}
        stage_points = per_level.get(level.value, 0)
        cumulative = sum(per_level.values())
        stage_votes = votes[cid].get(level.value, 0)
        metrics = engagement.get(cid, {})
        scores[cid] = ProgressionScore(
            contestant_id=cid,
            stage_level=level.value,
            carried_points=cumulative - stage_points,
            stage_points=stage_points,
            cumulative_points=cumulative,
            stage_votes=stage_votes,
            cumulative_votes=sum(votes[cid].values()),
            points_by_level=per_level,
            shares=int(metrics.get("shares", 0)),
            likes=int(metrics.get("likes", 0)),
            comments=int(metrics.get("comments", 0)),
            views=int(metrics.get("views", 0)),
            submitted_at=submission_time(by_id[cid]),
        )
    return scores


def rank_group(
    members: Iterable[Contestant],
    scores: Dict[int, ProgressionScore],
    *,
    one_per_nominator: bool = True,
) -> List[Contestant]:
    """Order one competition group by the canonical rule.

    ``one_per_nominator`` keeps only the best-ranked entry of each submitting
    user (the nominator, for nominations), so one person never takes two of a
    group's winner slots. The order of the kept entries is never changed.
    """
    ordered = sorted(
        (c for c in members if c.id is not None and int(c.id) in scores),
        key=lambda c: progression_sort_key(scores[int(c.id)]),
    )
    if not one_per_nominator:
        return ordered
    seen: set = set()
    kept: List[Contestant] = []
    for candidate in ordered:
        user_id = getattr(candidate, "user_id", None)
        if user_id is not None:
            if user_id in seen:
                continue
            seen.add(user_id)
        kept.append(candidate)
    return kept
