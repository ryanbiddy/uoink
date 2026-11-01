"""One button system across the dashboard, popup, setup page and in-page buttons.

UI review 2026-10-31 (handoff/ui-review-2026-10-31/REVIEW-codex.md): shared
variants and states from brand tokens, one primary per view, honest disabled
states, a visible in-page focus ring, and the small fixes that review found
(Newsletter wrap, sidebar focus, reader emphasis, tray and Mac wording).
Static checks plus one node run of the dashboard's inline Markdown renderer.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = (ROOT / "assets" / "dashboard" / "index.html").read_text(encoding="utf-8")
CSS = DASHBOARD.split("<style>", 1)[1].split("</style>", 1)[0]
POPUP = (ROOT / "extension" / "popup.html").read_text(encoding="utf-8")
SETUP = (ROOT / "extension" / "setup.html").read_text(encoding="utf-8")
SETUP_JS = (ROOT / "extension" / "setup.js").read_text(encoding="utf-8")
TOKENS = (ROOT / "assets" / "brand" / "tokens.css").read_text(encoding="utf-8")

BUTTON_TOKENS = ("--btn-border", "--btn-hover", "--btn-press", "--btn-primary-hover",
                 "--btn-primary-press", "--btn-danger", "--on-danger", "--btn-danger-hover",
                 "--btn-danger-press", "--btn-disabled", "--on-btn-disabled")


def _rule(css: str, selector: str) -> str:
    match = re.search(r"(?:^|[}/])\s*" + re.escape(selector) + r"\s*\{([^{}]*)\}", css)
    assert match, f"missing rule {selector}"
    return " ".join(match.group(1).split())


def _section(start: str, end: str) -> str:
    return DASHBOARD[DASHBOARD.index(start):DASHBOARD.index(end, DASHBOARD.index(start))]


def test_button_tokens_are_defined_for_every_theme():
    for name in BUTTON_TOKENS:
        # light, prefers-color-scheme dark, and forced data-theme="dark"
        assert TOKENS.count(name + ":") == 3, name


def test_dashboard_variants_and_states_use_the_tokens():
    base = _rule(CSS, ".button,\n    .icon-button")
    assert "font-weight: 600" in base and "border-radius: var(--radius-pill)" in base
    assert "min-height: var(--target-primary)" in base and "padding: 0 14px" in base
    assert "var(--btn-primary-hover)" in _rule(CSS, ".button.primary:hover")
    assert "var(--btn-primary-press)" in _rule(CSS, ".button.primary:active")
    assert "background: var(--btn-danger)" in _rule(CSS, ".button.danger")
    assert "text-decoration: underline" in _rule(CSS, ".button.link")
    small = _rule(CSS, ".button.small")
    assert "min-height: var(--target-chip)" in small and "font-size: 13px" in small
    assert "var(--btn-disabled)" in CSS and "var(--on-btn-disabled)" in CSS
    assert '.button[aria-busy="true"]::before' in CSS
    # The old per-surface disabled recipes are gone.
    assert "#tab-activity .button:disabled" not in CSS
    assert ".settings-tool-button:disabled" not in CSS


def test_extension_pages_share_the_same_states():
    for label, page in (("popup", POPUP), ("setup", SETUP)):
        for token in ("--btn-primary-hover", "--btn-primary-press", "--btn-disabled",
                      "--on-btn-disabled", "--btn-hover", "--btn-border"):
            assert f"var({token})" in page, f"{label} lacks {token}"
    # Primary hover is no longer pinned to the resting colour.
    assert "button.primary:hover, button.primary:active { background: var(--action)" not in POPUP
    assert "text-decoration: underline" not in _rule(SETUP, ".button:hover")


def test_one_primary_per_view():
    sources = _section('id="tab-sources"', 'id="getExtensionCard"')
    assert sources.count('class="button primary"') == 1
    assert 'id="universalCaptureButton"' in sources.split('class="button primary"', 1)[1][:60]
    for_you_head = _section('id="tab-for-you"', 'id="forYouSummary"')
    assert 'class="button primary"' not in for_you_head
    for marker in ('id="openYouTubeForYou"', 'id="newYoink"', "data-open-youtube>"):
        tag = DASHBOARD[DASHBOARD.rindex("<button", 0, DASHBOARD.index(marker)):DASHBOARD.index(marker) + len(marker)]
        assert 'class="button link"' in tag, marker
    assert "lead: i === 0" in DASHBOARD
    assert '`<button class="button${index === 0 ? " primary" : ""}" type="button" data-connect-agent=' in DASHBOARD


def test_setup_primary_follows_the_current_step():
    assert 'id="download-btn" class="button primary"' in SETUP
    assert 'id="verify-btn" class="button"' in SETUP
    assert 'button.classList.toggle("primary", name === step)' in SETUP_JS


def test_status_and_help_text_are_not_button_shaped():
    chip = _rule(CSS, ".universal-capture-chip")
    assert "border" not in chip and "radius" not in chip and "uppercase" not in chip
    learn = _rule(CSS, ".learn-links a,\n    .small-link-button")
    assert "text-decoration: underline" in learn and "background" not in learn


@pytest.mark.parametrize("name", ["content.js", "content-reddit.js", "content-x-article.js"])
def test_in_page_buttons_show_focus_and_keep_readable_hover(name):
    text = (ROOT / "extension" / name).read_text(encoding="utf-8")
    assert re.search(r":focus-visible \{\s*outline: 2px solid #0A0A0A;\s*outline-offset: 2px;\s*box-shadow: 0 0 0 2px #FFFFFF", text)
    assert "#FF3D00" not in text, "hover must not put white text on bright orange"


def test_generate_output_labels_do_not_break_mid_word():
    assert "minmax(min(148px, 100%), 1fr)" in _rule(CSS, ".radio-grid")
    assert "overflow-wrap: normal" in _rule(CSS, ".radio-grid .choice-row span")


def test_nav_focus_is_not_a_second_selection():
    assert ".nav-button:focus-visible" not in CSS
    assert 'closest(".nav-button[data-tab-button]")' in DASHBOARD


def test_platform_words():
    tray = (ROOT / "uoink_tray.py").read_text(encoding="utf-8")
    for label in ('"Open dashboard"', '"Open folder"', '"Recent items"', '"No recent items yet"'):
        assert label in tray
    assert "yoinks" not in tray.lower().split("def _recent_items", 1)[1].split("def _on_stop", 1)[0]
    assert 'data-mac-copy="Open at Login"' in DASHBOARD
    assert "without showing a notification" in DASHBOARD


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_reader_renders_emphasis_without_touching_code_or_maths():
    fn = re.search(r"function renderInlineMarkdown\(value\) \{.*?\n    \}", DASHBOARD, re.S).group(0)
    cases = ["*A spring tide*", "2 * 3 * 4", "snake_case and _this_", "`a*b*c` *x*"]
    script = (
        "const htmlEscape = (v) => String(v).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');\n"
        + fn + "\nprocess.stdout.write(JSON.stringify(" + json.dumps(cases) + ".map(renderInlineMarkdown)));"
    )
    out = json.loads(subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True).stdout)
    assert out == ["<em>A spring tide</em>", "2 * 3 * 4", "snake_case and <em>this</em>",
                   "<code>a*b*c</code> <em>x</em>"]
