"""UI re-haul foundation: tokens, bundled fonts, light/dark themes.

The re-haul SPEC (handoff/ui-rehaul-2026-10-15/SPEC.md, "Tokens") puts its
token table in assets/brand/tokens.css and extension/brand/tokens.css: light
is the default, dark applies under prefers-color-scheme: dark, and the old
token names keep working. Inter, Bungee and JetBrains Mono ship as local
font files with their SIL OFL texts, and no page loads fonts from the
network (the dashboard must work offline; the popup must not call Google on
every open). The files are the uoink.app site's own copies (site/app/fonts),
which are WOFF rather than the woff2 the SPEC mentions; either web format is
accepted as long as the bytes match the declared format. Keyboard focus
shows a 2px rust ring offset 2px, and prefers-reduced-motion: reduce stops
motion.

The helper serves the dashboard as a single page, so the dashboard carries an
inline copy of the token block; it must stay equal to the file. The helper
serves the fonts that block points at (GET /brand/fonts/<file>).

Static checks plus one in-process helper on loopback for the font route; no
browser and no network.
"""
from __future__ import annotations

from collections import Counter
from http.server import ThreadingHTTPServer
from html.parser import HTMLParser
import json
import re
import sys
import threading
import urllib.error
from urllib.parse import urljoin
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS_TOKENS = ROOT / "assets" / "brand" / "tokens.css"
EXT_TOKENS = ROOT / "extension" / "brand" / "tokens.css"
DASHBOARD = ROOT / "assets" / "dashboard" / "index.html"
SETUP_JS = ROOT / "extension" / "setup.js"
# Pages that link brand/tokens.css; none may redefine a token it sets.
TOKEN_PAGES = ("extension/popup.html", "extension/setup.html",
               "extension/uoink-memory.html", "extension/uoink-memory.css")
FONT_DIRS = (ROOT / "assets" / "brand" / "fonts", ROOT / "extension" / "brand" / "fonts")

FAMILIES = {"Inter", "Bungee", "JetBrains Mono"}
# Licence file (as the site ships it) -> the copyright holder it must name.
LICENCES = {
    "inter-OFL.txt": "The Inter Project Authors",
    "bungee-OFL.txt": "The Bungee Project Authors",
    "jetbrains-mono-OFL.txt": "The JetBrains Mono Project Authors",
}
# Web font suffix -> (file signature, CSS format() hint).
FONT_FORMATS = {".woff": (b"wOFF", "woff"), ".woff2": (b"wOF2", "woff2")}

# The SPEC token table, verbatim.
SPEC_LIGHT = {
    "--bg": "#FFF4EC",
    "--surface": "#FFFFFF",
    "--surface-sel": "#FBE6D6",
    "--text": "#0A0A0A",
    "--text-2": "#5C4A40",
    "--line": "#EBD5C5",
    "--line-strong": "#D9BBA6",
    "--action": "#C2410C",
    "--on-action": "#FFFFFF",
    "--ok": "#15803D",
    "--fail": "#C2410C",
    "--step-done": "#0A0A0A",
    "--step-now": "#C2410C",
    "--step-fail": "#C2410C",
    "--step-todo": "#EBD5C5",
}
SPEC_DARK = {
    "--bg": "#0A0A0A",
    "--surface": "#141110",
    "--surface-sel": "#1E1815",
    "--text": "#F5EDE6",
    "--text-2": "#A8968A",
    "--line": "#2A211C",
    "--line-strong": "#3A2E27",
    "--action": "#FF3D00",
    "--on-action": "#0A0A0A",
    "--ok": "#22C55E",
    "--fail": "#FF8A5C",
    "--step-done": "#F5EDE6",
    "--step-now": "#C2410C",
    "--step-fail": "#FF3D00",
    "--step-todo": "#3A2E27",
}
RUST = "#C2410C"

# Names the pages used before the re-haul. Each colour name is an alias of a
# theme token, so pages that still use it follow light and dark.
LEGACY_ALIASES = {
    "--ink": "var(--bg)",
    "--ink-warm": "var(--surface)",
    "--cream": "var(--text)",
    "--border": "var(--line)",
    "--muted": "var(--text-2)",
    "--dim": "var(--text-2)",
    "--rust": "var(--action)",
    "--ok-on-cream": "var(--ok)",
    "--control-radius": "var(--radius-input)",
    "--pill-radius": "var(--radius-pill)",
}
# Older accents with no SPEC role: one value per theme. --acid and --warn are
# text colours and must read on that theme's grounds.
LEGACY_ACCENTS = ("--acid", "--warn", "--danger-bg", "--danger-border", "--shadow-soft",
                  "--rust-bright", "--vermillion", "--ok-bright")
LEGACY_TEXT_ACCENTS = ("--acid", "--warn", "--rust-bright", "--vermillion", "--ok-bright")
# Old names whose value does not depend on the theme.
LEGACY_FIXED = {
    "--card-radius": "12px",
    "--font-ui": 'Inter, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
    "--font-display": "Bungee, Inter, system-ui, sans-serif",
    "--font-mono": '"JetBrains Mono", Consolas, "SFMono-Regular", monospace',
}

MOTION = {
    "--ease-enter": "cubic-bezier(0.16, 1, 0.3, 1)",
    "--dur-enter": "200ms",
    "--ease-exit": "cubic-bezier(0.6, 0, 0.9, 0.35)",
    "--dur-exit": "100ms",
}

ROOT_RE = re.compile(r":root\s*\{([^{}]*)\}")
DARK_RE = re.compile(
    r"@media\s*\(\s*prefers-color-scheme\s*:\s*dark\s*\)\s*\{\s*:root\s*\{([^{}]*)\}\s*\}")
DECL_RE = re.compile(r"(--[A-Za-z0-9-]+)\s*:\s*([^;]+);")
FONT_FACE_RE = re.compile(r"@font-face\s*\{([^{}]*)\}")
FOCUS_RE = re.compile(r"(?:^|[\s}]):focus-visible\s*\{([^{}]*)\}", re.M)
HEX_RE = re.compile(r"#[0-9A-Fa-f]{6}")

