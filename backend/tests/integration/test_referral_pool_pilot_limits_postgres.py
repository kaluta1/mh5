"""Multi-Unit Referral Pool unit limits on a real PostgreSQL server (opt-in RUN_POSTGRES_TESTS=1; one
DISPOSABLE database per test; SYNTHETIC).

Owner decision 2026-10-25: purchases are UNLIMITED. With every limit empty (NULL, production's
configuration), a member buys any positive number of units at $100 each, at once or again later, beyond
the former 5/5/50 pilot, and every unit is created and recognized. The optional limits an administrator
may still set are then proved with production's shape (the historical unit 1 of the founding member):
held units of every source count; purchases still being paid reserve their units; every refusal happens
at checkout, before any money is taken.
"""
from __future__ import annotations

import os
from datetime import datetime
from decimal import Decimal

import pytest

from app.models.business_model import ReferralPoolConfig, ReferralPoolPurchase, ReferralPoolUnit
from app.models.payment import Deposit
from app.models.user import User
from app.services import referral_pool_conversion as conversion
from app.services import referral_pool_units as units
from tests.integration.test_payments_postgres import pg  # noqa: F401
from tests.integration.test_referral_pool_conversion_postgres import seat
from tests.integration.test_referral_pool_units_postgres import (  # noqa: F401
    activate, buy, confirm, deposit, member, refusal, world,
)

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(os.getenv("RUN_POSTGRES_TESTS", "").lower() not in ("1", "true", "yes"),
                       reason="Set RUN_POSTGRES_TESTS=1 to run against a local PostgreSQL server"),
]


@pytest.fixture
def pilot(world):
    _e, Session = world
    with Session() as db:
        cfg = db.query(ReferralPoolConfig).one()
        cfg.multiunit_sales_enabled, cfg.allocation_enabled = True, False
        cfg.max_units_per_purchase, cfg.max_units_per_member, cfg.max_active_units = 5, 5, 50
        db.commit()
    founder = member(Session)
    mid = seat(Session, founder)
    with Session() as db:
        assert conversion.convert(db, mid, approved=[mid], run_id="pilot").outcome == conversion.CREATED
    return Session, founder


@pytest.fixture
def unlimited(world):
    _e, Session = world
    with Session() as db:
        cfg = db.query(ReferralPoolConfig).one()
        cfg.multiunit_sales_enabled, cfg.allocation_enabled = True, False
        assert (cfg.max_units_per_purchase, cfg.max_units_per_member, cfg.max_active_units) == (None, None, None)
        db.commit()
    founder = member(Session)
    mid = seat(Session, founder)
    with Session() as db:
        assert conversion.convert(db, mid, approved=[mid], run_id="unlimited").outcome == conversion.CREATED
    return Session, founder


def checkout(Session, user_id: int, quantity: int) -> str:
    d = deposit(Session, user_id, quantity)
    with Session() as db:
        outcome = refusal(lambda: units.create_purchase(db, user=db.get(User, user_id), deposit=db.get(Deposit, d),
                                                        quantity=quantity))
        db.commit() if outcome == "ok" else db.rollback()                   # an accepted checkout is kept
        return outcome


def test_without_limits_any_quantity_is_accepted_beyond_the_former_5_5_50(unlimited):
    Session, founder = unlimited                                             # 1 historical unit held
    assert checkout(Session, founder, 25) == "ok"                            # > 5 at once, > 5 held
    buyer = member(Session)
    assert checkout(Session, buyer, 30) == "ok"                              # pool 56 > 50
    assert checkout(Session, buyer, 30) == "ok"                              # again later: 60 held
    with Session() as db:
        totals = [(p.quantity, p.unit_price, p.total_amount) for p in db.query(ReferralPoolPurchase).order_by(ReferralPoolPurchase.id)]
    assert totals == [(25, Decimal("100.00"), Decimal("2500.00")), (30, Decimal("100.00"), Decimal("3000.00")),
                      (30, Decimal("100.00"), Decimal("3000.00"))]


def test_without_limits_a_large_paid_purchase_creates_and_recognizes_every_unit(unlimited):
    Session, _founder = unlimited
    buyer = member(Session)
    purchase_id, deposit_id = buy(Session, buyer, 60)
    confirm(Session, deposit_id)
    activate(Session, deposit_id)
    with Session() as db:
        purchase = db.get(ReferralPoolPurchase, purchase_id)
        assert (purchase.status, purchase.total_amount, db.get(Deposit, deposit_id).amount) ==             ("PAID", Decimal("6000.00"), Decimal("6000.00"))
        made = db.query(ReferralPoolUnit).filter_by(purchase_id=purchase_id).order_by(ReferralPoolUnit.unit_index).all()
        assert [u.unit_index for u in made] == list(range(1, 61))
        assert {(u.status, u.amount) for u in made} == {(units.ACTIVE, Decimal("100.00"))}
        assert all(u.revenue_recognition_id for u in made)


def test_at_most_5_units_per_purchase(pilot):
    Session, _founder = pilot
    buyer = member(Session)
    assert checkout(Session, buyer, 6) == "PURCHASE_LIMIT"
    assert checkout(Session, buyer, 5) == "ok"


def test_at_most_5_units_per_member_counting_the_historical_unit_and_unpaid_reservations(pilot):
    Session, founder = pilot
    assert checkout(Session, founder, 5) == "MEMBER_LIMIT"                   # 1 historical + 5 > 5
    assert checkout(Session, founder, 4) == "ok"                             # 1 + 4 = 5 (reserved while unpaid)
    assert checkout(Session, founder, 1) == "MEMBER_LIMIT"                   # the unpaid reservation counts
    buyer = member(Session)
    assert checkout(Session, buyer, 3) == "ok"
    assert checkout(Session, buyer, 3) == "MEMBER_LIMIT"
    assert checkout(Session, buyer, 2) == "ok"


def test_at_most_50_units_in_the_pool_counting_the_historical_unit(pilot):
    Session, _founder = pilot                                                # 1 held (historical)
    others = [member(Session) for _ in range(10)]
    with Session() as db:                                                    # 48 more held units, 6..5 per member
        for i in range(48):
            db.add(ReferralPoolUnit(user_id=others[i % 10], source="ADMIN_GRANT", status=units.ACTIVE,
                                    amount=units.UNIT_PRICE, currency="USD", activated_at=datetime(2026, 10, 25)))
        db.commit()
    buyer, late = member(Session), member(Session)
    assert checkout(Session, buyer, 2) == "POOL_LIMIT"                       # 49 + 2 > 50
    assert checkout(Session, buyer, 1) == "ok"                               # 50 (reserved while unpaid)
    assert checkout(Session, late, 1) == "POOL_LIMIT"
    with Session() as db:
        assert db.query(ReferralPoolUnit).count() == 49                      # refusals created nothing
