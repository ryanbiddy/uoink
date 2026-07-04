"""U-04 -- "Write from this" CTA on Library cards + Uoink detail (UX-09).

Run: python tests/test_u04_write_from_this.py  (also collected by pytest)

Static contract for the deep link (live proof:
handoff/qa-harness-playwright/u04-write-from-this-check.js):

1. Every library card template carries a data-write-from button.
2. The Uoink detail page-head has #yoinkWriteFrom as its primary action
   (Evidence steps down to ghost).
3. writeFromSource() switches to Generate, waits for the picker corpus,
   and selects through selectWritingSourceById.
4. In the global click handler, the data-write-from branch runs BEFORE the
   [data-folder] card branch, or the button would open the detail view
   instead.
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


def test_card_cta() -> None:
    card = DASHBOARD[pos("function cardHtml(row)"):pos("async function loadThumbnail")]
    require('data-write-from="${id}"' in card,
            "every library card must render the Write from this CTA")
    require("Write from this" in card, "card CTA label")
    print("ok  every card template carries the CTA")


def test_detail_primary() -> None:
    require('id="yoinkWriteFrom"' in DASHBOARD, "detail CTA missing")
    head = DASHBOARD[pos('id="yoinkOpenFolder"'):pos('id="yoinkWriteFrom"') + 60]
    require('class="button primary" type="button" id="yoinkWriteFrom"' in DASHBOARD,
            "detail CTA must be the primary action")
    require('class="button ghost" type="button" id="yoinkEvidence"' in DASHBOARD,
            "Evidence steps down to ghost so one primary remains")
    require("yoinkWriteFrom.disabled" in DASHBOARD,
            "detail CTA must disable without a loaded uoink")
    print("ok  detail head: Write from this is the one primary")


def test_deep_link_function() -> None:
    body = DASHBOARD[pos("async function writeFromSource"):pos("async function selectWritingSourceById")]
    require('switchTab("writing")' in body, "deep link must land on Generate")
    require("await loadWritingSources()" in body,
            "deep link must wait for the picker corpus")
    require("selectWritingSourceById(writingRowId(row))" in body,
            "deep link must select through the picker's own id scheme")
    require("clearWritingSource" in body and "showToast" in body,
            "unresolvable source must fall back to browse mode with honest copy")
    print("ok  writeFromSource lands picked, falls back honestly")


def test_click_order() -> None:
    write_branch = pos('event.target.closest("[data-write-from]")')
    card_branch = pos('const card = event.target.closest("[data-folder]")')
    require(write_branch < card_branch,
            "data-write-from branch must run before the card-open branch")
    print("ok  CTA click wins over card-open")


def main() -> None:
    test_card_cta()
    test_detail_primary()
    test_deep_link_function()
    test_click_order()
    print("\nall green")


if __name__ == "__main__":
    main()
