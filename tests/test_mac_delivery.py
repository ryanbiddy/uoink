"""Offline passes 7/9/10 contracts. No Apple commands or real HOME writes."""
from __future__ import annotations

import base64
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import plistlib
import subprocess
import sys
from types import ModuleType, SimpleNamespace
from urllib.parse import parse_qs, unquote, urlsplit
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/mac"))
import build_bundle
import build_mcpb
from helper import mac_lifecycle as life
import uoink_connect as connect
import uoink_cli as cli


@pytest.fixture
def install(tmp_path, monkeypatch):
    app = tmp_path / "Custom Apps & Snow 雪" / "Uoink.app"
    for relative in ("MacOS/Uoink", "Resources/Python/bin/python3", "Resources/server.py", "Resources/uoink_mcp.py"):
        path = app / "Contents" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    (app / "Contents/Info.plist").write_bytes(plistlib.dumps({"CFBundleIdentifier": life.LABEL}))
    home = tmp_path / "test home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setattr(life, "domain", lambda: "gui/501")
    return app, home


class Launchctl:
    def __init__(self, fail=None):
        self.active = False
        self.calls = []
        self.fail = fail
        self.program = ""

    def __call__(self, *args):
        self.calls.append(args)
        if args[0] == self.fail:
            return SimpleNamespace(returncode=5, stderr="simulated failure")
        if args[0] == "print":
            return SimpleNamespace(returncode=0 if self.active else 113, stderr="", stdout=f"program = {self.program}\n")
        self.active = args[0] == "bootstrap"
        if self.active:
            self.program = plistlib.loads(Path(args[2]).read_bytes())["ProgramArguments"][0]
        return SimpleNamespace(returncode=0, stderr="")


def test_login_opt_in_idempotence_disable_and_quit_policy(install, monkeypatch):
    app, home = install
    fake = Launchctl()
    monkeypatch.setattr(life, "launchctl", fake)
    assert life.status(app, home)["enabled"] is False
    assert not life.agent_path(home).exists()
    life.set_enabled(app, True, home)
    payload = plistlib.loads(life.agent_path(home).read_bytes())
    assert payload["ProgramArguments"] == [str(app / "Contents/MacOS/Uoink"), "--helper"]
    assert payload["RunAtLoad"] is True and payload["KeepAlive"] is False
    assert Path(payload["StandardOutPath"]).parent == home / "Library/Logs/Uoink"
    assert life.status(app, home)["enabled"] is True
    life.set_enabled(app, True, home)
    assert [c[0] for c in fake.calls].count("bootstrap") == 1
    life.set_enabled(app, False, home)
    assert ("bootout", "gui/501/" + life.LABEL) in fake.calls
    assert not life.agent_path(home).exists()
    assert life.status(app, home)["enabled"] is False


@pytest.mark.parametrize("failure", ["print", "bootstrap", "bootout"])
def test_launchctl_failures_are_not_reported_as_success(install, monkeypatch, failure):
    app, home = install
    fake = Launchctl()
    monkeypatch.setattr(life, "launchctl", fake)
    if failure == "bootout":
        life.set_enabled(app, True, home)
    fake.fail = failure
    with pytest.raises(OSError, match="launchctl"):
        life.set_enabled(app, failure != "bootout", home)
    assert life.agent_path(home).exists() == (failure == "bootout")


def test_disable_preflight_leaves_plist_until_bootout(install, monkeypatch):
    app, home = install
    fake = Launchctl()
    monkeypatch.setattr(life, "launchctl", fake)
    life.set_enabled(app, True, home)
    assert life.check_disable(app, home)
    assert fake.active and life.agent_path(home).exists()
    def launchctl(*args):
        if args[0] == "bootout":
            assert life.agent_path(home).is_file()
        return fake(*args)
    monkeypatch.setattr(life, "launchctl", launchctl)
    life.set_enabled(app, False, home)
    assert not fake.active and not life.agent_path(home).exists()


