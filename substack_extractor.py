"""Substack post extractor (Q-01, v3.3 source expansion, D-6 priority #1).

Captures a Substack article or newsletter post via the publication's public
JSON API (`https://<pub>.substack.com/api/v1/posts/<slug>`, no key, no
login), converts the body HTML to markdown, and returns an
`extract_result` in page_extractor's shape so
page_extractor.persist_page_yoink can land it as a yoink with
source_type='substack_post'.

Free posts only, honestly: when the API says the post is for paid
subscribers (audience != "everyone", or a paywalled/truncated body), the
extractor refuses with copy that says exactly that instead of saving a
teaser that pretends to be the article. Custom-domain publications are out
of scope for this pass (nothing in the URL identifies them as Substack);
the failure copy says so.

fetch is separated from parse/render so everything below the network is
unit-testable against fixtures. Transport (HTTP route + flag gate) is
owned by server.py. House pattern: reddit_extractor.py.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser

SOURCE_TYPE = "substack_post"
USER_AGENT = "uoink/1.0 (local corpus tool; +https://uoink.app)"
MAX_BODY_CHARS = 400_000  # hard cap so a pathological page can't blow up

_POST_RE = re.compile(
    r"^https?://([a-z0-9-]+)\.substack\.com/p/([a-z0-9-]+)",
    re.IGNORECASE,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z")


def is_substack_post_url(url: str) -> bool:
    m = _POST_RE.match((url or "").strip())
    # www. is the substack.com homepage, not a publication
    return bool(m) and m.group(1).lower() != "www"


def api_url(url: str) -> str | None:
    """Map a post URL to the publication's public JSON API endpoint."""
    m = _POST_RE.match((url or "").strip())
    if not m or m.group(1).lower() == "www":
        return None
    pub, slug = m.group(1).lower(), m.group(2).lower()
    return f"https://{pub}.substack.com/api/v1/posts/{slug}"


