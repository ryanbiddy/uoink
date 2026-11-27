"""Capture one Hacker News discussion through Algolia's public items API."""
from __future__ import annotations

import http.client
import json
import re
import time
from datetime import datetime, timezone
from html import unescape
from urllib.parse import parse_qs, urlsplit

import article_extractor as article
from reddit_extractor import DEFAULT_DEPTH_LIMIT, MAX_COMMENTS, USER_AGENT

SOURCE_TYPE = "hn_thread"
ITEM_URL = "https://news.ycombinator.com/item?id="
API_HOST = "hn.algolia.com"
MAX_BYTES = article.MAX_INPUT
MAX_MARKDOWN_BYTES = article.MAX_MARKDOWN
TIMEOUT = 8


def _id(value):
    text = str(value)
    return str(int(text)) if re.fullmatch(r"[0-9]{1,20}", text) and int(text) else None


def item_id(url):
    if not isinstance(url, str) or not url.strip():
        return None
    try:
        raw = url.strip()
        parsed = urlsplit(raw if "://" in raw else "https://" + raw)
        if (parsed.scheme not in {"https", "http"}
                or parsed.hostname not in {"news.ycombinator.com", "www.news.ycombinator.com"}
                or parsed.username is not None or parsed.password is not None
                or parsed.port not in {None, 443 if parsed.scheme == "https" else 80}
                or parsed.path not in {"/item", "/item/"}):
            return None
        ids = parse_qs(parsed.query, keep_blank_values=True).get("id", [])
        return _id(ids[0]) if len(ids) == 1 else None
    except ValueError:
        return None


