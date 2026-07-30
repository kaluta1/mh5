"""Tests for admin transaction export service."""
from app.services.admin_transactions import admin_transactions_to_csv


def test_admin_transactions_to_csv_includes_bom_and_headers():
    rows = [
        {
            "record_source": "deposit",
            "id": 1,
            "type": "deposit",
            "amount": 10.5,
            "currency": "USD",
            "status": "validated",
            "description": "Test deposit",
            "reference": "ORD-1",
            "user_id": 42,
            "user_email": "user@example.com",
            "user_username": "user1",
            "user_full_name": "Test User",
            "contest_id": None,
            "contest_name": None,
            "payment_method": "USDT",
            "product_type": "Premium",
            "order_id": "ORD-1",
            "external_payment_id": "np-123",
            "tx_hash": "0xabc",
            "created_at": "2026-07-30T10:00:00",
            "processed_at": None,
            "validated_at": "2026-07-30T11:00:00",
            "validated_by": 1,
        }
    ]
    csv_text = admin_transactions_to_csv(rows)
    assert csv_text.startswith("\ufeff")
    assert "Source;ID;Type" in csv_text or "Source" in csv_text.split("\n")[0]
    assert "deposit" in csv_text
    assert "user@example.com" in csv_text
