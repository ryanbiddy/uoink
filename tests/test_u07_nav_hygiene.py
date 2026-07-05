"""U-07 -- nav hygiene (UX-15, UX-12, UX-16, UX-17).

Run: python tests/test_u07_nav_hygiene.py  (also collected by pytest)

Live proof: handoff/qa-harness-playwright/u07-nav-hygiene-check.js.
"""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DASHBOARD = (ROOT / "assets" / "dashboard" / "index.html").read_text(
    encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_orphan_routes_get_nav_state() -> None:
    require('data-tab-button="activity"' in DASHBOARD,
            "Activity needs a real nav entry (UX-15)")
    require('data-tab-button="about"' in DASHBOARD,
            "About needs a real nav entry (UX-15)")
    require("const NAV_OWNER" in DASHBOARD
            and '"library"' in DASHBOARD.split("const NAV_OWNER", 1)[1][:200],
            "panels without nav entries must highlight their logical parent")
    for orphan in ("yoink:", "evidence:", "features:"):
        require(orphan in DASHBOARD.split("const NAV_OWNER", 1)[1][:200],
                f"NAV_OWNER must cover {orphan}")
    print("ok  Activity + About in nav; orphan panels map to a parent")


def test_activity_zero_state_headline() -> None:
    require('id="activityCount"' not in DASHBOARD,
            "the bare count headline should be gone")
    require("Nothing uoinking" in DASHBOARD,
            "zero-state headline copy missing (UX-17)")
    require("in flight <em>uoinking...</em>`" in DASHBOARD,
            "non-zero headline keeps the in-flight sentence")
    print("ok  activity headline reads as a sentence at zero")


def test_one_connection_json_disclosure() -> None:
    require(DASHBOARD.count("Advanced: connection JSON") == 1,
            "exactly one connection-JSON disclosure (UX-16)")
    print("ok  one connection-JSON disclosure")


def test_one_anchor_manager() -> None:
    require('id="writingAnchorCount"' not in DASHBOARD,
            "the form's duplicate anchor counter should be gone (UX-12)")
    require('id="writingAnchorSelect"' in DASHBOARD
            and 'id="manageAnchorsLink"' in DASHBOARD,
            "per-draft anchor selector with a manage link missing")
    require("function syncWritingStyleUi()" in DASHBOARD,
            "anchor selector must hide for Default voice")
    require("Anchors for this draft" in DASHBOARD,
            "the selector needs its purpose label")
    print("ok  one manager; form list is a labeled per-draft selector")


def main() -> None:
    test_orphan_routes_get_nav_state()
    test_activity_zero_state_headline()
    test_one_connection_json_disclosure()
    test_one_anchor_manager()
    print("\nall green")


if __name__ == "__main__":
    main()
