"""Portable receipt verdict tests. Apple tools and installed execution are mocked."""
from contextlib import contextmanager
import io
import json
from pathlib import Path
import plistlib
import shutil
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/mac"))
import receipt


def make_app(app):
    for name in ("Contents/MacOS/Uoink", "Contents/Resources/server.py", "Contents/Resources/uoink_mcp.py",
                 str(receipt.PYTHON_EXECUTABLE)):
        path = app / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fixture")
    (app / "Contents/Info.plist").write_bytes(plistlib.dumps({
        "CFBundleIdentifier": "com.ryanbiddy.uoink", "CFBundleShortVersionString": "3.10.0", "CFBundleVersion": "3100"}))
    return app


@pytest.fixture
def rig(tmp_path, monkeypatch):
    dmg = tmp_path / "fixture.dmg"
    dmg.write_bytes(b"fixture DMG")
    scratch = tmp_path / "Disposable With Spaces"
    scratch.mkdir()
    mounted = make_app(scratch / "mounted/Uoink.app")
    app = make_app(scratch / "Applications With Spaces/Uoink.app")
    state = SimpleNamespace(dmg=dmg, scratch=scratch, mounted=mounted, app=app, calls=[], failure=None,
                            real_bind=receipt.bind_health)
    monkeypatch.setattr(receipt.sys, "platform", "darwin")
    monkeypatch.setattr(receipt, "real_home", lambda: tmp_path / "real home")
    monkeypatch.setattr(receipt.tempfile, "mkdtemp", lambda **kw: str(scratch))
    snapshots = []

    def snapshot(home):
        snapshots.append(home)
        return {"data": {".": {"exists": False, "mtime_ns": None}},
                "port_5179": state.failure == "isolation" and len(snapshots) > 1}
    monkeypatch.setattr(receipt, "protected_snapshot", snapshot)

    @contextmanager
    def installed(dmg, scratch, report):
        report.update(app=str(app), read_only=True, detached=False)
        try:
            yield mounted, app
        finally:
            if state.failure == "detach":
                raise OSError("detach failed")
            report["detached"] = True
    monkeypatch.setattr(receipt.dmg_smoke, "installed_dmg", installed)
    monkeypatch.setattr(receipt.dmg_smoke, "prepare_normal_install",
                        lambda app, report: report.update(quarantine_absent=True))

    def command(argv, **kw):
        state.calls.append([str(x) for x in argv])
        result = {"argv": [str(x) for x in argv], "exit": 0, "stdout": "", "stderr": ""}
        if "-c" in argv:
            result["stdout"] = json.dumps({"executable": str(app / receipt.PYTHON_EXECUTABLE), "version": "fixture Python"})
        if "spctl" in str(argv[0]):
            result.update(exit=3, stderr="rejected: ad-hoc")
        if "-dv" in argv:
            digest = "b" if state.failure == "signature" and argv[-1] == app else "a"
            result["stderr"] = "Signature=adhoc\nCDHash=" + digest * 40 + "\n"
        if "--remove" in argv:
            if state.failure == "uninstall":
                result["exit"] = 1
            else:
                shutil.rmtree(app)
            if state.failure == "data":
                (scratch / "profile/index.db").unlink()
        return result
    monkeypatch.setattr(receipt, "command", command)

    def identity(pid):
        return {"pid": pid, "created_ms": 123456.789, "started_us": 123456789,
                "executable": str(app / receipt.PYTHON_EXECUTABLE)}
    monkeypatch.setattr(receipt, "observe", identity)
    monkeypatch.setattr(receipt, "bind_health", lambda proc, app, port: {
        "identity": identity(proc.pid + 2), "supervisor_identity": identity(proc.pid),
        "origin": {"translocated": False}, "listener_pid": proc.pid + 2, "port": port, "health": {"ok": True}})
    monkeypatch.setattr(receipt, "scoped_processes", lambda app: [identity(99)] if state.failure == "survivor" else [])
    monkeypatch.setattr(receipt, "listeners", lambda port: [])
    monkeypatch.setattr(receipt, "darwin_liveness", lambda *a: "unknown" if state.failure == "unknown" else "dead")

    def smoke(app, output, *, scratch, env, observer):
        if state.failure == "smoke":
            raise AssertionError("smoke failed")
        (Path(env["UOINK_ISOLATED_PROFILE"]) / "index.db").write_bytes(b"disposable data")
        for event, pid in (("connected", 10), ("quit", 10), ("relaunch", 20), ("helper_death", 20)):
            if state.failure != "missing_binding":
                observer(event, SimpleNamespace(pid=pid), {"pid": pid + 1})
        result = {"ok": True, "bundle_unchanged": True,
                  "mcp": [{"toolset": "full", "count": 91, "ok": True}, {"toolset": "core", "count": 35, "ok": True}],
                  "menubar": {name: True for name in ("connected", "duplicate_launch_same_pid", "quit_no_survivor",
                                                       "relaunch_connected", "helper_death_no_survivor")}}
        result.update({key: {"ok": True} for key in ("health", "media", "mirror", "connect", "launchagent", "cocoa", "status", "pillow")})
        if state.failure == "missing_check":
            result["mcp"] = []
        if state.failure == "changed_dmg":
            state.dmg.write_bytes(b"changed")
        return result
    monkeypatch.setattr(receipt.bundle_smoke, "smoke", smoke)
    return state


