"""G-31 sidebar badges should explain what each number counts.

Run: python tests/test_g31_sidebar_badge_labels.py
"""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DASHBOARD = (ROOT / "assets" / "dashboard" / "index.html").read_text(encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    for marker in (
        'data-nav-label="Library"',
        'data-nav-label="Sources"',
        'data-nav-label="For You"',
        'data-nav-label="Generate"',
        'data-nav-label="View activity"',
        'title="0 saved sources"',
        'title="0 source types"',
        'title="0 suggestions"',
        'title="0 Generate items"',
        'title="0 active jobs"',
        "function setSidebarBadge(el, count, label, options = {})",
        'button.setAttribute("aria-label", `${navLabel}, ${countLabel}`)',
    ):
        require(marker in DASHBOARD, f"sidebar badge label contract missing: {marker}")

    for stale in (
        "libraryNavCount.textContent",
        "sourcesNavCount.textContent",
        "forYouNavCount.textContent",
        "writingNavCount.textContent",
        "activityNavCount.textContent",
    ):
        require(stale not in DASHBOARD, f"direct sidebar badge write remains: {stale}")

    for call in (
        'setSidebarBadge(els.libraryNavCount, visibleCount, "saved sources", { hideWhenZero: true })',
        'setSidebarBadge(els.sourcesNavCount, SOURCE_CAPABILITIES.length, "source types")',
        'setSidebarBadge(els.forYouNavCount, worth.length + connections.length + gaps.length + anchors.length, "suggestions")',
        'setSidebarBadge(els.activityNavCount, activeCount, "active jobs")',
        "setSidebarBadge(els.writingNavCount, generateBadgeCount, generateBadgeLabel)",
    ):
        require(call in DASHBOARD, f"sidebar badge setter missing: {call}")

    print("ok  sidebar count badges have explicit labels and tooltips")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