REMOTE_FONT_RE = re.compile(
    r"fonts\.googleapis\.com|fonts\.gstatic\.com|typekit\.net|fonts\.bunny\.net"
    r"|rsms\.me/inter/[^\s\"']*\.css|fonts\.cdnfonts\.com|fontawesome\.com"
    r"|(?:jsdelivr\.net|unpkg\.com)/[^\s\"']*fontsource"
    r"|(?:https?:)?//[^\s\"'()<>]+\.(?:woff2?|ttf|otf|eot)\b"
    r"|@import\s+(?:url\(\s*)?[\"']?(?:https?:)?//"
    r"|<link\b[^>]*\bhref\s*=\s*[\"']?(?:https?:)?//",
    re.I)
BINARY_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".icns",
                   ".woff", ".woff2", ".ttf", ".otf", ".eot", ".zip"}


def _norm(value: str) -> str:
    return " ".join(value.split())


def _strip_comments(css: str) -> str:
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def _dashboard_css() -> str:
    match = re.search(r"<style>(.*?)</style>", DASHBOARD.read_text(encoding="utf-8"), re.S)
    assert match, "dashboard has no <style> block"
    return _strip_comments(match.group(1))


def _sources() -> dict[str, str]:
    """Every place the token block lives, comments removed."""
    return {
        "assets/brand/tokens.css": _strip_comments(ASSETS_TOKENS.read_text(encoding="utf-8")),
        "extension/brand/tokens.css": _strip_comments(EXT_TOKENS.read_text(encoding="utf-8")),
        "assets/dashboard/index.html": _dashboard_css(),
    }


def _decls(body: str) -> dict[str, str]:
    return {name: _norm(value) for name, value in DECL_RE.findall(body)}


def _themes(css: str) -> tuple[dict[str, str], dict[str, str]]:
    dark = DARK_RE.search(css)
    assert dark, "no :root block under @media (prefers-color-scheme: dark)"
    light = ROOT_RE.search(css)
    assert light and light.start() < dark.start(), "the light :root must come first, outside any @media"
    return _decls(light.group(1)), _decls(dark.group(1))


def _block_after(css: str, opener: str) -> str:
    """Body of the first block whose opening matches `opener` (ending in '{')."""
    match = re.search(opener, css)
    assert match, f"missing block: {opener}"
    depth, i = 1, match.end()
    while depth:
        assert i < len(css), f"unbalanced block: {opener}"
        depth += {"{": 1, "}": -1}.get(css[i], 0)
        i += 1
    return css[match.end():i - 1]


def _same(a: str, b: str) -> bool:
    return _norm(a).upper() == _norm(b).upper()


