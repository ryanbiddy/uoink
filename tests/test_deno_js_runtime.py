"""yt-dlp gets the bundled Deno as its JavaScript runtime (3.16.1)."""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import _platform  # noqa: E402
import server  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
BUILD = (ROOT / "build.ps1").read_text(encoding="utf-8")
ISS = (ROOT / "installer" / "uoink.iss").read_text(encoding="utf-8")
VERIFY = (ROOT / "installer" / "verify_install.ps1").read_text(encoding="utf-8")
DENO_NAME = "deno.exe" if sys.platform == "win32" else "deno"


def test_flag_added_when_bundled_deno_exists(tmp_path):
    fake = tmp_path / DENO_NAME
    fake.write_bytes(b"not a real deno")
    assert _platform.ytdlp_js_runtime_args(tmp_path) == ["--js-runtimes", f"deno:{fake}"]


def test_nothing_added_without_bundled_deno(tmp_path):
    assert _platform.ytdlp_js_runtime_args(tmp_path) == []
    assert _platform.ytdlp_js_runtime_args(tmp_path / "missing") == []
    (tmp_path / DENO_NAME).mkdir()  # a folder is not a binary
    assert _platform.ytdlp_js_runtime_args(tmp_path) == []


def test_ytdlp_cmd_uses_the_same_rule():
    extra = _platform.ytdlp_js_runtime_args(server._BIN_DIR)
    if extra:
        assert server.YTDLP_CMD[-2:] == extra
    else:
        assert "--js-runtimes" not in server.YTDLP_CMD
    # The twitter flag and interpreter stay first, so prefix checks still match.
    assert server.YTDLP_CMD[:4] == [sys.executable, "-m", "yt_dlp", "--extractor-args"]


def test_ytdlp_ignores_personal_config_on_every_platform():
    # The Mac gets it from ytdlp_media_args; Windows and Linux from the base list.
    assert server.YTDLP_CMD.count("--ignore-config") == 1


def test_deno_cache_and_update_check_are_contained():
    import os
    assert os.environ["DENO_NO_UPDATE_CHECK"] == "1"
    assert Path(os.environ["DENO_DIR"]) == Path(server.DATA_ROOT) / "deno-cache"


def test_youtube_call_detection_still_works_with_the_flag(monkeypatch, tmp_path):
    (tmp_path / DENO_NAME).write_bytes(b"x")
    cmd = [*server.YTDLP_CMD, "--js-runtimes", f"deno:{tmp_path / DENO_NAME}",
           "https://www.youtube.com/watch?v=abcdef12345"]
    assert server._is_youtube_ytdlp_call(cmd)


def test_installer_ships_and_verifies_deno():
    assert 'Source: "staging\\bin\\*"; DestDir: "{app}\\bin"; Flags: recursesubdirs ignoreversion' in ISS
    assert "'bin\\deno.exe'" in VERIFY
    assert "deno.exe" in VERIFY and "--version" in VERIFY
    assert "$StagingDir\\bin\\deno.exe" in BUILD


def test_build_pins_deno_and_ejs_with_a_hash():
    assert re.search(r"^\$DENO_VERSION = '\d+\.\d+\.\d+'", BUILD, re.M)
    assert re.search(r'^\$DENO_SHA256\s*= "[0-9a-f]{64}"', BUILD, re.M)
    assert "Confirm-Hash $denoZip $DENO_SHA256 'Deno'" in BUILD
    assert "https://github.com/denoland/deno/releases/download/v$DENO_VERSION/" in BUILD
    ejs = re.search(r"^\$YTDLP_EJS_VERSION = '([\d.]+)'", BUILD, re.M).group(1)
    assert f"yt-dlp-ejs=={ejs}" in (ROOT / "requirements-installer-lock.txt").read_text(encoding="utf-8")
    assert f"yt-dlp-ejs=={ejs}" in (ROOT / "requirements-linux.txt").read_text(encoding="utf-8")
    assert '"yt-dlp-ejs==$YTDLP_EJS_VERSION"' in BUILD


def test_ejs_matches_the_lock_hash_line():
    lock = (ROOT / "requirements-installer-lock.txt").read_text(encoding="utf-8")
    assert re.search(r"^yt-dlp-ejs==[\d.]+ --hash=sha256:[0-9a-f]{64}$", lock, re.M)


def test_license_files_are_pinned_and_shipped():
    folder = ROOT / "third-party-notices"
    for name in ("deno-2.9.8-MIT-LICENSE.txt", "yt-dlp-ejs-0.8.0-LICENSES.txt"):
        digest = hashlib.sha256((folder / name).read_bytes()).hexdigest()
        assert f"'{name}' = '{digest}'" in BUILD
        assert f"'third-party-notices\\{name}'" in BUILD
        assert f'Source: "staging\\third-party-notices\\{name}"' in ISS
    assert "MIT License" in (folder / "deno-2.9.8-MIT-LICENSE.txt").read_text(encoding="utf-8")


# --- /diagnose js_runtime must evaluate real JavaScript ----------------------
import subprocess  # noqa: E402


def test_deno_probe_command_evals_with_no_permissions(monkeypatch):
    seen = []
    monkeypatch.setattr(server, "_probe_command",
                        lambda cmd, expect=None: seen.append((cmd, expect)) or ("ok", "42"))
    server._build_diagnose_payload(public=False)
    cmd, expect = next(s for s in seen if "eval" in s[0])
    assert cmd[1] == "eval" and expect == "42"
    assert not [a for a in cmd if a.startswith("--allow-") or a in ("-A", "--allow-all")]
    assert "--no-prompt" in cmd and "--no-remote" in cmd and "--no-lock" in cmd


def _fake_run(monkeypatch, stdout="", stderr="", returncode=0, raises=None):
    def run(cmd, **kw):
        if raises:
            raise raises
        return subprocess.CompletedProcess(cmd, returncode, stdout, stderr)
    monkeypatch.setattr(server.subprocess, "run", run)


def _js_runtime_check():
    checks = server._build_diagnose_payload(public=False)["checks"]
    return next(c for c in checks if c["name"] == "js_runtime")


def _only_deno_fake(monkeypatch, **fake):
    real = server._probe_command
    _fake_run(monkeypatch, **fake)
    monkeypatch.setattr(server, "_probe_command",
                        lambda cmd, expect=None: real(cmd, expect) if "eval" in cmd
                        else ("ok", "stub"))


def test_js_runtime_ok_when_deno_prints_42(monkeypatch):
    _only_deno_fake(monkeypatch, stdout="42\n")
    assert _js_runtime_check()["status"] == "ok"


def test_js_runtime_warns_on_wrong_answer(monkeypatch):
    _only_deno_fake(monkeypatch, stdout="43\n")
    check = _js_runtime_check()
    assert check["status"] == "warning" and "43" in check["detail"]


def test_js_runtime_warns_on_crash_with_stderr_detail(monkeypatch):
    _only_deno_fake(monkeypatch, returncode=-5,
                    stderr="Failed to reserve virtual memory for CodeRange\n")
    check = _js_runtime_check()
    assert check["status"] == "warning"
    assert "CodeRange" in check["detail"]


def test_js_runtime_warns_on_nonzero_exit_and_timeout(monkeypatch):
    _only_deno_fake(monkeypatch, returncode=1)
    assert _js_runtime_check()["status"] == "warning"
    _only_deno_fake(monkeypatch, raises=subprocess.TimeoutExpired("deno", 10))
    assert _js_runtime_check()["status"] == "warning"
