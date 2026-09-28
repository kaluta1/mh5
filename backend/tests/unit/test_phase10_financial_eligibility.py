"""Phase 10: prize, KYC-initiation and financial eligibility (MyHigh5 Child/Teen
Safety s.3, s.5, s.9, s.14, s.30-32).

Every user, policy, guardian, prize, commission and payment here is SYNTHETIC.
No real payment, payout, refund, withdrawal or KYC provider is ever called: the
provider entry points are replaced by recorders that FAIL the test if reached
where they must not be. Test ids refer to the Phase 10 matrix (A..AN).
"""
from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal

import pytest

from app.core.child_safety import (
    AgeTier,
    ContentRating,
    GuardianConsentScope as S,
    PolicyOperation,
)
from app.models.accounting import AccountType, ChartOfAccounts, JournalEntry, JournalLine
from app.models.affiliate import AffiliateCashoutRequest, AffiliateCommission, CommissionStatus, CommissionType
from app.models.age_safety import AgeSafetyEvent, UserAgeProfile
from app.models.contest import Contest, ContestEntry, ContestVote
from app.models.media import Media
from app.models.payment import Deposit
from app.models.prize import Prize, PrizeType, PrizeWinner
from app.models.user import User
from app.services import commission_payout_service as payouts
from app.services import financial_eligibility as fe
from app.services import viewer_access as va
from app.services.financial_eligibility import FinancialOperation as Op, Outcome
from tests.unit.test_age_gate_registration import auth
from tests.unit.test_age_policy_engine import add_policy
from tests.unit.test_phase5_contest_eligibility import (  # noqa: F401
    accept_admin_review,
    contest,
    enforce,
    person,
    rule,
    verified_guardian,
)
from tests.unit.test_phase6_content_safety import role_user
from tests.unit.test_phase7_age_safe_delivery import gov
from tests.unit.test_new_business_model import world  # noqa: F401  (fixture)

CR_ADULT = ContentRating.ADULT_18_PLUS

# The member's own next step (e.g. ADD_DATE_OF_BIRTH) is allowed; DOB values/keys are not.
FORBIDDEN_IN_PAYLOADS = ('"date_of_birth"', "1990-", "1996-", "2010-", "guardian", "AGE_REQUIRED", "MINOR", "BELOW_MINIMUM_AGE",
                         "kyc_documents", "private_kyc", "reasons")


# ---------------------------------------------------------------------------
# Synthetic people and provider blockers
# ---------------------------------------------------------------------------

def adult(db, *, verified=False, **kw):
    u = person(db, 30, **kw)
    if verified:
        assure(db, u)
    return u


def assure(db, user, level="IDENTITY_AND_AGE_VERIFIED"):
    db.add(UserAgeProfile(user_id=user.id, assurance_level=level, review_status="NONE"))
    db.commit()


def unknown(db):
    return person(db, None)


def minor(db, age=15, **kw):
    return person(db, age, **kw)


@pytest.fixture
def provider(monkeypatch):
    """Payout provider replaced by a recorder; payouts reported configured."""
    calls = []

    def fake(**kwargs):
        calls.append(kwargs)
        return {"id": f"p10-{len(calls)}"}

    monkeypatch.setattr(payouts, "payouts_configured", lambda: True)
    monkeypatch.setattr(payouts, "send_single_payout_sync", fake)
    return calls


@pytest.fixture
def no_kyc_provider(monkeypatch):
    """Any real KYC provider session start fails the test."""
    from app.services import kaluta_kyc, shufti_pro

    def boom(*_a, **_k):
        raise AssertionError("a real KYC provider was called")

    monkeypatch.setattr(kaluta_kyc.kaluta_kyc_service, "create_session", boom)
    monkeypatch.setattr(shufti_pro.shufti_pro_service, "initiate_verification", boom)


@pytest.fixture
def no_payment_provider(monkeypatch):
    from app.api.api_v1.endpoints import payments as payments_api

    def boom(*_a, **_k):
        raise AssertionError("a real payment provider was called")

    monkeypatch.setattr(payments_api, "now_create_payment", boom)


def ledger_accounts(db):
    for code, kind in (("1001", AccountType.ASSET), ("2001", AccountType.LIABILITY),
                       ("2002", AccountType.LIABILITY), ("4005", AccountType.REVENUE)):
        if not db.query(ChartOfAccounts).filter(ChartOfAccounts.account_code == code).first():
            db.add(ChartOfAccounts(account_code=code, account_name=code, account_type=kind))
    db.commit()


