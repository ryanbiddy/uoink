from pathlib import Path
import shutil
import subprocess

import pytest


def test_dashboard_recovery_states_and_text_escaping():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is required for dashboard behavior tests')
    result = subprocess.run([node, str(Path(__file__).parent / 'js/helper_recovery_test.mjs')],
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
