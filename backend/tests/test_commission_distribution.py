"""Tests for commission distribution idempotency and sponsor-cycle protection.

The legacy engine is retired for future activity; these tests exercise it with the
legacy model explicitly re-enabled (the emergency rollback lever), so its safety
properties stay covered. Even re-enabled, and even with a stored rule that still says
"10 levels", it pays the DIRECT sponsor only: the affiliate program is level 1 only.
"""

from unittest.mock import MagicMock, patch

import pytest

from app.core.config import settings

from app.models.affiliate import AffiliateCommission, CommissionType
from app.models.payment import Deposit
from app.models.user import User
from app.services.commission_distribution import distribute_commissions


@pytest.fixture(autouse=True)
def _legacy_model_enabled(monkeypatch):
    monkeypatch.setattr(settings, "LEGACY_BUSINESS_MODEL_ENABLED", True)


def _user(user_id: int, sponsor_id: int | None) -> User:
    user = User()
    user.id = user_id
    user.sponsor_id = sponsor_id
    user.usdt_wallet_address = "0xwallet"
    user.email = f"u{user_id}@test.com"
    user.username = f"u{user_id}"
    return user


def _deposit(deposit_id: int = 1, payer_id: int = 100) -> Deposit:
    deposit = Deposit()
    deposit.id = deposit_id
    deposit.user_id = payer_id
    deposit.amount = 10.0
    deposit.product_type_id = 1
    return deposit


def _run_distribution(users: dict[int, User], deposit: Deposit) -> list[AffiliateCommission]:
    db = MagicMock()
    created: list[AffiliateCommission] = []

    rule = MagicMock()
    rule.commission_type = CommissionType.KYC_PAYMENT
    rule.direct_percentage = 10.0
    rule.indirect_percentage = 1.0
    rule.max_levels = 10
    rule.is_active = True

    user_ids_in_order = [deposit.user_id]
    payer = users[deposit.user_id]
    sid = payer.sponsor_id
    visited: set[int] = set()
    while sid is not None and sid not in visited:
        visited.add(sid)
        user_ids_in_order.append(sid)
        sid = users[sid].sponsor_id if sid in users else None

    def user_first():
        uid = user_ids_in_order.pop(0) if user_ids_in_order else None
        return users.get(uid) if uid is not None else None

    def query(model):
        q = MagicMock()
        name = getattr(model, "__name__", str(model))
        if name == "CommissionRule":
            q.filter.return_value.first.return_value = rule
        elif name == "AffiliateCommission":
            q.filter.return_value.all.return_value = []
            q.filter.return_value.first.return_value = None
        elif name == "User":
            q.filter.return_value.first = MagicMock(side_effect=user_first)
        return q

    db.query.side_effect = query
    db.add.side_effect = lambda obj: created.append(obj)

    with patch(
        "app.services.commission_payout_service.process_commission_payouts_sync",
        return_value=0,
    ):
        distribute_commissions(db, deposit, "kyc", commit=False)
    return created


def test_only_the_direct_sponsor_is_paid_even_with_a_ten_level_rule_and_a_cycle():
    """Payer 100 -> 1 -> 2 -> 3 -> 1 (cycle), stored rule max_levels=10: only user 1,
    the direct sponsor, receives a commission. Nobody above is walked or paid."""
    users = {
        100: _user(100, 1),
        1: _user(1, 2),
        2: _user(2, 3),
        3: _user(3, 1),
    }
    created = _run_distribution(users, _deposit())
    assert [(c.user_id, c.level) for c in created] == [(1, 1)]
    assert float(created[0].commission_amount) == 1.0          # the unchanged direct percentage of the rule


def test_ineligible_direct_sponsor_gets_nothing_and_nobody_above_is_paid():
    users = {100: _user(100, 1), 1: _user(1, 2), 2: _user(2, None)}
    users[1].is_active = False
    assert _run_distribution(users, _deposit()) == []


def test_skips_when_commissions_already_exist_for_deposit():
    db = MagicMock()
    existing = [MagicMock(spec=AffiliateCommission)]
    deposit = _deposit()
    payer = _user(100, 1)

    rule = MagicMock()
    rule.commission_type = CommissionType.KYC_PAYMENT
    rule.direct_percentage = 10.0
    rule.indirect_percentage = 1.0
    rule.max_levels = 10
    rule.is_active = True

    def query(model):
        q = MagicMock()
        name = getattr(model, "__name__", str(model))
        if name == "CommissionRule":
            q.filter.return_value.first.return_value = rule
        elif name == "AffiliateCommission":
            q.filter.return_value.all.return_value = existing
        elif name == "User":
            q.filter.return_value.first.return_value = payer
        return q

    db.query.side_effect = query
    result = distribute_commissions(db, deposit, "kyc", commit=False)
    assert result == existing
    db.add.assert_not_called()