def earnings(db, user, amounts=("60.00", "60.00")):
    """APPROVED commissions (earned history) + a payout wallet."""
    ledger_accounts(db)
    user.usdt_wallet_address, user.payout_currency = "0x" + "b" * 40, "usdtbsc"
    src = person(db, 40)
    rows = []
    for i, amount in enumerate(amounts, start=1):
        row = AffiliateCommission(user_id=user.id, source_user_id=src.id, commission_type=CommissionType.KYC_PAYMENT,
                                  level=i, base_amount=Decimal("600.00"), commission_amount=Decimal(amount),
                                  status=CommissionStatus.APPROVED)
        db.add(row)
        rows.append(row)
    db.commit()
    return rows


def snapshot(db, user_id):
    rows = db.query(AffiliateCommission).filter(AffiliateCommission.user_id == user_id).order_by(AffiliateCommission.id)
    return [(r.id, str(r.commission_amount), r.status, r.payout_reference) for r in rows]


def fin_fingerprint(db):
    return (db.query(AffiliateCashoutRequest).count(), db.query(JournalEntry).count(), db.query(JournalLine).count(),
            db.query(Deposit).count())


def withdraw(client, user, amount=120, key="k1"):
    return client.post("/api/v1/wallet/withdraw", json={"amount": amount},
                       headers={**auth(user), "Idempotency-Key": key})


def payload_is_generic(text):
    return not any(term.lower() in text.lower() for term in FORBIDDEN_IN_PAYLOADS)


# ---------------------------------------------------------------------------
# Synthetic contest result with a prize
# ---------------------------------------------------------------------------

def result_with_prize(db, winner, prize_type=PrizeType.PHYSICAL_ITEM, runner_up=None, c=None):
    c = c or contest(db)
    entries = []
    for rank, u in enumerate([winner] + ([runner_up] if runner_up else []), start=1):
        m = Media(title="m", media_type="image", path="p", url=f"/api/v1/media/file/{u.id}/a.jpg", user_id=u.id)
        db.add(m)
        db.flush()
        e = ContestEntry(contest_id=c.id, user_id=u.id, media_id=m.id, total_score=100 - rank, rank=rank)
        db.add(e)
        db.flush()
        db.add(ContestVote(entry_id=e.id, user_id=person(db, 30).id, score=5))
        entries.append(e)
    prize = Prize(contest_id=c.id, position=1, prize_type=prize_type, value=Decimal("500.00"), currency="USD",
                  title="First prize", requires_shipping=prize_type == PrizeType.PHYSICAL_ITEM)
    db.add(prize)
    db.flush()
    pw = PrizeWinner(prize_id=prize.id, user_id=winner.id, contest_entry_id=entries[0].id,
                     delivery_address="12 Private Road, Arusha")
    db.add(pw)
    db.commit()
    return pw, entries


def result_fingerprint(db, contest_id):
    entries = db.query(ContestEntry).filter(ContestEntry.contest_id == contest_id).order_by(ContestEntry.id).all()
    votes = db.query(ContestVote).filter(ContestVote.entry_id.in_([e.id for e in entries])).order_by(ContestVote.id)
    winners = db.query(PrizeWinner).order_by(PrizeWinner.id).all()
    return ([(e.id, e.user_id, e.total_score, e.rank) for e in entries], [(v.id, v.score) for v in votes],
            [(w.id, w.prize_id, w.user_id, w.is_claimed, w.is_delivered) for w in winners])


# ===========================================================================
# PRIZES (A-K)
# ===========================================================================

def test_A_confirmed_adult_winner_proceeds(db):
    a = adult(db, verified=True)
    pw, _ = result_with_prize(db, a)
    assert fe.guard_prize_fulfillment(db, pw, actor_id=None).allowed
    pw2, _ = result_with_prize(db, adult(db, verified=True), PrizeType.CASH)
    assert fe.prize_fulfillment_decision(db, pw2).operation == Op.MONETARY_PRIZE_PAYOUT
    assert fe.prize_fulfillment_decision(db, pw2).allowed


def test_A_prize_claim_needs_identity_and_age_verification_even_for_adults(db):
    # s.5: prize payment / binding agreement -> identity + age verification. A self-declared DOB is not enough.
    pw, _ = result_with_prize(db, adult(db))
    d = fe.prize_fulfillment_decision(db, pw)
    assert d.outcome == Outcome.HOLD and d.next_step == fe.NextStep.VERIFY_AGE


def test_B_L_AE_unknown_winner_is_never_adult_even_with_kyc(db):
    u = unknown(db)
    u.identity_verified = True                   # KYC APPROVED
    db.commit()
    assure(db, u)                                # even a stored assurance level without a DOB
    pw, _ = result_with_prize(db, u, PrizeType.CASH)
    for op in (Op.PRIZE_CLAIM, Op.MONETARY_PRIZE_PAYOUT, Op.DIGITAL_ASSET_PRIZE, Op.WITHDRAWAL, Op.KYC_INITIATION,
               Op.FINANCIAL_CONTRACT):
        d = fe.evaluate(db, u, op)
        assert d.outcome == Outcome.HOLD and d.next_step == fe.NextStep.ADD_DATE_OF_BIRTH, op
    assert va.viewer_for(db, u).tier == AgeTier.UNKNOWN    # L/AE: KYC never changes the tier
    assert not fe.prize_fulfillment_decision(db, pw).allowed


