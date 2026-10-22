"""Portable AppKit resource and per-copy translocation tests. No Apple tools run."""
import ctypes
import io
import json
import os
from pathlib import Path
import plistlib
import shutil
import signal
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/mac"))
import build_bundle
import bundle_smoke
import dmg_smoke
import quarantine_smoke
import receipt
from helper import mac_menubar
from tests.test_mac_receipt import make_app


@pytest.mark.parametrize("main_app,indexed", [(True, True), (False, True), (False, False), (False, "error")])
def test_nsbundle_resources_follow_running_executable(tmp_path, monkeypatch, main_app, indexed, caplog):
    app = make_app(tmp_path / "AppTranslocation/uuid/d/Uoink.app")
    assets = app / "Contents/Resources/assets/brand"
    shutil.copytree(ROOT / "assets/brand", assets)
    def lookup(name, ext, subdir):
        if indexed == "error":
            raise ValueError("resource index unavailable")
        return str(assets / (name + "." + ext)) if indexed else None
    bundle = SimpleNamespace(bundlePath=lambda: str(app), bundleIdentifier=lambda: "com.ryanbiddy.uoink",
                             resourcePath=lambda: str(app / "Contents/Resources"),
                             pathForResource_ofType_inDirectory_=lookup)
    python_bundle = SimpleNamespace(bundlePath=lambda: str(app / "Contents/Resources/Python/bin"),
                                    bundleIdentifier=lambda: None)
    NSBundle = SimpleNamespace(mainBundle=lambda: bundle if main_app else python_bundle,
                               bundleWithPath_=Mock(return_value=bundle))
    monkeypatch.setattr(mac_menubar, "sys", SimpleNamespace(executable=str(app / receipt.PYTHON_EXECUTABLE)))
    image, button = Mock(), Mock()
    reps = []

    def decode(raw):
        assert raw.startswith(b"\x89PNG\r\n\x1a\n")
        rep = Mock()
        reps.append(rep)
        return rep
    A = SimpleNamespace(NSImage=SimpleNamespace(alloc=lambda: SimpleNamespace(initWithSize_=lambda _: image)),
                        NSBitmapImageRep=SimpleNamespace(imageRepWithData_=decode, imageRepWithContentsOfFile_=lambda _: None))
    NSData = SimpleNamespace(dataWithBytes_length_=lambda raw, size: raw if len(raw) == size else None)
    with caplog.at_level("INFO", logger="uoink.menubar"):
        proof = mac_menubar.install_status_icon(button, A, NSBundle, NSData)
    assert proof["mode"] == "image" and len(proof["templates"]) == 2
    assert {Path(row["path"]).parent for row in proof["templates"]} == {assets}
    assert all(row["bytes"] > 0 and len(row["sha256"]) == 64 for row in proof["templates"])
    assert all(row["filename_decode"] == "nil" for row in proof["templates"])
    assert str(assets / "menubar-template.png") in caplog.text
    assert image.addRepresentation_.call_count == 2
    button.setImage_.assert_called_once_with(image)
    button.setTitle_.assert_not_called()
    log_file = tmp_path / "menu.log"
    log_file.write_text(caplog.text)
    assert bundle_smoke.menu_icon_evidence(log_file, os.getpid(), app) == proof
    if not main_app:
        NSBundle.bundleWithPath_.assert_called_once_with(str(app))


@pytest.mark.parametrize("failure", ["lookup", "missing", "decode", "exception"])
def test_icon_failure_keeps_text_menu_and_records_path(tmp_path, monkeypatch, failure, caplog):
    app = make_app(tmp_path / "Uoink.app")
    assets = app / "Contents/Resources/assets/brand"
    if failure != "missing":
        shutil.copytree(ROOT / "assets/brand", assets)
    bundle = SimpleNamespace(bundlePath=lambda: str(app), bundleIdentifier=lambda: "com.ryanbiddy.uoink",
                             resourcePath=lambda: str(app / "Contents/Resources"),
                             pathForResource_ofType_inDirectory_=lambda *a: None)
    NSBundle = SimpleNamespace(mainBundle=Mock(side_effect=OSError("bundle unavailable")) if failure == "lookup"
                               else lambda: bundle, bundleWithPath_=lambda _: None if failure == "lookup" else bundle)
    monkeypatch.setattr(mac_menubar, "sys", SimpleNamespace(executable=str(app / receipt.PYTHON_EXECUTABLE)))
    button, image = Mock(), Mock()
    decode = Mock(side_effect=ValueError("native decode failed")) if failure == "exception" else Mock(return_value=None)
    A = SimpleNamespace(NSImage=SimpleNamespace(alloc=lambda: SimpleNamespace(initWithSize_=lambda _: image)),
                        NSBitmapImageRep=SimpleNamespace(imageRepWithData_=decode))
    proof = mac_menubar.install_status_icon(button, A, NSBundle,
                                           SimpleNamespace(dataWithBytes_length_=lambda raw, size: raw))
    assert proof["mode"] == "text"
    button.setTitle_.assert_called_with("Uoink")
    button.setImage_.assert_not_called()
    if failure != "lookup":
        assert str(assets / "menubar-template.png") in caplog.text
        assert all("error" in row for row in proof["attempts"])


