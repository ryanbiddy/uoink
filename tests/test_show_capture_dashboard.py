"""Dashboard surface for Save a whole show.

Runs tests/js/dash_show_capture_test.mjs, which pulls the estimate, status,
button and row helpers out of the real dashboard script and checks the
markup and CSS guards (escaping, one primary action, long titles).
"""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_show_capture_dashboard():
    result = subprocess.run(
        ["node", "tests/js/dash_show_capture_test.mjs"], cwd=ROOT,
        capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert " 0 failures" in result.stdout
