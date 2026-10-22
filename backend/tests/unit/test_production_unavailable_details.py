"""Production error handler (main.http_exception_handler) and deliberate 502/503s.

Root cause fixed: in production every HTTP
error of status 500 or more had its detail replaced by "Internal server error",
so the member never saw the fixed, member-safe "temporarily unavailable" text,
and the payment dialog lost detail.code. Unexpected errors stay masked; only a
502/503 whose detail is exactly {code, message} with an allowlisted code passes.

Every account and value is SYNTHETIC; no provider is reached.
"""
from __future__ import annotations

import asyncio
import json

import pytest
from fastapi import HTTPException
from starlette.requests import Request

import main
from app.models.checkout_gateway import CheckoutGatewaySettings
from app.models.payment import Deposit
from tests.unit.test_admin_security_hardening import code_of
from tests.unit.test_dual_cashout import configure as np_configure
from tests.unit.test_dual_cashout import ledger, no_network  # noqa: F401
from tests.unit.test_gateway_management import sp_off
from tests.unit.test_new_business_model import world  # noqa: F401
from tests.unit.test_soncopay_payments import buy, buyer, environment, fake, nowpayments_calls  # noqa: F401
from tests.unit.test_soncopay_payments import configure as sp_setup

pytestmark = pytest.mark.unit

SAFE = {"code": "CHECKOUT_UNAVAILABLE", "message": "Payments are temporarily unavailable. Please try again later."}


@pytest.fixture
def production(monkeypatch):
    monkeypatch.setattr(main, "IS_PRODUCTION", True)


def handled(exc: HTTPException) -> tuple:
    request = Request({"type": "http", "method": "POST", "path": "/api/v1/x", "headers": [], "query_string": b""})
    response = asyncio.run(main.http_exception_handler(request, exc))
    return response.status_code, json.loads(response.body)


@pytest.mark.parametrize("status_code", [502, 503])
@pytest.mark.parametrize("code", sorted(main.MEMBER_SAFE_UNAVAILABLE_CODES))
def test_an_allowlisted_unavailable_detail_reaches_the_member_in_production(production, status_code, code):
    detail = {"code": code, "message": "Fixed member-safe sentence."}
    assert handled(HTTPException(status_code=status_code, detail=detail)) == (status_code, {
        "detail": detail, "code": f"HTTP_{status_code}", "message": "Fixed member-safe sentence."})


@pytest.mark.parametrize("status_code, detail", [
    (500, SAFE),                                                          # a 500 is never passed through
    (504, SAFE),
    (503, "Kaluta KYC is not configured (no API key saved in Admin > KYC)."),
    (503, {"code": "SOMETHING_ELSE", "message": "internal text"}),
    (503, {**SAFE, "provider_answer": "secret provider text"}),           # any extra key masks it all
    (503, {"code": "CHECKOUT_UNAVAILABLE", "message": {"nested": "x"}}),
    (503, {"code": "CHECKOUT_UNAVAILABLE"}),
    (502, "The payment provider could not process this request."),
])
def test_everything_else_of_500_or_more_stays_masked_in_production(production, status_code, detail):
    assert handled(HTTPException(status_code=status_code, detail=detail)) == (status_code, {
        "detail": "Internal server error", "code": f"HTTP_{status_code}", "message": "Internal server error"})


def test_outside_production_and_below_500_nothing_changes(monkeypatch):
    monkeypatch.setattr(main, "IS_PRODUCTION", False)
    assert handled(HTTPException(status_code=500, detail="boom"))[1]["detail"] == "boom"
    monkeypatch.setattr(main, "IS_PRODUCTION", True)
    assert handled(HTTPException(status_code=409, detail={"code": "X", "message": "m"}))[1]["detail"] == {
        "code": "X", "message": "m"}


# ---- Payments, end to end, in production mode ------------------------------

def test_no_gateway_keeps_checkout_unavailable_in_production(production, client, ledger, fake, buyer,
                                                              nowpayments_calls):
    db = ledger
    boss = sp_setup(db, default=False)
    sp_off(db, boss)
    np_configure(db, provider_enabled=False)
    db.query(CheckoutGatewaySettings).update({"default_provider": "soncopay"})
    db.commit()
    refused = buy(client, buyer, "k-prod-503")
    assert (refused.status_code, code_of(refused)) == (503, "CHECKOUT_UNAVAILABLE")
    assert refused.json()["detail"] == SAFE and "Internal server error" not in refused.text
    assert db.query(Deposit).count() == 0 and nowpayments_calls == [] and fake.calls == []


def test_a_refused_provider_keeps_its_fixed_sentence_in_production(production, client, ledger, fake, buyer):
    db = ledger
    sp_setup(db)
    fake.fail_create = 422
    refused = buy(client, buyer, "k-prod-502")
    assert (refused.status_code, code_of(refused)) == (502, "PAYMENT_PROVIDER_UNAVAILABLE")
    assert refused.json()["detail"]["message"].startswith("The payment provider could not process this request.")
    assert "provider_down" not in refused.text and "Internal server error" not in refused.text
