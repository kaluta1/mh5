"""Deterministic contest-period and historical vote context resolution.

The live schema models a period as a contest participating in a round, a
season for that round/level, and a stage inside that season. No component may
silently substitute another active/current row when one of those identifiers
is ambiguous.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import Iterable, Sequence

from sqlalchemy import bindparam, inspect, text
from sqlalchemy.orm import Session

from app.models.contest import Contest, ContestEntry
from app.models.contests import (
    ContestSeason,
    ContestSeasonLink,
    ContestStage,
    Contestant,
    ContestantSeason,
    SeasonLevel,
)
from app.models.round import Round, RoundStatus, round_contests
from app.models.voting import ContestantVoting, Vote


class ContestContextError(RuntimeError):
    pass


class ContestContextNotFound(ContestContextError):
    pass


class AmbiguousContestContext(ContestContextError):
    def __init__(self, message: str, *, candidate_ids: Sequence[int] = ()):
        super().__init__(message)
        self.candidate_ids = tuple(sorted({int(value) for value in candidate_ids}))


class AttributionClass(str, Enum):
    EXACT = "EXACT"
    STRONG = "STRONG"
    AMBIGUOUS = "AMBIGUOUS"
    ORPHANED_INVALID = "ORPHANED_INVALID"


@dataclass(frozen=True)
class ContestPeriodContext:
    contest_id: int
    round_id: int
    season_id: int
    stage_id: int
    category_key: str
    period_start: datetime
    period_end: datetime


@dataclass(frozen=True)
class HistoricalVoteAttribution:
    vote_id: int
    classification: AttributionClass
    stage_id: int | None
    season_id: int | None
    round_id: int | None
    contest_id: int | None
    candidate_contest_ids: tuple[int, ...]
    evidence: tuple[str, ...]


@dataclass(frozen=True)
class RosterResolution:
    contestant_ids: tuple[int, ...]
    evidence: str


def category_identity(contest: Contest) -> str:
    if contest.category_id is not None:
        return f"cat:{int(contest.category_id)}"
    contest_type = (contest.contest_type or "").strip().lower()
    contest_mode = (contest.contest_mode or "").strip().lower()
    return f"type:{contest_type}:mode:{contest_mode}"


def month_start(value: date) -> date:
    return date(value.year, value.month, 1)


def add_months(value: date, months: int) -> date:
    raw_month = value.month - 1 + months
    year = value.year + raw_month // 12
    month = raw_month % 12 + 1
    return date(year, month, min(value.day, calendar.monthrange(year, month)[1]))


class ContestContextService:
    """Read-time authority for contest, period, stage, category, and roster."""

    LEVEL_COHORT_OFFSETS = {
        SeasonLevel.CITY: -1,
        SeasonLevel.COUNTRY: -1,
        SeasonLevel.REGIONAL: -2,
        SeasonLevel.CONTINENT: -3,
        SeasonLevel.GLOBAL: -4,
    }

    @staticmethod
    def _unique(rows: Sequence, description: str):
        if not rows:
            raise ContestContextNotFound(f"No {description} exists.")
        if len(rows) > 1:
            raise AmbiguousContestContext(
                f"Multiple {description} records exist; explicit repair is required.",
                candidate_ids=[row.id for row in rows],
            )
        return rows[0]

    @classmethod
    def resolve_submission_round(cls, db: Session, period: date) -> Round:
        target = month_start(period)
        rows = (
            db.query(Round)
            .filter(
                Round.submission_start_date == target,
                Round.status != RoundStatus.CANCELLED,
            )
            .order_by(Round.id.asc())
            .all()
        )
        return cls._unique(rows, f"non-cancelled submission round for {target.isoformat()}")

    @classmethod
    def resolve_current_submission_round(
        cls, db: Session, *, today: date | None = None
    ) -> Round:
        return cls.resolve_submission_round(db, today or date.today())

    @classmethod
    def resolve_vote_round(
        cls,
        db: Session,
        level: SeasonLevel,
        *,
        today: date | None = None,
    ) -> Round:
        today = today or date.today()
        if level not in cls.LEVEL_COHORT_OFFSETS:
            raise ContestContextError(f"No nomination cohort rule for level {level.value}.")
        cohort_month = add_months(month_start(today), cls.LEVEL_COHORT_OFFSETS[level])
        return cls.resolve_submission_round(db, cohort_month)

    @staticmethod
    def resolve_round_by_id(db: Session, round_id: int) -> Round:
        row = db.query(Round).filter(Round.id == int(round_id)).one_or_none()
        if row is None:
            raise ContestContextNotFound(f"Round id={round_id} does not exist.")
        if row.status == RoundStatus.CANCELLED:
            raise ContestContextError(f"Round id={round_id} is cancelled.")
        return row

    @classmethod
    def resolve_contest_season(
        cls,
        db: Session,
        *,
        contest_id: int,
        round_id: int,
        level: SeasonLevel,
        active_only: bool = True,
    ) -> ContestSeason:
        """Resolve one explicit contest/round/level season or reject ambiguity."""
        query = (
            db.query(ContestSeason)
            .join(
                ContestSeasonLink,
                ContestSeasonLink.season_id == ContestSeason.id,
            )
            .filter(
                ContestSeasonLink.contest_id == int(contest_id),
                ContestSeason.round_id == int(round_id),
                ContestSeason.level == level,
                ContestSeason.is_deleted == False,
            )
        )
        if active_only:
            query = query.filter(ContestSeasonLink.is_active == True)
        rows = query.order_by(ContestSeason.id.asc()).all()
        return cls._unique(
            rows,
            f"season for contest={contest_id}, round={round_id}, level={level.value}",
        )

    @staticmethod
    def candidate_contest_ids(
        db: Session, *, season_id: int, round_id: int | None
    ) -> tuple[int, ...]:
        query = db.query(ContestSeasonLink.contest_id).filter(
            ContestSeasonLink.season_id == int(season_id)
        )
        ids = {int(row[0]) for row in query.all()}
        if round_id is not None:
            round_ids = {
                int(row[0])
                for row in db.query(round_contests.c.contest_id)
                .filter(round_contests.c.round_id == int(round_id))
                .all()
            }
            ids &= round_ids
        return tuple(sorted(ids))

    @classmethod
    def resolve_period(
        cls,
        db: Session,
        *,
        contest_id: int,
        season_id: int,
        stage_id: int,
        round_id: int,
    ) -> ContestPeriodContext:
        contest = db.query(Contest).filter(
            Contest.id == int(contest_id), Contest.is_deleted == False
        ).one_or_none()
        if contest is None:
            raise ContestContextNotFound(f"Contest id={contest_id} does not exist.")
        season = db.query(ContestSeason).filter(
            ContestSeason.id == int(season_id), ContestSeason.is_deleted == False
        ).one_or_none()
        if season is None:
            raise ContestContextNotFound(f"Season id={season_id} does not exist.")
        if season.round_id != int(round_id):
            raise ContestContextError("Season does not belong to the requested round.")
        stage = db.query(ContestStage).filter(ContestStage.id == int(stage_id)).one_or_none()
        if stage is None:
            raise ContestContextNotFound(f"Stage id={stage_id} does not exist.")
        if stage.season_id != season.id:
            raise ContestContextError("Stage does not belong to the requested season.")
        if db.query(ContestSeasonLink.id).filter(
            ContestSeasonLink.contest_id == contest.id,
            ContestSeasonLink.season_id == season.id,
        ).one_or_none() is None:
            raise ContestContextError("Contest is not linked to the requested season.")
        if db.query(round_contests.c.id).filter(
            round_contests.c.round_id == int(round_id),
            round_contests.c.contest_id == contest.id,
        ).one_or_none() is None:
            raise ContestContextError("Contest is not linked to the requested round.")
        if stage.end_date < stage.start_date:
            raise ContestContextError("Stage date range is invalid.")
        return ContestPeriodContext(
            contest_id=contest.id,
            round_id=int(round_id),
            season_id=season.id,
            stage_id=stage.id,
            category_key=category_identity(contest),
            period_start=stage.start_date,
            period_end=stage.end_date,
        )

    @staticmethod
    def _entry_contest_ids(
        db: Session, *, user_id: int, candidate_ids: Sequence[int]
    ) -> set[int]:
        if not candidate_ids:
            return set()
        result = {
            int(row[0])
            for row in db.query(ContestEntry.contest_id).filter(
                ContestEntry.user_id == int(user_id),
                ContestEntry.contest_id.in_(candidate_ids),
            ).distinct().all()
        }
        connection = db.connection()
        if inspect(connection).has_table("contest_entries"):
            statement = text(
                "SELECT DISTINCT contest_id FROM contest_entries "
                "WHERE user_id = :user_id AND contest_id IN :candidate_ids"
            ).bindparams(bindparam("candidate_ids", expanding=True))
            result.update(
                int(row[0])
                for row in db.execute(
                    statement,
                    {"user_id": int(user_id), "candidate_ids": list(candidate_ids)},
                ).all()
            )
        return result

    @classmethod
    def resolve_historical_vote(
        cls, db: Session, vote_or_id: Vote | int
    ) -> HistoricalVoteAttribution:
        vote = (
            vote_or_id
            if isinstance(vote_or_id, Vote)
            else db.query(Vote).filter(Vote.id == int(vote_or_id)).one_or_none()
        )
        if vote is None:
            raise ContestContextNotFound(f"Vote id={vote_or_id} does not exist.")
        stage = db.query(ContestStage).filter(ContestStage.id == vote.stage_id).one_or_none()
        contestant = db.query(Contestant).filter(
            Contestant.id == vote.contestant_id
        ).one_or_none()
        if stage is None or contestant is None:
            return HistoricalVoteAttribution(
                vote_id=vote.id,
                classification=AttributionClass.ORPHANED_INVALID,
                stage_id=vote.stage_id,
                season_id=None,
                round_id=None,
                contest_id=None,
                candidate_contest_ids=(),
                evidence=("missing stage or contestant",),
            )
        season = db.query(ContestSeason).filter(
            ContestSeason.id == stage.season_id
        ).one_or_none()
        if season is None:
            return HistoricalVoteAttribution(
                vote_id=vote.id,
                classification=AttributionClass.ORPHANED_INVALID,
                stage_id=stage.id,
                season_id=stage.season_id,
                round_id=None,
                contest_id=None,
                candidate_contest_ids=(),
                evidence=("missing season",),
            )
        candidates = cls.candidate_contest_ids(
            db, season_id=season.id, round_id=season.round_id
        )
        if not candidates:
            classification = AttributionClass.ORPHANED_INVALID
            resolved = None
            evidence = ("season/round has no contest candidate",)
        elif len(candidates) == 1:
            classification = AttributionClass.EXACT
            resolved = candidates[0]
            evidence = ("single contest linked to both season and round",)
        else:
            entry_ids = cls._entry_contest_ids(
                db, user_id=contestant.user_id, candidate_ids=candidates
            )
            vote_day = vote.vote_date.date()
            temporal_ids = {
                int(row[0])
                for row in db.query(Contest.id).filter(
                    Contest.id.in_(candidates),
                    Contest.voting_start_date.isnot(None),
                    Contest.voting_end_date.isnot(None),
                    Contest.voting_start_date <= vote_day,
                    Contest.voting_end_date >= vote_day,
                ).all()
            }
            resolved = None
            evidence_parts = []
            if len(entry_ids) == 1 and (len(temporal_ids) != 1 or entry_ids == temporal_ids):
                resolved = next(iter(entry_ids))
                evidence_parts.append("unique contestant-owner contest entry")
            elif not entry_ids and len(temporal_ids) == 1:
                resolved = next(iter(temporal_ids))
                evidence_parts.append("unique linked contest voting window")
            if resolved is None:
                classification = AttributionClass.AMBIGUOUS
                evidence_parts.append(
                    f"{len(candidates)} candidate contests; entries={sorted(entry_ids)}; "
                    f"temporal={sorted(temporal_ids)}"
                )
            else:
                classification = AttributionClass.STRONG
            evidence = tuple(evidence_parts)
        return HistoricalVoteAttribution(
            vote_id=vote.id,
            classification=classification,
            stage_id=stage.id,
            season_id=season.id,
            round_id=season.round_id,
            contest_id=resolved,
            candidate_contest_ids=candidates,
            evidence=evidence,
        )

    @classmethod
    def exact_historical_season_ids_for_contest(
        cls, db: Session, *, season_ids: Iterable[int], contest_id: int
    ) -> tuple[int, ...]:
        exact = []
        for season_id in sorted({int(value) for value in season_ids}):
            season = db.query(ContestSeason).filter(
                ContestSeason.id == season_id
            ).one_or_none()
            if season is None:
                continue
            candidates = cls.candidate_contest_ids(
                db, season_id=season.id, round_id=season.round_id
            )
            if candidates == (int(contest_id),):
                exact.append(season.id)
        return tuple(exact)

    @staticmethod
    def resolve_current_roster(
        db: Session, *, contest_id: int, season_id: int
    ) -> RosterResolution:
        # contestant_voting carries the only exact contestant->contest->season
        # relationship currently present in the ORM/live schema.
        ids = {
            int(row[0])
            for row in db.query(ContestantVoting.contestant_id).filter(
                ContestantVoting.contest_id == int(contest_id),
                ContestantVoting.season_id == int(season_id),
            ).distinct().all()
        }
        return RosterResolution(
            contestant_ids=tuple(sorted(ids)),
            evidence="explicit contestant_voting contest_id + season_id",
        )

    @classmethod
    def resolve_period_roster(
        cls, db: Session, *, contest_id: int, season_id: int
    ) -> RosterResolution:
        """Resolve only roster membership supported by contest-specific evidence.

        A shared season membership is exact only when that season/round maps to
        one contest.  For shared seasons, current contextual votes and explicit
        contest entries are retained; receiving a historical vote is never used
        as proof of membership.
        """
        season = db.query(ContestSeason).filter(
            ContestSeason.id == int(season_id),
            ContestSeason.is_deleted == False,
        ).one_or_none()
        if season is None:
            raise ContestContextNotFound(f"Season id={season_id} does not exist.")
        candidates = cls.candidate_contest_ids(
            db, season_id=season.id, round_id=season.round_id
        )
        if int(contest_id) not in candidates:
            raise ContestContextError("Contest is not a candidate for this season/round.")

        ids = set(
            cls.resolve_current_roster(
                db, contest_id=int(contest_id), season_id=season.id
            ).contestant_ids
        )
        evidence = ["explicit contestant_voting contest_id + season_id"] if ids else []

        if candidates == (int(contest_id),):
            ids.update(
                int(row[0])
                for row in db.query(ContestantSeason.contestant_id)
                .filter(ContestantSeason.season_id == season.id)
                .distinct()
                .all()
            )
            ids.update(
                int(row[0])
                for row in db.query(Contestant.id)
                .filter(Contestant.season_id == season.id)
                .distinct()
                .all()
            )
            evidence.append("season/round has one contest candidate")
        else:
            candidate_rows = db.query(Contestant.id, Contestant.user_id).filter(
                Contestant.id.in_(
                    db.query(ContestantSeason.contestant_id).filter(
                        ContestantSeason.season_id == season.id
                    )
                )
            ).all()
            for contestant_id, user_id in candidate_rows:
                if cls._entry_contest_ids(
                    db, user_id=int(user_id), candidate_ids=candidates
                ) == {int(contest_id)}:
                    ids.add(int(contestant_id))
            if ids:
                evidence.append("unique contestant-owner contest entry")

        return RosterResolution(
            contestant_ids=tuple(sorted(ids)),
            evidence="; ".join(evidence) or "no contest-specific roster evidence",
        )

    @classmethod
    def preflight_monthly_rounds(
        cls, db: Session, periods: Iterable[date]
    ) -> tuple[Round, ...]:
        """Read-only ambiguity gate to run before any calendar mutation."""
        resolved = []
        for period in periods:
            try:
                resolved.append(cls.resolve_submission_round(db, period))
            except ContestContextNotFound:
                # Missing periods are valid creation work; duplicates are not.
                continue
        return tuple(resolved)


contest_context_service = ContestContextService()