@pytest.mark.parametrize("active", [False, True])
@pytest.mark.parametrize("action", ["disable", "uninstall", "bootout", "preflight", "settings"])
def test_foreign_plist_refused_before_any_change(install, monkeypatch, active, action):
    app, home = install
    foreign = home / "Another Uoink.app/Contents/MacOS/Uoink"
    foreign.parent.mkdir(parents=True)
    foreign.touch()
    payload = life.plist(app, home)
    payload["ProgramArguments"][0] = str(foreign)
    path = life.agent_path(home)
    path.parent.mkdir(parents=True)
    before = plistlib.dumps(payload)
    path.write_bytes(before)
    fake = Launchctl()
    fake.active = active
    fake.program = str(app / "Contents/MacOS/Uoink")
    monkeypatch.setattr(life, "launchctl", fake)
    if action == "settings":
        import server
        monkeypatch.setattr(server.sys, "platform", "darwin")
        monkeypatch.setattr(server, "HERE", app / "Contents/Resources")
        monkeypatch.setattr(server, "_read_settings", lambda: pytest.fail("Must refuse before settings access"))
        replies = []
        handler = server.Handler.__new__(server.Handler)
        handler._send_json = lambda code, payload: replies.append((code, payload))
        handler._handle_settings_post({"autostart": False})
        assert replies[0][0] == 200 and replies[0][1]["ok"] is False
        assert "another install" in replies[0][1]["error"]
        assert not handler._mac_bootout_pending
    else:
        with pytest.raises(ValueError, match="another install"):
            if action == "disable":
                life.set_enabled(app, False, home)
            else:
                {"uninstall": life.uninstall, "bootout": life.bootout,
                 "preflight": life.check_disable}[action](app, home)
    assert path.read_bytes() == before and app.is_dir()
    assert fake.active is active and not fake.calls


def test_agent_program_symlink_must_resolve_inside_verified_app(install, monkeypatch):
    app, home = install
    path = life.agent_path(home)
    path.parent.mkdir(parents=True)
    payload = life.plist(app, home)
    program = Path(payload["ProgramArguments"][0])
    path.write_bytes(plistlib.dumps(payload))
    original_resolve = Path.resolve
    # Model an escaping executable link without requiring Windows symlink rights.
    monkeypatch.setattr(Path, "resolve", lambda p, **kw:
                        home / "foreign" if p == program else original_resolve(p, **kw))
    fake = Launchctl()
    monkeypatch.setattr(life, "launchctl", fake)
    with pytest.raises(ValueError):
        life.set_enabled(app, False, home)
    assert path.exists() and app.exists() and not fake.calls


def test_legacy_python_agent_can_be_disabled(install, monkeypatch):
    app, home = install
    path = life.agent_path(home)
    path.parent.mkdir(parents=True)
    payload = life.plist(app, home)
    payload["ProgramArguments"] = [str(app / "Contents/Resources/Python/bin/python3"), "-B", "-s",
                                   str(app / "Contents/Resources/server.py")]
    path.write_bytes(plistlib.dumps(payload))
    fake = Launchctl()
    fake.active = True
    fake.program = payload["ProgramArguments"][0]
    monkeypatch.setattr(life, "launchctl", fake)
    life.set_enabled(app, False, home)
    assert not fake.active and not path.exists()


def test_loaded_service_without_owned_plist_is_not_booted_out(install, monkeypatch):
    app, home = install
    fake = Launchctl()
    fake.active = True
    fake.program = str(app / "Contents/MacOS/Uoink")
    monkeypatch.setattr(life, "launchctl", fake)
    with pytest.raises(ValueError, match="no owned plist"):
        life.set_enabled(app, False, home)
    assert fake.active and all(call[0] == "print" for call in fake.calls)


@pytest.mark.parametrize("payload", [b"not a plist", [], {}, {"ProgramArguments": []},
                                   {"Label": life.LABEL, "ProgramArguments": ["relative/python3"]}])
def test_malformed_agent_refuses_removal(install, monkeypatch, payload):
    app, home = install
    path = life.agent_path(home)
    path.parent.mkdir(parents=True)
    before = payload if isinstance(payload, bytes) else plistlib.dumps(payload)
    path.write_bytes(before)
    fake = Launchctl()
    monkeypatch.setattr(life, "launchctl", fake)
    with pytest.raises(ValueError, match="ownership"):
        life.set_enabled(app, False, home)
    assert path.read_bytes() == before and not fake.calls


def test_uninstall_plan_and_removal_preserve_user_data(install, monkeypatch):
    app, home = install
    fake = Launchctl()
    monkeypatch.setattr(life, "launchctl", fake)
    marker = home / "Library/Application Support/Uoink/settings.json"
    marker.parent.mkdir(parents=True)
    marker.write_text('{"keep": true}')
    capture = home / "capture.txt"
    capture.write_text("keep")
    plan = life.uninstall_plan(app, home)
    assert app.exists() and not fake.calls
    assert {"captures", "settings", "Keychain"} <= set(plan["preserve"])
    life.uninstall(app, home)
    assert not app.exists() and marker.exists() and capture.read_text() == "keep"


