"""X (Twitter) post text + self-thread extractor (U-15, v3.2.6).

Captures the TEXT of an X post, plus the earlier posts in the author's own
reply chain, via the same public syndication endpoint the video path
already leans on (yt-dlp is invoked with twitter:api=syndication). No API
key, no login. Renders to markdown and returns an `extract_result` in
page_extractor's shape so page_extractor.persist_page_yoink can land it as
a yoink with source_type='x_thread'.

Honest scope, stated rather than papered over: the syndication endpoint
serves one post at a time and only links UPWARD (each post names its
parent). Starting from the shared URL we walk the author's own chain to
the root; posts BELOW the shared one are not reachable without
authenticated GraphQL, so a thread captured from its first post yields
that post only. The markdown says what was captured.

fetch is separated from parse/walk/render so everything below the network
is unit-testable against fixtures. Transport (HTTP route + flag gate) is
owned by server.py.
"""
from __future__ import annotations

import json
import math
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

SOURCE_TYPE = "x_thread"
SYNDICATION_URL = "https://cdn.syndication.twimg.com/tweet-result"
# The endpoint answers this UA reliably; same choice yt-dlp ships.
USER_AGENT = "Googlebot"
MAX_THREAD_HOPS = 25  # ancestor cap so a hostile chain can't loop us