def fetch_post_json(url: str, *, timeout: int = 20) -> dict:
    """GET the post JSON. Raises ValueError with actionable copy on the
    failure modes Substack returns."""
    target = api_url(url)
    if not target:
        raise ValueError("not a Substack post URL")
    req = urllib.request.Request(target, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise ValueError("Substack returned 404. The post was removed, "
                             "the slug is wrong, or this publication moved "
                             "to a custom domain (not supported yet).")
        if e.code == 429:
            raise ValueError("Substack is rate-limiting (429). Wait a minute "
                             "and try again.")
        raise ValueError(f"Substack returned HTTP {e.code}.")
    except urllib.error.URLError as e:
        raise ValueError(f"Couldn't reach Substack: {e.reason}")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise ValueError("Substack didn't return JSON (block page or outage).")
    if not isinstance(data, dict):
        raise ValueError("Unexpected Substack response shape.")
    return data


# ---- HTML -> markdown ------------------------------------------------------

class _MarkdownHTMLParser(HTMLParser):
    """Small, honest HTML->markdown converter for Substack post bodies.
    Handles the structures Substack actually emits (headings, paragraphs,
    lists, blockquotes, links, emphasis, code, images) and flattens
    anything else to its text."""

    _BLOCK_TAGS = {"p", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol",
                   "blockquote", "pre", "div", "figure", "hr", "li"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._list_stack: list[str] = []
        self._quote_depth = 0
        self._href: str | None = None
        self._in_pre = False
        self._suppress = 0  # inside script/style

    # -- helpers --
    def _newline_block(self):
        while self.parts and self.parts[-1] == "":
            self.parts.pop()
        if self.parts:
            self.parts.append("")

    def _emit(self, text: str):
        if self._suppress:
            return
        if self._quote_depth and (not self.parts or self.parts[-1] == ""):
            self.parts.append("> " * self._quote_depth + text)
        elif self.parts and self.parts[-1] != "":
            self.parts[-1] += text
        else:
            self.parts.append(text)

    # -- parser hooks --
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ("script", "style"):
            self._suppress += 1
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._newline_block()
            self._emit("#" * int(tag[1]) + " ")
        elif tag == "p":
            self._newline_block()
        elif tag == "br":
            self.parts.append("")
        elif tag == "ul":
            self._newline_block()
            self._list_stack.append("-")
        elif tag == "ol":
            self._newline_block()
            self._list_stack.append("1.")
        elif tag == "li":
            self._newline_block()
            marker = self._list_stack[-1] if self._list_stack else "-"
            indent = "  " * max(0, len(self._list_stack) - 1)
            self._emit(f"{indent}{marker} ")
        elif tag == "blockquote":
            self._newline_block()
            self._quote_depth += 1
        elif tag == "pre":
            self._newline_block()
            self._emit("```")
            self.parts.append("")
            self._in_pre = True
        elif tag == "code" and not self._in_pre:
            self._emit("`")
        elif tag in ("strong", "b"):
            self._emit("**")
        elif tag in ("em", "i"):
            self._emit("*")
        elif tag == "a":
            self._href = attrs.get("href")
            self._emit("[")
        elif tag == "img":
            alt = (attrs.get("alt") or "image").strip() or "image"
            src = attrs.get("src") or ""
            self._newline_block()
            self._emit(f"![{alt}]({src})")
            self._newline_block()
        elif tag == "hr":
            self._newline_block()
            self._emit("---")
            self._newline_block()

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._suppress = max(0, self._suppress - 1)
        elif tag in ("p", "h1", "h2", "h3", "h4", "h5", "h6", "li",
                     "figure", "div"):
            self._newline_block()
        elif tag in ("ul", "ol"):
            if self._list_stack:
                self._list_stack.pop()
            self._newline_block()
        elif tag == "blockquote":
            self._quote_depth = max(0, self._quote_depth - 1)
            self._newline_block()
        elif tag == "pre":
            self._in_pre = False
            self._emit("```")
            self._newline_block()
        elif tag == "code" and not self._in_pre:
            self._emit("`")
        elif tag in ("strong", "b"):
            self._emit("**")
        elif tag in ("em", "i"):
            self._emit("*")
        elif tag == "a":
            href = self._href
            self._href = None
            self._emit(f"]({href})" if href else "]")

    def handle_data(self, data):
        if self._suppress:
            return
        if self._in_pre:
            self._emit(data)
            return
        text = re.sub(r"\s+", " ", data)
        if text.strip() or (self.parts and self.parts[-1] != ""):
            self._emit(text if text.strip() else " ")

    def markdown(self) -> str:
        lines = [part.rstrip() for part in self.parts]
        out: list[str] = []
        for line in lines:
            if line == "" and out and out[-1] == "":
                continue
            out.append(line)
        return "\n".join(out).strip()


def html_to_markdown(body_html: str) -> str:
    parser = _MarkdownHTMLParser()
    parser.feed(unescape_safe(body_html)[:MAX_BODY_CHARS])
    parser.close()
    return parser.markdown()


def unescape_safe(html: str) -> str:
    # Substack double-escapes entities inside code blocks sometimes; a
    # single unescape round keeps prose readable without corrupting code.
    return html if "&" not in (html or "") else unescape(html)


# ---- parse ------------------------------------------------------------------

def parse_post(data: dict) -> dict:
    """Pure parse of the API payload. Raises ValueError with honest copy
    when the post is paid-only or the body is missing."""
    audience = (data.get("audience") or "").strip().lower()
    paywalled = bool(data.get("should_show_paywall"))
    body_html = (data.get("body_html") or "").strip()
    if audience not in ("", "everyone") or paywalled:
        raise ValueError("This post is for paid subscribers. Uoink only "
                         "captures free Substack posts, and saving the "
                         "teaser would pretend to be the article.")
    if not body_html:
        raise ValueError("Substack answered without the post body. If this "
                         "post is subscriber-only, that's why; otherwise "
                         "try again in a minute.")
    bylines = data.get("publishedBylines") or []
    author = ""
    if isinstance(bylines, list) and bylines and isinstance(bylines[0], dict):
        author = (bylines[0].get("name") or "").strip()
    return {
        "title": (data.get("title") or "Untitled Substack post").strip(),
        "subtitle": (data.get("subtitle") or "").strip(),
        "author": author,
        "post_date": (data.get("post_date") or "").strip(),
        "canonical_url": (data.get("canonical_url") or "").strip(),
        "wordcount": int(data.get("wordcount") or 0),
        "type": (data.get("type") or "newsletter").strip(),
        "body_html": body_html,
    }


def render_markdown(post: dict, source_url: str) -> str:
    lines = [f"# {post['title']}", ""]
    if post["subtitle"]:
        lines += [f"*{post['subtitle']}*", ""]
    meta = " · ".join(filter(None, [
        f"by {post['author']}" if post["author"] else "",
        post["post_date"][:10] if post["post_date"] else "",
        f"{post['wordcount']} words" if post["wordcount"] else "",
    ]))
    if meta:
        lines += [meta, ""]
    lines += [f"**Source:** {post['canonical_url'] or source_url}", "", ""]
    lines.append(html_to_markdown(post["body_html"]))
    return "\n".join(lines).strip() + "\n"


def extract_substack_post(url: str, *, timeout: int = 20, _fetch=None) -> dict:
    """Fetch + parse + render a Substack post into an extract_result dict
    shaped for page_extractor.persist_page_yoink. `_fetch` is the test
    injection point. Returns {ok: False, code, error} on any failure;
    paid posts come back as code='paywalled'."""
    if not is_substack_post_url(url):
        return {"ok": False, "code": "bad_url",
                "error": "Not a Substack post URL (expected "
                         "<publication>.substack.com/p/<slug>; custom "
                         "domains aren't supported yet)."}
    fetcher = _fetch or fetch_post_json
    try:
        data = fetcher(url, timeout=timeout)
    except ValueError as e:
        return {"ok": False, "code": "fetch_failed", "error": str(e)}
    try:
        post = parse_post(data)
    except ValueError as e:
        message = str(e)
        code = "paywalled" if "paid subscribers" in message else "parse_failed"
        return {"ok": False, "code": code, "error": message}
    except Exception as e:  # defensive: malformed payloads
        return {"ok": False, "code": "parse_failed",
                "error": f"Couldn't parse the Substack post: {e}"}

    markdown = render_markdown(post, url)
    return {
        "ok": True,
        "url": post["canonical_url"] or url.split("?", 1)[0],
        "title": post["title"],
        "markdown": markdown,
        "metadata": {
            "author": post["author"],
            "subtitle": post["subtitle"],
            "post_date": post["post_date"],
            "wordcount": post["wordcount"],
            "post_type": post["type"],
        },
        "extraction_engine": "substack-api",
        "extracted_at": _now_iso(),
        "links": [],
        "images": [],
        "screenshot_path": None,
    }
