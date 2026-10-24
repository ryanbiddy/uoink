"""Pure X response shaping. No requests or media downloads happen here.

Field patterns: FxEmbed API v2 api-schemas.ts and react-tweet api/types.
Provider records are merged without discarding longer text or supplied entities.
"""
from __future__ import annotations

from copy import deepcopy
import math
import re
import unicodedata
from urllib.parse import quote as quote_url, urlsplit

SCOPE = "shared post + earlier same-author chain"
METRICS = {
    "likes": ("likes", "favorite_count"),
    "reposts": ("reposts", "retweet_count"),
    "quotes": ("quotes", "quote_count"),
    "replies": ("replies", "reply_count", "conversation_count"),
    "views": ("views", "view_count"),
    "bookmarks": ("bookmarks", "bookmark_count"),
}


def _dict(value):
    return value if isinstance(value, dict) else {}


def _list(value):
    return value if isinstance(value, list) else []


def _text(value):
    return value.strip() if isinstance(value, str) else ""


def safe_url(value):
    """Accept only intact HTTP(S) destinations, before trimming or parsing."""
    if not isinstance(value, str) or not value or len(value) > 2048 or "\\" in value:
        return None
    if any(ch.isspace() or unicodedata.category(ch) in ("Cc", "Cf", "Zl", "Zp") for ch in value):
        return None
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            return None
        if parsed.username is not None or parsed.password is not None:
            return None
        parsed.port  # Reject malformed ports too.
    except ValueError:
        return None
    return value


def _url_field(key, record):
    if key == "display_url":  # A label, often a shortened hostname, not a destination.
        return False
    if key in {"url", "src", "href", "poster"} or key.endswith(("_url", "_url_https")):
        return True
    return key in {"original", "replacement"} and (
        record.get("type") in {"url", "media"}
        or any(isinstance(record.get(k), str) and re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", record[k])
               for k in ("original", "replacement")))


def url_fields(value):
    """Yield destinations even inside raw facets, attachments and source media."""
    if isinstance(value, dict):
        for key, child in value.items():
            if _url_field(key, value):
                yield child
            else:
                yield from url_fields(child)
    elif isinstance(value, list):
        for child in value:
            yield from url_fields(child)


def sanitize_urls(value, *, markdown=False):
    """Copy evidence with invalid destinations removed and the loss disclosed."""
    rejected = False

    def visit(node):
        nonlocal rejected
        if isinstance(node, dict):
            out = {}
            for key, child in node.items():
                if _url_field(key, node):
                    cleaned = safe_url(child)
                    if child is not None and cleaned is None:
                        rejected = True
                    # URL punctuation must not create Markdown links in prose.
                    out[key] = quote_url(cleaned, safe=":/?#@!$&'*+,;=%~-._") if cleaned and markdown else cleaned
                else:
                    out[key] = visit(child)
            return out
        if isinstance(node, list):
            return [visit(child) for child in node]
        return deepcopy(node)

    out = visit(value)
    if rejected and isinstance(out, dict):
        out["url_warnings"] = union(_list(out.get("url_warnings")), [
            "Some supplied URLs were omitted because they were not valid HTTP or HTTPS links."])
    return out


def union(left, right):
    out = deepcopy(left)
    for value in right:
        if value not in out:
            out.append(deepcopy(value))
    return out


def _retain(left, right):
    """Union lists and fill missing values; never shorten supplied strings."""
    out = deepcopy(left)
    for key, value in right.items():
        old = out.get(key)
        if isinstance(old, dict) and isinstance(value, dict):
            out[key] = _retain(old, value)
        elif isinstance(old, list) and isinstance(value, list):
            out[key] = union(old, value)
        elif old is None or old == "" or (isinstance(old, str)
                                          and isinstance(value, str) and len(value) > len(old)):
            out[key] = deepcopy(value)
    return out