def test_build_requires_both_identical_menu_resources(tmp_path):
    app = make_app(tmp_path / "Uoink.app")
    assets = app / "Contents/Resources/assets/brand"
    shutil.copytree(ROOT / "assets/brand", assets)
    assert len(build_bundle.verify_menu_resources(app)) == 2
    for name in mac_menubar.TEMPLATES:
        assert Path("assets/brand") / name in build_bundle.payload_files()
    (assets / "menubar-template.png").write_bytes(b"changed")
    with pytest.raises(ValueError, match="changed menu resource"):
        build_bundle.verify_menu_resources(app)


@pytest.fixture
def copies(tmp_path, monkeypatch):
    app = make_app(tmp_path / "Applications With Spaces/Uoink.app")
    other = make_app(tmp_path / "Other Applications/Uoink.app")
    trans = make_app(tmp_path / "AppTranslocation/owned/d/Uoink.app")
    foreign = make_app(tmp_path / "AppTranslocation/foreign/d/Uoink.app")
    monkeypatch.setattr(receipt, "translocated_original", lambda p: {trans: app, foreign: other}.get(p))
    return app, other, trans, foreign


def test_process_matching_requires_original_copy_not_same_id_or_bytes(copies, monkeypatch):
    app, other, trans, foreign = copies
    assert receipt.executable_origin(app, str(app / receipt.PYTHON_EXECUTABLE))["translocated"] is False
    proof = receipt.executable_origin(app, str(trans / receipt.PYTHON_EXECUTABLE))
    assert proof["original"] == str(app) and proof["method"] == "SecTranslocate"
    for wrong in (other, foreign, Path(str(app) + "-other")):
        assert receipt.executable_origin(app, str(wrong / receipt.PYTHON_EXECUTABLE)) is None
    (trans / "Contents/Info.plist").write_bytes(plistlib.dumps({"CFBundleIdentifier": "other.app"}))
    assert receipt.executable_origin(app, str(trans / receipt.PYTHON_EXECUTABLE)) is None


def test_unverified_translocation_and_escaping_link_are_not_owned(copies, monkeypatch):
    app, other, trans, foreign = copies
    monkeypatch.setattr(receipt, "translocated_original", lambda _: None)
    assert receipt.executable_origin(app, str(trans / receipt.PYTHON_EXECUTABLE)) is None
    original = Path.resolve
    linked = app / "Contents/Helpers/escaped"
    monkeypatch.setattr(Path, "resolve", lambda p, *a, **kw:
                        other / receipt.PYTHON_EXECUTABLE if p == linked else original(p, *a, **kw))
    assert receipt.executable_origin(app, str(linked)) is None


def test_scoped_processes_include_only_owned_normal_and_translocated_copies(copies, monkeypatch):
    app, other, trans, foreign = copies
    from _platform import DarwinProcessObservation
    mapping = dict(enumerate([app, other, trans, foreign], 10))
    monkeypatch.setattr(receipt, "command", lambda _: {"exit": 0, "stdout": "10 11 12 13"})
    monkeypatch.setattr(receipt, "darwin_observe", lambda pid, **kw:
                        DarwinProcessObservation("alive", pid * 1000000, str(mapping[pid] / receipt.PYTHON_EXECUTABLE)))
    assert [row["pid"] for row in receipt.scoped_processes(app)] == [10, 12]


def test_health_binds_translocated_interpreter_and_rejects_other_copy(copies, monkeypatch):
    app, other, trans, foreign = copies
    identity = {"pid": 10, "created_ms": 1, "started_us": 1000, "executable": str(trans / receipt.PYTHON_EXECUTABLE)}
    monkeypatch.setattr(receipt, "observe", lambda pid: dict(identity))
    monkeypatch.setattr(receipt, "listeners", lambda port: [10])
    monkeypatch.setattr(receipt.urllib.request, "build_opener", lambda *a: SimpleNamespace(
        open=lambda *a, **kw: io.BytesIO(b'{"ok": true}')))
    proc = SimpleNamespace(pid=10, poll=lambda: None)
    proof = receipt.bind_health(proc, app, 18081)
    assert proof["origin"]["bundle"] == str(trans) and proof["origin"]["translocated"]
    identity["executable"] = str(foreign / receipt.PYTHON_EXECUTABLE)
    with pytest.raises(ValueError, match="non-bundle interpreter"):
        receipt.bind_health(proc, app, 18081)


