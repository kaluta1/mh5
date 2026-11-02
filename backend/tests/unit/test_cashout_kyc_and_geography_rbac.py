"""Safety fixes of 2026-11-02 (audit P0-D4 and P0-D6). SYNTHETIC members only.

P0-D4: a USD cashout is requested and settled only for a member whose KYC is APPROVED (pending, in progress,
rejected, expired or under review are refused), re-checked at the administrator's settlement, with nothing
reserved or posted when refused. The crypto payout KYC rule is the same function, unchanged.

P0-D6: geography reference data (continents, regions, countries, cities, initialization) is written by
administrators only; reading it stays open."""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.core.config import settings
from app.models.accounting import JournalEntry
from app.models.kyc import KYCStatus, KYCVerification
from app.services import cashout_engine as engine
from app.services import cashout_service as cs
from app.services.financial_balances import get_commission_balance
from tests.unit.test_age_gate_registration import auth
from tests.unit.test_dual_cashout import (  # noqa: F401
    NOW,
    approve_kyc,
    cashouts,
    commission,
    configure,
    ledger,
    member,
    world,
)

pytestmark = pytest.mark.unit

NOT_APPROVED = [KYCStatus.PENDING, KYCStatus.IN_PROGRESS, KYCStatus.PENDING_PROOF_OF_ADDRESS,
                KYCStatus.REJECTED, KYCStatus.EXPIRED, KYCStatus.REQUIRES_REVIEW]


def set_kyc(db, user, status):
    row = db.query(KYCVerification).filter(KYCVerification.user_id == user.id).first()
    if row is None:
        row = KYCVerification(user_id=user.id, status=status)
        db.add(row)
    row.status = status
    db.commit()


# ---------------------------------------------------------------- USD cashout request

def test_an_approved_member_can_request_a_usd_cashout(client, ledger):
    db = ledger
    user = member(db, "m1", method="USD", wallet=None)              # approved KYC (fixture default)
    commission(db, user, "150.00")
    resp = client.post("/api/v1/wallet/cashout/usd", headers={**auth(user), "Idempotency-Key": "k1"}, json={})
    assert resp.status_code == 200 and resp.json()["status"] == "requested"
    assert len(cashouts(db, user)) == 1


def test_a_member_without_kyc_cannot_request_a_usd_cashout(client, ledger):
    db = ledger
    user = member(db, "m1", method="USD", wallet=None, kyc=False)
    commission(db, user, "150.00")
    before = get_commission_balance(db, user.id)
    for path in ("/api/v1/wallet/cashout/usd", "/api/v1/wallet/withdraw"):
        body = {} if path.endswith("usd") else {"amount": 150}
        resp = client.post(path, headers={**auth(user), "Idempotency-Key": path}, json=body)
        assert resp.status_code == 403 and resp.json()["detail"]["code"] == "KYC_NOT_APPROVED"
    after = get_commission_balance(db, user.id)
    assert cashouts(db, user) == [] and (after.available, after.reserved) == (before.available, before.reserved)
    assert db.query(JournalEntry).count() == 0


@pytest.mark.parametrize("status", NOT_APPROVED, ids=lambda s: s.value)
def test_a_member_whose_kyc_is_not_approved_cannot_request(ledger, status):
    db = ledger
    user = member(db, "m1", method="USD", wallet=None, kyc=False)
    set_kyc(db, user, status)
    commission(db, user, "150.00")
    with pytest.raises(cs.CashoutError) as refused:
        cs.request_usd_cashout(db, user, idempotency_key="k", now=NOW)
    assert refused.value.code == "KYC_NOT_APPROVED"
    assert cashouts(db, user) == []
    assert get_commission_balance(db, user.id).reserved == 0


# ---------------------------------------------------------------- USD settlement by an administrator

@pytest.mark.parametrize("status", [KYCStatus.REJECTED, KYCStatus.EXPIRED, KYCStatus.REQUIRES_REVIEW],
                         ids=lambda s: s.value)
def test_settlement_rechecks_kyc_and_posts_nothing_when_not_approved(ledger, monkeypatch, status):
    db = ledger
    monkeypatch.setattr(settings, "USD_CASHOUT_SETTLEMENT_ENABLED", True)
    configure(db, usd_settlement_enabled=True, usd_settlement_account="1010")
    user, admin = member(db, "m1", method="USD", wallet=None), member(db, "boss", admin=True)
    commission(db, user, "500.00")
    row = cs.request_usd_cashout(db, user, idempotency_key="k", now=NOW)
    set_kyc(db, user, status)                                       # approval withdrawn after the request
    with pytest.raises(cs.CashoutError) as refused:
        cs.settle_usd_cashout(db, row, admin=admin, reference="wire-123", now=NOW)
    assert refused.value.code == "KYC_NOT_APPROVED"
    out = cashouts(db, user)[0]
    assert out.status == "requested" and out.settlement_reference is None
    assert db.query(JournalEntry).count() == 0                      # nothing posted

    set_kyc(db, user, KYCStatus.APPROVED)                           # approved again: settled once, as before
    cs.settle_usd_cashout(db, out, admin=admin, reference="wire-123", now=NOW)
    assert cashouts(db, user)[0].status == "completed" and db.query(JournalEntry).count() == 1
    with pytest.raises(cs.CashoutError):
        cs.settle_usd_cashout(db, out, admin=admin, reference="wire-456", now=NOW)
    assert db.query(JournalEntry).count() == 1                      # no duplicate posting


