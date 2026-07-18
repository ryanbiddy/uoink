"""CM-4.4: Library writing handoff is present but visually secondary."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DASHBOARD = (ROOT / "assets" / "dashboard" / "index.html").read_text(
    encoding="utf-8"
)


def test_library_card_write_action_is_compact_and_secondary() -> None:
    card = DASHBOARD[
        DASHBOARD.index("function cardHtml(row)")
        : DASHBOARD.index("async function loadThumbnail")
    ]

    assert 'class="button ghost card-write"' in card
    assert 'class="button primary card-write"' not in card
    assert ">Write from this</button>" in card
    assert "data-write-from" in card


def test_library_card_write_action_is_not_full_width() -> None:
    style = DASHBOARD[
        DASHBOARD.index(".button.ghost.card-write {")
        : DASHBOARD.index("/* Hooks explainer", DASHBOARD.index(".button.ghost.card-write {"))
    ]

    assert "justify-self: start;" in style
    assert "width: auto;" in style
    assert "width: 100%;" not in style
