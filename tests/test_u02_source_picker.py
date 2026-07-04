"""U-02 -- Generate source picker rebuild (UX-08, UX-05).

Run: python tests/test_u02_source_picker.py  (also collected by pytest tests/)

Static UI contract for the rebuilt picker. The old picker pre-filled the
search input with the newest uoink's title, filtered the dropdown against
that title (1 of 31 sources visible), auto-reselected on clear, and capped
the rendered list at 20. The rebuild's contract:

1. Dedicated corpus-wide list, newest-first: the picker fetches
   /memory/search?limit=200 itself instead of leaning on the paged,
   filter-shaped state.library.
2. No prefill, no auto-select: the render pass never writes the hidden
   source id or the input value; browsing starts empty and shows everything.
3. No display cap: every filtered row renders (the list scrolls).
4. Selection collapses to a two-line chip (thumbnail, wrapped title, clear
   button) so the title can never become the filter text.
5. Keyboard nav: ArrowDown/ArrowUp move an active option with
   aria-activedescendant, Enter picks, Escape closes.

Playwright proof lives at handoff/qa-harness-playwright/u02-source-picker-
check.js; this file keeps the contract pinned in CI.
"""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DASHBOARD = (ROOT / "assets" / "dashboard" / "index.html").read_text(
    encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def section(start: str, end: str) -> str:
    require(start in DASHBOARD, f"marker missing: {start}")
    body = DASHBOARD.split(start, 1)[1]
    require(end in body, f"end marker missing after {start}: {end}")
    return body.split(end, 1)[0]


def test_dedicated_corpus_list() -> None:
    require("/memory/search?limit=200" in DASHBOARD,
            "picker must fetch its own corpus-wide source list")
    require("writingSourceRows: []" in DASHBOARD,
            "dedicated picker rows missing from state")
    require("function writingSourceRowsAll()" in DASHBOARD,
            "picker must read its own rows, not the paged library")
    require("state.writingSourceLoaded = false;" in DASHBOARD,
            "library refresh must invalidate the picker cache")
    print("ok  picker owns an unfiltered corpus-wide list")


def test_no_prefill_no_autoselect_no_cap() -> None:
    body = section("function syncWritingSourceOptions()",
                   "function syncWritingGenerateState")
    require("els.writingSource.value =" not in body,
            "render pass must never write the hidden source id")
    require("els.writingSourceSearch.value =" not in body,
            "render pass must never write the input value (the old prefill)")
    require(".slice(0, 20)" not in body and ".slice(0, 80)" not in body,
            "the rendered list must not be capped; it scrolls instead")
    require("els.writingSourceSearch.value = rowTitle(" not in DASHBOARD,
            "a selected title must never become the filter text")
    print("ok  no prefill, no auto-select, no display cap")


def test_selection_collapses_to_chip() -> None:
    require('id="writingSourceChip"' in DASHBOARD
            and 'id="writingSourceChipMain"' in DASHBOARD
            and 'id="writingSourceChipClear"' in DASHBOARD,
            "selected-source chip markup missing")
    chip = section("function renderWritingSourceChip()",
                   "function clearWritingSource(")
    require("combo-thumb" in chip and "job-sub" in chip,
            "chip must carry the thumbnail and channel/duration subtitle")
    require('aria-label="Clear selected source"' in DASHBOARD,
            "clear button needs an accessible label")
    require("-webkit-line-clamp: 2" in DASHBOARD,
            "chip title must wrap to two lines instead of truncating (UX-05)")
    print("ok  selection renders as a two-line chip with clear")


def test_keyboard_nav() -> None:
    require("function moveWritingSourceActive(" in DASHBOARD,
            "keyboard active-option mover missing")
    require('aria-activedescendant' in DASHBOARD,
            "active option must be exposed via aria-activedescendant")
    keydown = section('els.writingSourceSearch.addEventListener("keydown"',
                      'els.writingSourceChipMain.addEventListener')
    for key in ('"ArrowDown"', '"ArrowUp"', '"Enter"', '"Escape"'):
        require(key in keydown, f"picker keydown must handle {key}")
    require('aria-autocomplete="list"' in DASHBOARD,
            "combobox input should declare aria-autocomplete")
    print("ok  arrow keys, enter, escape wired")


def main() -> None:
    test_dedicated_corpus_list()
    test_no_prefill_no_autoselect_no_cap()
    test_selection_collapses_to_chip()
    test_keyboard_nav()
    print("\nall green")


if __name__ == "__main__":
    main()
