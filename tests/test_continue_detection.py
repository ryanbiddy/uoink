"""Read-only dashboard detection using disposable client homes, never live clients."""
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

import server
import uoink_connect as connect


@pytest.fixture(autouse=True)
def client_home(tmp_path, monkeypatch):
    home = tmp_path / "client home"
    home.mkdir()
    for key, value in {"HOME": home, "USERPROFILE": home,
                       "APPDATA": home / "Roaming", "LOCALAPPDATA": home / "Local"}.items():
        monkeypatch.setenv(key, str(value))
    app = tmp_path / "O'Brien & \u96ea Uoink"
    monkeypatch.setattr(server, "HERE", app)
    monkeypatch.setattr(server, "_mcp_stdio_command", lambda: (
        str(app / "python/python.exe"), [str(app / "uoink_mcp.py")]))
    return home


def write_config(home, content, suffix="yaml"):
    path = home / ".continue" / f"config.{suffix}"
    path.parent.mkdir(exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def detected():
    return next(item for item in server._detect_ai_clients() if item["name"] == "continue")


@pytest.mark.parametrize("platform", ["win32", "darwin", "linux"])
@pytest.mark.parametrize("format", ["yaml", "json-form-yaml", "legacy-json"])
def test_manually_merged_entry_is_detected_read_only(client_home, monkeypatch, platform, format):
    if format != "legacy-json":
        pytest.importorskip("yaml", reason="PyYAML ships in the installer lock")
    monkeypatch.setattr(sys, "platform", platform)
    command, args = server._mcp_stdio_command()
    if platform == "darwin":
        args = ["-B", "-s", *args]
        monkeypatch.setattr(server, "_mcp_stdio_command", lambda: (command, args))
    entry = {"name": "My library", "command": command, "args": args,
             "env": {"PYTHONUTF8": "1"}}
    if format == "yaml":
        content = ("name: My agent\nversion: 1.0.0\nschema: v1\nmodels: []\n"
                   "# Hand-merged entry, with quotes and an inline args list.\nmcpServers:\n"
                   f"  - name: My library\n    command: {json.dumps(command)}\n"
                   f"    args: {json.dumps(args)} # keep spaces within each argument\n"
                   "    env:\n      PYTHONUTF8: '1'\n")
    elif format == "json-form-yaml":
        content = json.dumps({"name": "My agent", "models": [], "mcpServers": [entry]})
    else:
        content = json.dumps({"models": [], "experimental": {
            "modelContextProtocolServers": [{"transport": {"type": "stdio", **entry}}]}})
    path = write_config(client_home, content, "json" if format == "legacy-json" else "yaml")
    before = {p: p.read_bytes() for p in client_home.rglob("*") if p.is_file()}
    result = detected()
    assert result["installed"] and result["connected"] and result["config_exists"]
    assert result["config_path"] == str(path)
    assert result["connected_reason"]
    # Exercise the HTTP handlers directly without opening any socket.
    response = SimpleNamespace(_send_json=lambda status, body: (status, body))
    status, body = server.Handler._handle_agents_detect(response)
    assert status == 200 and body["any_installed"]
    assert next(a for a in body["agents"] if a["name"] == "continue")["connected"]
    status, body = server.Handler._handle_agents_connect(response, "/agents/connect/continue")
    assert status == 409 and "uoink connect continue" in body["error"]
    assert {p: p.read_bytes() for p in client_home.rglob("*") if p.is_file()} == before


@pytest.mark.parametrize("suffix,content", [
    ("yaml", "mcpServers: [broken"),
    ("yaml", "mcpServers:\n  - command: 'unterminated\n"),
    ("yaml", "mcpServers: !!python/object/apply:os.system ['echo unsafe']"),
    ("yaml", "[]"), ("yaml", ""),
    ("yaml", "mcpServers: {uoink: {command: wrong}}"),
    ("yaml", "mcpServers: [null, 1]"),
    ("json", "{broken"), ("json", "[]"),
    ("json", '{"experimental": []}'),
    ("json", '{"experimental": {"modelContextProtocolServers": {}}}'),
])
def test_bad_config_returns_false_with_reason(client_home, suffix, content):
    if suffix == "yaml":
        pytest.importorskip("yaml", reason="PyYAML ships in the installer lock")
    path = write_config(client_home, content, suffix)
    before = path.read_bytes()
    result = detected()
    assert not result["connected"] and result["connected_reason"]
    assert path.read_bytes() == before


def test_missing_unreadable_and_invalid_utf8(client_home, monkeypatch):
    result = detected()
    assert not result["config_exists"] and not result["connected"]
    assert "not found" in result["connected_reason"]
    path = write_config(client_home, "")
    path.write_bytes(b"\xff\xfe")
    assert not detected()["connected"]
    original = Path.read_text

    def deny_config(self, *args, **kwargs):
        if self == path:
            raise PermissionError("private config detail")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", deny_config)
    result = detected()
    assert not result["connected"] and "could not be read" in result["connected_reason"]
    assert "private config detail" not in result["connected_reason"]


@pytest.mark.parametrize("yaml_content", ["mcpServers: []", "mcpServers: [broken"])
def test_yaml_takes_precedence_over_stale_json(client_home, yaml_content):
    command, args = server._mcp_stdio_command()
    write_config(client_home, json.dumps({"experimental": {"modelContextProtocolServers": [
        {"transport": {"type": "stdio", "command": command, "args": args}}]}}), "json")
    path = write_config(client_home, yaml_content)
    result = detected()
    assert not result["connected"] and result["config_path"] == str(path)


@pytest.mark.parametrize("change", ["none", "command", "script", "missing-args", "args-string",
                                    "extra-args", "disabled", "enabled", "remote", "empty", "null"])
def test_all_clients_match_the_same_launch(client_home, change):
    pytest.importorskip("yaml", reason="PyYAML ships in the installer lock")
    command, args = server._mcp_stdio_command()
    entry = {"name": "uoink", "command": command, "args": args}
    if change == "command":
        entry["command"] = str(client_home / "other/python.exe")
    elif change == "script":
        entry["args"] = [str(client_home / "other/uoink_mcp.py")]
    elif change == "missing-args":
        del entry["args"]
    elif change == "args-string":
        entry["args"] = args[0]
    elif change == "extra-args":
        entry["args"] = [*args, "--isolated-profile", "different"]
    elif change == "disabled":
        entry["disabled"] = True
    elif change == "enabled":
        entry["enabled"] = False
    elif change == "remote":
        entry["type"] = "sse"
    elif change == "empty":
        entry = {}
    elif change == "null":
        entry = None
    write_config(client_home, json.dumps({"mcpServers": [entry]}))
    expected = change == "none"
    assert detected()["connected"] is expected
    for name in ("claude-desktop", "cursor", "cline"):
        path = server._agent_client_spec(name)["config_path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"mcpServers": {"uoink": entry}}), encoding="utf-8")
        assert server._client_is_connected(path) is expected


def test_printed_continue_recipe_is_detected(client_home):
    pytest.importorskip("yaml", reason="PyYAML ships in the installer lock")
    command, _ = server._mcp_stdio_command()
    content = connect.render("continue", server.HERE, Path(command))
    write_config(client_home, content)
    assert detected()["connected"]


def test_windows_path_spelling_and_renamed_entry(client_home, monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    # Use real Windows paths: on a POSIX host the install paths have no drive, and
    # Python 3.13's ntpath.isabs treats "/Users/..." as relative.
    command = r"C:\Users\Me\AppData\Local\Uoink\python\python.exe"
    args = [r"C:\Users\Me\AppData\Local\Uoink\uoink_mcp.py"]
    monkeypatch.setattr(server, "_mcp_stdio_command", lambda: (command, args))
    entry = {"command": command.upper().replace("\\", "/"),
             "args": [a.upper().replace("\\", "/") for a in args]}
    path = client_home / "renamed.json"
    path.write_text(json.dumps({"mcpServers": {"my-library": entry}}), encoding="utf-8")
    assert server._client_is_connected(path)


def test_missing_yaml_parser_returns_reason(client_home, monkeypatch):
    write_config(client_home, "mcpServers: []")
    monkeypatch.setitem(sys.modules, "yaml", None)
    result = detected()
    assert not result["connected"] and "PyYAML" in result["connected_reason"]


def test_legacy_json_does_not_need_yaml_parser(client_home, monkeypatch):
    command, args = server._mcp_stdio_command()
    write_config(client_home, json.dumps({"experimental": {"modelContextProtocolServers": [
        {"transport": {"type": "stdio", "command": command, "args": args}}]}}), "json")
    monkeypatch.setitem(sys.modules, "yaml", None)
    assert detected()["connected"]


def test_detection_survives_a_bundle_without_its_launcher(tmp_path, monkeypatch):
    import server

    def missing_launcher():
        raise FileNotFoundError("bundled Python is missing")

    monkeypatch.setattr(server, "_mcp_stdio_command", missing_launcher)
    config = tmp_path / "mcp.json"
    config.write_text(json.dumps({"mcpServers": {"uoink": {"command": "python3", "args": ["uoink_mcp.py"]}}}),
                      encoding="utf-8")
    assert server._entry_launches_uoink({"command": "python3", "args": ["uoink_mcp.py"]}) is False
    assert server._client_is_connected(config) is False
    # `uoink mcp` needs no bundled-Python path to match.
    assert server._entry_launches_uoink({"command": "uoink", "args": ["mcp"]}) is True


@pytest.mark.parametrize("platform, command, args, expected", [
    ("win32", "uoink", ["mcp"], True),
    ("win32", "UOINK.cmd", ["mcp"], True),
    ("win32", "cmd", ["/c", "uoink", "mcp"], True),
    ("win32", r"C:\Windows\System32\cmd.exe", ["/C", "uoink", "mcp"], True),
    ("darwin", "uoink", ["mcp"], True),
    ("linux", "uoink", ["mcp"], True),
    ("win32", "uoink", ["mcp", "--toolset", "core"], False),
    ("win32", "uoink", ["status"], False),
    ("win32", "uoink", [], False),
    ("win32", "uoink-helper", ["mcp"], False),
    ("win32", "cmd", ["/c", "uoink"], False),
    ("win32", "cmd", ["/c", "other", "mcp"], False),
    ("win32", "cmd", ["/k", "uoink", "mcp"], False),
    ("darwin", "cmd", ["/c", "uoink", "mcp"], False),
    ("darwin", "uoink.cmd", ["mcp"], False),
    ("win32", r"C:\Other\Uoink\cli\uoink.cmd", ["mcp"], False),
])
def test_uoink_mcp_entries_are_detected(client_home, monkeypatch, platform, command, args, expected):
    monkeypatch.setattr(sys, "platform", platform)
    path = client_home / "mcp.json"
    path.write_text(json.dumps({"mcpServers": {"library": {"command": command, "args": args}}}),
                    encoding="utf-8")
    assert server._client_is_connected(path) is expected
    disabled = {"command": command, "args": args, "disabled": True}
    assert server._entry_launches_uoink(disabled) is False


def test_uoink_mcp_entry_carries_isolation_arguments(client_home, monkeypatch):
    # The isolated install's own profile, never the PATH install's default.
    flags = ["--isolated-profile", str(client_home / "profile"), "--isolated-port", "18094"]
    monkeypatch.setattr(server._install_isolation, "child_argv", lambda: flags)
    assert server._entry_launches_uoink({"command": "uoink", "args": ["mcp"]}) is False
    assert server._entry_launches_uoink({"command": "uoink", "args": ["mcp", *flags]}) is True


def test_uoink_mcp_absolute_launchers_of_this_install(client_home, tmp_path):
    name = "uoink.cmd" if sys.platform == "win32" else "uoink"
    for launcher, expected in ((server.HERE / "cli" / name, True), (server.HERE / name, True),
                               (tmp_path / "other" / "cli" / name, False)):
        entry = {"command": str(launcher), "args": ["mcp"]}
        assert server._entry_launches_uoink(entry) is expected, launcher
        assert server._entry_launches_uoink({"command": "cmd", "args": ["/c", str(launcher), "mcp"]}) is (
            expected and sys.platform == "win32")
    if sys.platform == "win32":
        spelled = str(server.HERE / "CLI" / "UOINK.CMD").replace("\\", "/")
        assert server._entry_launches_uoink({"command": spelled, "args": ["mcp"]})


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX symlinks and the Mac bundle layout")
def test_uoink_mcp_mac_shim_through_a_path_symlink(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    resources = tmp_path / "Uoink.app/Contents/Resources"
    monkeypatch.setattr(server, "HERE", resources)
    shim = resources.parent / "Helpers/uoink"
    shim.parent.mkdir(parents=True)
    shim.write_text("#!/bin/bash\n", encoding="utf-8")
    link = tmp_path / "bin/uoink"
    link.parent.mkdir()
    link.symlink_to(shim)
    for command, expected in ((shim, True), (link, True), (resources / "uoink", False),
                              (resources / "cli/uoink", False)):
        assert server._entry_launches_uoink({"command": str(command), "args": ["mcp"]}) is expected, command
