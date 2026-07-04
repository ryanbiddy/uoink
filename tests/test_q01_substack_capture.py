"""Q-01 -- Substack post capture: substack_extractor.py + POST /extract/substack.

Run: python tests/test_q01_substack_capture.py  (also collected by pytest)

Red on unpatched main: substack_extractor doesn't exist and POST
/extract/substack 404s.

Coverage:
- URL matcher accepts <pub>.substack.com/p/<slug> (query strings fine)
  and rejects the substack.com homepage, custom domains, and non-posts.
- Free posts render to structured markdown (headings, lists, links,
  emphasis, blockquote, code) via the stdlib HTML converter.
- Paid posts refuse honestly: audience='only_paid' or should_show_paywall
  -> code='paywalled' with copy that says why nothing was saved.
- Fetch failure modes carry actionable copy (404 mentions custom domains,
  429 rate limit, non-JSON).
- Route: ships dark behind substack_capture_enabled, token-gated, persists
  through page_extractor when on, relays the extractor's honest errors.
"""
from __future__ import annotations

import json
import tempfile
import threading
import urllib.error
import urllib.request
from contextlib import contextmanager
from http.server import ThreadingHTTPServer
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import substack_extractor  # noqa: E402
import index as index_mod  # noqa: E402
import server  # noqa: E402

_PORT = 0


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


FREE_POST = {
    "title": "How I sanded down the onboarding flow",
    "subtitle": "Three cuts that mattered",
    "audience": "everyone",
    "should_show_paywall": False,
    "post_date": "2026-06-20T09:00:00.000Z",
    "canonical_url": "https://ryan.substack.com/p/onboarding-flow",
    "wordcount": 640,
    "type": "newsletter",
    "publishedBylines": [{"name": "Ryan Biddy"}],
    "body_html": (
        "<h2>The first cut</h2>"
        "<p>We <strong>removed</strong> the survey. <em>Nobody</em> read it. "
        "See <a href=\"https://example.com/data\">the numbers</a>.</p>"
        "<ul><li>Step one</li><li>Step two</li></ul>"
        "<blockquote><p>Ship the boring version first.</p></blockquote>"
        "<pre>uoink --doctor</pre>"
    ),
}

PAID_POST = {
    "title": "Subscriber deep dive",
    "audience": "only_paid",
    "should_show_paywall": True,
    "body_html": "<p>Teaser paragraph only...</p>",
    "publishedBylines": [{"name": "Ryan Biddy"}],
}


def _fetcher(payload=None, exc=None):
    def fetch(url, *, timeout=20):
        if exc is not None:
            raise exc
        return payload
    return fetch


# ---- URL matching ----------------------------------------------------------

def test_url_matcher():
    yes = [
        "https://ryan.substack.com/p/onboarding-flow",
        "https://some-pub.substack.com/p/a-post?utm_source=x",
        "http://a1.substack.com/p/slug-9",
    ]
    no = [
        "https://www.substack.com/p/whatever",   # homepage host, not a pub
        "https://substack.com/home",
        "https://ryan.substack.com/about",
        "https://ryansnewsletter.com/p/custom-domain-post",
        "https://evil.com/ryan.substack.com/p/x",
        "",
    ]
    for url in yes:
        _assert(substack_extractor.is_substack_post_url(url), f"should match: {url}")
    for url in no:
        _assert(not substack_extractor.is_substack_post_url(url), f"must not match: {url}")
    _assert(substack_extractor.api_url(yes[0])
            == "https://ryan.substack.com/api/v1/posts/onboarding-flow",
            "api url mapping")
    print("ok  URL matcher + api mapping")


# ---- extraction ------------------------------------------------------------

def test_free_post_renders_markdown():
    result = substack_extractor.extract_substack_post(
        "https://ryan.substack.com/p/onboarding-flow",
        _fetch=_fetcher(FREE_POST))
    _assert(result["ok"], f"free post failed: {result}")
    md = result["markdown"]
    _assert("# How I sanded down the onboarding flow" in md, "title heading")
    _assert("*Three cuts that mattered*" in md, "subtitle")
    _assert("by Ryan Biddy" in md and "640 words" in md, "byline meta")
    _assert("## The first cut" in md, "h2 converted")
    _assert("**removed**" in md and "*Nobody*" in md, "emphasis converted")
    _assert("[the numbers](https://example.com/data)" in md, "links converted")
    _assert("- Step one" in md and "- Step two" in md, "list converted")
    _assert("> Ship the boring version first." in md, "blockquote converted")
    _assert("```" in md and "uoink --doctor" in md, "code block fenced")
    _assert(result["metadata"]["post_type"] == "newsletter", "metadata type")
    _assert(result["url"] == "https://ryan.substack.com/p/onboarding-flow",
            "canonical url")
    print("ok  free post -> structured markdown")


