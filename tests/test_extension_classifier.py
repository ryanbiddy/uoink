"""Drive the extension's client-side capture classifier through Node.

The popup classifies the active tab client-side (the shipped helper has no
/detect route), so the classifier lives in extension/lib/extract.js. This
wrapper runs the Node harness (tests/js/classifier_test.mjs) as part of the
standalone pytest suite. It skips cleanly when Node isn't on PATH so the
Python-only CI job stays green.
"""
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HARNESS = REPO_ROOT / "tests" / "js" / "classifier_test.mjs"


@pytest.mark.skipif(shutil.which("node") is None,
                    reason="node not available; classifier harness needs Node")
def test_client_side_capture_classifier():
    assert HARNESS.exists(), f"missing harness: {HARNESS}"
    proc = subprocess.run(
        ["node", str(HARNESS)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    # Surface the harness output on failure so the mismatch is visible.
    assert proc.returncode == 0, (
        f"classifier harness failed:\n{proc.stdout}\n{proc.stderr}")