def test_C_D_E_AF_AK_minor_winner_keeps_result_no_substitute_no_rank_change(db):
    m, runner = minor(db, 16), adult(db, verified=True)
    pw, entries = result_with_prize(db, m, PrizeType.CASH, runner_up=runner)
    before = result_fingerprint(db, entries[0].contest_id)
    with pytest.raises(fe.FinancialEligibilityHold) as exc:
        fe.guard_prize_fulfillment(db, pw, actor_id=None)
    assert exc.value.decision.outcome in (Outcome.HOLD, Outcome.REVIEW_REQUIRED)
    db.expire_all()
    assert result_fingerprint(db, entries[0].contest_id) == before       # C/D/E: nothing rewritten
    assert db.query(PrizeWinner).count() == 1 and db.query(PrizeWinner).one().user_id == m.id   # D: no substitute
    ev = db.query(AgeSafetyEvent).filter(AgeSafetyEvent.event_type.like("FINANCIAL_ACTION_%")).all()
    assert ev and ev[-1].details["prize_winner_id"] == pw.id and payload_is_generic(json.dumps(ev[-1].details)
                                                                                    .replace("reasons", ""))


def test_F_G_prize_types_use_separate_operations(db):
    ops = {t: fe.prize_operation(Prize(prize_type=t)) for t in PrizeType}
    assert ops[PrizeType.CASH] == ops[PrizeType.GIFT_CARD] == ops[PrizeType.CREDITS] == Op.MONETARY_PRIZE_PAYOUT
    assert ops[PrizeType.DIGITAL_ITEM] == Op.DIGITAL_ASSET_PRIZE
    assert ops[PrizeType.PHYSICAL_ITEM] == ops[PrizeType.EXPERIENCE] == Op.PRIZE_FULFILLMENT
    # G: no digital-asset policy is configured -> minors are always reviewed, even with all consent.
    m = minor(db, 17)
    assert fe.evaluate(db, m, Op.DIGITAL_ASSET_PRIZE).outcome == Outcome.REVIEW_REQUIRED
    # F: a monetary payout needs BOTH prize acceptance and financial payment decisions.
    spec = fe.SPECS[Op.MONETARY_PRIZE_PAYOUT]
    assert set(spec.policy_operations) == {PolicyOperation.PRIZE_CONTRACT, PolicyOperation.PAYMENT}
    assert set(spec.consent_scopes) == {S.PRIZE_ACCEPTANCE, S.FINANCIAL_PAYMENT}


def test_H_physical_fulfilment_never_exposes_minor_delivery_data(db):
    m = minor(db, 16)
    pw, _ = result_with_prize(db, m)
    admin, reviewer = role_user(db, "admin"), role_user(db, "child_safety_resolve")
    assert "delivery_address" not in fe.fulfillment_view(db, pw, admin)       # ordinary admin: no address
    assert "delivery_address" not in fe.fulfillment_view(db, pw, adult(db))
    assert "delivery_address" not in fe.fulfillment_view(db, pw, None)
    assert fe.fulfillment_view(db, pw, m)["delivery_address"]                 # the winner themself
    assert fe.fulfillment_view(db, pw, reviewer)["delivery_address"]          # explicit child-safety reviewer


def configured_minor_payment_policy(db):
    """SYNTHETIC TZ policy: minors may pay from 14 with guardian consent below 18."""
    add_policy(db, payment_minimum_age=14, parental_consent_age=18,
               kyc_requirement={"operations": []},
               age_assurance_level={"default": "SELF_DECLARED_DOB", "operations": {}},
               parental_consent_requirement={"operations": ["PAYMENT"]})
    enforce(db, PolicyOperation.PAYMENT)


def test_I_AI_guardian_consent_verified_and_scope_specific(db, accept_admin_review):
    configured_minor_payment_policy(db)
    m = minor(db, 15)
    d = fe.evaluate(db, m, Op.PAYMENT)
    assert d.outcome == Outcome.HOLD and d.next_step == fe.NextStep.GUARDIAN_CONSENT
    verified_guardian(db, m, scopes=[S.PRIZE_ACCEPTANCE, S.PUBLICITY])        # AI: other scopes do not count
    assert fe.evaluate(db, m, Op.PAYMENT).outcome == Outcome.HOLD
    m2 = minor(db, 15)
    verified_guardian(db, m2, scopes=[S.FINANCIAL_PAYMENT])
    assert fe.evaluate(db, m2, Op.PAYMENT).allowed                           # I: exactly the configured scope
    assert fe.evaluate(db, m2, Op.WITHDRAWAL).outcome == Outcome.REVIEW_REQUIRED   # AI: never unrelated operations


