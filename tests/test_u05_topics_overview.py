"""U-05 -- Topics overview on Library (UX-13).

Run: python tests/test_u05_topics_overview.py  (also collected by pytest)

Topics existed in four scattered places (filter dropdown, Generate chips,
Settings editor, For You gaps) and none was an overview; 8 of 31 uoinks
sat in "Uncategorized" with no screen surfacing it. The overview's
contract (live proof: handoff/qa-harness-playwright/
u05-topics-overview-check.js):

1. A #topicOverview chip row above the Library grid, fed by the
   corpus-wide /library/facets counts (not the loaded page).
2. Uncategorized is visually flagged and carries a hygiene hint.
3. Chips click through to a filtered Library via the real topic filter;
   clicking the active chip clears it.
"""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DASHBOARD = (ROOT / "assets" / "dashboard" / "index.html").read_text(
    encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def pos(needle: str) -> int:
    require(needle in DASHBOARD, f"marker missing: {needle}")
    return DASHBOARD.index(needle)


def test_overview_markup_above_grid() -> None:
    require(pos('id="topicOverview"') < pos('id="libraryGrid"'),
            "topic overview must sit above the library grid")
    print("ok  overview row sits above the grid")


def test_renderer_uses_corpus_facets() -> None:
    body = DASHBOARD[pos("function renderTopicOverview()"):pos("function facetSourceKeys")]
    require("state.facets" in body and ".topic" in body,
            "overview must read the corpus-wide facet counts")
    require("uncategorized" in body,
            "Uncategorized must get its own visual treatment")
    require("no topic yet" in body,
            "Uncategorized chip needs the hygiene hint copy")
    require("sort" in body, "topics render biggest-first")
    facets_loader = DASHBOARD[pos("async function loadLibraryFacets()"):pos("function renderTopicOverview()")]
    require("renderTopicOverview()" in facets_loader,
            "facets load must render the overview")
    print("ok  renderer reads /library/facets counts, flags Uncategorized")


def test_click_through_filters_library() -> None:
    handler = DASHBOARD[pos('closest("[data-topic-overview]")'):]
    handler = handler[:handler.index("loadLibrary({ reset: true })") + 40]
    require("els.topicFilter.value = next" in handler,
            "chip click must drive the real topic filter")
    require('state.filters.topic === value ? "" : value' in handler,
            "clicking the active chip must clear the filter")
    print("ok  chips click through to a filtered Library, toggle to clear")


def main() -> None:
    test_overview_markup_above_grid()
    test_renderer_uses_corpus_facets()
    test_click_through_filters_library()
    print("\nall green")


if __name__ == "__main__":
    main()
