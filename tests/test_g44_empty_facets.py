"""G-44 empty facet dropdown contract (E2E D6).

A facet with zero tagged sources renders as a labeled, disabled empty state
instead of an "all"-only dropdown indistinguishable from a broken control.

Run: python tests/test_g44_empty_facets.py
"""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DASHBOARD = (ROOT / "assets" / "dashboard" / "index.html").read_text(encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_empty_facets_get_labeled_disabled_state() -> None:
    require("const FACET_EMPTY_STATES = {" in DASHBOARD, "facet empty-state table missing")
    require("if (empty && !options.length && !state.facetsFallback) {" in DASHBOARD,
            "syncOptions does not branch on a loaded-but-empty facet")
    require("select.disabled = true;" in DASHBOARD, "empty facet control is not disabled")
    require("select.title = empty.title;" in DASHBOARD, "empty facet control carries no explanation")
    for label in (
        "Format: none tagged yet",
        "Performance: none tagged yet",
        "Length: none tagged yet",
        "Hook: none tagged yet",
        "Channel: none saved yet",
        "Topic: none saved yet",
    ):
        require(label in DASHBOARD, f"empty-state label missing: {label}")
    print("ok  loaded-but-empty facets render a labeled, disabled state")


def test_fallback_and_populated_paths_stay_usable() -> None:
    require("select.disabled = false;" in DASHBOARD,
            "populated facets are never re-enabled after an empty pass")
    require('select.removeAttribute("title");' in DASHBOARD,
            "stale empty-state tooltip survives a repopulated facet")
    # The fallback path (facets request failed) keeps built-in defaults, so
    # the empty branch must be gated on state.facetsFallback.
    require("state.facetsFallback" in DASHBOARD, "facets fallback flag missing")
    print("ok  populated and fallback facets keep the normal dropdowns")


def test_every_library_facet_is_covered() -> None:
    for key in ("channel", "topic", "hook_type", "format", "performance", "length"):
        require(f"FACET_EMPTY_STATES.{key}" in DASHBOARD,
                f"facet {key} does not pass its empty state to syncOptions")
    print("ok  all six Library facet dropdowns carry an empty state")


def main() -> int:
    test_empty_facets_get_labeled_disabled_state()
    test_fallback_and_populated_paths_stay_usable()
    test_every_library_facet_is_covered()
    print("\nALL G-44 EMPTY FACET TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