def test_I_without_configured_policy_minor_prize_is_reviewed_not_guessed(db, accept_admin_review):
    m = minor(db, 16)
    verified_guardian(db, m, scopes=[S.PRIZE_ACCEPTANCE, S.FINANCIAL_PAYMENT])
    d = fe.evaluate(db, m, Op.MONETARY_PRIZE_PAYOUT)
    assert d.outcome == Outcome.REVIEW_REQUIRED and fe.R.POLICY_NOT_ENFORCED in d.reasons   # no invented age


def test_J_M_sponsor_nominator_kyc_are_not_guardians(db):
    configured_minor_payment_policy(db)
    sponsor = adult(db, verified=True)
    m = minor(db, 15, sponsor_id=sponsor.id)
    m.identity_verified = True                                                 # M: KYC approved
    db.commit()
    nominator = adult(db)
    gov(db, m, rating=ContentRating.GENERAL)                                   # an entry exists
    for _ in (sponsor, nominator):
        d = fe.evaluate(db, m, Op.PAYMENT)
        assert d.outcome == Outcome.HOLD and fe.R.GUARDIAN_CONSENT_REQUIRED in d.reasons


def test_K_publicity_release_is_independent(db, accept_admin_review):
    m = minor(db, 16)
    assert fe.evaluate(db, m, Op.PUBLICITY_RELEASE).outcome == Outcome.HOLD
    verified_guardian(db, m, scopes=[S.PRIZE_ACCEPTANCE])
    assert fe.evaluate(db, m, Op.PUBLICITY_RELEASE).outcome == Outcome.HOLD   # prize consent != publicity
    m2 = minor(db, 16)
    verified_guardian(db, m2, scopes=[S.PUBLICITY])
    assert fe.evaluate(db, m2, Op.PUBLICITY_RELEASE).allowed
    assert not fe.evaluate(db, m2, Op.PRIZE_CLAIM).allowed                    # and publicity != prize
    assert fe.evaluate(db, m2, Op.FINANCIAL_CONTRACT).outcome == Outcome.REVIEW_REQUIRED   # no contract scope exists


def test_contest_prize_restrictions_are_reviewed_not_interpreted(db):
    c = contest(db)
    rule(db, scope_id=c.id, prize_restrictions={"note": "synthetic"})
    a = adult(db, verified=True)
    pw, _ = result_with_prize(db, a, c=c)
    d = fe.prize_fulfillment_decision(db, pw)
    assert d.outcome == Outcome.REVIEW_REQUIRED and fe.R.CONTEST_RESTRICTIONS_REVIEW in d.reasons


# ===========================================================================
# KYC (L-R)
# ===========================================================================

def test_L_N_kyc_approved_minor_is_not_adult_and_cannot_withdraw(db):
    m = minor(db, 16)
    m.identity_verified = True
    db.commit()
    assert va.viewer_for(db, m).tier == AgeTier.TEEN_16_17
    assert fe.evaluate(db, m, Op.WITHDRAWAL).outcome == Outcome.REVIEW_REQUIRED


def test_O_P_kyc_initiation_respects_age_and_never_reaches_a_provider(client, db, no_kyc_provider):
    for u, status_code, step in ((unknown(db), 403, "ADD_DATE_OF_BIRTH"), (minor(db, 16), 403, "WAIT_FOR_REVIEW")):
        from app.models.kyc import DocumentType

        submit_body = {"firstName": "S", "lastName": "T", "dateOfBirth": "2000-01-01T00:00:00", "nationality": "TZ",
                       "address": "synthetic", "documentType": list(DocumentType)[0].value, "issuingCountry": "TZ"}
        for path, body in (("/api/v1/kyc/initiate", {"residential_address": "x"}), ("/api/v1/kyc/submit", submit_body)):
            r = client.post(path, json=body, headers=auth(u))
            assert r.status_code == status_code, (path, r.text)
            assert r.json()["detail"]["next_step"] == step and payload_is_generic(r.text)
    assert fe.evaluate(db, adult(db), Op.KYC_INITIATION).allowed


def test_P_dispatcher_refuses_a_minor_before_any_provider_call(db, no_kyc_provider):
    import asyncio

    from app.services.kyc_provider_dispatch import initiate_kyc_session

    with pytest.raises(fe.FinancialEligibilityHold):
        asyncio.run(initiate_kyc_session(db=db, user=minor(db, 16), reference="r", language="EN",
                                         country_iso="TZ", residential_address=None))


