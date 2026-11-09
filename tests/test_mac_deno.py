"""Mac bundle: pinned Deno, its one entitlement, signing checks and the JIT smoke test."""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import plistlib
import re
import subprocess
import sys
import zipfile
from types import SimpleNamespace

import pytest

import _platform

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/mac"))
import bundle_smoke
import deno_bundle
import verify_signing

PLIST = ROOT / "scripts/mac/deno.entitlements.plist"
PIN = json.loads((ROOT / "scripts/mac/payload.json").read_text(encoding="utf-8"))["deno"]


# --- payload pin and entitlements file -------------------------------------

def test_payload_pin_shape():
    assert PIN["version"] == "2.9.8"
    assert PIN["url"] == ("https://github.com/denoland/deno/releases/download/"
                          "v2.9.8/deno-aarch64-apple-darwin.zip")
    assert re.fullmatch(r"[0-9a-f]{64}", PIN["sha256"])
    assert re.fullmatch(r"[0-9a-f]{64}", PIN["entitlements_sha256"])
    assert PIN["size"] == 38770795 and PIN["license"] == "MIT" and PIN["arch"] == "arm64"
    assert PIN["entitlements"] == "deno.entitlements.plist"


def test_entitlements_plist_is_allow_jit_only_and_matches_its_pin():
    assert plistlib.loads(PLIST.read_bytes()) == {"com.apple.security.cs.allow-jit": True}
    assert deno_bundle.ALLOWED_ENTITLEMENTS == {"com.apple.security.cs.allow-jit": True}
    assert hashlib.sha256(PLIST.read_bytes()).hexdigest() == PIN["entitlements_sha256"]
    assert deno_bundle.load_pin() == PIN


def test_changed_plist_fails_the_pin(tmp_path, monkeypatch):
    other = tmp_path / "deno.entitlements.plist"
    other.write_bytes(PLIST.read_bytes() + b"\n")
    monkeypatch.setattr(deno_bundle, "ENTITLEMENTS", other)
    with pytest.raises(ValueError, match="pin"):
        deno_bundle.load_pin()


# --- install ---------------------------------------------------------------

def fake_pin(tmp_path, content=b"\xcf\xfa\xed\xfefake-deno"):
    archive = tmp_path / "deno.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("deno", content)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    return archive, {**PIN, "sha256": digest}


def test_install_puts_deno_in_helpers_with_notices(tmp_path, monkeypatch):
    archive, pin = fake_pin(tmp_path)
    monkeypatch.setattr(deno_bundle, "load_pin", lambda: pin)
    app, notices = tmp_path / "Uoink.app", tmp_path / "notices"
    notices.mkdir()
    info = deno_bundle.install(app, notices, tmp_path / "cache", download=lambda p, c: archive)
    deno = app / "Contents/Helpers/deno"
    assert deno.read_bytes().startswith(b"\xcf\xfa\xed\xfe")
    if sys.platform != "win32":  # Windows has no POSIX modes
        assert deno.stat().st_mode & 0o777 == 0o755
    assert (notices / "deno/LICENSE.txt").read_text(encoding="utf-8").startswith("MIT License")
    assert (notices / "deno/deno.entitlements.plist").read_bytes() == PLIST.read_bytes()
    assert info["version"] == "2.9.8" and info["entitlements"] == ["com.apple.security.cs.allow-jit"]
    assert info["binary_sha256"] == hashlib.sha256(deno.read_bytes()).hexdigest()


def test_install_rejects_wrong_hash_and_extra_zip_members(tmp_path, monkeypatch):
    archive, pin = fake_pin(tmp_path)
    monkeypatch.setattr(deno_bundle, "load_pin", lambda: {**pin, "sha256": "0" * 64})
    with pytest.raises(ValueError, match="SHA-256"):
        deno_bundle.install(tmp_path / "a.app", tmp_path, tmp_path / "c", download=lambda p, c: archive)
    extra = tmp_path / "extra.zip"
    with zipfile.ZipFile(extra, "w") as zf:
        zf.writestr("deno", b"x")
        zf.writestr("other", b"y")
    monkeypatch.setattr(deno_bundle, "load_pin", lambda: {**pin, "sha256": hashlib.sha256(extra.read_bytes()).hexdigest()})
    with pytest.raises(ValueError, match="Unexpected Deno zip"):
        deno_bundle.install(tmp_path / "b.app", tmp_path, tmp_path / "c", download=lambda p, c: extra)


