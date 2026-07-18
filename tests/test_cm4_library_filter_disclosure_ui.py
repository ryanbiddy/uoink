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

    for control_id in (
        "searchInput",
        "platformFilter",
        "sourceTypeFilter",
        "channelFilter",
        "topicFilter",
        "sortFilter",
    ):
        assert f'id="{control_id}"' in primary
    for control_id in (
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
