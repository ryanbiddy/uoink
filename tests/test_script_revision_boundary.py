"""Script revision UI must distinguish context assembly from persistence."""
from __future__ import annotations

import tempfile
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import index as index_mod  # noqa: E402
import scripts  # noqa: E402
import workspaces  # noqa: E402


DASHBOARD = (ROOT / "assets" / "dashboard" / "index.html").read_text(
    encoding="utf-8"
)


def test_dashboard_names_both_revision_phases_honestly() -> None:
    assert "Run revision / save version" not in DASHBOARD
    assert 'id="reviseScript">Prepare revision<' in DASHBOARD
    assert 'id="saveScriptRevision">Prepare revision context<' in DASHBOARD
    assert (
        "Uoink prepares context for a connected agent. "
        "Paste a revised script to save a new version."
    ) in DASHBOARD
    assert "Save pasted revision" in DASHBOARD

    action = DASHBOARD.split(
        "async function reviseCurrentScript", 1
    )[1].split("async function deriveCurrentShotList", 1)[0]
    assert "Revision context ready for a connected agent" in action
    assert "Script v${data.version || \"\"} saved." in action


def test_revision_context_phase_does_not_save_a_new_version() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        idx = index_mod.Index.open(Path(temp_dir) / "index.db")
        try:
            workspace = workspaces.create_workspace(idx, topic="hooks")
            first = scripts.generate_script(
                idx,
                workspace["id"],
                script={
                    "hook": "Original hook",
                    "beats": [],
                    "source_yoinks": [],
                },
            )
            before = scripts.list_scripts(idx, workspace_id=workspace["id"])
            result = scripts.revise_script(
                idx,
                first["id"],
                revision_target="Tighten the opening",
            )
            after = scripts.list_scripts(idx, workspace_id=workspace["id"])
            assert result["mode"] == "revision_context"
            assert len(before) == len(after) == 1
        finally:
            idx.close()
