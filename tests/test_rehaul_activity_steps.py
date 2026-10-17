"""Activity: pure five-step mapping, grouped rows, failure actions and SSE.

Runs the actual dashboard script in a Node VM with in-memory DOM, storage,
fetch and timers. No helper, user profile or network is used.
"""
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "tests/js/rehaul_activity_steps_test.mjs"


@pytest.mark.parametrize("group", ["steps", "rows", "errors", "caption429", "exhaustion", "actions", "stream"])
def test_activity_behaviour(group):
    result = subprocess.run(
        ["node", str(HARNESS), group], cwd=ROOT,
        capture_output=True, text=True, encoding="utf-8", timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"PASS {group}:" in result.stdout


def test_activity_markup_is_grouped_and_drawer_is_accessible():
    text = (ROOT / "assets/dashboard/index.html").read_text(encoding="utf-8")
    activity = text.split('id="tab-activity"', 1)[1].split('id="tab-settings"', 1)[0]
    headings = [activity.index(f'>{title}<') for title in ("Needs attention", "In progress", "Earlier")]
    assert headings == sorted(headings)
    assert activity.index('id="todayTitle"') < headings[2]
    assert '<dialog class="activity-drawer"' in activity
    assert 'aria-labelledby="captureFailureTitle"' in activity
    assert 'aria-describedby="captureFailureLabel"' in activity
    assert 'id="captureFailureActionStatus" role="status"' in activity
    assert 'id="retryCaptureFailure">Retry now</button>' in activity
    assert 'id="removeCaptureFailure">Remove</button>' in activity
    assert 'trapModalFocus(event, els.captureFailureDrawer, closeCaptureFailure)' in text
    assert 'els.captureFailureDrawer.addEventListener("cancel"' in text
    assert '<em>' not in activity
    assert 'class="panel"' not in activity
