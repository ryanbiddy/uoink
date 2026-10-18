"""Writing drafts never overwrite another source or lose edits (D21, D22).

D21: saveWritingDraft() in assets/dashboard/index.html sent the last saved
draft id whatever source was picked. POST /writing/draft updates the row whose
id it gets, source and all (server.py _handle_writing_draft_save ->
index.save_writing_draft), so saving a draft for video B overwrote the saved
draft for video A. The id is now reused only while the source the draft was
saved from (or recovered with) is the one picked.

D22: Generate/Revise wrote "Preparing your draft..." into the preview and the
composer and turned Save on, so a failed or agent-less run lost hand edits and
Save could store the placeholder. Progress and failures now show in their own
status line, Save/Copy/Revise (and Generate) stay off while a run is going,
and the draft on screen is replaced only when a run returns a draft.

Runs tests/js/dash_draft_safety_test.mjs, which loads the REAL dashboard
script (everything before init()) into a node:vm context over a fake page
holding every id the markup declares. The fake helper keeps drafts the way
index.save_writing_draft does (insert without an id, update in place with
one), and generate requests can be held mid-run:

  source_switch   -- save for A, switch to B (or clear the source), save: A's
                     draft is untouched and B gets its own; saving again from
                     the same source still updates in place.
  recovered_draft -- a draft recovered after a reload keeps its source; its
                     id is reused only once that source is picked again.
  generate_run    -- while Generate runs the preview and composer keep the
                     draft, progress shows in the status line, the actions are
                     off and a second click starts nothing; a failure keeps
                     hand edits or the earlier draft and says so; a success
                     replaces the draft.
  no_agent        -- a run with no writing agent keeps hand edits and earlier
                     output; with nothing written the setup notice still fills
                     the preview.
  script_run      -- the script path follows the same rules.

No network: fetch is a stub inside the harness.
"""
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HARNESS = REPO_ROOT / "tests" / "js" / "dash_draft_safety_test.mjs"

GROUPS = [
    "source_switch",
    "recovered_draft",
    "generate_run",
    "no_agent",
    "script_run",
]


@pytest.mark.parametrize("group", GROUPS)
def test_dash_draft_safety(group):
    assert HARNESS.exists(), f"missing harness: {HARNESS}"
    proc = subprocess.run(
        ["node", str(HARNESS), group],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    output = f"{proc.stdout}\n{proc.stderr}"
    assert proc.returncode == 0, f"{group} harness failed:\n{output}"
    assert "FAIL" not in output, output
    # Guard against a group that silently ran nothing.
    marker = f"group {group}: "
    assert marker in proc.stdout, output
    count = int(proc.stdout.split(marker, 1)[1].split(" ", 1)[0])
    assert count >= 5, output
