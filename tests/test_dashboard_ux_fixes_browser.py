"""Offline browser checks using an existing Playwright/Chromium installation.

The Node harness fulfills or aborts every request, starts no helper, and writes
screenshots only under OS temp. Missing browser dependencies skip without downloads.
"""
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "tests/js/dashboard_ux_fixes_browser.mjs"


def test_dashboard_ux_fixes_browser():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is not installed")
    result = subprocess.run(
        [node, str(HARNESS)], cwd=ROOT,
        capture_output=True, text=True, encoding="utf-8", timeout=120,
    )
    output = result.stdout + result.stderr
    if result.returncode == 77 and result.stdout.startswith("SKIP dashboard UX:"):
        pytest.skip(result.stdout.strip())
    assert result.returncode == 0, output
    assert "PASS dashboard UX: 4 viewport/theme combinations" in result.stdout
