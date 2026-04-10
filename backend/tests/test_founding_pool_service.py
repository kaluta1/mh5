from decimal import Decimal

from app.services.founding_pool_service import split_pool_amount


def test_split_equal_when_weights_sum_zero():
    out = split_pool_amount(Decimal("10.00"), [10, 20], {10: Decimal(0), 20: Decimal(0)})
    assert len(out) == 2
    assert sum(Decimal(str(v)) for v in out.values()) == Decimal("10.00")


def test_split_proportional():
    out = split_pool_amount(Decimal("100.00"), [1, 2], {1: Decimal("0.6"), 2: Decimal("0.4")})
    assert out[1] + out[2] == Decimal("100.00")
    assert out[1] == Decimal("60.00")
    assert out[2] == Decimal("40.00")