def _lum(hex_colour: str) -> float:
    def channel(c: int) -> float:
        c = c / 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    h = hex_colour.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def _contrast(a: str, b: str) -> float:
    hi, lo = sorted((_lum(a), _lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_no_remote_font_urls_anywhere_in_assets_or_extension():
    hits = []
    for base in (ROOT / "assets", ROOT / "extension"):
        for path in sorted(base.rglob("*")):
            if not path.is_file() or path.suffix.lower() in BINARY_SUFFIXES:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for lineno, line in enumerate(text.splitlines(), 1):
                if REMOTE_FONT_RE.search(line):
                    hits.append(f"{path.relative_to(ROOT).as_posix()}:{lineno}: {line.strip()[:160]}")
    assert not hits, "remote font or stylesheet references:\n" + "\n".join(hits)


def test_extension_pages_load_the_bundled_tokens_before_their_own_styles():
    for name in ("popup.html", "setup.html", "uoink-memory.html"):
        html = (ROOT / "extension" / name).read_text(encoding="utf-8")
        link = re.search(r'<link rel="stylesheet" href="brand/tokens\.css">', html)
        assert link, f"{name} must load brand/tokens.css (fonts and tokens)"
        later = [m.start() for m in re.finditer(r"<style\b|<link rel=\"stylesheet\"", html)
                 if m.start() != link.start()]
        assert all(link.start() < pos for pos in later), \
            f"{name}: tokens.css must load before the page's own styles so they can override it"
    # The extension pages may only use fonts packaged with the extension.
    manifest = json.loads((ROOT / "extension" / "manifest.json").read_text(encoding="utf-8"))
    csp = manifest.get("content_security_policy", {}).get("extension_pages", "")
    assert "font-src 'self'" in csp and "script-src 'self'" in csp, csp


def test_font_faces_resolve_to_bundled_font_files():
    expected: set[str] | None = None
    for label, css in _sources().items():
        base = (ROOT / label).parent
        faces = FONT_FACE_RE.findall(css)
        families, files = set(), set()
        for face in faces:
            family = re.search(r"font-family\s*:\s*[\"']?([^;\"']+)[\"']?\s*;", face)
            assert family, f"{label}: @font-face without a family"
            families.add(family.group(1).strip())
            assert "font-display: swap" in _norm(face), f"{label}: {family.group(1)} should swap"
            sources = re.findall(
                r"url\(\s*[\"']?([^\"')]+)[\"']?\s*\)\s*format\(\s*[\"']?([A-Za-z0-9-]+)[\"']?\s*\)", face)
            assert sources and len(sources) == face.count("url("), \
                f"{label}: every {family.group(1)} src needs a url() and a format() hint"
            for url, fmt in sources:
                assert not re.match(r"(?:[a-z][a-z0-9+.-]*:|//)", url, re.I), \
                    f"{label}: font url must be a relative bundled path, got {url}"
                path = (base / url).resolve()
                suffix = path.suffix.lower()
                assert suffix in FONT_FORMATS, f"{label}: {url} is not a woff or woff2 web font"
                magic, hint = FONT_FORMATS[suffix]
                assert fmt == hint, f"{label}: {url} is declared as format({fmt}), expected format({hint})"
                assert any(path.parent == d.resolve() for d in FONT_DIRS), \
                    f"{label}: {url} is outside the bundled font folders"
                assert path.is_file(), f"{label}: missing bundled font {path.relative_to(ROOT)}"
                assert path.read_bytes()[:4] == magic, f"{path.relative_to(ROOT)} is not a {hint} file"
                files.add(path.name)
        assert families == FAMILIES, f"{label}: @font-face families {sorted(families)}"
        if expected is None:
            expected = files
        assert files == expected, f"{label}: font files {sorted(files)} != {sorted(expected)}"
    for folder in FONT_DIRS:
        shipped = {p.name for p in folder.iterdir() if p.suffix.lower() in FONT_FORMATS}
        assert shipped == expected, \
            f"{folder.relative_to(ROOT)}: fonts no @font-face uses {sorted(shipped - expected)}"


def test_font_licences_ship_beside_the_fonts():
    listings = []
    for folder in FONT_DIRS:
        assert folder.is_dir(), f"missing {folder.relative_to(ROOT)}"
        for name, holder in LICENCES.items():
            path = folder / name
            assert path.is_file(), f"missing licence {path.relative_to(ROOT)}"
            text = _norm(path.read_text(encoding="utf-8", errors="ignore")).upper()
            assert "SIL OPEN FONT LICENSE" in text and "VERSION 1.1" in text, \
                f"{path.relative_to(ROOT)} is not the SIL OFL 1.1 text"
            assert "COPYRIGHT" in text and holder.upper() in text, \
                f"{path.relative_to(ROOT)} lacks the copyright line for {holder}"
        listings.append({p.name: p.read_bytes() for p in folder.iterdir() if p.is_file()})
    assert listings[0] == listings[1], "assets/brand/fonts and extension/brand/fonts must hold the same files"


def test_notices_name_the_bundled_fonts():
    for rel in ("THIRD-PARTY-NOTICES.md", "third-party-notices/README.md"):
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert "SIL Open Font License" in text, rel
        for family in FAMILIES:
            assert family in text, f"{rel} does not name {family}"
        for name in LICENCES:
            assert name in text, f"{rel} does not point to {name}"


def test_token_files_match_and_both_themes_define_every_token():
    assert ASSETS_TOKENS.read_bytes() == EXT_TOKENS.read_bytes(), \
        "assets/brand/tokens.css and extension/brand/tokens.css must be identical"
    themes = {label: _themes(css) for label, css in _sources().items()}
    for label, (light, dark) in themes.items():
        for name, value in SPEC_LIGHT.items():
            assert name in light and _same(light[name], value), f"{label} light {name}={light.get(name)}"
        for name, value in SPEC_DARK.items():
            assert name in dark and _same(dark[name], value), f"{label} dark {name}={dark.get(name)}"
        assert set(dark) <= set(light), f"{label}: dark-only tokens {sorted(set(dark) - set(light))}"
        themed = {n for n, v in light.items() if HEX_RE.fullmatch(v)}
        assert themed <= set(dark), f"{label}: no dark value for {sorted(themed - set(dark))}"
        assert not set(dark) & set(LEGACY_ALIASES), \
            f"{label}: aliases follow the theme tokens; the dark theme must not repaint them"
        root = ROOT_RE.search(_sources()[label])
        assert "color-scheme: light dark" in _norm(root.group(1)), f"{label}: missing color-scheme"
    reference = themes["assets/brand/tokens.css"]
    assert themes["assets/dashboard/index.html"] == reference, \
        "the dashboard's inline token block drifted from assets/brand/tokens.css"


def test_old_token_names_follow_the_theme():
    for label, css in _sources().items():
        light, dark = _themes(css)
        for name, target in LEGACY_ALIASES.items():
            assert _same(light.get(name, ""), target), \
                f"{label}: old token {name} must alias {target}, got {light.get(name)}"
        for name in LEGACY_ACCENTS:
            assert name in light and name in dark, f"{label}: {name} needs a light and a dark value"
            assert not _same(light[name], dark[name]), f"{label}: {name} is the same in both themes"
        for theme, values in (("light", light), ("dark", dark)):
            grounds = SPEC_LIGHT if theme == "light" else SPEC_DARK
            for name in LEGACY_TEXT_ACCENTS:
                for ground in ("--bg", "--surface"):
                    ratio = _contrast(values[name], grounds[ground])
                    assert ratio >= 4.5, f"{label} {theme}: {name} on {ground} is {ratio:.2f}:1"
        for name, value in LEGACY_FIXED.items():
            assert _same(light.get(name, ""), value), f"{label}: {name}={light.get(name)}"
        for name, value in MOTION.items():
            assert _same(light.get(name, ""), value), f"{label}: {name}={light.get(name)}"


def test_theme_colours_meet_wcag_aa():
    for theme, tokens in (("light", SPEC_LIGHT), ("dark", SPEC_DARK)):
        for ground in ("--bg", "--surface", "--surface-sel"):
            for ink in ("--text", "--text-2"):
                ratio = _contrast(tokens[ink], tokens[ground])
                assert ratio >= 4.5, f"{theme}: {ink} on {ground} is {ratio:.2f}:1"
            for part in ("--step-done", "--step-now", "--step-fail"):
                ratio = _contrast(tokens[part], tokens[ground])
                assert ratio >= 3, f"{theme}: {part} on {ground} is {ratio:.2f}:1"
            ratio = _contrast(RUST, tokens[ground])
            assert ratio >= 3, f"{theme}: focus ring on {ground} is {ratio:.2f}:1"
        for ground in ("--bg", "--surface"):
            for ink in ("--action", "--ok", "--fail"):
                ratio = _contrast(tokens[ink], tokens[ground])
                assert ratio >= 4.5, f"{theme}: {ink} text on {ground} is {ratio:.2f}:1"
        ratio = _contrast(tokens["--on-action"], tokens["--action"])
        assert ratio >= 4.5, f"{theme}: button text is {ratio:.2f}:1"


def test_focus_ring_is_two_px_rust_offset_two():
    for label, css in _sources().items():
        light, dark = _themes(css)
        assert _same(light.get("--focus-ring", ""), RUST) and _same(dark.get("--focus-ring", ""), RUST), \
            f"{label}: the focus ring is rust in both themes"
        rules = [_norm(body) for body in FOCUS_RE.findall(css)]
        assert any("outline: 2px solid var(--focus-ring) !important" in body and
                   "outline-offset: 2px !important" in body for body in rules), \
            f"{label}: no global :focus-visible ring (older 'outline: none' rules must not hide it)"


def test_reduced_motion_stops_motion():
    for label, css in _sources().items():
        body = _norm(_block_after(css, r"@media\s*\(\s*prefers-reduced-motion\s*:\s*reduce\s*\)\s*\{"))
        assert "--dur-enter: 0ms" in body and "--dur-exit: 0ms" in body, label
        assert "*, *::before, *::after {" in body, f"{label}: reduced motion must cover every element"
        for decl in ("animation-duration: 0.01ms !important",
                     "animation-iteration-count: 1 !important",
                     "transition-duration: 0.01ms !important",
                     "scroll-behavior: auto !important"):
            assert decl in body, f"{label}: reduced motion lacks '{decl}'"


def _token_counts(text: str) -> Counter:
    return Counter(name for name, _value in DECL_RE.findall(_strip_comments(text)))


def test_pages_do_not_redefine_the_shared_tokens():
    canonical = _token_counts(ASSETS_TOKENS.read_text(encoding="utf-8"))
    # The dashboard mirrors the token file once; any further declaration of a
    # token name would override the theme for that page.
    dashboard = _token_counts(DASHBOARD.read_text(encoding="utf-8"))
    drift = {name: dashboard[name] for name in canonical if dashboard[name] != canonical[name]}
    assert not drift, f"dashboard redeclares shared tokens: {drift}"
    for rel in TOKEN_PAGES:
        counts = _token_counts((ROOT / rel).read_text(encoding="utf-8"))
        clashes = sorted(name for name in canonical if counts[name])
        assert not clashes, f"{rel} overrides shared tokens {clashes}; use brand/tokens.css"


def test_every_token_a_page_uses_is_defined():
    defined = set(_token_counts(ASSETS_TOKENS.read_text(encoding="utf-8")))
    for rel in ("assets/dashboard/index.html", *TOKEN_PAGES):
        text = (ROOT / rel).read_text(encoding="utf-8")
        # A var() with a fallback may be page-local (set from script); one
        # without a fallback must resolve.
        used = set(re.findall(r"var\(\s*(--[A-Za-z0-9-]+)\s*\)", text))
        missing = sorted(used - defined - set(_token_counts(text)))
        assert not missing, f"{rel} uses undefined tokens {missing}"


def test_scripted_scrolling_respects_reduced_motion():
    for path in (DASHBOARD, SETUP_JS):
        text = path.read_text(encoding="utf-8")
        rel = path.relative_to(ROOT).as_posix()
        assert not re.search(r"behavior\s*:\s*[\"']smooth[\"']", text), \
            f"{rel}: smooth scrolling must go through scrollBehavior()"
        helper = re.search(r"function scrollBehavior\(\)\s*\{(.*?)\}", text, re.S)
        assert helper, f"{rel}: no scrollBehavior() helper"
        body = _norm(helper.group(1))
        assert 'matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth"' in body, body
        assert re.search(r"behavior:\s*scrollBehavior\(\)", text), f"{rel}: helper unused"


def _get(url: str) -> tuple[int, str, bytes]:
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            return response.status, response.headers.get("Content-Type", ""), response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.headers.get("Content-Type", ""), error.read()


def test_helper_serves_the_dashboard_fonts_without_a_token():
    sys.path.insert(0, str(ROOT))
    import server  # noqa: E402

    urls = []
    for face in FONT_FACE_RE.findall(_dashboard_css()):
        urls += re.findall(r"url\(\s*[\"']?([^\"')]+)", face)
    assert len(urls) == 4, urls
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{httpd.server_address[1]}"
        # The page is reachable with and without the trailing slash; the
        # relative font URLs must resolve to the font route either way.
        for page in ("/dashboard", "/dashboard/"):
            for url in urls:
                status, kind, body = _get(urljoin(base + page, url))
                name = Path(url).name
                assert status == 200, f"{page} -> {url}: {status}"
                assert kind == "font/woff", f"{url}: Content-Type {kind}"
                assert body == (ROOT / "assets" / "brand" / "fonts" / name).read_bytes(), url
        for bad in ("/brand/fonts/inter-OFL.txt", "/brand/fonts/missing.woff",
                    "/brand/fonts/../../server.py", "/brand/fonts/%2e%2e/%2e%2e/server.py",
                    "/brand/fonts/..%5c..%5cserver.py", "/brand/fonts/", "/brand/tokens.css"):
            status, _kind, _body = _get(base + bad)
            assert status in (401, 403, 404), f"{bad} must not be served: {status}"
    finally:
        httpd.shutdown()
        httpd.server_close()


# Every page that draws on the shared tokens. The popup's own layout is
# re-done later, but no page may keep a surface or text colour that only
# works on the old dark ground.
STYLED_PAGES = ("assets/dashboard/index.html", "extension/popup.html", "extension/setup.html",
                "extension/uoink-memory.html", "extension/uoink-memory.css")
LITERAL_RE = re.compile(r"#[0-9A-Fa-f]{3,8}\b|\brgba?\([^()]*\)")
FILLED_TEXT_MIN = 4.5


def _without_var_fallbacks(value: str) -> str:
    """Drop the fallback part of every var(--x, fallback)."""
    out, i = [], 0
    while i < len(value):
        if value.startswith("var(", i):
            j, depth = i + 4, 1
            while j < len(value) and depth:
                depth += {"(": 1, ")": -1}.get(value[j], 0)
                j += 1
            inner = value[i + 4:j - 1]
            out.append("var(" + inner.split(",", 1)[0] + ")")
            i = j
        else:
            out.append(value[i])
            i += 1
    return "".join(out)


def _page_rules(rel: str):
    text = (ROOT / rel).read_text(encoding="utf-8")
    css = "\n".join(re.findall(r"<style[^>]*>(.*?)</style>", text, re.S)) if rel.endswith(".html") else text
    css = _strip_comments(css)
    for match in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
        selector = _norm(match.group(1))
        if selector.startswith((":root", "@")) or re.fullmatch(r"(?:from|to|\d+%)(?:\s*,\s*(?:from|to|\d+%))*", selector):
            continue
        props = {name: _norm(value) for name, value in
                 re.findall(r"(?<![-\w])([a-z-]+)\s*:\s*([^;]+);", match.group(2))}
        yield selector, props
    if rel.endswith(".html"):
        # Static style attributes count too (template expressions are skipped).
        for match in re.finditer(r"\bstyle=\"([^\"]*)\"", text):
            if "${" in match.group(1):
                continue
            line = text.count("\n", 0, match.start()) + 1
            props = {name: _norm(value) for name, value in
                     re.findall(r"(?<![-\w])([a-z-]+)\s*:\s*([^;]+)(?:;|$)", match.group(1))}
            yield f"[style attribute, line {line}]", props


def _opaque(literal: str) -> bool:
    if literal.startswith("#"):
        return True
    parts = [p.strip() for p in literal[literal.index("(") + 1:-1].replace("/", ",").split(",")]
    alpha = float(parts[3]) if len(parts) > 3 else 1.0
    return alpha >= 0.5


def test_no_page_keeps_a_fixed_surface_or_text_colour():
    problems = []
    for rel in STYLED_PAGES:
        for selector, props in _page_rules(rel):
            for prop, value in props.items():
                literals = LITERAL_RE.findall(_without_var_fallbacks(value))
                if prop in ("background", "background-color"):
                    bad = [lit for lit in literals if _opaque(lit)]
                elif prop == "color":
                    bad = literals
                elif prop in ("border", "border-color"):
                    bad = [lit for lit in literals if lit.startswith("#")]
                else:
                    continue
                if bad:
                    problems.append(f"{rel}: {selector} {{ {prop}: {value} }}")
    assert not problems, "use theme tokens:\n" + "\n".join(problems)


def _resolver(rel: str):
    light, dark = _themes(_sources()["assets/brand/tokens.css"])
    page = _strip_comments((ROOT / rel).read_text(encoding="utf-8"))
    for block in re.finditer(r"(@media\s*\(\s*prefers-color-scheme\s*:\s*dark\s*\)\s*\{\s*)?:root\s*\{([^{}]*)\}", page):
        (dark if block.group(1) else light).update(_decls(block.group(2)))
    return {"light": light, "dark": {**light, **dark}}


def _rgb(hex_colour: str) -> tuple[float, float, float]:
    h = hex_colour.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _hex(rgb) -> str:
    return "#" + "".join(f"{max(0, min(255, round(c))):02X}" for c in rgb)


def _over(top: str, alpha: float, ground: str) -> str:
    t, g = _rgb(top), _rgb(ground)
    return _hex(alpha * a + (1 - alpha) * b for a, b in zip(t, g))


def _colour(value: str, table: dict, ground: str, depth: int = 0):
    """Resolve a CSS colour to the hex it paints over `ground`, or None."""
    value = _norm(value)
    if depth > 12:
        return None
    ref = re.fullmatch(r"var\(\s*(--[A-Za-z0-9-]+)\s*(?:,\s*(.+))?\)", value)
    if ref:
        if ref.group(1) in table:
            return _colour(table[ref.group(1)], table, ground, depth + 1)
        return _colour(ref.group(2), table, ground, depth + 1) if ref.group(2) else None
    if HEX_RE.fullmatch(value):
        return value.upper()
    if re.fullmatch(r"#[0-9A-Fa-f]{3}", value):
        return "#" + "".join(c * 2 for c in value[1:]).upper()
    rgba = re.fullmatch(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*([\d.]+)\s*)?\)", value)
    if rgba:
        top = _hex(int(x) for x in rgba.groups()[:3])
        return _over(top, float(rgba.group(4) or 1), ground)
    mix = re.fullmatch(r"color-mix\(\s*in srgb\s*,\s*(.+?)\s+([\d.]+)%\s*,\s*(.+)\)", value)
    if mix:
        first = _colour(mix.group(1), table, ground, depth + 1)
        pct = float(mix.group(2)) / 100
        second = mix.group(3).strip()
        if not first:
            return None
        if second == "transparent":
            return _over(first, pct, ground)
        other = _colour(second, table, ground, depth + 1)
        return _over(first, pct, other) if other else None
    if value == "transparent":
        return ground
    return None


def _paint(background: str) -> str | None:
    """The plain colour part of a background shorthand, if it has one."""
    if "gradient(" in background or "url(" in background:
        return None
    return background


PHOTOS = ["#FFFFFF", "#000000"]


def _translucent(background: str, table: dict) -> bool:
    """Partly see-through: a tint, not an opaque fill and not fully transparent."""
    over_white = _colour(background, table, "#FFFFFF")
    over_black = _colour(background, table, "#000000")
    return over_white != over_black and (over_white, over_black) != ("#FFFFFF", "#000000")


def _grounds(background: str, table: dict, props: dict | None = None) -> list[str]:
    # Overlays sit on photos: check them over the lightest and darkest image.
    if "var(--scrim)" in background:
        return PHOTOS
    if props and props.get("position") == "absolute" and _translucent(background, table):
        return PHOTOS
    return [_colour("var(--bg)", table, "#FFFFFF"), _colour("var(--surface)", table, "#FFFFFF")]


def _opacity(props: dict) -> float:
    value = props.get("opacity", "1")
    if not re.fullmatch(r"[\d.]+", value) or float(value) == 0:
        return 1.0  # 0 is hidden until a state shows it; check it as shown
    return min(1.0, float(value))


def _painted(props: dict, background: str | None, colour: str, table: dict, ground: str):
    """(fill, text) as they reach the screen, including the element's opacity."""
    fill = _colour(background, table, ground) if background else ground
    ink = _colour(colour, table, fill) if fill else None
    if not fill or not ink:
        return None, None
    alpha = _opacity(props)
    if alpha < 1:
        fill, ink = _over(fill, alpha, ground), _over(ink, alpha, ground)
    return fill, ink


def _exempt(selector: str) -> bool:
    """Disabled controls are exempt from the contrast minimum (WCAG 1.4.3)."""
    return all(DISABLED_RE.search(part) for part in selector.split(","))


def _pair_failures(rel: str):
    tables = _resolver(rel)
    rules = list(_page_rules(rel))
    out = []
    for selector, props in rules:
        background = _paint(props.get("background-color") or props.get("background") or "")
        colour = props.get("color")
        if not background or not colour or colour == "transparent" or _exempt(selector):
            continue  # transparent text is a hidden glyph, not text
        for theme, table in tables.items():
            for ground in _grounds(background, table, props):
                fill, ink = _painted(props, background, colour, table, ground)
                if fill and ink and _contrast(fill, ink) < FILLED_TEXT_MIN:
                    out.append(f"{rel} {theme}: {selector} {colour} on {background} over {ground} "
                               f"is {_contrast(fill, ink):.2f}:1")
                    break
    return out


STATE_RE = re.compile(r":hover|:focus-visible|:focus-within|:active|\.active(?![\w-])|\.selected(?![\w-])|\[aria-(?:selected|current)[^\]]*\]")
DISABLED_RE = re.compile(r":disabled|\[disabled\]|\[aria-disabled|\.disabled(?![\w-])")


def _state_failures(rel: str):
    """Text inside a hover/active state must read on that state's background."""
    tables = _resolver(rel)
    rules = list(_page_rules(rel))
    by_part = {}
    for selector, props in rules:
        for part in (p.strip() for p in selector.split(",")):
            by_part.setdefault(part, {}).update(props)
    out = []

    def check(label, colour, props, background, state_props):
        if DISABLED_RE.search(label):
            return
        for theme, table in tables.items():
            for ground in _grounds(background, table, state_props):
                fill, ink = _painted(props, background, colour, table, ground)
                if fill and ink and _contrast(fill, ink) < FILLED_TEXT_MIN:
                    out.append(f"{rel} {theme}: {label} ({colour}) on {background} is {_contrast(fill, ink):.2f}:1")
                    return

    for selector, props in rules:
        background = _paint(props.get("background-color") or props.get("background") or "")
        if not background:
            continue
        for part in (p.strip() for p in selector.split(",")):
            if not STATE_RE.search(part):
                continue
            base = STATE_RE.sub("", part).strip()
            base_props = by_part.get(base, {})
            # The element's own text in the state (its own colour or the base one).
            own = props.get("color") or base_props.get("color")
            if own and own != "transparent":
                check(part, own, {**base_props, **props}, background, props)
            for child_part, child in by_part.items():
                if not child_part.startswith(base + " "):
                    continue
                tail = child_part[len(base):]
                restyled = by_part.get(part + tail)
                merged = {**child, **(restyled or {})}
                if "background" in merged or "background-color" in merged:
                    continue
                colour = merged.get("color")
                if colour and colour != "transparent":
                    check(part + tail, colour, merged, background, props)
    return sorted(set(out))


def _plain_text_failures(rel: str):
    """Text with no fill of its own must read on the page grounds."""
    tables = _resolver(rel)
    out = []
    for selector, props in _page_rules(rel):
        colour = props.get("color")
        if (not colour or colour == "transparent" or "background" in props or "background-color" in props
                or STATE_RE.search(selector) or "::placeholder" in selector or ":disabled" in selector
                or "[disabled]" in selector):
            continue
        for theme, table in tables.items():
            for ground_name in ("--bg", "--surface"):
                ground = _colour(f"var({ground_name})", table, "#FFFFFF")
                fill, ink = _painted(props, None, colour, table, ground)
                if ink and _contrast(fill, ink) < FILLED_TEXT_MIN:
                    out.append(f"{rel} {theme}: {selector} ({colour}) on {ground_name} is {_contrast(ground, ink):.2f}:1")
                    break
    return sorted(set(out))


def test_text_on_every_fill_and_tint_meets_aa_in_both_themes():
    failures = [f for rel in STYLED_PAGES for f in _pair_failures(rel)]
    assert not failures, "\n".join(failures)


def test_text_inside_hover_and_active_states_stays_readable():
    failures = [f for rel in STYLED_PAGES for f in _state_failures(rel)]
    assert not failures, "\n".join(failures)


def test_plain_text_reads_on_the_page_grounds():
    failures = [f for rel in STYLED_PAGES for f in _plain_text_failures(rel)]
    assert not failures, "\n".join(failures)


def test_photo_overlays_use_the_scrim_pair():
    light, dark = _themes(_sources()["assets/brand/tokens.css"])
    for theme in (light, {**light, **dark}):
        assert _same(theme["--on-scrim"], "#FFFFFF")
        assert _contrast("#FFFFFF", _colour("var(--scrim)", theme, "#FFFFFF")) >= 4.5
    for rel in STYLED_PAGES:
        for selector, props in _page_rules(rel):
            background = props.get("background-color") or props.get("background") or ""
            if "var(--scrim)" in background and "color" in props:
                assert props["color"] == "var(--on-scrim)", f"{rel}: {selector} text on the scrim"


def test_scripted_badge_and_link_colours_use_tokens():
    dashboard = DASHBOARD.read_text(encoding="utf-8")
    popup_js = (ROOT / "extension" / "popup.js").read_text(encoding="utf-8")
    for label, text in (("dashboard", dashboard), ("popup.js", popup_js)):
        hits = re.findall(r"\.style\.(?:color|background(?:Color)?)\s*=\s*[\"'][^\"']*(?:#[0-9A-Fa-f]{3,8}|rgba?\()", text)
        hits = [h for h in hits if LITERAL_RE.search(_without_var_fallbacks(h.split("=", 1)[1]))]
        assert not hits, f"{label}: scripted colours must be theme tokens: {hits}"


# ---- Markup-aware contrast: variants and ancestor fills -------------------

# Text on a fill an ancestor paints (hover/active/error states included).
ANCESTOR_TEXT_MIN = FILLED_TEXT_MIN

# Scripts that build each page's markup from HTML template strings.
PAGE_SCRIPTS = {
    "assets/dashboard/index.html": ("assets/dashboard/index.html",),
    "extension/popup.html": ("extension/popup.html", "extension/popup.js"),
    "extension/setup.html": ("extension/setup.html", "extension/setup.js"),
    "extension/uoink-memory.html": ("extension/uoink-memory.html",),
}
NAME_RE = re.compile(r"[.#][A-Za-z_][\w-]*")
COMBINATOR_RE = re.compile(r"\s*[>+~]\s*|\s+")


class _Nesting(HTMLParser):
    """Collects every element as (ancestor name sets, outermost first; own names)."""
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}

    def __init__(self, elements: list):
        super().__init__(convert_charrefs=True)
        self.stack: list[set] = []
        self.elements = elements

    def handle_starttag(self, tag, attrs):
        names = set()
        for key, value in attrs:
            if key == "class" and value:
                names |= {"." + c for c in value.split() if re.fullmatch(r"[A-Za-z_][\w-]*", c)}
            if key == "id" and value and re.fullmatch(r"[A-Za-z_][\w-]*", value):
                names.add("#" + value)
        if names:
            self.elements.append((tuple(frozenset(a) for a in self.stack), frozenset(names)))
        if tag not in self.VOID:
            self.stack.append(names)

    def handle_endtag(self, tag):
        if tag not in self.VOID and self.stack:
            self.stack.pop()


