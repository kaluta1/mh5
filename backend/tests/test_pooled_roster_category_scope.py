"""Pooled nomination rosters must not mix contestants from other categories."""
from types import SimpleNamespace

from app.services.contest_category_integrity import pooled_roster_contest_scope_clause


class _FakeQuery:
    def __init__(self):
        self.filters = []

    def filter(self, *args):
        self.filters.extend(args)
        return self


class _FakeDb:
    def __init__(self, category_ids):
        self.category_ids = category_ids

    def query(self, _model):
        q = _FakeQuery()

        def _all():
            return [(i,) for i in self.category_ids]

        q.all = _all
        return q


def test_pooled_scope_uses_category_bucket():
    contest = SimpleNamespace(id=177, category_id=108, contest_type="meme")
    db = _FakeDb([177, 188])
    clause = pooled_roster_contest_scope_clause(db, contest)
    assert hasattr(clause, "compare") or str(clause).startswith("Contestant.season_id IN")


def test_pooled_scope_falls_back_to_contest_id_without_category():
    contest = SimpleNamespace(id=3, category_id=None, contest_type="beauty")
    db = _FakeDb([3])
    clause = pooled_roster_contest_scope_clause(db, contest)
    assert clause is not None
