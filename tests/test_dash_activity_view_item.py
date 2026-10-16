"""Dashboard Activity reconnects and View Item opens the item (D20, D3).

D20: connectJobsStream() in assets/dashboard/index.html read /jobs/stream once.
A clean end broke out of the read loop and an error only scheduled a single
refreshActivity(), so after a helper restart or a PC sleep the Activity list,
the nav badge and "N in flight" froze until the page was reloaded.

D3: View Item in the Library activity evidence modal checked for
showYoinkDetail(), which does not exist, so it only hid the modal and left
focus on a control inside it.

Runs tests/js/dash_activity_view_item_test.mjs, which loads the REAL dashboard
script (everything before init()) into a node:vm context over a fake page
holding every id the markup declares. setTimeout and Date are fakes the test
drives, and /jobs/stream answers with a stream the test feeds, ends or breaks:

  reconnect -- a stream that ends cleanly or breaks is reopened after a wait,
               each reopen calls refreshActivity() and waits for it before
               the stream reopens, so a slow /jobs answer never lands on top
               of the reopened stream's snapshot, and the reopened stream
               drives Activity, the nav badge and "N in flight" again; every
               connect sends the token, and split frames still parse.
  backoff   -- while the helper is down the waits double from 1 s to a 30 s
               cap, a 503 refusal waits too, a stream that stayed open a while
               starts again from 1 s, and one that ends at once keeps backing
               off.
  view_item -- View Item closes the evidence modal, opens that item's detail
               (the loaded Library row when there is one) and moves focus to
               something visible in the item view, not to the Library trigger
               the tab switch hides. Markup ids sit in their markup tab panel,
               and focus() only lands on a shown, focusable element.

No network: fetch is a stub inside the harness.
"""
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HARNESS = REPO_ROOT / "tests" / "js" / "dash_activity_view_item_test.mjs"

GROUPS = [
    "reconnect",
    "backoff",
    "view_item",
]


@pytest.mark.parametrize("group", GROUPS)
def test_dash_activity_view_item(group):
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