def test_fetch_reuses_a_verified_cache_and_rejects_a_bad_download(tmp_path, monkeypatch):
    archive, pin = fake_pin(tmp_path)
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / Path(pin["url"]).name).write_bytes(archive.read_bytes())
    monkeypatch.setattr(deno_bundle.urllib.request, "urlopen", lambda *a, **k: pytest.fail("cache hit"))
    assert deno_bundle.fetch(pin, cache).read_bytes() == archive.read_bytes()
    (cache / Path(pin["url"]).name).write_bytes(b"corrupt")

    monkeypatch.setattr(deno_bundle.urllib.request, "urlopen", lambda *a, **k: io.BytesIO(b"not the pinned zip"))
    with pytest.raises(ValueError, match="pinned"):
        deno_bundle.fetch(pin, cache)
    assert not list(cache.glob("*.part"))


# --- _platform -------------------------------------------------------------

def bundle(tmp_path, monkeypatch, with_deno=True):
    contents = tmp_path / "Uoink.app/Contents"
    (contents / "Helpers").mkdir(parents=True)
    if with_deno:
        (contents / "Helpers/deno").write_bytes(b"x")
    monkeypatch.setattr(_platform, "mac_bundle_contents", lambda: contents)
    return contents


def test_bundle_mode_returns_helpers_deno_and_wins_over_bin_dir(tmp_path, monkeypatch):
    contents = bundle(tmp_path, monkeypatch)
    other = tmp_path / "bin"
    other.mkdir()
    (other / "deno").write_bytes(b"x")
    expected = ["--js-runtimes", f"deno:{contents / 'Helpers/deno'}"]
    assert _platform.ytdlp_js_runtime_args(other) == expected
    assert _platform.ytdlp_js_runtime_args(None) == expected


def test_bundle_mode_missing_deno_adds_nothing_even_if_bin_dir_has_one(tmp_path, monkeypatch):
    bundle(tmp_path, monkeypatch, with_deno=False)
    other = tmp_path / "bin"
    other.mkdir()
    (other / "deno").write_bytes(b"x")
    assert _platform.ytdlp_js_runtime_args(other) == []


def test_bundle_mode_rejects_symlinked_deno_and_helpers(tmp_path, monkeypatch):
    contents = bundle(tmp_path, monkeypatch, with_deno=False)
    real = tmp_path / "real-deno"
    real.write_bytes(b"x")
    try:
        (contents / "Helpers/deno").symlink_to(real)
    except OSError:
        pytest.skip("symlinks unavailable")
    assert _platform.ytdlp_js_runtime_args() == []
    (contents / "Helpers/deno").unlink()
    (contents / "Helpers").rmdir()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "deno").write_bytes(b"x")
    (contents / "Helpers").symlink_to(elsewhere, target_is_directory=True)
    assert _platform.ytdlp_js_runtime_args() == []


def test_non_bundle_behaviour_is_unchanged(tmp_path, monkeypatch):
    monkeypatch.setattr(_platform, "mac_bundle_contents", lambda: None)
    name = "deno.exe" if sys.platform == "win32" else "deno"
    (tmp_path / name).write_bytes(b"x")
    assert _platform.ytdlp_js_runtime_args(tmp_path) == ["--js-runtimes", f"deno:{tmp_path / name}"]


# --- verify_signing --------------------------------------------------------

def entitlements_xml(values):
    return "Executable=/x\n" + plistlib.dumps(values).decode() if values else ""


def make_execute(by_name):
    def execute(argv):
        path = Path(argv[-1])
        return {"argv": argv, "exit": 0, "stdout": entitlements_xml(by_name.get(path.name, {})), "stderr": ""}
    return execute


def fixture_paths(app):
    return [app / "Contents/MacOS/Uoink", app / "Contents/Helpers/ffmpeg", app / "Contents/Helpers/deno"]


JIT = {"com.apple.security.cs.allow-jit": True}


def test_verify_entitlements_accepts_deno_with_only_allow_jit(tmp_path):
    app = tmp_path / "Uoink.app"
    found = verify_signing.verify_entitlements(app, fixture_paths(app), execute=make_execute({"deno": JIT}))
    assert found["Contents/Helpers/deno"] == JIT and found["Contents/Helpers/ffmpeg"] == {}


@pytest.mark.parametrize("deno,other,message", [
    ({}, {}, "exactly allow-jit"),
    ({**JIT, "com.apple.security.cs.allow-unsigned-executable-memory": True}, {}, "exactly allow-jit"),
    ({"com.apple.security.cs.allow-jit": False}, {}, "exactly allow-jit"),
    (JIT, {"ffmpeg": JIT}, "unexpected entitlements"),
    (JIT, {"Uoink": {"com.apple.security.get-task-allow": True}}, "unexpected entitlements"),
])
def test_verify_entitlements_rejects_everything_else(tmp_path, deno, other, message):
    app = tmp_path / "Uoink.app"
    with pytest.raises(ValueError, match=message):
        verify_signing.verify_entitlements(app, fixture_paths(app), execute=make_execute({"deno": deno, **other}))