@pytest.mark.parametrize("state, terminate, success", [("alive", True, True), ("dead", False, True), ("unknown", True, False), ("alive", False, False)])
def test_uninstall_uses_shared_identity_and_fails_closed(install, monkeypatch, state, terminate, success):
    import _platform
    import uoink_install_isolation
    app, home = install
    path = home / "Library/Application Support/Uoink/runtime-identity.json"
    path.parent.mkdir(parents=True)
    identity = {"pid": 43210, "created_ms": 123456789, "script": str(app / "Contents/Resources/server.py"),
                "executable": str(app / "Contents/Resources/Python/bin/python3")}
    path.write_text(json.dumps(identity))
    calls = []
    monkeypatch.setattr(_platform, "darwin_liveness", lambda *a: state)
    monkeypatch.setattr(uoink_install_isolation, "_terminate_owned", lambda i: calls.append(i) or terminate)
    monkeypatch.setattr(life, "launchctl", Launchctl())
    if success:
        life.uninstall(app, home)
        assert not app.exists()
    else:
        with pytest.raises(ValueError, match="verified"):
            life.uninstall(app, home)
        assert app.exists()
    assert len(calls) == int(state == "alive")


def test_uninstall_rejects_other_install_and_wrong_bundle(install, monkeypatch):
    app, home = install
    path = home / "Library/Application Support/Uoink/runtime-identity.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"pid": 1, "created_ms": 2, "script": "/foreign/server.py", "executable": "/foreign/python3"}))
    with pytest.raises(ValueError, match="another install"):
        life.stop_verified(app, home)
    assert app.exists()
    (app / "Contents/Info.plist").write_bytes(plistlib.dumps({"CFBundleIdentifier": "foreign"}))
    with pytest.raises(ValueError, match="not Uoink"):
        life.uninstall_plan(app, home)


def test_connect_darwin_paths_and_deeplinks(install, monkeypatch):
    app, home = install
    resources = app / "Contents/Resources"
    monkeypatch.setattr(connect.sys, "platform", "darwin")
    python = connect.python_command(resources)
    entry = connect.server_entry("claude-desktop", resources, python)
    assert entry["command"] == str(app / "Contents/Resources/Python/bin/python3")
    assert entry["args"] == ["-B", "-s", str(resources / "uoink_mcp.py")]
    for client in ("cursor", "vscode"):
        link = connect.deeplink(client, resources, python)
        actual = (json.loads(base64.b64decode(parse_qs(urlsplit(link).query)["config"][0])) if client == "cursor"
                  else json.loads(unquote(link.split("?", 1)[1])))
        assert actual["command"] == entry["command"] and actual["args"] == entry["args"]
    assert connect.client_spec("claude-desktop").location == str(home / "Library/Application Support/Claude/claude_desktop_config.json")
    assert connect.client_spec("cursor").location == str(home / ".cursor/mcp.json")
    assert connect.client_spec("codex").location == str(home / ".codex/config.toml")
    python.unlink()
    with pytest.raises(FileNotFoundError, match="Reinstall"):
        connect.python_command(resources)


def load_release_module(name):
    fixtures = ROOT / "tests/fixtures/connect_v3100"
    source = (fixtures / (name + ".py.txt")).read_bytes()
    baseline = json.loads((fixtures / "baseline.json").read_text())
    assert hashlib.sha256(source).hexdigest() == baseline["files"][name]["sha256"]
    module = ModuleType("release_" + name)
    module.__file__ = str(ROOT / (name + ".py"))
    sys.modules[module.__name__] = module
    exec(compile(source, module.__file__, "exec"), module.__dict__)
    return module


