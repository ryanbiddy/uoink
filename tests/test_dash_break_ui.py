"""Dashboard stress-test fixes (break-ui run, 2026-11-11).

Runs tests/js/dash_break_ui_test.mjs, which pulls the pure helpers (future
dates, speaker timeline buckets) out of the real dashboard script and checks
the CSS and markup guards for the overflow, controls, Retry and Show more fixes.
"""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_break_ui_fixes():
    result = subprocess.run(
        ["node", "tests/js/dash_break_ui_test.mjs"], cwd=ROOT,
        capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "0 failures" in result.stdout
