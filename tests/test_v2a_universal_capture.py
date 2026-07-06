"""V-2a -- universal "paste a URL to uoink" capture.

Run: python tests/test_v2a_universal_capture.py  (also collected by pytest)

Covers the detection brain (server._classify_capture_url), the GET /detect
route that exposes it, and the dashboard wiring that routes each detected
source to the right existing capture endpoint.

Red on unpatched main: _classify_capture_url doesn't exist and GET /detect
404s.

Detection reuses the validators that already ship (_normalize_youtube_url,
_normalize_playlist_url, _normalize_twitter_url,
reddit_extractor.is_reddit_thread_url, _normalize_any_url), so the chip can
never claim a source the capture route would reject.
"""
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.parse
import urllib.request
from contextlib import contextmanager
from http.server import ThreadingHTTPServer
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import server  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DASHBOARD = (ROOT / "assets" / "dashboard" / "index.html").read_text(
    encoding="utf-8")

_PORT = 0


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


# ---- classifier unit coverage --------------------------------------------

def test_classifier_routes_each_source():
    cases = {
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ":
            ("youtube_video", "/extract", "url"),
        "https://youtu.be/dQw4w9WgXcQ?si=track":
            ("youtube_video", "/extract", "url"),
        "https://www.youtube.com/playlist?list=PLabcdEFGH12345678":
            ("youtube_playlist", "/playlist/start", "url"),
        "https://x.com/ryanbiddy/status/1790000000000000000":
            ("x_video", "/extract", "url"),
        "https://twitter.com/i/status/1790000000000000000":
            ("x_video", "/extract", "url"),
        "https://www.reddit.com/r/python/comments/abc123/some_title/":
            ("reddit_thread", "/extract/reddit", "url"),
        "https://feeds.megaphone.fm/vergecast":
            ("podcast_feed", "/podcasts/feeds", "feed_url"),
        "https://example.com/podcast/feed.xml":
            ("podcast_feed", "/podcasts/feeds", "feed_url"),
        "https://arstechnica.com/some/article/":
            ("web_page", "/extract/page", "url"),
    }
    for url, (source, endpoint, key) in cases.items():
        r = server._classify_capture_url(url)
        _assert(r["ok"] is True, f"{url} should be supported: {r}")
        _assert(r["source"] == source,
                f"{url} -> {r['source']} expected {source}")
        _assert(r["endpoint"] == endpoint,
                f"{url} endpoint {r['endpoint']} expected {endpoint}")
        _assert(r["payload_key"] == key,
                f"{url} payload_key {r['payload_key']} expected {key}")
        _assert(r["canonical"], f"{url} should carry a canonical form: {r}")
    print("ok  every supported source routes to its existing endpoint")


