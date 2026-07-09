"""v3.2 Universal Site Uoinking — page extraction + allowlist.

Per PROMPT-V3.2-CC-BACKEND.md Deliverable 2 + Ryan's locked answer #1:
opt-in allowlist (defaults pre-seeded: YouTube + X/Twitter; user adds
others) + Crawl4AI as the canonical engine (lazy import) + stdlib
fallback that ALWAYS works so the helper boots fine even when the
Crawl4AI bundle is broken.

Compute policy (locked, LOCAL-FIRST):
- Crawl4AI runs ON-DEVICE. No third-party API.
- Lazy import same hygiene as whisperx (FLAG-1 fix): probe at module
  top, cache result in _CRAWL4AI_AVAILABLE. BaseException catch so a
  broken bundle (playwright DLL miss, browser binary missing) leaves
  the helper booting cleanly.
- Stdlib fallback uses urllib + a simple regex/heuristic markdown
  synthesis. No JS rendering, no screenshot, but produces useful
  output for static pages. The extraction_engine field on the
  response tells the dashboard which path was used.

Allowlist behaviour:
- Patterns are bare hostnames or hostname-with-wildcard
  ('*.docs.example.com'). NOT URL prefixes -- the extension scopes
  by host_permissions, so matching by host is the right granularity.
- _host_matches normalizes case + strips port + supports leading
  wildcards. No regex escaping risk since patterns aren't regex.

Module surface:
- _CRAWL4AI_AVAILABLE        runtime probe result
- DEFAULT_ALLOW_SEEDS        the 4 default hostnames from migration 0015
- list_allowed (idx)
- add_allowed (idx, pattern)
- remove_allowed (idx, pattern)
- host_is_allowed (idx, url)
- extract_page (idx, url, render_mode, include_screenshot,
                 follow_links_depth) -> structured dict
- persist_page_yoink (idx, extract_result, *, data_root) -> yoink row id

Transport (HTTP + MCP) is owned by server.py + uoink_mcp_tools.py."""

from __future__ import annotations

import hashlib
import logging
import re
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

log = logging.getLogger("uoink.page_extractor")


# ---- Crawl4AI lazy probe (CC's v3.1.3 FLAG-1 hygiene applied) ----------
def _probe_crawl4ai() -> bool:
    try:
        import crawl4ai  # noqa: F401
        return True
    except BaseException as e:  # noqa: BLE001 -- same posture as whisperx
        log.info("crawl4ai unavailable: %s: %s", type(e).__name__, e)
        return False


_CRAWL4AI_AVAILABLE = _probe_crawl4ai()


def is_crawl4ai_available() -> bool:
    """O(1) cached probe result. Used by /diagnose + the dashboard's
    'engine' surface."""
    return _CRAWL4AI_AVAILABLE


# ---- enums + constants -------------------------------------------------
ENGINE_CRAWL4AI = "crawl4ai"
ENGINE_STDLIB = "stdlib"

RENDER_MODE_JS = "js"
RENDER_MODE_STATIC = "static"
_RENDER_MODES = (RENDER_MODE_JS, RENDER_MODE_STATIC)

DEFAULT_ALLOW_SEEDS = ("youtube.com", "youtu.be", "x.com", "twitter.com")

# Source-type tag persisted on the yoink row.
SOURCE_TYPE_PAGE = "page"

# ---- Phase 2 source-agnostic taxonomy -------------------------------------
# The `platform` column stores one clean tag per source network. These are
# the values the Library's Platform facet filters on, so they stay short and
# stable (x, not "twitter"; web, not "generic").
PLATFORM_YOUTUBE = "youtube"
PLATFORM_X = "x"
PLATFORM_REDDIT = "reddit"
PLATFORM_PODCAST = "podcast"
PLATFORM_WEB = "web"
# Short-form video networks (context-layer item 2). TikToks and Instagram
# Reels are their own platform facet; a YouTube Short stays platform=youtube
# (it IS YouTube) but is tagged source_type='short_video' so it filters
# alongside the others. See server._normalize_short_video_url.
PLATFORM_TIKTOK = "tiktok"
PLATFORM_INSTAGRAM = "instagram"
# A note the user wrote to themselves. Not a source network, but it slots into
# the same platform facet so a note filters like any other uoink. Kept 1:1 with
# source_type='note', the way every other source maps (x_thread->x, page->web).
PLATFORM_NOTE = "note"
KNOWN_PLATFORMS = (PLATFORM_YOUTUBE, PLATFORM_X, PLATFORM_REDDIT,
                   PLATFORM_PODCAST, PLATFORM_WEB, PLATFORM_TIKTOK,
                   PLATFORM_INSTAGRAM, PLATFORM_NOTE)

