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
    command, args = server._mcp_stdio_command()
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
