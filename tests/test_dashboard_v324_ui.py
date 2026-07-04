"""Static UI contract checks for the v3.2.4 dashboard consolidation.

Run: python tests/test_dashboard_v324_ui.py
"""
from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DASHBOARD = (ROOT / "assets" / "dashboard" / "index.html").read_text(encoding="utf-8")
SPLASH = (ROOT / "assets" / "splash" / "index.html").read_text(encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_sidebar() -> None:
    nav = re.search(r'<nav class="nav" aria-label="Sections">(.*?)</nav>', DASHBOARD, re.S)
    require(nav is not None, "sidebar nav missing")
    labels = [
        re.sub(r"<.*?>", "", item).strip().split()[0]
        for item in re.findall(r'<button class="nav-button.*?>(.*?)</button>', nav.group(1), re.S)
    ]
    require(labels == ["Library", "Sources", "For", "Generate", "Settings"], f"unexpected sidebar: {labels}")
    require('data-tab-button="build"' not in DASHBOARD, "Build tab still visible")
    require('data-tab-button="script"' not in DASHBOARD, "Script tab still visible")
    print("ok  sidebar: five locked tabs, Build and Script gone")


def test_picker() -> None:
    require("grid-template-columns: repeat(4, minmax(0, 1fr))" in DASHBOARD, "picker is not four columns")
    require("grid-template-columns: repeat(3, minmax(0, 1fr))" in DASHBOARD, "picker does not retain three columns at smaller widths")
    require("/screenshots?dedupe=${" in DASHBOARD, "picker list endpoint missing")
    require("/screenshots/suggest?${query.toString()}" in DASHBOARD, "suggest endpoint missing")
    require("/screenshots/${encodeURIComponent(shot.index ?? position)}.png" in DASHBOARD, "binary thumbnail endpoint missing")
    require("state.writingSelectedScreenshots = new Set();" in DASHBOARD, "zero-selection reset missing")
    require("Preselect all screenshots" not in DASHBOARD, "preselect-all UI still present")
    for copy in ("Pick best for", "Hide visual duplicates", "Apply range", "Auto-distribute to posts"):
        require(copy in DASHBOARD, f"picker control missing: {copy}")
    require("data.selected.map((shot) => String(shot.index))" in DASHBOARD, "deduped suggestions lose original screenshot ids")
    require("data-thread-shot" in DASHBOARD, "per-post screenshot assignment missing")
    require("state.writingScreenshotAssignments.get(index)" in DASHBOARD, "per-post assignments are not used in handoff")
    require("Unassigned screenshots" in DASHBOARD, "thread handoff does not distinguish unassigned screenshots")
    print("ok  picker: endpoint thumbnails, dedupe/range/suggest, zero default, post assignment")


def test_generate_and_agents() -> None:
    for copy in (
        'value="script"',
        "Surface audience questions",
        "Use your past performance as the default style anchor",
        "Critique against corpus",
    ):
        require(copy in DASHBOARD, f"Generate consolidation missing: {copy}")
    require('authFetch("/agents/detect")' in DASHBOARD, "agent detection missing")
    require("/agents/connect/${encodeURIComponent(client)}" in DASHBOARD, "one-click agent connect missing")
    require("Install Claude Desktop" in DASHBOARD, "zero-agent install CTA missing")
    require("Advanced: connection JSON" in DASHBOARD, "advanced connection disclosure missing")
    require("Open agent setup" not in DASHBOARD, "stale creator-path agent link remains")
    require("body.generate = true" in DASHBOARD, "BYO Path C opt-in missing")
    require("!hasWritingAgentBridge() && state.settings && state.settings.anthropic_key_set" in DASHBOARD, "BYO fallback incorrectly depends on agent config state")
    require("Generated using your Anthropic key (no agent)" in DASHBOARD, "BYO indicator missing")
    require("kind: mode" in DASHBOARD, "Tweet/Thread request does not send the backend kind contract")
    require("function writingBodyWithCredit" in DASHBOARD, "duplicate credit guard missing")
    require("bodyText.replace(creditStem, fullCredit)" in DASHBOARD, "existing creator credit is not upgraded in place")
    # U-02: the picker no longer auto-selects anything, so the old
    # reselect-guard condition is gone; assert the prefill itself is gone.
    require("!current && !query && selected" not in DASHBOARD, "auto-reselect crept back into the writing picker")
    require("els.writingSourceSearch.value = rowTitle(" not in DASHBOARD, "typed source title must never become the picker filter")
    audience = DASHBOARD.split("async function surfaceAudienceQuestions()", 1)[1].split("function renderLocalCorpusCritique", 1)[0]
    critique = DASHBOARD.split("async function critiqueWritingAgainstCorpus()", 1)[1].split("async function generateScriptInWriting()", 1)[0]
    require("ensureGenerateWorkspace" not in audience, "audience questions create a hidden Build workspace")
    require("ensureGenerateWorkspace" not in critique, "critique creates a hidden Build workspace")
    require("/workspace/critique" not in critique and "objectToMarkdown(data)" not in critique, "critique leaks raw backend machinery")
    print("ok  Generate: script features inline, context-aware agents, Path C indicator")


def test_activity_and_star() -> None:
    require("Retry, captions only" in DASHBOARD, "captions-only retry affordance missing")
    require('long_video_mode: "lite"' in DASHBOARD, "retry does not post lite recovery mode")
    require("activityErrorMessage" in DASHBOARD, "phase-level error copy missing")
    locked = "⭐ Star on GitHub"
    url = "https://github.com/ryanbiddy/uoink"
    require(locked in DASHBOARD and locked in SPLASH, "locked star copy missing from a placement")
    require(url in DASHBOARD and url in SPLASH, "GitHub URL missing from a placement")
    print("ok  Activity and GitHub star CTAs")


def main() -> int:
    test_sidebar()
    test_picker()
    test_generate_and_agents()
    test_activity_and_star()
    print("\nALL DASHBOARD v3.2.4 UI CONTRACT TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