@pytest.mark.parametrize("state", ["alive", "dead", "unknown", "reused"])
def test_cleanup_never_signals_other_copy_or_reused_pid(copies, monkeypatch, state):
    app, other, trans, foreign = copies
    owned = {"pid": 10, "created_ms": 1, "started_us": 1000, "executable": str(trans / receipt.PYTHON_EXECUTABLE)}
    outsider = {**owned, "pid": 20, "executable": str(foreign / receipt.PYTHON_EXECUTABLE)}
    monkeypatch.setattr(receipt, "scoped_processes", lambda _: [owned])
    monkeypatch.setattr(receipt, "darwin_liveness", lambda *a: "alive" if state == "reused" else state)
    monkeypatch.setattr(receipt, "observe", lambda pid: {**owned, "started_us": 2000} if state == "reused" else owned)
    monkeypatch.setattr(receipt, "no_survivors", lambda *a, **kw: {"ok": True})
    monkeypatch.setattr(receipt, "signal", SimpleNamespace(SIGTERM=15, SIGKILL=9))
    kill = Mock()
    monkeypatch.setattr(receipt.os, "kill", kill)
    proof = receipt.stop_owned(app, [owned, outsider], 18081)
    assert proof["ok"]
    assert kill.call_args_list == ([((10, 15),)] if state == "alive" else [])


def test_survivor_identity_is_rechecked_after_settle(tmp_path, monkeypatch):
    identity = {"pid": 10, "created_ms": 1, "started_us": 1000, "executable": "gone"}
    states = iter(["alive", "dead"])
    monkeypatch.setattr(receipt, "darwin_liveness", lambda *a: next(states))
    monkeypatch.setattr(receipt, "scoped_processes", lambda _: [])
    owners = iter([[10], []])
    monkeypatch.setattr(receipt, "listeners", lambda _: next(owners))
    monkeypatch.setattr(receipt.time, "sleep", lambda _: None)
    proof = receipt.no_survivors(tmp_path, [identity], 18081)
    assert proof["ok"] and proof["settled_after_s"] == .25
    assert proof["identities"][0]["state"] == "dead"


@pytest.mark.parametrize("mode", ["translocated", "normal", "error"])
def test_security_api_original_url_and_cf_ownership(tmp_path, monkeypatch, mode):
    original = tmp_path / "Original/Uoink.app"
    released = []

    def status(url, value, error):
        assert url == 1
        ctypes.cast(value, ctypes.POINTER(ctypes.c_bool))[0] = mode == "translocated"
        if mode == "error":
            ctypes.cast(error, ctypes.POINTER(ctypes.c_void_p))[0] = 3
            return False
        return True

    def get_path(url, resolve, buffer, size):
        assert url == 2 and resolve
        buffer.value = os.fsencode(original)
        return True
    cf = SimpleNamespace(CFURLCreateFromFileSystemRepresentation=lambda *a: 1,
                         CFURLGetFileSystemRepresentation=get_path, CFRelease=released.append)
    security = SimpleNamespace(SecTranslocateIsTranslocatedURL=status,
                               SecTranslocateCreateOriginalPathForURL=lambda *a: 2)
    monkeypatch.setattr(receipt, "translocation_api", lambda: (cf, security))
    if mode == "error":
        with pytest.raises(ValueError, match="translocation status"):
            receipt.translocated_original(tmp_path)
        assert released == [3, 1]
    else:
        assert receipt.translocated_original(tmp_path) == (original if mode == "translocated" else None)
        assert released == ([2, 1] if mode == "translocated" else [1])


@pytest.mark.parametrize("quarantined", [True, False])
def test_normal_install_only_clears_quarantine_on_disposable_copy(tmp_path, monkeypatch, quarantined):
    app = make_app(tmp_path / "Applications With Spaces/Uoink.app")
    calls = []
    attrs = iter(["com.apple.quarantine: fixture" if quarantined else "", ""])

    def run(argv, **kw):
        calls.append(argv)
        return SimpleNamespace(stdout=next(attrs) if "-lr" in argv else "")
    monkeypatch.setattr(dmg_smoke, "run", run)
    proof = {}
    dmg_smoke.prepare_normal_install(app, proof)
    assert proof["quarantine_absent"] and proof["signature_verified"]
    assert [c for c in calls if "-dr" in c] == (
        [["/usr/bin/xattr", "-dr", "com.apple.quarantine", app]] if quarantined else [])
    assert calls[-1] == ["codesign", "--verify", "--strict", "--deep", app]


