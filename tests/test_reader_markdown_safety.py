"""Saved page Markdown is hostile input. These cases come from web pages an
attacker controls, posted to /extract/page/dom by "Uoink this page".

Save time: page_dom_capture.sanitize_markdown must leave no raw HTML, no
autolink and no link, image or reference target other than http(s) or mailto,
under the CommonMark and GFM rules other Markdown apps render with, in linear
time. Render time: the dashboard reader must never emit a tag or href it did
not write itself, whatever the saved file says.
"""
from __future__ import annotations

import json
from html.parser import HTMLParser
from pathlib import Path
import re
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import page_dom_capture as dom  # noqa: E402

TAG = re.compile(r"<(?=[A-Za-z/!?])")
EVIL = "<img src=x onerror=alert(1)>"
# The checker's own idea of a safe target, kept apart from the code it checks.
TARGET = r"(?:https?://[^\s/?#\\<>`()]|mailto:[^\s\\<>`()])"
SAFE_TAIL = re.compile(TARGET + r"[^\s\\<>`()]*(?:\([^\s\\<>`()]*\)[^\s\\<>`()]*){0,8}\)", re.I)
SAFE_TARGET = re.compile(TARGET, re.I)


def _has_scheme(token):
    from html import unescape
    value = unescape(re.sub(r"\\([!-/:-@\[-`{-~])", r"\1", token))
    value = re.sub(r"[\t\n\r]", "", value).lstrip("".join(map(chr, range(33))))
    return re.match(r"[A-Za-z][A-Za-z0-9+.-]*:", value) is not None

ATTACKS = [
    # inline links and images: case, whitespace, entity, percent and escape tricks
    "[a](javascript:alert(1))",
    "[a](JaVaScRiPt:alert(1))",
    "[a]( javascript:alert(1))",
    "[a](\tjavascript:alert(1))",
    "[a](java\tscript:alert(1))",
    "[a](&#106;avascript:alert(1))",
    "[a](&#x6A;avascript&#58;alert(1))",
    "[a](javascript&colon;alert(1))",
    "[a](%6Aavascript:alert(1))",
    "[a](java\\script:alert(1))",
    "[a](<javascript:alert(1)>)",
    '[a](javascript:alert(1) "title")',
    "[a](\njavascript:alert(1))",
    "[](javascript:alert(1))",
    "![x](data:image/svg+xml,<svg onload=alert(1)>)",
    "![](data:text/html,x)",
    "[a](vbscript:msgbox(1))",
    "[a](file:///etc/passwd)",
    "[a](http:/\\evil.test)",
    "[a](https://x.test/`) " + EVIL + " `)",
    "x]![a](javascript:1)(javascript:2)",
    "[a<](javascript:1)img src=x onerror=alert(1)>",
    # reference definitions, in containers, over two lines, padded
    "[ref]: javascript:alert(1)\n\n[a][ref]",
    "> [ref]: javascript:alert(1)\n\n[a][ref]",
    "- [ref]:\n  javascript:alert(1)\n\n[a][ref]",
    "[re\nf]: javascript:alert(1)\n\n[a][re f]",
    "[ref]: javascript:alert(1)" + " " * 80 + "\n\n[a][ref]",
    "[ref]: <javascript:alert(1)>\n\n[a][ref]",
    "[^1]: javascript:alert(1)",
    "[^1]: &#106;avascript:alert(1)",
    "[^1]: &#32;javascript:alert(1)",
    # raw HTML and autolinks
    "<script>alert(1)</script>",
    EVIL,
    "<javascript:alert(1)>",
    "<a href='javascript:alert(1)'>x</a>",
    "<!-- x --><iframe src=https://x.test>",
    "< img>" + EVIL,
    # code that a renderer would read differently than a naive scan
    "`a\\`" + EVIL + "`",
    "a ` b\nc ` " + EVIL + " `",
    "| `a | b` `" + EVIL + "` |\n| --- | --- |",
    "[a`b]: https://x.test \"`\"\n[x][a`b] " + EVIL + " `",
    "- item\n  ```\n- " + EVIL,
    "   ```\n<b>x</b>\n```\n" + EVIL,
    "> ```\n" + EVIL,
    "````\n```\n<i>code</i>\n````\n" + EVIL,
    "```\ncode\n  ```\n" + EVIL,
    "```\ncode\n\t```\n" + EVIL + "\n```",
    "~~~\ncode\n```\n~~~\n" + EVIL,
    "```js `x`\n" + EVIL + "\n```",
]


