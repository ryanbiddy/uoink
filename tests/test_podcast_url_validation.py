"""Contract tests for podcast feed URL normalization."""

import pytest

from podcasts import _validate_feed_url


def test_feed_url_preserves_explicit_port() -> None:
    assert (
        _validate_feed_url("https://feeds.example.com:8443/show.rss")
        == "https://feeds.example.com:8443/show.rss"
    )


def test_feed_url_rejects_malformed_port() -> None:
    assert _validate_feed_url("https://feeds.example.com:bad/show.rss") is None


def test_feed_url_rejects_embedded_credentials() -> None:
    assert _validate_feed_url("https://user:pass@feeds.example.com/show.rss") is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "http://[2001:db8::1]:8080/feed",
            "http://[2001:db8::1]:8080/feed",
        ),
        ("https://[2001:db8::1]/feed", "https://[2001:db8::1]/feed"),
    ],
)
def test_feed_url_serializes_ipv6_with_brackets(raw: str, expected: str) -> None:
    assert _validate_feed_url(raw) == expected
