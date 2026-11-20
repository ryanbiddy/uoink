"""Full text of long X posts and X Article bodies (3.18.0).

Why X saves were cut off: X serves the first ~275 characters of a long post
("note tweet") in its ``text`` field and marks the post with a bare
``note_tweet: {"id": ...}`` that carries no text. The public syndication
endpoint answers with exactly that, and Uoink runs yt-dlp with
``twitter:api=syndication``, so both the text path and the video path saved
the cut-off copy. X Articles are worse: syndication returns the title, the
cover and a short preview, and the Article page itself is login-walled.

Where the full text comes from, in Uoink's order (3.18.0 product decision:
anything that touches a network beyond the source is opt-in):

1. X's own syndication endpoint, for every post (x_extractor). It tells us
   whether a post is long (the note_tweet marker) and carries the quoted
   post and the t.co link expansions.
2. The open X tab, through the extension. When a person saves the post they
   are looking at, the extension reads the post text from the page and sends
   it along (``dom_post``). Nothing leaves the computer for this.
3. FxTwitter API v2, a free community service, only when the person turns
   on ``fxtwitter_enrichment_enabled``. It sees the link of the post being
   saved. Owned by x_extractor (cache, back-off, named User-Agent).

Nothing here forges X client headers or uses X's internal web API.

This module holds the pure helpers: X's length count, the offline "may be
cut off" screen, the text comparison the repair job uses before it
rewrites anything, and the Draft.js to Markdown converter for the Article
bodies FxTwitter returns.
"""
from __future__ import annotations

import html
import re
import time
import unicodedata


def _retry_after(headers) -> float | None:
    """Seconds to wait, from Retry-After or x-rate-limit-reset."""
    if headers is None:
        return None
    try:
        value = headers.get("Retry-After")
        if value is not None and str(value).strip().isdigit():
            return float(value)
        reset = headers.get("x-rate-limit-reset")
        if reset is not None and str(reset).strip().isdigit():
            return max(1.0, float(reset) - time.time())
    except (TypeError, ValueError, AttributeError):
        return None
    return None


def _dict(value) -> dict:
    return value if isinstance(value, dict) else {}


# ---- text helpers ----------------------------------------------------------
_TCO_RE = re.compile(r"https?://t\.co/[A-Za-z0-9]+")
_URL_RE = re.compile(r"https?://\S+")


def weighted_length(text: str) -> int:
    """X's own length count: Latin and common punctuation weigh 1, other
    characters (CJK, emoji) weigh 2, and every link counts as 23."""
    text = text or ""
    total = 23 * len(_URL_RE.findall(text))
    for ch in _URL_RE.sub("", text):
        code = ord(ch)
        light = (code <= 4351 or 8192 <= code <= 8205 or 8208 <= code <= 8223
                 or 8242 <= code <= 8247)
        total += 1 if light else 2
    return total


def strip_trailing_links(text: str) -> str:
    """Drop the t.co links X appends after the visible text (media, quote)."""
    out = (text or "").rstrip()
    while True:
        trimmed = re.sub(r"\s*https?://t\.co/[A-Za-z0-9]+$", "", out).rstrip()
        if trimmed == out:
            return out
        out = trimmed


# X cuts a long post near 275 weighted characters. A saved text shorter than
# this cannot be a cut-off long post, whatever its last character is.
CUT_OFF_MIN_WEIGHT = 240
CUT_OFF_MAX_WEIGHT = 300


def looks_cut_off(text: str) -> bool:
    """Cheap offline screen for a save that may hold X's cut-off copy. A
    hit is only a reason to ask X (the note_tweet marker decides), so this
    errs on the side of asking."""
    body = strip_trailing_links(text)
    if not body:
        return False
    if re.search(r"(?:…|\.\.\.)$", body):
        return weighted_length(body) >= 100
    return CUT_OFF_MIN_WEIGHT <= weighted_length(body) <= CUT_OFF_MAX_WEIGHT


def normalize(text: str) -> str:
    """Compare form: entities unescaped, links removed, whitespace collapsed."""
    text = unicodedata.normalize("NFC", html.unescape(text or ""))
    text = _URL_RE.sub(" ", text)
    return " ".join(text.replace("…", " ").split())


def extends(saved: str, full: str) -> bool:
    """True when ``full`` is a longer version of ``saved``: the saved words
    (minus the last, possibly half, word) open the full text."""
    old, new = normalize(saved), normalize(full)
    if not new or len(new) <= len(old):
        return False
    mentions = re.compile(r"^(?:@\w+\s+)+")  # a reply's leading @handles
    for a, b in ((old, new), (mentions.sub("", old), mentions.sub("", new))):
        head = a.rsplit(" ", 1)[0] if " " in a else a
        if len(head) < 20:
            head = a
        if head and b.startswith(head):
            return True
    return False


