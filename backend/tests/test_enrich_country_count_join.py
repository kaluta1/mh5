"""Regression: country-scoped nomination counts must not double-join users."""
from __future__ import annotations

from sqlalchemy import event, func, or_

from app.crud.crud_contest import (
    CRUDContest,
    _get_country_match_patterns,
    _nomination_row_entry_type_clause,
)
from app.db.session import SessionLocal
from app.models.contests import Contestant
from app.models.user import User


def test_country_fallback_count_query_uses_single_users_join():
    """Mirrors enrich_contest_with_stats country fallback (logged-in TZ user)."""
    db = SessionLocal()
    try:
        q = db.query(func.count(func.distinct(Contestant.user_id))).outerjoin(
            User, Contestant.user_id == User.id
        ).filter(
            Contestant.is_deleted == False,
            _nomination_row_entry_type_clause("nomination", "nomination"),
            Contestant.season_id == 219,
            Contestant.round_id == 26,
        )
        patterns = _get_country_match_patterns("Tanzania")
        conds = []
        for pat in patterns:
            conds.append(Contestant.country.ilike(pat))
            conds.append(Contestant.nominator_country.ilike(pat))
            conds.append(User.country.ilike(pat))
        q = q.filter(or_(*conds))
        sql = str(q.statement).lower()
        assert sql.count("join users") == 1
    finally:
        db.close()


def test_count_nomination_roster_for_card_count_only_skips_enrich(monkeypatch):
    """count_only must not run enrich_contest_with_stats (avoids duplicate-join path)."""
    db = SessionLocal()
    enrich_called = {"n": 0}

    def _boom(*args, **kwargs):
        enrich_called["n"] += 1
        raise AssertionError("enrich_contest_with_stats should be skipped for count_only")

    monkeypatch.setattr(CRUDContest, "enrich_contest_with_stats", _boom)
    try:
        crud = CRUDContest()
        crud.count_nomination_roster_for_card(
            db,
            contest_id=7,
            current_user_id=9,
            filter_country="Tanzania",
            entry_type="nomination",
            round_id=26,
            requested_ui_level="country",
        )
        assert enrich_called["n"] == 0
    finally:
        db.close()
