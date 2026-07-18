"""v3.3.3 -- three live bugs Ryan hit on v3.3.2.

Run: python tests/test_v333_live_fixes.py  (also collected by pytest tests/)

Red on unpatched main:
- Bug 1: x_extractor has no is_x_article_url; _classify_capture_url routes an
  X Article URL to the generic "web_page" source with the generic note, and
  page_extractor happily persists X's "JavaScript is not available" login
  wall as a junk uoink (title=None) instead of failing honestly.
- Bug 2: server._plain_error_from_text turns an X 404 (no video in the post)
  into "X would not hand this one over cleanly" with the "Single-video"
  download framing -- no honest guidance that a post/thread is text. Reconciled
  with V-2c: the honest copy now also points long-form X Articles at the
  extension's "Uoink this article" button (Articles ARE supported).
- Bug 3: the uoink detail header (#tab-yoink .page-head) has no rule making
  the detail action toolbar a full-width wrapping row, so the controls wrap
  into a squeezed right column and get cut off on a DPI-scaled window.

These tests avoid pytest-only fixtures so the file also runs standalone.
"""
from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import x_extractor  # noqa: E402
import page_extractor  # noqa: E402
import server  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DASHBOARD = (ROOT / "assets" / "dashboard" / "index.html").read_text(
    encoding="utf-8")


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


# ---- Bug 1: X Article detection + honest routing -------------------------

def test_x_extractor_detects_article_urls():
    articles = [
        "https://x.com/paulg/article/1789012345678901234",
        "https://x.com/i/article/1789012345678901234",
        "https://twitter.com/paulg/article/1789012345678901234",
        "https://www.x.com/paulg/article/1789012345678901234",
        # A1: detection is now the single strict x_article_extractor shape
        # (id >= 5 chars), shared by classify + persist so they can't disagree.
        "https://mobile.twitter.com/paulg/article/98765",
    ]
    for u in articles:
        _assert(x_extractor.is_x_article_url(u),
                f"should detect X Article: {u}")
    not_articles = [
        "https://x.com/paulg/status/1789012345678901234",
        "https://x.com/i/status/1789012345678901234",
        "https://example.com/paulg/article/1",
        "https://x.com/paulg",
        "",
    ]
    for u in not_articles:
        _assert(not x_extractor.is_x_article_url(u),
                f"should NOT be an X Article: {u}")
    # An Article URL is not a status URL and yields no tweet id.
    _assert(not x_extractor.is_x_status_url(
        "https://x.com/paulg/article/1789012345678901234"),
        "an Article URL must not read as a status URL")
    print("ok  is_x_article_url matches Articles, rejects posts/other hosts")


def test_classifier_routes_x_article_honestly():
    r = server._classify_capture_url(
        "https://x.com/paulg/article/1789012345678901234")
    _assert(r["ok"] is True, f"X Article should classify, not error: {r}")
    _assert(r["source"] == "x_article",
            f"X Article must be its own source, not generic web_page: {r}")
    _assert(r["endpoint"] == "/extract/page",
            f"best-effort route is the web-page path: {r}")
    note = (r.get("note") or "").lower()
    _assert("article" in note,
            f"note must name X Articles specifically: {r}")
    _assert("login" in note or "log in" in note or "logged" in note,
            f"note must be honest about X's login wall: {r}")
    _assert("—" not in (r.get("note") or "") and "–" not in (r.get("note") or ""),
            "no em/en dashes in the X Article note (Voice DNA)")
    # A real X post still routes to the full text/thread path.
    p = server._classify_capture_url(
        "https://x.com/paulg/status/1789012345678901234")
    _assert(p["source"] == "x_video" and p["endpoint"] == "/extract/x",
            f"a real X post must still route to /extract/x: {p}")
    print("ok  X Article routes to a best-effort page path with honest copy")


def _x_login_wall_result(url):
    return {
        "ok": True,
        "extraction_engine": "stdlib",
        "url": url,
        "title": None,
        "markdown": (
            "# JavaScript is not available.\n\n"
            "We've detected that JavaScript is disabled in this browser. "
            "Please enable JavaScript or switch to a supported browser to "
            "continue using x.com."),
        "metadata": {},
        "links": [],
        "images": [],
    }


