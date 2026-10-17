"""CM-4.5: common Library filters lead; advanced filters use disclosure."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DASHBOARD = (ROOT / "assets" / "dashboard" / "index.html").read_text(
    encoding="utf-8"
)


def test_advanced_library_filters_are_in_a_closed_disclosure() -> None:
    grid_start = DASHBOARD.index('<div class="control-grid">')
    grid_end = DASHBOARD.index("</div>\n          <div id=\"dateRangeError\"", grid_start)
    grid = DASHBOARD[grid_start:grid_end]
    details_start = grid.index('<details class="library-more-filters"')
    details_end = grid.index("</details>", details_start)
    primary = grid[:details_start] + grid[details_end:]
    advanced = grid[details_start:details_end]

    # UI re-haul (SPEC "Library"): the common controls are the one box, the
    # type chips and the one sort control; the topic list with counts sits in
    # the sidebar. Platform, type, author and the topic menu moved into the
    # disclosure with the other advanced filters.
    for control_id in (
        "searchInput",
        "libraryKinds",
        "sortFilter",
    ):
        assert f'id="{control_id}"' in primary
    assert primary.count('data-library-kind="') == 5
    sidebar = DASHBOARD[DASHBOARD.index('<aside class="sidebar"'):DASHBOARD.index("</aside>")]
    assert 'id="topicOverview"' in sidebar
    for control_id in (
        "platformFilter",
        "sourceTypeFilter",
        "channelFilter",
        "topicFilter",
        "hookFilter",
        "formatFilter",
        "performanceFilter",
        "lengthFilter",
        "dateFrom",
        "dateTo",
    ):
        assert f'id="{control_id}"' in advanced
    assert '<details class="library-more-filters" id="libraryMoreFilters" open>' not in grid


def test_applied_filters_render_as_removable_chips() -> None:
    assert "function renderLibraryFilterChips()" in DASHBOARD
    assert 'data-remove-library-filter="${htmlEscape(entry.key)}"' in DASHBOARD
    assert "function removeLibraryFilter(key)" in DASHBOARD
    assert 'event.target.closest("[data-remove-library-filter]")' in DASHBOARD
    assert 'id="advancedFilterCount">0</span>' in DASHBOARD