def _media(payload):
    container = _dict(payload.get("media"))
    entries = []
    for key, kind in (("photos", "photo"), ("videos", "video"), ("all", "unknown")):
        entries += [(v, kind) for v in _list(container.get(key))]
    entries += [(v, "photo") for v in _list(payload.get("photos"))]
    entries += [(v, "unknown") for v in _list(payload.get("mediaDetails"))]
    for entity in _list(_dict(payload.get("entities")).get("media")):
        if isinstance(entity, dict) and (entity.get("media_url_https") or entity.get("video_info")):
            entries.append((entity, "unknown"))
    if isinstance(payload.get("video"), dict):
        entries.append((payload["video"], "video"))
    out = []
    for value, fallback in entries:
        if not isinstance(value, dict):
            continue
        kind = _text(value.get("type")) or fallback
        if kind == "animated_gif":
            kind = "gif"
        variants = union(_list(value.get("formats")), _list(value.get("variants")))
        variants = union(variants, _list(_dict(value.get("video_info")).get("variants")))
        variants = [dict(v, url=v.get("url") or v.get("src"))
                    for v in variants if isinstance(v, dict)]
        variant_url = next((v["url"] for v in variants if v.get("url")), None)
        is_photo = kind == "photo"
        url = value.get("media_url_https") if is_photo else None
        url = url or (variant_url if value.get("video_info") else value.get("url"))
        url = url or value.get("url") or variant_url
        # Keep the original descriptor too (dimensions, format, duration, etc.).
        descriptor = dict(deepcopy(value), type=kind, url=url,
                          source_descriptors=[deepcopy(value)],
                          alt_text=next((value[k] for k in ("altText", "ext_alt_text", "alt", "alt_text")
                                         if value.get(k) is not None), None),
                          poster=(value.get("thumbnail_url") or value.get("poster")
                                  or (value.get("media_url_https") if not is_photo else None)),
                          variants=variants)
        out = merge_media(out, [descriptor])
    return out


def merge_media(left, right):
    out = deepcopy(left)
    for value in right:
        match = next((i for i, old in enumerate(out)
                      if old.get("type") == value.get("type") and
                      ((old.get("url") and old.get("url") == value.get("url")) or
                       (old.get("id") and old.get("id") == value.get("id")) or
                       (old.get("poster") and old.get("poster") == value.get("poster")))), None)
        if match is None:
            out.append(deepcopy(value))
        else:
            out[match] = _retain(out[match], value)
    return out


