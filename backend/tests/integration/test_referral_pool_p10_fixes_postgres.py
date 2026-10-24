"""Multi-Unit Referral Pool, P10: regression tests for the defects fixed in the final audit, on a
real PostgreSQL server (opt-in RUN_POSTGRES_TESTS=1; DISPOSABLE databases; SYNTHETIC data).

1. The eligibility sweep visits every holder, not only the first `limit`.
2. One failing holder neither stops the sweep nor the queue after it.
3. An administrator cannot record a refund reference in a provider-verified format, and an
   approved manual record always reads as a claim.
4. A full reversal of a pool deposit is refused once a unit's cash was refunded (no double cash out).
"""
from __future__ import annotations

import os
from decimal import Decimal

import pytest

from app.api.api_v1.endpoints import referral_pool as pool_api
from app.models.accounting import JournalEntry
from app.models.business_model import ReferralPoolUnit
from app.models.payment import Deposit
from app.models.user import User
from app.services import payment_config
from app.services import referral_pool_allocation as alloc
from app.services import referral_pool_integration as integration
from app.services import referral_pool_units as units
from app.services.financial_integrity import FinancialIntegrityError
from app.services.new_model_payments import reverse_new_model_deposit
from tests.integration.test_payments_postgres import pg  # noqa: F401
from tests.integration.test_referral_pool_accounting_postgres import sponsored_buyer
from tests.integration.test_referral_pool_allocation_postgres import holder, referral, set_allocation
from tests.integration.test_referral_pool_checkout_postgres import (  # noqa: F401  (fixtures)
    checkout, provider_event, purchase_of, shop,
)
from tests.integration.test_referral_pool_units_postgres import member, world  # noqa: F401

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(os.getenv("RUN_POSTGRES_TESTS", "").lower() not in ("1", "true", "yes"),
                       reason="Set RUN_POSTGRES_TESTS=1 to run against a local PostgreSQL server"),
]


def statuses(Session, user_id: int) -> list:
    with Session() as db:
        return sorted(u.status for u in db.query(ReferralPoolUnit).filter_by(user_id=user_id))


def deactivate(Session, user_id: int) -> None:
    with Session() as db:
        db.get(User, user_id).is_active = False                    # a change that writes no pool event
        db.commit()


def test_the_sweep_visits_every_holder_beyond_one_batch(world):
    _engine, Session = world
    holders = [holder(Session, 1) for _ in range(3)]
    deactivate(Session, holders[-1])                               # the highest user id
    assert integration.sweep_eligibility(Session, limit=1) == 1
    assert statuses(Session, holders[-1]) == [units.SUSPENDED]
    assert statuses(Session, holders[0]) == statuses(Session, holders[1]) == [units.ACTIVE]


def test_one_failing_holder_does_not_stop_the_sweep_or_the_queue(world, monkeypatch):
    _engine, Session = world
    set_allocation(Session, True)
    broken, other = holder(Session, 1), holder(Session, 1)
    deactivate(Session, other)
    waiting = referral(Session)
    real = units.sync_member_eligibility

    def flaky(db, user_id, **kw):
        if user_id == broken:
            raise RuntimeError("synthetic failure")
        return real(db, user_id, **kw)

    monkeypatch.setattr(units, "sync_member_eligibility", flaky)
    result = integration.run_once(Session)
    assert result["swept"] == 1 and statuses(Session, other) == [units.SUSPENDED]
    assert [r.outcome for r in result["queue"]] == [alloc.ASSIGNED]           # the queue still ran
    with Session() as db:
        assert db.get(User, waiting).sponsor_id == broken


def test_a_manual_refund_cannot_use_a_provider_verified_reference(shop, monkeypatch):
    Session = shop
    monkeypatch.setattr(payment_config, "has_permission", lambda user, permission: True)
    monkeypatch.setattr(payment_config, "require_reauth", lambda actor, password: None)
    proposer = member(Session)
    buyer, _ = sponsored_buyer(Session)
    _c, r = checkout(Session, buyer, 2)
    provider_event(Session, r.deposit_id, "paid")
    pid = purchase_of(Session, r.deposit_id)[0]
    for reference in (f"soncopay-refund:{r.deposit_id}:100.00", "provider-refund:1:100", "DEPOSIT-REFUND:9"):
        with Session() as db:
            with pytest.raises(units.UnitsError) as info:
                units.propose_manual_refund(db, db.get(User, proposer), purchase_id=pid, quantity=1, amount=Decimal("100"),
                                            provider_reference=reference, evidence_note="Seen at the provider", password="x")
            assert info.value.code == "REFERENCE_RESERVED"
    claim = pool_api.refund_evidence("soncopay-refund:7:100.00", {"soncopay-refund:7:100.00"})   # a legacy record
    assert (claim["evidence"], claim["provider_verified"]) == ("ADMIN_ENTERED_CLAIM", False)
    assert pool_api.refund_evidence("soncopay-refund:7:100.00")["provider_verified"] is True


def test_a_full_reversal_after_a_unit_refund_is_refused_and_writes_nothing(shop):
    Session = shop
    buyer, _ = sponsored_buyer(Session)
    _c, r = checkout(Session, buyer, 2)
    provider_event(Session, r.deposit_id, "paid")
    assert provider_event(Session, r.deposit_id, "partially_refunded", refunded_amount="100.00") == "SYNCED"
    with Session() as db:
        entries_before = db.query(JournalEntry).count()
        with pytest.raises(FinancialIntegrityError, match="already has refunded Referral Pool units"):
            reverse_new_model_deposit(db, db.get(Deposit, r.deposit_id), reason="script reversal")
        db.rollback()
        assert db.query(JournalEntry).count() == entries_before
    assert purchase_of(Session, r.deposit_id)[3] == ["ACTIVE", "REFUNDED"]
    assert provider_event(Session, r.deposit_id, "refunded", refunded_amount="200.00") == "SYNCED"   # the per-unit path
    assert purchase_of(Session, r.deposit_id)[1:] == ("REFUNDED", 2, ["REFUNDED", "REFUNDED"])