# ---- X Article body (Draft.js content_state) -------------------------------
_HEADINGS = {"header-one": "# ", "header-two": "## ", "header-three": "### ",
             "header-four": "#### ", "header-five": "##### ", "header-six": "###### "}


def _media_urls(article: dict) -> dict:
    out = {}
    for item in article.get("media_entities") or []:
        if not isinstance(item, dict):
            continue
        info = _dict(item.get("media_info"))
        url = info.get("original_img_url")
        variants = [v for v in info.get("variants") or [] if isinstance(v, dict)
                    and str(v.get("content_type") or "").startswith("video/mp4")]
        if variants:
            best = max(variants, key=lambda v: v.get("bit_rate") or v.get("bitrate") or 0)
            url = best.get("url") or url
        if not url:
            url = _dict(info.get("preview_image")).get("original_img_url")
        if isinstance(url, str) and url.startswith("https://"):
            out[str(item.get("media_id") or "")] = (url, info.get("__typename") == "ApiVideo")
    return out


def _entity_map(content: dict) -> dict:
    raw = content.get("entityMap")
    if isinstance(raw, dict):
        return {str(k): _dict(v) for k, v in raw.items()}
    out = {}
    for entry in raw or []:
        if isinstance(entry, dict):
            out[str(entry.get("key"))] = _dict(entry.get("value"))
    return out


def _linked_text(block: dict, entities: dict) -> str:
    text = block.get("text") if isinstance(block.get("text"), str) else ""
    ranges = []
    for item in block.get("entityRanges") or []:
        entity = entities.get(str(_dict(item).get("key")), {})
        url = _dict(entity.get("data")).get("url")
        if entity.get("type") == "LINK" and isinstance(url, str) and url.startswith(("https://", "http://")):
            try:
                start, length = int(item["offset"]), int(item["length"])
            except (KeyError, TypeError, ValueError):
                continue
            ranges.append((start, length, url))
    for start, length, url in sorted(ranges, reverse=True):
        label = text[start:start + length]
        if label.strip():
            text = f"{text[:start]}[{label}]({url}){text[start + length:]}"
    return text


def article_markdown(article: dict) -> tuple[str, list[dict]]:
    """Render an Article's Draft.js content to Markdown. Returns the Markdown
    and the image descriptors it references. Unknown block types keep their
    text, so nothing the author wrote is dropped."""
    content = _dict(_dict(article).get("content"))
    blocks = content.get("blocks") if isinstance(content.get("blocks"), list) else []
    entities = _entity_map(content)
    media = _media_urls(article)
    parts: list[str] = []
    images: list[dict] = []
    list_run = False
    for block in blocks:
        if not isinstance(block, dict):
            continue
        kind = block.get("type") or "unstyled"
        if kind == "atomic":
            for item in block.get("entityRanges") or []:
                entity = entities.get(str(_dict(item).get("key")), {})
                data = _dict(entity.get("data"))
                if entity.get("type") == "MEDIA":
                    for media_item in data.get("mediaItems") or []:
                        found = media.get(str(_dict(media_item).get("mediaId") or ""))
                        if found:
                            # Links, not embeds: opening the saved Article
                            # never loads anything from X by itself.
                            url, is_video = found
                            parts.append(f"[Video]({url})" if is_video else f"[Image]({url})")
                            if not is_video:
                                images.append({"src": url, "alt": ""})
                elif entity.get("type") == "DIVIDER":
                    parts.append("---")
                elif entity.get("type") == "TWEET" and str(data.get("tweetId") or "").isdigit():
                    parts.append(f"[Embedded post](https://x.com/i/status/{data['tweetId']})")
            list_run = False
            continue
        text = _linked_text(block, entities).rstrip()
        if not text.strip():
            list_run = False
            continue
        if kind in ("unordered-list-item", "ordered-list-item"):
            bullet = "- " if kind == "unordered-list-item" else "1. "
            if list_run and parts:
                parts[-1] += "\n" + bullet + text
            else:
                parts.append(bullet + text)
            list_run = True
            continue
        list_run = False
        if kind in _HEADINGS:
            parts.append(_HEADINGS[kind] + " ".join(text.split()))
        elif kind == "blockquote":
            parts.append("\n".join("> " + line for line in text.splitlines()))
        elif kind == "code-block":
            parts.append("```\n" + text + "\n```")
        else:
            parts.append(text)
    return "\n\n".join(parts).strip(), images
