# Scoring and sibling selection adapted from Mozilla Readability 0.6.0.
# https://github.com/mozilla/readability/blob/0.6.0/Readability.js
# Copyright (c) 2010 Arc90 Inc. Licensed under Apache-2.0.
# See third-party-notices/mozilla-readability-APACHE-2.0.txt.
# Modified for Uoink: stdlib HTML parsing, bounded work, metadata and Markdown.
"""Extract an article from already-fetched HTML. This module never uses the network.

This is a limited Python adaptation, not a complete browser DOM or a claim of
Mozilla Readability compatibility. A limit returns a failed attempt so the caller
can try another extractor without publishing a partial parse.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from html import unescape
from html.parser import HTMLParser
import json
import re
import time
from urllib.parse import quote, urljoin, urlsplit

ENGINE = "readability_stdlib"
VERSION = "1"
MAX_INPUT = 8 * 1024 * 1024
MAX_NODES = 40000
MAX_DEPTH = 80
MAX_SECONDS = 2.0
MAX_MARKDOWN = 100000
MIN_TEXT = 200
MIN_BRIEF = 80
_SPACE = re.compile(r"\s+")
_COMMAS = re.compile(r"[,\u060c\ufe50\ufe10\ufe11\u2e41\u2e34\u2e32\uff0c]")
_POSITIVE = re.compile(r"article|body|content|entry|main|post|text|blog|story", re.I)
_NEGATIVE = re.compile(r"banner|comment|footer|masthead|promo|related|share|sidebar|sponsor|widget|advert|(?:^|[-_ ])ads?(?:$|[-_ ])", re.I)
# Keep wall prompts until the chosen content is checked. A wall class elsewhere
# in the document must not decide whether the selected prose is an article.
_UNLIKELY = re.compile(r"breadcrumb|combx|comment|disqus|footer|menu|related|replies|sidebar|social|share|sponsor|advert|popup|cookie|(?:^|[-_ ])ads?(?:$|[-_ ])", re.I)
_VOID = set("area base br col embed hr img input link meta param source track wbr".split())
_HIDDEN = set("script style template noscript svg canvas iframe object".split())
_NOISE = set("header nav footer aside form button input select textarea".split())
_BLOCK = set("article section div p pre blockquote table ul ol li dl h1 h2 h3 h4 h5 h6".split())
_WALL = re.compile(r"(?:sign\s*in|log\s*in|subscribe|subscription|register|create an account)\s+(?:is required|required|to (?:read|continue|view|access|unlock))|(?:subscriber|members?)[- ]only|already a subscriber|unlock (?:this|the|full) article|purchase (?:a )?subscription", re.I)
_JS = re.compile(r"enable javascript|javascript is (?:not available|disabled|required)|requires javascript|please turn on javascript", re.I)
_BYLINE = re.compile(r"(?:^|[\s_-])(?:byline|author|writtenby)(?:$|[\s_-])", re.I)
_LOADER = re.compile(r"^(?:loading(?:\s+(?:the\s+)?(?:reader|article|page|content|app|application|data))?|please wait)(?:[.!\u2026 ]|\bplease wait)*$", re.I)


class ExtractionLimit(ValueError):
    pass


@dataclass(eq=False, slots=True)
class Node:
    tag: str
    attrs: dict = field(default_factory=dict)
    parent: Node | None = None
    children: list = field(default_factory=list)
    excluded: bool = False
    length: int = 0
    links: int = 0
    commas: int = 0
    score: float = 0.0

    @property
    def hint(self):
        return self.attrs.get("class", "") + " " + self.attrs.get("id", "")

    @property
    def density(self):
        return self.links / max(1, self.length)


class Document(HTMLParser):
    def __init__(self, deadline):
        super().__init__(convert_charrefs=True)
        self.root = Node("document")
        self.stack = [self.root]
        self.nodes = [self.root]
        self.deadline = deadline

    def check(self):
        if time.monotonic() > self.deadline:
            raise ExtractionLimit("time limit")

    def handle_starttag(self, tag, attrs):
        self.check()
        if len(self.nodes) >= MAX_NODES or len(self.stack) >= MAX_DEPTH:
            raise ExtractionLimit("HTML structure limit")
        # Common omitted end tags. This is deliberately not an HTML5 DOM.
        if tag in {"p", "li", "tr", "td", "th"} and self.stack[-1].tag == tag:
            self.stack.pop()
        if tag in _BLOCK and self.stack[-1].tag == "p":
            self.stack.pop()
        node = Node(tag, {k: (v or "")[:4096] for k, v in attrs[:80]}, self.stack[-1])
        node.parent.children.append(node)
        self.nodes.append(node)
        if tag not in _VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in _VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        self.check()
        self.stack[-1].children.append(data)


def _text(node, *, raw=False, limit=MAX_INPUT, blocks=False):
    parts, size, stack = [], 0, [node]
    while stack and size < limit:
        item = stack.pop()
        if isinstance(item, str):
            parts.append(item[:limit - size])
            size += len(parts[-1])
        elif not item.excluded:
            if blocks and item.tag in _BLOCK:
                stack.append("\n")
            stack.extend(reversed(item.children))
            if blocks and item.tag in _BLOCK:
                stack.append("\n")
    text = "".join(parts)
    return text if raw else _SPACE.sub(" ", text).strip()


def _value(value):
    if isinstance(value, str):
        return _SPACE.sub(" ", unescape(value)).strip()[:500]
    if isinstance(value, dict):
        return _value(value.get("name"))
    if isinstance(value, list):
        return ", ".join(filter(None, (_value(v) for v in value[:10])))[:500]
    return ""


def _metadata(doc):
    meta, ld = {}, {}
    budget = 128000
    for node in doc.nodes:
        if node.tag == "meta":
            key = (node.attrs.get("property") or node.attrs.get("name") or "").lower()
            if key and len(meta) < 100:
                meta[key] = _value(node.attrs.get("content"))
        if node.tag == "title":
            meta.setdefault("html_title", _text(node, limit=500))
        if node.tag == "script" and node.attrs.get("type", "").lower() == "application/ld+json" and budget > 0:
            text = _text(node, raw=True, limit=budget + 1)
            budget -= len(text)
            if budget < 0:
                continue
            try:
                pending = [json.loads(text)]
                for _ in range(500):
                    if not pending:
                        break
                    value = pending.pop()
                    if isinstance(value, list):
                        pending.extend(value[:100])
                    elif isinstance(value, dict):
                        types = value.get("@type", [])
                        types = [types] if isinstance(types, str) else types
                        if isinstance(types, list) and any(str(t).endswith(("Article", "Posting", "Report")) for t in types):
                            ld.setdefault("title", _value(value.get("headline") or value.get("name")))
                            ld.setdefault("author", _value(value.get("author")))
                            ld.setdefault("published_date", _value(value.get("datePublished")))
                            ld.setdefault("site_name", _value(value.get("publisher")))
                        if "@graph" in value:
                            pending.append(value["@graph"])
            except (ValueError, RecursionError, TypeError):
                pass
    def first(*keys):
        return next((meta[k] for k in keys if meta.get(k)), None)
    result = {
        "title": ld.get("title") or first("og:title", "twitter:title", "title", "html_title"),
        "author": ld.get("author") or first("author", "article:author", "byl", "byline", "dc.creator"),
        "published_date": ld.get("published_date") or first("article:published_time", "datepublished", "date", "pubdate", "dc.date", "dcterms.created"),
        "site_name": ld.get("site_name") or first("og:site_name", "application-name"),
    }
    bylines = []
    for node in doc.nodes:
        if (not result["author"] and node.tag not in {"html", "body", "main", "article"}
                and node.tag not in _HIDDEN and _BYLINE.search(node.hint)):
            text = _text(node, limit=201)
            if text and len(text) <= 200:
                bylines.append(text)
        if not result["title"] and node.tag == "h1":
            result["title"] = _text(node, limit=500) or None
    if bylines:
        result["author"] = min(bylines, key=len)
    return {k: v for k, v in result.items() if v}


def _prepare(doc):
    for node in doc.nodes:
        a = node.attrs
        hidden = ("hidden" in a or a.get("aria-hidden") == "true" or
                  re.search(r"display\s*:\s*none|visibility\s*:\s*hidden", a.get("style", ""), re.I))
        noise = (node.tag in _NOISE or a.get("role") in {"navigation", "complementary", "menu", "contentinfo"}
                 or _UNLIKELY.search(node.hint))
        node.excluded = bool((node.parent and node.parent.excluded) or hidden or noise or node.tag in _HIDDEN or node.tag == "head")
    for node in reversed(doc.nodes):
        if node.excluded:
            continue
        for child in node.children:
            if isinstance(child, str):
                text = _SPACE.sub(" ", child).strip()
                node.length += len(text)
                node.commas += len(_COMMAS.findall(text))
            elif not child.excluded:
                node.length += child.length
                node.links += child.links
                node.commas += child.commas
        if node.tag == "a":
            node.links = node.length


def _choose(doc):
    candidates = set()
    for node in doc.nodes:
        if node.excluded or node.length < 25:
            continue
        is_text = node.tag in {"p", "pre", "td", "li", "blockquote"}
        if node.tag == "div":
            is_text = not any(isinstance(c, Node) and c.tag in _BLOCK for c in node.children)
        if not is_text:
            continue
        score = (2 + node.commas + min(node.length // 100, 3)) * (1 - node.density)
        parent = node.parent
        for divisor in (1, 2):
            if parent is None:
                break
            if parent not in candidates:
                parent.score = (5 if parent.tag in {"div", "article", "main"} else 0)
                parent.score += 25 * bool(_POSITIVE.search(parent.hint))
                parent.score -= 25 * bool(_NEGATIVE.search(parent.hint))
                candidates.add(parent)
            parent.score += score / divisor
            parent = parent.parent
    # Document order breaks ties, independent of object hashes.
    ranked = [n for n in doc.nodes if n in candidates and n.tag not in {"document", "html"} and n.density < 0.6]
    for node in ranked:
        node.score *= 1 - node.density
    if not ranked:
        return []
    best = max(ranked, key=lambda n: n.score)
    # Lift one-child wrappers to recover adjacent headings and later sections.
    while best.parent and best.parent.tag not in {"document", "html", "body"}:
        siblings = [n for n in best.parent.children if isinstance(n, Node) and not n.excluded and n.length]
        if len(siblings) != 1:
            break
        best = best.parent
    siblings = best.parent.children if best.parent else [best]
    threshold = max(10, best.score * .2)
    chosen = []
    for node in siblings:
        if not isinstance(node, Node) or node.excluded:
            continue
        bonus = best.score * .2 if node.attrs.get("class") and node.attrs.get("class") == best.attrs.get("class") else 0
        prose = node.tag == "p" and node.length > 80 and node.density < .25
        heading = node.tag in {"h1", "h2"} and node.density == 0
        if node is best or node.score + bonus >= threshold or prose or heading:
            chosen.append(node)
    return chosen


def safe_link(href, url):
    if not href or any(ord(c) < 32 for c in href) or "\\" in href:
        return None
    try:
        target = urljoin(url, href.strip())
        parsed = urlsplit(target)
        if (parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname
                or parsed.username is not None or parsed.password is not None):
            return None
        return quote(target, safe=":/?#@!$&'*+,;=%")
    except ValueError:
        return None


def _escape(text):
    text = _SPACE.sub(" ", text)
    return re.sub(r"([\\`*_[\]])", r"\\\1", text).replace("<", "&lt;").replace(">", "&gt;")


class Markdown:
    def __init__(self, url, check):
        self.url, self.check = url, check
        self.links = []
        self.truncated = False

    def cap(self, text):
        if len(text) > MAX_MARKDOWN:
            self.truncated = True
        return text[:MAX_MARKDOWN]

    def render(self, node):
        self.check()
        if isinstance(node, str):
            return _escape(node)
        if node.excluded:
            return ""
        tag = node.tag
        if tag == "pre":
            code = _text(node, raw=True, limit=MAX_MARKDOWN).strip("\n")
            fence = "`" * max(3, 1 + max((len(m[0]) for m in re.finditer(r"`+", code)), default=0))
            return self.cap(f"\n\n{fence}\n{code}\n{fence}\n\n")
        if tag == "table":
            rows, stack = [], list(reversed(node.children))
            while stack:
                child = stack.pop()
                if not isinstance(child, Node) or child.excluded:
                    continue
                if child.tag == "tr":
                    cells = [self.render(c).strip().replace("|", "\\|").replace("\n", " ")
                             for c in child.children if isinstance(c, Node) and c.tag in {"th", "td"}]
                    if cells:
                        rows.append(cells)
                elif child.tag != "table":
                    stack.extend(reversed(child.children))
            if not rows:
                return ""
            width = min(20, max(map(len, rows)))
            if any(len(r) > width for r in rows):
                self.truncated = True
            lines = ["| " + " | ".join((r + [""] * width)[:width]) + " |" for r in rows]
            lines.insert(1, "| " + " | ".join(["---"] * width) + " |")
            return self.cap("\n\n" + "\n".join(lines) + "\n\n")
        parts, size = [], 0
        for child in node.children:
            if (isinstance(child, str) and child.isspace() and
                    tag in {"article", "main", "section", "div", "body", "ul", "ol", "header"}):
                continue
            part = self.render(child)
            if not part:
                continue
            if parts and parts[-1].endswith("\n\n") and part.startswith("\n"):
                part = part.lstrip("\n")
            parts.append(part)
            size += len(part)
            if size > MAX_MARKDOWN:
                self.truncated = True
                break
        inner = self.cap("".join(parts))
        if tag == "a":
            href = safe_link(node.attrs.get("href"), self.url)
            if href and inner.strip():
                if len(self.links) < 50 and {"href": href} not in self.links:
                    self.links.append({"href": href})
                return self.cap(f"[{inner.strip()}]({href})")
        if tag == "code":
            text = _text(node, limit=MAX_MARKDOWN)
            fence = "`" * (1 + max((len(m[0]) for m in re.finditer(r"`+", text)), default=0))
            padding = " " if text.startswith("`") or text.endswith("`") else ""
            return self.cap(f"{fence}{padding}{text}{padding}{fence}")
        if tag in {"strong", "b", "em", "i"}:
            mark = "**" if tag in {"strong", "b"} else "*"
            return self.cap(mark + inner.strip() + mark)
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            return self.cap("\n\n" + "#" * int(tag[1]) + " " + inner.strip() + "\n\n")
        if tag == "blockquote":
            return self.cap("\n\n" + "\n".join("> " + line for line in inner.strip().splitlines()) + "\n\n")
        if tag == "li":
            marker = "1. " if node.parent and node.parent.tag == "ol" else "- "
            return self.cap("\n" + marker + inner.strip().replace("\n", "\n   ") + "\n")
        if tag in _BLOCK or tag in {"main", "header"}:
            return self.cap("\n\n" + inner.strip() + "\n\n")
        if tag == "br":
            return "\n"
        if tag == "hr":
            return "\n\n---\n\n"
        return inner


def _solid_prose(text):
    return (len(text) >= MIN_BRIEF and len(text.split()) >= 12
            and sum(c.isalpha() for c in text) >= len(text) * .6
            and bool(re.search(r"[.!?]", text)))


def text_diagnostic(text, *, script_backed=False, allow_short=False):
    """Judge chosen prose, not page chrome. Never echo page data in diagnostics."""
    # Count distinct sentences/blocks so repeated account copy cannot drown out
    # a wall prompt. Keep block boundaries for headings and Markdown fallbacks.
    units = {}
    for part in re.split(r"(?<=[.!?])\s+|[\r\n]+", text or ""):
        part = _SPACE.sub(" ", part).strip(" \t#>*-_").casefold()
        if part:
            units[part] = units.get(part, 0) + 1

    def substance(pattern):
        # A mention inside a report is not a prompt. Measure phrase coverage,
        # with no length ceiling, including prompts repeated without punctuation.
        prompts = {u for u in units if sum(len(m[0]) for m in pattern.finditer(u)) >= len(u) * .35}
        other = sum(len(u) for u in units if u not in prompts)
        return prompts and other < MIN_TEXT and (len(prompts) >= 2 or sum(map(len, prompts)) >= other * .5)

    text = _SPACE.sub(" ", text or "").strip()
    if substance(_WALL):
        return "article body not found: login or paywall page"
    if substance(_JS):
        return "article body not found: empty JavaScript page"
    if script_backed:
        total = sum(len(u) * count for u, count in units.items())
        repeated = any(count >= 3 and len(u) <= 160 and len(u) * count >= total * .8
                       for u, count in units.items())
        loader = bool(units) and all(_LOADER.fullmatch(u) for u in units)
        if len(text) < 40 or repeated or loader:
            return "article body not found: empty JavaScript page"
    if len(text) < MIN_TEXT and not (allow_short and _solid_prose(text)):
        return "article body not found: too little main text"
    return None


def extract(html: bytes | str, url: str) -> dict:
    """Return bounded Markdown and attribution; accept HTML, never a URL fetch."""
    result = {"ok": False, "extraction_engine": ENGINE, "extraction_version": VERSION,
              "url": url, "markdown": "", "metadata": {}, "links": [], "images": [],
              "screenshot_path": None, "article_status": "not_found"}
    doc = Document(time.monotonic() + MAX_SECONDS)
    try:
        if len(html) > MAX_INPUT:
            raise ExtractionLimit("input size limit")
        if isinstance(html, bytes):
            # Honor common HTML charset declarations without third-party sniffers.
            declaration = re.search(br'charset\s*=\s*["\x27]?([a-zA-Z0-9_-]+)', html[:4096])
            encoding = declaration[1].decode("ascii") if declaration else "utf-8-sig"
            try:
                html = html.decode(encoding, errors="replace")
            except (LookupError, UnicodeError):
                html = html.decode("utf-8", errors="replace")
        for offset in range(0, len(html), 16384):
            doc.check()
            doc.feed(html[offset:offset + 16384])
        doc.close()
        result["metadata"] = _metadata(doc)
        result["title"] = result["metadata"].get("title")
        _prepare(doc)
        chosen = _choose(doc)
        length = sum(n.length for n in chosen)
        result["article_text_length"] = length
        text = "\n".join(_text(n, raw=True, blocks=True) for n in chosen)
        # A titled brief needs a prose paragraph, not just a heading or menu.
        brief = False
        if length < MIN_TEXT and result["title"]:
            chosen_set = set(chosen)
            in_content = set()
            for node in doc.nodes:
                if not node.excluded and (node in chosen_set or node.parent in in_content):
                    in_content.add(node)
            brief = any(n.tag == "p" and n.density < .25 and _solid_prose(_text(n)) for n in in_content)
        diagnostic = text_diagnostic(text, script_backed=any(n.tag == "script" for n in doc.nodes),
                                     allow_short=brief)
        if diagnostic:
            result.update(code="article_body_not_found", diagnostic=diagnostic, error=diagnostic)
            return result
        base = next((n.attrs["href"] for n in doc.nodes if n.tag == "base" and "href" in n.attrs), None)
        renderer = Markdown(safe_link(base, url) or url, doc.check)
        markdown = renderer.cap("".join(renderer.render(n) for n in chosen)).strip()
        doc.check()
        result.update(ok=True, markdown=markdown, links=renderer.links,
                      article_status="short_article" if length < MIN_TEXT else "found",
                      output_truncated=renderer.truncated)
        if length < MIN_TEXT:
            result["diagnostic"] = "short article"
        return result
    except ExtractionLimit as exc:
        diagnostic = "article body not found: " + str(exc)
        result.update(code="article_extraction_limit", diagnostic=diagnostic, error=diagnostic)
        return result
