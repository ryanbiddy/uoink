"""Dashboard claim actions must match the agent-owned compute boundary."""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DASHBOARD = (ROOT / "assets" / "dashboard" / "index.html").read_text(
    encoding="utf-8"
)
SERVER = (ROOT / "server.py").read_text(encoding="utf-8")
CHANGELOG = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")


def test_dashboard_does_not_present_an_empty_write_as_a_claim_scan() -> None:
    assert 'id="runEvidenceClaims"' not in DASHBOARD
    assert "data-run-claims" not in DASHBOARD
    assert 'authFetch("/claims/extract"' not in DASHBOARD
    assert (
        'JSON.stringify({ video_id: videoId, claims: [], mode: "agent" })'
        not in DASHBOARD
    )
    assert "Run claim scan" not in CHANGELOG


def test_dashboard_explains_that_claims_arrive_from_a_connected_agent() -> None:
    assert "A connected agent must submit claims before they appear here." in DASHBOARD
    assert 'id="reloadEvidence"' in DASHBOARD


def test_server_does_not_claim_that_a_dead_setting_gates_automatic_work() -> None:
    assert "calling agent does the LLM" in SERVER
    assert "gates batch / auto-verify flows" not in SERVER