def test_the_settlement_endpoint_cannot_bypass_kyc(client, ledger, monkeypatch):
    db = ledger
    monkeypatch.setattr(settings, "USD_CASHOUT_SETTLEMENT_ENABLED", True)
    configure(db, usd_settlement_enabled=True, usd_settlement_account="1010")
    user, admin = member(db, "m1", method="USD", wallet=None), member(db, "boss", admin=True)
    commission(db, user, "500.00")
    row = cs.request_usd_cashout(db, user, idempotency_key="k", now=NOW)
    set_kyc(db, user, KYCStatus.REJECTED)
    resp = client.post(f"/api/v1/admin/cashouts/{row.id}/settle-usd", headers=auth(admin),
                       json={"reference": "wire-123"})
    assert resp.status_code == 403 and resp.json()["detail"]["code"] == "KYC_NOT_APPROVED"
    assert cashouts(db, user)[0].status == "requested" and db.query(JournalEntry).count() == 0


# ---------------------------------------------------------------- crypto rule unchanged

def test_the_crypto_payout_kyc_rule_is_unchanged(ledger):
    db = ledger
    approved = member(db, "c1", method="CRYPTO")
    missing = member(db, "c2", method="CRYPTO", kyc=False, wallet="0x" + "c" * 40)
    assert engine.kyc_problem(db, approved) is None
    assert engine.kyc_problem(db, missing) == "KYC_NOT_APPROVED"
    for status in NOT_APPROVED:
        set_kyc(db, missing, status)
        assert engine.kyc_problem(db, missing) == "KYC_NOT_APPROVED"


# ---------------------------------------------------------------- geography reference data

WRITES = [
    ("/api/v1/geography/continents", {"name": "Synthetica", "code": "SY"}),
    ("/api/v1/geography/regions", {"continent_id": 1, "name": "Synthetic Region"}),
    ("/api/v1/geography/countries", {"region_id": 1, "name": "Synthetic Country"}),
    ("/api/v1/geography/cities", {"country_id": 1, "name": "Synthetic City"}),
    ("/api/v1/geography/initialize", None),
]


def _geography_count(db):
    from app.models.geography import City, Continent, Country, Region

    return sum(db.query(m).count() for m in (Continent, Region, Country, City))


def test_anonymous_and_ordinary_members_cannot_write_geography(client, ledger):
    db = ledger
    user = member(db, "m1", wallet=None)
    before = _geography_count(db)
    for path, body in WRITES:
        assert client.post(path, json=body).status_code == 401, path
        assert client.post(path, headers=auth(user), json=body).status_code == 403, path
    assert _geography_count(db) == before


def test_an_administrator_can_write_geography(client, ledger):
    db = ledger
    admin = member(db, "boss", admin=True)
    continent = client.post(WRITES[0][0], headers=auth(admin), json=WRITES[0][1])
    assert continent.status_code == 201
    region = client.post(WRITES[1][0], headers=auth(admin), json={**WRITES[1][1], "continent_id": continent.json()["id"]})
    assert region.status_code == 201
    country = client.post(WRITES[2][0], headers=auth(admin), json={**WRITES[2][1], "region_id": region.json()["id"]})
    assert country.status_code == 201
    # POST /cities is admin-only too (above); its create itself fails on a pre-existing schema/model mismatch
    # (`state_province`), reported separately and not changed here.


def test_reading_geography_stays_open(client, ledger):
    db = ledger
    admin, user = member(db, "boss", admin=True), member(db, "m1", wallet=None)
    continent = client.post(WRITES[0][0], headers=auth(admin), json=WRITES[0][1]).json()
    region = client.post(WRITES[1][0], headers=auth(admin),
                         json={**WRITES[1][1], "continent_id": continent["id"]}).json()
    for headers in ({}, auth(user)):
        listed = client.get("/api/v1/geography/continents", headers=headers)
        assert listed.status_code == 200 and [c["name"] for c in listed.json()] == ["Synthetica"]
        assert client.get(f"/api/v1/geography/continents/{continent['id']}/regions",
                          headers=headers).json()[0]["id"] == region["id"]
        assert client.get(f"/api/v1/geography/regions/{region['id']}", headers=headers).status_code == 200


def test_no_geography_write_route_is_left_to_ordinary_members(app):
    from fastapi.routing import APIRoute

    from app.api import deps

    writes = [r for r in app.routes if isinstance(r, APIRoute) and r.path.startswith("/api/v1/geography")
              and r.methods & {"POST", "PUT", "PATCH", "DELETE"}]
    assert len(writes) == 5
    for route in writes:
        calls = {d.call for d in route.dependant.dependencies}
        assert deps.get_current_admin_user in calls, route.path
