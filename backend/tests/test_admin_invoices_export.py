"""Tests for admin invoice HTML/PDF export."""
from datetime import datetime
from importlib.util import find_spec
from types import SimpleNamespace

import pytest

from app.services.invoice_renderer import (
    payment_origin_label,
    render_invoice_html,
    render_invoices_bulk_html,
    user_origin_label,
)


def _sample_deposit(**overrides):
    defaults = dict(
        id=42,
        amount=25.0,
        currency="USD",
        validated_at=datetime(2026, 7, 30, 10, 0, 0),
        created_at=datetime(2026, 7, 30, 9, 0, 0),
        external_payment_id="np-abc123",
        order_id="ORD-42",
        validated_by=None,
        tx_hash=None,
        from_address=None,
        crypto_currency=None,
        payment_method=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _sample_user(**overrides):
    defaults = dict(
        full_name="Jane Doe",
        username="jane",
        email="jane@example.com",
        city="Dar es Salaam",
        country="Tanzania",
        region=None,
        continent="Africa",
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_render_invoice_html_includes_origin_and_payment_origin():
    deposit = _sample_deposit()
    user = _sample_user()
    html = render_invoice_html(
        deposit,
        billed_user=user,
        product_name="Premium membership",
        lang="en",
    )
    assert "Origin" in html
    assert "Dar es Salaam, Tanzania" in html
    assert "Payment origin" in html
    assert "NOWPayments" in html
    assert "Premium membership" in html
    assert "000042" in html


def test_user_origin_label_falls_back_to_region():
    user = SimpleNamespace(city=None, country=None, region="East Africa", continent="Africa")
    assert user_origin_label(user, "en") == "East Africa"


def test_payment_origin_label_admin_grant():
    deposit = _sample_deposit(validated_by=1, external_payment_id=None)
    assert payment_origin_label(deposit, "en") == "Admin grant"


def test_render_invoices_bulk_html_combines_pages():
    items = [
        (_sample_deposit(id=1), _sample_user(email="a@example.com"), "Product A"),
        (_sample_deposit(id=2), _sample_user(email="b@example.com"), "Product B"),
    ]
    html = render_invoices_bulk_html(items, lang="en")
    assert "000001" in html
    assert "000002" in html
    assert "a@example.com" in html
    assert "b@example.com" in html


@pytest.mark.skipif(
    find_spec("xhtml2pdf") is None,
    reason="xhtml2pdf not installed",
)
def test_html_to_pdf_bytes_generates_pdf_header():
    from app.services.invoice_pdf import html_to_pdf_bytes

    deposit = _sample_deposit()
    user = _sample_user()
    html = render_invoice_html(
        deposit,
        billed_user=user,
        product_name="Service",
        lang="en",
    )
    pdf = html_to_pdf_bytes(html)
    assert pdf.startswith(b"%PDF")
