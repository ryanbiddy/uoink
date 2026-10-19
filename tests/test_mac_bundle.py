"""Offline builder checks: hashes, source closure, archive safety and inventories."""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import subprocess
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
            dependency = "/opt/homebrew/lib/libbad.dylib" if problem == "dependency" else "/usr/lib/libSystem.B.dylib"
            output = f"Load command 0\ncmd LC_LOAD_DYLIB\nname {dependency} (offset 24)\n"
            if problem == "rpath":
                output += "Load command 1\ncmd LC_RPATH\npath /Users/runner/build/lib (offset 12)\n"
        return SimpleNamespace(stdout=output)

    monkeypatch.setattr(bundle, "run", inspect)
    if problem:
        with pytest.raises(ValueError):
            bundle.binary_inventory(tmp_path)
    else:
        assert bundle.binary_inventory(tmp_path)[0]["architectures"] == "arm64"


@pytest.mark.parametrize("universal", [False, True])
@pytest.mark.parametrize("dependency", [
    "@loader_path/libok.dylib", "@rpath/libok.dylib", "@executable_path/../libok.dylib",
    "/usr/lib/libSystem.B.dylib", "/System/Library/Frameworks/Cocoa.framework/Cocoa",
    "/DLC/PIL/.dylibs/libXau.6.dylib", "/opt/homebrew/lib/libbad.dylib",
    "/Users/runner/build/libbad.dylib", "/usr/lib/../../opt/libbad.dylib",
    "/System/../opt/libbad.dylib",
])
def test_native_inventory_distinguishes_install_id_from_real_loads(
        monkeypatch, tmp_path, dependency, universal):
    from types import SimpleNamespace
    binary = tmp_path / "libXau.6.dylib"
    binary.write_bytes(b"\xcf\xfa\xed\xfe" + b"fixture")
    install_id = "/DLC/PIL/.dylibs/libXau.6.dylib"
    arches = ("arm64", "x86_64") if universal else ("arm64",)
    loads = commands = ""
    for arch in arches:
        header = f"{binary} (architecture {arch}):\n"
        loads += header + f"\t{install_id} (compatibility version 1.0.0)\n\t{dependency} (compatibility version 1.0.0)\n"
        commands += (header + f"Load command 0\n      cmd LC_ID_DYLIB\n  cmdsize 64\n     name {install_id} (offset 24)\n"
                     f"Load command 1\n      cmd LC_LOAD_DYLIB\n  cmdsize 64\n     name {dependency} (offset 24)\n"
                     "Load command 2\n      cmd LC_RPATH\n  cmdsize 32\n     path @loader_path/.. (offset 12)\n")
    monkeypatch.setattr(bundle, "run", lambda command, **kwargs: SimpleNamespace(
        stdout=" ".join(arches) if command[0] == "lipo" else loads if command[1] == "-L" else commands))
    if dependency.startswith(("/DLC/", "/opt/", "/Users/")) or "libbad" in dependency:
        with pytest.raises(ValueError, match="Nonrelocatable dependency"):
            bundle.binary_inventory(tmp_path)
    else:
        assert bundle.binary_inventory(tmp_path)[0]["path"] == binary.name


@pytest.mark.parametrize("command", ["LC_LOAD_WEAK_DYLIB", "LC_REEXPORT_DYLIB",
                                     "LC_LAZY_LOAD_DYLIB", "LC_LOAD_UPWARD_DYLIB"])
def test_optional_native_loads_are_still_dependencies(command):
    assert bundle.native_loader_paths(
        f"cmd {command}\nname /outside/libbad.dylib (offset 24)\n"
    ) == [("dependency", "/outside/libbad.dylib")]
    with pytest.raises(ValueError, match="Malformed"):
        bundle.native_loader_paths(f"cmd {command}\nname broken\n")


def test_native_inventory_accepts_bundle_absolute_load_and_system_rpath(monkeypatch, tmp_path):
    from types import SimpleNamespace
    binary = tmp_path / "native.dylib"
    binary.write_bytes(b"\xcf\xfa\xed\xfe" + b"fixture")
    dependency = tmp_path / "internal/libhelper.dylib"
    dependency.parent.mkdir()
    dependency.write_bytes(b"fixture")
    commands = (f"cmd LC_LOAD_DYLIB\nname {dependency} (offset 24)\n"
                "cmd LC_RPATH\npath /usr/lib (offset 12)\n")
    monkeypatch.setattr(bundle, "run", lambda command, **kwargs: SimpleNamespace(
        stdout="arm64" if command[0] == "lipo" else commands if command[1] == "-l" else ""))
    assert bundle.binary_inventory(tmp_path)[0]["path"] == binary.name


PILLOW_RPATH = "/Users/runner/work/Pillow/Pillow/build/deps/darwin/lib"


def loader_fixture(kind, value):
    command, field, offset = ("LC_RPATH", "path", 12) if kind == "rpath" else ("LC_LOAD_DYLIB", "name", 24)
    return f"Load command 1\n      cmd {command}\n  cmdsize 128\n     {field} {value} (offset {offset})\n"


