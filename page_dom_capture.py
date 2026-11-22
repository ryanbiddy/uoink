"""Uoink this page: persist the page the user sees, read in their own tab.

The extension runs Defuddle plus extension/lib/page-capture.js in the tab the
user clicked (after JavaScript ran, with the user's own session), and posts
{url, title, author, published, site, markdown, ...} to /extract/page/dom.
This module owns the helper half: validate and bound that payload, refuse a
wall or an empty tab honestly, and shape an extract_result that
page_extractor.persist_page_yoink saves like any other web page. The page
text stays on this computer. The helper only fetches a thumbnail when the
lead image and any redirects stay on the page's site.

Transport (route, token, allowlist gate, body cap) is owned by server.py.
"""
from __future__ import annotations

from datetime import datetime, timezone
from html import unescape
import re

import article_extractor
import page_extractor

ENGINE = "defuddle"
ENGINE_VERSION = "0.19.6"
CAPTURE_SOURCE = page_extractor.DOM_CAPTURE_SOURCE
MAX_BODY_BYTES = 2 * 1024 * 1024
MAX_MARKDOWN = 400_000

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")

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


# ---- Page text is hostile -----------------------------------------------------
# sanitize_markdown is the save-time guarantee for the Markdown the extension
# posts, held to the CommonMark and GFM rules that Obsidian, GitHub and VS Code
# render with (the dashboard's own renderer escapes everything and links only
# http(s), so it is safe on its own):
# - no raw HTML and no autolink: every "<" that could open a tag becomes &lt;,
#   except inside code;
# - links and images only to http(s) or mailto, in the form page-capture.js
#   writes ([text](url): no title, no spaces); any other "](" becomes "]\(",
#   which every renderer shows as text;
# - no link reference definition unless its target is http(s) or mailto (a
#   footnote may start with a plain word);
# - code fences only at column 0, closed by the same fence; every other line
#   that could open or close a fence is escaped, so no renderer disagrees
#   about where code starts and ends;
# - inline code is left as written only where its pairing is certain: each
#   backtick run that pairs with nothing is escaped, so no code span can run
#   onto the next line, and a line with "|" (maybe a table row, which GFM
#   splits on "|" before it reads code) gets no exception.
# Each line is read once, left to right; nothing backtracks.
_TOP_FENCE = re.compile(r"(`{3,}|~{3,})(.*)")
_CLOSE_FENCE = re.compile(r" {0,3}(`{3,}|~{3,})[ \t]*$")
_ANY_FENCE = re.compile(r"((?:[ \t>]|(?:[-*+]|\d{1,9}[.)])(?=[ \t]))*)(`{3}|~{3})")
_INFO = re.compile(r"[\w+#.-]{0,30}")
_TICKS = re.compile(r"`+")
_BRACKET = re.compile(r"[\[\]]")
_TARGET = r"(?:https?://[^\s/?#\\<>`()]|mailto:[^\s\\<>`()])"
_SAFE_TAIL = re.compile(_TARGET + r"[^\s\\<>`()]*(?:\([^\s\\<>`()]*\)[^\s\\<>`()]*){0,8}\)", re.I)
_SAFE_TARGET = re.compile(_TARGET, re.I)
_SIMPLE_TAIL = re.compile(r"[^\s`\[\]()]{0,2048}(?:\([^\s`\[\]()]{0,2048}\)[^\s`\[\]()]{0,2048}){0,4}\)")
_DEF_TOKEN = re.compile(r"[ \t]{0,64}(\S{0,512})[ \t]{0,64}(.?)")
_TAG_OPEN = re.compile(r"<(?=[A-Za-z/!?]|$)")


def _backslashes_before(line: str, index: int) -> int:
    count = 0
    while index - count - 1 >= 0 and line[index - count - 1] == "\\":
        count += 1
    return count


