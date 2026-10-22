"""Official-doc recipe contracts, with no installed clients or network access."""
import json
from pathlib import Path
import shlex
import re
import socket
import sys
import tomllib

import pytest

import uoink_cli as cli
import uoink_connect as connect

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/connect_20261021"
CHANGES = json.loads((FIXTURES / "changes.json").read_text())


def fake_install(base, platform):
    app = base / "O'Brien & 雪 with spaces" / "Uoink.app"
    resources = app / "Contents/Resources" if platform == "darwin" else app
    python = resources / ("Python/bin/python3" if platform == "darwin" else "python/python.exe")
    python.parent.mkdir(parents=True, exist_ok=True)
    python.touch()
    (resources / "uoink_mcp.py").touch()
    return app, resources, python


def normalize_output(output, app, resources, python, profile):
    """Replace only fixture-dependent paths, including their shell/JSON quoting."""
    replacements = ((python, "<PYTHON>"), (resources / "uoink_mcp.py", "<MCP>"),
                    (app / "Contents/Helpers/uoink", "<CLI>"),
                    (resources / "cli/uoink.cmd", "<CLI>"), (profile, "<PROFILE>"))
    for path, label in replacements:
        value = str(path)
        candidates = {value, json.dumps(value, ensure_ascii=False)[1:-1],
                      shlex.quote(value), "'" + value.replace("'", "''") + "'",
                      value.replace("`", "``").replace("'", "`'")}
        for candidate in sorted(candidates, key=len, reverse=True):
            output = output.replace(candidate, label)
    return output


@pytest.mark.parametrize("platform", ["win32", "darwin"])
@pytest.mark.parametrize("client", connect.CLIENTS)
def test_platform_output_and_print_only_contract(tmp_path, monkeypatch, capsys, platform, client):
    app, resources, python = fake_install(tmp_path, platform)
    profile = tmp_path / "profile with spaces"
    home = tmp_path / "temporary home"
    home.mkdir()
    for key, value in {"HOME": home, "USERPROFILE": home, "APPDATA": home / "Roaming",
                       "LOCALAPPDATA": home / "Local"}.items():
        monkeypatch.setenv(key, str(value))
    # Real-looking configs exist only in the disposable home. Nothing may change.
    canaries = [home / p for p in (".cursor/mcp.json", ".lmstudio/mcp.json", ".qwen/settings.json",
                                  ".factory/mcp.json", ".kiro/settings/mcp.json", ".continue/config.yaml")]
    for path in canaries:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'{"theme":"keep","mcpServers":{"other":{"command":"keep"}}}\n')
    before = {p: p.read_bytes() for p in home.rglob("*") if p.is_file()}
    monkeypatch.setattr(sys, "platform", platform)
    monkeypatch.setattr(cli, "APP_DIR", resources)
    monkeypatch.setattr(cli.isolation, "apply_from_process", lambda _: None)
    monkeypatch.setattr(cli.isolation, "child_argv", lambda: ["--isolated-profile", str(profile), "--isolated-port", "5187"])
    monkeypatch.setattr(cli, "backend", lambda: pytest.fail("connect must not import backend"))
    monkeypatch.setattr(socket.socket, "connect", lambda *a: pytest.fail("connect must be offline"))
    spec = connect.CLIENTS[client]
    code = cli.main(["connect", client])
    out = capsys.readouterr()
    assert {p: p.read_bytes() for p in home.rglob("*") if p.is_file()} == before
    if platform not in spec.platforms:
        assert code == 2 and out.out == "" and "no recipe" in out.err
        return
    assert code == 0, out
    assert spec.checked in out.err and all(url in out.err for url in spec.sources)
    assert "not yet tested" in out.err
    assert "Official docs verified:" not in out.out
    if platform == "darwin":
        assert "%APPDATA%" not in connect.client_spec(client).location
        assert "%USERPROFILE%" not in connect.client_spec(client).location
    if spec.format in {"json", "jsonc", "yaml", "toml"}:
        data = tomllib.loads(out.out) if spec.format == "toml" else json.loads(out.out)
        entry = (data if spec.shape == "entry" else data["mcpServers"][0]
                 if spec.shape == "list" else data[spec.shape]["uoink"])
        expected_args = (["-B", "-s"] if platform == "darwin" else []) + [str(resources / "uoink_mcp.py"),
                         "--isolated-profile", str(profile), "--isolated-port", "5187"]
        if spec.shape == "mcp":
            assert entry["command"] == [str(python), *expected_args]
        else:
            assert entry.get("command", entry.get("cmd")) == str(python)
            assert entry["args"] == expected_args
        if client == "continue":
            assert (data["name"], data["version"], data["schema"]) == ("Uoink", "1.0.0", "v1")
        if client == "copilot-cli":
            assert entry["type"] == "local" and entry["tools"] == ["*"]
        if client == "dive":
            assert entry["enabled"] is True
    if client in {"claude-code", "crush", "perplexity"}:
        expected = [str(python), *(["-B", "-s"] if platform == "darwin" else []),
                    str(resources / "uoink_mcp.py"), "--isolated-profile", str(profile), "--isolated-port", "5187"]
        if client == "claude-code":
            tail = out.out.split(" -- ", 1)[1]
            actual = ([s.replace("''", "'") for s in re.findall(r"'((?:[^']|'')*)'", tail)]
                      if platform == "win32" else shlex.split(tail))
        elif client == "crush":
            tokens = shlex.split(out.out)
            actual = [tokens[4], *tokens[6:tokens.index("--env")]]
        else:
            line = next(line for line in out.out.splitlines() if line.startswith("/usr/bin/env"))
            tokens = shlex.split(line)
            assert tokens[:3] == ["/usr/bin/env", "PYTHONIOENCODING=utf-8", "PYTHONUTF8=1"]
            actual = tokens[3:]
        assert actual == expected
    snapshot_clients = set(CHANGES["added"]) | set(CHANGES["stdout_changed"])
    if client in snapshot_clients:
        snapshots = json.loads((FIXTURES / "recipes.json").read_text(encoding="utf-8"))
        actual = normalize_output(out.out.rstrip("\n"), app, resources, python, profile)
        assert actual == snapshots[platform][client]


