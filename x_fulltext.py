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
   it to the local helper (``dom_post``). The helper still asks X's public
   endpoint for the post by its ID, as for any X save.
3. FxTwitter API v2, a free community service, only when the person turns
   on ``fxtwitter_enrichment_enabled``. It sees the post's ID and the
   computer's IP address. Owned by x_extractor (switch, cache, back-off,
   named User-Agent).

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


_LEADING_MENTIONS_RE = re.compile(r"^(?:@\w{1,15}\s+)+")


def looks_cut_off(text: str) -> bool:
    """Cheap offline screen for a save that may hold X's cut-off copy. A
    hit is only a reason to ask X (the note_tweet marker decides), so this
    errs on the side of asking. A reply's leading @handles don't count
    toward X's limit, so they are left out of the length. Text longer than
    X's cut-off copy is whole, even when it ends in an ellipsis."""
    body = _LEADING_MENTIONS_RE.sub("", strip_trailing_links(text).lstrip())
    if not body:
        return False
    weight = weighted_length(body)
    if re.search(r"(?:…|\.\.\.)$", body):
        return 100 <= weight <= CUT_OFF_MAX_WEIGHT
    return CUT_OFF_MIN_WEIGHT <= weight <= CUT_OFF_MAX_WEIGHT


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
# The body is someone else's words, so the Markdown is built to say only
# what they wrote: their characters are escaped, links are plain http(s)
# with their brackets and spaces encoded, images are links (never embeds),
# and no HTML passes through.
_HEADINGS = {"header-one": "# ", "header-two": "## ", "header-three": "### ",
             "header-four": "#### ", "header-five": "##### ", "header-six": "###### "}
# Enough to stop links, images, HTML and code spans. Underscores stay as
# they are: handles and file names keep reading (and searching) normally.
_MD_INLINE_RE = re.compile(r"([\\`*\[\]<>])")
_MD_LINE_START_RE = re.compile(r"^(\s*)(?:([#>+=-])|(\d+)([.)]))", re.MULTILINE)


def _md_inline(text: str) -> str:
    return _MD_INLINE_RE.sub(r"\\\1", text or "")


def _line_start(match) -> str:
    lead, mark, number, dot = match.groups()
    # Only punctuation can be escaped in Markdown, so a list number keeps
    # its digits and its dot is escaped ("1\. ").
    return lead + ("\\" + mark if mark else number + "\\" + dot)


def _md_line_starts(text: str) -> str:
    return _MD_LINE_START_RE.sub(_line_start, text or "")


def md_text(text: str) -> str:
    """Article text as literal Markdown: no link, image, HTML, heading or
    emphasis can come out of the author's own characters."""
    return _md_line_starts(_md_inline(text))


def md_url(url) -> str | None:
    """An http(s) address safe inside ``[label](...)``, or None."""
    try:
        from uoink_core.x_evidence import safe_url
    except ImportError:  # pragma: no cover - uoink_core ships with the helper
        return None
    clean = safe_url(url)
    if not clean:
        return None
    from urllib.parse import quote
    return quote(clean, safe=":/?#@!$&*+,;=%~-._")


def _utf16_offsets(text: str) -> list[int]:
    """offsets[i] is the UTF-16 position of text[i] (and of the end, at
    len(text)). Draft.js counts in UTF-16 units, Python in code points."""
    out, unit = [], 0
    for ch in text:
        out.append(unit)
        unit += 2 if ord(ch) > 0xFFFF else 1
    out.append(unit)
    return out


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
        clean = md_url(url) if isinstance(url, str) and url.startswith("https://") else None
        if clean:
            out[str(item.get("media_id") or "")] = (clean, info.get("__typename") == "ApiVideo")
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
    """The block's text as escaped Markdown, its LINK ranges as links.
    Ranges are in UTF-16 units; one that is out of bounds, splits an emoji
    or overlaps an earlier one is dropped (its text stays, unlinked)."""
    text = block.get("text") if isinstance(block.get("text"), str) else ""
    offsets = _utf16_offsets(text)
    index_of = {unit: i for i, unit in enumerate(offsets)}
    ranges = []
    for item in block.get("entityRanges") or []:
        entity = entities.get(str(_dict(item).get("key")), {})
        url = md_url(_dict(entity.get("data")).get("url"))
        if entity.get("type") != "LINK" or not url:
            continue
        try:
            start, length = int(_dict(item)["offset"]), int(_dict(item)["length"])
        except (KeyError, TypeError, ValueError):
            continue
        if start < 0 or length <= 0 or start not in index_of or start + length not in index_of:
            continue
        ranges.append((index_of[start], index_of[start + length], url))
    out, cursor = [], 0
    for start, end, url in sorted(ranges):
        if start < cursor:
            continue  # overlaps the link before it
        label = " ".join(text[start:end].split())
        out.append(_md_inline(text[cursor:start]))
        out.append(f"[{_md_inline(label)}]({url})" if label else _md_inline(text[start:end]))
        cursor = end
    out.append(_md_inline(text[cursor:]))
    return _md_line_starts("".join(out))


def _code_fence(text: str) -> str:
    longest = max((len(run) for run in re.findall(r"`+", text or "")), default=0)
    return "`" * max(3, longest + 1)


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
                elif entity.get("type") == "TWEET" and _ascii_digits(data.get("tweetId")):
                    parts.append(f"[Embedded post](https://x.com/i/status/{data['tweetId']})")
            list_run = False
            continue
        if kind == "code-block":
            raw = (block.get("text") if isinstance(block.get("text"), str) else "").rstrip()
            list_run = False
            if raw.strip():
                fence = _code_fence(raw)
                parts.append(f"{fence}\n{raw}\n{fence}")
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
        else:
            parts.append(text)
    return "\n\n".join(parts).strip(), images


def _ascii_digits(value) -> bool:
    text = str(value or "")
    return 0 < len(text) <= 25 and text.isascii() and text.isdigit()
