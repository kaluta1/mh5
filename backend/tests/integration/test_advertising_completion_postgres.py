"""Advertising completion (Prompt 4) on real PostgreSQL: migration e5a7c9e1f3b4 writes the approved prices only
where unset (audited), keeps every switch off, accepts the new review statuses and is reversible; concurrent
cancellation releases a campaign budget once. Runs only against a LOCAL server (POSTGRES_ADMIN_URL)."""
from __future__ import annotations

import threading
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text

from tests.integration.test_advertising_postgres import MIGRATION as ADVERTISING, _drop_model_tables, pg  # noqa: F401
from tests.integration.test_payments_postgres import migrate

pytestmark = [pytest.mark.integration, pytest.mark.postgres]
COMPLETION = "e5a7c9e1f3b4_advertising_completion.py"


def _user(engine, email):
    from sqlalchemy.orm import sessionmaker

    from app.models.user import User

    with sessionmaker(bind=engine)() as db:
        user = User(email=email, hashed_password="x", is_active=True, is_deleted=False)
        db.add(user)
        db.commit()
        return user.id


def test_prices_written_only_where_unset_switches_off_and_reversible(pg):  # noqa: F811
    engine, _ = pg
    _drop_model_tables(engine)
    migrate(engine, ADVERTISING, "upgrade")
    with engine.begin() as c:
        c.execute(text("UPDATE adv_settings SET cpm_rate_usd = 0.7500"))        # an administrator's existing value
    migrate(engine, COMPLETION, "upgrade")
    with engine.connect() as c:
        row = c.execute(text("SELECT cpm_rate_usd, min_campaign_budget_usd, campaigns_enabled, funding_enabled, "
                             "contest_sharing_enabled, adsense_sharing_enabled FROM adv_settings")).one()
        assert tuple(row) == (Decimal("0.7500"), Decimal("10.00"), False, False, False, False)
        audit = c.execute(text("SELECT action, new_values::text FROM audit_trails WHERE table_name = 'adv_settings'")).all()
        assert len(audit) == 1 and audit[0][0] == "APPROVED_PRICING" and '"0.7500"' in audit[0][1]
        cols = {r[0] for r in c.execute(text("SELECT column_name FROM information_schema.columns "
                                             "WHERE table_name = 'adv_creatives'"))}
        assert {"image_mime", "image_bytes", "image_width", "image_height"} <= cols
    uid = _user(engine, "adv-pg@t.com")
    with engine.begin() as c:
        c.execute(text("INSERT INTO adv_campaigns (advertiser_user_id, name, status, pricing_model, currency, budget_total, "
                       "spent, reserved, created_at, updated_at) VALUES (:u, 'x', 'CHANGES_REQUESTED', 'CPM', 'USD', 10, 0, 0, "
                       "now(), now())"), {"u": uid})
    with pytest.raises(Exception, match="new statuses"):
        migrate(engine, COMPLETION, "downgrade")                             # refuses while the statuses are used
    with engine.begin() as c:
        c.execute(text("DELETE FROM adv_campaigns"))
    migrate(engine, COMPLETION, "downgrade")
    with pytest.raises(Exception):
        with engine.begin() as c:
            c.execute(text("INSERT INTO adv_campaigns (advertiser_user_id, name, status, pricing_model, currency, "
                           "budget_total, spent, reserved, created_at, updated_at) VALUES (:u, 'x', 'CANCELLED', 'CPM', "
                           "'USD', 10, 0, 0, now(), now())"), {"u": uid})
    migrate(engine, COMPLETION, "upgrade")                                    # repeatable; prices already set
    with engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM audit_trails WHERE table_name = 'adv_settings'")).scalar() == 1
        assert c.execute(text("SELECT cpm_rate_usd FROM adv_settings")).scalar() == Decimal("0.7500")


def test_unset_prices_become_the_approved_policy(pg):  # noqa: F811
    engine, _ = pg
    _drop_model_tables(engine)
    migrate(engine, ADVERTISING, "upgrade")
    migrate(engine, COMPLETION, "upgrade")
    with engine.connect() as c:
        row = c.execute(text("SELECT cpm_rate_usd, min_campaign_budget_usd, campaigns_enabled, funding_enabled "
                             "FROM adv_settings")).one()
        assert tuple(row) == (Decimal("0.5000"), Decimal("10.00"), False, False)


def test_racing_cancellations_release_the_budget_once(pg):  # noqa: F811
    engine, Session = pg
    _drop_model_tables(engine)
    migrate(engine, ADVERTISING, "upgrade")
    migrate(engine, COMPLETION, "upgrade")
    from app.models.advertising_v2 import AdvCampaign, AdvCreditMovement
    from app.models.user import User
    from app.services import ad_campaigns as camp

    with Session() as db:
        user = User(email="race-adv@t.com", hashed_password="x", is_active=True, is_deleted=False)
        db.add(user)
        db.flush()
        c = AdvCampaign(advertiser_user_id=user.id, name="r", status="PENDING_REVIEW", budget_total=Decimal("10.00"),
                        cpm_rate_usd=Decimal("0.50"), start_at=datetime.utcnow(),
                        end_at=datetime.utcnow() + timedelta(days=3), placements=["IN_FEED"])
        db.add(c)
        db.flush()
        db.add(AdvCreditMovement(advertiser_user_id=user.id, movement_type="ALLOCATE", amount=Decimal("-10.00"),
                                 campaign_id=c.id, idempotency_key=f"campaign:{c.id}:allocate"))
        db.commit()
        uid, cid = user.id, c.id
    barrier, errors = threading.Barrier(8), []

    def worker():
        with Session() as db:
            try:
                barrier.wait()
                adv = db.get(User, uid)
                camp.cancel_campaign(db, adv, db.get(AdvCampaign, cid))
                db.commit()
            except camp.AdError:
                db.rollback()
            except Exception as exc:  # noqa: BLE001
                db.rollback()
                errors.append(repr(exc))

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors, errors
    with Session() as db:
        assert db.get(AdvCampaign, cid).status == "CANCELLED"
        releases = db.query(AdvCreditMovement).filter(AdvCreditMovement.movement_type == "RELEASE").all()
        assert [m.amount for m in releases] == [Decimal("10.00")]
        assert camp.credit_balance(db, uid) == Decimal("0.00")