# source_type (already stored per capture route) -> platform.
#
# NOTE: 'short_video' is deliberately NOT in this table. A short is
# multi-platform (a TikTok, a Reel, OR a YouTube Short), so its platform must
# come from the URL host, not the source_type. platform_for() falls through to
# host detection for it.
_SOURCE_TYPE_PLATFORM = {
    "video": PLATFORM_YOUTUBE,
    "x_thread": PLATFORM_X,
    "x_article": PLATFORM_X,
    "reddit_thread": PLATFORM_REDDIT,
    "page": PLATFORM_WEB,
    "episode": PLATFORM_PODCAST,
    "note": PLATFORM_NOTE,
}

_YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}
_X_HOSTS = {"x.com", "www.x.com", "twitter.com", "www.twitter.com",
            "mobile.twitter.com"}
_REDDIT_HOSTS = {"reddit.com", "www.reddit.com", "old.reddit.com",
                 "new.reddit.com"}
_TIKTOK_HOSTS = {"tiktok.com", "www.tiktok.com", "m.tiktok.com",
                 "vm.tiktok.com", "vt.tiktok.com"}
_INSTAGRAM_HOSTS = {"instagram.com", "www.instagram.com", "m.instagram.com"}


def platform_for(source_type: str | None, url: str = "") -> str:
    """Map a capture to its platform tag. source_type is authoritative
    (it's set per route); the URL host is the fallback for rows that have no
    source_type. A legacy row with neither is treated as a YouTube video,
    which is what every pre-v3.2 row is."""
    st = (source_type or "").strip().lower()
    if st in _SOURCE_TYPE_PLATFORM:
        return _SOURCE_TYPE_PLATFORM[st]
    host = ""
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        host = ""
    if host in _YOUTUBE_HOSTS:
        return PLATFORM_YOUTUBE
    if host in _X_HOSTS:
        return PLATFORM_X
    if host in _REDDIT_HOSTS:
        return PLATFORM_REDDIT
    if host in _TIKTOK_HOSTS:
        return PLATFORM_TIKTOK
    if host in _INSTAGRAM_HOSTS:
        return PLATFORM_INSTAGRAM
    if not st and not host:
        return PLATFORM_YOUTUBE
    return PLATFORM_WEB


def author_for(source_type: str | None, metadata: dict | None,
               url: str = "") -> str | None:
    """Derive the real "who" from a capture's extractor metadata.

    - X (post/article): "Name (@handle)", or "@handle", or the name alone.
    - Reddit: "r/<subreddit>" (the community is the durable "who"; the OP
      username is often deleted).
    - web page: the site host (best signal a generic page has).

    Returns None when nothing usable is present, so the caller can fall back
    to the hostname."""
    md = metadata or {}
    platform = platform_for(source_type, url)
    if platform in (PLATFORM_YOUTUBE, PLATFORM_PODCAST, PLATFORM_TIKTOK,
                    PLATFORM_INSTAGRAM):
        # The caller already has the real "who" (the channel / uploader /
        # creator, from the extractor metadata); the host would be the wrong
        # answer here. The video/short pipeline falls back to sidecar.channel,
        # which it fills from yt-dlp's uploader/channel/creator.
        return None
    if platform == PLATFORM_NOTE:
        # A note's author is the user, supplied by notes.persist_note ("You" by
        # default). Return whatever the sidecar carried; never the host.
        return (md.get("author") or "").strip() or None
    if platform == PLATFORM_X:
        name = (md.get("author_name") or md.get("author") or "").strip()
        handle = (md.get("author_handle") or "").strip().lstrip("@")
        if name and handle:
            return f"{name} (@{handle})"
        if handle:
            return f"@{handle}"
        if name:
            return name
        return None
    if platform == PLATFORM_REDDIT:
        sub = (md.get("subreddit") or "").strip()
        if sub:
            return f"r/{sub}"
        author = (md.get("author") or "").strip()
        if author and author not in ("[unknown]", "[deleted]", ""):
            return f"u/{author}"
        return None
    # Generic web page: the host is the site, which is the honest "who".
    host = ""
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        host = ""
    return host or None