def test_rpath_rewrite_plan_parses_universal_otool_fixture(tmp_path):
    commands = (
        "Load command 0\n      cmd LC_ID_DYLIB\n  cmdsize 64\n"
        "     name /DLC/PIL/.dylibs/libjpeg.62.4.0.dylib (offset 24)\n"
        + loader_fixture("dependency", "/outside/libbad.dylib")
        + "".join(loader_fixture("rpath", value) for value in (
            PILLOW_RPATH, "/opt/homebrew/lib", "/System/PrivateFrameworks",
            "/System/Library/../../outside", "@loader_path/..", "@rpath",
            "@executable_path/../Frameworks", "/usr/lib", "/System/Library",
            "/System/Library/Frameworks", str(tmp_path / "Contents/Frameworks"), "relative/lib")))
    universal = "libjpeg (architecture arm64):\n" + commands + "libjpeg (architecture x86_64):\n" + commands
    assert bundle.rpath_removals(universal, tmp_path) == [
        PILLOW_RPATH, "/opt/homebrew/lib", "/System/PrivateFrameworks", "/System/Library/../../outside"]


@pytest.mark.parametrize("kind", ["dependency", "rpath"])
@pytest.mark.parametrize("value,allowed", [
    ("/usr/lib", True), ("/usr/lib/libSystem.B.dylib", True),
    ("/System/Library", True), ("/System/Library/Frameworks/Cocoa.framework/Cocoa", True),
    ("/System", False), ("/System/PrivateFrameworks/libbad.dylib", False),
    ("/System/LibraryExtra/libbad.dylib", False), ("/usr/library/libbad.dylib", False),
    ("/System/Library/../../outside", False), ("/usr/lib/../../outside", False),
    ("/Users/runner/build/libbad.dylib", False), ("relative/lib", False),
])
def test_native_inventory_checks_stored_paths(monkeypatch, tmp_path, kind, value, allowed):
    from types import SimpleNamespace
    binary = tmp_path / "native.dylib"
    binary.write_bytes(b"\xcf\xfa\xed\xfe" + b"fixture")
    commands = loader_fixture(kind, value)
    monkeypatch.setattr(bundle, "run", lambda command, **kwargs: SimpleNamespace(
        stdout="arm64" if command[0] == "lipo" else commands))
    if allowed:
        assert bundle.binary_inventory(tmp_path)
    else:
        with pytest.raises(ValueError, match=f"Nonrelocatable {kind}"):
            bundle.binary_inventory(tmp_path)


@pytest.mark.parametrize("case", ["outside_in", "inside_out", "inside_out_in", "inside_in", "traversal", "sibling"])
def test_loader_path_symlink_containment_without_os_symlink_privileges(monkeypatch, tmp_path, case):
    app = tmp_path / "Uoink.app"
    app.mkdir()
    inside = app / "lib"
    outside = tmp_path / "external"
    link = app / "link"
    links = {}
    if case == "outside_in":
        value, links = outside, {outside: inside}
    elif case == "inside_out":
        value, links = link, {link: outside}
    elif case == "inside_out_in":
        value, links = link, {link: outside, outside: inside}
    elif case == "inside_in":
        value, links = link, {link: Path("lib")}
    elif case == "traversal":
        value = app / ".." / "external"
    else:
        value = tmp_path / "Uoink.app-extra/lib"
    # Model the OS answers, including the deceptive final target inside the app.
    monkeypatch.setattr(Path, "is_symlink", lambda path: path in links)
    monkeypatch.setattr(bundle.os, "readlink", lambda path: str(links[path]))
    monkeypatch.setattr(Path, "resolve", lambda path, **kwargs:
                        app if path == app else outside if case == "inside_out" else inside)
    allowed = case == "inside_in"
    assert bundle.allowed_absolute_loader_path(str(value), app) is allowed
    assert bundle.rpath_removals(loader_fixture("rpath", str(value)), app) == ([] if allowed else [str(value)])


@pytest.mark.parametrize("failure", [None, "delete", "remaining_rpath", "dependency"])
@pytest.mark.parametrize("relative", ["libjpeg.62.4.0.dylib", "Contents/Helpers/ffmpeg",
                                    "Contents/Helpers/ffprobe", "Contents/Frameworks/FFmpeg7/libavcodec.61.dylib",
                                    "Contents/MacOS/Uoink"])