@pytest.mark.parametrize("platform", ["win32", "linux"])
def test_unchanged_connect_stdout_is_byte_identical_to_v3100(tmp_path, monkeypatch, platform):
    old_connect = load_release_module("uoink_connect")
    old_cli = load_release_module("uoink_cli")
    monkeypatch.setattr(sys, "platform", platform)
    home = tmp_path / "temporary home"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    # Exercise the POSIX quoting branch even on the Windows test host.
    if platform == "linux":
        for module in (old_connect, connect):
            monkeypatch.setattr(module, "os", SimpleNamespace(name="posix"))
    app = tmp_path / "App's & 雪"
    python = app / "python" / ("python.exe" if platform == "win32" else "bin/python3")
    python.parent.mkdir(parents=True)
    python.touch()
    for module in (old_cli, cli):
        monkeypatch.setattr(module, "APP_DIR", app)
    monkeypatch.setattr(cli.isolation, "apply_from_process", lambda _: None)
    monkeypatch.setattr(cli.isolation, "child_argv", lambda: [])
    changes = json.loads((ROOT / "tests/fixtures/connect_20261021/changes.json").read_text())
    assert set(connect.CLIENTS) - set(old_connect.CLIENTS) == set(changes["added"])
    assert set(old_connect.CLIENTS) <= set(connect.CLIENTS)
    commands = [["connect", c] for c in old_connect.CLIENTS]
    commands += [["connect", c, "--deeplink"] for c in ("cursor", "vscode")]
    changed_locations = set()
    for args in commands:
        outputs = []
        for module, recipes in ((old_cli, old_connect), (cli, connect)):
            monkeypatch.setitem(sys.modules, "uoink_connect", recipes)
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = module.main(args)
            outputs.append((code, out.getvalue().encode("utf-8"), err.getvalue().encode("utf-8")))
        name = args[1]
        if platform not in connect.CLIENTS[name].platforms:
            assert name in changes["restricted_platforms"]
            assert platform not in changes["restricted_platforms"][name]
            assert outputs[1][0] == 2 and outputs[1][1] == b""
        else:
            assert outputs[0][0] == outputs[1][0] == 0
            if name in changes["stdout_changed"] and "--deeplink" not in args:
                # Deliberate recipe changes have reviewed replacement snapshots.
                assert outputs[0][1] != outputs[1][1], args
            else:
                assert outputs[0][1] == outputs[1][1], args
            assert b"Official docs verified:" in outputs[1][2]
            assert b"Checked: 2026-10-21" in outputs[1][2]
            if platform == "linux":
                old_location, new_location = (output[2].splitlines()[0] for output in outputs)
                if old_location != new_location:
                    # Location changes are on stderr, never a stdout exemption.
                    changed_locations.add(name)
                    location = changes["linux_locations_changed"][name]
                    if location.startswith("~/"):
                        location = str(home / location[2:])
                    assert new_location == f"File: {location}".encode("utf-8"), args
    if platform == "linux":
        assert changed_locations == set(changes["linux_locations_changed"])


def test_darwin_mcpb_payload_and_validation(tmp_path):
    path = build_mcpb.build(tmp_path)
    manifest = build_mcpb.check(path)
    assert "Contents/Resources/Python/bin/python3" in manifest["long_description"]
    assert path.name == f"uoink-{(ROOT / 'VERSION').read_text().strip()}-macos.mcpb"
    assert manifest["compatibility"]["platforms"] == ["darwin"]
    assert manifest["user_config"]["uoink_dir"]["default"] == "/Applications/Uoink.app"
    from mcpb_manifest import validate
    validate(json.loads((ROOT / ".mcpb/manifest.json").read_text()))
    manifest["server"]["entry_point"] = "wrong.py"
    with pytest.raises(ValueError, match="entry_point"):
        validate(manifest, "darwin")
    with zipfile.ZipFile(path) as archive:
        assert not archive.read("manifest.json").startswith(b"\xef\xbb\xbf")
        launcher = archive.read("launch-macos.sh").decode()
        assert 'python="$app/Contents/Resources/Python/bin/python3"' in launcher
        assert 'exec "$python" -B -s "$script"' in launcher
        assert "Uoink is not installed" in launcher


