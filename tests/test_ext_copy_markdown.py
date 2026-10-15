"""E5: the popup's Copy Markdown button actually copies the corpus.

Runs tests/js/ext_copy_markdown_test.mjs, which loads the REAL extension
scripts (lib/extract.js, lib/ui.js and popup.js's loadRecentUoinks) into a
fake browser built on node:vm, renders the Last Uoinked Video card from a
stubbed /recent and clicks Copy Markdown:

  request    -- the click resolves to an exported, authed helper call: one
                POST /mcp/v1/tools/call with the extension token and
                {name: "get_uoink_corpus", arguments: {slug: <folder name>}}
                (/recent rows carry folder, not slug), and the corpus lands
                on the clipboard with the success toast.
  failure    -- a helper "uoink not found" reply, a stale token (403, then
                one refresh) and an unreachable helper each end with the
                right toast and the button restored.
  call_sites -- every STC.* / UoinkUI.* call in popup.js names a function
                the loaded libs export (E5 called the private
                STC._postJson, which extract.js never exported).

No network: fetch and chrome.* are stubs inside the harness.
"""
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HARNESS = REPO_ROOT / "tests" / "js" / "ext_copy_markdown_test.mjs"

GROUPS = [
    "request",
    "failure",
    "call_sites",
]


@pytest.mark.parametrize("group", GROUPS)
def test_popup_copy_markdown(group):
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
    assert count >= 3, output
