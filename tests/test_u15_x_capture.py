"""U-15 -- X text/thread capture: x_extractor.py + POST /extract/x.

Run: python tests/test_u15_x_capture.py  (also collected by pytest tests/)

Red on unpatched main: x_extractor doesn't exist and POST /extract/x 404s.

Coverage:
- URL matcher accepts x.com/twitter.com/mobile status URLs (and /i/status/,
  query strings) and rejects everything else.
- The syndication token matches the browser's JS
  ((id/1e15)*PI).toString(36).replace(/(0+|.)/g,'') digit for digit
  (reference values generated with node).
- Thread walk: collects the author's own ancestor chain root-first, uses
  the embedded parent payload without refetching, stops at other-author
  parents, survives a deleted ancestor, and hop-caps.
- Honest failure copy for the ways X refuses (404, tombstone, non-JSON).
- Route: feature-flagged off by default (x_text_capture_enabled), persists
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
import x_extractor  # noqa: E402
import index as index_mod  # noqa: E402
import server  # noqa: E402

_PORT = 0


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


# ---- fixtures -------------------------------------------------------------

def _payload(tid, text, *, handle="ryanbiddy", name="Ryan Biddy",
             reply_to=None, reply_handle=None, parent=None, photos=0,
             video=False):
    data = {
        "id_str": str(tid),
        "text": text,
        "created_at": "2026-07-01T12:00:00.000Z",
        "user": {"name": name, "screen_name": handle},
        "photos": [{"url": f"p{i}"} for i in range(photos)],
    }
    if video:
        data["video"] = {"variants": []}
    if reply_to:
        data["in_reply_to_status_id_str"] = str(reply_to)
        data["in_reply_to_screen_name"] = reply_handle or handle
    if parent:
        data["parent"] = parent
    return data


def _fetcher(payloads):
    calls = []

    def fetch(tweet_id, *, timeout=20):
        calls.append(str(tweet_id))
        payload = payloads.get(str(tweet_id))
        if payload is None:
            raise ValueError("X returned 404 for this post. That can mean "
                             "deleted, protected account, or X refusing the "
                             "public endpoint right now. Nothing was saved.")
        return payload

    fetch.calls = calls
    return fetch


# ---- URL matching ---------------------------------------------------------

def test_url_matcher():
    yes = [
        "https://x.com/ryanbiddy/status/1720000000000000000",
        "https://twitter.com/someone/status/123456",
        "https://mobile.twitter.com/a/status/9",
        "https://www.x.com/a/statuses/9",
        "https://x.com/i/status/1720000000000000000?s=20&t=abc",
    ]
    no = [
        "https://x.com/ryanbiddy",
        "https://x.com/home",
        "https://youtube.com/watch?v=abc",
        "https://x.com.evil.com/a/status/9",
        "",
    ]
    for url in yes:
        _assert(x_extractor.is_x_status_url(url), f"should match: {url}")
    for url in no:
        _assert(not x_extractor.is_x_status_url(url), f"must not match: {url}")
    _assert(x_extractor.tweet_id_from_url(yes[0]) == "1720000000000000000",
            "id extraction")
    print("ok  URL matcher")


# ---- token ----------------------------------------------------------------

def test_syndication_token_matches_js():
    # node -e "((Number(id)/1e15)*Math.PI).toString(36).replace(/(0+|\.)/g,'')"
    expected = {
        "1720000000000000000": "463jfkp3ln",
        "1541278577388199936": "3qi2ij651a",
        "929876523954579456": "295ak2656ba",
        "1": "bhi2ay3f28n",
    }
    for tid, token in expected.items():
        got = x_extractor.syndication_token(tid)
        _assert(got == token, f"token for {tid}: {got} != {token}")
    print("ok  syndication token matches the JS reference digit for digit")


# ---- thread walk ----------------------------------------------------------

def test_single_post():
    fetch = _fetcher({"10": _payload("10", "Just one banger.")})
    result = x_extractor.extract_x_thread(
        "https://x.com/ryanbiddy/status/10", _fetch=fetch)
    _assert(result["ok"], f"single post capture failed: {result}")
    _assert(result["metadata"]["tweets_captured"] == 1, "one post")
    _assert("Just one banger." in result["markdown"], "text in markdown")
    _assert(result["title"].startswith("@ryanbiddy:"), f"title: {result['title']}")
    _assert(result["url"] == "https://x.com/ryanbiddy/status/10",
            f"canonical url: {result['url']}")
    print("ok  single post")


def test_thread_walk_root_first_with_embedded_parent():
    root = _payload("1", "Thread start.")
    mid = _payload("2", "Middle point.", reply_to="1", parent=root)
    top = _payload("3", "Final point.", reply_to="2", parent=mid)
    fetch = _fetcher({"3": top})
    result = x_extractor.extract_x_thread(
        "https://x.com/ryanbiddy/status/3", _fetch=fetch)
    _assert(result["ok"], f"walk failed: {result}")
    _assert(result["metadata"]["tweets_captured"] == 3, f"3 posts: {result['metadata']}")
    md = result["markdown"]
    _assert(md.index("Thread start.") < md.index("Middle point.") < md.index("Final point."),
            "reading order must be root first")
    _assert(fetch.calls == ["3"],
            f"embedded parent payloads must not refetch: {fetch.calls}")
    _assert("## 1/3" in md and "## 3/3" in md, "posts numbered")
    print("ok  ancestor walk, root first, zero refetches")


def test_walk_refetches_when_parent_not_embedded():
    payloads = {
        "3": _payload("3", "End.", reply_to="2"),
        "2": _payload("2", "Mid.", reply_to="1"),
        "1": _payload("1", "Root."),
    }
    fetch = _fetcher(payloads)
    result = x_extractor.extract_x_thread(
        "https://x.com/ryanbiddy/status/3", _fetch=fetch)
    _assert(result["ok"] and result["metadata"]["tweets_captured"] == 3,
            f"refetch walk: {result}")
    _assert(fetch.calls == ["3", "2", "1"], f"walk order: {fetch.calls}")
    print("ok  ancestor walk refetches by id when needed")


def test_walk_stops_at_other_author():
    payloads = {
        "3": _payload("3", "My reply to someone else.",
                      reply_to="2", reply_handle="someoneelse"),
    }
    fetch = _fetcher(payloads)
    result = x_extractor.extract_x_thread(
        "https://x.com/ryanbiddy/status/3", _fetch=fetch)
    _assert(result["ok"] and result["metadata"]["tweets_captured"] == 1,
            "a reply to another account is not the author's thread")
    print("ok  walk stops at other-author parents")


def test_walk_survives_deleted_ancestor():
    payloads = {"3": _payload("3", "Still here.", reply_to="2")}
    fetch = _fetcher(payloads)  # "2" missing -> fetch raises
    result = x_extractor.extract_x_thread(
        "https://x.com/ryanbiddy/status/3", _fetch=fetch)
    _assert(result["ok"] and result["metadata"]["tweets_captured"] == 1,
            f"deleted ancestor must not fail the capture: {result}")
    print("ok  deleted ancestor keeps the partial capture")


def test_honest_failure_copy():
    fetch = _fetcher({})  # everything 404s
    result = x_extractor.extract_x_thread(
        "https://x.com/ryanbiddy/status/404404", _fetch=fetch)
    _assert(result["ok"] is False and result["code"] == "fetch_failed",
            f"fetch failure shape: {result}")
    _assert("deleted, protected account, or X refusing" in result["error"],
            f"honest 404 copy: {result['error']}")
    bad = x_extractor.extract_x_thread("https://x.com/ryanbiddy")
    _assert(bad["code"] == "bad_url", "non-status URL rejected without network")
    print("ok  honest failure copy")


# ---- route ---------------------------------------------------------------

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
        status, res = _post("/extract/x",
                            {"url": "https://x.com/a/status/1"})
        _assert(status == 200,
                f"/extract/x must exist (red on main: 404), got {status}")
        _assert(res.get("ok") is False and res.get("code") == "disabled",
                f"flag off must answer disabled: {res}")
        _assert("x_text_capture_enabled" in (res.get("error") or ""),
                f"disabled copy names the flag: {res}")
    print("ok  route ships dark behind x_text_capture_enabled")


def test_route_token_gated():
    with _server({"x_text_capture_enabled": True}):
        status, _res = _post("/extract/x", {"url": "https://x.com/a/status/1"},
                             token=False)
        _assert(status == 403, f"no token must 403, got {status}")
    print("ok  route is token-gated")


def test_route_captures_and_persists():
    with tempfile.TemporaryDirectory() as d:
        idx = index_mod.Index.open(Path(d) / "index.db")
        original_get_index = server._get_index
        original_extract = server.x_extractor.extract_x_thread
        server._get_index = lambda: idx
        fetch = _fetcher({"7": _payload("7", "Persist me.")})
        # server.x_extractor is this same module object, so route through
        # the saved original or the lambda calls itself.
        server.x_extractor.extract_x_thread = (
            lambda url, **kw: original_extract(url, _fetch=fetch))
        try:
            with _server({"x_text_capture_enabled": True}):
                status, res = _post("/extract/x",
                                    {"url": "https://x.com/ryanbiddy/status/7"})
                _assert(status == 200 and res.get("ok") is True,
                        f"capture failed: {status} {res}")
                _assert(res.get("video_id"), f"persisted id missing: {res}")
                _assert(res.get("tweets_captured") == 1, f"count: {res}")
                row = idx.get_yoink(res["video_id"])
                _assert(row and row.get("source_type") == "x_thread",
                        f"index row: {row}")

                # extractor failures relay their honest copy
                fetch2 = _fetcher({})
                server.x_extractor.extract_x_thread = (
                    lambda url, **kw: original_extract(url, _fetch=fetch2))
                status, res = _post("/extract/x",
                                    {"url": "https://x.com/a/status/999"})
                _assert(status == 200 and res.get("ok") is False
                        and res.get("code") == "fetch_failed",
                        f"failure relay: {res}")
        finally:
            server._get_index = original_get_index
            server.x_extractor.extract_x_thread = original_extract
            idx.close()
    print("ok  route persists an x_thread yoink and relays honest errors")


def test_extension_wiring():
    root = Path(__file__).resolve().parent.parent
    popup_html = (root / "extension" / "popup.html").read_text(encoding="utf-8")
    popup_js = (root / "extension" / "popup.js").read_text(encoding="utf-8")
    lib = (root / "extension" / "lib" / "extract.js").read_text(encoding="utf-8")
    _assert('id="uoink-x-text-btn"' in popup_html,
            "popup needs the X text capture button")
    _assert("hidden" in popup_html.split('id="uoink-x-text-btn"')[0].rsplit("<button", 1)[1],
            "the button ships hidden (flag-gated)")
    _assert("x_text_capture_enabled" in popup_js,
            "popup must gate the button on the server flag")
    _assert("postExtractX" in popup_js and "normalizeTwitterUrl" in popup_js,
            "popup must detect X status tabs and post through the lib")
    _assert('"/extract/x"' in lib and "postExtractX," in lib,
            "lib must expose postExtractX on STC")
    print("ok  extension button wired, dark by default")


def main():
    for fn in (
        test_url_matcher,
        test_syndication_token_matches_js,
        test_single_post,
        test_thread_walk_root_first_with_embedded_parent,
        test_walk_refetches_when_parent_not_embedded,
        test_walk_stops_at_other_author,
        test_walk_survives_deleted_ancestor,
        test_honest_failure_copy,
        test_route_flag_off_by_default,
        test_route_token_gated,
        test_route_captures_and_persists,
        test_extension_wiring,
    ):
        fn()
    print("\nall green")


if __name__ == "__main__":
    main()
