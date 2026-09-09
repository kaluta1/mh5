from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.api.api_v1.endpoints.search import search as global_search, search_clubs
from app.models.clubs import ClubStatus, FanClub, MembershipStatus
from app.services.club_marketplace_integrity import (
    ClubMarketplaceIntegrityError,
    marketplace_split,
    membership_is_entitled,
    purchase_allows_download,
    require_owner,
    review_is_allowed,
    validate_authoritative_charge,
    validate_membership_transition,
)


def test_dormant_financial_routers_remain_fail_closed(app):
    paths = {route.path for route in app.routes}
    assert not any(path.startswith("/api/v1/clubs") for path in paths)
    assert not any(path.startswith("/api/v1/dsp") for path in paths)


def test_server_price_is_authoritative_and_uses_decimal():
    amount, currency = validate_authoritative_charge(
        submitted_amount="4.990",
        submitted_currency="usd",
        server_amount=Decimal("4.99"),
        server_currency="USD",
    )
    assert amount == Decimal("4.99")
    assert currency == "USD"
    assert isinstance(amount, Decimal)

    with pytest.raises(ClubMarketplaceIntegrityError, match="server product price"):
        validate_authoritative_charge(
            submitted_amount="0.01",
            submitted_currency="USD",
            server_amount="4.99",
            server_currency="USD",
        )


def test_membership_transition_and_entitlement_fail_closed():
    now = datetime.now(timezone.utc)
    club = SimpleNamespace(id=7, status=ClubStatus.ACTIVE)
    membership = SimpleNamespace(
        club_id=7,
        status=MembershipStatus.ACTIVE,
        start_date=now - timedelta(days=1),
        end_date=now + timedelta(days=1),
    )
    assert membership_is_entitled(
        membership,
        club=club,
        authoritative_payment_confirmed=True,
        at=now,
    )
    assert not membership_is_entitled(
        membership,
        club=club,
        authoritative_payment_confirmed=False,
        at=now,
    )
    assert not membership_is_entitled(
        membership,
        club=club,
        authoritative_payment_confirmed=True,
        payment_refunded=True,
        at=now,
    )
    membership.end_date = now
    assert not membership_is_entitled(
        membership,
        club=club,
        authoritative_payment_confirmed=True,
        at=now,
    )

    validate_membership_transition(MembershipStatus.ACTIVE, MembershipStatus.CANCELLED)
    with pytest.raises(ClubMarketplaceIntegrityError):
        validate_membership_transition(MembershipStatus.CANCELLED, MembershipStatus.ACTIVE)


def test_owner_checks_prevent_cross_account_management():
    require_owner(actor_user_id=11, owner_user_id=11)
    with pytest.raises(ClubMarketplaceIntegrityError, match="ownership"):
        require_owner(actor_user_id=11, owner_user_id=12)


def test_marketplace_split_is_server_controlled_and_exact():
    fee, seller = marketplace_split(
        gross_amount=Decimal("10.03"), server_platform_fee_rate=Decimal("0.20")
    )
    assert fee == Decimal("2.01")
    assert seller == Decimal("8.02")
    assert fee + seller == Decimal("10.03")

    with pytest.raises(ClubMarketplaceIntegrityError):
        marketplace_split(gross_amount="10.00", server_platform_fee_rate="1.01")


def test_download_requires_buyer_payment_active_product_and_remaining_allowance():
    purchase = SimpleNamespace(
        buyer_id=4, product_id=9, download_count=0, max_downloads=5
    )
    product = SimpleNamespace(id=9, is_active=True)
    allowed = dict(
        purchase=purchase,
        product=product,
        authenticated_user_id=4,
        authoritative_payment_confirmed=True,
    )
    assert purchase_allows_download(**allowed)
    assert not purchase_allows_download(**{**allowed, "authenticated_user_id": 5})
    assert not purchase_allows_download(**{**allowed, "payment_refunded": True})
    assert not purchase_allows_download(
        **{**allowed, "authoritative_payment_confirmed": False}
    )
    purchase.download_count = 5
    assert not purchase_allows_download(**allowed)


def test_reviews_require_confirmed_purchase_and_prevent_self_review():
    assert review_is_allowed(
        buyer_user_id=1, seller_user_id=2, has_confirmed_purchase=True
    )
    assert not review_is_allowed(
        buyer_user_id=1, seller_user_id=1, has_confirmed_purchase=True
    )
    assert not review_is_allowed(
        buyer_user_id=1, seller_user_id=2, has_confirmed_purchase=False
    )


def test_club_search_excludes_private_and_non_active_rows(db):
    db.add_all(
        [
            FanClub(
                owner_id=1,
                name="Alpha Public Club",
                slug="alpha-public",
                is_public=True,
                status=ClubStatus.ACTIVE,
            ),
            FanClub(
                owner_id=1,
                name="Alpha Private Club",
                slug="alpha-private",
                is_public=False,
                status=ClubStatus.ACTIVE,
            ),
            FanClub(
                owner_id=1,
                name="Alpha Suspended Club",
                slug="alpha-suspended",
                is_public=True,
                status=ClubStatus.SUSPENDED,
            ),
        ]
    )
    db.commit()

    result = search_clubs(q="Alpha", skip=0, limit=10, db=db, current_user=object())
    assert [item["title"] for item in result] == ["Alpha Public Club"]
    combined = global_search(q="Alpha", db=db, current_user=object())
    assert [item["title"] for item in combined["club"]] == ["Alpha Public Club"]


def test_club_search_is_deterministic_and_bounded(db):
    for index, name in enumerate(("Zulu Club", "Alpha Club", "Beta Club"), start=1):
        db.add(
            FanClub(
                owner_id=1,
                name=name,
                slug=f"ordered-{index}",
                is_public=True,
                status=ClubStatus.ACTIVE,
            )
        )
    db.commit()

    result = search_clubs(q="Club", skip=0, limit=2, db=db, current_user=object())
    assert [item["title"] for item in result] == ["Alpha Club", "Beta Club"]
