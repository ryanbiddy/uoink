"""Contract tests for generic capture URL normalization and its security docs."""

from pathlib import Path

import server


ROOT = Path(__file__).resolve().parents[1]


def test_any_url_preserves_explicit_port() -> None:
    assert server._normalize_any_url(
        "https://media.example.com:8443/watch"
    ) == ("https://media.example.com:8443/watch", "generic")


def test_any_url_rejects_malformed_port() -> None:
    assert server._normalize_any_url(
        "https://media.example.com:bad/watch"
    ) == (None, None)


def test_any_url_rejects_embedded_credentials() -> None:
    assert server._normalize_any_url(
        "https://user:pass@media.example.com/watch"
    ) == (None, None)


def test_security_doc_matches_current_url_boundaries() -> None:
    text = (ROOT / "docs" / "security.md").read_text(encoding="utf-8")
    normalized = " ".join(text.split())

    assert (
        "checked against an explicit YouTube host allowlist, and canonicalized"
        not in normalized
    )
    for claim in (
        "YouTube, X/Twitter, TikTok, and Instagram",
        "Embedded credentials and malformed ports are rejected",
        "IP literals are currently permitted",
        "redirect targets are not revalidated by Uoink",
    ):
        assert claim in normalized
