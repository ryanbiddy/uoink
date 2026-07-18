"""CM-4.1: Library cards show health exceptions, not healthy decoration."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DASHBOARD = (ROOT / "assets" / "dashboard" / "index.html").read_text(
    encoding="utf-8"
)


def test_library_card_health_is_exception_only() -> None:
    function = DASHBOARD[
        DASHBOARD.index("function healthException(health)")
        : DASHBOARD.index("function videoIdOf(row)")
    ]
    card = DASHBOARD[
        DASHBOARD.index("function cardHtml(row)")
        : DASHBOARD.index("async function loadThumbnail")
    ]

    assert 'if (!issues.length) return "";' in function
    assert '"Needs attention"' in function
    assert '"Still working"' in function
    assert "${healthException(row.health)}" in card
    assert "healthDots(row.health)" not in card


def test_library_legend_does_not_label_healthy_cards() -> None:
    legend_start = DASHBOARD.index('<span class="health-legend"')
    legend_end = DASHBOARD.index("</span>\n          </div>", legend_start)
    legend = DASHBOARD[legend_start:legend_end]

    assert ">ready<" not in legend
    assert "still working" in legend
    assert "needs attention" in legend