_SLUG_STRIP_RE = re.compile(r"[^a-z0-9]+")


def _slugify(value: str, *, max_len: int = 40) -> str:
    """Lowercase, ASCII-ish, hyphen-joined slug for a readable folder name.
    Empty / all-punctuation input returns ''."""
    text = _SLUG_STRIP_RE.sub("-", str(value or "").lower()).strip("-")
    return text[:max_len].strip("-")


def readable_slug(source_type: str | None, metadata: dict | None,
                  url: str, digest: str) -> str:
    """A human-legible folder slug for a non-YouTube capture, mirroring the
    on-disk legibility YouTube captures already have. Deterministic from the
    handle/subreddit/host + a short stable hash, so re-capturing the same URL
    lands in the same folder. e.g. 'boardyai-805baf72', 'r-python-1a2b3c4d'."""
    md = metadata or {}
    short = (digest or "")[:8] or "00000000"
    platform = platform_for(source_type, url)
    base = ""
    if platform == PLATFORM_X:
        base = _slugify(md.get("author_handle") or md.get("author_name") or "x")
    elif platform == PLATFORM_REDDIT:
        sub = _slugify(md.get("subreddit") or "")
        base = f"r-{sub}" if sub else "reddit"
    else:
        host = ""
        try:
            host = (urlparse(url).hostname or "").lower()
        except Exception:
            host = ""
        if host.startswith("www."):
            host = host[4:]
        base = _slugify(host) or "page"
    return f"{base}-{short}" if base else short

# yt-dlp + extension already enforce safety on those URLs; for universal
# site we add our own scheme + hostname gate so attacker-shaped inputs
# can't reach urlopen.
_GENERIC_HOST_RE = re.compile(
    r"^[A-Za-z0-9]([A-Za-z0-9.-]{0,253}[A-Za-z0-9])?$")
_USER_AGENT = ("Uoink/3.2 (Universal Site uoinking; "
                "+https://uoink.video) Mozilla/5.0")
_PAGE_FETCH_TIMEOUT_SEC = 15.0
_PAGE_MAX_BYTES = 8 * 1024 * 1024  # 8 MB hard cap on body read

# Limit follow_links_depth -- the prompt allows it but a depth-2 crawl
# on a high-degree site fans out fast. We cap at 1 to keep the surface
# bounded.
_MAX_FOLLOW_LINKS_DEPTH = 1


# Hosts that serve a "JavaScript is not available" login/nojs wall to a
# plain (non-browser) fetch. Reading real content on these needs a
# logged-in browser, so a stdlib/static fetch gets the wall, not the page.
_X_WALL_HOSTS = {
    "x.com", "www.x.com", "mobile.x.com",
    "twitter.com", "www.twitter.com", "mobile.twitter.com",
}
_X_WALL_SIGNAL = "javascript is not available"


def _is_x_login_wall(url: str, result: dict) -> bool:
    """True when `result` is X's login/nojs wall page rather than real
    content. Guards against saving that wall as a junk uoink (title=None,
    body = 'enable JavaScript...'). Keyed on host + the wall's headline so a
    genuine article that happens to mention JavaScript isn't caught."""
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return False
    if host not in _X_WALL_HOSTS:
        return False
    md = (result.get("markdown") or "").lower()
    title = (result.get("title") or "").strip()
    # The wall has no real <title> and leads with the headline.
    return _X_WALL_SIGNAL in md and not title


def _now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