def test_Q_R_eligibility_payloads_carry_no_kyc_or_protected_data(client, db):
    m = minor(db, 15)
    m.identity_verified = True
    db.commit()
    r = client.get("/api/v1/financial-eligibility/me", headers=auth(m))
    assert r.status_code == 200 and payload_is_generic(r.text)
    status = {i["operation"]: i["status"] for i in r.json()["items"]}
    assert status["WITHDRAWAL"] == status["KYC_INITIATION"] == "REVIEW_REQUIRED"
    assert status["PAYMENT"] == "ALLOWED"             # no configured payment restriction (not adulthood)
    r = client.get("/api/v1/wallet/withdraw/preview", headers=auth(m))
    assert r.status_code == 200 and r.json()["eligibility_status"] == "REVIEW_REQUIRED" and payload_is_generic(r.text)
    for ev in db.query(AgeSafetyEvent).filter(AgeSafetyEvent.event_type.like("FINANCIAL_%")).all():
        assert "date_of_birth" not in json.dumps(ev.details)


# ===========================================================================
# WITHDRAWALS / FINANCE (S-AD)
# ===========================================================================

def test_S_AA_AB_adult_withdrawal_works_and_replay_is_idempotent(client, db, provider):
    a = adult(db)
    earnings(db, a)
    r = withdraw(client, a, 120, "adult-1")
    assert r.status_code == 200, r.text
    again = withdraw(client, a, 120, "adult-1")                   # AA: same key -> no second payout
    assert again.status_code in (200, 409)
    assert len(provider) == 1                                      # AB/AD: exactly one (fake) provider call
    assert db.query(AffiliateCashoutRequest).count() == 1
    assert db.query(JournalEntry).filter(JournalEntry.description.like("Affiliate Cashout #%")).count() == 1


@pytest.mark.parametrize("who", ["unknown", "minor_kyc"])
def test_T_U_V_unknown_or_kyc_minor_cannot_withdraw_via_direct_endpoint(client, db, provider, who):
    u = unknown(db) if who == "unknown" else minor(db, 16, identity_verified=True)
    earnings(db, u)
    before, fp = snapshot(db, u.id), fin_fingerprint(db)
    r = withdraw(client, u)
    assert r.status_code == 403 and payload_is_generic(r.text)
    assert r.json()["detail"]["code"] in ("FINANCIAL_ACTION_UNAVAILABLE", "PENDING_SAFETY_REVIEW")
    assert provider == []                                           # AD
    db.expire_all()
    assert snapshot(db, u.id) == before and fin_fingerprint(db) == fp   # Z: earnings/balances untouched


def test_W_AH_admin_retry_and_wallet_autopay_do_not_bypass(client, db, provider):
    m = minor(db, 16)
    earnings(db, m)
    before = snapshot(db, m.id)
    admin = role_user(db, "admin")
    admin.is_admin = True
    db.commit()
    r = client.post(f"/api/v1/admin/affiliate/retry-payouts?user_id={m.id}", headers=auth(admin))
    assert r.status_code == 200 and r.json()["retried"] == 0
    r = client.patch("/api/v1/users/me/wallet", json={"usdt_wallet_address": "0x" + "c" * 40,
                                                       "payout_currency": "usdtbsc"}, headers=auth(m))
    assert r.status_code == 200
    assert provider == []
    db.expire_all()
    assert [(i, a, s) for i, a, s, _ in snapshot(db, m.id)] == [(i, a, s) for i, a, s, _ in before]


def test_W_AH_leaders_admin_record_payout_uses_the_gate(db):
    from app.models.business_model import LeadersAllocationLine, LeadersPeriod
    from app.services import leaders_service

    m = minor(db, 16)
    period = LeadersPeriod(period_year=2026, period_month=9, status="POSTED", revenue_definition="synthetic",
                           eligible_company_revenue=Decimal("100.00"), pool_rate=Decimal("0.2500"),
                           pool_amount=Decimal("25.00"), max_members=10, snapshot_sha256="0" * 64)
    db.add(period)
    db.flush()
    line = LeadersAllocationLine(period_id=period.id, user_id=m.id, rank=1, direct_commission_amount=Decimal("10"),
                                 ratio=Decimal("1"), reward_amount=Decimal("25.00"), payout_status="UNPAID")
    db.add(line)
    db.commit()
    with pytest.raises(leaders_service.LeadersError):
        leaders_service.record_external_payout(db, line_id=line.id, reference="synthetic")
    db.rollback()
    db.expire_all()
    assert db.query(LeadersAllocationLine).get(line.id).payout_status == "UNPAID"   # earned reward kept
    assert db.query(JournalEntry).count() == 0


