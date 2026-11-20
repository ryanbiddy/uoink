"""Uoink this page: persist the page the user sees, read in their own tab.

The extension runs Defuddle plus extension/lib/page-capture.js in the tab the
user clicked (after JavaScript ran, with the user's own session), and posts
{url, title, author, published, site, markdown, ...} to /extract/page/dom.
This module owns the helper half: validate and bound that payload, refuse a
wall or an empty tab honestly, and shape an extract_result that
page_extractor.persist_page_yoink saves like any other web page. No network
happens here; the page text never leaves this computer.

Transport (route, token, allowlist gate, body cap) is owned by server.py.
"""
from __future__ import annotations

from datetime import datetime, timezone
import re

import article_extractor
import page_extractor

ENGINE = "defuddle"
ENGINE_VERSION = "0.19.6"
CAPTURE_SOURCE = "browser_dom"
MAX_BODY_BYTES = 2 * 1024 * 1024
MAX_MARKDOWN = 400_000

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_IMAGE = re.compile(r"!\[([^\]\n]*)\]\(([^)\s]*)\)")
_LINK = re.compile(r"(?<!!)\[([^\]\n]*)\]\(([^)\s]*)\)")
_FENCE = re.compile(r"^(`{3,}|~{3,})", re.M)

WALL_COPY = ("This tab shows a sign-in, paywall or robot check instead of the page, so nothing was saved. "
             "Sign in or finish the check in the tab, then try again.")
THIN_COPY = "This tab has too little text to save as a page, so nothing was saved."


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _text(value, limit: int) -> str:
    if value is None or isinstance(value, (dict, list)):
        return ""
    return re.sub(r"\s+", " ", _CONTROL.sub("", str(value))).strip()[:limit]


def _http(url: str) -> bool:
    return bool(re.match(r"https?://[^\s/]+", url or "", re.I))


def scrub_markdown(markdown: str) -> str:
    """Keep only http(s) link and image targets; never store script or data URLs."""
    parts = re.split(r"(^`{3,}[^\n]*\n.*?^`{3,}[ \t]*$)", markdown, flags=re.M | re.S)
    for i in range(0, len(parts), 2):  # odd parts are fenced code, left as written
        text = _IMAGE.sub(lambda m: m.group(0) if _http(m.group(2)) else "", parts[i])
        parts[i] = _LINK.sub(lambda m: m.group(0) if _http(m.group(2)) else m.group(1), text)
    return "".join(parts)


def _plain(markdown: str) -> str:
    text = _IMAGE.sub(" ", markdown)
    text = _LINK.sub(lambda m: m.group(1), text)
    return re.sub(r"\s+", " ", re.sub(r"[#>*`|_~-]+", " ", text)).strip()


page_state = page_extractor.page_state


def build_extract_result(payload) -> dict:
    """Validate the extension's capture and return an extract_page-shaped
    result, or {ok: False, code, error} when it cannot be saved."""
    if not isinstance(payload, dict):
        return {"ok": False, "code": "bad_payload", "error": "Expected a page capture object."}
    url = page_extractor.normalize_page_url(str(payload.get("url") or ""))
    if not url:
        return {"ok": False, "code": "bad_url", "error": "url must be http(s) with a valid hostname"}
    raw = payload.get("markdown")
    if not isinstance(raw, str):
        return {"ok": False, "code": "bad_payload", "url": url, "error": "markdown must be text."}
    truncated = bool(payload.get("truncated")) or len(raw) > MAX_MARKDOWN
    markdown = scrub_markdown(_CONTROL.sub("", raw[:MAX_MARKDOWN]).replace("\r\n", "\n"))
    if len(_FENCE.findall(markdown)) % 2:
        markdown += "\n```"  # a cut inside a code block must not swallow what follows
    markdown = re.sub(r"\n{3,}", "\n\n", markdown).strip()
    title = _text(payload.get("title"), 500)
    plain = _plain(markdown)
    diagnostic = article_extractor.text_diagnostic(markdown, allow_short=bool(title))
    if diagnostic:
        state = page_state(diagnostic)
        return {"ok": False, "code": "article_body_not_found", "url": url, "page_state": state,
                "diagnostic": diagnostic, "extraction_engine": ENGINE,
                "error": WALL_COPY if state == "wall" else THIN_COPY}
    engine_version = _text(payload.get("engine_version"), 20) or ENGINE_VERSION
    metadata = {key: value for key, value in (
        ("title", title),
        ("author", _text(payload.get("author"), 300)),
        ("published_date", _text(payload.get("published"), 100)),
        ("site_name", _text(payload.get("site"), 300)),
        ("description", _text(payload.get("description"), 1000)),
        ("image", _text(payload.get("image"), 2000) if _http(_text(payload.get("image"), 2000)) else ""),
        ("language", _text(payload.get("language"), 40)),
    ) if value}
    metadata["capture_source"] = CAPTURE_SOURCE
    now = _now()
    short = len(plain) < article_extractor.MIN_TEXT
    result = {
        "ok": True, "url": url, "title": title or url, "markdown": markdown, "metadata": metadata,
        "extraction_engine": ENGINE, "extraction_version": engine_version,
        "fetched_at": now, "fetched_url": url, "extracted_at": now,
        "extraction_attempts": [{"engine": ENGINE, "version": engine_version, "status": "ok", "diagnostic": ""}],
        "article_status": "short_article" if short else "found", "article_text_length": len(plain),
        "output_truncated": truncated, "links": [], "images": [], "screenshot_path": None,
    }
    if short:
        result["diagnostic"] = "short article"
    return result