def test_signing_order_and_assessment(tmp_path, monkeypatch):
    app = tmp_path / "Uoink.app"
    binary = app / "Contents/Frameworks/Inner.app/Contents/MacOS/inner"
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"\xcf\xfa\xed\xfe")
    nested = binary.parents[2]
    (nested / "Contents/Info.plist").write_bytes(plistlib.dumps({"CFBundleExecutable": "inner"}))
    main = app / "Contents/MacOS/Uoink"
    natives = [main, app / "Contents/Resources/Python/bin/python3",
               app / "Contents/Resources/Python/lib/python3.13/lib-dynload/_ssl.so",
               app / "Contents/Resources/Python/lib/libpython3.13.dylib",
               app / "Contents/Helpers/ffmpeg", app / "Contents/Helpers/ffprobe",
               app / "Contents/Frameworks/Codec.framework/Versions/A/Codec"]
    for path in natives:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"\xcf\xfa\xed\xfe")
    (app / "Contents/Info.plist").write_bytes(plistlib.dumps({"CFBundleExecutable": "Uoink"}))
    (app / "Contents/Resources/Python/lib/os.py").write_text("# resource, not native code")
    shim = app / "Contents/Helpers/uoink"
    shim.write_text("#!/bin/sh\nexec true\n")
    framework = app / "Contents/Frameworks/Codec.framework"
    (framework / "Resources").mkdir()
    (framework / "Resources/Info.plist").write_bytes(plistlib.dumps({"CFBundleExecutable": "Codec"}))
    calls = []
    monkeypatch.setattr(build_bundle, "run", lambda args, **kw: calls.append(args))
    monkeypatch.setattr(build_bundle.subprocess, "run", lambda *a, **kw: SimpleNamespace(returncode=3, stdout="", stderr="rejected"))
    report = tmp_path / "signing.json"
    build_bundle.sign_app(app, report)
    signed = [c[-1] for c in calls if "--sign" in c]
    assert signed == build_bundle.signing_order(app)
    assert set(signed) == {binary, nested, framework, app, shim, *natives}
    # Scripts in code locations are signed before the bundle that contains them.
    assert signed.index(shim) < signed.index(app)
    assert signed.index(binary) < signed.index(nested) < signed.index(app)
    assert signed.index(natives[-1]) < signed.index(framework) < signed.index(app)
    assert signed[-1] == app and signed.index(main) < signed.index(app)
    assert all(c[:5] == ["codesign", "--force", "--sign", "-", "--timestamp=none"]
               and "--deep" not in c for c in calls if "--sign" in c)
    assert [c for c in calls if "--verify" in c] == [["codesign", "--verify", "--strict", "--deep", app]]
    assert json.loads(report.read_text())["spctl"]["returncode"] == 3


@pytest.mark.parametrize("verify", [False, True])
def test_codesign_failure_prints_captured_stderr(monkeypatch, capsys, verify):
    def fail(command, **kwargs):
        assert kwargs["capture_output"] and kwargs["check"]
        raise subprocess.CalledProcessError(1, command, stderr="fixture signing failure detail")
    monkeypatch.setattr(build_bundle.subprocess, "run", fail)
    command = ["codesign", *( ["--verify", "--strict", "--deep"] if verify else
                             ["--force", "--sign", "-", "--timestamp=none"]), "Uoink.app"]
    with pytest.raises(subprocess.CalledProcessError):
        build_bundle.run(command)
    stderr = capsys.readouterr().err
    assert "codesign failed (1): Uoink.app" in stderr
    assert "fixture signing failure detail" in stderr


@pytest.mark.parametrize("executable", [None, "wrong", "../MacOS/Uoink"])
def test_signing_rejects_wrong_main_executable(tmp_path, executable):
    contents = tmp_path / "Uoink.app/Contents"
    contents.mkdir(parents=True)
    (contents / "Info.plist").write_bytes(plistlib.dumps(
        {} if executable is None else {"CFBundleExecutable": executable}))
    with pytest.raises(ValueError, match="CFBundleExecutable"):
        build_bundle.signing_order(contents.parent)


def test_dmg_format_volume_link_and_digest(tmp_path, monkeypatch):
    app = tmp_path / "Uoink.app"
    app.mkdir()
    calls = []
    links = {}
    monkeypatch.setattr(Path, "symlink_to", lambda p, target, **kw: links.update({p: target}))
    def run(args, **kwargs):
        calls.append(args)
        if args[0] == "ditto":
            args[2].mkdir()
        else:
            stage = args[args.index("-srcfolder") + 1]
            assert links[stage / "Applications"] == "/Applications"
            args[-1].write_bytes(b"fake UDZO")
    monkeypatch.setattr(build_bundle, "run", run)
    dmg = build_bundle.create_dmg(app, tmp_path, "3.10.0")
    args = calls[-1]
    assert args[:6] == ["hdiutil", "create", "-format", "UDZO", "-volname", "Uoink 3.10.0"]
    receipt = json.loads((tmp_path / "dmg.json").read_text())
    assert receipt["sha256"] == build_bundle.sha256(dmg) and receipt["size_bytes"] == len(b"fake UDZO")