def test_rpath_rewrite_reports_edits_and_inventory_rechecks(monkeypatch, tmp_path, failure, relative):
    from types import SimpleNamespace
    app = tmp_path / "Uoink.app"
    app.mkdir()
    binary = app / relative
    binary.parent.mkdir(parents=True, exist_ok=True)
    binary.write_bytes(b"\xcf\xfa\xed\xfe" + b"before")
    (app / "plain.txt").write_text("not Mach-O")
    report = tmp_path / "removals.json"
    pending = [PILLOW_RPATH, "/opt/homebrew/lib"]
    calls = []

    def run(command, **kwargs):
        assert kwargs["check"] is True
        calls.append(command)
        output = ""
        if command[0] == "otool":
            output = "".join(loader_fixture("rpath", value) for value in pending)
            if failure == "dependency":
                output += loader_fixture("dependency", "/outside/libbad.dylib")
        elif command[0] == "install_name_tool":
            assert command[1] == "-delete_rpath" and len(command) == 4
            if failure == "delete" and command[2] == pending[-1]:
                raise subprocess.CalledProcessError(1, command)
            if failure != "remaining_rpath":
                pending.remove(command[2])
        elif command[0] == "codesign":
            pytest.fail("Rpath edits must leave signing to the final inside-out pass")
        elif command[0] == "lipo":
            output = "arm64"
        return SimpleNamespace(stdout=output)

    monkeypatch.setattr(bundle.subprocess, "run", run)
    if failure == "delete":
        with pytest.raises(subprocess.CalledProcessError):
            bundle.rewrite_rpaths(app, report)
    else:
        bundle.rewrite_rpaths(app, report)
        if failure:
            with pytest.raises(ValueError, match="Nonrelocatable"):
                bundle.binary_inventory(app)
        else:
            inventory = bundle.binary_inventory(app)
            assert inventory[0]["sha256"] == hashlib.sha256(binary.read_bytes()).hexdigest()
            bundle.rewrite_rpaths(app, tmp_path / "second-report.json")
            assert json.loads((tmp_path / "second-report.json").read_text()) == []
    expected = [PILLOW_RPATH] if failure == "delete" else [PILLOW_RPATH, "/opt/homebrew/lib"]
    assert json.loads(report.read_text()) == [{"file": relative, "rpath": value} for value in expected]
    assert not any(command[0] == "codesign" for command in calls)


@pytest.mark.parametrize("mutate,fail", [(False, False), (True, False), (False, True)])
def test_smoke_success_requires_completed_checks_and_immutable_bundle(monkeypatch, tmp_path, mutate, fail):
    from types import SimpleNamespace
    import bundle_smoke
    app = tmp_path / "Original.app"
    app.mkdir()
    (app / "payload").write_text("original")
    output = tmp_path / "evidence"
    capabilities = {"library_mirror": {"code": "library_mirror_unavailable_macos"},
                    "media": {"available": True, "code": None}}

    class Socket:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def bind(self, address):
            assert address == ("127.0.0.1", 0)

        def getsockname(self):
            return ("127.0.0.1", 43871)

    def run(command, **kwargs):
        if "connect" in command:
            scratch = Path(kwargs["cwd"])
            contents = scratch / "Relocated App With Spaces/Uoink.app/Contents"
            return SimpleNamespace(returncode=0,
                stdout=json.dumps({"mcpServers": {"uoink": {
                    "command": str(contents / "Frameworks/Python/bin/python3"),
                    "args": ["-B", "-s", str(contents / "Resources/uoink_mcp.py")]}}}),
                stderr=str(Path(kwargs["env"]["HOME"]) / "Library/Application Support/Claude/claude_desktop_config.json"))
        if "helper.mac_lifecycle" in command:
            import plistlib
            contents = Path(command[-1]) / "Contents"
            return SimpleNamespace(returncode=0, stdout=plistlib.dumps({
                "ProgramArguments": [str(contents / "MacOS/Uoink"), "--helper"],
                "KeepAlive": False, "RunAtLoad": True,
                "StandardOutPath": str(Path(kwargs["env"]["HOME"]) / "Library/Logs/Uoink/launchd.out.log")}))
        if command[-1] == "status":
            mirror = "mirror" in command
            return SimpleNamespace(returncode=1 if mirror else 0, stderr="",
                stdout=json.dumps({"ok": not mirror, "helper_running": True, "code": "library_mirror_unavailable_macos",
                                   "capabilities": capabilities}))
        if fail:
            raise RuntimeError("synthetic Pillow failure")
        if mutate:
            relocated = Path(kwargs["cwd"]) / "Relocated App With Spaces/Uoink.app"
            (relocated / "payload").write_text("changed")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(bundle_smoke.socket, "socket", Socket)
    monkeypatch.setattr(Path, "symlink_to", lambda *args, **kwargs: None)
    monkeypatch.setattr(bundle_smoke.urllib.request, "urlopen", lambda *args, **kwargs: io.StringIO(
        json.dumps({"ok": True, "capabilities": capabilities})))
    monkeypatch.setattr(bundle_smoke.subprocess, "Popen", lambda *args, **kwargs: SimpleNamespace(poll=lambda: None))
    monkeypatch.setattr(bundle_smoke.subprocess, "run", run)
    monkeypatch.setattr(bundle_smoke, "stdio", lambda *args: {"ok": True})
    monkeypatch.setattr(bundle_smoke, "media_smoke", lambda *args: {"ok": True})
    monkeypatch.setattr(bundle_smoke, "stop", lambda proc: None)
    if mutate or fail:
        with pytest.raises(AssertionError if mutate else RuntimeError):
            bundle_smoke.smoke(app, output)
    else:
        bundle_smoke.smoke(app, output)
    report = json.loads((output / "smoke.json").read_text())
    assert report["ok"] is (not mutate and not fail)
    assert report["bundle_unchanged"] is (not mutate)
    assert app.is_dir()
