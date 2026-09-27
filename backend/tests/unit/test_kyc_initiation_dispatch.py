"""KYC initiation provider-dispatch regression (the /kyc/initiate -> dispatcher
contract) plus the Phase 10 gate ordering around it.

Every user, deposit and provider response here is SYNTHETIC. Real network I/O
is impossible: httpx transports are replaced by a guard that FAILS the test,
and provider boundaries are replaced per test with monkeypatch (nothing in the
persistent configuration is changed; no real key, URL or credential is used).
"""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import httpx
import pytest
from sqlalchemy.orm import Session

from app.api.api_v1.endpoints import kyc as kyc_endpoint
from app.models.age_safety import UserAgeProfile
from app.models.kyc import KYCStatus, KYCVerification
from app.models.payment import Deposit, DepositStatus, ProductType
from app.services import kaluta_kyc, shufti_pro
from app.services import kyc_provider_dispatch as dispatch
from tests.unit.test_age_gate_registration import auth
from tests.unit.test_phase5_contest_eligibility import person
from tests.unit.test_phase6_content_safety import role_user
from tests.unit.test_phase7_age_safe_delivery import gov
from app.core.child_safety import ContentRating

INITIATE = "/api/v1/kyc/initiate"
ADDRESS = {"residential_address": "12 Synthetic Road, Arusha"}
FAKE_KEY = "test-only-not-a-real-key"


@pytest.fixture(autouse=True)
def no_real_network(monkeypatch):
    """Any real HTTP attempt (sync or async) fails the test. Only httpx's
    NETWORK transports are replaced; the in-process TestClient transport is not."""
    def boom(*_a, **_k):
        raise AssertionError("real network I/O attempted in a KYC test")

    async def aboom(*_a, **_k):
        raise AssertionError("real network I/O attempted in a KYC test")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", boom)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", aboom)


@pytest.fixture
def providers(monkeypatch):
    """Recorders at the provider boundary (both providers)."""
    calls = {"kaluta": [], "shufti": [], "validity": []}

    async def kaluta_create(*, external_id, user, country_iso=None, residential_address=None):
        calls["kaluta"].append({"external_id": external_id, "user_id": user.id, "country": country_iso,
                                "address": residential_address})
        return {"success": True, "session_id": f"sess-{len(calls['kaluta'])}",
                "verification_url": f"https://verify.invalid/s/{len(calls['kaluta'])}", "reference": external_id}

    async def shufti_init(*, reference, email, country=None, language="EN"):
        calls["shufti"].append({"reference": reference})
        return {"success": True, "verification_url": "https://shufti.invalid/v", "reference": reference}

    async def validity(verification):
        calls["validity"].append(verification.id)
        return {"is_valid": bool(verification.verification_url), "is_completed": False,
                "verification_url": verification.verification_url, "data": {}}

    monkeypatch.setattr(kaluta_kyc.kaluta_kyc_service, "create_session", kaluta_create)
    monkeypatch.setattr(kaluta_kyc.kaluta_kyc_service, "check_reference_validity", validity)
    monkeypatch.setattr(shufti_pro.shufti_pro_service, "initiate_verification", shufti_init)
    return calls


@pytest.fixture
def dispatcher_spy(monkeypatch):
    """Wraps the REAL dispatcher the endpoint calls, recording its kwargs."""
    seen = []
    real = dispatch.initiate_kyc_session

    async def spy(*args, **kwargs):
        seen.append({"args": args, **kwargs})
        return await real(*args, **kwargs)

    monkeypatch.setattr(kyc_endpoint, "initiate_kyc_session", spy)
    return seen


def kyc_paid(db, user):
    """A validated, unused KYC deposit (the existing precondition for a new attempt)."""
    product = db.query(ProductType).filter(ProductType.code == "kyc").first()
    if product is None:
        product = ProductType(code="kyc", name="KYC", price=Decimal("10.00"), currency="USD", is_active=True)
        db.add(product)
        db.flush()
    dep = Deposit(user_id=user.id, product_type_id=product.id, amount=Decimal("10.00"), currency="USD",
                  order_id=f"kyc-{user.id}-{datetime.utcnow().timestamp()}", status=DepositStatus.VALIDATED,
                  validated_at=datetime.utcnow() - timedelta(minutes=1))
    db.add(dep)
    db.commit()
    return dep


