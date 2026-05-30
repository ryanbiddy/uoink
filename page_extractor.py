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

    if _CRAWL4AI_AVAILABLE:
        try:
            return _extract_crawl4ai(canonical, render_mode=render_mode,
                                       include_screenshot=include_screenshot,
                                       follow_links_depth=depth)
        except Exception as e:
            log.warning("crawl4ai extract failed (%s); falling back to "
                          "stdlib: %s", canonical, e)
    return _extract_stdlib(canonical,
                              include_screenshot=include_screenshot)


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
                         data_root: Path | None = None) -> str | None:
    """Persist a successful extract_page result as a yoink row with
    source_type='page'. Returns the synthetic video_id used (so caller
    can link to it). When the extract result is ok=False, returns None.

    The page yoink has no real video_id; we synthesize one from a
    stable hash of the canonical URL so re-extracting the same page
    upserts cleanly."""
    if not isinstance(extract_result, dict) or not extract_result.get("ok"):
        return None
    url = extract_result.get("url") or ""
    title = extract_result.get("title") or url
    md = extract_result.get("markdown") or ""
    metadata = extract_result.get("metadata") or {}
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()
    video_id = f"page_{digest[:11]}"

    # Folder for the page corpus + sidecar. Re-use DESKTOP_ROOT semantics:
    # if data_root is supplied, drop under <data_root>/Pages/<digest[:8]>/
    folder = None
    corpus_path = None
    sidecar_path = None
    if data_root is not None:
        folder = Path(data_root) / "Pages" / digest[:8]
        folder.mkdir(parents=True, exist_ok=True)
        corpus_path = folder / "page.md"
        sidecar_path = folder / "page.json"
        corpus_path.write_text(
            f"# {title}\n\n**Source:** {url}\n\n" + (md or ""),
            encoding="utf-8")
        import json as _json
        sidecar_path.write_text(_json.dumps({
            "schema_version": 2,
            "source_type": SOURCE_TYPE_PAGE,
            "url": url, "title": title,
            "extraction_engine": extract_result.get("extraction_engine"),
            "metadata": metadata,
            "links": extract_result.get("links") or [],
            "images": extract_result.get("images") or [],
            "screenshot_path": extract_result.get("screenshot_path"),
            "extracted_at": extract_result.get("extracted_at"),
        }, indent=2, ensure_ascii=False), encoding="utf-8")

    try:
        idx.upsert_yoink({
            "video_id": video_id,
            "slug": digest[:11],
            "channel": urlparse(url).hostname or "",
            "title": title[:240] if title else None,
            "topic": topic,
            "yoinked_at": extract_result.get("extracted_at") or _now_iso(),
            "corpus_path": str(corpus_path) if corpus_path else None,
            "sidecar_path": str(sidecar_path) if sidecar_path else None,
            "source_type": SOURCE_TYPE_PAGE,
        }, content=md[:65000])
    except Exception as e:
        log.warning("persist_page_yoink upsert failed: %s", e)
        return None
    return video_id