def test_complete_receipt_passes_only_after_cleanup_and_adhoc_assessment_is_data(rig, tmp_path):
    output = tmp_path / "output"
    assert receipt.main(["--dmg", str(rig.dmg), "--output", str(output), "--expected-sha256", receipt.sha256(rig.dmg)]) == 0
    result = json.loads((output / "receipt.json").read_text())
    assert result["verdict"] == "installed-pass" and result["reasons"] == []
    assert result["artifact"]["spctl"]["exit"] == 3
    assert result["artifact"]["CFBundleVersion"] == "3100"
    assert result["interpreter"]["sha256"] == result["interpreter"]["mounted_sha256"]
    assert [row["event"] for row in result["interpreter"]["health_bindings"]] == ["connected", "relaunch"]
    assert result["cleanup"]["after_uninstall"]["ok"] and result["install"]["detached"]
    assert (rig.scratch / "profile/index.db").read_bytes() == b"disposable data"
    assert not rig.app.exists()


def test_source_checkout_refusal_writes_fail_json_without_apple_commands(tmp_path, monkeypatch):
    monkeypatch.setattr(receipt, "command", lambda *a, **kw: pytest.fail("Must refuse before commands"))
    assert receipt.main(["--dmg", str(ROOT), "--output", str(tmp_path / "out")]) == 1
    result = json.loads((tmp_path / "out/receipt.json").read_text())
    assert result["verdict"] == "fail"
    assert "source checkout" in result["reasons"][0]


def test_hash_mismatch_refusal_before_mount(rig, tmp_path, monkeypatch):
    monkeypatch.setattr(receipt.dmg_smoke, "installed_dmg", lambda *a: pytest.fail("Hash mismatch must not mount"))
    assert receipt.main(["--dmg", str(rig.dmg), "--output", str(tmp_path / "out"), "--expected-sha256", "0" * 64]) == 1
    result = json.loads((tmp_path / "out/receipt.json").read_text())
    assert result["verdict"] == "fail" and "SHA-256 differs" in result["reasons"][0]


def test_missing_expected_hash_refusal_before_mount(rig, tmp_path, monkeypatch):
    monkeypatch.setattr(receipt.dmg_smoke, "installed_dmg", lambda *a: pytest.fail("No hash must not mount"))
    assert receipt.main(["--dmg", str(rig.dmg), "--output", str(tmp_path / "out")]) == 1
    result = json.loads((tmp_path / "out/receipt.json").read_text())
    assert result["verdict"] == "fail" and "No --expected-sha256" in result["reasons"][0]