@pytest.mark.parametrize("platform", ["win32", "darwin"])
@pytest.mark.parametrize("client", ["claude-desktop", "cursor", "cline"])
def test_file_writers_preserve_unrelated_config(tmp_path, monkeypatch, platform, client):
    import server
    home = tmp_path / "O'Brien & 雪 temporary home"
    for key, value in {"HOME": home, "USERPROFILE": home, "APPDATA": home / "AppData/Roaming",
                       "LOCALAPPDATA": home / "AppData/Local"}.items():
        monkeypatch.setenv(key, str(value))
    monkeypatch.setattr(sys, "platform", platform)
    app, resources, python = fake_install(tmp_path, platform)
    monkeypatch.setattr(server, "HERE", resources)
    monkeypatch.setattr(server, "_mcp_stdio_command", lambda: (str(python), [str(resources / "uoink_mcp.py")]))
    spec = server._agent_client_spec(client)
    cfg = spec["config_path"]
    assert cfg.is_relative_to(home)
    cfg.parent.mkdir(parents=True)
    original = b'{"theme":"dark","mcpServers":{"other":{"command":"untouched","env":{"NOTE":"keep"}}}}\n'
    cfg.write_bytes(original)
    for action in ("added", "updated"):
        before = cfg.read_bytes()
        result = server._connect_ai_client(client)
        assert result["action"] == action
        assert Path(result["backup_path"]).read_bytes() == before
        data = json.loads(cfg.read_text(encoding="utf-8"))
        assert data["theme"] == "dark"
        assert data["mcpServers"]["other"] == json.loads(original)["mcpServers"]["other"]
        assert data["mcpServers"]["uoink"]["command"] == str(python)


@pytest.mark.parametrize("platform", ["win32", "darwin"])
def test_continue_dashboard_refuses_obsolete_write(tmp_path, monkeypatch, platform):
    import server
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setattr(sys, "platform", platform)
    config = tmp_path / ".continue/config.yaml"
    config.parent.mkdir()
    original = "name: Existing agent\nmodels: []\n# Keep my comments\n"
    config.write_text(original)
    legacy = config.with_suffix(".json")
    legacy.write_text('{"models": ["keep"]}')
    with pytest.raises(ValueError, match="uoink connect continue") as exc:
        server._connect_ai_client("continue")
    assert exc.value.http_status == 409
    assert config.read_text() == original
    assert legacy.read_text() == '{"models": ["keep"]}'
    assert sorted(p.name for p in config.parent.iterdir()) == ["config.json", "config.yaml"]


def test_generated_tables_have_all_sources_and_dates():
    for relative in ("docs/connect-your-agent.md", "agent-kit/README.md"):
        document = (ROOT / relative).read_text(encoding="utf-8")
        assert connect.client_table() in document
    assert all(connect.CLIENTS[name].platforms == tuple(platforms)
               for name, platforms in CHANGES["restricted_platforms"].items())


def test_list_has_every_recipe_once(capsys):
    assert cli.main(["connect", "--list"]) == 0
    output = capsys.readouterr()
    assert json.loads(output.out) == {"ok": True, "clients": list(connect.CLIENTS)}
    assert not output.err


def test_obsolete_wrappers_and_mac_mirror_are_not_claimed():
    assert connect.CLIENTS["ollama"].format == "text"
    assert "not an MCP client" in connect.CLIENTS["ollama"].guide
    for name in ("jan", "cherry-studio", "raycast", "chatbox"):
        assert connect.CLIENTS[name].format == "text"
    assert connect.CLIENTS["msty"].shape == "entry"
    assert "gated off" in connect.CLIENTS["obsidian"].guide
    assert "obsidian://open?" in connect.CLIENTS["obsidian"].guide
    assert "/mcp/v1" in connect.CLIENTS["n8n"].guide