def test_verify_entitlements_requires_deno_to_be_checked_and_codesign_to_succeed(tmp_path):
    app = tmp_path / "Uoink.app"
    with pytest.raises(ValueError, match="not checked"):
        verify_signing.verify_entitlements(app, fixture_paths(app)[:2], execute=make_execute({}))
    failing = lambda argv: {"argv": argv, "exit": 1, "stdout": "", "stderr": "nope"}
    with pytest.raises(ValueError, match="cannot read"):
        verify_signing.verify_entitlements(app, fixture_paths(app), execute=failing)


def test_parse_ignores_trailing_text_and_legacy_blob_prefix():
    xml = plistlib.dumps(JIT).decode()
    assert verify_signing.parse_entitlements(xml + "Executable=/x\n") == JIT
    assert verify_signing.parse_entitlements("") == {}
    assert verify_signing.parse_entitlements("Executable=/x\n") == {}
    blob = bytes([0xfa, 0xde, 0x71, 0x71, 0, 0, 1, 0x2c, 0]).decode("utf-8", errors="replace")
    assert verify_signing.parse_entitlements(blob + xml) == JIT
    assert verify_signing.parse_entitlements(blob + xml + "tail") == JIT


def test_verify_entitlements_ignores_stderr_executable_line(tmp_path):
    app = tmp_path / "Uoink.app"

    def execute(argv):
        values = JIT if Path(argv[-1]).name == "deno" else {}
        return {"argv": argv, "exit": 0, "stdout": plistlib.dumps(values).decode() if values else "",
                "stderr": f"Executable={argv[-1]}\n"}

    found = verify_signing.verify_entitlements(app, fixture_paths(app), execute=execute)
    assert found["Contents/Helpers/deno"] == JIT


# --- bundle_smoke ----------------------------------------------------------

def smoke_rig(tmp_path, monkeypatch, outputs):
    contents = tmp_path / "Contents"
    (contents / "Helpers").mkdir(parents=True)
    (contents / "Helpers/deno").write_bytes(b"x")
    calls = []

    def run(argv, **kw):
        calls.append(argv)
        code, out = outputs[len(calls) - 1]
        return SimpleNamespace(returncode=code, stdout=out, stderr="V8 crash")

    monkeypatch.setattr(bundle_smoke.subprocess, "run", run)
    return contents, calls


def test_deno_smoke_runs_real_js_with_probe_flags_and_checks_both_results(tmp_path, monkeypatch):
    loop = bundle_smoke.deno_expected_loop()
    contents, calls = smoke_rig(tmp_path, monkeypatch, [(0, "42\n"), (0, loop + "\n")])
    report = bundle_smoke.deno_smoke(contents, tmp_path, {"PATH": "/usr/bin"})
    assert report == {"eval": "42", "jit_loop": loop}
    first = calls[0]
    assert first[:8] == [str(contents / "Helpers/deno"), "eval", "--no-prompt", "--no-remote", "--no-npm",
                         "--no-lock", "--no-config", "--node-modules-dir=none"]
    assert first[-1] == "console.log(6*7)" and "--version" not in first
    assert len(calls) == 2 and loop == "899994"


@pytest.mark.parametrize("outputs", [[(133, "")], [(0, "41\n")], [(0, "42\n"), (133, "")], [(0, "42\n"), (0, "1\n")]])
def test_deno_smoke_fails_on_crash_or_wrong_output(tmp_path, monkeypatch, outputs):
    contents, _ = smoke_rig(tmp_path, monkeypatch, outputs)
    with pytest.raises(AssertionError, match="Bundled Deno"):
        bundle_smoke.deno_smoke(contents, tmp_path, {})


def test_deno_smoke_fails_when_deno_is_missing(tmp_path):
    with pytest.raises(AssertionError, match="Missing bundled Deno"):
        bundle_smoke.deno_smoke(tmp_path, tmp_path, {})


def test_smoke_flags_match_the_diagnose_probe_in_server():
    text = (ROOT / "server.py").read_text(encoding="utf-8")
    probe = re.search(r'\[deno_cmd, "eval", (.*?), "console\.log\(6\*7\)"\]', text, re.S).group(1)
    assert re.findall(r'"([^"]+)"', probe) == bundle_smoke.DENO_FLAGS[1:]