def test_python_link_outside_bundle_refusal_without_symlink_privileges(rig, tmp_path, monkeypatch):
    original = Path.resolve
    python = rig.app / receipt.PYTHON_EXECUTABLE
    monkeypatch.setattr(Path, "resolve", lambda p, *a, **kw:
                        tmp_path / "system/python3" if p == python else original(p, *a, **kw))
    assert receipt.main(["--dmg", str(rig.dmg), "--output", str(tmp_path / "out"),
                         "--expected-sha256", receipt.sha256(rig.dmg)]) == 1
    result = json.loads((tmp_path / "out/receipt.json").read_text())
    assert result["verdict"] == "fail" and "resolves outside" in result["reasons"][0]


def test_non_bundle_health_interpreter_refusal_writes_fail(rig, tmp_path, monkeypatch):
    # Keep the real binder; a valid installed path alone cannot earn credit.
    monkeypatch.setattr(receipt, "bind_health", rig.real_bind)
    monkeypatch.setattr(receipt, "observe", lambda pid: {"pid": pid, "executable": str(tmp_path / "system/python3")})
    assert receipt.main(["--dmg", str(rig.dmg), "--output", str(tmp_path / "out"),
                         "--expected-sha256", receipt.sha256(rig.dmg)]) == 1
    result = json.loads((tmp_path / "out/receipt.json").read_text())
    assert result["verdict"] == "fail" and "non-bundle interpreter" in result["reasons"][0]


@pytest.mark.parametrize("failure", ["smoke", "detach", "uninstall", "data", "isolation", "survivor", "unknown",
                                     "missing_check", "missing_binding", "changed_dmg", "signature"])
def test_incomplete_or_failed_evidence_never_earns_installed_pass(rig, tmp_path, failure):
    rig.failure = failure
    result = receipt.collect(rig.dmg, tmp_path / "out", receipt.sha256(rig.dmg))
    assert result["verdict"] == "fail" and result["reasons"]
    if failure != "detach":
        assert result["install"]["detached"]
    assert "after" in result["isolation"]


def test_health_binds_listener_and_exact_incarnation(tmp_path, monkeypatch):
    app = make_app(tmp_path / "Uoink.app")
    identity = {"pid": 11, "created_ms": 123.456, "started_us": 123456,
                "executable": str(app / receipt.PYTHON_EXECUTABLE)}
    supervisor = {**identity, "pid": 10}
    monkeypatch.setattr(receipt, "observe", lambda pid: supervisor if pid == 10 else identity)
    monkeypatch.setattr(receipt, "describe", lambda pid: {"ppid": 10})
    monkeypatch.setattr(receipt, "listeners", lambda port: [11])
    monkeypatch.setattr(receipt.urllib.request, "build_opener", lambda *a: SimpleNamespace(
        open=lambda *a, **kw: io.BytesIO(b'{"ok": true, "pid": 11, "supervisor_run_id": "fixture"}')))
    proc = SimpleNamespace(pid=10, poll=lambda: None)
    bound = receipt.bind_health(proc, app, 18081)
    assert bound["identity"] == identity and bound["supervisor_identity"] == supervisor
    assert bound["listener_pid"] == 11
    monkeypatch.setattr(receipt, "listeners", lambda port: [10])
    with pytest.raises(ValueError, match="listener"):
        receipt.bind_health(proc, app, 18081)
    monkeypatch.setattr(receipt, "listeners", lambda port: [11])
    observations = iter([supervisor, identity, {**identity, "started_us": 123457}])
    monkeypatch.setattr(receipt, "observe", lambda pid: next(observations))
    with pytest.raises(ValueError, match="identity changed"):
        receipt.bind_health(proc, app, 18081)


@pytest.mark.parametrize("invalid", ["parent", "helper_executable", "health_pid", "run_id",
                                    "supervisor_reused", "supervisor_exited", "reparented"])
