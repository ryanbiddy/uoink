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
                                    "Contents/Resources/Python/bin/python3",
                                    "Contents/Resources/Python/lib/python3.13/site-packages/PIL/_imaging.so",
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
    monkeypatch.setattr(bundle_smoke, "menu_icon_evidence", lambda *a: {"mode": "image"})
    app = tmp_path / "Original.app"
    app.mkdir()
    (app / "payload").write_text("original")
    (app / "Contents/Resources").mkdir(parents=True)
    (app / "Contents/Resources/VERSION").write_text("3.10.0")
    for relative in ("Contents/Resources/Python/lib/python3.13/site-packages/PyObjCTest/__init__.py",
                     "Contents/Frameworks/example.dSYM/Contents/Resources/DWARF/example"):
        target = app / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"debug/test fixture")
    bundle.prune_development_payload(app, tmp_path / "development-pruned.json")
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
        if command[0] == "/bin/ps":
            if command[1] == "-axo":
                row = "" if current[0].dead else f"{current[0].pid + 1} -m helper.mac_menubar --data-root {current[0].profile}"
                return SimpleNamespace(returncode=0, stdout=row)
            if command[-1] == "stat=":
                return SimpleNamespace(returncode=1, stdout="")
            return SimpleNamespace(returncode=0, stdout=str(current[0].python) + " -B -s -m helper.mac_menubar")
        if "connect" in command:
            scratch = Path(kwargs["cwd"])
            contents = scratch / "Relocated App With Spaces/Uoink.app/Contents"
            return SimpleNamespace(returncode=0,
                stdout=json.dumps({"mcpServers": {"uoink": {
                    "command": str(contents / "Resources/Python/bin/python3"),
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
        return SimpleNamespace(returncode=0, stdout="cocoa")

    current = [None]
    def popen(command, **kwargs):
        pid = 100 if current[0] is None else 200
        current[0] = SimpleNamespace(pid=pid, poll=lambda: None, wait=lambda **kw: 0, kill=lambda: None,
                                     python=Path(command[0]).parents[1] / "Resources/Python/bin/python3",
                                     profile=Path(kwargs["env"]["UOINK_ISOLATED_PROFILE"]).resolve(), dead=False)
        current[0].kill = lambda: setattr(current[0], "dead", True)
        return current[0]

    def request(req, **kwargs):
        url = req.full_url if hasattr(req, "full_url") else req
        if url.endswith("/token"):
            data = {"token": "fixture-only"}
        elif url.endswith("/helper/ui"):
            data = {"ok": True, "alive": True, "connected": True, "pid": current[0].pid + 1}
        else:
            if url.endswith("/helper/quit"):
                current[0].dead = True
            data = {"ok": True, "capabilities": capabilities}
        return io.StringIO(json.dumps(data))

    monkeypatch.setattr(bundle_smoke.socket, "socket", Socket)
    monkeypatch.setattr(Path, "symlink_to", lambda *args, **kwargs: None)
    monkeypatch.setattr(bundle_smoke.urllib.request, "urlopen", request)
    monkeypatch.setattr(bundle_smoke.subprocess, "Popen", popen)
    monkeypatch.setattr(bundle_smoke.time, "sleep", lambda *_: None)
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
    assert report["development_payload"] == []
    if not mutate and not fail:
        assert report["cocoa"]["import_only"]
        assert report["menubar"]["connected"]
        assert report["menubar"]["duplicate_launch_same_pid"]
        assert report["menubar"]["quit_no_survivor"]
    assert app.is_dir()


def test_python_pruning_records_removals_and_preserves_runtime(tmp_path):
    app = tmp_path / "Uoink.app"
    root = app / bundle.PYTHON_ROOT
    discarded = ["bin/pip3", "bin/python3-config", "bin/python3.14", "include/python3.13/Python.h",
                 "lib/pkgconfig/python-3.13-embed.pc", "lib/python3.13/config-3.13-darwin/Makefile",
                 "share/man/man1/python.1", "lib/python3.13/test/test_os.py",
                 "lib/python3.13/unittest/test/test_case.py", "lib/python3.13/ctypes/test/test_loading.py"]
    retained = ["bin/python3", "lib/libpython3.13.dylib", "lib/python3.13/os.py",
                "lib/python3.13/lib-dynload/_ssl.so", "lib/python3.13/lib-dynload/_tkinter.so",
                "lib/python3.13/tkinter/filedialog.py", "lib/python3.13/idlelib/__init__.py",
                "lib/tcl8.6/init.tcl", "lib/tk8.6/tk.tcl",
                "lib/python3.13/site-packages/torchcodec/libtorchcodec_core7.dylib",
                "lib/python3.13/site-packages/package/tests/runtime_data.json"]
    for name in discarded + retained:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fixture")
    report = tmp_path / "python-pruned.json"
    rows = bundle.prune_python(app, report)
    assert rows == json.loads(report.read_text())
    assert {r["path"] for r in rows if r["type"] == "file"} == set(discarded)
    assert all(not (root / name).exists() for name in discarded)
    assert all((root / name).read_bytes() == b"fixture" for name in retained)


@pytest.mark.parametrize("external", [False, True])
def test_python_pruning_keeps_only_internal_interpreter_target(tmp_path, external):
    app = tmp_path / "Uoink.app"
    root = app / bundle.PYTHON_ROOT
    (root / "bin").mkdir(parents=True)
    target = tmp_path / "outside-python" if external else root / "bin/python3.13"
    target.write_bytes(b"interpreter")
    try:
        (root / "bin/python3").symlink_to(target)
    except OSError as error:
        pytest.skip(f"Symlink creation unavailable: {error}")
    report = tmp_path / "pruned.json"
    if external:
        with pytest.raises(ValueError, match="inside Python/bin"):
            bundle.prune_python(app, report)
    else:
        assert bundle.prune_python(app, report) == []
    assert target.read_bytes() == b"interpreter"
    assert (root / "bin/python3").is_symlink()


def test_development_pruning_records_nested_debug_and_pyobjc_tests_only(tmp_path):
    app = tmp_path / "Uoink.app"
    site = "Contents/Resources/Python/lib/python3.13/site-packages/"
    discarded = [site + "PyObjCTest/__init__.py", site + "PyObjCTest/NULL.so",
                 site + "PyObjCTest/NULL.so.dSYM/Contents/Resources/DWARF/NULL.so",
                 site + "objc/_objc.so.dSYM/Contents/Resources/DWARF/_objc.so",
                 "Contents/Frameworks/native.dSYM/Contents/Resources/DWARF/native"]
    retained = [site + name for name in ("objc/_objc.so", "AppKit/__init__.py", "Quartz/__init__.py",
                "WebKit/__init__.py", "Security/__init__.py", "webview/platforms/cocoa.py",
                "other/tests/runtime_data.json", "PyObjCTestExtra/__init__.py")]
    for relative in discarded + retained:
        path = app / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"\xcf\xfa\xed\xfe" + b"fixture")
    report = tmp_path / "development-pruned.json"
    rows = bundle.prune_development_payload(app, report)
    assert rows == json.loads(report.read_text())
    assert {r["path"] for r in rows if r["type"] == "file"} == set(discarded)
    assert len({r["path"] for r in rows}) == len(rows)
    assert bundle.development_payload(app) == []
    assert all(not (app / name).exists() for name in discarded)
    assert all((app / name).read_bytes().endswith(b"fixture") for name in retained)
    assert {p.relative_to(app).as_posix() for p in bundle.signing_order(app, require_main=False)} == set(retained)
    assert bundle.prune_development_payload(app, tmp_path / "second-pass.json") == []


def test_development_pruning_refuses_an_escaping_target(tmp_path):
    app = tmp_path / "Uoink.app"
    app.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep").write_text("keep")
    try:
        (app / "native.dSYM").symlink_to(outside, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"Symlink creation unavailable: {error}")
    with pytest.raises(ValueError, match="outside payload root"):
        bundle.prune_development_payload(app, tmp_path / "report.json")
    assert (outside / "keep").read_text() == "keep"


@pytest.mark.parametrize("relative", ["PyObjCTest/__init__.py", "native.dSYM/Contents/Resources/DWARF/native"])
def test_bundle_smoke_rejects_unpruned_payload_before_execution(tmp_path, monkeypatch, relative):
    import bundle_smoke
    app = tmp_path / "Uoink.app"
    target = app / "Contents/Resources" / relative
    target.parent.mkdir(parents=True)
    target.write_text("unwanted payload")
    monkeypatch.setattr(bundle_smoke.subprocess, "run", lambda *a, **kw: pytest.fail("Payload must not execute"))
    output = tmp_path / "evidence"
    with pytest.raises(AssertionError):
        bundle_smoke.smoke(app, output)
    report = json.loads((output / "smoke.json").read_text())
    assert not report["ok"] and report["bundle_unchanged"] and report["development_payload"]


def test_runtime_source_does_not_reference_pyobjc_test_package():
    for relative in bundle.payload_files():
        if relative.suffix == ".py":
            assert "PyObjCTest" not in (ROOT / relative).read_text(encoding="utf-8-sig"), relative
