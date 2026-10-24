"""Offline article fixtures, publication compatibility and resource limits."""
import hashlib
import io
import json
from pathlib import Path
import socket
import time
from unittest.mock import Mock

import pytest

import article_extractor as article
import page_extractor as pages

FIXTURES = Path(__file__).parent / "fixtures" / "articles"
URL = "https://news.example.org/notes/article"


def html(name):
    return (FIXTURES / (name + ".html")).read_bytes()


def response(raw):
    body = io.BytesIO(raw)
    body.status = 200
    return body


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Article tests must not access the network")
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(pages, "_CRAWL4AI_AVAILABLE", False)


@pytest.mark.parametrize("name,expected", [
    ("noisy-news", "Willow reservoir reopened"),
    ("technical", "queue can preserve work"),
    ("lists", "station name and the observation date"),
    ("meta", "west window needed a new seal"),
])
def test_readable_fixtures(name, expected):
    result = pages.extract_page(None, URL, enforce_allowlist=False,
                                http_open=lambda *a, **k: response(html(name)))
    assert result["ok"], result
    assert result["extraction_engine"] == article.ENGINE
    assert result["extraction_version"] == article.VERSION
    assert result["fetched_at"].endswith("Z")
    assert expected in result["markdown"]
    assert "](" in result["markdown"]
    for unwanted in ("NAV NOISE", "AD NOISE", "RELATED NOISE", "FOOTER NOISE", "SIDEBAR NOISE"):
        assert unwanted not in result["markdown"]
    assert len(result["extraction_attempts"]) == 1


@pytest.mark.parametrize("name,diagnostic", [
    ("js-shell", "empty JavaScript page"),
    ("paywall", "login or paywall page"),
    ("login", "login or paywall page"),
])
def test_shells_are_not_published(name, diagnostic, tmp_path):
    result = pages.extract_page(None, URL, enforce_allowlist=False,
                                http_open=lambda *a, **k: response(html(name)))
    assert not result["ok"]
    assert result["code"] == "article_body_not_found"
    assert diagnostic in result["diagnostic"]
    assert len(result["diagnostic"]) <= 240 and result["markdown"] == ""
    assert result["extraction_engine"] in {article.ENGINE, "stdlib"}
    assert result["extraction_attempts"][0]["engine"] == article.ENGINE
    idx = Mock()
    assert pages.persist_page_yoink(idx, result, data_root=tmp_path) is None
    idx.upsert_yoink.assert_not_called()
    assert list(tmp_path.iterdir()) == []


def test_markdown_retains_code_table_quote_and_safe_links():
    result = article.extract(html("technical"), URL)
    md = result["markdown"]
    assert "## Example" in md
    assert "```\ndef next_item(queue):\n    if queue:\n        return queue[0] < 10" in md
    assert "`next_item(queue)`" in md
    assert "| State | Action |\n| --- | --- |" in md
    assert "| Pending | Read \\| retry |" in md
    assert "> Keep the pending record" in md
    assert "[queue guide](https://news.example.org/guide)" in md
    assert "[API reference](https://docs.example.org/api)" in md
    assert "script label" in md and "data label" in md
    assert "javascript:" not in md and "data:" not in md


def test_lists_and_nested_items():
    md = article.extract(html("lists"), URL)["markdown"]
    assert "1. Write the station" in md and "1. Record the instrument" in md
    assert "- A pencil" in md and "   - Keep the bottle sealed" in md


def test_redirect_base_keeps_source_identity():
    body = response(html("noisy-news"))
    body.geturl = lambda: "https://final.example.net/news/story"
    result = pages.extract_page(None, URL, enforce_allowlist=False, http_open=lambda *a, **k: body)
    assert result["ok"] and result["url"] == URL
    assert result["fetched_url"] == "https://final.example.net/news/story"
    assert "[water report](https://final.example.net/water/report?day=2&site=west)" in result["markdown"]


def test_nav_login_link_does_not_make_an_article_a_wall():
    document = html("meta").replace(b"NAV NOISE", b"Sign in to continue")
    assert article.extract(document, URL)["ok"]


