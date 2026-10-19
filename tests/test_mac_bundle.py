"""Offline builder checks: hashes, source closure, archive safety and inventories."""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import sys
import tarfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/mac"))
import build_bundle as bundle
import wheel_lock


def wheel_fixture(tmp_path):
    filename = "sample-1.0-py3-none-any.whl"
    path = tmp_path / filename
    path.write_bytes(b"qualified bytes")
    row = {"filename": filename, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    report = {"graph_attempts": [{"platform": "macosx_15_0_arm64", "resolved": True,
                                  "errors": [], "wheels": [row]}],
              "packages": [{"package": "sample", "version": "1.0"}]}
    (tmp_path / "wheel-manifest.json").write_text(json.dumps({"errors": [], "wheels": [row],
        "pins": [{"package": "sample", "version": "1.0"}]}))
    return report, path


def test_lock_freezes_verified_resolved_graph(tmp_path):
    report, _ = wheel_fixture(tmp_path)
    wheel_lock.generate(report, tmp_path, {})
    assert "sample==1.0 --hash=sha256:" in (tmp_path / wheel_lock.LOCK_NAME).read_text()
    assert len(wheel_lock.verify(tmp_path, {})) == 1


@pytest.mark.parametrize("corruption", ["bytes", "lock", "excluded", "duplicate", "missing_pin", "unresolved"])
def test_lock_fails_closed(tmp_path, corruption):
    report, path = wheel_fixture(tmp_path)
    exclusions = {}
    if corruption == "bytes":
        path.write_bytes(b"changed")
    elif corruption == "excluded":
        exclusions["sample"] = "Windows-only"
    elif corruption == "duplicate":
        report["graph_attempts"][0]["wheels"] *= 2
    elif corruption == "missing_pin":
        report["packages"].append({"package": "missing", "version": "1"})
    elif corruption == "unresolved":
        report["graph_attempts"][0]["resolved"] = False
    if corruption == "lock":
        wheel_lock.generate(report, tmp_path, {})
        (tmp_path / wheel_lock.LOCK_NAME).write_text("sample==1.0\n")
        with pytest.raises(ValueError):
            wheel_lock.verify(tmp_path, {})
    else:
        with pytest.raises(ValueError):
            wheel_lock.generate(report, tmp_path, exclusions)


def test_payload_matches_windows_source_closure_without_changing_windows_builder():
    from tests.test_installer_files_complete import reachable_modules, staged_sources
    manifest = json.loads((ROOT / "scripts/mac/payload.json").read_text())
    assert set(manifest["paths"]) == (staged_sources() - {"uoink.cmd", "scripts/install-watchdog.ps1"}) | {
        "VERSION", "LICENSE", "third-party-notices"}
    files = set(bundle.payload_files())
    assert reachable_modules(ROOT) <= files
    assert {Path("skills/uoink/SKILL.md"), Path("voice_dna/VOICE-DNA.md"), Path("extension/manifest.json")} <= files
    assert not any(p.name in {"token.txt", "server.log"} for p in files)


def test_tree_inventory_detects_content_modes_and_new_files(tmp_path):
    path = tmp_path / "file"
    path.write_bytes(b"before")
    before = bundle.tree_inventory(tmp_path)
    path.write_bytes(b"after")
    assert bundle.tree_inventory(tmp_path) != before
    (tmp_path / "extra").mkdir()
    assert any(row["type"] == "directory" for row in bundle.tree_inventory(tmp_path))


def archive(tmp_path, name):
    path = tmp_path / "python.tar.gz"
    with tarfile.open(path, "w:gz") as stream:
        entry = tarfile.TarInfo(name)
        entry.size = 5
        stream.addfile(entry, io.BytesIO(b"hello"))
    pin = {"size_bytes": path.stat().st_size, "sha256": bundle.sha256(path)}
    return path, pin


def test_extract_hash_and_traversal_checks(tmp_path):
    path, pin = archive(tmp_path, "python/bin/python3")
    bundle.extract_python(path, tmp_path / "good", pin)
    assert (tmp_path / "good/python/bin/python3").read_bytes() == b"hello"
    with pytest.raises(ValueError, match="hash"):
        bundle.extract_python(path, tmp_path / "bad", {**pin, "sha256": "0" * 64})
    path, pin = archive(tmp_path, "python/../../outside")
    with pytest.raises(tarfile.FilterError):
        bundle.extract_python(path, tmp_path / "escape", pin)
    assert not (tmp_path / "outside").exists()


def test_builder_cannot_download_on_windows(monkeypatch, tmp_path):
    monkeypatch.setattr(bundle.sys, "platform", "win32")
    with pytest.raises(RuntimeError, match="macOS arm64"):
        bundle.build(tmp_path / "wheels", tmp_path / "output")
    assert not (tmp_path / "output").exists()


def test_pip_scripts_are_relocatable_and_valid_python():
    for header in ("#!/temporary/build/python3\n", "#!/bin/sh\n'''exec' /build/python3 \"$0\" \"$@\"\n' '''\n"):
        result = bundle.relocate_python_script(header + "print('ok')\n")
        assert "/build/" not in result
        assert '-B -s "$0"' in result
        compile(result, "script", "exec")


@pytest.mark.parametrize("problem", ["arch", "dependency", "rpath", None])
def test_native_inventory_rejects_wrong_architecture_and_external_loaders(monkeypatch, tmp_path, problem):
    from types import SimpleNamespace
    binary = tmp_path / "native.dylib"
    binary.write_bytes(b"\xcf\xfa\xed\xfe" + b"fixture")
    assert all(len(magic) == 4 for magic in bundle.MACHO)

    def inspect(command, **kwargs):
        if command[0] == "lipo":
            output = "x86_64" if problem == "arch" else "arm64"
        elif command[1] == "-L":
            dependency = "/opt/homebrew/lib/libbad.dylib" if problem == "dependency" else "/usr/lib/libSystem.B.dylib"
            output = f"{binary}:\n\t{dependency} (compatibility version 1.0.0)\n"
        else:
            output = "cmd LC_RPATH\npath /Users/runner/build/lib (offset 12)" if problem == "rpath" else ""
        return SimpleNamespace(stdout=output)

    monkeypatch.setattr(bundle, "run", inspect)
    if problem:
        with pytest.raises(ValueError):
            bundle.binary_inventory(tmp_path)
    else:
        assert bundle.binary_inventory(tmp_path)[0]["architectures"] == "arm64"