def adult(db, **kw):
    return person(db, 30, **kw)


def kyc_rows(db, user):
    return db.query(KYCVerification).filter(KYCVerification.user_id == user.id).all()


def no_provider_contact(providers):
    return not providers["kaluta"] and not providers["shufti"] and not providers["validity"]


# ===========================================================================
# ROOT BUG (A-F)
# ===========================================================================

def test_A_B_D_E_eligible_adult_reaches_the_mocked_provider_through_the_mounted_route(
        client, db, providers, dispatcher_spy):
    a = adult(db)
    kyc_paid(db, a)
    r = client.post(INITIATE, json=ADDRESS, headers=auth(a))
    assert r.status_code == 200, r.text                                                  # A
    assert len(dispatcher_spy) == 1
    call = dispatcher_spy[0]
    assert isinstance(call["db"], Session) and call["db"] is db                         # B: the live request session
    assert call["args"] == () and call["user"].id == a.id                                # D: keyword contract, auth user
    assert call["residential_address"] == ADDRESS["residential_address"]
    assert providers["kaluta"] == [{"external_id": call["reference"], "user_id": a.id, "country": call["country_iso"],
                                    "address": ADDRESS["residential_address"]}]
    body = r.json()                                                                       # E: existing contract
    assert set(body) == {"verification_url", "reference", "verification_id", "reused", "provider", "status",
                         "attempts_count", "max_attempts", "attempts_remaining"}
    assert body["status"] == "new" and body["reused"] is False and body["provider"] == "kaluta"
    assert body["reference"] == call["reference"] and body["verification_url"].startswith("https://verify.invalid/")
    row = kyc_rows(db, a)[0]
    assert row.status == KYCStatus.IN_PROGRESS and not row.identity_verified         # not verified by initiation


def test_C_the_old_call_contract_fails():
    """The pre-fix call (no db) cannot reach the dispatcher body at all."""
    import asyncio

    with pytest.raises(TypeError, match="db"):
        asyncio.run(dispatch.initiate_kyc_session(user=object(), reference="r", language="en",
                                                  country_iso=None, residential_address=None))


def test_C_the_endpoint_passes_db_explicitly():
    import inspect

    src = inspect.getsource(kyc_endpoint.initiate_shufti_verification)
    call = src[src.index("await initiate_kyc_session("):]
    call = call[:call.index(")\n")]
    assert "db=db" in call


def test_F_double_call_reuses_the_session_no_duplicate_record_or_payment(client, db, providers):
    a = adult(db)
    dep = kyc_paid(db, a)
    first = client.post(INITIATE, json=ADDRESS, headers=auth(a))
    second = client.post(INITIATE, json=ADDRESS, headers=auth(a))
    assert first.status_code == second.status_code == 200
    assert second.json()["reused"] is True and second.json()["verification_id"] == first.json()["verification_id"]
    assert len(providers["kaluta"]) == 1                     # existing reuse rule: one provider session
    assert len(kyc_rows(db, a)) == 1                          # one record per user (existing rule)
    db.refresh(dep)
    assert dep.is_used and db.query(Deposit).filter(Deposit.user_id == a.id).count() == 1
    assert kyc_rows(db, a)[0].attempts_count == 1


# ===========================================================================
# SAFETY GATE (G-N): provider call count must be 0
# ===========================================================================

def _blocked(client, db, providers, dispatcher_spy, user):
    kyc_paid(db, user)
    r = client.post(INITIATE, json=ADDRESS, headers=auth(user))
    assert r.status_code == 403, r.text
    assert r.json()["detail"]["code"] in ("FINANCIAL_ACTION_UNAVAILABLE", "PENDING_SAFETY_REVIEW")
    assert no_provider_contact(providers) and dispatcher_spy == []
    assert kyc_rows(db, user) == []                          # nothing written before the decision
    assert db.query(Deposit).filter(Deposit.user_id == user.id, Deposit.is_used == True).count() == 0  # noqa: E712
    return r


def test_G_unknown_age_is_held_before_dispatch(client, db, providers, dispatcher_spy):
    r = _blocked(client, db, providers, dispatcher_spy, person(db, None))
    assert r.json()["detail"]["next_step"] == "ADD_DATE_OF_BIRTH"