@pytest.mark.parametrize("name", ["login", "paywall"])
def test_long_account_boilerplate_does_not_make_a_wall_an_article(name):
    boilerplate = b"<p>Members can manage their account preferences and billing details here. </p>" * 80
    document = html(name).replace(b"</main>", boilerplate + b"</main>")
    result = article.extract(document, URL)
    assert not result["ok"] and "login or paywall" in result["diagnostic"]


@pytest.mark.parametrize("target", ["javascript:alert(1)", "data:text/html,x", "file:///tmp/x",
                                    "ftp://example.org/x", "java\nscript:alert(1)", "//user:pass@example.org/x"])
def test_non_http_or_credential_links_are_dropped(target):
    assert article.safe_link(target, URL) is None


@pytest.mark.parametrize("name,expected", [
    ("noisy-news", {"title": "A reservoir returns", "author": "Mira Vale",
                    "published_date": "2026-10-20", "site_name": "Test Gazette"}),
    ("meta", {"title": "Repairing the west window", "author": "Rowan Moss",
              "published_date": "2026-10-21T08:30:00Z", "site_name": "Workshop Notes"}),
])
def test_jsonld_and_meta_attribution(name, expected):
    assert article.extract(html(name), URL)["metadata"] == expected


def test_sibling_joining_link_density_and_class_hints():
    paragraph = "The researchers measured the channel, recorded the current and checked the banks. " * 3
    document = (f'<body><div class="sidebar"><p>{paragraph * 4}</p></div>'
                f'<div class="entry"><p>{paragraph}</p></div><div class="ads">AD NOISE</div>'
                f'<div class="entry"><p>SECOND SECTION {paragraph}</p></div>'
                f'<div><p><a href="/catalog">LINK FARM {paragraph * 5}</a></p></div></body>')
    result = article.extract(document, URL)
    assert result["ok"] and "SECOND SECTION" in result["markdown"]
    assert "LINK FARM" not in result["markdown"] and "AD NOISE" not in result["markdown"]


def test_missing_body_and_short_candidate_cannot_be_rescued_by_regex():
    result = pages.extract_page(None, URL, enforce_allowlist=False,
                               http_open=lambda *a, **k: response(b"<article><p>Short teaser.</p></article>"))
    assert not result["ok"] and "too little main text" in result["diagnostic"]
    assert [a["engine"] for a in result["extraction_attempts"]] == [article.ENGINE, "stdlib"]


def test_fallback_order_and_single_static_fetch(monkeypatch):
    fetched = Mock(side_effect=lambda *a, **k: response(html("noisy-news")))
    monkeypatch.setattr(article, "extract", Mock(side_effect=ValueError("private details")))
    monkeypatch.setattr(pages, "_CRAWL4AI_AVAILABLE", True)
    crawler = Mock(side_effect=RuntimeError("private browser details"))
    monkeypatch.setattr(pages, "_extract_crawl4ai", crawler)
    result = pages.extract_page(None, URL, enforce_allowlist=False, http_open=fetched, check_url=lambda u: u)
    assert result["ok"] and result["extraction_engine"] == "stdlib"
    assert [a["engine"] for a in result["extraction_attempts"]] == [article.ENGINE, "crawl4ai", "stdlib"]
    assert all(a["version"] for a in result["extraction_attempts"])
    assert "private" not in json.dumps(result)
    fetched.assert_called_once()


def test_crawl4ai_can_recover_js_body_but_not_a_shell(monkeypatch):
    monkeypatch.setattr(pages, "_CRAWL4AI_AVAILABLE", True)
    crawler = Mock(return_value={"ok": True, "url": URL, "markdown": "Rendered article has useful facts, examples and explanations. " * 8})
    monkeypatch.setattr(pages, "_extract_crawl4ai", crawler)
    def run():
        return pages.extract_page(None, URL, enforce_allowlist=False, check_url=lambda u: u,
                                  http_open=lambda *a, **k: response(html("js-shell")))
    result = run()
    assert result["ok"] and result["extraction_engine"] == "crawl4ai"
    crawler.return_value = {"ok": True, "markdown": "Sign in to continue"}
    assert not run()["ok"]