def shape(payload, provider="syndication"):
    """Normalize one post, including quotes, without trimming display ranges."""
    payload = sanitize_urls(_dict(payload))
    author = _dict(payload.get("author") or payload.get("user"))
    post_id = str(payload.get("id_str") or payload.get("id") or "")
    text = _text(payload.get("text"))
    raw = _dict(payload.get("raw_text"))
    raw_text = _text(raw.get("text"))
    if len(raw_text) > len(text):
        text = raw_text
    note = _dict(payload.get("note_tweet"))
    note_result = _dict(_dict(note.get("note_tweet_results")).get("result"))
    note_text = note.get("text") or note_result.get("text")
    if isinstance(note_text, str) and len(note_text) > len(text):
        text = note_text.strip()
    truncated = bool(payload.get("truncated") or (note and not note_text))
    truncated = truncated or bool(re.search(r"(?:\u2026|\.\.\.)\s*(?:https?://t\.co/\S+)?$", text))
    completeness = "truncated" if truncated else (
        "complete" if provider == "FxTwitter" and (isinstance(payload.get("text"), str) or raw_text) else "unknown")
    reason = ("response marks omitted text" if payload.get("truncated") or (note and not note_text)
              else "text ends with an ellipsis" if truncated
              else "full status text supplied by FxTwitter" if completeness == "complete"
              else "response does not verify full text")
    entities = deepcopy(_dict(payload.get("entities")))
    entities = _retain(entities, _dict(note.get("entity_set") or note.get("entities")))
    entities = _retain(entities, _dict(note_result.get("entity_set") or note_result.get("entities")))
    facets = _list(raw.get("facets"))
    links = []
    for entity in _list(entities.get("urls")) + _list(entities.get("media")):
        if isinstance(entity, dict):
            links = union(links, [dict(deepcopy(entity), url=_text(entity.get("url")) or None,
                                      expanded_url=_text(entity.get("expanded_url")) or None)])
    for facet in facets:
        if isinstance(facet, dict) and (safe_url(facet.get("original")) or safe_url(facet.get("replacement"))):
            links = union(links, [dict(deepcopy(facet), url=_text(facet.get("original")) or None,
                                       expanded_url=_text(facet.get("replacement")) or None,
                                       display_url=facet.get("display"))])
    media = _media(payload)
    metrics = {}
    for key, aliases in METRICS.items():
        metrics[key] = next((payload[a] for a in aliases
                             if type(payload.get(a)) in (int, float) and math.isfinite(payload[a])
                             and payload[a] >= 0), None)
    if metrics["views"] is None:
        views = _dict(payload.get("video")).get("viewCount")
        if type(views) in (int, float) and math.isfinite(views) and views >= 0:
            metrics["views"] = views
    replying = _dict(payload.get("replying_to"))
    quote = payload.get("quote") or payload.get("quoted_tweet")
    if not isinstance(quote, dict) and payload.get("quoted_status_id_str"):
        quote = {"id": payload["quoted_status_id_str"], "type": "tombstone"}
    result = {
        "id": post_id,
        "url": payload.get("url") or (f"https://x.com/{author.get('screen_name') or 'i'}/status/{post_id}" if post_id else None),
        "author": {"name": _text(author.get("name")) or None, "handle": _text(author.get("screen_name")) or None},
        "created_at": payload.get("created_at") or None,
        "text": text, "text_completeness": completeness, "capture_provider": provider,
        "text_completeness_reason": reason,
        "providers": [provider], "provider_status": {provider: "captured"},
        "quote": shape(quote, provider) if isinstance(quote, dict) else None,
        "quote_status": "captured" if isinstance(quote, dict) else "unknown",
        "expanded_links": links, "entities": entities, "raw_text": deepcopy(raw),
        "media": media, "media_status": "captured" if media else "unknown",
        "engagement": metrics,
        "in_reply_to_id": str(payload.get("in_reply_to_status_id_str") or replying.get("status") or ""),
        "in_reply_to_handle": _text(payload.get("in_reply_to_screen_name") or replying.get("screen_name")),
        "missing_parent": None,
        "attachments": {k: deepcopy(payload[k]) for k in ("poll", "card", "article", "community_note") if k in payload},
        "media_extra": {k: deepcopy(v) for k, v in _dict(payload.get("media")).items()
                        if k not in {"photos", "videos", "all"}},
    }
    if payload.get("url_warnings"):
        result["url_warnings"] = payload["url_warnings"]
    if payload.get("type") == "tombstone" or payload.get("__typename") == "TweetTombstone":
        result["text_completeness"] = "unknown"
        result["unavailable_reason"] = payload.get("reason") or "unavailable"
    result["quote_status"] = _quote_status(result.get("quote"))
    return sanitize_urls(result)


def _quote_status(quote):
    if not quote:
        return "unknown"
    if quote.get("unavailable_reason") and not quote.get("text"):
        return "unavailable"
    return "captured" if quote["text_completeness"] == "complete" else "partial"