_STATUS_RE = re.compile(
    r"^https?://(?:www\.|mobile\.)?(?:x|twitter)\.com/[^/]+/status(?:es)?/(\d+)",
    re.IGNORECASE,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z")


def is_x_status_url(url: str) -> bool:
    return bool(_STATUS_RE.match((url or "").strip()))


def tweet_id_from_url(url: str) -> str | None:
    m = _STATUS_RE.match((url or "").strip())
    return m.group(1) if m else None


def _js_base36(val: float) -> str:
    """JS Number.prototype.toString(36) for positive finite doubles.
    Port of yt-dlp's js_number_to_string digit emitter (jsinterp.py,
    Unlicense), radix fixed at 36, because the syndication token must
    match the browser's output digit for digit."""
    if val == 0:
        return "0"
    alphabet = "0123456789abcdefghijklmnopqrstuvwxyz"
    fraction, integer = math.modf(val)
    delta = max(math.nextafter(0.0, math.inf), math.ulp(val) / 2)
    digits: list[int] = []  # fractional digit values
    while fraction >= delta:
        delta *= 36
        fraction, digit = math.modf(fraction * 36)
        digits.append(int(digit))
        needs_rounding = fraction > 0.5 or (fraction == 0.5 and int(digit) & 1)
        if needs_rounding and fraction + delta > 1:
            for index in reversed(range(len(digits))):
                if digits[index] + 1 < 36:
                    digits[index] += 1
                    break
                digits.pop()
            else:
                integer += 1
            break
    int_part = ""
    integer = int(integer)
    while integer:
        integer, r = divmod(integer, 36)
        int_part = alphabet[r] + int_part
    out = int_part or "0"
    if digits:
        out += "." + "".join(alphabet[d] for d in digits)
    return out


def syndication_token(tweet_id: str) -> str:
    """((Number(id) / 1e15) * Math.PI).toString(36).replace(/(0+|\\.)/g, '')"""
    value = (int(tweet_id) / 1e15) * math.pi
    return _js_base36(value).replace("0", "").replace(".", "")


def fetch_tweet_json(tweet_id: str, *, timeout: int = 20) -> dict:
    """GET the syndication payload for one post. Raises ValueError with an
    actionable message on the ways X refuses: the endpoint 404s deleted,
    protected, AND blocked requests alike, so the copy says so instead of
    guessing."""
    query = urllib.parse.urlencode({
        "id": str(int(tweet_id)),
        "token": syndication_token(tweet_id),
        "lang": "en",
    })
    req = urllib.request.Request(f"{SYNDICATION_URL}?{query}", headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise ValueError(
                "X returned 404 for this post. That can mean deleted, "
                "protected account, or X refusing the public endpoint "
                "right now. Nothing was saved.")
        if e.code == 429:
            raise ValueError("X is rate-limiting (429). Wait a minute and "
                             "try again.")
        raise ValueError(f"X returned HTTP {e.code}.")
    except urllib.error.URLError as e:
        raise ValueError(f"Couldn't reach X: {e.reason}")
    if not raw.strip():
        raise ValueError("X answered with an empty body. It blocks this "
                         "endpoint sometimes; try again later.")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise ValueError("X didn't return JSON (block page or outage).")
    if not isinstance(data, dict):
        raise ValueError("Unexpected X response shape.")
    if data.get("__typename") == "TweetTombstone":
        raise ValueError("X served a tombstone: this post is unavailable "
                         "(deleted, restricted, or withheld).")
    return data


def _shape_tweet(payload: dict) -> dict:
    user = payload.get("user") or {}
    photos = payload.get("photos") or []
    return {
        "id": str(payload.get("id_str") or ""),
        "author_name": (user.get("name") or "").strip() or "Unknown",
        "author_handle": (user.get("screen_name") or "").strip(),
        "text": (payload.get("text") or "").strip(),
        "created_at": payload.get("created_at") or "",
        "in_reply_to_id": str(payload.get("in_reply_to_status_id_str") or ""),
        "in_reply_to_handle": (payload.get("in_reply_to_screen_name") or "").strip(),
        "photo_count": len(photos) if isinstance(photos, list) else 0,
        "has_video": bool(payload.get("video")),
        "parent_payload": payload.get("parent") if isinstance(payload.get("parent"), dict) else None,
    }


def collect_thread(tweet_id: str, *, timeout: int = 20, _fetch=None) -> list[dict]:
    """Fetch the shared post, then walk the author's own reply chain upward
    to the root (or MAX_THREAD_HOPS). Returns tweets in reading order,
    root first. Uses the embedded `parent` payload when the endpoint
    includes it, refetching by id otherwise. A missing ancestor stops the
    walk without failing the capture: you still get everything below it."""
    fetcher = _fetch or fetch_tweet_json
    start = _shape_tweet(fetcher(tweet_id, timeout=timeout))
    chain = [start]
    hops = 0
    current = start
    while (current["in_reply_to_id"]
           and current["in_reply_to_handle"]
           and current["in_reply_to_handle"].lower() == start["author_handle"].lower()
           and hops < MAX_THREAD_HOPS):
        hops += 1
        parent_payload = current["parent_payload"]
        try:
            if parent_payload and str(parent_payload.get("id_str") or "") == current["in_reply_to_id"]:
                parent = _shape_tweet(parent_payload)
            else:
                parent = _shape_tweet(fetcher(current["in_reply_to_id"],
                                              timeout=timeout))
        except ValueError:
            break  # ancestor gone; keep what we have
        chain.append(parent)
        current = parent
    chain.reverse()
    return chain


def _snippet(text: str, limit: int = 60) -> str:
    flat = re.sub(r"\s+", " ", (text or "")).strip()
    return flat if len(flat) <= limit else flat[:limit - 1].rstrip() + "…"


def render_markdown(tweets: list[dict], source_url: str) -> str:
    root = tweets[0]
    handle = f"@{root['author_handle']}" if root["author_handle"] else "unknown account"
    title = f"{root['author_name']} ({handle}) on X"
    lines = [f"# {title}", ""]
    count = len(tweets)
    lines.append(f"**Source:** {source_url}")
    lines.append("")
    scope = (f"{count} post{'s' if count != 1 else ''} captured: the shared "
             "post and the earlier posts in the author's own chain. Replies "
             "below the shared post aren't served by X's public endpoint.")
    lines += [f"*{scope}*", ""]
    for index, tweet in enumerate(tweets, start=1):
        lines.append(f"## {index}/{count}")
        lines.append(tweet["text"] or "(no text)")
        extras = []
        if tweet["photo_count"]:
            extras.append(f"{tweet['photo_count']} photo{'s' if tweet['photo_count'] != 1 else ''}")
        if tweet["has_video"]:
            extras.append("video (capture it with the regular Uoink button)")
        meta = " · ".join(filter(None, [tweet["created_at"], ", ".join(extras)]))
        if meta:
            lines.append("")
            lines.append(f"*{meta}*")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def extract_x_thread(url: str, *, timeout: int = 20, _fetch=None) -> dict:
    """Fetch + walk + render an X post chain into an extract_result dict
    shaped for page_extractor.persist_page_yoink. `_fetch` is the test
    injection point. Returns {ok: False, code, error} on any failure."""
    tweet_id = tweet_id_from_url(url)
    if not tweet_id:
        return {"ok": False, "code": "bad_url",
                "error": "Not an X post URL (expected x.com/<user>/status/<id>)."}
    try:
        tweets = collect_thread(tweet_id, timeout=timeout, _fetch=_fetch)
    except ValueError as e:
        return {"ok": False, "code": "fetch_failed", "error": str(e)}
    except Exception as e:  # defensive: malformed payloads
        return {"ok": False, "code": "parse_failed",
                "error": f"Couldn't parse the X response: {e}"}
    if not tweets:
        return {"ok": False, "code": "parse_failed",
                "error": "X answered but no post came back."}
    if len(tweets) == 1 and not tweets[0]["text"] and not tweets[0]["photo_count"]:
        return {"ok": False, "code": "empty",
                "error": "That post has no text to capture. For a video "
                         "post, use the regular Uoink button."}

    root = tweets[0]
    canonical = (f"https://x.com/{root['author_handle']}/status/{tweet_id}"
                 if root["author_handle"] else f"https://x.com/i/status/{tweet_id}")
    markdown = render_markdown(tweets, canonical)
    handle = f"@{root['author_handle']}" if root["author_handle"] else "X post"
    return {
        "ok": True,
        "url": canonical,
        "title": f"{handle}: {_snippet(root['text']) or 'X post'}",
        "markdown": markdown,
        "metadata": {
            "author_name": root["author_name"],
            "author_handle": root["author_handle"],
            "tweets_captured": len(tweets),
            "capture_scope": "shared post + earlier same-author chain",
            "photo_count": sum(t["photo_count"] for t in tweets),
            "has_video": any(t["has_video"] for t in tweets),
        },
        "extraction_engine": "x-syndication",
        "extracted_at": _now_iso(),
        "links": [],
        "images": [],
        "screenshot_path": None,
        "tweets_captured": len(tweets),
    }