def _fetch_item(item):
    # Fixed HTTPS origin, no redirect handling, cookies or story-link fetches.
    conn = http.client.HTTPSConnection(API_HOST, timeout=TIMEOUT)
    try:
        conn.request("GET", f"/api/v1/items/{item}",
                     headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        resp = conn.getresponse()
        if resp.status == 404:
            raise ValueError("Algolia could not find this Hacker News item.")
        if resp.status == 429:
            raise ValueError("Algolia is rate-limiting requests. Try again in a minute.")
        if resp.status != 200:
            raise ValueError(f"Algolia returned HTTP {resp.status} for this Hacker News item.")
        raw = bytearray()
        deadline = time.monotonic() + TIMEOUT
        while len(raw) <= MAX_BYTES:
            if time.monotonic() > deadline:
                raise TimeoutError
            chunk = resp.read1(min(65536, MAX_BYTES + 1 - len(raw)))
            if not chunk:
                break
            raw.extend(chunk)
        if len(raw) > MAX_BYTES:
            raise ValueError("This Hacker News thread exceeds the download limit.")
    except TimeoutError:
        raise ValueError("Algolia took too long to return the Hacker News thread.") from None
    except (OSError, http.client.HTTPException):
        raise ValueError("Could not reach the Hacker News API at hn.algolia.com.") from None
    finally:
        conn.close()
    try:
        return json.loads(raw)
    except (ValueError, UnicodeError, RecursionError):
        raise ValueError("Algolia returned unreadable Hacker News thread data.") from None


def _markdown(html, url, deadline):
    if not html:
        return "", False
    doc = article.Document(deadline)
    doc.feed(html)
    doc.close()
    # HN supports a small HTML vocabulary. Ignore active content and media,
    # unwrap unknown formatting, and reuse the article reader's safe links,
    # escaping and code fences.
    for node in doc.nodes:
        if node.tag in {"script", "style", "iframe", "svg", "object", "template", "img"}:
            node.excluded = True
        elif node.tag not in {"p", "pre", "code", "a", "i", "em", "b", "strong", "br"}:
            node.tag = "span"
    writer = article.Markdown(url, doc.check)
    rendered = writer.render(doc.root).strip()
    if writer.truncated or len(rendered.encode()) > MAX_MARKDOWN_BYTES // 3:
        # Leave room for both the selected comment and story. Re-escape a
        # plain excerpt so cutting a long body cannot split a link or fence.
        excerpt = article._text(doc.root, limit=MAX_MARKDOWN_BYTES // 3)
        excerpt = excerpt.encode()[:MAX_MARKDOWN_BYTES // 8].decode(errors="ignore")
        return article._escape(excerpt) + " … (text shortened)", True
    return rendered, False


def _visible(node):
    return (not node.get("dead") and not node.get("deleted")
            and (node.get("text") or "").strip() not in {"", "[dead]", "[deleted]", "[removed]"})


def _time(node):
    if node.get("created_at"):
        return str(node["created_at"])[:40]
    if node.get("created_at_i") is not None:
        return datetime.fromtimestamp(node["created_at_i"], timezone.utc).isoformat()
    return ""


def _comment(node, depth, deadline):
    url = ITEM_URL + _id(node["id"])
    author = article._escape((node.get("author") or "[unknown]")[:100])
    stamp = article._escape(_time(node)) or "permalink"
    heading = "#" * min(depth + 3, 6)
    body, shortened = _markdown(node["text"], url, deadline)
    block = f"{heading} {author} · [{stamp}]({url})\n{body}" if body else ""
    return block, shortened


def _comments(parent, depth=0):
    for node in parent.get("children") or ():
        if not isinstance(node, dict) or node.get("type") != "comment":
            continue
        yield node, depth
        # A removed parent can still have public replies.
        if depth < DEFAULT_DEPTH_LIMIT:
            yield from _comments(node, depth + 1)


def _render(story, focus):
    deadline = time.monotonic() + article.MAX_SECONDS
    if story.get("type") != "story" or story.get("dead") or story.get("deleted"):
        raise ValueError("The Hacker News story is unavailable.")
    url = ITEM_URL + _id(story["id"])
    title = " ".join(unescape(story.get("title") or "Untitled Hacker News story").split())[:500]
    author = (story.get("author") or "[unknown]")[:100]
    stamp = _time(story)
    raw_link = story.get("url") or ""
    link = article.safe_link(raw_link, url) if len(raw_link) <= 4096 else None
    points = int(story.get("points") or 0)
    meta = [f"posted by {article._escape(author)}", f"{points} points"]
    if stamp:
        meta.append(article._escape(stamp))
    parts = [f"# {article._escape(title)}", "**Hacker News** · " + " · ".join(meta),
             f"**Source:** {url}"]
    if link:
        parts.append(f"**Story link:** [Open the story]({link})")
    count = 0
    truncated = False
    # Reserve space for the footer. Keep complete Markdown blocks.
    remaining = MAX_MARKDOWN_BYTES - len("\n\n".join(parts).encode()) - 100

    def append(block, shortened=False):
        nonlocal remaining, truncated
        truncated |= shortened
        size = len(block.encode()) + 2
        if size > remaining:
            truncated = True
            return False
        parts.append(block)
        remaining -= size
        return True

    focus_id = _id(focus["id"]) if focus else None
    if focus:
        append("## Selected comment")
        selected, shortened = _comment(focus, 0, deadline) if _visible(focus) else ("", False)
        if selected:
            if append(selected, shortened):
                count += 1
        else:
            append(f"[This comment]({ITEM_URL}{focus_id}) is unavailable.")
    if story.get("text"):
        append(*_markdown(story["text"], url, deadline))
    append("## Top comments")
    for node, depth in _comments(story):
        if depth == DEFAULT_DEPTH_LIMIT and node.get("children"):
            truncated = True
        if not _visible(node) or not _id(node.get("id")):
            continue
        is_selected = _id(node["id"]) == focus_id
        if is_selected:
            # Keep the selected comment's place in the tree for its replies.
            block = "#" * min(depth + 3, 6) + f" [Selected comment]({ITEM_URL}{focus_id})"
            shortened = False
        else:
            if count >= MAX_COMMENTS:
                truncated = True
                break
            block, shortened = _comment(node, depth, deadline)
            if not block:
                continue
        if not append(block, shortened):
            break
        if not is_selected:
            count += 1
    if truncated:
        parts.append("(Thread shortened to fit the capture limit.)")
    elif not count:
        parts.append("(No public comments.)")
    return {
        "ok": True, "url": url, "title": title, "markdown": "\n\n".join(parts) + "\n",
        "metadata": {"author": author, "score": points, "created_at": stamp,
                     "source_url": ITEM_URL + focus_id if focus_id else url,
                     "story_url": link, "selected_comment_id": focus_id,
                     "comments_captured": count, "depth_limit": DEFAULT_DEPTH_LIMIT},
        "extraction_engine": "hn-algolia", "extracted_at": datetime.now(timezone.utc).isoformat(),
        "output_truncated": truncated, "comments_captured": count,
        "links": [{"href": link}] if link else [], "images": [], "screenshot_path": None,
    }


def extract_hn_thread(url):
    requested = item_id(url)
    if not requested:
        return {"ok": False, "code": "bad_url", "error": "Expected a Hacker News item link."}

    def fetch(item):
        node = _fetch_item(item)
        if not isinstance(node, dict) or _id(node.get("id")) != item:
            raise ValueError("Algolia returned an unexpected Hacker News item.")
        return node

    try:
        item = fetch(requested)
        if item.get("type") == "comment":
            story_id = _id(item.get("story_id"))
            if not story_id:
                raise ValueError("Algolia could not identify the story for this comment.")
            return _render(fetch(story_id), item)
        return _render(item, None)
    except article.ExtractionLimit:
        return {"ok": False, "code": "parse_failed", "error": "This thread exceeds the text processing limit."}
    except ValueError as exc:
        return {"ok": False, "code": "fetch_failed", "error": str(exc)}
    except (TypeError, AttributeError, KeyError, OverflowError, OSError):
        return {"ok": False, "code": "parse_failed", "error": "Algolia returned invalid thread data."}
