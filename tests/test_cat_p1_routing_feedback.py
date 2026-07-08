"""Categorization Phase 1 (A1 + A2): authoritative X-Article routing and
honest, visible walled-capture feedback.

A1 -- one authoritative Article definition, every entry point uses it:
  * helper classify (server._classify_capture_url -> x_extractor.is_x_article_url)
    and helper persist (x_article_extractor) share ONE definition, so they can
    never disagree. The strict x_article_extractor shape is that definition.
  * the extension collapses its two JS copies to one (XArticle owns it;
    STC delegates) and the context menu + popup route an actual Article to the
    in-page DOM parse, not the login-walled /extract/page fetch.

A2 -- a walled/failed capture is honest and visible:
  * page_extractor detects X's login wall and persists nothing (already true);
    the extension surfaces it as a PERSISTENT, actionable message (popup alert
    + requireInteraction notification), not a transient toast, and never a
    saved empty/junk uoink.
  * a stale-token 403 on /extract/page auto-refreshes the token (the authed
    fetch retry) instead of dead-ending.

Red on unpatched main:
  * x_extractor.is_x_article_url used a LOOSE regex (no id required) that
    disagreed with the strict persist shape -> test_shared_detector_agreement.
  * the context menu was a static "Uoink this page (article)" that skipped
    detection -> test_context_menu_routes_article_to_dom_parse.
  * the popup labelled from the URL shape only -> test_popup_resolves_via_dom.
  * walled feedback was a transient toast / generic "Uoink failed" ->
    test_popup_walled_feedback_is_persistent / test_background_walled_feedback.

No real (copyrighted) article text appears here -- fixtures are synthetic.

Run: python tests/test_cat_p1_routing_feedback.py  (also collected by pytest).
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import page_extractor  # noqa: E402
import server  # noqa: E402
import x_article_extractor  # noqa: E402
import x_extractor  # noqa: E402

EXT = REPO_ROOT / "extension"


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


# ---- A1: one authoritative Python definition ------------------------------

_ARTICLE_URLS = [
    "https://x.com/jack/article/1900000000001",
    "https://x.com/i/article/1900000000002",
    "https://twitter.com/jack/article/1900000000003?s=20",
    "https://www.x.com/jack/article/1900000000004",
    "https://mobile.twitter.com/a/article/ABC12345",
    "https://x.com/jack/article/1900000000005/some-slug",
]
_NOT_ARTICLE_URLS = [
    "https://x.com/jack/status/1234567890123456789",
    "https://x.com/i/status/1234567890123456789",
    "https://x.com/home",
    "https://x.com/jack",
    # loose-regex trap: an /article path with NO id. The old loose copy matched
    # this; the strict single definition does not. Both copies must now agree.
    "https://x.com/jack/article",
    "https://x.com/jack/article/",
    "https://example.com/jack/article/1900000000001",
    "https://youtube.com/watch?v=abc",
    "",
]


def test_shared_detector_agreement():
    """x_extractor and x_article_extractor must return the SAME verdict for
    every URL -- classify and persist can't disagree. (Red on main: the loose
    x_extractor copy matched a no-id /article path the strict copy rejected.)"""
    for url in _ARTICLE_URLS + _NOT_ARTICLE_URLS:
        a = x_extractor.is_x_article_url(url)
        b = x_article_extractor.is_x_article_url(url)
        _assert(a == b, f"detectors disagree on {url!r}: "
                        f"x_extractor={a} x_article_extractor={b}")
    print("ok  x_extractor + x_article_extractor agree on every URL")


def test_shared_detector_positive_and_canonical():
    for url in _ARTICLE_URLS:
        _assert(x_article_extractor.is_x_article_url(url),
                f"should be an article: {url}")
        canonical = x_article_extractor.canonical_article_url(url)
        _assert(canonical and canonical.startswith("https://x.com/"),
                f"canonical should normalise to x.com: {url} -> {canonical}")
    for url in _NOT_ARTICLE_URLS:
        _assert(not x_article_extractor.is_x_article_url(url),
                f"must NOT be an article: {url}")
    print("ok  article URL variants classify + canonicalise; non-articles reject")


def test_server_classifier_uses_shared_detector():
    for url in _ARTICLE_URLS:
        cls = server._classify_capture_url(url)
        _assert(cls.get("ok") and cls.get("source") == "x_article",
                f"pasted article should classify x_article: {url} -> {cls}")
        _assert(cls.get("canonical", "").startswith("https://x.com/"),
                f"classifier canonicalises the article URL: {cls}")
    # A no-id /article path is no longer misdetected as an article.
    noid = server._classify_capture_url("https://x.com/jack/article")
    _assert(noid.get("source") != "x_article",
            f"no-id /article must not classify as x_article: {noid}")
    print("ok  server capture classifier routes through the shared detector")


# ---- A2: honest walled capture persists nothing ---------------------------

def _x_wall_result(url):
    return {
        "ok": True, "extraction_engine": "stdlib", "url": url, "title": None,
        "markdown": ("# JavaScript is not available.\n\nWe've detected that "
                     "JavaScript is disabled in this browser."),
        "metadata": {}, "links": [], "images": [],
    }


def test_walled_capture_honest_and_persists_nothing():
    url = "https://x.com/jack/article/1900000000001"
    saved_stdlib = page_extractor._extract_stdlib
    saved_crawl = page_extractor._CRAWL4AI_AVAILABLE
    page_extractor._CRAWL4AI_AVAILABLE = False
    page_extractor._extract_stdlib = lambda u, **k: _x_wall_result(u)
    try:
        class _Idx:
            def upsert_yoink(self, *a, **k):
                raise AssertionError("walled capture must NOT persist anything")
        result = page_extractor.extract_page(_Idx(), url, enforce_allowlist=False)
        _assert(result.get("ok") is False, f"walled fetch must fail: {result}")
        _assert(result.get("code") == "x_login_wall",
                f"walled fetch must flag x_login_wall: {result}")
        err = (result.get("error") or "").lower()
        _assert("article" in err and ("log" in err or "wall" in err),
                f"walled copy must name the article + login wall: {result}")
        # persist_page_yoink on an ok=False result is a no-op (nothing saved).
        _assert(page_extractor.persist_page_yoink(_Idx(), result) is None,
                "persist on a failed result must return None (no junk uoink)")
    finally:
        page_extractor._extract_stdlib = saved_stdlib
        page_extractor._CRAWL4AI_AVAILABLE = saved_crawl
    print("ok  X login wall fails honestly and persists nothing")


# ---- A1/A2: extension wiring (source contracts) ---------------------------

def _read(rel):
    return (EXT / rel).read_text(encoding="utf-8")


def test_single_js_definition_delegates():
    """extract.js must not keep its own Article regex -- it delegates to the
    single XArticle definition (loaded before it in popup.html + background)."""
    lib = _read("lib/extract.js")
    _assert("_X_ARTICLE_ID_RE" not in lib and "_X_ARTICLE_HOSTS" not in lib,
            "extract.js must drop its duplicate Article regex/host copy")
    _assert("global.XArticle" in lib and "normalizeXArticleUrl" in lib,
            "extract.js normalizeXArticleUrl must delegate to XArticle")
    _assert("resolveTabSource" in lib,
            "extract.js must export resolveTabSource (DOM-aware routing)")
    popup_html = _read("popup.html")
    _assert(popup_html.index('lib/x-article.js') < popup_html.index('lib/extract.js'),
            "popup.html must load x-article.js before extract.js")
    bg = _read("background.js")
    _assert('importScripts("lib/x-article.js"' in bg,
            "background.js must importScripts x-article.js before extract.js")
    print("ok  one JS Article definition; extract.js delegates to XArticle")


def test_context_menu_routes_article_to_dom_parse():
    """The right-click menu must detect an X Article and route it to the
    in-page DOM parse, not the static login-walled /extract/page fetch."""
    bg = _read("background.js")
    _assert('title: "Uoink this page (article)"' not in bg,
            "the static 'Uoink this page (article)' label must be gone")
    _assert("captureXArticleFromTab" in bg,
            "context menu must call the article DOM-parse capture")
    _assert("uoinkParseXArticle" in bg,
            "background must ask the content script to parse the article DOM")
    _assert("isXArticleTab" in bg and "updateArticleMenuTitle" in bg,
            "menu must detect an X Article and keep its label honest per tab")
    print("ok  context menu detects X Articles and routes to the DOM parse")


def test_popup_resolves_via_dom():
    """The popup must resolve the tab source with a live-DOM signal so an
    article reached via /status/, t.co, or an unsettled SPA route is still
    recognised (not silently 'Uoink this page')."""
    popup = _read("popup.js")
    _assert("resolveTabSource" in popup and "probeXArticleDom" in popup,
            "popup must probe the DOM and resolve via resolveTabSource")
    _assert("hasArticleDom" in popup,
            "popup must pass the DOM signal into resolution")
    print("ok  popup resolves the article via a live-DOM probe")


def test_popup_walled_feedback_is_persistent():
    """The popup's walled-capture feedback must be a persistent alert, not a
    1.8s toast, with actionable copy and no saved junk."""
    popup = _read("popup.js")
    _assert("showSourceAlert" in popup,
            "popup must have a persistent source alert helper")
    _assert('x_login_wall' in popup,
            "popup must special-case the X login wall")
    # The walled branch must not use the transient toast.
    idx = popup.index("x_login_wall")
    window = popup[idx:idx + 600]
    _assert("showSourceAlert" in window and "showToast" not in window,
            "walled branch must use the persistent alert, not showToast")
    _assert("Nothing was saved" in popup,
            "walled copy must state nothing was saved")
    popup_html = _read("popup.html")
    _assert('id="current-source-alert"' in popup_html,
            "popup.html must contain the persistent alert element")
    print("ok  popup walled feedback is persistent + honest")


def test_background_walled_feedback():
    bg = _read("background.js")
    _assert("notifyWalledXArticle" in bg,
            "background must have an honest walled-capture notification")
    _assert("requireInteraction: true" in bg,
            "walled/failure notifications must be persistent (requireInteraction)")
    _assert("Nothing was saved" in bg,
            "walled copy must state nothing was saved")
    print("ok  background walled feedback is persistent + honest")


def test_token_403_refresh_on_page_path():
    """/extract/page (and every authed route) must ride the 403 token-refresh
    retry so a stale token can't dead-end the capture."""
    lib = _read("lib/extract.js")
    _assert("_authedFetch(\"/extract/page\"" in lib,
            "postExtractPage must go through the authed fetch (403 retry)")
    idx = lib.index("if (res.status === 403)")
    window = lib[idx:idx + 900]
    _assert("getToken({ refresh: true })" in window and "_readStoredToken" in window,
            "the 403 path must refresh the token (with a stored-token fallback)")
    print("ok  stale-token 403 refreshes on /extract/page (no second dead end)")