def test_classifier_video_wins_over_playlist():
    # A watch URL that also carries a list= is a video (they're watching
    # one), not a playlist add.
    r = server._classify_capture_url(
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PLabcdEFGH12345678")
    _assert(r["source"] == "youtube_video",
            f"watch+list should be a video: {r}")
    print("ok  watch?v=...&list=... is a single video, not a playlist")


def test_classifier_x_is_video_only_and_honest():
    r = server._classify_capture_url(
        "https://x.com/ryanbiddy/status/1790000000000000000")
    note = (r.get("note") or "").lower()
    _assert("video only" in note,
            f"X note must say video only: {r}")
    _assert("text isn't supported" in note or "text isn" in note,
            f"X note must be honest about missing text: {r}")
    print("ok  X detection is honest: video only, no text")


def test_classifier_unsupported_is_honest_not_an_error():
    for bad in ("ftp://evil.com/x", "javascript:alert(1)", "not a url", ""):
        r = server._classify_capture_url(bad)
        _assert(r["ok"] is False, f"{bad!r} should not be supported: {r}")
        _assert(r["endpoint"] is None, f"{bad!r} has no endpoint: {r}")
    unsup = server._classify_capture_url("ftp://evil.com/x")
    _assert("not a supported source" in (unsup["label"] or "").lower(),
            f"unsupported label must be plain: {unsup}")
    print("ok  unsupported URLs answer honestly instead of failing weird")


# ---- GET /detect route ----------------------------------------------------

def _get(path, token=True):
    headers = {"X-Uoink-Token": server.TOKEN} if token else {}
    req = urllib.request.Request(
        f"http://127.0.0.1:{_PORT}{path}", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")


@contextmanager
def _server():
    global _PORT
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    _PORT = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield
    finally:
        httpd.shutdown()


def test_detect_route_classifies():
    with _server():
        status, res = _get(
            "/detect?url=" + urllib.parse.quote(
                "https://www.reddit.com/r/python/comments/abc/x/"))
        _assert(status == 200, f"/detect must exist (red on main 404): {status}")
        _assert(res.get("source") == "reddit_thread"
                and res.get("endpoint") == "/extract/reddit",
                f"reddit routed: {res}")

        status, res = _get(
            "/detect?url=" + urllib.parse.quote(
                "https://www.youtube.com/watch?v=dQw4w9WgXcQ"))
        _assert(res.get("ok") is True and res.get("endpoint") == "/extract",
                f"youtube routed: {res}")

        # Unsupported is a valid 200 answer, not an HTTP error.
        status, res = _get("/detect?url=" + urllib.parse.quote("ftp://x/y"))
        _assert(status == 200 and res.get("ok") is False,
                f"unsupported answers 200 ok:false: {status} {res}")
    print("ok  GET /detect classifies and answers 200 for unsupported")


def test_detect_route_token_gated():
    with _server():
        status, _res = _get("/detect?url=https://x.com/a/status/1", token=False)
        _assert(status in (401, 403), f"detect must be token-gated: {status}")
    print("ok  GET /detect is token-gated")


# ---- dashboard wiring -----------------------------------------------------

def test_dashboard_has_universal_capture_box():
    for marker in (
        'id="universalCapture"',
        'id="universalCaptureInput"',
        'id="universalCaptureChip"',
        'id="universalCaptureButton"',
        'id="universalCaptureNote"',
        'id="emptyPasteUrl"',
    ):
        _assert(marker in DASHBOARD, f"dashboard missing {marker}")
    print("ok  universal capture box + empty-state entry present")


def test_dashboard_detects_and_routes_by_endpoint():
    _assert("/detect?url=" in DASHBOARD,
            "dashboard must call GET /detect for detection")
    _assert("runUniversalCapture" in DASHBOARD
            and "universalState.endpoint" in DASHBOARD,
            "dashboard must route the capture off the detected endpoint")
    # It posts to the endpoint the server handed back, not a hardcoded route,
    # so it can never drift from detection.
    _assert("authFetch(universalState.endpoint" in DASHBOARD,
            "capture must POST to the detected endpoint")
    _assert("feed_url" in DASHBOARD,
            "podcast feed uses the feed_url payload key")
    print("ok  dashboard routes each source to its detected endpoint")


def test_dashboard_x_video_only_copy_is_honest():
    # The honesty copy is server-owned (the note travels with detection),
    # so the box shows exactly what the classifier says.
    _assert("universalCaptureNote" in DASHBOARD
            and "result.note" in DASHBOARD,
            "dashboard must render the server detection note verbatim")
    print("ok  dashboard renders the honest per-source note")


def test_new_copy_has_no_em_dashes():
    # Voice DNA: no em dashes in user-facing copy. Check the strings we added.
    for snippet in ("Uoink anything", "Paste a URL to uoink",
                    "Detection runs as you paste"):
        idx = DASHBOARD.find(snippet)
        _assert(idx != -1, f"expected copy present: {snippet}")
    # No em dash or en dash in the universal-capture block.
    block = DASHBOARD.split('id="universalCapture"', 1)[1].split(
        'id="getExtensionCard"', 1)[0]
    _assert("—" not in block and "–" not in block,
            "no em/en dashes in the universal capture copy")
    print("ok  new copy respects Voice DNA (no em dashes)")


def main():
    for fn in (
        test_classifier_routes_each_source,
        test_classifier_video_wins_over_playlist,
        test_classifier_x_is_video_only_and_honest,
        test_classifier_unsupported_is_honest_not_an_error,
        test_detect_route_classifies,
        test_detect_route_token_gated,
        test_dashboard_has_universal_capture_box,
        test_dashboard_detects_and_routes_by_endpoint,
        test_dashboard_x_video_only_copy_is_honest,
        test_new_copy_has_no_em_dashes,
    ):
        fn()
    print("\nALL V-2A UNIVERSAL CAPTURE TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