# ---- URL validation ----------------------------------------------------
def normalize_page_url(raw: str) -> str | None:
    """Conservative URL validator + canonicalizer. Returns the canonical
    https://host[:port]/path?query form, or None if the input is bad.

    Rejects javascript: data: file: ftp: vbscript: mailto: blob: per
    same posture as v3.1 universal extractor; rejects IP literals and
    bracketed IPv6 to keep attacker-shaped URLs out of urlopen."""
    if not raw or not isinstance(raw, str):
        return None
    raw = raw.strip()
    if not raw:
        return None
    lower = raw.lower()
    for bad in ("javascript:", "data:", "vbscript:", "file:", "ftp:",
                 "mailto:", "blob:"):
        if lower.startswith(bad):
            return None
    if "://" not in raw:
        raw = "https://" + raw
    try:
        u = urlparse(raw)
    except ValueError:
        return None
    if u.scheme not in ("http", "https"):
        return None
    host = (u.hostname or "")
    if not host or len(host) > 253:
        return None
    if not _GENERIC_HOST_RE.match(host):
        return None
    netloc = host.lower()
    if u.port:
        netloc = f"{netloc}:{u.port}"
    query = f"?{u.query}" if u.query else ""
    return f"{u.scheme}://{netloc}{u.path}{query}"


# ---- allowlist ---------------------------------------------------------
def list_allowed(idx, *, active_only: bool = False) -> list[dict]:
    sql = "SELECT * FROM allowed_sites"
    if active_only:
        sql += " WHERE active = 1"
    sql += " ORDER BY added_at ASC"
    rows = idx._conn.execute(sql).fetchall()
    return [dict(r) for r in rows]


def add_allowed(idx, url_pattern: str) -> dict:
    """Insert (idempotent on UNIQUE url_pattern). Returns the row."""
    pattern = (url_pattern or "").strip().lower()
    if not pattern:
        raise ValueError("url_pattern required")
    # Don't pre-validate as a strict hostname -- wildcards are explicit:
    # '*.docs.example.com' is a legal pattern (and not a legal hostname).
    # We just confirm it's not gibberish.
    if len(pattern) > 253:
        raise ValueError("url_pattern too long (max 253)")
    if any(c in pattern for c in (" ", "\t", "\n", "\r")):
        raise ValueError("url_pattern cannot contain whitespace")
    with idx._lock:
        cur = idx._conn.execute(
            "INSERT OR IGNORE INTO allowed_sites "
            "(url_pattern, added_at) VALUES (?, ?)",
            (pattern, _now_iso()))
        if cur.rowcount == 0:
            row = idx._conn.execute(
                "SELECT * FROM allowed_sites WHERE url_pattern=?",
                (pattern,)).fetchone()
            return dict(row) if row else {}
    return _get_allowed(idx, cur.lastrowid or 0) or {}


def remove_allowed(idx, url_pattern: str) -> bool:
    pattern = (url_pattern or "").strip().lower()
    if not pattern:
        return False
    with idx._lock:
        cur = idx._conn.execute(
            "DELETE FROM allowed_sites WHERE url_pattern=?", (pattern,))
        return cur.rowcount > 0


def _get_allowed(idx, allowed_id: int) -> dict | None:
    row = idx._conn.execute(
        "SELECT * FROM allowed_sites WHERE id=?",
        (allowed_id,)).fetchone()
    return dict(row) if row else None


def _host_matches(host: str, pattern: str) -> bool:
    """True iff host matches pattern. Both are lowercase. Pattern may
    have a leading wildcard ('*.docs.example.com'). Plain pattern
    matches exact host AND any subdomain of pattern (so 'example.com'
    matches 'www.example.com')."""
    host = (host or "").lower()
    pattern = (pattern or "").lower()
    if not host or not pattern:
        return False
    if pattern.startswith("*."):
        suffix = pattern[2:]
        return host == suffix or host.endswith("." + suffix)
    return host == pattern or host.endswith("." + pattern)


def host_is_allowed(idx, url: str) -> bool:
    """True iff the URL's host matches any active allowlist entry."""
    canonical = normalize_page_url(url)
    if not canonical:
        return False
    parsed = urlparse(canonical)
    host = (parsed.hostname or "").lower()
    if not host:
        return False
    for row in list_allowed(idx, active_only=True):
        if _host_matches(host, row["url_pattern"]):
            return True
    return False


