"""E2: the in-page Uoink buttons appear after in-site navigation.

YouTube and X move between pages with the History API, and Chrome only
injects declared content scripts on a real page load. The manifest used to
match only watch/shorts and /article/ URLs, so opening a video from the
YouTube home page (or an article from the X timeline) never loaded content.js
/ content-x-article.js and the in-page button was missing until a reload.

  manifest   -- Chrome match-pattern semantics: content.js loads on every
                YouTube page and content-x-article.js on every X page, with
                no new permission or host (the scripts then gate themselves)
  youtube    -- tests/js/ext_spa_navigation_test.mjs drives the REAL
  x_article     content.js / content-x-article.js / background.js in a fake
  background    browser: inert off a video/article (no button, no /health
                polling, DOM churn is a string compare), a working button
                and polling after yt-navigate-finish / the DOM observer /
                popstate, torn down when leaving; the context-menu X Article
                capture injects lib/x-article.js + content-x-article.js and
                asks once more when the tab has no receiver.

No network: fetch and chrome.* are stubs inside the harness.
"""
import json
import re
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST = REPO_ROOT / "extension" / "manifest.json"
HARNESS = REPO_ROOT / "tests" / "js" / "ext_spa_navigation_test.mjs"

YOUTUBE_JS = ["lib/extract.js", "lib/ui.js", "content.js"]
X_ARTICLE_JS = ["lib/x-article.js", "content-x-article.js"]

# What the manifest granted before E2; widening the matches must not add to it.
PERMISSIONS = [
    "alarms", "clipboardWrite", "notifications", "storage", "contextMenus",
    "activeTab", "scripting", "offscreen",
]
HOST_PERMISSIONS = [
    "https://www.youtube.com/*",
    "https://m.youtube.com/*",
    "https://youtu.be/*",
    "https://x.com/*",
    "https://twitter.com/*",
    "https://mobile.twitter.com/*",
    "https://*.reddit.com/*",
    "http://127.0.0.1:5179/*",
    "http://localhost:5179/*",
]
YOUTUBE_HOSTS = {"www.youtube.com", "m.youtube.com"}
X_HOSTS = {"x.com", "www.x.com", "twitter.com", "www.twitter.com"}


def _pattern_parts(pattern):
    m = re.fullmatch(r"(\*|https?)://([^/]+)(/.*)", pattern)
    assert m, f"unparseable match pattern {pattern!r}"
    return m.group(1), m.group(2), m.group(3)


def _matches(pattern, url):
    """Chrome match-pattern test: scheme, host (with a leading *. wildcard),
    and a path glob checked against the URL's path plus query."""
    scheme, host, path = _pattern_parts(pattern)
    parts = urlsplit(url)
    if scheme == "*":
        if parts.scheme not in ("http", "https"):
            return False
    elif parts.scheme != scheme:
        return False
    hostname = parts.hostname or ""
    if host == "*":
        pass
    elif host.startswith("*."):
        base = host[2:]
        if hostname != base and not hostname.endswith("." + base):
            return False
    elif hostname != host:
        return False
    target = parts.path + (f"?{parts.query}" if parts.query else "")
    glob = "".join(".*" if c == "*" else re.escape(c) for c in path)
    return re.fullmatch(glob, target) is not None


def _manifest():
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def _entry(manifest, js):
    entries = [cs for cs in manifest["content_scripts"] if cs.get("js") == js]
    assert len(entries) == 1, f"expected one content_scripts entry for {js}"
    return entries[0]


def _loads(entry, url):
    return any(_matches(p, url) for p in entry["matches"])


def test_youtube_script_loads_on_every_youtube_page():
    entry = _entry(_manifest(), YOUTUBE_JS)
    for url in [
        "https://www.youtube.com/",
        "https://www.youtube.com/results?search_query=claude",
        "https://www.youtube.com/@somechannel/videos",
        "https://www.youtube.com/feed/subscriptions",
        "https://m.youtube.com/",
        "https://www.youtube.com/watch?v=abc123def45",
        "https://www.youtube.com/shorts/abc123def45",
        "https://m.youtube.com/watch?v=abc123def45",
    ]:
        assert _loads(entry, url), (
            f"E2: content.js must already be in a tab showing {url}, so an "
            "in-site navigation to a video finds it there")


def test_x_article_script_loads_on_every_x_page():
    entry = _entry(_manifest(), X_ARTICLE_JS)
    for url in [
        "https://x.com/home",
        "https://x.com/jack",
        "https://x.com/jack/status/1900000000001",
        "https://x.com/explore",
        "https://www.x.com/home",
        "https://twitter.com/home",
        "https://www.twitter.com/home",
        "https://x.com/jack/article/1900000000001",
        "https://x.com/i/article/1900000000001",
    ]:
        assert _loads(entry, url), (
            f"E2: content-x-article.js must already be in a tab showing {url}, "
            "so an in-site navigation to an article finds it there")


def test_widening_adds_no_permission_or_host():
    manifest = _manifest()
    assert manifest["permissions"] == PERMISSIONS
    assert manifest["host_permissions"] == HOST_PERMISSIONS
    for js, hosts in ((YOUTUBE_JS, YOUTUBE_HOSTS), (X_ARTICLE_JS, X_HOSTS)):
        for pattern in _entry(manifest, js)["matches"]:
            scheme, host, _path = _pattern_parts(pattern)
            assert scheme == "https" and host in hosts, (
                f"{js[-1]} match {pattern!r} reaches beyond the hosts it "
                "already ran on")
    # Unrelated scripts keep their scope.
    reddit = _entry(manifest, ["lib/extract.js", "lib/ui.js", "content-reddit.js"])
    assert reddit["matches"] == ["*://*.reddit.com/r/*/comments/*"]
    assert not _loads(_entry(manifest, YOUTUBE_JS), "https://www.reddit.com/")
    assert not _loads(_entry(manifest, X_ARTICLE_JS), "https://www.youtube.com/")


GROUPS = ["youtube", "x_article", "background"]


@pytest.mark.parametrize("group", GROUPS)
def test_buttons_follow_in_site_navigation(group):
    assert HARNESS.exists(), f"missing harness: {HARNESS}"
    proc = subprocess.run(
        ["node", str(HARNESS), group],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    output = f"{proc.stdout}\n{proc.stderr}"
    assert proc.returncode == 0, f"{group} harness failed:\n{output}"
    assert "FAIL" not in output, output
    # Guard against a group that silently ran nothing.
    marker = f"group {group}: "
    assert marker in proc.stdout, output
    count = int(proc.stdout.split(marker, 1)[1].split(" ", 1)[0])
    assert count >= 3, output