def test_page_extractor_flags_x_login_wall_and_does_not_persist():
    url = "https://x.com/i/article/1789012345678901234"
    saved_stdlib = page_extractor._extract_stdlib
    saved_crawl = page_extractor._CRAWL4AI_AVAILABLE
    try:
        page_extractor._CRAWL4AI_AVAILABLE = False
        page_extractor._extract_stdlib = (
            lambda u, **k: _x_login_wall_result(u))
        r = page_extractor.extract_page(
            None, url, enforce_allowlist=False, include_screenshot=False)
    finally:
        page_extractor._extract_stdlib = saved_stdlib
        page_extractor._CRAWL4AI_AVAILABLE = saved_crawl
    _assert(r.get("ok") is False,
            f"the X login wall must fail honestly, not save junk: {r}")
    _assert(r.get("code") == "x_login_wall", f"honest code: {r}")
    err = (r.get("error") or "").lower()
    _assert("login" in err or "logged" in err, f"honest error copy: {r}")
    _assert("—" not in (r.get("error") or "") and "–" not in (r.get("error") or ""),
            "no em/en dashes in the login-wall copy (Voice DNA)")
    # And nothing gets persisted from an ok:false result.
    _assert(page_extractor.persist_page_yoink(None, r) is None,
            "an ok:false wall result must never persist a uoink")
    # A genuine article page (no wall signature) is untouched.
    saved_stdlib = page_extractor._extract_stdlib
    saved_crawl = page_extractor._CRAWL4AI_AVAILABLE
    try:
        page_extractor._CRAWL4AI_AVAILABLE = False
        page_extractor._extract_stdlib = lambda u, **k: {
            "ok": True, "extraction_engine": "stdlib", "url": u,
            "title": "Real Article", "markdown": "# Real Article\n\nBody.",
            "metadata": {}, "links": [], "images": []}
        ok = page_extractor.extract_page(
            None, "https://x.com/i/article/1", enforce_allowlist=False,
            include_screenshot=False)
    finally:
        page_extractor._extract_stdlib = saved_stdlib
        page_extractor._CRAWL4AI_AVAILABLE = saved_crawl
    _assert(ok.get("ok") is True,
            f"a real x.com page that renders must still succeed: {ok}")
    print("ok  X login wall fails honestly; real pages still pass")


# ---- Bug 2: honest Activity copy for an X post with no video --------------

_X_404_DUMP = (
    "Command: pythonw.exe -m yt_dlp --extractor-args twitter:api=syndication "
    "--dump-single-json --no-download https://x.com/i/status/1790000000000000000\n"
    "Exit code: 1\n"
    "WARNING: [twitter] 1790000000000000000: Not all metadata or media is "
    "available via syndication endpoint\n"
    "ERROR: [twitter] 1790000000000000000: Unable to download JSON metadata: "
    "HTTP Error 404: Not Found (caused by <HTTPError 404: Not Found>)")


def test_x_no_video_error_copy_is_honest_not_a_download():
    msg = server._plain_error_from_text(_X_404_DUMP)
    low = msg.lower()
    _assert("x " in low or low.startswith("x"),
            f"copy should name X: {msg!r}")
    _assert("post" in low or "thread" in low,
            f"copy should point at post/thread text capture: {msg!r}")
    # Reconciled with V-2c: X Articles ARE supported now (extension button), so
    # the copy must name Articles and point at the button, not a dead end.
    _assert("article" in low,
            f"copy should name X Articles specifically: {msg!r}")
    _assert("aren't supported" not in low and "not supported" not in low,
            f"copy must not claim Articles are unsupported: {msg!r}")
    _assert("uoink this article" in low,
            f"copy should point at the extension's article button: {msg!r}")
    # The old generic copy is misleading here -- it must not be what we return.
    _assert("would not hand this one over cleanly" not in low,
            f"must not fall back to the vague yt-dlp copy: {msg!r}")
    _assert("—" not in msg and "–" not in msg,
            "no em/en dashes in the X no-video copy (Voice DNA)")
    print("ok  X 404 (no video) yields honest, non-download guidance")


def test_dashboard_mirrors_honest_x_no_video_copy():
    # translateMachineMessage must carry the same honest X-no-video branch,
    # keyed on the syndication 404 signature.
    _assert("not all metadata or media" in DASHBOARD.lower(),
            "dashboard needs the X syndication 404 signal")
    # Reconciled with V-2c: Articles are supported via the extension button, so
    # the dashboard's no-video copy points there instead of the old dead end.
    _assert("Uoink this article button" in DASHBOARD,
            "dashboard no-video copy must point at the article button")
    _assert("X Articles aren't supported yet" not in DASHBOARD,
            "the now-false 'not supported yet' dead end must be gone")
    print("ok  dashboard mirrors the honest X no-video copy")


# ---- Bug 3: uoink detail action toolbar never cut off ---------------------

def test_detail_action_toolbar_wraps_full_width():
    # The fix scopes a rule to the uoink detail header so its action row is a
    # full-width wrapping toolbar (never a squeezed right column that clips
    # under DPI scaling).
    _assert("#tab-yoink .page-head" in DASHBOARD,
            "detail header needs a scoped layout rule")
    _assert("yoink-actions" in DASHBOARD,
            "the detail action row needs its dedicated class")
    # The action row class is applied to the button row in the markup.
    head = DASHBOARD.split('id="tab-yoink"', 1)[1].split("</section>", 1)[0]
    _assert('class="inline-row yoink-actions"' in head
            or 'class="yoink-actions' in head,
            "the detail controls must carry the yoink-actions class")
    for marker in ("Open folder", "Open transcript file", "Re-capture source",
                   "Re-transcribe", "Evidence", "Write from this"):
        _assert(marker in head, f"detail action missing: {marker}")
    print("ok  detail action toolbar is a full-width wrapping row")


def main():
    for fn in (
        test_x_extractor_detects_article_urls,
        test_classifier_routes_x_article_honestly,
        test_page_extractor_flags_x_login_wall_and_does_not_persist,
        test_x_no_video_error_copy_is_honest_not_a_download,
        test_dashboard_mirrors_honest_x_no_video_copy,
        test_detail_action_toolbar_wraps_full_width,
    ):
        fn()
    print("\nALL V3.3.3 LIVE-FIX TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
