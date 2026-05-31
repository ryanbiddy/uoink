"""Reddit thread extractor (V3.3-SOURCE-EXPANSION-SPEC.md section 4).

Fetches a thread via Reddit's public `.json` endpoint (no API key, no OAuth),
flattens the comment tree (depth + score limited), renders it to markdown, and
returns an `extract_result` in page_extractor's shape so
page_extractor.persist_page_yoink can land it as a yoink with
source_type='reddit_thread'. The conversational corpus structures as
`# Post -> ## Top comments -> ### nested replies` so search and facets work on
it instead of a flat wall of comments.

fetch is separated from parse/render so the parsing is unit-testable against a
fixture without the network. Transport (HTTP route + MCP tool) is owned by
server.py.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone

SOURCE_TYPE = "reddit_thread"
USER_AGENT = "uoink/1.0 (local corpus tool; +https://uoink.app)"
DEFAULT_DEPTH_LIMIT = 4
DEFAULT_SCORE_THRESHOLD = 2
MAX_COMMENTS = 500  # hard cap so a 10k-comment thread can't blow up the corpus

_THREAD_RE = re.compile(
    r"^https?://(?:www\.|old\.|new\.|np\.)?reddit\.com/r/[^/]+/comments/[^/]+",
    re.IGNORECASE,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z")


def is_reddit_thread_url(url: str) -> bool:
    return bool(_THREAD_RE.match((url or "").strip()))


def canonical_json_url(url: str) -> str | None:
    """Normalise any reddit thread URL to https://www.reddit.com/<path>.json.
    Returns None when the URL isn't a recognisable thread."""
    url = (url or "").strip()
    if not is_reddit_thread_url(url):
        return None
    # drop query + fragment
    base = url.split("?", 1)[0].split("#", 1)[0]
    # normalise host to www.reddit.com
    base = re.sub(r"^https?://(?:www\.|old\.|new\.|np\.)?reddit\.com",
                  "https://www.reddit.com", base, flags=re.IGNORECASE)
    base = base.rstrip("/")
    if base.endswith(".json"):
        return base
    return base + "/.json"