def test_H_minor_never_reaches_dispatch(client, db, providers, dispatcher_spy):
    _blocked(client, db, providers, dispatcher_spy, person(db, 16))
    _blocked(client, db, providers, dispatcher_spy, person(db, 12))


def test_I_open_child_safety_escalation_blocks_dispatch(client, db, providers, dispatcher_spy):
    a = adult(db)
    gov(db, a, state="CHILD_SAFETY_ESCALATED", escalated=True, rating=None)
    _blocked(client, db, providers, dispatcher_spy, a)


def test_J_open_age_review_blocks_dispatch(client, db, providers, dispatcher_spy):
    a = adult(db)
    db.add(UserAgeProfile(user_id=a.id, review_status="AGE_REVIEW_REQUIRED"))
    db.commit()
    _blocked(client, db, providers, dispatcher_spy, a)


def test_K_M_kyc_approved_minor_stays_a_minor(client, db, providers, dispatcher_spy):
    from app.core.child_safety import AgeTier
    from app.services import viewer_access as va

    m = person(db, 16, identity_verified=True)
    _blocked(client, db, providers, dispatcher_spy, m)
    assert va.viewer_for(db, m).tier == AgeTier.TEEN_16_17


def test_L_sponsor_is_not_guardian_authority(client, db, providers, dispatcher_spy):
    sponsor = adult(db)
    _blocked(client, db, providers, dispatcher_spy, person(db, 16, sponsor_id=sponsor.id))


def test_N_admin_status_is_not_a_bypass(client, db, providers, dispatcher_spy):
    admin = role_user(db, "admin")
    admin.is_admin, admin.date_of_birth = True, None           # admin without a DOB: UNKNOWN
    db.commit()
    _blocked(client, db, providers, dispatcher_spy, admin)


def test_dispatcher_itself_rechecks_before_any_provider(db, providers):
    """Defence in depth: even a direct call cannot reach a provider for UNKNOWN."""
    import asyncio

    from app.services.financial_eligibility import FinancialEligibilityHold

    with pytest.raises(FinancialEligibilityHold):
        asyncio.run(dispatch.initiate_kyc_session(db=db, user=person(db, None), reference="r", language="en",
                                                  country_iso="TZ", residential_address=None))
    assert no_provider_contact(providers)


# ===========================================================================
# PAYMENT -> KYC (section 10)
# ===========================================================================

def test_unknown_can_pay_for_kyc_but_cannot_start_it(client, db, providers, dispatcher_spy, monkeypatch):
    from app.api.api_v1.endpoints import payments as payments_api

    invoices = []

    async def fake_invoice(**kwargs):
        invoices.append(kwargs)
        return {"payment_id": "p-kyc-1", "payment_status": "waiting", "pay_address": "synthetic",
                "pay_amount": "10", "pay_currency": "usdtbsc"}

    monkeypatch.setattr(payments_api, "now_create_payment", fake_invoice)
    db.add(ProductType(code="kyc", name="KYC", price=Decimal("10.00"), currency="USD", is_active=True))
    db.commit()
    u = person(db, None)
    r = client.post("/api/v1/payments/create", json={"product_code": "kyc", "amount": "10.00", "currency": "usd"},
                    headers={**auth(u), "Idempotency-Key": "kyc-pay-1"})
    assert r.status_code == 200, r.text                        # payment unchanged (no configured restriction)
    dep = db.query(Deposit).filter(Deposit.user_id == u.id).one()
    dep.status, dep.validated_at = DepositStatus.VALIDATED, datetime.utcnow()   # as if the provider confirmed it
    db.commit()
    for _ in range(2):                                          # retrying KYC later
        k = client.post(INITIATE, json=ADDRESS, headers=auth(u))
        assert k.status_code == 403 and k.json()["detail"]["next_step"] == "ADD_DATE_OF_BIRTH"
    db.refresh(dep)
    assert not dep.is_used                                      # the payment stays valid for later
    assert db.query(Deposit).filter(Deposit.user_id == u.id).count() == 1 and len(invoices) == 1
    assert no_provider_contact(providers) and dispatcher_spy == []


# ===========================================================================
# PROVIDERS (sections 11-13)
# ===========================================================================