def test_fetch_refusal_never_runs_extractors(monkeypatch):
    primary = Mock()
    monkeypatch.setattr(article, "extract", primary)
    crawler = Mock()
    monkeypatch.setattr(pages, "_extract_crawl4ai", crawler)
    def refuse(*args, **kwargs):
        raise pages.source_subscriptions.ServiceError("unsupported_source", "Blocked target")
    monkeypatch.setattr(pages.source_subscriptions, "public_http_open", refuse)
    result = pages.extract_page(None, URL, enforce_allowlist=False)
    assert not result["ok"]
    primary.assert_not_called()
    crawler.assert_not_called()


def test_publication_preserves_identity_and_adds_provenance(tmp_path):
    import index
    idx = index.Index.open(tmp_path / "index.db")
    try:
        result = pages.extract_page(None, URL, enforce_allowlist=False,
                                    http_open=lambda *a, **k: response(html("meta")))
        identifier = pages.persist_page_yoink(idx, result, data_root=tmp_path / "corpus")
        assert identifier == "page_" + hashlib.sha1(URL.encode()).hexdigest()[:11]
        row = idx.get_yoink(identifier)
        assert row["author"] == row["channel"] == "Rowan Moss"
        sidecar = json.loads(Path(row["sidecar_path"]).read_text(encoding="utf-8"))
        metadata = json.loads(row["metadata_json"])
        assert sidecar["schema_version"] == 2
        for key in ("extraction_engine", "extraction_version", "fetched_at", "article_status"):
            assert sidecar[key] == metadata[key] == result[key]
        saved = Path(row["corpus_path"]).read_text(encoding="utf-8")
        assert "**Published:** 2026-10-21T08:30:00Z" in saved
        assert saved.count("# Repairing the west window") == 1
        assert pages.persist_page_yoink(idx, result, data_root=tmp_path / "corpus") == identifier
    finally:
        idx.close()


def test_bounds_and_malformed_html(monkeypatch):
    assert article.extract("<div>" * 100 + "x", URL)["code"] == "article_extraction_limit"
    assert article.extract(b"x" * (article.MAX_INPUT + 1), URL)["code"] == "article_extraction_limit"
    monkeypatch.setattr(article, "MAX_NODES", 10)
    assert article.extract("<p>words</p>" * 11, URL)["code"] == "article_extraction_limit"
    monkeypatch.setattr(article, "MAX_NODES", 40000)
    monkeypatch.setattr(article, "MAX_SECONDS", -1)
    assert "time limit" in article.extract(html("meta"), URL)["diagnostic"]


def test_two_megabyte_page_has_bounded_time_and_output():
    paragraph = b"<p>A synthetic field report describes the water, the bank and the instrument readings in detail. </p>"
    start, end = b'<article class="content">', b"</article>"
    count = (2 * 1024 * 1024 - len(start) - len(end)) // len(paragraph)
    raw = start + paragraph * count
    raw += b" " * (2 * 1024 * 1024 - len(raw) - len(end)) + end
    before = time.perf_counter()
    result = article.extract(raw, URL)
    elapsed = time.perf_counter() - before
    print(f"2 MiB article: {elapsed:.3f}s, {len(result['markdown'])} Markdown characters")
    assert result["ok"], result
    assert elapsed < 3.0
    assert len(result["markdown"]) <= article.MAX_MARKDOWN
    assert result["output_truncated"]


def test_packaging_and_adapted_notices():
    root = Path(__file__).resolve().parents[1]
    assert "article_extractor.py" in (root / "build.ps1").read_text(encoding="utf-8")
    assert 'Source: "staging\\article_extractor.py"' in (root / "installer/uoink.iss").read_text(encoding="utf-8")
    assert "article_extractor.py" in json.loads((root / "scripts/mac/payload.json").read_text())["paths"]
    import importlib.util
    spec = importlib.util.spec_from_file_location("article_notices", root / "scripts/gen_third_party_notices.py")
    notices = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(notices)
    assert notices.ADAPTED_TEXT_BLOCK in (root / "THIRD-PARTY-NOTICES.md").read_text(encoding="utf-8")
    assert (root / "third-party-notices/mozilla-readability-APACHE-2.0.txt").is_file()