def _templates(js: str) -> list[str]:
    """Top-level template literals, with nested templates inlined where their
    ${...} expression sits (other expressions become 'x'). Comments and quoted
    strings are skipped so their backticks do not open templates."""
    n, out = len(js), []

    def skip_string(i: int, quote: str) -> int:
        i += 1
        while i < n and js[i] != quote and js[i] != "\n":
            i += 2 if js[i] == "\\" else 1
        return i + 1

    def template(i: int) -> tuple[str, int]:
        buf = []
        while i < n:
            c = js[i]
            if c == "\\":
                buf.append(js[i:i + 2]); i += 2; continue
            if c == "`":
                return "".join(buf), i + 1
            if js.startswith("${", i):
                inner, i = expression(i + 2)
                buf.append(inner or "x"); continue
            buf.append(c); i += 1
        return "".join(buf), i

    def expression(i: int) -> tuple[str, int]:
        depth, parts = 1, []
        while i < n and depth:
            c = js[i]
            if c == "`":
                text, i = template(i + 1); parts.append(text); continue
            if c in "'\"":
                i = skip_string(i, c); continue
            depth += {"{": 1, "}": -1}.get(c, 0)
            i += 1
        return "".join(parts), i

    i = 0
    while i < n:
        if js.startswith("//", i):
            j = js.find("\n", i); i = n if j < 0 else j
        elif js.startswith("/*", i):
            j = js.find("*/", i + 2); i = n if j < 0 else j + 2
        elif js[i] in "'\"":
            i = skip_string(i, js[i])
        elif js[i] == "`":
            text, i = template(i + 1); out.append(text)
        else:
            i += 1
    return out


