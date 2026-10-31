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


@pytest.mark.parametrize("newline", ["\r\n", "\r"])
@pytest.mark.parametrize("as_bytes", [False, True])
def test_html_input_newlines_are_normalized(newline, as_bytes):
    document = html("technical").decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    expected = article.extract(document, URL)
    document = document.replace("\n", newline)
    result = article.extract(document.encode("utf-8") if as_bytes else document, URL)
    assert result["ok"] and result == expected
    assert "\r" not in result["markdown"]
    assert "```\ndef next_item(queue):\n    if queue:\n" in result["markdown"]


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


def prose(length):
    """Synthetic reporting with an exact length for the reviewed regressions."""
    text = ("The council opened the river path after workers repaired the bridge. "
            "Residents can reach the station again, and the eastern gate stays open. "
            "Inspectors checked the railings and recorded the repairs in the public log. "
            "The next inspection will cover the footbridge beside the school. ")
    return (text * (length // len(text) + 1))[:length - 1] + "."


@pytest.mark.parametrize("chrome", [
    '<header><a href="/login">Sign in to continue</a></header>',
    '<noscript>Please enable JavaScript</noscript>',
])
def test_short_article_survives_header_login_and_noscript(chrome):
    body = prose(364)
    result = article.extract(f"<title>River path opens</title>{chrome}<article><p>{body}</p></article>", URL)
    assert result["ok"] and result["extraction_engine"] == article.ENGINE
    assert body in result["markdown"]
    assert "Sign in to continue" not in result["markdown"]
    assert "enable JavaScript" not in result["markdown"]


def test_short_article_can_discuss_subscriptions():
    body = "The library lets residents subscribe to read its weekly reports. "
    body += prose(283 - len(body))
    assert len(body) == 283
    result = article.extract(f"<title>Library reports</title><article><p>{body}</p></article>", URL)
    assert result["ok"] and body in result["markdown"]


@pytest.mark.parametrize("sentence,length", [
    ("Please enable JavaScript to continue.", 1519),
    ("Loading the reader.", 399),
    ("Please enable JavaScript to continue.", 3039),
    ("Please enable JavaScript to continue", 1519),
    ("The reader will appear in a moment.", 399),
])
def test_repeated_javascript_shell_is_not_an_article(sentence, length):
    body = ((sentence + " ") * (length // (len(sentence) + 1) + 1))[:length]
    document = f'<title>Reading app</title><body><div id="root">{body}</div><script src="/app.js"></script></body>'
    result = pages.extract_page(None, URL, enforce_allowlist=False,
                                http_open=lambda *a, **k: response(document.encode()))
    assert not result["ok"] and "empty JavaScript page" in result["diagnostic"]
    assert result["markdown"] == ""


def test_single_loader_and_javascript_prompt_without_script():
    loader = article.extract('<body><div>Loading the reader.</div><script src="app.js"></script></body>', URL)
    assert not loader["ok"] and "empty JavaScript page" in loader["diagnostic"]
    prompt = "Please enable JavaScript to continue. " * 80
    result = article.extract(f"<body><div>{prompt}</div></body>", URL)
    assert not result["ok"] and "empty JavaScript page" in result["diagnostic"]


def test_root_skin_flags_do_not_hide_a_server_rendered_article():
    # Wiki skins put feature flags such as "main-menu-pinned-disabled" on <html>.
    result = pages.extract_page(None, URL, enforce_allowlist=False,
                                http_open=lambda *a, **k: response(html("wiki-skin")))
    assert result["ok"] and result["extraction_engine"] == article.ENGINE
    assert result["article_status"] == "found"
    # The JSON-LD headline is the wiki's short description; the name is the title.
    assert result["title"] == result["metadata"]["title"] == "Harbor lanterns"
    assert "dissolves in salt water" in result["markdown"] and "## History" in result["markdown"]
    for unwanted in ("NAV NOISE", "MENU NOISE", "FOOTER NOISE"):
        assert unwanted not in result["markdown"]


@pytest.mark.parametrize("title,ld,expected", [
    ("Harbor lanterns - Example Wiki", {"name": "Harbor lanterns", "headline": "paper lights floated on the tide"},
     "Harbor lanterns"),
    ("River path opens after repairs | Example Daily", {"name": "Example Daily", "headline": "River path opens after repairs"},
     "River path opens after repairs"),
    ("Example Daily | River path opens after repairs", {"name": "Example Daily", "headline": "River path opens after repairs"},
     "River path opens after repairs"),
    ("River path opens after repairs", {"name": "River path opens after repairs today", "headline": "River path opens after repairs"},
     "River path opens after repairs today"),
    ("Example Daily", {"name": "River path opens", "headline": "Repairs finished on the bridge"}, "River path opens"),
    ("Example Daily", {"headline": "River path opens"}, "River path opens"),
    ("Example Daily", {"name": "River path opens"}, "River path opens"),
])
def test_jsonld_headline_wins_only_when_it_matches_the_page_title(title, ld, expected):
    data = json.dumps({"@context": "https://schema.org", "@type": "NewsArticle", **ld})
    # JSON-LD ahead of <title>: the choice waits for the whole document.
    document = (f'<head><script type="application/ld+json">{data}</script><title>{title}</title></head>'
                f"<article><p>{prose(364)}</p></article>")
    assert article.extract(document, URL)["metadata"]["title"] == expected


@pytest.mark.parametrize("root", ['<html class="client-nojs main-menu-pinned">',
                                  '<html><body class="has-sidebar comments-open">'])
def test_root_class_hints_keep_articles_and_shells_apart(root):
    body = prose(364)
    result = article.extract(f'{root}<div class="menu">MENU NOISE</div>'
                             f'<article><p>{body}</p></article><script src="/app.js"></script>', URL)
    assert result["ok"] and body in result["markdown"] and "MENU NOISE" not in result["markdown"]
    shell = article.extract(f'{root}<div id="root"></div><noscript>Please enable JavaScript.</noscript>'
                            '<script src="/app.js"></script>', URL)
    assert not shell["ok"] and "empty JavaScript page" in shell["diagnostic"]


@pytest.mark.parametrize("base,expected", [
    ("https://cdn.example.org/blog/post/", "https://cdn.example.org/blog/post/photo.html"),
    ("/images/", "https://news.example.org/images/photo.html"),
    ("javascript:alert(1)", "https://news.example.org/notes/photo.html"),
    ("data:text/html,x", "https://news.example.org/notes/photo.html"),
    ("https://user:pass@cdn.example.org/", "https://news.example.org/notes/photo.html"),
    ("https://@cdn.example.org/", "https://news.example.org/notes/photo.html"),
])
def test_document_base_controls_safe_relative_links(base, expected):
    document = (f'<head><base href="{base}"></head><article><p>{prose(364)} '
                '<a href="photo.html">Photo</a><a href="javascript:alert(1)">Script</a>'
                '<a href="data:text/html,x">Data</a></p></article>')
    result = article.extract(document, URL)
    assert result["ok"] and f"[Photo]({expected})" in result["markdown"]
    assert result["links"] == [{"href": expected}]


@pytest.mark.parametrize("container,byline", [
    ('<body class="author-jane">', '<span class="byline">Jane Doe</span>'),
    ('<body><div class="authority">City Desk</div>', '<span class="author">Jane Doe</span>'),
    ('<body><div class="author-box">Report by Jane Doe</div>', '<span id="article-author">Jane Doe</span>'),
])
def test_visible_byline_uses_shortest_matching_token(container, byline):
    document = f"{container}<article>{byline}<p>{prose(364)}</p></article></body>"
    assert article.extract(document, URL)["metadata"]["author"] == "Jane Doe"


@pytest.mark.parametrize("tag", ["header", "nav"])
def test_header_login_form_does_not_veto_div_article(tag):
    body = prose(2404)
    document = (f'<{tag}><form class="login-wall"><input type="password">'
                f'<h2>Sign in to continue</h2></form></{tag}>'
                f'<div class="content"><h1>River path opens</h1><p>{body}</p></div>')
    result = article.extract(document, URL)
    assert result["ok"] and body in result["markdown"]
    assert "Sign in" not in result["markdown"]


@pytest.mark.parametrize("length", [93, 125, 199])
def test_one_paragraph_brief_is_labeled_short_article(length):
    body = prose(length)
    document = f'<title>River path opens</title><article><p>{body}</p></article><script src="analytics.js"></script>'
    result = pages.extract_page(None, URL, enforce_allowlist=False,
                                http_open=lambda *a, **k: response(document.encode()))
    assert result["ok"] and body in result["markdown"]
    assert result["extraction_engine"] == article.ENGINE
    assert result["article_status"] == "short_article" and result["diagnostic"] == "short article"


def test_short_heading_or_untitled_snippet_is_not_a_brief():
    for document in (f"<article><p>{prose(125)}</p></article>",
                     f"<title>Menu</title><article><h1>{prose(125)}</h1></article>"):
        assert not article.extract(document, URL)["ok"]


@pytest.mark.parametrize("browser", [False, True])
@pytest.mark.parametrize("limit", ["depth", "size"])
def test_extractor_limits_try_fallbacks(monkeypatch, browser, limit):
    body = prose(364)
    document = f"<title>River path opens</title><p>{body}</p>"
    if limit == "depth":
        document = "<div>" * 90 + document + "</div>" * 90
    else:
        monkeypatch.setattr(article, "MAX_INPUT", 100)
    monkeypatch.setattr(pages, "_CRAWL4AI_AVAILABLE", browser)
    crawler = Mock(return_value={"ok": True, "markdown": body})
    monkeypatch.setattr(pages, "_extract_crawl4ai", crawler)
    result = pages.extract_page(None, URL, enforce_allowlist=False, check_url=lambda u: u,
                                http_open=lambda *a, **k: response(document.encode()))
    assert result["ok"] and body in result["markdown"]
    assert result["extraction_engine"] == ("crawl4ai" if browser else "stdlib")
    assert "limit" in result["extraction_attempts"][0]["diagnostic"]
    assert len(result["extraction_attempts"]) == 2


@pytest.mark.parametrize("browser", [False, True])
def test_deep_brief_is_recovered_and_labeled(monkeypatch, browser):
    body = prose(125)
    document = "<div>" * 90 + f"<title>River path opens</title><p>{body}</p>" + "</div>" * 90
    monkeypatch.setattr(pages, "_CRAWL4AI_AVAILABLE", browser)
    monkeypatch.setattr(pages, "_extract_crawl4ai", Mock(return_value={"ok": True, "title": "River path opens", "markdown": body}))
    result = pages.extract_page(None, URL, enforce_allowlist=False, check_url=lambda u: u,
                                http_open=lambda *a, **k: response(document.encode()))
    assert result["ok"] and result["article_status"] == "short_article"
    assert result["diagnostic"] == result["extraction_attempts"][-1]["diagnostic"] == "short article"


def test_fetch_byte_cap_is_terminal(monkeypatch):
    primary, crawler = Mock(), Mock()
    monkeypatch.setattr(article, "extract", primary)
    monkeypatch.setattr(pages, "_extract_crawl4ai", crawler)
    monkeypatch.setattr(pages, "_CRAWL4AI_AVAILABLE", True)
    result = pages.extract_page(None, URL, enforce_allowlist=False,
                                http_open=lambda *a, **k: response(b"x" * (pages._PAGE_MAX_BYTES + 1)))
    assert not result["ok"] and result["code"] == "page_fetch_too_large"
    primary.assert_not_called()
    crawler.assert_not_called()


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
    crawler = Mock(return_value={"ok": True, "url": URL, "markdown": prose(364)})
    monkeypatch.setattr(pages, "_extract_crawl4ai", crawler)
    def run():
        return pages.extract_page(None, URL, enforce_allowlist=False, check_url=lambda u: u,
                                  http_open=lambda *a, **k: response(html("js-shell")))
    result = run()
    assert result["ok"] and result["extraction_engine"] == "crawl4ai"
    crawler.return_value = {"ok": True, "markdown": "Sign in to continue"}
    assert not run()["ok"]
    crawler.return_value = {"ok": True, "markdown": "Loading the reader. " * 21}
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


@pytest.mark.parametrize("browser", [False, True])
def test_private_target_refusal_has_no_fetch_or_extraction_provenance(monkeypatch, browser):
    url = "http://192.168.1.2/private-page"
    clock = Mock(return_value="2026-10-24T01:00:00Z")
    monkeypatch.setattr(pages, "_now_iso", clock)
    monkeypatch.setattr(pages, "_CRAWL4AI_AVAILABLE", browser)
    expected = {"ok": False, "url": url, "code": "unsupported_source",
                "error": "fetch failed: Loopback, link-local and private targets are refused"}
    assert pages.extract_page(None, url, enforce_allowlist=False) == expected
    clock.return_value = "2026-10-24T02:00:00Z"
    assert pages.extract_page(None, url, enforce_allowlist=False) == expected
    assert pages._extract_stdlib(url, include_screenshot=False) == expected
    clock.assert_not_called()


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


def png():
    from PIL import Image
    buffer = io.BytesIO()
    Image.new("RGB", (64, 48), (40, 90, 160)).save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.mark.parametrize("head,expected", [
    ('<meta property="og:image" content="/media/lead.png"><meta name="twitter:image" content="https://cdn.example.org/t.png">',
     "https://news.example.org/media/lead.png"),
    ('<meta property="og:image" content="data:image/png;base64,AAAA"><meta name="twitter:image" content="t.png">',
     "https://news.example.org/notes/t.png"),
    ('<link rel="image_src" href="//cdn.example.org/src.png">', "https://cdn.example.org/src.png"),
    ('<base href="https://cdn.example.org/a/"><meta property="og:image" content="lead.png">',
     "https://cdn.example.org/a/lead.png"),
    ('<meta property="og:image" content="  ">', None),
])
def test_lead_image_prefers_og_then_twitter_then_image_src(head, expected):
    result = article.extract(f"<head><title>River path opens</title>{head}</head>"
                             f"<article><p>{prose(364)}</p></article>", URL)
    assert result["ok"] and result["metadata"].get("image") == expected


def capture(tmp_path, http_open, document=None):
    import index
    idx = index.Index.open(tmp_path / "index.db")
    try:
        result = pages.extract_page(None, URL, enforce_allowlist=False,
                                    http_open=lambda *a, **k: response(document or html("wiki-skin")))
        identifier = pages.persist_page_yoink(idx, result, data_root=tmp_path / "corpus", http_open=http_open)
        return idx.get_yoink(identifier)
    finally:
        idx.close()


def test_page_lead_image_becomes_the_library_thumbnail(tmp_path):
    opened = []
    def http_open(url, **kwargs):
        opened.append((url, kwargs))
        return response(png())
    row = capture(tmp_path, http_open)
    # The Library row and reader look for thumbnail.jpg beside the corpus file.
    folder = Path(row["corpus_path"]).parent
    assert (folder / "thumbnail.jpg").read_bytes().startswith(b"\xff\xd8\xff")
    assert [url for url, _ in opened] == ["https://news.example.org/media/thumb/harbor-lanterns-960.jpg"]
    assert opened[0][1]["timeout"] == pages._PAGE_FETCH_TIMEOUT_SEC
    assert json.loads(row["metadata_json"])["image"] == opened[0][0]
    assert sorted(p.name for p in folder.iterdir()) == ["page.json", "page.md", "thumbnail.jpg"]


def failing_image(kind):
    def http_open(url, **kwargs):
        if kind == "error":
            raise OSError("image host unavailable")
        if kind == "status":
            body = response(png())
            body.status = 404
            return body
        if kind == "html":
            return response(b"<!doctype html><title>Not an image</title>")
        if kind == "large":
            import images
            return response(png() + b"\0" * images.MAX_IMAGE_BYTES)
        return response(b"\x89PNG\r\n\x1a\n" + b"\0" * 64)  # right magic, no image
    return http_open


@pytest.mark.parametrize("kind", ["error", "status", "html", "large", "corrupt"])
def test_failed_lead_image_never_fails_the_capture(tmp_path, kind):
    row = capture(tmp_path, failing_image(kind))
    assert row and Path(row["corpus_path"]).is_file()
    assert sorted(p.name for p in Path(row["corpus_path"]).parent.iterdir()) == ["page.json", "page.md"]


def test_lead_image_uses_the_public_network_policy(tmp_path, monkeypatch):
    refused = []
    public_open = pages.source_subscriptions.public_http_open
    def spy(url, **kwargs):
        try:
            return public_open(url, **kwargs)
        except pages.source_subscriptions.ServiceError as exc:
            refused.append(exc.code)
            raise
    monkeypatch.setattr(pages.source_subscriptions, "public_http_open", spy)
    document = html("wiki-skin").replace(b"/media/thumb/harbor-lanterns-960.jpg", b"http://192.168.1.2/lead.jpg")
    row = capture(tmp_path, None, document)
    assert refused == ["unsupported_source"]
    assert not (Path(row["corpus_path"]).parent / "thumbnail.jpg").exists()


def test_page_without_lead_image_or_other_sources_fetch_nothing(tmp_path):
    http_open = Mock(side_effect=AssertionError("no image fetch expected"))
    assert capture(tmp_path, http_open, html("meta"))
    result = {"ok": True, "url": "https://www.reddit.com/r/example/comments/1", "title": "Thread",
              "markdown": prose(364), "metadata": {"image": "https://cdn.example.org/t.png"}}
    import index
    idx = index.Index.open(tmp_path / "reddit.db")
    try:
        assert pages.persist_page_yoink(idx, result, data_root=tmp_path / "corpus", source_type="reddit_thread",
                                        subfolder="Reddit", slug_prefix="reddit", http_open=http_open)
    finally:
        idx.close()
    http_open.assert_not_called()


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