def test_no_em_en_dashes_in_new_copy():
    """Voice DNA: no em/en dashes in the user-facing copy we added."""
    for rel in ("popup.js", "background.js"):
        text = _read(rel)
        for needle in ("Nothing was saved", "Uoink this article",
                       "logged-out link fetches", "X blocks"):
            for line in text.splitlines():
                if needle in line:
                    _assert("—" not in line and "–" not in line,
                            f"em/en dash in new copy ({rel}): {line.strip()}")
    print("ok  no em/en dashes in the new user-facing copy")


# ---- JS harnesses ---------------------------------------------------------

def _run_node(script):
    return subprocess.run(["node", str(REPO_ROOT / "tests" / "js" / script)],
                          cwd=str(REPO_ROOT), capture_output=True, text=True)


def test_js_routing_harness():
    if shutil.which("node") is None:
        print("skip  node not available; routing harness needs Node")
        return
    proc = _run_node("x_article_routing_test.mjs")
    _assert(proc.returncode == 0,
            f"routing harness failed:\n{proc.stdout}\n{proc.stderr}")
    print("ok  X Article routing harness (resolveTabSource + delegation) green")


def test_node_check_edited_js():
    if shutil.which("node") is None:
        print("skip  node not available; node --check needs Node")
        return
    for rel in ("background.js", "popup.js", "lib/extract.js", "lib/x-article.js"):
        proc = subprocess.run(["node", "--check", str(EXT / rel)],
                              capture_output=True, text=True)
        _assert(proc.returncode == 0,
                f"node --check failed on {rel}:\n{proc.stderr}")
    print("ok  node --check clean on the edited extension JS")


def main():
    for fn in (
        test_shared_detector_agreement,
        test_shared_detector_positive_and_canonical,
        test_server_classifier_uses_shared_detector,
        test_walled_capture_honest_and_persists_nothing,
        test_single_js_definition_delegates,
        test_context_menu_routes_article_to_dom_parse,
        test_popup_resolves_via_dom,
        test_popup_walled_feedback_is_persistent,
        test_background_walled_feedback,
        test_token_403_refresh_on_page_path,
        test_no_em_en_dashes_in_new_copy,
        test_js_routing_harness,
        test_node_check_edited_js,
    ):
        fn()
    print("\nall green")


if __name__ == "__main__":
    main()
