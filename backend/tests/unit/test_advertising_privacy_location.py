"""Lead privacy foundation and verified-location foundation (owner-approved 2026-11-05). Lead and Daily City stay
NOT READY in code. SYNTHETIC data only."""
from __future__ import annotations

import json
from datetime import timedelta
from decimal import Decimal

import pytest

from app.models.advertising_v2 import AdvGeoAttestation, AdvLead, AdvLeadAccess
from app.services import ad_campaigns as camp, ad_delivery as dl, ad_geo, ad_leads, ad_packages as pk
from tests.conftest import TEST_PAYMENT_SETTINGS_ENCRYPTION_KEY
from tests.unit.test_admin_security_hardening import PASSWORD, bearer, person
from tests.unit.test_advertising_phase_a import _city, _live, _resident, _settings
from tests.unit.test_advertising_program import T0, _fund
from tests.unit.test_new_business_model import _user, world  # noqa: F401

pytestmark = pytest.mark.unit
D = Decimal


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("PAYMENT_SETTINGS_ENCRYPTION_KEY", TEST_PAYMENT_SETTINGS_ENCRYPTION_KEY)


def _lead_campaign(db, adv):
    _settings(db)
    _fund(db, adv, "20.00")
    c = camp.create_campaign(db, adv, name="L", budget="10.00", start_at=T0 - timedelta(days=1),
                             end_at=T0 + timedelta(days=30), placements=["IN_FEED"])
    c.pricing_model = "LEAD"                     # Lead is NOT READY: the campaign is shaped directly for the test
    db.flush()
    return c


def _lead(db, c, contact="Person@Example.com", **kw):
    args = dict(campaign_id=c.id, name="Pat", contact=contact, consent=True, consent_version="c-v1",
                privacy_notice_version="pn-v1", advertiser_identity="Acme Coffee Ltd", decision_id=None, now=T0)
    args.update(kw)
    return ad_leads._record(db, **args)


def test_lead_collection_is_closed_and_needs_notice_identity_and_encryption(world, monkeypatch):
    db = world
    assert pk.PACKAGES["lead"].not_ready
    adv = _user(db, "lp1@t.com")
    c = _lead_campaign(db, adv)
    with pytest.raises(ad_leads.LeadError) as e:
        ad_leads.submit(db, campaign_id=c.id, name="N", contact="n@example.com", consent=True, consent_version="v1",
                        privacy_notice_version="pn-v1", advertiser_identity="Acme")
    assert e.value.code == "NOT_READY" and db.query(AdvLead).count() == 0
    with pytest.raises(ad_leads.LeadError) as e:
        _lead(db, c, privacy_notice_version=None)
    assert e.value.code == "PRIVACY_NOTICE_REQUIRED"
    monkeypatch.delenv("PAYMENT_SETTINGS_ENCRYPTION_KEY")
    monkeypatch.setattr("app.core.config.settings.PAYMENT_SETTINGS_ENCRYPTION_KEY", "", raising=False)
    with pytest.raises(ad_leads.LeadError) as e:
        _lead(db, c)
    assert e.value.code == "ENCRYPTION_UNAVAILABLE" and db.query(AdvLead).count() == 0


def test_contact_details_are_stored_only_encrypted_and_readable_only_by_authorised_roles(world):
    db = world
    adv, stranger = _user(db, "lp2@t.com"), _user(db, "lp2x@t.com")
    c = _lead_campaign(db, adv)
    lead = _lead(db, c)
    raw = json.dumps({"name": lead.pii_ciphertext})
    assert "Person@Example.com" not in raw and "Pat" not in raw and lead.pii_ciphertext.startswith("v1:")
    assert lead.advertiser_identity == "Acme Coffee Ltd" and lead.privacy_notice_version == "pn-v1"
    with pytest.raises(ad_leads.LeadError) as e:               # not yet accepted: the advertiser cannot read it
        ad_leads.read_details(db, lead.id, adv)
    assert e.value.code == "FORBIDDEN"
    lead.status, lead.decided_at = "ACCEPTED", T0               # (acceptance itself is tested in Phase A)
    db.flush()
    out = ad_leads.read_details(db, lead.id, adv, export=True)
    assert (out["name"], out["contact"]) == ("Pat", "Person@Example.com")
    with pytest.raises(ad_leads.LeadError) as e:
        ad_leads.read_details(db, lead.id, stranger)
    assert e.value.code == "FORBIDDEN"
    assert [a.action for a in db.query(AdvLeadAccess).all()] == ["EXPORT"]


