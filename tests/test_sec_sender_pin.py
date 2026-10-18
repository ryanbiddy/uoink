"""Run the existing sender-ID regressions under pytest, entirely offline."""
from pathlib import Path
import re
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def test_extension_runtime_messages_require_own_sender_id():
    node = shutil.which("node")
    assert node, "Node.js is required for the offline extension sender harness"
    result = subprocess.run(
        [node, "--test", "--test-reporter=tap", "tests/js/sec_sender_pin_test.mjs"],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=60,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    passed = re.findall(r"^# pass (\d+)$", result.stdout, re.MULTILINE)
    assert len(passed) == 1 and int(passed[0]) >= 7, output
    assert re.findall(r"^# fail (\d+)$", result.stdout, re.MULTILINE) == ["0"], output
