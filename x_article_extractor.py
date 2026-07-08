"""X (Twitter) ARTICLE capture — persist a pre-parsed long-form article.

X Articles (x.com/<handle>/article/<id> or x.com/i/article/<id>) are X's
long-form content. Unlike posts/threads, they are NOT served by the public
syndication endpoint the video/text paths lean on — the reliable capture is
the browser extension reading the rendered Article DOM out of the user's
authenticated session (extension/content-x-article.js +
extension/lib/x-article.js). That sidesteps X's login wall.

This module owns the SERVER half: it takes the already-parsed
{url, title, author, markdown, images} the extension posts, validates it,
and shapes it into an `extract_result` dict so
page_extractor.persist_page_yoink can land it as a yoink with
source_type='x_article' under the configured output root. No network happens
here — the parsing already ran in the page.

Transport (HTTP route + token gate) is owned by server.py.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

SOURCE_TYPE = "x_article"
EXTRACTION_ENGINE = "x-article-dom"

# Below this many characters of body text the parse is "thin": we fail
# honestly rather than persist page chrome as if it were the article. Mirrors
# XArticle.MIN_BODY_CHARS on the extension side.
MIN_BODY_CHARS = 40

_ARTICLE_RE = re.compile(
    r"^https?://(?:www\.|mobile\.)?(?:x|twitter)\.com/"
    r"(?:i/article/([A-Za-z0-9]{5,})"
    r"|([A-Za-z0-9_]{1,15})/article/([A-Za-z0-9]{5,}))",
    re.IGNORECASE,
)

def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z")


def is_x_article_url(url: str) -> bool:
    return bool(_ARTICLE_RE.match((url or "").strip()))


def canonical_article_url(url: str) -> str | None:
    """Normalise any X Article URL to https://x.com/<handle>/article/<id> (or
    the /i/article/<id> form). Returns None when it isn't an article URL."""
    m = _ARTICLE_RE.match((url or "").strip())
    if not m:
        return None
    bare_id, handle, handle_id = m.group(1), m.group(2), m.group(3)
    if bare_id:
        return f"https://x.com/i/article/{bare_id}"
    return f"https://x.com/{handle}/article/{handle_id}"


def _body_text(markdown: str) -> str:
    """Strip markdown punctuation to measure real content length."""
    stripped = re.sub(r"[#>*`\-!\[\]()]", " ", markdown or "")
    return re.sub(r"\s+", " ", stripped).strip()


def _clean_images(images) -> list[dict]:
    out: list[dict] = []
    if not isinstance(images, list):
        return out
    for item in images:
        if isinstance(item, str) and item.strip():
            out.append({"src": item.strip(), "alt": ""})
        elif isinstance(item, dict):
            src = str(item.get("src") or "").strip()
            if src:
                out.append({"src": src, "alt": str(item.get("alt") or "")})
        if len(out) >= 100:
            break
    return out


def build_extract_result(payload: dict) -> dict:
    """Validate the extension's pre-parsed article and return an
    `extract_result` shaped for page_extractor.persist_page_yoink, or
    {ok: False, code, error} when the payload is unusable.

    Honesty guard: an empty / thin parse (no title AND < MIN_BODY_CHARS of
    body) is rejected with code 'empty' so a blocked or still-loading page
    never lands as a junk yoink."""
    if not isinstance(payload, dict):
        return {"ok": False, "code": "bad_payload",
                "error": "Expected a parsed article object."}

    url = str(payload.get("url") or "").strip()
    canonical = canonical_article_url(url)
    if not canonical:
        return {"ok": False, "code": "bad_url",
                "error": ("Not an X Article URL (expected "
                          "x.com/<handle>/article/<id>).")}

    title = str(payload.get("title") or "").strip()
    author = str(payload.get("author") or "").strip()
    author_name = str(payload.get("author_name") or "").strip()
    author_handle = str(payload.get("author_handle") or "").strip().lstrip("@")
    markdown = str(payload.get("markdown") or "").strip()
    images = _clean_images(payload.get("images"))

    body_len = len(_body_text(markdown))
    if body_len < MIN_BODY_CHARS and not title:
        return {"ok": False, "code": "empty",
                "error": ("The article came back empty. X may have "
                          "login-walled the page or changed its markup. "
                          "Nothing was saved.")}

    if not title:
        title = f"{author} on X" if author else "X Article"

    return {
        "ok": True,
        "url": canonical,
        "title": title,
        "markdown": markdown,
        "metadata": {
            "author": author,
            "author_name": author_name,
            "author_handle": author_handle,
            "image_count": len(images),
            "capture_scope": "rendered X Article DOM (authenticated session)",
        },
        "extraction_engine": EXTRACTION_ENGINE,
        "extracted_at": _now_iso(),
        "links": [],
        "images": images,
        "screenshot_path": None,
        "image_count": len(images),
    }


# NOTE: the pasted-URL fallback's honest login-wall handling lives in
# page_extractor.extract_page (_is_x_login_wall), a single engine-agnostic
# implementation shared by every /extract/page caller. It returns
# {ok: False, code: "x_login_wall"} before anything persists, so this module
# no longer needs its own thin-content guard for that path.
