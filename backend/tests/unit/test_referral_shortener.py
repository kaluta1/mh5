"""Unit tests for referral share path normalization."""
import pytest

from app.services.referral_shortener import to_public_share_path, to_public_share_url


pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "path,expected",
    [
        ("/dashboard/contests/5/contestant/12", "/contests/5/entry/12"),
        ("/dashboard/feed/99", "/feed/99"),
        ("/s/f/42", "/feed/42"),
        ("/s/c/7", "/s/c/7"),
        ("/c/3", "/c/3"),
        ("/contestants/8", "/contestants/8"),
        ("/other/path", "/other/path"),
    ],
)
def test_to_public_share_path(path, expected):
    assert to_public_share_path(path) == expected


def test_to_public_share_url_rewrites_path():
    url = "https://myhigh5.com/dashboard/contests/1/contestant/2?utm=1"
    result = to_public_share_url(url)
    assert "/contests/1/entry/2" in result
    assert "utm=1" in result
