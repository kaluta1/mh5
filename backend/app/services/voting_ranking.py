"""Canonical voting write and ranking compatibility service.

Production has two generations of vote facts:

* ``votes`` is the immutable historical/stage ledger.
* ``contestant_voting`` is the contextual MyHigh5 ledger used by the current UI.

New MyHigh5 writes go only to ``contestant_voting``.  Rankings are calculated
through this module so historical stage votes remain visible without copying or
rewriting them.  Scope is always supplied explicitly; there is no current-date
or contest-only fallback here.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Sequence

from sqlalchemy import and_, func, literal, or_, select, union_all
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.comment import Comment
from app.models.contest import Contest
from app.models.contests import ContestStage, Contestant
from app.models.user import User
from app.models.voting import (
    ContestComment,
    ContestLike,
    ContestantReaction,
    ContestantShare,
    ContestantVoting,
    PageView,
    Vote,
    VoteStatus,
)


MAX_MYHIGH5_VOTES = 5


class VotingConflict(Exception):
    """A stable, user-facing voting rule conflict."""

    def __init__(self, code: str, message: str, *, payload: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.payload = payload or {}


class VotingValidationError(Exception):
    """The requested vote mutation does not match the authoritative scope."""


@dataclass(frozen=True)
class RankingRow:
    contestant_id: int
    total_points: int = 0
    total_votes: int = 0
    shares: int = 0
    likes: int = 0
    comments: int = 0
    views: int = 0
    rank: int = 0


def points_for_position(position: int) -> int:
    """Server-owned MyHigh5 scoring: positions 1..5 receive 5..1 points."""
    if position < 1 or position > MAX_MYHIGH5_VOTES:
        raise VotingValidationError("MyHigh5 position must be between 1 and 5.")
    return (MAX_MYHIGH5_VOTES + 1) - position


def ranking_sort_key(row: RankingRow) -> tuple[int, ...]:
    """Product winner rule, including the final stable ID tie-break."""
    return (
        -int(row.total_points),
        -int(row.shares),
        -int(row.likes),
        -int(row.comments),
        -int(row.views),
        int(row.contestant_id),
    )


def rank_rows(rows: Iterable[RankingRow], *, limit: int | None = None) -> list[RankingRow]:
    """Return ordinal ranks. Equal metrics do not share a rank; lower ID wins."""
    ordered = sorted(rows, key=ranking_sort_key)
    if limit is not None:
        ordered = ordered[: max(0, limit)]
    return [
        RankingRow(
            contestant_id=row.contestant_id,
            total_points=row.total_points,
            total_votes=row.total_votes,
            shares=row.shares,
            likes=row.likes,
            comments=row.comments,
            views=row.views,
            rank=index,
        )
        for index, row in enumerate(ordered, start=1)
    ]


def _lock_voter(db: Session, voter_id: int) -> None:
    """Serialize all MyHigh5 mutations for one voter on PostgreSQL."""
    row = (
        db.query(User.id)
        .filter(User.id == voter_id)
        .with_for_update()
        .one_or_none()
    )
    if row is None:
        raise VotingValidationError("Voter does not exist.")


def _scope_query(
    db: Session,
    *,
    voter_id: int,
    season_id: int,
    contest_id: int,
    bucket_key: str,
):
    # MyHigh5 is category-scoped. New rows carry a durable bucket key; NULL
    # compatibility rows are accepted only for the exact contest that created
    # them. Season remains mandatory so periods never bleed into each other.
    query = db.query(ContestantVoting).filter(
        ContestantVoting.user_id == voter_id,
        ContestantVoting.season_id == season_id,
    )
    return query.filter(
        or_(
            ContestantVoting.vote_bucket_key == bucket_key,
            and_(
                ContestantVoting.vote_bucket_key.is_(None),
                ContestantVoting.contest_id == contest_id,
            ),
        )
    )


def _ordered_scope_votes(query) -> list[ContestantVoting]:
    return query.order_by(
        ContestantVoting.position.asc().nullslast(),
        ContestantVoting.vote_date.asc(),
        ContestantVoting.id.asc(),
    ).all()


def _ensure_no_nominator_duplicate(
    db: Session,
    *,
    scope_query,
    nominator_user_id: int,
    exclude_contestant_id: int | None = None,
) -> None:
    query = scope_query.join(
        Contestant, Contestant.id == ContestantVoting.contestant_id
    ).filter(Contestant.user_id == nominator_user_id)
    if exclude_contestant_id is not None:
        query = query.filter(ContestantVoting.contestant_id != exclude_contestant_id)
    if query.first() is not None:
        raise VotingConflict(
            "already_voted",
            "You have already voted for this nominator in this category.",
        )


def cast_myhigh5_vote(
    db: Session,
    *,
    voter_id: int,
    contestant_id: int,
    nominator_user_id: int,
    season_id: int,
    contest_id: int,
    bucket_key: str,
) -> ContestantVoting:
    """Create one contextual MyHigh5 vote without committing the transaction."""
    _lock_voter(db, voter_id)
    scope = _scope_query(
        db,
        voter_id=voter_id,
        season_id=season_id,
        contest_id=contest_id,
        bucket_key=bucket_key,
    )

    duplicate = db.query(ContestantVoting.id).filter(
        ContestantVoting.user_id == voter_id,
        ContestantVoting.contestant_id == contestant_id,
        ContestantVoting.season_id == season_id,
    ).first()
    if duplicate is not None:
        raise VotingConflict(
            "already_voted",
            "You have already voted for this contestant in this season.",
        )

    _ensure_no_nominator_duplicate(
        db,
        scope_query=scope,
        nominator_user_id=nominator_user_id,
    )
    current = _ordered_scope_votes(scope)
    if len(current) >= MAX_MYHIGH5_VOTES:
        fifth = current[MAX_MYHIGH5_VOTES - 1]
        raise VotingConflict(
            "max_votes_reached",
            "You already have 5 votes in this category.",
            payload={
                "replaced_contestant": {
                    "id": fifth.contestant_id,
                    "position": MAX_MYHIGH5_VOTES,
                },
                "current_votes_count": len(current),
            },
        )

    position = len(current) + 1
    vote = ContestantVoting(
        user_id=voter_id,
        contestant_id=contestant_id,
        contest_id=contest_id,
        season_id=season_id,
        vote_bucket_key=bucket_key,
        position=position,
        points=points_for_position(position),
    )
    try:
        with db.begin_nested():
            db.add(vote)
            db.flush()
    except IntegrityError as exc:
        raise VotingConflict(
            "already_voted",
            "You have already voted for this contestant in this season.",
        ) from exc
    return vote


def replace_fifth_myhigh5_vote(
    db: Session,
    *,
    voter_id: int,
    contestant_id: int,
    nominator_user_id: int,
    season_id: int,
    contest_id: int,
    bucket_key: str,
) -> tuple[ContestantVoting, int]:
    """Atomically replace position five; caller owns commit/rollback."""
    _lock_voter(db, voter_id)
    scope = _scope_query(
        db,
        voter_id=voter_id,
        season_id=season_id,
        contest_id=contest_id,
        bucket_key=bucket_key,
    )
    current = _ordered_scope_votes(scope)
    if len(current) < MAX_MYHIGH5_VOTES:
        raise VotingValidationError(
            "You have less than 5 votes. Use the regular vote endpoint."
        )
    if db.query(ContestantVoting.id).filter(
        ContestantVoting.user_id == voter_id,
        ContestantVoting.contestant_id == contestant_id,
        ContestantVoting.season_id == season_id,
    ).first() is not None:
        raise VotingConflict("already_voted", "You have already voted for this contestant.")

    removed = current[MAX_MYHIGH5_VOTES - 1]
    _ensure_no_nominator_duplicate(
        db,
        scope_query=scope,
        nominator_user_id=nominator_user_id,
        exclude_contestant_id=removed.contestant_id,
    )
    removed_contestant_id = int(removed.contestant_id)
    db.delete(removed)
    db.flush()

    vote = ContestantVoting(
        user_id=voter_id,
        contestant_id=contestant_id,
        contest_id=contest_id,
        season_id=season_id,
        vote_bucket_key=bucket_key,
        position=MAX_MYHIGH5_VOTES,
        points=points_for_position(MAX_MYHIGH5_VOTES),
    )
    try:
        with db.begin_nested():
            db.add(vote)
            db.flush()
    except IntegrityError as exc:
        raise VotingConflict(
            "already_voted", "You have already voted for this contestant."
        ) from exc
    return vote, removed_contestant_id


def reorder_myhigh5_votes(
    db: Session,
    *,
    voter_id: int,
    season_id: int,
    contest_id: int,
    bucket_key: str,
    ordered_contestant_ids: Sequence[int],
) -> list[ContestantVoting]:
    """Reorder the complete scoped set and recalculate every point server-side."""
    _lock_voter(db, voter_id)
    requested = [int(value) for value in ordered_contestant_ids]
    if not requested or len(requested) > MAX_MYHIGH5_VOTES:
        raise VotingValidationError("Between 1 and 5 votes must be supplied.")
    if len(set(requested)) != len(requested):
        raise VotingValidationError("A contestant can appear only once in a reorder.")

    current = _ordered_scope_votes(
        _scope_query(
            db,
            voter_id=voter_id,
            season_id=season_id,
            contest_id=contest_id,
            bucket_key=bucket_key,
        )
    )
    current_by_id = {int(vote.contestant_id): vote for vote in current}
    if set(current_by_id) != set(requested):
        raise VotingValidationError(
            "Reorder must contain exactly the current contest/season/category votes."
        )

    result = []
    for position, contestant_id in enumerate(requested, start=1):
        vote = current_by_id[contestant_id]
        vote.position = position
        vote.points = points_for_position(position)
        result.append(vote)
    db.flush()
    return result


def _engagement(
    db: Session,
    contestant_ids: list[int],
    *,
    start_at: datetime | None,
    end_at: datetime | None,
) -> dict[int, dict[str, int]]:
    if not contestant_ids:
        return {}

    # Engagement rows have no contest/season/stage foreign key. Without an
    # explicit, validated time window, lifetime values would contaminate a
    # monthly ranking, so they are deliberately neutral.
    if start_at is None or end_at is None:
        return {
            contestant_id: {
                "shares": 0,
                "likes": 0,
                "comments": 0,
                "views": 0,
            }
            for contestant_id in contestant_ids
        }

    def metric_rows(model, timestamp_column, metric: str, *filters):
        values = {
            "shares": (1, 0, 0, 0),
            "likes": (0, 1, 0, 0),
            "comments": (0, 0, 1, 0),
            "views": (0, 0, 0, 1),
        }[metric]
        return select(
            model.contestant_id.label("contestant_id"),
            literal(values[0]).label("shares"),
            literal(values[1]).label("likes"),
            literal(values[2]).label("comments"),
            literal(values[3]).label("views"),
        ).where(
            model.contestant_id.in_(contestant_ids),
            timestamp_column >= start_at,
            timestamp_column <= end_at,
            *filters,
        )

    # One UNION ALL aggregation replaces six independent round trips over the
    # largest engagement tables. Each branch remains independently indexable.
    engagement_events = union_all(
        metric_rows(ContestantShare, ContestantShare.created_at, "shares"),
        metric_rows(ContestLike, ContestLike.created_at, "likes"),
        metric_rows(
            ContestantReaction,
            ContestantReaction.created_at,
            "likes",
            ContestantReaction.reaction_type.in_(["like", "love", "wow"]),
        ),
        metric_rows(ContestComment, ContestComment.created_at, "comments"),
        metric_rows(
            Comment,
            Comment.created_at,
            "comments",
            Comment.is_hidden == False,
            Comment.is_deleted == False,
        ),
        metric_rows(PageView, PageView.viewed_at, "views"),
    ).subquery("engagement_events")
    metric_totals = {
        int(row.contestant_id): {
            "shares": int(row.shares or 0),
            "likes": int(row.likes or 0),
            "comments": int(row.comments or 0),
            "views": int(row.views or 0),
        }
        for row in db.execute(
            select(
                engagement_events.c.contestant_id,
                func.sum(engagement_events.c.shares).label("shares"),
                func.sum(engagement_events.c.likes).label("likes"),
                func.sum(engagement_events.c.comments).label("comments"),
                func.sum(engagement_events.c.views).label("views"),
            ).group_by(engagement_events.c.contestant_id)
        ).all()
    }

    return {
        contestant_id: {
            **metric_totals.get(
                contestant_id,
                {"shares": 0, "likes": 0, "comments": 0, "views": 0},
            ),
        }
        for contestant_id in contestant_ids
    }


def aggregate_rankings(
    db: Session,
    *,
    season_ids: Sequence[int],
    contestant_ids: Sequence[int],
    contest_id: int | None = None,
    bucket_key: str | None = None,
    stage_ids: Sequence[int] | None = None,
    engagement_start_at: datetime | None = None,
    engagement_end_at: datetime | None = None,
    require_votes: bool = False,
    limit: int | None = None,
) -> list[RankingRow]:
    """Rank one explicit scope across historical and current vote generations.

    Historical ``votes`` are scoped through ``stage_id -> contest_stages.season_id``.
    For a contest-specific ranking they are included only when the season and
    round resolve to that single contest. Ambiguous historical rows are never
    assigned merely because their contestant appears in a caller-supplied
    roster. Current MyHigh5 rows are scoped directly by season and contest/bucket.
    """
    seasons = sorted({int(value) for value in season_ids})
    candidates = sorted({int(value) for value in contestant_ids})
    if not seasons or not candidates:
        return []

    historical_seasons = seasons
    if contest_id is not None:
        from app.services.contest_context import contest_context_service

        historical_seasons = list(
            contest_context_service.exact_historical_season_ids_for_contest(
                db, season_ids=seasons, contest_id=int(contest_id)
            )
        )

    historical = db.query(
        Vote.contestant_id,
        func.coalesce(func.sum(Vote.points), 0).label("points"),
        func.count(Vote.id).label("votes"),
    ).join(ContestStage, ContestStage.id == Vote.stage_id).filter(
        ContestStage.season_id.in_(historical_seasons),
        Vote.status == VoteStatus.ACTIVE,
        Vote.contestant_id.in_(candidates),
    )
    if stage_ids is not None:
        stages = sorted({int(value) for value in stage_ids})
        if not stages:
            return []
        historical = historical.filter(Vote.stage_id.in_(stages))
    historical_rows = historical.group_by(Vote.contestant_id).all()

    current = db.query(
        ContestantVoting.contestant_id,
        func.coalesce(func.sum(ContestantVoting.points), 0).label("points"),
        func.count(ContestantVoting.id).label("votes"),
    ).filter(
        ContestantVoting.season_id.in_(seasons),
        ContestantVoting.contestant_id.in_(candidates),
    )
    if contest_id is not None:
        if bucket_key:
            current = current.filter(
                or_(
                    ContestantVoting.vote_bucket_key == bucket_key,
                    and_(
                        ContestantVoting.vote_bucket_key.is_(None),
                        ContestantVoting.contest_id == contest_id,
                    ),
                )
            )
        else:
            current = current.filter(ContestantVoting.contest_id == contest_id)
    current_rows = current.group_by(ContestantVoting.contestant_id).all()

    totals = {contestant_id: [0, 0] for contestant_id in candidates}
    for row in [*historical_rows, *current_rows]:
        totals[int(row.contestant_id)][0] += int(row.points or 0)
        totals[int(row.contestant_id)][1] += int(row.votes or 0)

    engagement = _engagement(
        db,
        candidates,
        start_at=engagement_start_at,
        end_at=engagement_end_at,
    )
    rows = [
        RankingRow(
            contestant_id=contestant_id,
            total_points=totals[contestant_id][0],
            total_votes=totals[contestant_id][1],
            shares=engagement.get(contestant_id, {}).get("shares", 0),
            likes=engagement.get(contestant_id, {}).get("likes", 0),
            comments=engagement.get(contestant_id, {}).get("comments", 0),
            views=engagement.get(contestant_id, {}).get("views", 0),
        )
        for contestant_id in candidates
        if not require_votes or totals[contestant_id][1] > 0
    ]
    return rank_rows(rows, limit=limit)


def ranking_map(rows: Iterable[RankingRow]) -> dict[int, RankingRow]:
    return {row.contestant_id: row for row in rows}


def lifetime_vote_counts(
    db: Session, contestant_ids: Sequence[int]
) -> dict[int, int]:
    """Compatibility totals for non-ranking profile/list displays only."""
    candidates = sorted({int(value) for value in contestant_ids})
    if not candidates:
        return {}
    totals = {contestant_id: 0 for contestant_id in candidates}
    historical = db.query(
        Vote.contestant_id, func.count(Vote.id).label("votes")
    ).filter(
        Vote.status == VoteStatus.ACTIVE,
        Vote.contestant_id.in_(candidates),
    ).group_by(Vote.contestant_id).all()
    current = db.query(
        ContestantVoting.contestant_id,
        func.count(ContestantVoting.id).label("votes"),
    ).filter(
        ContestantVoting.contestant_id.in_(candidates)
    ).group_by(ContestantVoting.contestant_id).all()
    for row in [*historical, *current]:
        totals[int(row.contestant_id)] += int(row.votes or 0)
    return totals


def bucket_key_for_contest(contest: Contest) -> str:
    if contest.category_id is not None:
        return f"cat:{contest.category_id}"
    return f"ty:{(contest.contest_type or '').strip().lower()}:{(contest.contest_mode or '').strip().lower()}"


def invalidate_ranking_cache(*, season_id: int, contest_id: int) -> None:
    """Best-effort invalidation; correctness never relies on Redis."""
    try:
        from app.core.cache import cache_service

        cache_service.delete_pattern(
            f"cache:ranking:season:{int(season_id)}:contest:{int(contest_id)}:*"
        )
        cache_service.invalidate_contest(int(contest_id))
    except Exception:
        # Redis is optional and ranking endpoints compute from the database.
        return
