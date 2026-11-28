"""Windows notifications must never run text from a saved title as code.

3.18.0 spliced the title into a PowerShell single-quoted string and escaped only
the ASCII apostrophe. PowerShell also accepts U+2018..U+201B as quote marks, so a
web page or video titled with a curly quote could close the string and run
commands when the "saved" notification appeared.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import _platform  # noqa: E402

HOSTILE = [
    "Talk ’; Set-Content -LiteralPath $env:UOINK_TOAST_CANARY -Value pwned; ’",
    "Talk '; Set-Content -LiteralPath $env:UOINK_TOAST_CANARY -Value pwned; '",
    "Talk ‘$(Set-Content -LiteralPath $env:UOINK_TOAST_CANARY -Value pwned)‘",
    "Talk ‛; Set-Content -LiteralPath $env:UOINK_TOAST_CANARY -Value pwned; ‚",
    'Talk "$(Set-Content -LiteralPath $env:UOINK_TOAST_CANARY -Value pwned)"',
]


@pytest.mark.parametrize("title", HOSTILE)
def test_title_and_body_never_reach_the_script(title):
    argv, env = _platform._windows_toast_command(title, title + " body", None)
    script = argv[-1]
    assert script == _platform._WINDOWS_TOAST_SCRIPT
    assert "Set-Content" not in " ".join(argv)
    assert env["UOINK_TOAST_TITLE"] == title[:_platform._TOAST_TITLE_MAX]
    assert env["UOINK_TOAST_BODY"] == (title + " body")[:_platform._TOAST_BODY_MAX]
    assert "UOINK_TOAST_ICON" not in env


def test_icon_path_is_data_and_only_when_the_file_exists(tmp_path):
    icon = tmp_path / "it’s; calc.ico"
    icon.write_bytes(b"\0")
    argv, env = _platform._windows_toast_command("t", "b", str(icon))
    assert str(icon) not in argv[-1]
    assert env["UOINK_TOAST_ICON"] == str(icon)
    _, env2 = _platform._windows_toast_command("t", "b", str(tmp_path / "missing.ico"))
    assert "UOINK_TOAST_ICON" not in env2


def test_control_characters_are_dropped_and_long_text_trimmed():
    _, env = _platform._windows_toast_command("a\0b\x07c", "x" * 5000, None)
    assert env["UOINK_TOAST_TITLE"] == "a b c"
    assert len(env["UOINK_TOAST_BODY"]) == _platform._TOAST_BODY_MAX


def test_windows_toast_passes_env_to_popen(monkeypatch):
    seen = {}

    def fake_popen(argv, **kwargs):
        seen["argv"], seen["kwargs"] = argv, kwargs
        return None

    monkeypatch.setattr(_platform.subprocess, "Popen", fake_popen)
    _platform._windows_toast(HOSTILE[0], "body", None)
    assert seen["argv"][-1] == _platform._WINDOWS_TOAST_SCRIPT
    assert seen["kwargs"]["env"]["UOINK_TOAST_TITLE"].startswith("Talk ’")


POWERSHELL = shutil.which("powershell.exe") or shutil.which("pwsh")


@pytest.mark.skipif(sys.platform != "win32" or not POWERSHELL,
                    reason="needs Windows PowerShell")
@pytest.mark.parametrize("title", HOSTILE)
def test_real_powershell_reads_the_title_as_data(tmp_path, title):
    """Run the same data path the toast uses, minus the balloon, in real PowerShell."""
    canary = tmp_path / "canary.txt"
    _, env = _platform._windows_toast_command(title, "body", None)
    env["UOINK_TOAST_CANARY"] = str(canary)
    # Same assignments as the toast script, written to stdout instead of a balloon.
    probe = ("$t = [string]$env:UOINK_TOAST_TITLE;"
             "[Console]::OutputEncoding = [Text.Encoding]::UTF8;"
             "[Console]::Out.Write($t)")
    out = subprocess.run([POWERSHELL, "-NoProfile", "-NonInteractive", "-Command", probe],
                         env=env, capture_output=True, timeout=60)
    assert out.returncode == 0, out.stderr
    assert out.stdout.decode("utf-8") == title[:_platform._TOAST_TITLE_MAX]
    assert not canary.exists()


@pytest.mark.skipif(sys.platform != "win32" or not POWERSHELL,
                    reason="needs Windows PowerShell")
def test_old_splicing_was_exploitable(tmp_path):
    """Proof the 3.18.0 escaping was not enough (so the test above matters)."""
    canary = tmp_path / "canary.txt"
    title = HOSTILE[0]
    escaped = title.replace("'", "''")  # the 3.18.0 escaping
    probe = f"$t = '{escaped}'"
    env = dict(_platform.os.environ, UOINK_TOAST_CANARY=str(canary))
    subprocess.run([POWERSHELL, "-NoProfile", "-NonInteractive", "-Command", probe],
                   env=env, capture_output=True, timeout=60)
    assert canary.exists(), "curly-quote breakout no longer reproduces on this PowerShell"