def _elements(page: str) -> list:
    elements: list = []
    for rel in PAGE_SCRIPTS.get(page, (page,)):
        text = (ROOT / rel).read_text(encoding="utf-8")
        fragments = []
        if rel.endswith(".html"):
            fragments.append(re.sub(r"<(style|script)\b.*?</\1>", "", text, flags=re.S | re.I))
            scripts = "\n".join(re.findall(r"<script\b[^>]*>(.*?)</script>", text, re.S | re.I))
        else:
            scripts = text
        fragments += [t for t in _templates(scripts) if "<" in t and "class=" in t]
        for fragment in fragments:
            parser = _Nesting(elements)
            try:
                parser.feed(fragment)
                parser.close()
            except Exception:  # an unparseable fragment adds nothing
                continue
    return elements


def _nesting(page: str) -> set:
    """(ancestor, descendant) name pairs."""
    return {(a, n) for chain, names in _elements(page) for level in chain for a in level for n in names}


def _split(part: str) -> tuple[str, str]:
    """(ancestor context, last compound) of one selector part."""
    pieces = [p for p in COMBINATOR_RE.split(part.strip()) if p]
    last = pieces[-1] if pieces else part
    context = part.strip()[: len(part.strip()) - len(last)].strip()
    return context, last


def _names(compound: str) -> set:
    return set(NAME_RE.findall(re.sub(r"::?[a-z-]+(\([^)]*\))?", "", compound)))