def _fenced(md):
    """Line numbers inside column-0 fences, read the way CommonMark reads them."""
    inside, fence = set(), ""
    for n, line in enumerate(md.split("\n")):
        if fence:
            close = re.match(r" {0,3}(`{3,}|~{3,})[ \t]*$", line)
            if close and close[1][0] == fence[0] and len(close[1]) >= len(fence):
                fence = ""
            else:
                inside.add(n)
            continue
        top = re.match(r"(`{3,}|~{3,})(.*)", line)
        if top and not (top[1][0] == "`" and "`" in top[2]):
            fence = top[1]
    return inside


def _unsafe(md):
    """Every way the output could still carry script or a non-web target."""
    problems = []
    inside = _fenced(md)
    for n, line in enumerate(md.split("\n")):
        if n in inside:
            continue
        if re.match(r"(?:[ \t>]|(?:[-*+]|\d{1,9}[.)])(?=[ \t]))*(?:`{3}|~{3})", line) and not re.match(r"(`{3,}|~{3,})", line):
            problems.append(("nested fence", line))
        for m in re.finditer(r"\]\(", line):
            if not SAFE_TAIL.match(line, m.end()):
                problems.append(("link", line))
        for m in re.finditer(r"\]:", line):
            if line[:m.start()].endswith("\\"):
                continue
            label = line[:m.start()].rpartition("[")[2]
            rest = line[m.end():].strip()
            token = rest.split()[0] if rest else ""
            if not (SAFE_TARGET.match(token) or (label.startswith("^") and token and not _has_scheme(token))
                    or len(rest.split()) > 1 and rest.split()[1][0] not in "\"'("):
                problems.append(("definition", line))
        bare = re.sub(r"(`+)(?!`).*?(?<!`)\1(?!`)", "", line) if "|" not in line else line
        if TAG.search(bare):
            problems.append(("tag", line))
    return problems


def test_every_attack_is_neutralized_at_save_time():
    for attack in ATTACKS:
        out = dom.sanitize_markdown(attack)
        assert not _unsafe(out), (attack, out, _unsafe(out))
        fenced = _fenced(out)
        for n, line in enumerate(out.split("\n")):
            if n not in fenced and "`" not in line:
                assert not any(raw in line for raw in (EVIL, "<script", "<svg", "<iframe", "<a ")), (attack, out)


def test_specific_neutralizations():
    s = dom.sanitize_markdown
    assert s("[click](javascript:alert(1)) after") == "click after"
    assert s("![x](data:image/png;base64,AAAA) after") == "x after"
    assert s("[a](https://x.test/`) b `)").startswith("[a]\\(")
    assert s("| `a | b` `<i>` |") == "| `a | b` `&lt;i>` |"
    assert s("a ` b") == "a \\` b"  # a backtick that opens nothing cannot pair on the next line
    assert s("- item\n  ```\n- <b>") == "- item\n  \\`\\`\\`\n- &lt;b>"
    assert s("```\ncode\n  ```\n<b>") == "```\ncode\n```\n&lt;b>"
    assert s("```\nstill open") == "```\nstill open\n```"