def test_health_rejects_unowned_or_changed_supervision(tmp_path, monkeypatch, invalid):
    app = make_app(tmp_path / "Uoink.app")
    observations = []
    def observe(pid):
        observations.append(pid)
        return {"pid": pid, "created_ms": 1,
                "started_us": 2000 if invalid == "supervisor_reused" and len(observations) == 4 else 1000,
                "executable": str(tmp_path / "foreign") if invalid == "helper_executable" and pid == 11
                else str(app / receipt.PYTHON_EXECUTABLE)}
    parents = iter([99, 99] if invalid == "parent" else [10, 99] if invalid == "reparented" else [10, 10])
    monkeypatch.setattr(receipt, "observe", observe)
    monkeypatch.setattr(receipt, "describe", lambda pid: {"ppid": next(parents)})
    monkeypatch.setattr(receipt, "listeners", lambda port: [11])
    health = {"ok": True, "pid": 99 if invalid == "health_pid" else 11,
              "supervisor_run_id": "" if invalid == "run_id" else "fixture"}
    monkeypatch.setattr(receipt.urllib.request, "build_opener", lambda *a: SimpleNamespace(
        open=lambda *a, **kw: io.BytesIO(json.dumps(health).encode())))
    proc = SimpleNamespace(pid=10, poll=lambda: 0 if invalid == "supervisor_exited" else None)
    with pytest.raises(ValueError):
        receipt.bind_health(proc, app, 18081)


def test_protected_snapshot_never_reads_contents_and_detects_added_file(tmp_path, monkeypatch):
    data = tmp_path / "Library/Application Support/Uoink"
    data.mkdir(parents=True)
    (data / "token.txt").touch()
    monkeypatch.setattr(Path, "open", lambda *a, **kw: pytest.fail("Protected contents must never open"))
    monkeypatch.setattr(receipt, "listeners", lambda port: [8])
    before = receipt.protected_snapshot(tmp_path)
    assert before["port_5179"]["exists"]
    (data / "new").touch()
    after = receipt.protected_snapshot(tmp_path)
    assert before != after
    assert set(before["data"]["token.txt"]) == {"exists", "mtime_ns"}


def test_survivor_settle_is_bounded_and_records_first_look(tmp_path, monkeypatch):
    row = {"pid": 7, "created_ms": 1.0, "started_us": 1000, "executable": "x"}
    looks = iter([[row], [row], []])
    monkeypatch.setattr(receipt, "scoped_processes", lambda app: next(looks))
    monkeypatch.setattr(receipt, "listeners", lambda port: [])
    monkeypatch.setattr(receipt, "describe", lambda pid: {"command": "python3 -m probe"})
    monkeypatch.setattr(receipt.time, "sleep", lambda seconds: None)
    settled = receipt.no_survivors(tmp_path, [], 18081)
    assert settled["ok"] and settled["first_look"][0]["command"] == "python3 -m probe"
    monkeypatch.setattr(receipt, "scoped_processes", lambda app: [row])
    stuck = receipt.no_survivors(tmp_path, [], 18081)
    assert not stuck["ok"] and stuck["settled_after_s"] == 5.0
    assert stuck["survivors"][0]["command"] == "python3 -m probe"


def test_passive_port_observation_uses_no_network(monkeypatch):
    calls = []
    monkeypatch.setattr(receipt, "command", lambda argv: calls.append(argv) or {"exit": 1, "stdout": "", "stderr": ""})
    assert receipt.listeners(5179) == []
    assert calls == [["/usr/sbin/lsof", "-nP", "-a", "-iTCP:5179", "-sTCP:LISTEN", "-Fp"]]


def test_health_refuses_live_port_before_any_observation(tmp_path, monkeypatch):
    monkeypatch.setattr(receipt, "observe", lambda *a: pytest.fail("Do not probe live helper"))
    with pytest.raises(ValueError, match="disposable port"):
        receipt.bind_health(SimpleNamespace(pid=10), tmp_path, 5179)


def test_output_cannot_touch_protected_user_paths(rig, monkeypatch):
    home = rig.scratch / "real home"
    monkeypatch.setattr(receipt, "real_home", lambda: home)
    output = home / "Library/Application Support/Uoink/receipt"
    assert receipt.main(["--dmg", str(rig.dmg), "--output", str(output)]) == 1
    assert not output.exists()


def test_existing_receipt_is_not_overwritten(tmp_path):
    target = tmp_path / "receipt.json"
    target.write_text("old receipt")
    with pytest.raises(FileExistsError):
        receipt.main(["--dmg", str(tmp_path / "x.dmg"), "--output", str(tmp_path)])
    assert target.read_text() == "old receipt"