def test_ci_does_not_credit_text_fallback_as_icon_proof(tmp_path):
    path = tmp_path / "stderr"
    path.write_text('INFO:uoink.menubar:menu bar icon: {"pid":10,"mode":"text","templates":[]}\n')
    with pytest.raises(ValueError, match="Both menu templates"):
        bundle_smoke.menu_icon_evidence(path, 10, tmp_path)


@pytest.mark.parametrize("foreign_menu", [False, True])
def test_menu_proof_requires_live_event_loop_in_same_bundle(copies, tmp_path, monkeypatch, foreign_menu):
    app, other, trans, foreign = copies
    helper = {"pid": 10, "created_ms": 1, "started_us": 1000, "executable": str(trans / receipt.PYTHON_EXECUTABLE)}
    menu = {**helper, "pid": 11, "executable": str((foreign if foreign_menu else trans) / receipt.PYTHON_EXECUTABLE)}
    bound = {"port": 18081, "identity": helper,
             "origin": receipt.interpreter_origin(app, helper["executable"])}
    monkeypatch.setattr(receipt, "listeners", lambda _: [10])
    monkeypatch.setattr(receipt, "observe", lambda pid: helper if pid == 10 else menu)
    replies = iter([{"token": "fixture-secret"},
                    {"helper_pid": 10, "pid": 11, "alive": True, "connected": False},
                    {"helper_pid": 10, "pid": 11, "alive": True, "connected": True}])
    calls = []

    def open_request(request, **kw):
        calls.append(request)
        return io.BytesIO(json.dumps(next(replies)).encode())
    monkeypatch.setattr(quarantine_smoke.urllib.request, "build_opener",
                        lambda *a: SimpleNamespace(open=open_request))
    monkeypatch.setattr(quarantine_smoke.time, "sleep", lambda _: None)
    monkeypatch.setattr(bundle_smoke, "menu_icon_evidence", lambda *a: {"mode": "image"})
    if foreign_menu:
        with pytest.raises(ValueError, match="non-bundle interpreter"):
            quarantine_smoke.bind_menu(app, bound, tmp_path / "stderr")
    else:
        proof = quarantine_smoke.bind_menu(app, bound, tmp_path / "stderr")
        assert proof["connected"] and proof["identity"] == menu
        assert "fixture-secret" not in json.dumps(proof)
    assert [r.full_url for r in calls] == ["http://127.0.0.1:18081" + p for p in ("/token", "/helper/ui", "/helper/ui")]


@pytest.mark.parametrize("translocated", [True, False])
@pytest.mark.parametrize("menu_fails", [True, False])
def test_launch_requires_menu_and_cleans_on_success_or_crash(copies, tmp_path, monkeypatch, translocated, menu_fails):
    app, other, trans, foreign = copies
    (app / "Contents/Resources/VERSION").write_text("3.10.0")
    helper = {"pid": 10, "created_ms": 1, "started_us": 1000,
              "executable": str((trans if translocated else app) / receipt.PYTHON_EXECUTABLE)}
    menu = {**helper, "pid": 11}
    bound = {"identity": helper, "origin": {"translocated": translocated}, "port": 18081}
    monkeypatch.setattr(quarantine_smoke.subprocess, "run",
                        lambda *a, **kw: SimpleNamespace(returncode=0, stdout="", stderr=""))
    monkeypatch.setattr(receipt, "listeners", lambda _: [10])
    monkeypatch.setattr(receipt, "bind_health", lambda *a: bound)
    monkeypatch.setattr(quarantine_smoke, "bind_menu",
                        Mock(side_effect=RuntimeError("menu crashed")) if menu_fails else lambda *a: {"identity": menu})
    cleanup = Mock(return_value={"ok": True})
    monkeypatch.setattr(receipt, "stop_owned", cleanup)
    report = {}
    if menu_fails:
        with pytest.raises(RuntimeError, match="menu crashed"):
            quarantine_smoke.launch(app, tmp_path, tmp_path / "out", report, translocated=translocated)
    else:
        quarantine_smoke.launch(app, tmp_path, tmp_path / "out", report, translocated=translocated)
        assert report["menubar"]["identity"] == menu
    assert cleanup.call_args.args[1] == ([helper] if menu_fails else [helper, menu])
    assert report["cleanup"]["ok"]