def test_real_content_is_kept_as_written():
    s = dom.sanitize_markdown
    for keep in ("Use `List<String>` here, and `a<b` there.",
                 "[ok](https://x.test/a_(b)) and [mail](mailto:hi@x.test)",
                 "![chart](https://x.test/c.png)",
                 "[^1]: See [the source](https://x.test/s) for more.",
                 "[^2]: Note: the ramp was rebuilt.",
                 "[^3]: [Source](https://x.test/s)",
                 "Prices rose 3 < 4 percent, and x<=y.",
                 "```html\n<div class=\"a\">[x](javascript:void(0))</div>\n```",
                 "~~~\n<b>bold</b>\n~~~",
                 "> quoted *text* with `code<T>`",
                 "1. step one\n2. step two"):
        assert s(keep) == keep, keep


def test_sanitizer_is_linear_on_hostile_shapes():
    shapes = ["[" * 200_000, "](" * 100_000, "]:" * 100_000, "`" * 3 + "x\n" * 1, "`a" * 100_000,
              "```x\n" * 40_000, "![" * 100_000, "[a](" * 50_000, "<a" * 100_000, "\\`" * 100_000,
              "[^1]:" * 50_000, "| `x` " * 40_000]
    for shape in shapes:
        start = time.perf_counter()
        dom.sanitize_markdown(shape)
        assert time.perf_counter() - start < 2.0, shape[:20]


def test_wall_padded_with_links_is_still_a_wall_and_thin_is_thin():
    pad = " ".join(f"[Sign in](https://login.example.org/sso/{'x' * 60}/{i})" for i in range(12))
    wall = dom.build_extract_result({"url": "https://news.example.org/a", "title": "A story", "markdown": (
        "Subscribe to continue reading. " + pad + "\n\nAlready a subscriber? Sign in to continue.")})
    assert not wall["ok"] and wall["page_state"] == "wall", wall
    links = "\n".join(f"- [Section {i}](https://news.example.org/{'section/' * 8}{i})" for i in range(9))
    thin = dom.build_extract_result({"url": "https://news.example.org/b", "title": "", "markdown": links})
    assert not thin["ok"] and thin["page_state"] == "thin", thin


class _Tags(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags, self.hrefs = [], []

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, tuple(name for name, _v in attrs)))
        self.hrefs += [v for name, v in attrs if name == "href"]


def test_dashboard_reader_never_renders_page_html_or_script_links():
    from test_dashboard_runthrough_fixes import run_js
    docs = ATTACKS + [dom.sanitize_markdown(a) for a in ATTACKS] + [
        "# Title\n\nBody ![pixel](https://tracker.example.net/p.gif) and ![chart](https://x.test/c.png)",
        "![only](https://tracker.example.net/p.gif)"]
    html = run_js("(() => %s.map((md) => readerMarkdownHtml(md)))()" % json.dumps(docs))
    allowed = {"div": {"class"}, "p": set(), "ul": set(), "li": set(), "h2": set(), "h3": set(), "h4": set(),
               "strong": set(), "em": set(), "code": set(),
               "a": {"href", "data-source-link", "target", "rel"}}
    for md, out in zip(docs, html):
        parser = _Tags()
        parser.feed(out)
        for tag, attrs in parser.tags:
            assert tag in allowed and set(attrs) <= allowed[tag], (md, out)
        assert all(re.match(r"https?://", href) for href in parser.hrefs), (md, out)
        assert "<img" not in out, (md, out)  # no remote image is ever loaded from a saved page


def test_dashboard_reader_shows_escaped_characters_as_characters():
    from test_dashboard_runthrough_fixes import run_js
    out = run_js("readerMarkdownHtml(%s)" % json.dumps(
        "Body\n\nPrices rose 3 &lt; 4 and a " + r"\* b, see \[1\], in `a\*b`, &lt;b>"))
    assert "3 &lt; 4" in out and "a * b" in out and "see [1]" in out, out
    assert r"<code>a\*b</code>" in out and "&lt;b&gt;" in out and "&amp;lt;" not in out, out
