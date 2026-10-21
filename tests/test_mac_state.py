"""Immutable application resources and writable Darwin state regressions."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
from types import SimpleNamespace
import urllib.request

import pytest

import _platform
import server
from tests.test_c01_mcp_stdio import _StdioClient, CANONICAL_STDIO_TOOLS, CORE_STDIO_TOOLS
from tests.test_installer_files_complete import staged_sources

ROOT = Path(__file__).resolve().parents[1]


def _copy_staged_app(app):
    # Consume the Windows builder's real source list, including package trees
    # and non-code resources. VERSION is generated separately by that builder.
    for name in sorted(staged_sources() | {"VERSION"}):
        source, target = ROOT / name, app / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, target, dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        else:
            shutil.copyfile(source, target)


def test_readonly_fixture_uses_complete_staged_payload(tmp_path):
    _copy_staged_app(tmp_path)
    from tests.test_installer_files_complete import reachable_modules
    assert all((tmp_path / path).is_file() for path in reachable_modules(ROOT))
    assert (tmp_path / "voice_dna/VOICE-DNA.md").is_file()


@pytest.mark.parametrize("platform", ["win32", "darwin", "linux"])
def test_state_locations_preserve_other_platforms(monkeypatch, tmp_path, platform):
    monkeypatch.setattr(_platform, "sys", SimpleNamespace(platform=platform))
    app, data = tmp_path / "app", tmp_path / "data"
    for name in ("token.txt", "server.log", "server.pid", "topics.json"):
        assert _platform.app_state_path(app, data, name) == (
            data if platform == "darwin" else app) / name
    _platform.prepare_app_state(data)
    assert data.exists() == (platform == "darwin")


def test_topics_first_edit_preserves_defaults_then_reads_override(monkeypatch, tmp_path):
    monkeypatch.setattr(_platform, "sys", SimpleNamespace(platform="darwin"))
    app, data = tmp_path / "app", tmp_path / "data"
    app.mkdir()
    data.mkdir()
    packaged = app / "topics.json"
    defaults = {"topics": [{"name": "Old", "keywords": ["old"]}], "fallback": "Custom fallback"}
    packaged.write_text(json.dumps(defaults), encoding="utf-8")
    before = packaged.read_bytes()
    monkeypatch.setattr(server, "HERE", app)
    monkeypatch.setattr(server, "TOPICS_PATH", data / "topics.json")
    assert server._load_topics() == defaults
    server._write_topics([{"name": " New ", "keywords": [" new "]}])
    assert server._load_topics() == {"topics": [{"name": "New", "keywords": ["new"]}],
                                     "fallback": "Custom fallback"}
    assert packaged.read_bytes() == before
    assert not (data / "topics.json.tmp").exists()


def test_extension_updates_keep_user_prompts(monkeypatch, tmp_path):
    monkeypatch.setattr(_platform, "sys", SimpleNamespace(platform="darwin"))
    app, data = tmp_path / "app", tmp_path / "data"
    packaged = app / "extension"
    packaged.mkdir(parents=True)
    (app / "VERSION").write_text("1.0.0")
    (packaged / "prompts.json").write_text('{"default": true}')
    (packaged / "setup.js").write_text("version1")
    target = _platform.editable_extension_dir(app, data)
    assert target == data / "extension"
    (target / "prompts.json").write_text('{"custom": true}')
    (app / "VERSION").write_text("1.1.0")
    (packaged / "setup.js").write_text("version2")
    assert _platform.editable_extension_dir(app, data) == target
    assert (target / "prompts.json").read_text() == '{"custom": true}'
    assert (target / "setup.js").read_text() == "version2"
    assert (packaged / "prompts.json").read_text() == '{"default": true}'


def test_darwin_bind_does_not_resolve_dns(monkeypatch):
    monkeypatch.setattr(server, "sys", SimpleNamespace(platform="darwin"))
    def forbidden(*args):
        raise AssertionError("binding a loopback service must not wait for DNS")
    monkeypatch.setattr(socket, "getfqdn", forbidden)
    with server._YoinkHTTPServer(("127.0.0.1", 0), server.Handler) as httpd:
        assert httpd.server_name == "localhost"
        assert httpd.server_port > 0


@pytest.mark.parametrize("platform", ["darwin", "win32"])
def test_splash_fallback_keeps_darwin_sentinels_outside_app(monkeypatch, tmp_path, platform):
    import uoink_splash
    monkeypatch.setattr(uoink_splash, "sys", SimpleNamespace(platform=platform))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setitem(sys.modules, "_platform", None)
    expected = (tmp_path / "Library/Application Support/Uoink"
                if platform == "darwin" else uoink_splash.HERE)
    assert uoink_splash._data_root() == expected
    if platform == "win32":
        assert uoink_splash._extension_dir() == uoink_splash.HERE / "extension"


def test_mcp_darwin_resident_requires_complete_exact_identity(monkeypatch, tmp_path):
    import _platform as identity
    app = tmp_path / "app"
    app.mkdir()
    (app / "server.py").write_text("# fixture")
    payload = {"pid": 123, "created_ms": 456, "executable": str(app / "python"),
               "script": str(app / "server.py")}
    (app / "python").write_text("fixture")
    record = tmp_path / "runtime-identity.json"
    monkeypatch.setattr(identity, "darwin_observe", lambda *a, **k:
                        identity.DarwinProcessObservation("alive", 456000, str(app / "python")))
    record.write_text(json.dumps(payload))
    assert _platform.darwin_helper_running(app, tmp_path)
    for invalid in ({**payload, "created_ms": 457}, {**payload, "created_ms": None},
                    {**payload, "executable": ""}, {**payload, "script": "missing"}):
        record.write_text(json.dumps(invalid))
        assert not _platform.darwin_helper_running(app, tmp_path)


_READONLY_LAUNCHER = r'''
import os, pathlib, runpy, sys
from types import SimpleNamespace
app = pathlib.Path(sys.argv[1]).resolve()
mode, port = sys.argv[2], int(sys.argv[3])
sys.path.insert(0, str(app))
def guard(event, args):
    if event == "open" and not isinstance(args[0], int):
        path, access, flags = args
        writing = (isinstance(access, str) and any(c in access for c in "wax+")) or (
            isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC))
        if writing and pathlib.Path(path).resolve().is_relative_to(app):
            raise AssertionError("attempted app-tree write: " + str(path))
    if event in {"os.mkdir", "os.remove", "os.rmdir", "os.rename"}:
        for path in args[:2] if event == "os.rename" else args[:1]:
            if isinstance(path, (str, bytes, os.PathLike)) and pathlib.Path(os.fsdecode(path)).resolve().is_relative_to(app):
                raise AssertionError("attempted app-tree mutation: " + str(path))
    if event == "socket.connect":
        address = args[1]
        if isinstance(address, tuple) and (address[0] not in {"127.0.0.1", "::1"} or address[1] == 5179):
            raise AssertionError("external or production-port connection forbidden")
sys.addaudithook(guard)
# Portable CI intentionally has no ASR stack. Exercise its supported absence,
# even on developer machines where importing it would load torch/model caches.
sys.modules["whisperx"] = None
# Exercise Darwin's resource/state policy on every POSIX host. On Darwin all
# process and filesystem calls remain native; Linux keeps its real /proc API.
if sys.platform != "darwin":
    sys.dont_write_bytecode = True
    import _platform
    _platform.sys = SimpleNamespace(platform="darwin")
sys.argv = [str(app / ("server.py" if mode == "helper" else "uoink_mcp.py"))]
if mode == "helper":
    # Execute the entry file as a script (no import-loader pyc), then select
    # the ephemeral port before main(), just as an explicit launcher would.
    import types
    server = types.ModuleType("server")
    server.__file__ = str(app / "server.py")
    sys.modules["server"] = server
    exec(compile((app / "server.py").read_text(encoding="utf-8"), server.__file__, "exec"), vars(server))
    server._platform.show_toast = lambda *a, **k: None
    server.PORT = port
    server._write_topics([{"name": "Read only app", "keywords": ["test"]}])
    server._platform.editable_extension_dir(server.HERE, server.DATA_ROOT)
    server._server_log_handler.doRollover()
    server.main()
else:
    runpy.run_path(str(app / "uoink_mcp.py"), run_name="__main__")
'''


@pytest.mark.skipif(os.name == "nt", reason="POSIX read-only mode bits do not enforce Windows ACLs; Windows layout is covered separately")
@pytest.mark.parametrize("isolated", [False, True])
def test_helper_and_mcp_start_from_read_only_app(tmp_path, isolated):
    app = tmp_path / "Uoink App"
    app.mkdir()
    _copy_staged_app(app)
    files = [path for path in app.rglob("*") if path.is_file()]
    before = {str(path.relative_to(app)): hashlib.sha256(path.read_bytes()).hexdigest() for path in files}
    directories = [app, *(path for path in app.rglob("*") if path.is_dir())]
    for path in files:
        path.chmod(0o444)
    for path in directories:
        path.chmod(0o555)
    env = dict(os.environ)
    for key in ("UOINK_ISOLATED_PROFILE", "UOINK_ISOLATED_PORT", "UOINK_ISOLATED_APP_DIR", "ANTHROPIC_API_KEY"):
        env.pop(key, None)
    home = tmp_path / "home"
    home.mkdir()
    env.update(HOME=str(home), USERPROFILE=str(home), LOCALAPPDATA=str(tmp_path / "local"),
               APPDATA=str(tmp_path / "roaming"), XDG_DATA_HOME=str(tmp_path / "xdg"),
               UOINK_OUTPUT_DIR=str(tmp_path / "output"),
               PYTHON_KEYRING_BACKEND="keyring.backends.null.Keyring", PYTHONPATH=str(app))
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    assert port != 5179
    data = home / "Library/Application Support/Uoink"
    if isolated:
        data = tmp_path / "profile"
        data.mkdir()
        env.update(UOINK_ISOLATED_PROFILE=str(data), UOINK_ISOLATED_PORT=str(port))
    env.pop("PYTHONDONTWRITEBYTECODE", None)  # Entry points must enforce this themselves on Darwin.
    env.pop("PYTHONPYCACHEPREFIX", None)
    launch = [sys.executable, "-c", _READONLY_LAUNCHER, str(app)]
    log = tmp_path / "helper-output.txt"
    helper = None
    try:
        with log.open("w", encoding="utf-8") as stream:
            helper = subprocess.Popen([*launch, "helper", str(port)], env=env, cwd=tmp_path,
                                      stdout=stream, stderr=subprocess.STDOUT)
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            if helper.poll() is not None:
                pytest.fail(log.read_text(encoding="utf-8"))
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1) as response:
                    assert response.status == 200
                    break
            except OSError:
                time.sleep(0.1)
        else:
            pytest.fail("read-only helper did not start: " + log.read_text(encoding="utf-8"))
        for name in ("token.txt", "server.log", "server.log.1", "server.pid", "topics.json", "index.db"):
            assert (data / name).is_file(), name
        assert (data / "extension/prompts.json").is_file()
        if isolated or sys.platform == "darwin":
            assert (data / "runtime-identity.json").is_file()
        for mode, expected in (("full", CANONICAL_STDIO_TOOLS), ("core", CORE_STDIO_TOOLS)):
            client = _StdioClient([*launch, "mcp", str(port)], str(tmp_path),
                                  {**env, "UOINK_MCP_TOOLSET": mode}, timeout=60)
            try:
                client.send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                    "protocolVersion": "2024-11-05", "capabilities": {},
                    "clientInfo": {"name": "read-only-app", "version": "1"}}})
                assert "result" in client.wait_for(1)
                client.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
                client.send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
                names = [tool["name"] for tool in client.wait_for(2)["result"]["tools"]]
                assert len(names) == len(expected) and set(names) == set(expected)
            finally:
                client.close()
                client.proc.wait(timeout=10)
        after = {str(path.relative_to(app)): hashlib.sha256(path.read_bytes()).hexdigest()
                 for path in app.rglob("*") if path.is_file()}
        assert after == before
        assert (data / "token.txt").stat().st_mode & 0o077 == 0
    finally:
        if helper is not None:
            helper.terminate()
            helper.wait(timeout=10)
        for path in directories:
            path.chmod(0o755)
        for path in files:
            path.chmod(0o644)