def merge(left, right):
    """Combine matching posts, keeping text and completeness from the fuller one."""
    left, right = sanitize_urls(left), sanitize_urls(right)
    if left.get("id") and right.get("id") and right["id"] != left["id"]:
        out = deepcopy(left)
        out["provider_status"][right["capture_provider"]] = "post ID mismatch"
        return out
    out = _retain(left, right)
    out["engagement"] = {}
    for key in METRICS:
        counts = [p.get("engagement", {}).get(key) for p in (left, right)]
        counts = [v for v in counts if type(v) in (int, float) and math.isfinite(v) and v >= 0]
        out["engagement"][key] = max(counts) if counts else None
    for key in ("id", "url", "in_reply_to_id", "in_reply_to_handle"):
        out[key] = left.get(key) or right.get(key)
    out["author"] = {key: left["author"].get(key) or right["author"].get(key)
                     for key in ("name", "handle")}
    if len(right["text"]) > len(left["text"]) or (
            right["text"] == left["text"] and right["text_completeness"] == "complete"):
        for key in ("text", "text_completeness", "text_completeness_reason", "capture_provider"):
            out[key] = right[key]
    else:
        for key in ("text", "text_completeness", "text_completeness_reason", "capture_provider"):
            out[key] = left[key]
    out["media"] = merge_media(left["media"], right["media"])
    for key in ("quote",):
        if left.get(key) and right.get(key):
            out[key] = merge(left[key], right[key])
    out["quote_status"] = _quote_status(out.get("quote"))
    out["media_status"] = "captured" if out["media"] else "unknown"
    out["provider_status"].update(right["provider_status"])
    return out


def expanded_text(post):
    links = {}
    for link in post["expanded_links"]:
        original, expanded = safe_url(link.get("url")), safe_url(link.get("expanded_url"))
        if original and expanded and len(expanded) > len(links.get(original, "")):
            links[original] = expanded
    links = {k: quote_url(v, safe=":/?#@!$&'*+,;=%~-._") for k, v in links.items()}
    return re.sub(r"https?://t\.co/[A-Za-z0-9]+", lambda m: links.get(m[0], m[0]), post["text"])


def disclosures(post):
    notes = [f"Text: {post['text_completeness']}. Provider: {post['capture_provider']}."]
    notes.extend(post.get("url_warnings", []))
    if post["text_completeness"] == "truncated":
        notes.append(f"Text completeness signal: {post['text_completeness_reason']}.")
    for provider, status in post["provider_status"].items():
        if status != "captured":
            notes.append(f"{provider} supplement: {status}. Saved available evidence.")
    if post.get("missing_parent"):
        parent = post["missing_parent"]
        notes.append(f"Parent {parent['id']} not captured: {parent['reason']}.")
    if post.get("unavailable_reason"):
        notes.append(f"Post unavailable: {post['unavailable_reason']}.")
    if not post.get("quote"):
        notes.append("Quoted-post availability is unknown.")
    else:
        quote = post["quote"]
        notes.append(f"Quoted post {quote['id']}: text {quote['text_completeness']}. "
                     f"Provider: {quote['capture_provider']}.")
        if quote.get("unavailable_reason"):
            notes.append(f"Quoted post {quote['id']} unavailable: {quote['unavailable_reason']}.")
    if not post["media"]:
        notes.append("Media availability is unknown.")
    else:
        notes.append("Media URLs saved as descriptors. Media files were not downloaded by this capture.")
        if any(m["type"] == "photo" and m.get("alt_text") is None for m in post["media"]):
            notes.append("Some photo alt text is unavailable.")
        if any(m["type"] in {"video", "gif"} and not m.get("variants") for m in post["media"]):
            notes.append("Some video or GIF variants are unavailable.")
        if any(m["type"] in {"video", "gif"} and not m.get("poster") for m in post["media"]):
            notes.append("Some video or GIF posters are unavailable.")
    unresolved = set(re.findall(r"https?://t\.co/[A-Za-z0-9]+", expanded_text(post)))
    if unresolved:
        notes.append("Some shortened links could not be expanded from the response.")
    missing_metrics = [key for key, value in post["engagement"].items() if value is None]
    if missing_metrics:
        notes.append("Engagement unavailable: " + ", ".join(missing_metrics) + ".")
    return notes


