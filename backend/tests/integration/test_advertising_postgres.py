"""Advertising on real PostgreSQL: migration a6c8e0f2b4d6 (upgrade/downgrade, defaults OFF, no price,
immutable origin trigger) and concurrent budget reservations (no overspend under parallel requests).
Runs only against a LOCAL server (POSTGRES_ADMIN_URL, default postgresql://postgres@127.0.0.1:5432/postgres)."""
from __future__ import annotations

import os
import threading
import uuid
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from tests.integration.test_payments_postgres import migrate
from tests.integration.test_month_end_locking_postgres import _build_schema

pytestmark = [pytest.mark.integration, pytest.mark.postgres]
ADMIN_URL = os.getenv("POSTGRES_ADMIN_URL", "postgresql://postgres@127.0.0.1:5432/postgres")
MIGRATION = "a6c8e0f2b4d6_advertising_placements_campaigns_sharing.py"
ADV_TABLES = ("adv_annualads_payments", "adv_allocations", "adv_adsense_months", "adv_adsense_buckets",
              "adv_adsense_imports", "adv_impression_events", "adv_serve_decisions", "adv_entry_origins",
              "adv_creatives", "adv_campaign_days", "adv_credit_movements", "adv_campaigns", "adv_settings")


@pytest.fixture
def pg():
    url = make_url(ADMIN_URL)
    if url.host not in ("127.0.0.1", "localhost", "::1"):
        pytest.skip("local PostgreSQL only")
    admin = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    name = f"mh5_adv_{uuid.uuid4().hex[:10]}"
    try:
        with admin.connect() as c:
            c.execute(text(f'CREATE DATABASE "{name}"'))
    except Exception:  # noqa: BLE001
        pytest.skip("PostgreSQL not available")
    engine = create_engine(url.set(database=name), pool_size=30, max_overflow=10,
                           connect_args={"options": "-c statement_timeout=15000"})
    try:
        _build_schema(engine)
        yield engine, sessionmaker(bind=engine, autocommit=False, autoflush=False)
    finally:
        engine.dispose()
        with admin.connect() as c:
            c.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


def _drop_model_tables(engine):
    with engine.begin() as c:
        for t in ADV_TABLES:
            c.execute(text(f"DROP TABLE IF EXISTS {t} CASCADE"))
        for code in ("1000", "2000", "4000", "5000"):
            c.execute(text("INSERT INTO chart_of_accounts (account_code, account_name, account_type, balance, is_active, "
                           "created_at, updated_at) SELECT :c, :c, CAST(:t AS accounttype), 0, true, now(), now() "
                           "WHERE NOT EXISTS (SELECT 1 FROM chart_of_accounts WHERE account_code = :c)"),
                      {"c": code, "t": {"1000": "ASSET", "2000": "LIABILITY", "4000": "REVENUE", "5000": "EXPENSE"}[code]})


def test_migration_upgrade_defaults_off_and_downgrade(pg):
    engine, _ = pg
    _drop_model_tables(engine)
    migrate(engine, MIGRATION, "upgrade")
    with engine.connect() as c:
        row = c.execute(text("SELECT cpm_rate_usd, campaigns_enabled, funding_enabled, contest_sharing_enabled, "
                             "adsense_sharing_enabled, adsense_fallback_enabled FROM adv_settings")).one()
        assert tuple(row) == (None, False, False, False, False, True)          # no price; money switches off
        codes = {r[0] for r in c.execute(text("SELECT account_code FROM chart_of_accounts"))}
        assert {"1240", "2320", "2322", "4020", "4021", "5006"} <= codes
        product = c.execute(text("SELECT price, has_affiliate_commission FROM product_types "
                                 "WHERE code = 'advertising_credit'")).one()
        assert (Decimal(str(product[0])), product[1]) == (Decimal("1.00"), False)
        assert c.execute(text("SELECT count(*) FROM permissions WHERE name = 'manage_advertising'")).scalar() == 1
        assert c.execute(text("SELECT count(*) FROM role_permissions rp JOIN permissions p ON p.id = rp.permission_id "
                              "WHERE p.name = 'manage_advertising'")).scalar() == 0   # held by nobody
    migrate(engine, MIGRATION, "downgrade")
    with engine.connect() as c:
        assert c.execute(text("SELECT to_regclass('public.adv_settings')")).scalar() is None
        assert c.execute(text("SELECT count(*) FROM product_types WHERE code = 'advertising_credit'")).scalar() == 0
    migrate(engine, MIGRATION, "upgrade")