def test_provider_selection_is_unchanged(client, db, providers, monkeypatch):
    from app.core.config import settings

    a = adult(db)
    kyc_paid(db, a)
    assert client.post(INITIATE, json=ADDRESS, headers=auth(a)).json()["provider"] == "kaluta"
    assert len(providers["kaluta"]) == 1 and providers["shufti"] == []
    monkeypatch.setattr(settings, "KYC_PROVIDER", "shufti_pro")   # test-only override, reverted after the test
    b = adult(db)
    kyc_paid(db, b)
    r = client.post(INITIATE, json=ADDRESS, headers=auth(b))
    assert r.status_code == 200 and r.json()["provider"] == "shufti_pro"
    assert len(providers["shufti"]) == 1 and len(providers["kaluta"]) == 1


def test_disabled_kaluta_stays_disabled_and_fails_safely(client, db, monkeypatch):
    """With the real adapter and KALUTA_KYC_ENABLED off (the default), nothing is
    sent and the endpoint answers 503, as before."""
    monkeypatch.setattr(kaluta_kyc.kaluta_kyc_service, "enabled", False)
    a = adult(db)
    kyc_paid(db, a)
    r = client.post(INITIATE, json=ADDRESS, headers=auth(a))
    assert r.status_code == 503 and "disabled" in r.text
    row = kyc_rows(db, a)[0]
    assert row.status == KYCStatus.PENDING and not row.identity_verified and not row.verification_url


@pytest.mark.parametrize("kind", ["timeout", "rejected", "malformed"])
def test_provider_failures_are_safe_and_retryable(client, db, providers, monkeypatch, kind):
    """The REAL Kaluta adapter against a fake HTTP layer (test-only key, no network)."""
    real_create = kaluta_kyc.KalutaKYCService.create_session
    svc = kaluta_kyc.kaluta_kyc_service
    monkeypatch.setattr(svc, "create_session", real_create.__get__(svc))
    monkeypatch.setattr(svc, "enabled", True)
    monkeypatch.setattr(svc, "api_key", FAKE_KEY)

    async def fake_post(self, url, **kwargs):
        if kind == "timeout":
            raise httpx.ReadTimeout("synthetic timeout")
        if kind == "rejected":
            return httpx.Response(401, json={"detail": "synthetic rejection"}, request=httpx.Request("POST", url))
        return httpx.Response(201, json={"unexpected": True}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    a = adult(db)
    kyc_paid(db, a)
    r = client.post(INITIATE, json=ADDRESS, headers=auth(a))
    assert r.status_code >= 500
    assert FAKE_KEY not in r.text and "Traceback" not in r.text and "date_of_birth" not in r.text
    row = kyc_rows(db, a)[0]
    assert row.status != KYCStatus.APPROVED and not row.identity_verified and not row.verification_url
    assert not a.identity_verified
    # Retry (existing behavior): the same cycle is retried without a new payment or attempt.
    ok = []

    async def recorder(*, external_id, user, country_iso=None, residential_address=None):
        ok.append(external_id)
        return {"success": True, "session_id": "s-retry", "verification_url": "https://verify.invalid/retry"}

    monkeypatch.setattr(svc, "create_session", recorder)
    again = client.post(INITIATE, json=ADDRESS, headers=auth(a))
    assert again.status_code == 200 and again.json()["status"] == "new" and len(ok) == 1
    assert len(kyc_rows(db, a)) == 1 and kyc_rows(db, a)[0].attempts_count == 1


def test_network_guard_trips_on_any_real_request():
    import asyncio

    with pytest.raises(AssertionError, match="real network"):
        httpx.Client().get("https://kyc.invalid/")
    with pytest.raises(AssertionError, match="real network"):
        async def go():
            async with httpx.AsyncClient() as c:
                await c.post("https://kyc.invalid/sessions", json={})
        asyncio.run(go())


def test_initiation_response_carries_no_private_data(client, db, providers):
    a = adult(db)
    kyc_paid(db, a)
    r = client.post(INITIATE, json=ADDRESS, headers=auth(a))
    text = r.text
    for forbidden in ("date_of_birth", "private_kyc", "document", "proof", "guardian", FAKE_KEY, "api_key"):
        assert forbidden not in text.lower() if forbidden.islower() else forbidden not in text