def fetch_thread_json(url: str, *, timeout: int = 20) -> list:
    """GET the thread's .json. Raises ValueError with an actionable message on
    the failure modes Reddit returns (403 private/quarantined, 404 removed,
    rate-limit, non-JSON)."""
    json_url = canonical_json_url(url)
    if not json_url:
        raise ValueError("not a Reddit thread URL")
    req = urllib.request.Request(json_url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        if e.code == 403:
            raise ValueError("Reddit returned 403. This thread is private, "
                             "quarantined, or rate-limited. Try again later.")
        if e.code == 404:
            raise ValueError("Reddit returned 404. This thread was removed or "
                             "the URL is wrong.")
        if e.code == 429:
            raise ValueError("Reddit is rate-limiting (429). Wait a minute "
                             "and try again.")
        raise ValueError(f"Reddit returned HTTP {e.code}.")
    except urllib.error.URLError as e:
        raise ValueError(f"Couldn't reach Reddit: {e.reason}")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise ValueError("Reddit didn't return JSON (login wall or outage).")
    if not isinstance(data, list) or len(data) < 2:
        raise ValueError("Unexpected Reddit response shape.")
    return data


def _flatten_comments(children: list, *, depth: int, depth_limit: int,
                       score_threshold: int, acc: list) -> None:
    for child in children:
        if len(acc) >= MAX_COMMENTS:
            return
        if not isinstance(child, dict) or child.get("kind") != "t1":
            continue  # skip "more" stubs and malformed entries
        data = child.get("data") or {}
        body = (data.get("body") or "").strip()
        if not body or body in ("[deleted]", "[removed]"):
            continue
        try:
            score = int(data.get("score") or 0)
        except (TypeError, ValueError):
            score = 0
        if score < score_threshold:
            continue
        acc.append({
            "author": data.get("author") or "[unknown]",
            "body": body,
            "score": score,
            "depth": depth,
        })
        if depth < depth_limit:
            replies = data.get("replies")
            if isinstance(replies, dict):
                grand = (replies.get("data") or {}).get("children") or []
                _flatten_comments(grand, depth=depth + 1,
                                  depth_limit=depth_limit,
                                  score_threshold=score_threshold, acc=acc)


def parse_thread(raw_json: list, *, depth_limit: int = DEFAULT_DEPTH_LIMIT,
                  score_threshold: int = DEFAULT_SCORE_THRESHOLD) -> dict:
    """Pure parse of the [post_listing, comments_listing] shape into
    {post, comments:[{author, body, score, depth}]} with depth + score
    limits applied. Comments are returned pre-order (parent before its
    replies) with a `depth` marker so the renderer can nest them."""
    post_children = (raw_json[0].get("data") or {}).get("children") or []
    if not post_children:
        raise ValueError("No post found in the Reddit response.")
    pd = post_children[0].get("data") or {}
    permalink = pd.get("permalink") or ""
    post = {
        "title": (pd.get("title") or "Untitled Reddit thread").strip(),
        "author": pd.get("author") or "[unknown]",
        "subreddit": pd.get("subreddit") or "",
        "selftext": (pd.get("selftext") or "").strip(),
        "score": int(pd.get("score") or 0),
        "num_comments": int(pd.get("num_comments") or 0),
        "url": ("https://www.reddit.com" + permalink) if permalink else (pd.get("url") or ""),
        "created_utc": pd.get("created_utc"),
    }
    comments: list = []
    comment_children = (raw_json[1].get("data") or {}).get("children") or []
    _flatten_comments(comment_children, depth=0, depth_limit=depth_limit,
                      score_threshold=score_threshold, acc=comments)
    return {"post": post, "comments": comments}


def render_markdown(parsed: dict) -> str:
    post = parsed["post"]
    comments = parsed["comments"]
    lines = [f"# {post['title']}", ""]
    meta = f"**r/{post['subreddit']}** · posted by u/{post['author']} · score {post['score']} · {post['num_comments']} comments"
    lines.append(meta)
    if post.get("url"):
        lines.append("")
        lines.append(f"**Source:** {post['url']}")
    if post.get("selftext"):
        lines += ["", post["selftext"]]
    lines += ["", "## Top comments", ""]
    if not comments:
        lines.append("(No comments cleared the score threshold.)")
    for c in comments:
        # depth 0 -> ###, deeper replies nest one heading level down (cap at
        # ###### so markdown stays valid).
        level = min(3 + c["depth"], 6)
        heading = "#" * level
        lines.append(f"{heading} u/{c['author']} (score {c['score']})")
        lines.append(c["body"])
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def extract_reddit_thread(url: str, *,
                           depth_limit: int = DEFAULT_DEPTH_LIMIT,
                           score_threshold: int = DEFAULT_SCORE_THRESHOLD,
                           timeout: int = 20,
                           _fetch=None) -> dict:
    """Fetch + parse + render a Reddit thread into an extract_result dict
    shaped for page_extractor.persist_page_yoink. `_fetch` is an injection
    point for tests (defaults to fetch_thread_json). Returns
    {ok: False, error} on any failure."""
    if not is_reddit_thread_url(url):
        return {"ok": False, "code": "bad_url",
                "error": "Not a Reddit thread URL (expected reddit.com/r/<sub>/comments/...)."}
    fetcher = _fetch or fetch_thread_json
    try:
        raw = fetcher(url, timeout=timeout)
        parsed = parse_thread(raw, depth_limit=depth_limit,
                              score_threshold=score_threshold)
    except ValueError as e:
        return {"ok": False, "code": "fetch_failed", "error": str(e)}
    except Exception as e:  # defensive: malformed tree, etc.
        return {"ok": False, "code": "parse_failed",
                "error": f"Couldn't parse the Reddit thread: {e}"}

    markdown = render_markdown(parsed)
    post = parsed["post"]
    return {
        "ok": True,
        "url": post["url"] or canonical_json_url(url),
        "title": post["title"],
        "markdown": markdown,
        "metadata": {
            "subreddit": post["subreddit"],
            "author": post["author"],
            "score": post["score"],
            "num_comments": post["num_comments"],
            "comments_captured": len(parsed["comments"]),
            "depth_limit": depth_limit,
            "score_threshold": score_threshold,
        },
        "extraction_engine": "reddit-json",
        "extracted_at": _now_iso(),
        "links": [],
        "images": [],
        "screenshot_path": None,
        "comments_captured": len(parsed["comments"]),
    }
