"""SoncoPay Compliance conditions (written confirmation 2026-10-31) for automated commission payouts.
SYNTHETIC members and a fake SoncoPay (no network): dashboard confirmation recorded with evidence (never
inferred from the API registration or SoncoPay's auto-confirm), 24 hours before the first payout,
identified members only (KYC), USD 5 provider minimum, rolling 24-hour limits of 50 payouts and USD 10,000
(both, counted conservatively and under the settings lock), manual review above USD 1,000 never treated as
paid nor resent, destination suspension, and the administrator permissions."""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from app.models.checkout_gateway import SoncoPayPayoutDestination
from app.services import cashout_engine as engine
from app.services import soncopay_payouts as spo
from tests.unit.test_admin_security_hardening import PASSWORD as ADMIN_PASSWORD
from tests.unit.test_dual_cashout import NOW, OTHER_WALLET, cashouts, commission, member  # noqa: F401
from tests.unit.test_soncopay_payouts import (  # noqa: F401
    dashboard_confirm,
    destination,
    engine_on,
    fake,
    keys,
    ledger,
    no_network,
    payouts_on,
    real_figures,
    run,
    soncopay_live,
    world,
)
from tests.unit.test_super_admin import superadmin

pytestmark = [pytest.mark.unit, pytest.mark.discontinued, pytest.mark.ten_dollar_minimum]


@pytest.fixture(autouse=True)
def real_minimum(monkeypatch, keys):  # noqa: F811 - after the legacy module's floor override
    monkeypatch.setattr(spo, "PROVIDER_MIN_PAYOUT_USD", Decimal("5.00"))


def registered(db, fake, name="m1", *, wallet=None, kyc=True, usable=True, amount=None):
    """A member whose approved wallet is registered with SoncoPay and confirmed by SoncoPay (NOT yet in
    the dashboard). With `amount`, that commission is waiting to be paid."""
    user = member(db, name, method="CRYPTO", kyc=kyc, **({"wallet": wallet} if wallet else {}))
    commission(db, user, amount or "1.00")
    run(db)                                                       # approved wallet -> registered with SoncoPay
    fake.confirm(destination(db, user).destination_id, usable=usable)
    run(db)
    return user


# ---------------------------------------------------------------- confirmation and waiting period

def test_registration_and_soncopays_auto_confirmation_are_not_the_dashboard_confirmation(payouts_on, fake):
    db = payouts_on
    real_figures(db, fake)
    fake.auto_confirm = True
    user = member(db, "m1", method="CRYPTO")
    commission(db, user, "20.00")
    run(db)                                                       # registered (and auto-confirmed by SoncoPay)
    assert run(db)["members"] == {"DESTINATION_AWAITING_DASHBOARD_CONFIRMATION": 1}
    assert destination(db, user).status == "ACTIVE" and fake.posts("/v1/payouts") == []


def test_the_first_payout_waits_24_hours_after_the_dashboard_confirmation(payouts_on, fake):
    db = payouts_on
    real_figures(db, fake)
    user = registered(db, fake)
    commission(db, user, "20.00")
    dashboard_confirm(db, user, at=NOW - timedelta(hours=23))
    assert run(db)["members"] == {"DESTINATION_WAITING_PERIOD": 1} and fake.posts("/v1/payouts") == []
    assert run(db, now=NOW + timedelta(hours=2))["members"] == {"SUBMITTED": 1}
    assert len(fake.payouts) == 1


def test_recording_the_confirmation_needs_permission_password_evidence_and_kyc(payouts_on, fake):
    db = payouts_on
    user = registered(db, fake)
    row = destination(db, user)
    row.registered_at = NOW - timedelta(days=1)                   # the cycle clock is real time; tests use NOW
    db.commit()
    boss = superadmin(db, "boss-confirm")
    plain = member(db, "plain")
    with pytest.raises(PermissionError):
        spo.record_dashboard_confirmation(db, plain, destination_row_id=row.id, confirmed_at=NOW,
                                          evidence="dashboard screenshot 1", ownership_evidence="signed message 0x1",
                                          password=ADMIN_PASSWORD, now=NOW)
    with pytest.raises(Exception):
        spo.record_dashboard_confirmation(db, boss, destination_row_id=row.id, confirmed_at=NOW,
                                          evidence="dashboard screenshot 1", ownership_evidence="signed message 0x1",
                                          password="wrong", now=NOW)
    db.rollback()
    with pytest.raises(ValueError, match="dashboard"):
        spo.record_dashboard_confirmation(db, boss, destination_row_id=row.id, confirmed_at=NOW, evidence="x",
                                          ownership_evidence="signed message 0x1", password=ADMIN_PASSWORD, now=NOW)
    db.rollback()
    with pytest.raises(ValueError, match="future"):
        spo.record_dashboard_confirmation(db, boss, destination_row_id=row.id, confirmed_at=NOW + timedelta(hours=1),
                                          evidence="dashboard screenshot 1", ownership_evidence="signed message 0x1",
                                          password=ADMIN_PASSWORD, now=NOW)
    db.rollback()
    ok = spo.record_dashboard_confirmation(db, boss, destination_row_id=row.id, confirmed_at=NOW - timedelta(hours=2),
                                           evidence="dashboard screenshot 1", ownership_evidence="signed message 0x1",
                                           password=ADMIN_PASSWORD, now=NOW)
    assert ok.dashboard_confirmed_by == boss.id and spo.payable_from(ok) == NOW + timedelta(hours=22)
    with pytest.raises(ValueError, match="already recorded"):
        spo.record_dashboard_confirmation(db, boss, destination_row_id=row.id, confirmed_at=NOW,
                                          evidence="dashboard screenshot 2", ownership_evidence="signed message 0x1",
                                          password=ADMIN_PASSWORD, now=NOW)


