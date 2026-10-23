"""Dashboard Library: search never shows stale results (D1).

Before the fix, loadLibrary() in assets/dashboard/index.html returned early
while a load was in flight. Typing "ai" and then " agents" never sent the
second search, so the "ai" results stayed under an "ai agents" search box; the
Library refresh after saving a note or an image was dropped the same way.

Runs tests/js/dash_search_sequencing_test.mjs, which loads the REAL dashboard
script (everything before init()) into a node:vm context over a fake page
holding every id the markup declares, wires the real listeners with
wireEvents(), and holds each /memory/search answer until the scenario releases
it:

  typing      -- a search typed while an older one is unanswered is still
                 sent, and only the newest search's answer is shown, whichever
                 answer lands first.
  stale_error -- an older search failing late never replaces the newer
                 results; an older search answering late never replaces the
                 newer search's error.
  load_more   -- Load more still pages, a double click never duplicates rows,
                 and a search typed while Load more is unanswered drops the old
                 query's page.
  date_range  -- a bad date range entered while a search is unanswered keeps
                 its date message when that search answers.
  note_image  -- saving a note or an image while a search is unanswered still
                 refreshes Library, and the new item is shown.
  before_debounce -- an older answer, failure or Load more page landing after
                 the search box or a filter changed, but before the 260 ms
                 debounce sends the new search, is dropped too.
  refresh_before_debounce -- a note or image refresh, or Load more, started
                 after the search box or a filter changed but before the
                 debounce asks for the new search from its first page, so its
                 answer never shows the old search's rows.

No network: fetch is a stub inside the harness.
"""
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HARNESS = REPO_ROOT / "tests" / "js" / "dash_search_sequencing_test.mjs"

GROUPS = [
    "search_modes",
    "typing",
    "stale_error",
    "load_more",
    "date_range",
    "note_image",
    "before_debounce",
    "refresh_before_debounce",
]


@pytest.mark.parametrize("group", GROUPS)
def test_dash_search_sequencing(group):
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