def test_X_toctou_recheck_before_provider_releases_reservation(db, provider, monkeypatch):
    a = adult(db)
    rows = earnings(db, a)
    before = snapshot(db, a.id)
    real = payouts.evaluate_financial_eligibility
    calls = {"n": 0}

    def flip(db_, user, op, **kw):          # allowed at reservation, restricted just before the provider
        calls["n"] += 1
        if calls["n"] >= 2:
            return fe.Decision(op, Outcome.REVIEW_REQUIRED, (fe.R.CHILD_SAFETY_REVIEW,))
        return real(db_, user, op, **kw)

    monkeypatch.setattr(payouts, "evaluate_financial_eligibility", flip)
    with pytest.raises(fe.FinancialEligibilityHold):
        payouts.process_manual_withdrawal_sync(db, a, Decimal("120.00"), idempotency_key="race")
    assert provider == []
    db.expire_all()
    assert snapshot(db, a.id) == before                         # reservation released, nothing paid
    assert db.query(AffiliateCashoutRequest).one().status == "failed"
    assert db.query(JournalEntry).count() == 0
    monkeypatch.setattr(payouts, "evaluate_financial_eligibility", real)
    replay = payouts.process_manual_withdrawal_sync(db, a, Decimal("120.00"), idempotency_key="race")
    assert replay["status"] == "failed" and provider == []      # AA: same key never pays later
    assert all(r.status == CommissionStatus.APPROVED for r in rows)


def test_Y_completed_historical_withdrawal_is_untouched(db, provider):
    a = adult(db)
    earnings(db, a)
    payouts.process_manual_withdrawal_sync(db, a, Decimal("120.00"), idempotency_key="hist")
    done = db.query(AffiliateCashoutRequest).one()
    frozen = (done.id, done.status, str(done.net_amount), done.payout_reference)
    a.date_of_birth = None                                       # the member later becomes UNKNOWN
    db.commit()
    assert fe.evaluate(db, a, Op.WITHDRAWAL).outcome == Outcome.HOLD
    db.expire_all()
    done = db.query(AffiliateCashoutRequest).one()
    assert (done.id, done.status, str(done.net_amount), done.payout_reference) == frozen
    assert all(r.status == CommissionStatus.PAID for r in db.query(AffiliateCommission).all())


def test_AC_refund_and_reversal_paths_are_unchanged(db):
    """The gate is not wired into refunds/reversals: the marketplace refund of a
    minor seller's order (money back to the buyer) is never blocked by it."""
    import inspect

    from app.services import financial_reversal, marketplace_service

    assert "financial_eligibility" not in inspect.getsource(financial_reversal)
    src = inspect.getsource(marketplace_service.resolve_dispute)
    assert 'if outcome == "RELEASE":' in src and "request_refund" in src


@pytest.fixture
def fake_payment_provider(monkeypatch):
    """The payment provider replaced by a recorder (no network, no real invoice)."""
    from app.api.api_v1.endpoints import payments as payments_api

    calls = []

    async def fake(**kwargs):
        calls.append(kwargs)
        return {"payment_id": f"p10-pay-{len(calls)}", "payment_status": "waiting", "pay_address": "synthetic",
                "pay_amount": str(kwargs.get("price_amount")), "pay_currency": "usdtbsc"}

    monkeypatch.setattr(payments_api, "now_create_payment", fake)
    return calls


def product(db, code="p10_ordinary", price="10.00"):
    from app.models.payment import ProductType

    db.add(ProductType(code=code, name=code, price=Decimal(price), currency="USD", is_active=True))
    db.commit()


def pay(client, user, code="p10_ordinary", amount="10.00", key="p10-key"):
    return client.post("/api/v1/payments/create", json={"product_code": code, "amount": amount, "currency": "usd"},
                       headers={**auth(user), "Idempotency-Key": key})


def test_PAY_A_C_unknown_ordinary_payment_is_not_an_adult_classification(client, db, fake_payment_provider):
    product(db)
    u = unknown(db)
    d = fe.evaluate(db, u, Op.PAYMENT)
    assert d.allowed and d.reasons == (fe.R.NO_CONFIGURED_RESTRICTION,)
    r = pay(client, u)
    assert r.status_code == 200, r.text                                          # A
    assert len(fake_payment_provider) == 1 and db.query(Deposit).count() == 1
    assert va.viewer_for(db, u).tier == AgeTier.UNKNOWN                          # C: tier unchanged
    assert CR_ADULT not in va.viewer_for(db, u).allowed_ratings
    for op in (Op.WITHDRAWAL, Op.KYC_INITIATION, Op.MONETARY_PRIZE_PAYOUT, Op.DIGITAL_ASSET_PRIZE,
               Op.FINANCIAL_CONTRACT, Op.PRIZE_CLAIM):
        assert not fe.evaluate(db, u, op).allowed, op                           # D-H: adult-only stays closed