def test_no_confirmation_is_recorded_for_a_member_without_approved_kyc(payouts_on, fake):
    db = payouts_on
    user = registered(db, fake, kyc=False)
    destination(db, user).registered_at = NOW - timedelta(days=1)
    db.commit()
    boss = superadmin(db, "boss-kyc")
    with pytest.raises(ValueError, match="KYC"):
        spo.record_dashboard_confirmation(db, boss, destination_row_id=destination(db, user).id,
                                          confirmed_at=NOW - timedelta(hours=1), evidence="dashboard screenshot 1",
                                          ownership_evidence="signed message 0x1", password=ADMIN_PASSWORD, now=NOW)


def test_a_member_without_approved_kyc_is_never_paid(payouts_on, fake):
    db = payouts_on
    real_figures(db, fake)
    user = registered(db, fake, kyc=False)
    dashboard_confirm(db, user)
    commission(db, user, "20.00")
    assert run(db)["members"] == {"KYC_NOT_APPROVED": 1} and fake.posts("/v1/payouts") == []


def test_a_wallet_change_needs_a_new_dashboard_confirmation(payouts_on, fake):
    from tests.unit.test_dual_cashout import approve_wallet

    db = payouts_on
    real_figures(db, fake)
    user = registered(db, fake)
    dashboard_confirm(db, user)
    user.usdt_wallet_address = OTHER_WALLET
    db.commit()
    approve_wallet(db, user)
    run(db)
    new = destination(db, user)
    assert new.address == OTHER_WALLET and new.dashboard_confirmed_at is None
    fake.confirm(new.destination_id, usable=True)
    commission(db, user, "20.00")
    assert run(db)["members"] == {"DESTINATION_AWAITING_DASHBOARD_CONFIRMATION": 1}


def test_a_suspended_destination_is_never_paid_and_resumes_when_lifted(payouts_on, fake):
    db = payouts_on
    real_figures(db, fake)
    user = registered(db, fake)
    dashboard_confirm(db, user)
    boss = superadmin(db, "boss-susp")
    row = destination(db, user)
    spo.set_suspended(db, boss, destination_row_id=row.id, suspend=True, reason="ownership query",
                      password=ADMIN_PASSWORD)
    commission(db, user, "20.00")
    assert run(db)["members"] == {"DESTINATION_SUSPENDED": 1} and fake.posts("/v1/payouts") == []
    spo.set_suspended(db, boss, destination_row_id=row.id, suspend=False, reason="ownership confirmed",
                      password=ADMIN_PASSWORD)
    assert run(db)["members"] == {"SUBMITTED": 1}


# ---------------------------------------------------------------- minimum and limits

def test_the_provider_minimum_is_at_least_five_dollars():
    facts = spo.published_fee_and_minimum({"fees": {"USDT:BSC": "0.23"}, "min_payout_usd": "0.5",
                                           "limits": {"USDT:BSC": {"minimum": "2", "fee": "0.23"}}})
    assert facts.minimum == Decimal("5.00")
    facts = spo.published_fee_and_minimum({"fees": {"USDT:BSC": "0.23"}, "min_payout_usd": "7"})
    assert facts.minimum == Decimal("7")


def test_the_rolling_24_hour_count_limit_is_never_passed(payouts_on, fake, monkeypatch):
    db = payouts_on
    real_figures(db, fake)
    monkeypatch.setattr(spo.SoncoPayPayoutProvider, "max_24h_count", 2)
    users = [registered(db, fake, f"c{i}", wallet="0x" + f"{i + 1}" * 40) for i in range(3)]
    for user in users:
        dashboard_confirm(db, user)
        commission(db, user, "20.00")
    report = run(db)
    assert report["members"].get("SUBMITTED") == 2 and report["members"].get("PROVIDER_24H_COUNT_LIMIT") == 1
    assert len(fake.payouts) == 2
    # Rolling, not a calendar day: still refused 23 hours later, allowed after 24.
    assert run(db, now=NOW + timedelta(hours=23))["members"].get("PROVIDER_24H_COUNT_LIMIT") == 1
    assert run(db, now=NOW + timedelta(hours=24, minutes=1))["members"].get("SUBMITTED") == 1


