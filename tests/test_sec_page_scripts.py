"""Offline audit #3 regressions using real extension scripts in a Node VM.

No server imports, sockets, browser profiles or real clipboard access. The
JavaScript harness supplies every browser API and fetch response in memory.
"""
from pathlib import Path
import re
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_page_scripts_cannot_capture_read_corpus_or_open_arbitrary_tabs():
    node = shutil.which("node")
    assert node, "Node.js is required for the offline extension security harness"
    result = subprocess.run(
        [node, "--test", "--test-reporter=tap", "tests/js/sec_page_scripts_test.mjs"],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=60,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    # Node can exit successfully without registering any regression tests.
    passed = re.findall(r"^# pass (\d+)$", result.stdout, re.MULTILINE)
    assert len(passed) == 1 and int(passed[0]) >= 67, (
        f"Expected at least 67 passing security regressions:\n{output}"
    )
    assert re.findall(r"^# fail (\d+)$", result.stdout, re.MULTILINE) == ["0"], output


@pytest.mark.parametrize("stdout,returncode", [
    ("", 0),
    ("# tests 0\n# pass 0\n# fail 0\n", 0),
    ("# pass 1\n# fail 0\n", 0),
    ("# pass 66\n# fail 0\n", 0),
    ("# pass 67\n", 0),
    ("# pass 67\n# fail 1\n", 0),
    ("# pass 67\n# fail 0\n", 1),
])
def test_harness_gate_rejects_missing_or_incomplete_results(monkeypatch, stdout, returncode):
    monkeypatch.setattr(shutil, "which", lambda _: "synthetic-node")
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: subprocess.CompletedProcess(
        args=args, returncode=returncode, stdout=stdout, stderr="",
    ))
    with pytest.raises(AssertionError):
        test_page_scripts_cannot_capture_read_corpus_or_open_arbitrary_tabs()