# ---- extraction --------------------------------------------------------
def extract_page(idx, url: str, *,
                  render_mode: str = RENDER_MODE_JS,
                  include_screenshot: bool = True,
                  follow_links_depth: int = 0,
                  enforce_allowlist: bool = True) -> dict:
    """Extract a single page. Returns the structured response shape per
    PROMPT-V3.2-CC-BACKEND.md Deliverable 2.

    Engine selection: Crawl4AI when available (handles JS render +
    screenshot), stdlib fallback otherwise (static HTML + heuristic
    markdown + no screenshot).

    The allowlist gate runs by default. Callers that need to bypass
    (e.g., the Writing Studio URL anchor ingestion that wraps this
    function) pass enforce_allowlist=False."""
    canonical = normalize_page_url(url)
    if not canonical:
        return {"ok": False,
                "error": ("url must be http(s) with a valid hostname")}
    if render_mode not in _RENDER_MODES:
        return {"ok": False,
                "error": f"render_mode must be one of {list(_RENDER_MODES)}"}
    if enforce_allowlist and not host_is_allowed(idx, canonical):
        host = urlparse(canonical).hostname
        return {"ok": False, "code": "host_not_allowed",
                "error": (f"host '{host}' is not in the allowlist. "
                          f"Add it via /extract/page/allowlist or the "
                          f"Sites Settings panel.")}
    depth = max(0, min(int(follow_links_depth or 0),
                          _MAX_FOLLOW_LINKS_DEPTH))

    result = None
    if _CRAWL4AI_AVAILABLE:
        try:
            result = _extract_crawl4ai(
                canonical, render_mode=render_mode,
                include_screenshot=include_screenshot,
                follow_links_depth=depth)
        except Exception as e:
            log.warning("crawl4ai extract failed (%s); falling back to "
                          "stdlib: %s", canonical, e)
    if result is None:
        result = _extract_stdlib(canonical,
                                   include_screenshot=include_screenshot)
    # Honest handling of X's login/nojs wall: a plain fetch of an x.com
    # Article or page comes back as "JavaScript is not available", not the
    # content. Fail cleanly with actionable copy instead of persisting the
    # wall as a junk uoink (the v3.3.2 behaviour Ryan hit).
    if result.get("ok") and _is_x_login_wall(canonical, result):
        return {
            "ok": False,
            "code": "x_login_wall",
            "url": canonical,
            "extraction_engine": result.get("extraction_engine"),
            "error": ("X needs a logged-in browser to show this, so Uoink "
                      "can't get past X's login wall from a pasted link. For "
                      "a long-form X Article, open it and use the extension's "
                      "Uoink this article button, which reads it from your "
                      "logged-in page. X posts and threads capture fully from "
                      "a /status/ link."),
        }
    return result


def _extract_crawl4ai(url: str, *, render_mode: str,
                        include_screenshot: bool,
                        follow_links_depth: int) -> dict:
    """Crawl4AI path. Heavy-runtime extraction with optional screenshot
    when render_mode='js'. Bounded surface area -- if Crawl4AI's API
    changes we localise the breakage to this function."""
    # Imported lazily; _CRAWL4AI_AVAILABLE gate above means this won't
    # raise ImportError on the import line, but Crawl4AI's internals
    # might (network, playwright init).
    import asyncio
    from crawl4ai import AsyncWebCrawler  # type: ignore

    async def _run() -> dict:
        async with AsyncWebCrawler(verbose=False) as crawler:
            result = await crawler.arun(
                url=url,
                screenshot=include_screenshot and render_mode == RENDER_MODE_JS,
                bypass_cache=True,
            )
            return result
    result = asyncio.run(_run())
    md = getattr(result, "markdown", None) or getattr(result, "fit_markdown", "")
    title = getattr(result, "metadata", {}).get("title") if hasattr(
        result, "metadata") else None
    metadata = (getattr(result, "metadata", {}) or {}) if hasattr(
        result, "metadata") else {}
    links = list(getattr(result, "links", {}).get("internal", []) or []) if hasattr(
        result, "links") else []
    images = list(getattr(result, "media", {}).get("images", []) or []) if hasattr(
        result, "media") else []
    screenshot_path = None
    screenshot_b64 = getattr(result, "screenshot", None)
    if screenshot_b64:
        screenshot_path = f"<inline-base64:{len(screenshot_b64)}b>"
    return {
        "ok": True,
        "extraction_engine": ENGINE_CRAWL4AI,
        "url": url,
        "title": title,
        "markdown": md or "",
        "screenshot_path": screenshot_path,
        "screenshot_b64": screenshot_b64,
        "metadata": metadata,
        "links": [{"href": l} if isinstance(l, str) else l for l in links[:50]],
        "images": [{"src": i} if isinstance(i, str) else i for i in images[:50]],
        "extracted_at": _now_iso(),
    }


