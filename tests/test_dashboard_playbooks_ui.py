"""T7 + F34: execute the shipped dashboard with mocked I/O, no helper or network."""
from pathlib import Path
import re
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
PAGE = (ROOT / "assets/dashboard/index.html").read_text(encoding="utf-8")
HARNESS = ROOT / "tests/js/dashboard_playbooks_test.cjs"


@pytest.mark.parametrize("scenario", [
    "scopes", "controls", "bridge", "paid", "copy_prompt", "in_flight",
    "provider_error", "resource_error", "transport_error", "packet_error",
    "mcp_error_envelope", "bridge_error", "citations", "save", "save_failure", "draft_posts",
])
def test_dashboard_playbooks_behavior(scenario):
    result = subprocess.run(
        ["node", str(HARNESS), scenario], cwd=ROOT,
        capture_output=True, text=True, encoding="utf-8", timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_research_markup_keyboard_and_theme_contract():
    markup, script = PAGE.split("<script>", 1)
    for mode in ("tweet", "thread", "blog", "script", "research", "newsletter"):
        assert f'name="writingMode" value="{mode}"' in markup
    for name in ("outlier-posts", "transcript-intel", "comment-mining",
                 "creator-teardown", "repurpose-pack"):
        assert f'<option value="{name}">' in markup
    for control in ("researchPlaybook", "researchScope", "researchCaptureSearch",
                    "researchTopic", "researchPrompt", "researchCitedSource", "researchPostMode"):
        assert f'for="{control}"' in markup
    assert 'id="researchControls"' in markup and '<fieldset' in markup
    assert 'id="researchStatus" role="status" aria-live="polite"' in markup
    assert 'id="researchWarnings" role="status" aria-live="polite"' in markup
    assert 'id="researchPreviewPanel" aria-label="Research report"' in markup
    assert 'id="researchPrompt" readonly' in markup
    assert 'addEventListener("click", generateWriting)' in script
    assert 'bindResearchControls();' in script
    for name in ("copyResearchPrompt", "saveResearchDraft", "draftPostsFromResearch"):
        assert f'addEventListener("click", {name})' in script
    css = markup.split("<style>", 1)[1].split("</style>", 1)[0]
    research_css = css.split(".research-controls {", 1)[1].split(".get-extension {", 1)[0]
    for token in ("--text", "--text-2", "--action", "--line-strong", "--surface"):
        assert f"var({token})" in research_css
    assert "min-height: 32px" in research_css
    assert "outline: 2px solid var(--action); outline-offset: 2px" in research_css
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b|https?://|@import", research_css)
    assert not re.search(r'<(?:link|script)[^>]+(?:href|src)="https?://', markup)


def test_http_error_fixtures_match_reviewed_route_shapes():
    server = (ROOT / "server.py").read_text(encoding="utf-8")
    route = server.split("def _handle_playbooks_run(", 1)[1].split("def _handle_writing_draft_save", 1)[0]
    assert '"ok": False, "error": {' in route  # provider error, HTTP 200
    assert '"code": "anthropic_error"' in route
    assert "except _lr.ResourceError as exc:" in route
    assert "result = exc.envelope()" in route  # versioned domain refusal
    assert 'return self._send_json(200, result)' in route