def test_retention_purge_and_deletion_keep_financial_evidence(world):
    db = world
    adv = _user(db, "lp3@t.com")
    c = _lead_campaign(db, adv)
    rejected, accepted, fresh, pending = (_lead(db, c, contact=f"p{i}@example.com") for i in range(4))
    rejected.status, rejected.decided_at = "REJECTED", T0
    accepted.status, accepted.decided_at = "ACCEPTED", T0
    accepted.charged_amount, accepted.charge_day = D("0.25"), T0.date()
    fresh.status, fresh.decided_at = "EXPIRED", T0 + timedelta(days=20)
    db.flush()
    assert ad_leads.purge_expired(db, now=T0 + timedelta(days=31)) == 1           # rejected only (30 days)
    assert rejected.pii_ciphertext is None and rejected.pii_purged_at is not None
    assert accepted.pii_ciphertext is not None and fresh.pii_ciphertext is not None
    assert pending.pii_ciphertext is not None                                     # undecided: never purged
    assert ad_leads.purge_expired(db, now=T0 + timedelta(days=91)) == 2           # accepted (90) + expired (30)
    assert (accepted.status, accepted.charged_amount, accepted.charge_day) == ("ACCEPTED", D("0.25"), T0.date())
    assert accepted.contact_hash == f"erased:{accepted.id}"
    assert ad_leads.purge_expired(db, now=T0 + timedelta(days=200)) == 0          # idempotent
    ad_leads.request_deletion(db, pending.id, actor_id=adv.id)
    assert pending.pii_ciphertext is None and pending.deletion_requested_at is not None
    ad_leads.request_deletion(db, pending.id, actor_id=adv.id)                    # once
    acts = [a.action for a in db.query(AdvLeadAccess).order_by(AdvLeadAccess.id).all()]
    assert acts == ["PURGE", "PURGE", "PURGE", "DELETE"]
    with pytest.raises(ad_leads.LeadError) as e:
        ad_leads.read_details(db, accepted.id, person(db, "lp3adm", admin=True,
                                                      permissions=(camp.PERMISSION_MANAGE,)))
    assert e.value.code == "ERASED"


# ---------------------------------------------------------------- verified location

def test_attestation_has_provenance_and_needs_an_authorised_reviewer(world):
    db = world
    city = _city(db)
    m = _resident(db, city)
    row = db.query(AdvGeoAttestation).filter_by(user_id=m.id).one()
    assert (row.status, row.evidence_source, row.country_id, row.local_area_id) == (
        "ATTESTED", "KYC_ADDRESS_DECLARED_CITY", city.country_id, None)
    plain = _user(db, "geo-plain@t.com")
    with pytest.raises(ad_geo.GeoError) as e:
        ad_geo.review(db, row.id, actor=plain, decision="VERIFIED", note="checked doc")
    assert e.value.code == "FORBIDDEN"
    reviewer = person(db, "geo-rev", admin=True, permissions=(camp.PERMISSION_MANAGE,))
    self_row = ad_geo.attest_on_address_approval(db, reviewer, None) if reviewer.city_id else None
    assert self_row is None
    ad_geo.review(db, row.id, actor=reviewer, decision="VERIFIED", note="utility bill matches city")
    assert (row.status, row.reviewed_by_user_id) == ("VERIFIED", reviewer.id)
    assert dl.verified_city(db, m.id) == city.id
    with pytest.raises(ad_geo.GeoError) as e:
        ad_geo.review(db, row.id, actor=reviewer, decision="REJECTED", note="again")
    assert e.value.code == "ALREADY_REVIEWED"


def test_rejected_or_changed_location_is_never_verified_and_profile_city_alone_never_counts(world):
    db = world
    city, other = _city(db), _city(db, "Mombasa")
    reviewer = person(db, "geo-rev2", admin=True, permissions=(camp.PERMISSION_MANAGE,))
    m = _resident(db, city)
    row = db.query(AdvGeoAttestation).filter_by(user_id=m.id).one()
    ad_geo.review(db, row.id, actor=reviewer, decision="REJECTED", note="document is for another city")
    assert dl.verified_city(db, m.id) is None
    n = _resident(db, city)
    ad_geo.on_profile_city_change(db, n, other.id)
    assert dl.verified_city(db, n.id) is None
    plain = _user(db, "geo-np@t.com")
    plain.city_id, plain.address_verified = city.id, True        # editable profile city, no attestation
    db.flush()
    assert dl.verified_city(db, plain.id) is None
    self_m = _resident(db, city)
    self_m_row = db.query(AdvGeoAttestation).filter_by(user_id=self_m.id).one()
    with pytest.raises(ad_geo.GeoError) as e:
        ad_geo.review(db, self_m_row.id, actor=self_m, decision="VERIFIED", note="mine")
    assert e.value.code in ("FORBIDDEN", "SELF_REVIEW")


def test_geo_review_api_requires_permission_and_reauthentication(world, client):
    db = world
    city = _city(db)
    m = _resident(db, city)
    row = db.query(AdvGeoAttestation).filter_by(user_id=m.id).one()
    db.commit()
    plain = person(db, "geo-api-plain", admin=True)
    url = f"/api/v1/admin/advertising/geo-attestations/{row.id}/review"
    body = {"decision": "VERIFIED", "note": "checked", "current_password": PASSWORD}
    assert client.post(url, json=body, headers=bearer(plain)).status_code == 403
    reviewer = person(db, "geo-api-rev", admin=True, permissions=(camp.PERMISSION_MANAGE,))
    assert client.post(url, json={**body, "current_password": "wrong"}, headers=bearer(reviewer)).status_code == 403
    r = client.post(url, json=body, headers=bearer(reviewer))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "VERIFIED"
    listed = client.get("/api/v1/admin/advertising/geo-attestations?status=VERIFIED", headers=bearer(reviewer))
    assert [i["id"] for i in listed.json()["items"]] == [row.id]