def test_resolved_origin_is_immutable_in_the_database(pg):
    engine, _ = pg
    _drop_model_tables(engine)
    migrate(engine, MIGRATION, "upgrade")
    from app.models.contests import Contestant
    from app.models.user import User

    Session = sessionmaker(bind=engine)
    with Session() as db:
        user = User(email="o@t.com", hashed_password="x", is_active=True, is_deleted=False)
        db.add(user)
        db.flush()
        contestant = Contestant(user_id=user.id, entry_type="participation", is_active=True)
        db.add(contestant)
        db.commit()
        cid = contestant.id
    with engine.begin() as c:
        c.execute(text("INSERT INTO adv_entry_origins (contestant_id, origin_kind, status, created_at, updated_at) "
                       "VALUES (:c, 'PERSONAL_SUBMISSION', 'RESOLVED', now(), now())"), {"c": cid})
    with pytest.raises(Exception, match="cannot change"):
        with engine.begin() as c:
            c.execute(text("UPDATE adv_entry_origins SET origin_kind = 'NOMINATION'"))
    with pytest.raises(Exception, match="cannot change"):
        with engine.begin() as c:
            c.execute(text("DELETE FROM adv_entry_origins"))


def test_concurrent_reservations_never_exceed_budget_or_daily_cap(pg):
    """60 parallel decisions against a campaign with budget for 25 impressions and a daily cap of 20."""
    engine, Session = pg
    from app.models.advertising_v2 import AdvCampaign, AdvCampaignDay, AdvCreative, AdvSettings, AdvServeDecision
    from app.models.user import User
    from app.services import ad_delivery as dl

    with Session() as db:
        user = User(email="cc@t.com", hashed_password="x", is_active=True, is_deleted=False)
        db.add(user)
        db.flush()
        db.add(AdvSettings(cpm_rate_usd=Decimal("1000.00"), campaigns_enabled=True, funding_enabled=True,
                           frequency_cap_per_day=1000))
        now = datetime.utcnow()
        c = AdvCampaign(advertiser_user_id=user.id, name="cc", status="ACTIVE", cpm_rate_usd=Decimal("1000.00"),
                        budget_total=Decimal("25"), daily_cap=Decimal("20"), start_at=now - timedelta(days=1),
                        end_at=now + timedelta(days=1), placements=["IN_FEED"], targeting={})
        db.add(c)
        db.flush()
        db.add(AdvCreative(campaign_id=c.id, headline="h", destination_url="https://ex.com", review_status="APPROVED"))
        db.commit()
        campaign_id = c.id
    late = datetime.combine(datetime.utcnow().date(), datetime.max.time()) - timedelta(seconds=30)
    barrier = threading.Barrier(60)
    results, errors = [], []

    def worker(i):
        db = Session()
        try:
            barrier.wait()
            r = dl.decide(db, page_type="FEED", slot_kind="IN_FEED", slot_key="k", contestant_id=None,
                          viewer=f"v{i}", now=late)
            db.commit()
            results.append(r.get("source"))
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            errors.append(repr(exc))
        finally:
            db.close()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(60)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    with Session() as db:
        c = db.query(AdvCampaign).filter(AdvCampaign.id == campaign_id).one()
        day = db.query(AdvCampaignDay).filter(AdvCampaignDay.campaign_id == campaign_id).one()
        reserved = db.query(AdvServeDecision).filter(AdvServeDecision.state == "RESERVED").count()
        assert results.count("MYHIGH5") == reserved == 20             # the daily cap, exactly
        assert c.reserved == Decimal("20") and day.reserved == Decimal("20")
        assert c.spent + c.reserved <= c.budget_total