def test_PAY_B_M_unknown_membership_payment_keeps_business_rules(client, world, fake_payment_provider):
    """(Was the $100 Referral Pool entry; the pool is retired, so a NEW_V2 platform product is used.)"""
    db = world
    u = unknown(db)
    jl, je = db.query(JournalLine).count(), db.query(JournalEntry).count()
    comm = db.query(AffiliateCommission).count()
    r = pay(client, u, "annual_membership", "50.00", key="annual-1")
    assert r.status_code == 200, r.text                                          # B: no new DOB requirement
    assert fake_payment_provider[0]["price_amount"] == Decimal("50.00")          # M: price unchanged
    again = pay(client, u, "annual_membership", "50.00", key="annual-1")        # L: idempotent replay
    assert again.status_code == 200 and again.json()["deposit_id"] == r.json()["deposit_id"]
    assert len(fake_payment_provider) == 1
    assert db.query(Deposit).filter(Deposit.user_id == u.id).count() == 1
    # M: nothing is recognised, committed or journalled at invoice time (unchanged: that happens on confirmation).
    assert (db.query(JournalLine).count(), db.query(JournalEntry).count(), db.query(AffiliateCommission).count()) \
        == (jl, je, comm)


def test_PAY_retired_referral_pool_checkout_is_gone_for_everyone(client, world, fake_payment_provider):
    from app.models.business_model import ReferralPoolMembership
    from app.services.new_model_reference_data import REFERRAL_POOL_PRODUCT_CODE

    db = world
    for u in (unknown(db), person(db, 30)):
        r = pay(client, u, REFERRAL_POOL_PRODUCT_CODE, "100.00", key=f"pool-{u.id}")
        assert r.status_code == 410 and "retired" in r.json()["detail"].lower()
    assert fake_payment_provider == []
    assert db.query(Deposit).count() == 0 and db.query(ReferralPoolMembership).count() == 0


def test_PAY_I_explicit_jurisdiction_restriction_blocks_unknown_before_any_deposit(client, db, no_payment_provider):
    product(db)
    add_policy(db)
    enforce(db, PolicyOperation.PAYMENT)                  # an operator-configured restriction for TZ
    u = unknown(db)
    r = pay(client, u)
    assert r.status_code == 403 and r.json()["detail"]["next_step"] == "ADD_DATE_OF_BIRTH"
    assert payload_is_generic(r.text) and db.query(Deposit).count() == 0
    other = person(db, None, country="Kenya")             # restriction is per configured jurisdiction
    assert fe.evaluate(db, other, Op.PAYMENT).allowed
    enforce(db, PolicyOperation.PAYMENT, jurisdiction="*")
    assert fe.evaluate(db, other, Op.PAYMENT).outcome in (Outcome.HOLD, Outcome.REVIEW_REQUIRED)


def test_PAY_J_minor_payment_follows_configured_policy_not_adult_authorization(db, accept_admin_review):
    m = minor(db, 15)
    d = fe.evaluate(db, m, Op.PAYMENT)
    assert d.allowed and d.reasons == (fe.R.NO_CONFIGURED_RESTRICTION,)          # nothing manufactured
    assert va.viewer_for(db, m).tier == AgeTier.TEEN_13_15                        # still a minor
    assert fe.evaluate(db, m, Op.WITHDRAWAL).outcome == Outcome.REVIEW_REQUIRED   # no adult authority gained
    configured_minor_payment_policy(db)                                            # TZ: 14+, consent below 18
    assert fe.evaluate(db, m, Op.PAYMENT).next_step == fe.NextStep.GUARDIAN_CONSENT
    assert fe.evaluate(db, minor(db, 13), Op.PAYMENT).outcome == Outcome.HOLD     # below the configured minimum
    verified_guardian(db, m, scopes=[S.FINANCIAL_PAYMENT])
    assert fe.evaluate(db, m, Op.PAYMENT).allowed


def test_PAY_K_L_confirmed_adult_payments_and_idempotency_unchanged(client, db, fake_payment_provider):
    product(db)
    a = adult(db)
    first, second = pay(client, a, key="adult-pay"), pay(client, a, key="adult-pay")
    assert first.status_code == second.status_code == 200
    assert first.json()["deposit_id"] == second.json()["deposit_id"]
    assert len(fake_payment_provider) == 1 and db.query(Deposit).count() == 1


def test_PAY_account_and_child_safety_state_still_apply_to_payments(db):
    u = unknown(db)
    gov(db, u, state="CHILD_SAFETY_ESCALATED", escalated=True, rating=None)
    assert fe.evaluate(db, u, Op.PAYMENT).outcome == Outcome.REVIEW_REQUIRED
    inactive = adult(db)
    inactive.is_active = False
    db.commit()
    assert fe.evaluate(db, inactive, Op.PAYMENT).outcome == Outcome.HOLD


def test_marketplace_buyer_and_seller_are_gated(db):
    from app.services import marketplace_service as ms

    m = minor(db, 16)
    ms._require_financial(db, m.id, Op.PAYMENT, {"market_item_type": "x"})      # no configured payment restriction
    with pytest.raises(fe.FinancialEligibilityHold):
        ms._require_financial(db, m.id, Op.WITHDRAWAL, {"market_item_type": "x"})   # the seller side stays strict
    ms._require_financial(db, adult(db).id, Op.PAYMENT, {"market_item_type": "x"})   # adults unchanged