def summary_lines(evidence):
    """Disclosures for bounded cards and CLI text, including nested quotes."""
    lines = ["Capture scope: " + evidence.get("scope", "unknown") + "."]
    lines.extend(evidence.get("limits", []))
    def visit(post, prefix=""):
        notes = post.get("disclosures") or disclosures(post)
        lines.extend(prefix + note for note in notes)
        if post.get("quote"):
            visit(post["quote"], f"Quoted post {post['quote']['id']}: ")
    for post in evidence.get("posts", []):
        visit(post, f"Post {post['id']}: ")
    if evidence.get("summary"):
        for key, value in evidence["summary"].items():
            lines.append(f"{key.replace('_', ' ').capitalize()}: {value}")
    if evidence.get("details_omitted"):
        lines.append("Card details were shortened. Full evidence is in the saved X sidecar.")
    return lines


def compact_summary(evidence):
    """Keep a long thread's limits visible even in a small library card."""
    states = {"complete": 0, "truncated": 0, "unknown": 0}
    providers = []
    missing = []
    for post in evidence.get("posts", []):
        states[post["text_completeness"]] += 1
        providers = union(providers, [post["capture_provider"]])
        missing.extend(note for note in post.get("disclosures", []) if note.startswith("Parent "))
    return {
        "scope": evidence.get("scope"), "limits": evidence.get("limits"),
        "details_omitted": True, "detail_location": "Saved X sidecar metadata.x_capture",
        "posts": [],
        "summary": {"post_count": len(evidence.get("posts", [])), "text_completeness": states,
                    "capture_providers": providers, "missing_parents": missing,
                    "omitted_details": "Per-post text, quotes, links, media, metrics and provider failures are in the saved sidecar."},
    }


def capture(posts, scope=SCOPE):
    return {"schema_version": 1, "scope": scope, "posts": [sanitize_urls(p) for p in posts],
            "limits": ["Only the shared post and earlier same-author posts are captured.",
                       "Replies below the shared post and other authors' replies are outside this capture."]}


def has_content(post):
    return bool(post["text"] or post["media"] or post["quote"]
                or any(post.get("attachments", {}).values()))


def _attachment_lines(value, label):
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _attachment_lines(child, label + " " + key.replace("_", " "))
    elif isinstance(value, list):
        for i, child in enumerate(value, 1):
            yield from _attachment_lines(child, f"{label} {i}")
    elif value is not None and value != "":
        yield f"{label}: {value}"


def render_post(post):
    body = expanded_text(post)
    original_quote = post.get("quote")
    post = sanitize_urls(post, markdown=True)
    lines = [body or "(no text)", "", *disclosures(post)]
    for media in post["media"]:
        lines.append(f"{media['type'].capitalize()}: {media.get('url') or 'URL unavailable'}")
        if media.get("alt_text") is not None:
            lines.append(f"Alt text: {media['alt_text']}")
        if media.get("poster"):
            lines.append(f"Poster: {media['poster']}")
        for variant in media.get("variants", []):
            lines.append(f"Variant: {variant.get('url') or 'URL unavailable'}")
    seen_links = set()
    for link in post["expanded_links"]:
        expanded = link.get("expanded_url") or link.get("url")
        if expanded and expanded not in seen_links:
            lines.append(f"Link: {expanded}")
            seen_links.add(expanded)
    available = [f"{k}: {v}" for k, v in post["engagement"].items() if v is not None]
    if available:
        lines.append("Engagement: " + ", ".join(available) + ".")
    for kind, value in post.get("attachments", {}).items():
        lines.extend(_attachment_lines(value, kind.replace("_", " ").capitalize()))
    if post.get("quote"):
        quote = post["quote"]
        lines += ["", f"Quoted post {quote['id']} by @{quote['author'].get('handle') or 'unknown'}: {quote['url'] or 'URL unavailable'}",
                  *render_post(original_quote)]
    return lines