# ---- stdlib fallback ---------------------------------------------------
_TAG_RE = re.compile(r"<[^>]+>", re.S)
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>",
                          re.S | re.IGNORECASE)
_META_RE = re.compile(
    r'<meta\s+(?:name|property)\s*=\s*["\'](?P<key>[^"\']+)["\']\s+'
    r'content\s*=\s*["\'](?P<val>[^"\']*)["\']',
    re.S | re.IGNORECASE)
_LINK_RE = re.compile(
    r'<a\s+[^>]*href\s*=\s*["\'](?P<href>[^"\'#]+)["\']',
    re.S | re.IGNORECASE)
_IMG_RE = re.compile(
    r'<img\s+[^>]*src\s*=\s*["\'](?P<src>[^"\']+)["\']',
    re.S | re.IGNORECASE)
_SCRIPT_STYLE_RE = re.compile(
    r"<(?:script|style)[^>]*>.*?</(?:script|style)>",
    re.S | re.IGNORECASE)


def _html_to_markdown(html: str) -> str:
    """Cheap, defensive HTML -> markdown. Strips script/style first,
    converts headings + links + paragraphs, collapses whitespace.
    NOT a full Markdownify -- enough for an LLM to ingest cleanly when
    Crawl4AI isn't available."""
    if not html:
        return ""
    s = _SCRIPT_STYLE_RE.sub("", html)
    # Headings + paragraphs + line breaks
    s = re.sub(r"</?h1[^>]*>", "\n\n# ", s, flags=re.IGNORECASE)
    s = re.sub(r"</?h2[^>]*>", "\n\n## ", s, flags=re.IGNORECASE)
    s = re.sub(r"</?h3[^>]*>", "\n\n### ", s, flags=re.IGNORECASE)
    s = re.sub(r"</?(h4|h5|h6)[^>]*>", "\n\n#### ", s, flags=re.IGNORECASE)
    s = re.sub(r"</?p[^>]*>", "\n\n", s, flags=re.IGNORECASE)
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.IGNORECASE)
    s = re.sub(r"</?li[^>]*>", "\n- ", s, flags=re.IGNORECASE)
    s = _TAG_RE.sub("", s)
    # Decode a few common entities + collapse whitespace
    s = (s.replace("&amp;", "&")
         .replace("&lt;", "<")
         .replace("&gt;", ">")
         .replace("&quot;", '"')
         .replace("&#39;", "'")
         .replace("&nbsp;", " "))
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n\s+\n", "\n\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def _extract_stdlib(url: str, *, include_screenshot: bool) -> dict:
    """Stdlib-only fallback. urllib GET + regex-based HTML-to-markdown.
    Always returns a usable result for static pages; returns
    screenshot_path=None because we can't render."""
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=_PAGE_FETCH_TIMEOUT_SEC) as resp:
            if resp.status != 200:
                return {"ok": False,
                        "error": f"upstream returned HTTP {resp.status}",
                        "extraction_engine": ENGINE_STDLIB,
                        "url": url}
            raw = resp.read(_PAGE_MAX_BYTES)
    except urllib.error.URLError as e:
        return {"ok": False, "error": f"fetch failed: {e}",
                "extraction_engine": ENGINE_STDLIB, "url": url}
    except Exception as e:
        return {"ok": False, "error": f"fetch failed: {e}",
                "extraction_engine": ENGINE_STDLIB, "url": url}

    html = raw.decode("utf-8", errors="replace")
    title_match = _TITLE_RE.search(html)
    title = title_match.group(1).strip() if title_match else None
    metadata: dict[str, str] = {}
    for m in _META_RE.finditer(html):
        key = m.group("key").strip().lower()
        val = m.group("val").strip()
        if key:
            metadata[key] = val
    links = [{"href": m.group("href").strip()}
              for m in _LINK_RE.finditer(html)
              if m.group("href").strip()][:50]
    images = [{"src": m.group("src").strip()}
                for m in _IMG_RE.finditer(html)
                if m.group("src").strip()][:50]
    markdown = _html_to_markdown(html)
    return {
        "ok": True,
        "extraction_engine": ENGINE_STDLIB,
        "url": url,
        "title": title,
        "markdown": markdown,
        "screenshot_path": None,
        "metadata": metadata,
        "links": links,
        "images": images,
        "extracted_at": _now_iso(),
    }