# ===========================================================================
# CROSS-PHASE (AE-AN)
# ===========================================================================

def test_AG_forged_ids_and_other_users_cannot_bypass(client, db, provider):
    m, a = minor(db, 16), adult(db)
    earnings(db, m)
    # A member cannot act for another member: the withdrawal always uses the caller's own identity.
    r = client.post("/api/v1/wallet/withdraw", json={"amount": 120, "user_id": a.id},
                    headers={**auth(m), "Idempotency-Key": "forge"})
    assert r.status_code in (403, 422) and provider == []


def test_AJ_phase9_interaction_state_grants_nothing_financial(db):
    from app.models.interaction_safety import UserBlock
    from app.models.social_group import GroupMember, GroupType, SocialGroup

    m, a = minor(db, 16), adult(db, verified=True)
    g = SocialGroup(name="G", group_type=GroupType.PUBLIC, creator_id=a.id, member_count=2)
    db.add(g)
    db.flush()
    db.add_all([GroupMember(group_id=g.id, user_id=a.id), GroupMember(group_id=g.id, user_id=m.id)])
    db.commit()
    assert fe.evaluate(db, m, Op.WITHDRAWAL).outcome == Outcome.REVIEW_REQUIRED
    db.add(UserBlock(blocker_id=m.id, blocked_id=a.id))
    db.commit()
    assert fe.evaluate(db, a, Op.PAYMENT).allowed                 # a block is not a financial restriction


def test_AM_open_child_safety_escalation_stops_irreversible_actions(db, provider):
    a = adult(db, verified=True)
    earnings(db, a)
    gov(db, a, state="CHILD_SAFETY_ESCALATED", escalated=True, rating=None)
    for op in (Op.WITHDRAWAL, Op.PRIZE_CLAIM, Op.MONETARY_PRIZE_PAYOUT, Op.KYC_INITIATION, Op.PAYMENT):
        d = fe.evaluate(db, a, op)
        assert d.outcome == Outcome.REVIEW_REQUIRED and fe.R.CHILD_SAFETY_REVIEW in d.reasons
    with pytest.raises(fe.FinancialEligibilityHold):
        payouts.process_manual_withdrawal_sync(db, a, Decimal("120.00"), idempotency_key="esc")
    assert provider == []


def test_AN_age_review_state_is_authoritative(db):
    a = adult(db, verified=True)
    db.query(UserAgeProfile).filter(UserAgeProfile.user_id == a.id).update({"review_status": "AGE_REVIEW_REQUIRED"})
    db.commit()
    assert fe.evaluate(db, a, Op.WITHDRAWAL).outcome == Outcome.REVIEW_REQUIRED


def test_enforced_policy_governs_adults_too_with_kyc_as_additional_requirement_only(db):
    add_policy(db)                       # SYNTHETIC TZ: PAYMENT needs KYC + IDENTITY_AND_AGE_VERIFIED
    a = adult(db)
    assert fe.evaluate(db, a, Op.PAYMENT).allowed                  # not enforced: platform adult baseline
    enforce(db, PolicyOperation.PAYMENT)
    assert fe.evaluate(db, a, Op.PAYMENT).next_step == fe.NextStep.VERIFY_AGE
    assure(db, a)
    assert fe.evaluate(db, a, Op.PAYMENT).next_step == fe.NextStep.COMPLETE_KYC
    a.identity_verified = True
    db.commit()
    assert fe.evaluate(db, a, Op.PAYMENT).allowed


def test_evaluation_failure_fails_closed(db, monkeypatch):
    monkeypatch.setattr(fe, "_evaluate", lambda *a, **k: 1 / 0)
    d = fe.evaluate(db, adult(db), Op.WITHDRAWAL)
    assert d.outcome == Outcome.REVIEW_REQUIRED


def test_enforcement_switch_accepts_phase10_operations(db):
    from app.core.child_safety import ENFORCEABLE_OPERATIONS

    assert {PolicyOperation.PRIZE_CONTRACT, PolicyOperation.PAYMENT} <= ENFORCEABLE_OPERATIONS
    row = enforce(db, PolicyOperation.PRIZE_CONTRACT, enabled=False)
    assert row.enabled is False


def test_provider_blockers_trip_on_any_unexpected_call(no_kyc_provider, no_payment_provider):
    """The blockers used above really fail a test if a provider is reached."""
    import asyncio

    from app.api.api_v1.endpoints import payments as payments_api
    from app.services import kaluta_kyc, shufti_pro

    for call in (lambda: kaluta_kyc.kaluta_kyc_service.create_session(external_id="x", user=None),
                 lambda: shufti_pro.shufti_pro_service.initiate_verification(reference="x"),
                 lambda: payments_api.now_create_payment(price_amount=1)):
        with pytest.raises(AssertionError):
            result = call()
            if asyncio.iscoroutine(result):
                asyncio.run(result)