def _code_spans(line: str):
    """CommonMark code spans on one line, and the backtick runs that open none.
    A run after an odd number of backslashes opens one backtick later; its
    closer is the next raw run of the same length."""
    runs = []
    for match in _TICKS.finditer(line):
        runs.append((match.start(), match.end(), _backslashes_before(line, match.start()) % 2))
    by_length, pointer = {}, {}
    for index, (start, end, _escaped) in enumerate(runs):
        by_length.setdefault(end - start, []).append(index)
    spans, loose, i = [], [], 0
    while i < len(runs):
        start, end, escaped = runs[i]
        start += escaped
        length = end - start
        if not length:
            i += 1
            continue
        same, p = by_length.get(length, []), pointer.get(length, 0)
        while p < len(same) and same[p] <= i:
            p += 1
        pointer[length] = p
        if p < len(same):
            spans.append((start, runs[same[p]][1]))
            i = same[p] + 1
        else:
            loose.append((start, end))
            i += 1
    return spans, loose


def _definition_ok(line: str, j: int, opened: int) -> bool:
    """Is the "]:" at j harmless? "[label]: target" defines a link wherever it
    sits (in a quote, a list, a label over two lines), unless words follow."""
    if opened < 0:
        return False  # the label started on an earlier line: cannot judge it
    label = line[opened + 1:j]
    if "`" in label:
        return False  # a renderer would read the label past what looks like code
    token, after = _DEF_TOKEN.match(line, j + 2).groups()
    if not token or len(token) >= 512:
        return False  # the target may be on the next line, or too long to judge
    if _SAFE_TARGET.match(token):
        return True
    if label.startswith("^") and not re.search(r"\s", label) and not _has_scheme(token):
        return True  # a footnote's first word: a relative link at worst
    return bool(after.strip()) and after not in "\"'("  # more words follow: not a definition


def _has_scheme(token: str) -> bool:
    # What a browser would read: entities and escapes decoded, tabs and
    # newlines dropped, leading spaces and controls stripped.
    value = unescape(re.sub(r"\\([!-/:-@\[-`{-~])", r"\1", token))
    value = re.sub(r"[\t\n\r]", "", value).lstrip("".join(map(chr, range(33))))
    return re.match(r"[A-Za-z][A-Za-z0-9+.-]*:", value) is not None


def _sanitize_line(line: str) -> str:
    fence = _ANY_FENCE.match(line)
    if fence:
        line = line[:fence.end(1)] + "\\" + line[fence.end(1):]
    spans, loose = _code_spans(line)
    code = [] if "|" in line else spans
    # Edits are (start, text to insert, end of text to drop there).
    edits = [(k, "\\", k) for start, end in loose for k in range(start, end)]
    opened, s = -1, 0
    for match in _BRACKET.finditer(line):
        j = match.start()
        if line[j] == "[":
            if _backslashes_before(line, j) % 2 == 0:
                opened = j
            continue
        while s < len(code) and code[s][1] <= j:
            s += 1
        in_code = s < len(code) and code[s][0] <= j
        if line.startswith(":", j + 1) and _backslashes_before(line, j) % 2 == 0:
            # Definitions are read before code spans, so code does not shield them.
            if not _definition_ok(line, j, opened):
                edits.append((j, "\\", j))
        elif line.startswith("(", j + 1) and not in_code and not _SAFE_TAIL.match(line, j + 2):
            label = line[opened + 1:j] if opened >= 0 else ""
            tail = _SIMPLE_TAIL.match(line, j + 2) if label.strip() and "`" not in label else None
            if tail:
                # Keep the words, drop the target: "[click](javascript:...)" -> "click".
                start = opened - 1 if opened and line[opened - 1] == "!" else opened
                edits.append((start, "", opened + 1))
                edits.append((j, "", tail.end()))
            else:
                edits.append((j + 1, "\\", j + 1))  # "]\(" is text to every renderer
        opened = -1
    edits.sort(key=lambda edit: edit[0])
    cuts = sorted({0, len(line), *(x for span in code for x in span), *(x for k, _t, end in edits for x in (k, end))})
    out, e, s, skip = [], 0, 0, 0
    for a, b in zip(cuts, cuts[1:]):
        while e < len(edits) and edits[e][0] == a:
            out.append(edits[e][1])
            skip = max(skip, edits[e][2])
            e += 1
        if a < skip:
            continue
        while s < len(code) and code[s][1] <= a:
            s += 1
        piece = line[a:b]
        # A "<" at the end of a piece meets whatever follows a dropped target: escape it too.
        out.append(piece if s < len(code) and code[s][0] <= a else _TAG_OPEN.sub("&lt;", piece))
    out.extend(text for _k, text, _end in edits[e:])
    return "".join(out)


