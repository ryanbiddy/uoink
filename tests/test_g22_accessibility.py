"""G-22 dashboard accessibility and keyboard interaction contract.

Run: python tests/test_g22_accessibility.py
"""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DASHBOARD = (ROOT / "assets" / "dashboard" / "index.html").read_text(encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_controls_have_real_names() -> None:
    for marker in (
        'id="searchInput" type="search" placeholder="search transcripts, titles, comments" aria-label="Search Library"',
        'id="platformFilter" aria-label="Filter by platform"',
        'id="sourceTypeFilter" aria-label="Filter by source type"',
        'id="channelFilter" aria-label="Filter by author"',
        'id="topicFilter" aria-label="Filter by topic"',
        'id="hookFilter" aria-label="Filter by hook"',
        'id="formatFilter" aria-label="Filter by format"',
        'id="performanceFilter" aria-label="Filter by performance"',
        'id="lengthFilter" aria-label="Filter by length"',
        'id="sortFilter" aria-label="Sort Library"',
        'id="anthropicKey" type="password" placeholder="Paste your Anthropic key" aria-label="Anthropic API key"',
        'id="channelHandle" type="text" placeholder="@yourhandle" aria-label="Channel handle"',
        'id="playlistUrl" type="url" placeholder="YouTube playlist URL" aria-label="YouTube playlist URL"',
        'id="podcastFeedUrl" type="url" placeholder="RSS feed URL" aria-label="Podcast RSS feed URL"',
        'id="allowedSitePattern" type="text" placeholder="example.com or *.docs.example.com" aria-label="Site domain pattern"',
        'id="outputFolder" type="text" value="Loading..." aria-label="Output folder path"',
    ):
        require(marker in DASHBOARD, f"missing control name: {marker}")
    print("ok  placeholder-led fields have accessible names")


def test_cards_keyboard_activate_detail() -> None:
    for marker in (
        'class="uoink-card ${htmlEscape(variant)}"',
        'tabindex="0" role="button" aria-label="Open ${title}"',
        'class="insight-card"',
        'tabindex="0" role="button" aria-label="Open ${htmlEscape(rowTitle(row))}"',
        'document.addEventListener("keydown", (event) => {',
        "isCardActivationKey(event)",
        ".uoink-card[role='button'], .insight-card[role='button']",
        "openYoinkDetail(rowFromCard(card));",
    ):
        require(marker in DASHBOARD, f"missing keyboard card marker: {marker}")
    print("ok  Library and For You cards open from keyboard")


def test_source_cards_have_list_semantics() -> None:
    for marker in (
        'id="sourceMap" role="list" aria-label="Supported source types"',
        'class="source-card" role="listitem" aria-labelledby="source-card-title-${index}"',
        'id="source-card-title-${index}"',
    ):
        require(marker in DASHBOARD, f"missing source-card semantic marker: {marker}")
    print("ok  source cards expose list semantics")


def test_modals_trap_focus_and_escape() -> None:
    for marker in (
        "const FOCUSABLE_SELECTOR",
        "function trapModalFocus",
        'event.key === "Escape"',
        "state.defaultAnchorsFocusTarget = document.activeElement;",
        "focusFirstIn(els.defaultAnchorsModal, document.getElementById(\"closeDefaultAnchors\"));",
        "restoreFocus(state.defaultAnchorsFocusTarget);",
        "els.defaultAnchorsModal.addEventListener(\"keydown\", (event) => trapModalFocus(event, els.defaultAnchorsModal, closeDefaultAnchorsModal));",
        "focusFirstIn(els.stopHelperConfirm, els.cancelStopHelper);",
        "trapModalFocus(event, els.stopHelperConfirm, closeStopHelperConfirm);",
    ):
        require(marker in DASHBOARD, f"missing modal focus marker: {marker}")
    print("ok  modals trap focus, close on Escape, and restore focus")


def main() -> int:
    test_controls_have_real_names()
    test_cards_keyboard_activate_detail()
    test_source_cards_have_list_semantics()
    test_modals_trap_focus_and_escape()
    print("\nALL G-22 ACCESSIBILITY TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
