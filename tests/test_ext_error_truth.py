"""E3/E4/E6/E7: every extension surface shows the real failure reason.

Runs tests/js/ext_error_truth_test.mjs, which loads the REAL extension
scripts (lib/extract.js, content.js, content-reddit.js, content-x-article.js,
background.js and popup.js's capture and Retry functions) into a fake browser built on
node:vm and drives them through failing captures:

  E3 -- the helper's {ok:false, error, error_detail, failure_phase} reaches
        the in-page tooltip/notification, the remembered failure, the popup
        toast and context-menu notifications as phase + last yt-dlp ERROR
        line, without the "Details are tucked below." pointer.
  E4 -- only HTTP 403 or the exact "missing or invalid token" body reads as
        an authorization change ("PO Token", "HTTP Error 403: Forbidden" and
        "max tokens" stay what they are).
  E6 -- Reddit and X Article button failures notify, set the tooltip and are
        remembered, instead of only reaching console.error. Retry on a
        remembered failure (popup Recent row) makes the opened page actually
        start the capture; the record is only dropped or replaced after that.
        On the SPA pages (Reddit, X Article) a failure that lands after the
        tab moved on is recorded for the page that failed, and a Retry still
        waiting to run never captures the page the tab moved to.
  E7 -- thrown errors are classified: timeout -> still working (Activity),
        lost SW port / invalidated context -> lost track (Library), offline
        only when the /health ping fails too, with platform-aware copy; only
        offline opens the setup tab.

Since E1 the popup's video, Reddit and page captures run in background.js's
queue (tests/test_ext_popup_queue.py), so the popup group loads both and
checks the reason in the SW notification and in the open popup's toast.

No network: fetch and chrome.* are stubs inside the harness.
"""
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HARNESS = REPO_ROOT / "tests" / "js" / "ext_error_truth_test.mjs"

GROUPS = [
    "lib",
    "content_youtube",
    "content_reddit",
    "content_x_article",
    "background",
    "popup",
    "retry",
]


@pytest.mark.parametrize("group", GROUPS)
def test_extension_shows_real_failure_reason(group):
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