@pytest.mark.parametrize("foreign", ["program", "pid", "unknown"])
def test_bootout_never_stops_an_unverified_service(install, monkeypatch, foreign):
    import _platform
    app, home = install
    agent = life.agent_path(home)
    agent.parent.mkdir(parents=True)
    agent.write_bytes(plistlib.dumps(life.plist(app, home)))
    text = f"program = {app / 'Contents/MacOS/Uoink'}\npid = 123\n"
    if foreign == "program":
        text = "program = /foreign/python3\npid = 123\n"
    identity = home / "Library/Application Support/Uoink/runtime-identity.json"
    identity.parent.mkdir(parents=True)
    identity.write_text(json.dumps({"pid": 124 if foreign == "pid" else 123, "created_ms": 12345,
        "script": str(app / "Contents/Resources/server.py"),
        "executable": str(app / "Contents/Resources/Python/bin/python3")}))
    calls = []
    def fake(*args):
        calls.append(args)
        return SimpleNamespace(returncode=0, stderr="", stdout=text)
    monkeypatch.setattr(life, "launchctl", fake)
    monkeypatch.setattr(_platform, "darwin_liveness", lambda *a: "unknown" if foreign == "unknown" else "alive")
    with pytest.raises(ValueError, match="refusing bootout"):
        life.bootout(app, home)
    assert all(c[0] == "print" for c in calls)


def test_dashboard_and_stdio_use_the_same_darwin_entry(install, monkeypatch):
    import server
    app, home = install
    resources = app / "Contents/Resources"
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(server, "HERE", resources)
    monkeypatch.setattr(server._install_isolation, "child_argv", lambda: [])
    entry = connect.server_entry("claude-desktop", resources, connect.python_command(resources))
    assert server._mcp_stdio_command() == (entry["command"], entry["args"])
    assert server._mcp_settings_snippet()["claude_desktop"]["mcpServers"]["uoink"] == entry
    for client in ("cursor", "vscode"):
        assert server._mcp_config_payload()["install_links"][client] == connect.deeplink(client, resources, connect.python_command(resources))
    specs = {s["name"]: s for s in server._agent_client_specs()}
    assert specs["claude-desktop"]["config_path"] == home / "Library/Application Support/Claude/claude_desktop_config.json"
    assert specs["cline"]["config_path"].is_relative_to(home / "Library/Application Support/Code/User")