def _merged_parts(page: str) -> dict:
    """Props per selector part; a compound variant (.a.b) includes its base (.a)."""
    by_part: dict = {}
    for selector, props in _page_rules(page):
        for part in (p.strip() for p in selector.split(",")):
            by_part.setdefault(part, {}).update(props)
    merged = {}
    for part, props in by_part.items():
        context, last = _split(part)
        names = _names(last)
        base: dict = {}
        if len(names) > 1:
            for other, other_props in by_part.items():
                other_context, other_last = _split(other)
                other_names = _names(other_last)
                if (other_context == context and other_names and other_names < names
                        and re.fullmatch(r"(?:[.#][A-Za-z_][\w-]*)+", other_last)):
                    base.update(other_props)
        merged[part] = {**base, **props}
    return merged


def _covers(page: str, parts: dict, tables: dict):
    """Names whose own (base-state) rule paints an opaque fill."""
    opaque = set()
    for part, props in parts.items():
        background = _paint(props.get("background-color") or props.get("background") or "")
        if (background and re.fullmatch(r"[.#][A-Za-z_][\w-]*", part) and props.get("display") != "none"
                and not _translucent(background, tables["light"])
                and _colour(background, tables["light"], "#FFFFFF") == _colour(background, tables["light"], "#000000")):
            opaque.add(part)
    return opaque


