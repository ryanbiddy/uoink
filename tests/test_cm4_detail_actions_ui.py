"""CM-4.3: saved-source detail has one primary action and an overflow."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DASHBOARD = (ROOT / "assets" / "dashboard" / "index.html").read_text(
    encoding="utf-8"
)


def test_detail_actions_have_one_primary_and_one_overflow() -> None:
    start = DASHBOARD.index('<div class="inline-row yoink-actions">')
    end = DASHBOARD.index("</details>", start) + len("</details>")
    actions = DASHBOARD[start:end]

    assert actions.count('class="button primary"') == 1
    assert 'id="yoinkWriteFrom"' in actions
    assert '<details class="action-menu yoink-action-menu" id="yoinkActionMenu">' in actions
    assert '<summary class="button ghost">More actions</summary>' in actions
    for control_id in (
        "yoinkOpenFolder",
        "yoinkOpenMarkdown",
        "yoinkRetryCapture",
        "yoinkRetranscribe",
        "yoinkEvidence",
    ):
        assert f'id="{control_id}"' in actions


def test_detail_overflow_closes_after_an_action() -> None:
    assert 'document.querySelectorAll("#yoinkActionMenu button")' in DASHBOARD
    assert 'document.getElementById("yoinkActionMenu").removeAttribute("open")' in DASHBOARD
