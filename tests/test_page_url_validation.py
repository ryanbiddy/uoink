"""Contract tests for web-page URL normalization."""

from page_extractor import normalize_page_url


def test_page_url_preserves_explicit_port() -> None:
    assert (
        normalize_page_url("https://pages.example.com:8443/article")
        == "https://pages.example.com:8443/article"
    )


def test_page_url_rejects_malformed_port() -> None:
    assert normalize_page_url("https://pages.example.com:bad/article") is None


def test_page_url_rejects_embedded_credentials() -> None:
    assert normalize_page_url("https://user:pass@pages.example.com/article") is None
