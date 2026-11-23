"""Dashboard Tidy Uncategorized and Select (3.18 shelves).

Runs tests/js/dash_shelves_test.mjs, which pulls the pure helpers out of the
real dashboard script and checks the copy, escaping, chunking and the layout
guards for long names at phone width.
"""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_dashboard_shelves():
    result = subprocess.run(
        ["node", "tests/js/dash_shelves_test.mjs"], cwd=ROOT,
        capture_output=True, text=True, encoding="utf-8", timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "0 failures" in result.stdout