def sanitize_markdown(markdown: str) -> str:
    """Page Markdown that no Markdown renderer can turn into script, raw HTML
    or a non-web link. A code block cut off at the end gets its closing fence."""
    out, fence = [], ""
    for line in str(markdown or "").split("\n"):
        if fence:
            close = _CLOSE_FENCE.match(line)
            if close and close[1][0] == fence[0] and len(close[1]) >= len(fence):
                out.append(fence)
                fence = ""
            else:
                out.append(line)
            continue
        top = _TOP_FENCE.match(line)
        if top and not (top[1][0] == "`" and "`" in top[2]):
            fence = top[1]
            out.append(fence + _INFO.match(top[2].strip())[0])
            continue
        out.append(_sanitize_line(line))
    if fence:
        out.append(fence)
    return "\n".join(out)


_PROSE_TAIL = re.compile(r"\]\((?:https?://|mailto:)[^\s\\<>`()]*\)", re.I)
_PROSE_IMAGE = re.compile(r"!\[[^\[\]\n]*\]")
_PROSE_MARKS = re.compile(r"\[\^[^\s\[\]]*\]:?|[\[\]*_`~|\\]+")


def _is_rule_line(line: str) -> bool:
    """A table or thematic rule: only whitespace, |, : and -, with "---" in it.
    Checked in linear time; a regex here was cubic on a long run of dashes."""
    return "---" in line and all(c.isspace() or c in "|:-" for c in line)


def prose(markdown: str) -> str:
    """The words a reader sees, one block per line: link text without its URL,
    no image, fence line or table rule. Input for the wall and thin checks."""
    lines = []
    for line in markdown.split("\n"):
        if _TOP_FENCE.match(line) or _is_rule_line(line):
            continue
        text = _PROSE_IMAGE.sub(" ", _PROSE_TAIL.sub("]", line))
        lines.append(unescape(_PROSE_MARKS.sub(" ", text)).strip())
    return "\n".join(line for line in lines if line)


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
    text = _CONTROL.sub("", raw[:MAX_MARKDOWN].replace("\r\n", "\n").replace("\r", "\n"))
    markdown = re.sub(r"\n{3,}", "\n\n", sanitize_markdown(text)).strip()
    title = _text(payload.get("title"), 500)
    plain = prose(markdown)
    diagnostic = article_extractor.text_diagnostic(plain, allow_short=bool(title))
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
    length = len(re.sub(r"\s+", " ", plain))
    short = length < article_extractor.MIN_TEXT
    result = {
        "ok": True, "url": url, "title": title or url, "markdown": markdown, "metadata": metadata,
        "extraction_engine": ENGINE, "extraction_version": engine_version,
        "fetched_at": now, "fetched_url": url, "extracted_at": now,
        "extraction_attempts": [{"engine": ENGINE, "version": engine_version, "status": "ok", "diagnostic": ""}],
        "article_status": "short_article" if short else "found", "article_text_length": length,
        "output_truncated": truncated, "links": [], "images": [], "screenshot_path": None,
    }
    if short:
        result["diagnostic"] = "short article"
    if article_extractor.maybe_paywall_preview(plain):
        result.update(preview_hint=True, diagnostic="short article: may be a paywall preview")
    return result