def _uncovered(elements: list, fill_names: set, text_names: set, opaque: set) -> bool:
    """Some element named like the text sits inside the fill with no opaque
    element between them."""
    for chain, names in elements:
        if not names & text_names:
            continue
        for k in range(len(chain) - 1, -1, -1):
            if chain[k] & fill_names:
                if not any(level & opaque for level in chain[k + 1:]):
                    return True
                break
    return False


def _ancestor_fill_failures(page: str, minimum: float | None = None):
    minimum = ANCESTOR_TEXT_MIN if minimum is None else minimum
    tables = _resolver(page)
    parts = _merged_parts(page)
    elements = _elements(page)
    nesting = {(a, n) for chain, names in elements for level in chain for a in level for n in names}
    opaque = _covers(page, parts, tables)
    fills = []
    for part, props in parts.items():
        background = _paint(props.get("background-color") or props.get("background") or "")
        last = _split(part)[1]
        if (background and not DISABLED_RE.search(part) and "::" not in last
                and props.get("display") != "none" and ".hidden" not in _names(last)):
            fills.append((part, props, background, _names(last)))
    out = []
    for part, props in parts.items():
        colour = props.get("color")
        if (not colour or colour == "transparent" or "background" in props or "background-color" in props
                or DISABLED_RE.search(part) or "::placeholder" in part):
            continue
        context, last = _split(part)
        text_names = _names(last)
        for fill_part, fill_props, background, fill_names in fills:
            if fill_part == part:
                continue
            if not any((a, t) in nesting for a in fill_names for t in text_names):
                continue
            if not _uncovered(elements, fill_names, text_names, opaque):
                continue
            # A text rule scoped to a different ancestor does not apply here.
            if context and not (fill_part == context or context.startswith(fill_part + " ")
                                or _names(context.split()[-1]) <= fill_names):
                continue
            # The fill's own state/variant restyles this text: check that rule instead.
            if any(other.startswith(fill_part + " ") and _names(_split(other)[1]) & text_names
                   and "color" in parts[other] and other != part for other in parts):
                continue
            for theme, table in tables.items():
                hit = None
                for ground in _grounds(background, table, fill_props):
                    fill, ink = _painted(props, background, colour, table, ground)
                    if fill and ink and _contrast(fill, ink) < minimum:
                        hit = f"{page} {theme}: {part} ({colour}) inside {fill_part} ({background}) is {_contrast(fill, ink):.2f}:1"
                        break
                if hit:
                    out.append(hit)
                    break
    return sorted(set(out))


