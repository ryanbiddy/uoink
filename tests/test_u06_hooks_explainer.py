"""U-06 -- in-app hooks explainer + hook-taxonomy reconciliation (UX-14).

Run: python tests/test_u06_hooks_explainer.py  (also collected by pytest)

Hook vocabulary was everywhere (card badges, Library filter, Generate
picker) and defined nowhere in-app; the only explainer was an external
link on a hidden route. And the Generate picker was seeded with raw
classification facet values (authority, demo) that the backend's
normalize_hook_lens rejects with a 400.

Contract (live proof: handoff/qa-harness-playwright/
u06-hooks-explainer-check.js):

1. #hookExplainer modal fed by GET /hooks/guide (the classifier's own
   definitions; U-01 serves them from the same source as the prompt).
2. Linked from every hook badge/picker: card badges are data-hook-explain
   buttons, Library summary line and Generate's Hook pattern label carry
   "what's a hook?" affordances.
3. The Generate lens picker renders ONLY writing_studio.HOOK_LENS_TYPES
   values, decorated with corpus counts through an explicit
   classification->lens map. Decision logged in handoff/DECISIONS-LOG.md
   (2026-07-04, map-don't-unify).
"""
from __future__ import annotations

import re
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import writing_studio  # noqa: E402


ROOT = Path(__file__).resolve().parent.parent
DASHBOARD = (ROOT / "assets" / "dashboard" / "index.html").read_text(
    encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def pos(needle: str) -> int:
    require(needle in DASHBOARD, f"marker missing: {needle}")
    return DASHBOARD.index(needle)


def test_explainer_fed_by_hooks_guide() -> None:
    require('id="hookExplainer"' in DASHBOARD, "explainer modal missing")
    require('fetch("/hooks/guide")' in DASHBOARD,
            "explainer must read the classifier's own definitions")
    require("first 10 seconds" in DASHBOARD, "the what-is-a-hook sentence")
    print("ok  explainer modal reads /hooks/guide")


def test_linked_from_badges_and_pickers() -> None:
    card = DASHBOARD[pos("function cardHtml(row)"):pos("async function loadThumbnail")]
    require("data-hook-explain" in card and "hook-chip" in card,
            "card hook badges must open the explainer")
    summary = DASHBOARD[pos('id="resultSummary"'):pos('id="libraryGrid"')]
    require("data-hook-explain" in summary,
            "Library needs a what's-a-hook affordance near the filters")
    advanced = DASHBOARD[pos('id="generateAdvanced"'):pos('id="generateWriting"')]
    require("data-hook-explain" in advanced,
            "Generate's Hook pattern label needs the affordance")
    explain_branch = pos('closest("[data-hook-explain]")')
    card_branch = pos('const card = event.target.closest("[data-folder]")')
    require(explain_branch < card_branch,
            "explainer click must win over card-open for badges inside cards")
    print("ok  linked from card badges, Library, and Generate")


def test_lens_catalog_matches_backend() -> None:
    catalog = DASHBOARD[pos("const HOOK_LENS_CATALOG"):pos("function renderGenerateHookChoices()")]
    values = set(re.findall(r'value: "([a-z_]+)"', catalog))
    require(values == set(writing_studio.HOOK_LENS_TYPES),
            f"lens catalog must mirror HOOK_LENS_TYPES exactly: {values ^ set(writing_studio.HOOK_LENS_TYPES)}")
    for lens, directive in writing_studio.HOOK_LENS_TYPES.items():
        require(directive in catalog,
                f"directive drifted from writing_studio for {lens}")
    render = DASHBOARD[pos("function renderGenerateHookChoices()"):pos("async function loadHookGuide()")]
    require("HOOK_LENS_CATALOG" in render and "lens.classification" in render,
            "picker must render the catalog with mapped corpus counts")
    print("ok  lens picker mirrors writing_studio.HOOK_LENS_TYPES with mapped counts")


def test_decision_logged() -> None:
    log = (ROOT.parent.parent / "handoff" / "DECISIONS-LOG.md")
    if not log.exists():
        print("skip decision-log check (handoff not present in this checkout)")
        return
    text = log.read_text(encoding="utf-8")
    require("map, don't unify" in text and "U-06" in text,
            "hook-taxonomy call must be logged in DECISIONS-LOG.md")
    print("ok  decision logged")


def main() -> None:
    test_explainer_fed_by_hooks_guide()
    test_linked_from_badges_and_pickers()
    test_lens_catalog_matches_backend()
    test_decision_logged()
    print("\nall green")


if __name__ == "__main__":
    main()