# ---- persist as a yoink row -------------------------------------------
def persist_page_yoink(idx, extract_result: dict, *,
                         topic: str | None = None,
                         data_root: Path | None = None,
                         source_type: str = SOURCE_TYPE_PAGE,
                         subfolder: str = "Pages",
                         slug_prefix: str = "page",
                         topic_classifier=None) -> str | None:
    """Persist a successful extract_page-shaped result as a yoink row.
    Returns the synthetic video_id used (so caller can link to it). When the
    extract result is ok=False, returns None.

    Defaults persist a universal-site page (source_type='page', under
    <data_root>/Pages/). Other HTML->markdown sources that produce the same
    extract_result shape reuse this by overriding source_type / subfolder /
    slug_prefix -- e.g. Reddit threads pass source_type='reddit_thread',
    subfolder='Reddit', slug_prefix='reddit'. The yoink has no real video_id;
    we synthesize one from a stable hash of the canonical URL so re-capturing
    the same source upserts cleanly."""
    if not isinstance(extract_result, dict) or not extract_result.get("ok"):
        return None
    url = extract_result.get("url") or ""
    title = extract_result.get("title") or url
    md = extract_result.get("markdown") or ""
    metadata = extract_result.get("metadata") or {}
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()
    video_id = f"{slug_prefix}_{digest[:11]}"

    # Phase 2 taxonomy: stop hard-coding channel=hostname. Derive the real
    # platform + author from the extractor metadata, and fall back to the host
    # only when there is no better "who" (a generic web page).
    platform = platform_for(source_type, url)
    author = author_for(source_type, metadata, url) or (urlparse(url).hostname or "")
    # `channel` stays populated for every path that still reads it (search,
    # the channel picker, performance tier), but now with the real author
    # instead of "x.com" / "reddit.com".
    channel = author or (urlparse(url).hostname or "")

    # Classify a topic for non-video sources too, so X / Reddit / web stop
    # piling into Uncategorized. The caller injects the classifier (server's
    # _classify_topic) so page_extractor stays standalone. Only runs when the
    # caller didn't already pass a topic.
    if topic is None and topic_classifier is not None:
        try:
            topic = topic_classifier({
                "title": title or "",
                "description": (md or "")[:2000],
                "channel": author or "",
            }) or None
        except Exception as e:  # defensive: never block a save on classify
            log.warning("persist_page_yoink topic classify failed: %s", e)
            topic = None

    # Readable slug folder (Phase 2), mirroring YouTube's on-disk legibility.
    slug = readable_slug(source_type, metadata, url, digest)

    # Folder for the corpus + sidecar. If data_root is supplied, drop under
    # <data_root>/<subfolder>/<readable-slug>/.
    folder = None
    corpus_path = None
    sidecar_path = None
    if data_root is not None:
        folder = Path(data_root) / subfolder / slug
        folder.mkdir(parents=True, exist_ok=True)
        corpus_path = folder / f"{slug_prefix}.md"
        sidecar_path = folder / f"{slug_prefix}.json"
        corpus_path.write_text(
            f"# {title}\n\n**Source:** {url}\n\n" + (md or ""),
            encoding="utf-8")
        import json as _json
        sidecar_path.write_text(_json.dumps({
            "schema_version": 2,
            "source_type": source_type,
            "platform": platform,
            "author": author,
            "url": url, "title": title,
            "extraction_engine": extract_result.get("extraction_engine"),
            "metadata": metadata,
            "links": extract_result.get("links") or [],
            "images": extract_result.get("images") or [],
            "screenshot_path": extract_result.get("screenshot_path"),
            "extracted_at": extract_result.get("extracted_at"),
        }, indent=2, ensure_ascii=False), encoding="utf-8")

    import json as _json
    metadata_json = _json.dumps({
        **metadata,
        "url": url,
        "platform": platform,
        "author": author,
        "source_type": source_type,
    }, ensure_ascii=False)

    try:
        idx.upsert_yoink({
            "video_id": video_id,
            "slug": slug,
            "channel": channel,
            "platform": platform,
            "author": author,
            "title": title[:240] if title else None,
            "topic": topic,
            "yoinked_at": extract_result.get("extracted_at") or _now_iso(),
            "corpus_path": str(corpus_path) if corpus_path else None,
            "sidecar_path": str(sidecar_path) if sidecar_path else None,
            "metadata_json": metadata_json,
            "source_type": source_type,
        }, content=md[:65000])
    except Exception as e:
        log.warning("persist_page_yoink upsert failed: %s", e)
        return None
    return video_id