def _variant_failures(page: str):
    """Variant rules (.a.b) are checked with their base rule's fill and position."""
    tables = _resolver(page)
    out = []
    for part, props in _merged_parts(page).items():
        background = _paint(props.get("background-color") or props.get("background") or "")
        colour = props.get("color")
        if not background or not colour or colour == "transparent" or DISABLED_RE.search(part):
            continue
        for theme, table in tables.items():
            for ground in _grounds(background, table, props):
                fill, ink = _painted(props, background, colour, table, ground)
                if fill and ink and _contrast(fill, ink) < FILLED_TEXT_MIN:
                    out.append(f"{page} {theme}: {part} ({colour} on {background} over {ground}) is "
                               f"{_contrast(fill, ink):.2f}:1")
                    break
    return sorted(set(out))


def test_markup_nesting_is_found():
    # Guards the guard: the nesting the checks below depend on is really read.
    assert (".queue-banner", ".queue-banner-toggle") in _nesting("extension/popup.html")
    assert (".uoink-card", ".card-source") in _nesting("assets/dashboard/index.html")
    # An opaque card between a backdrop and its text hides the backdrop.
    elements = [((frozenset({".modal-backdrop"}), frozenset({".modal-card"})), frozenset({".soft-note"}))]
    assert not _uncovered(elements, {".modal-backdrop"}, {".soft-note"}, {".modal-card"})
    assert _uncovered(elements, {".modal-card"}, {".soft-note"}, {".modal-card"})
    merged = _merged_parts("assets/dashboard/index.html")
    assert merged[".platform-chip.live"].get("position") == "absolute"


def test_variant_rules_meet_aa_with_their_base_fill():
    failures = [f for page in PAGE_SCRIPTS for f in _variant_failures(page)]
    assert not failures, "\n".join(failures)


def test_text_reads_on_every_fill_its_ancestors_paint():
    failures = [f for page in PAGE_SCRIPTS for f in _ancestor_fill_failures(page)]
    assert not failures, "\n".join(failures)


# The accent-text names carry a darker light-mode value so small labels read;
# fills, borders and dots must use the SPEC --action / --ok instead.
ACCENT_TEXT_NAMES = ("--vermillion", "--rust-bright", "--ok-bright")


def test_accent_text_names_are_only_used_for_text():
    misuse = []
    for rel in STYLED_PAGES:
        for selector, props in _page_rules(rel):
            for prop, value in props.items():
                if prop == "color" or prop.startswith("--"):
                    continue
                if any(f"var({name})" in value for name in ACCENT_TEXT_NAMES):
                    misuse.append(f"{rel}: {selector} {{ {prop}: {value} }}")
    assert not misuse, "fills and borders use --action / --ok:\n" + "\n".join(misuse)


def _script_classes(page: str) -> set:
    """Class names a page's scripts assign to elements they build."""
    names = set()
    for rel in PAGE_SCRIPTS.get(page, ()):
        if not rel.endswith(".js"):
            continue
        text = (ROOT / rel).read_text(encoding="utf-8")
        for match in re.finditer(r"\.className\s*=\s*([\"'`])(.*?)\1", text):
            value = re.sub(r"\$\{[^}]*\}", " ", match.group(2))
            names |= {"." + c for c in value.split() if re.fullmatch(r"[A-Za-z_][\w-]*", c)}
        for match in re.finditer(r"\.classList\.(?:add|toggle)\(([^)]*)\)", text):
            names |= {"." + c for c in re.findall(r"[\"']([A-Za-z_][\w-]*)[\"']", match.group(1))}
    return names


def _script_built_text_failures(page: str):
    """Script-built rows can sit in a hovered row (--surface-sel): their text
    must read there as well as on --bg and --surface."""
    built = _script_classes(page)
    if not built:
        return []
    tables = _resolver(page)
    out = []
    for part, props in _merged_parts(page).items():
        colour = props.get("color")
        if (not colour or colour == "transparent" or "background" in props or "background-color" in props
                or DISABLED_RE.search(part) or not _names(_split(part)[1]) & built):
            continue
        for theme, table in tables.items():
            for ground_name in ("--bg", "--surface", "--surface-sel"):
                ground = _colour(f"var({ground_name})", table, "#FFFFFF")
                fill, ink = _painted(props, None, colour, table, ground)
                if ink and _contrast(fill, ink) < FILLED_TEXT_MIN:
                    out.append(f"{page} {theme}: {part} ({colour}) on {ground_name} is {_contrast(fill, ink):.2f}:1")
                    break
    return sorted(set(out))


def test_script_built_text_reads_in_hovered_rows():
    assert ".hook-correction-message" in _script_classes("extension/popup.html")
    failures = [f for page in PAGE_SCRIPTS for f in _script_built_text_failures(page)]
    assert not failures, "\n".join(failures)
