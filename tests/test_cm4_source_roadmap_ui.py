"""CM-4.2: shipped capture sources lead; planned sources stay collapsed."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DASHBOARD = (ROOT / "assets" / "dashboard" / "index.html").read_text(
    encoding="utf-8"
)


def test_sources_separate_ready_and_planned_entries() -> None:
    render = DASHBOARD[
        DASHBOARD.index("function renderSources()")
        : DASHBOARD.index("// V-2a: universal")
    ]

    assert 'source.status !== "planned"' in render
    assert 'source.status === "planned"' in render
    assert "ready.map((source, index)" in render
    assert "planned.map((source, index)" in render
    assert '"capture-ready source types"' in render


def test_planned_sources_are_collapsed_and_visually_secondary() -> None:
    assert '<h2>Capture now</h2>' in DASHBOARD
    assert '<details class="source-roadmap" id="sourceRoadmap">' in DASHBOARD
    assert '<details class="source-roadmap" id="sourceRoadmap" open>' not in DASHBOARD
    assert 'class="source-roadmap-row" role="listitem"' in DASHBOARD
    assert 'id="sourceRoadmapList" role="list" aria-label="Planned source types"' in DASHBOARD
