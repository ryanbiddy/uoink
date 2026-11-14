"""Runs the After a save and extension break-ui JS suites (real extension scripts in a fake browser)."""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
@pytest.mark.parametrize("name", ["ext_after_save_test.mjs", "ext_break_ui_test.mjs"])
def test_extension_js_suite(name):
    proc = subprocess.run(
        ["node", "--test", str(ROOT / "tests" / "js" / name)],
        cwd=ROOT, capture_output=True, text=True, timeout=180,
    )
    assert proc.returncode == 0, proc.stdout[-2500:] + proc.stderr[-1500:]