# ---- Phase 2 backfill: correct existing non-YouTube rows -------------------
def _looks_like_host(channel: str, url: str) -> bool:
    """True when `channel` is a bare hostname (the Bug 3 value) rather than a
    real author. Matches the row's own URL host, a known platform host, or the
    generic www./domain.tld shape."""
    c = (channel or "").strip().lower()
    if not c:
        return True
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        host = ""
    if c == host and host:
        return True
    if c in _X_HOSTS or c in _REDDIT_HOSTS or c in _YOUTUBE_HOSTS:
        return True
    # A bare domain with no spaces (example.com, sub.example.co.uk).
    return bool(re.match(r"^[a-z0-9.-]+\.[a-z]{2,}$", c)) and " " not in c


def backfill_platform_author(idx, *, dry_run: bool = False) -> dict:
    """Second half of the Phase 2 backfill (the SQL migration did platform +
    YouTube author). Re-reads each non-YouTube row's sidecar to recover the
    real author X / Reddit / web captured, sets the `author` column, and
    corrects `channel` where it's still the hostname (the Bug 3 value).

    Idempotent: a row that already has a real author + a non-hostname channel
    is skipped, so re-running does nothing. Returns before/after counts:
    {total, scanned, author_from_sidecar, channel_corrected, stayed_hostname,
     already_ok, missing_sidecar}."""
    import json as _json
    rows = idx.rows_for_taxonomy_backfill()
    stats = {
        "total": len(rows), "scanned": 0, "author_from_sidecar": 0,
        "channel_corrected": 0, "stayed_hostname": 0, "already_ok": 0,
        "missing_sidecar": 0,
    }
    for row in rows:
        platform = row.get("platform") or platform_for(
            row.get("source_type"), "")
        if platform == PLATFORM_YOUTUBE:
            continue  # handled by the SQL migration (author = channel)
        stats["scanned"] += 1
        channel = row.get("channel") or ""
        author = row.get("author") or ""
        # Read the sidecar for the real author. persist_page_yoink writes a
        # top-level `author` on new rows; older sidecars only nest it under
        # `metadata`, so derive from there as a fallback.
        sidecar_path = row.get("sidecar_path") or ""
        url = ""
        sc_author = ""
        sc_meta: dict = {}
        source_type = row.get("source_type")
        if sidecar_path and Path(sidecar_path).exists():
            try:
                sc = _json.loads(Path(sidecar_path).read_text(encoding="utf-8"))
                url = sc.get("url") or ""
                sc_meta = sc.get("metadata") or {}
                source_type = sc.get("source_type") or source_type
                sc_author = (sc.get("author")
                             or author_for(source_type, sc_meta, url) or "")
            except (OSError, _json.JSONDecodeError, TypeError):
                stats["missing_sidecar"] += 1
        else:
            stats["missing_sidecar"] += 1

        # The best author we can offer: an existing real author wins, then the
        # sidecar's, then the current channel (host) as a last resort.
        new_author = author or sc_author or channel or None
        # Correct channel only when it's still the bare hostname AND we have a
        # genuinely better name (a real author that isn't itself the host).
        new_channel = channel
        if (sc_author and not _looks_like_host(sc_author, url)
                and _looks_like_host(channel, url)):
            new_channel = sc_author

        author_changed = bool(new_author) and new_author != author
        channel_changed = new_channel != channel

        if author_changed and sc_author and new_author == sc_author:
            stats["author_from_sidecar"] += 1
        if channel_changed:
            stats["channel_corrected"] += 1
        if not author_changed and not channel_changed:
            if _looks_like_host(new_channel, url):
                stats["stayed_hostname"] += 1
            else:
                stats["already_ok"] += 1
            continue
        if not author_changed and channel_changed and _looks_like_host(new_channel, url):
            stats["stayed_hostname"] += 1

        if not dry_run:
            idx.update_taxonomy(
                row["video_id"], platform=platform,
                author=new_author, channel=new_channel)
    return stats
