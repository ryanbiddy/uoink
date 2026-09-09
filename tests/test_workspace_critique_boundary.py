"""Workspace critique UI must not present context assembly as LLM analysis."""
from __future__ import annotations

import tempfile
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import index as index_mod  # noqa: E402
import workspaces  # noqa: E402


DASHBOARD = (ROOT / "assets" / "dashboard" / "index.html").read_text(
    encoding="utf-8"
)


def test_dashboard_names_the_context_only_action_honestly() -> None:
    assert 'id="prepareWorkspaceCritiqueContext"' in DASHBOARD
    assert "Prepare critique context" in DASHBOARD
    assert (
        "This prepares corpus context for a connected agent; "
        "Uoink does not run the critique itself."
    ) in DASHBOARD
    assert "Run critique" not in DASHBOARD
    assert "runWorkspaceCritique" not in DASHBOARD

    action = DASHBOARD.split(
        "async function prepareWorkspaceCritiqueContext()", 1
    )[1].split("async function loadScripts()", 1)[0]
    assert 'authFetch("/workspace/critique"' in action
    assert "findings" not in action
    assert "Context ready for a connected agent" in action


def test_context_only_phase_does_not_write_a_critique_row() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        idx = index_mod.Index.open(Path(temp_dir) / "index.db")
        try:
            workspace = workspaces.create_workspace(idx, topic="hooks")
            result = workspaces.critique_against_corpus(
                idx, workspace["id"], draft_text="rough draft"
            )
            assert result["mode"] == "context_only"
            assert workspaces.critique_log_for(idx, workspace["id"]) == []
        finally:
            idx.close()