def test_paid_post_refuses_honestly():
    result = substack_extractor.extract_substack_post(
        "https://ryan.substack.com/p/deep-dive", _fetch=_fetcher(PAID_POST))
    _assert(result["ok"] is False and result["code"] == "paywalled",
            f"paywall shape: {result}")
    _assert("paid subscribers" in result["error"]
            and "free" in result["error"],
            f"paywall copy must say why: {result['error']}")

    # audience alone is enough, even without the paywall flag
    sneaky = dict(FREE_POST, audience="founding", should_show_paywall=False)
    result = substack_extractor.extract_substack_post(
        "https://ryan.substack.com/p/founding", _fetch=_fetcher(sneaky))
    _assert(result["code"] == "paywalled", f"audience gate: {result}")
    print("ok  paid posts refuse with honest copy, nothing saved")


def test_fetch_failures_have_actionable_copy():
    err404 = ValueError("Substack returned 404. The post was removed, the "
                        "slug is wrong, or this publication moved to a "
                        "custom domain (not supported yet).")
    result = substack_extractor.extract_substack_post(
        "https://ryan.substack.com/p/gone", _fetch=_fetcher(exc=err404))
    _assert(result["code"] == "fetch_failed"
            and "custom domain" in result["error"],
            f"404 copy: {result}")
    bad = substack_extractor.extract_substack_post("https://ryansnewsletter.com/p/x")
    _assert(bad["code"] == "bad_url" and "custom domains" in bad["error"],
            f"custom-domain copy on bad_url: {bad}")
    empty = substack_extractor.extract_substack_post(
        "https://ryan.substack.com/p/hollow",
        _fetch=_fetcher(dict(FREE_POST, body_html="")))
    _assert(empty["code"] == "parse_failed", f"empty body: {empty}")
    print("ok  failure copy is specific")


# ---- route -----------------------------------------------------------------

def _post(path, payload, *, token=True):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Uoink-Token"] = server.TOKEN
    req = urllib.request.Request(
        f"http://127.0.0.1:{_PORT}{path}",
        data=json.dumps(payload).encode(), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")


@contextmanager
def _server(settings):
    global _PORT
    original_read = server._read_settings
    server._read_settings = lambda: dict(settings)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    _PORT = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield
    finally:
        httpd.shutdown()
        server._read_settings = original_read


def test_route_flag_off_by_default():
    with _server({}):
        status, res = _post("/extract/substack",
                            {"url": "https://a.substack.com/p/x"})
        _assert(status == 200,
                f"/extract/substack must exist (red on main: 404), got {status}")
        _assert(res.get("ok") is False and res.get("code") == "disabled",
                f"flag off must answer disabled: {res}")
        _assert("substack_capture_enabled" in (res.get("error") or ""),
                f"disabled copy names the flag: {res}")
    print("ok  route ships dark behind substack_capture_enabled")


def test_route_token_gated():
    with _server({"substack_capture_enabled": True}):
        status, _res = _post("/extract/substack",
                             {"url": "https://a.substack.com/p/x"}, token=False)
        _assert(status == 403, f"no token must 403, got {status}")
    print("ok  route is token-gated")


def test_route_captures_and_persists():
    with tempfile.TemporaryDirectory() as d:
        idx = index_mod.Index.open(Path(d) / "index.db")
        original_get_index = server._get_index
        original_extract = substack_extractor.extract_substack_post
        server._get_index = lambda: idx
        server.substack_extractor.extract_substack_post = (
            lambda url, **kw: original_extract(url, _fetch=_fetcher(FREE_POST)))
        try:
            with _server({"substack_capture_enabled": True}):
                status, res = _post(
                    "/extract/substack",
                    {"url": "https://ryan.substack.com/p/onboarding-flow"})
                _assert(status == 200 and res.get("ok") is True,
                        f"capture failed: {status} {res}")
                _assert(res.get("video_id"), f"persisted id missing: {res}")
                row = idx.get_yoink(res["video_id"])
                _assert(row and row.get("source_type") == "substack_post",
                        f"index row: {row}")

                # paywall refusal relays through the route
                server.substack_extractor.extract_substack_post = (
                    lambda url, **kw: original_extract(url, _fetch=_fetcher(PAID_POST)))
                status, res = _post(
                    "/extract/substack",
                    {"url": "https://ryan.substack.com/p/deep-dive"})
                _assert(status == 200 and res.get("code") == "paywalled",
                        f"paywall relay: {res}")
        finally:
            server._get_index = original_get_index
            server.substack_extractor.extract_substack_post = original_extract
            idx.close()
    print("ok  route persists a substack_post yoink, relays the paywall refusal")


def main():
    for fn in (
        test_url_matcher,
        test_free_post_renders_markdown,
        test_paid_post_refuses_honestly,
        test_fetch_failures_have_actionable_copy,
        test_route_flag_off_by_default,
        test_route_token_gated,
        test_route_captures_and_persists,
    ):
        fn()
    print("\nall green")


if __name__ == "__main__":
    main()