def test_cli_status_includes_darwin_capabilities(install, monkeypatch, capsys):
    import uoink_agent_runtime
    app, home = install
    capabilities = {"media": {"available": True}, "library_mirror": {"available": False}}
    backend = SimpleNamespace(VERSION="3.10.0", DATA_ROOT=home,
                              _platform=SimpleNamespace(platform_capabilities=lambda: capabilities))
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(cli.isolation, "apply_from_process", lambda _: None)
    monkeypatch.setattr(cli, "backend", lambda: backend)
    monkeypatch.setattr(uoink_agent_runtime, "helper_running", lambda _: True)
    assert cli.main(["status"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["helper_running"] is True and payload["capabilities"] == capabilities


def test_settings_autostart_uses_lifecycle_and_flushes_before_unload(install, monkeypatch):
    import server
    app, home = install
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(server, "HERE", app / "Contents/Resources")
    fake = Launchctl()
    monkeypatch.setattr(life, "launchctl", fake)
    assert server._autostart_enabled() is False
    assert server._set_autostart(True) is True
    assert server._autostart_enabled() is True
    events = []
    handler = server.Handler.__new__(server.Handler)
    def write_settings(_):
        assert fake.active and life.agent_path(home).exists()
        events.append("write")
    def reply(code, payload):
        assert code == 200 and payload == {"ok": True, "settings": {"autostart": False}}
        assert fake.active and life.agent_path(home).exists()
        events.append("reply")
    monkeypatch.setattr(server, "_read_settings", lambda: {})
    monkeypatch.setattr(server, "_write_settings", write_settings)
    monkeypatch.setattr(server, "_public_settings", lambda _: {"autostart": True})
    handler._send_json = reply
    handler.wfile = SimpleNamespace(flush=lambda: events.append("flush"))
    def launchctl(*args):
        if args[0] == "bootout":
            assert life.agent_path(home).is_file()
            events.append("bootout")
        return fake(*args)
    monkeypatch.setattr(life, "launchctl", launchctl)
    def spawn(command, **kwargs):
        assert command == [str(app / "Contents/Resources/Python/bin/python3"), "-B", "-s", "-m",
                           "helper.mac_lifecycle", "disable", str(app)]
        assert kwargs["start_new_session"] is True
        assert kwargs["cwd"] == app / "Contents/Resources"
        assert not any(key.startswith("DYLD_") for key in kwargs["env"])
        assert not {"PYTHONHOME", "PYTHONPATH", "PYTHONSTARTUP", "PYTHONUSERBASE", "PYTHONEXECUTABLE"} & kwargs["env"].keys()
        events.append("spawn")
        life.set_enabled(app, False, home)  # Simulate the detached worker's CLI.
    monkeypatch.setattr(life.subprocess, "Popen", spawn)
    handler._handle_settings_post({"autostart": False})
    assert events == ["write", "reply", "flush", "spawn", "bootout"]
    assert not fake.active and not life.agent_path(home).exists()


@pytest.mark.parametrize("failure", ["validation", "write"])
def test_failed_settings_request_does_not_schedule_disable(install, monkeypatch, failure):
    import server
    app, home = install
    monkeypatch.setattr(server.sys, "platform", "darwin")
    monkeypatch.setattr(server, "HERE", app / "Contents/Resources")
    fake = Launchctl()
    monkeypatch.setattr(life, "launchctl", fake)
    life.set_enabled(app, True, home)
    path = life.agent_path(home)
    before = path.read_bytes()
    monkeypatch.setattr(server, "_read_settings", lambda: {})
    def fail_write(_):
        raise OSError("fixture write failed")
    monkeypatch.setattr(server, "_write_settings", fail_write)
    monkeypatch.setattr(life, "disable_after_reply", lambda *a: pytest.fail("Failed request must not disable"))
    handler = server.Handler.__new__(server.Handler)
    replies = []
    handler._send_json = lambda code, payload: replies.append((code, payload))
    body = {"autostart": False, **({"topics": {}} if failure == "validation" else {})}
    handler._handle_settings_post(body)
    assert replies and replies[0][1]["ok"] is False
    assert not handler._mac_bootout_pending
    assert fake.active and path.read_bytes() == before


@pytest.mark.parametrize("fail", [False, True])
def test_dmg_smoke_detaches_on_success_and_failure(tmp_path, monkeypatch, fail):
    import dmg_smoke
    dmg = tmp_path / "test.dmg"
    dmg.write_bytes(b"fixture")
    output = tmp_path / "evidence"
    calls = []
    def run(args, **kw):
        calls.append(args)
        if args[0] == "ditto":
            args[-1].mkdir(parents=True)
    def smoke(*args):
        if fail:
            raise ValueError("smoke failed")
    monkeypatch.setattr(dmg_smoke, "run", run)
    monkeypatch.setattr(dmg_smoke.subprocess, "run", lambda args, **kw: calls.append(args))
    monkeypatch.setattr(dmg_smoke, "check", lambda _: {"version": "3.10.0"})
    monkeypatch.setattr(dmg_smoke, "smoke", smoke)
    monkeypatch.setattr(Path, "is_symlink", lambda p: p.name == "Applications")
    monkeypatch.setattr(dmg_smoke.os, "readlink", lambda _: "/Applications")
    if fail:
        with pytest.raises(ValueError, match="smoke failed"):
            dmg_smoke.smoke_dmg(dmg, tmp_path / "fake.mcpb", output)
    else:
        dmg_smoke.smoke_dmg(dmg, tmp_path / "fake.mcpb", output)
    assert calls[0][:4] == ["hdiutil", "attach", "-readonly", "-nobrowse"]
    assert calls[-1][:2] == ["hdiutil", "detach"]
    installed = next(c[-1] for c in calls if c[0] == "ditto")
    assert [c for c in calls if c[0] == "codesign"] == [
        ["codesign", "--verify", "--strict", "--deep", installed]] * (1 if fail else 2)
    report = json.loads((output / "dmg-smoke.json").read_text())
    assert report["detached"] is True and report["ok"] is not fail


def test_mcpb_missing_install_error():
    import shutil
    bash = shutil.which("bash")
    if not bash:
        pytest.skip("bash unavailable")
    result = subprocess.run([bash, "installer/mac/mcpb-launch.sh", "/uoink-test-missing-install/Uoink.app"],
                            cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 1 and "Uoink is not installed" in result.stderr
    assert not result.stdout