def test_the_rolling_24_hour_amount_limit_counts_both_at_once(payouts_on, fake, monkeypatch):
    db = payouts_on
    real_figures(db, fake)
    monkeypatch.setattr(spo.SoncoPayPayoutProvider, "max_24h_amount", Decimal("30.00"))
    users = [registered(db, fake, f"a{i}", wallet="0x" + f"{i + 4}" * 40) for i in range(2)]
    for user in users:
        dashboard_confirm(db, user)
        commission(db, user, "20.00")
    report = run(db)
    assert report["members"].get("SUBMITTED") == 1 and report["members"].get("PROVIDER_24H_AMOUNT_LIMIT") == 1


def test_reserved_and_sent_payouts_count_in_the_window_failed_unsent_do_not(payouts_on, fake):
    from app.models.affiliate import AffiliateCashoutRequest

    db = payouts_on
    for n, (status, batch) in enumerate((("requested", None), ("processing", "po_1"), ("unknown", None),
                                         ("completed", "po_2"), ("failed", "po_3"), ("failed", None),
                                         ("cancelled", None))):
        user = member(db, f"w{n}", method="CRYPTO")
        db.add(AffiliateCashoutRequest(user_id=user.id, gross_amount=Decimal("10.00"), net_amount=Decimal("10.00"),
                                       status=status, cashout_method="CRYPTO", provider_batch_id=batch,
                                       requested_at=NOW - timedelta(hours=1)))
    old = member(db, "w-old", method="CRYPTO")
    db.add(AffiliateCashoutRequest(user_id=old.id, gross_amount=Decimal("10.00"), net_amount=Decimal("10.00"),
                                   status="completed", cashout_method="CRYPTO", provider_batch_id="po_old",
                                   requested_at=NOW - timedelta(hours=25)))
    db.commit()
    assert engine.provider_window_usage(db, NOW) == (Decimal("50.00"), 5)


def test_manual_review_above_1000_is_never_completed_nor_resent(payouts_on, fake):
    from app.services import payment_config
    from tests.unit.test_dual_cashout import configure

    db = payouts_on
    real_figures(db, fake)
    configure(db, max_single_payout_usd=Decimal("2000.00"), max_daily_payout_usd=Decimal("5000.00"))
    fake.balance = "5000"
    user = registered(db, fake)
    dashboard_confirm(db, user)
    row = commission(db, user, "1500.00")
    assert run(db)["members"] == {"SUBMITTED": 1}
    [po] = fake.payouts.values()
    po["status"] = "pending_review"                                 # SoncoPay holds it for manual review
    run(db)
    out = cashouts(db, user)[0]
    assert out.status == "processing" and out.provider_status == "pending_review"
    assert len(fake.posts("/v1/payouts")) == 1                      # never sent again
    assert spo.provider_limit_view(db, NOW)["in_manual_review"][0]["cashout_id"] == out.id
    db.refresh(row)
    assert row.status.value != "PAID"
    fake.complete(po["id"])
    run(db)
    assert cashouts(db, user)[0].status == "completed"
    assert payment_config.payout_activation_switch() is True        # engine_on fixture (tests only)


# ---------------------------------------------------------------- administrator API

def test_the_confirmation_and_suspension_endpoints_need_an_authorized_administrator(payouts_on, fake, client):
    from tests.unit.test_admin_security_hardening import bearer

    db = payouts_on
    user = registered(db, fake)
    destination(db, user).registered_at = datetime.utcnow() - timedelta(days=1)
    db.commit()
    row_id = destination(db, user).id
    url = f"/api/v1/admin/finance/soncopay/payouts/destinations/{row_id}"
    body = {"confirmed_at": (datetime.utcnow() - timedelta(hours=1)).isoformat(), "evidence": "dashboard screenshot 1",
            "ownership_evidence": "signed message 0x1", "current_password": ADMIN_PASSWORD}
    other = member(db, "nosy")
    assert client.post(f"{url}/dashboard-confirmation", json=body, headers=bearer(other)).status_code == 403
    boss = superadmin(db, "boss-api")
    res = client.post(f"{url}/dashboard-confirmation", json=body, headers=bearer(boss))
    assert res.status_code == 200 and res.json()["dashboard_confirmed_at"]
    res = client.post(f"{url}/suspension", json={"suspend": True, "reason": "check wallet",
                                                 "current_password": ADMIN_PASSWORD}, headers=bearer(boss))
    assert res.status_code == 200 and res.json()["suspended_at"]
    view = client.get("/api/v1/admin/finance/soncopay/payouts", headers=bearer(boss)).json()
    dest = next(d for d in view["destinations"] if d["id"] == row_id)
    assert dest["state"] == "DESTINATION_SUSPENDED" and dest["ownership_evidence"] == "signed message 0x1"
    assert view["provider_limits"]["count_limit"] == 50 and view["provider_limits"]["amount_limit"] == "10000.00"
    db.expire_all()
    assert db.query(SoncoPayPayoutDestination).filter(SoncoPayPayoutDestination.id == row_id).one().suspended_by == boss.id
