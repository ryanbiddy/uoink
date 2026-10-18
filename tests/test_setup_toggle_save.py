"""Settings regressions retained after the controls moved out of setup.

The seven original groups now drive the dashboard's real Settings markup,
change handlers, authenticated transport, save queue and hydration. The tests
still check field-scoped payloads, inline status ownership, rejected/omitted
values, serialized saves, stale responses, typed drafts, key isolation and
bounded reads. The spec's per-control autosave model replaces section Save
buttons; failed drafts remain visible for explicit Retry save. Numeric controls
validate their displayed range instead of silently clamping a typed value.

All helper I/O and browser storage are in-memory stubs. No live helper is used.
"""
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HARNESS = REPO_ROOT / "tests" / "js" / "setup_toggle_save_test.mjs"

GROUPS = [
    "hook_type",
    "screenshot",
    "failure",
    "overlap",
    "ci_save",
    "section_status",
    "read_timeout",
]


@pytest.mark.parametrize("group", GROUPS)
def test_setup_toggle_save(group):
    assert HARNESS.exists(), f"missing harness: {HARNESS}"
    proc = subprocess.run(
        ["node", str(HARNESS), group],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    output = f"{proc.stdout}\n{proc.stderr}"
    assert proc.returncode == 0, f"{group} harness failed:\n{output}"
    assert "FAIL" not in output, output
    # Guard against a group that silently ran nothing.
    marker = f"group {group}: "
    assert marker in proc.stdout, output
    count = int(proc.stdout.split(marker, 1)[1].split(" ", 1)[0])
    assert count >= 3, output
    minimum_scenarios = {
        "hook_type": 3, "screenshot": 3, "failure": 5, "overlap": 22,
        "ci_save": 5, "section_status": 15, "read_timeout": 13,
    }
    assert count >= minimum_scenarios[group], output
