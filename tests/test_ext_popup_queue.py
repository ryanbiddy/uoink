"""E1: popup captures survive the popup closing.

Chrome closes the extension popup as soon as the user clicks back into the
page. popup.js used to await STC.postExtract (and postExtractReddit /
postExtractPage) inside its own document, and the helper's /extract only
answers when the whole capture is done, so closing the popup killed the
request and lost the clipboard copy, Claude tab, notification and failure
record; users then retried captures that had actually finished.

Runs tests/js/ext_popup_queue_test.mjs, which loads popup.js's REAL capture,
hand-off, refreshQueue and Recent failures code and the REAL background.js
into two fake extension contexts (node:vm) that share chrome.storage, with the
popup's runtime messages delivered to the service worker's listeners:

  handoff -- Uoink this video / thread / page / post / article (the X Article
             /extract/page fallback) and "Allow this site and retry" send one
             popupCapture message and return while the helper is still
             working, or before /queue/status has answered; the popup calls
             no capture endpoint and no queue-status check itself (it no
             longer awaits postExtract).
  closed  -- after the popup is gone the service worker still copies the
             corpus, opens Claude, notifies (persistently on an X login wall),
             and records a failure (with its real reason) for the popup's
             Recent failures row.
  open    -- a popup that stays or is reopened renders the SW queue from
             chrome.storage.session ("Uoinking..."), shows a handed-off
             outcome once, de-duplicates a second click of the same capture
             (a context-menu one included, even one queued with the tab's
             #fragment: the joined job still answers the popup and records
             its failure) but not a session add of the same URL, reports a
             full helper queue, still offers "Allow this site and retry" on an allowlist
             wall, and shows X Article walls as its persistent alert.
  worker  -- the SW accepts popupCapture only from extension pages, with a
             known route and an http(s) URL; context-menu jobs are unchanged.
  retry   -- Recent failures Retry on a capture the SW recorded (a web page,
             a Reddit thread, a YouTube or X post's video) reruns it in the
             SW queue, never a content-script tab; the record stays
             until the rerun goes through and a new failure replaces it. A
             Retry of a capture already queued or running joins that job (no
             second extraction), the context menu's included; its success
             drops the record and its failure replaces it. "Allow this site
             and retry" after a Retry's allowlist wall reruns the Retry's
             page and record, not the active tab's.
  restart -- MV3 lifecycle: while a job runs the SW makes an extension API
             call on a sub-30 s timer (Chrome's keep-alive). A new SW started
             on the storage a stopped one left takes the interrupted capture
             back: resumed once and finished there (a popup click joins it
             instead of starting a second extraction); one already resumed,
             already answered, or a session add gets the lost-track notice,
             and the rest of the queue still runs.
  race    -- with chrome.storage.session answers coming back late, a popup
             capture sent while drain() reads the queue (to take the next job
             or to go idle) is neither erased nor stranded, Clear queue isn't
             undone, and under late, out-of-order answers every acknowledged
             capture runs exactly once and the queue ends idle.

No network: fetch and chrome.* are stubs inside the harness.
"""
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HARNESS = REPO_ROOT / "tests" / "js" / "ext_popup_queue_test.mjs"

GROUPS = [
    "handoff",
    "closed",
    "open",
    "worker",
    "retry",
    "restart",
    "race",
]


@pytest.mark.parametrize("group", GROUPS)
def test_popup_capture_survives_popup_closing(group):
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
