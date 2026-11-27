"""Exercise the CLI and dashboard against disposable client settings."""
import io
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

import pytest

import server
import uoink_cli as cli
import uoink_connect as recipes


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    root = tmp_path / "client home"
    root.mkdir()
    for key, path in {"HOME": root, "USERPROFILE": root, "APPDATA": root / "Roaming",
                      "LOCALAPPDATA": root / "Local", "XDG_CONFIG_HOME": root / ".config",
                      "COPILOT_HOME": root / ".copilot"}.items():
        monkeypatch.setenv(key, str(path))
    monkeypatch.chdir(root)
    return root


def connect(client, *flags):
    return cli.main(["connect", client, *flags])


def test_preview_and_noninteractive_refusal(home, capsys, monkeypatch):
    cfg = home / ".cursor/mcp.json"
    assert connect("cursor") == 0
    preview = capsys.readouterr()
    assert preview.err.rstrip().endswith("Run with --write to add it for you.")
    entry = json.loads(preview.out)["mcpServers"]["uoink"]
    monkeypatch.setattr(sys, "stdin", io.StringIO("y\n"))
    assert connect("cursor", "--write") != 0
    assert "--yes" in capsys.readouterr().err
    assert not cfg.parent.exists()
    assert connect("cursor", "--write", "--yes") == 0
    result = capsys.readouterr()
    assert str(cfg) in result.out + result.err
    assert json.loads(cfg.read_bytes())["mcpServers"]["uoink"] == entry
    assert not cfg.with_suffix(".json.bak").exists()


def test_cli_entry_point_in_a_pipe(home):
    args = [sys.executable, cli.__file__, "connect", "cursor", "--write"]
    refused = subprocess.run(args, input="y\n", text=True, capture_output=True, timeout=30)
    assert refused.returncode == 1 and "--yes" in refused.stderr
    assert not (home / ".cursor").exists()
    saved = subprocess.run([*args, "--yes"], input="", text=True, capture_output=True, timeout=30)
    assert saved.returncode == 0, saved.stderr
    assert saved.stdout.rstrip().endswith("Restart Cursor, then ask it: what's in my Uoink library?")
    assert json.loads((home / ".cursor/mcp.json").read_bytes())["mcpServers"]["uoink"]["env"]["UOINK_MCP_TOOLSET"] == "core"


@pytest.mark.parametrize("client,relative,section", [
    ("gemini", ".gemini/settings.json", "mcpServers"),
    ("vscode", ".vscode/mcp.json", "servers"),
    ("opencode", ".config/opencode/opencode.json", "mcp"),
    ("amp", ".config/amp/settings.json", "amp.mcpServers"),
])
def test_merge_matches_recipe(home, capsys, client, relative, section):
    cfg = home / relative
    cfg.parent.mkdir(parents=True)
    before = json.dumps({"theme": "dark", section: {"other": {"keep": True}}}).encode()
    cfg.write_bytes(before)
    assert connect(client, "--toolset", "search") == 0
    entry = json.loads(capsys.readouterr().out)[section]["uoink"]
    assert connect(client, "--toolset", "search", "--write", "--yes") == 0
    assert json.loads(cfg.read_bytes()) == {"theme": "dark", section: {
        "other": {"keep": True}, "uoink": entry}}
    assert cfg.with_suffix(".json.bak").read_bytes() == before


@pytest.mark.parametrize("bad", [b"{bad", b"", b"[]", b'{"mcpServers": []}', b"\xff",
                                 b'{"mcpServers":{"uoink":NaN}}', b'{"dup":1,"dup":2}'])
def test_malformed_config_untouched(home, bad, capsys):
    cfg = home / ".cursor/mcp.json"
    cfg.parent.mkdir()
    cfg.write_bytes(bad)
    assert connect("cursor", "--write", "--yes") == 1
    assert "JSON" in capsys.readouterr().err
    assert cfg.read_bytes() == bad
    assert list(cfg.parent.iterdir()) == [cfg]


def desktop_paths(home):
    name = "claude_desktop_config.json"
    return (home / "Roaming/Claude" / name,
            home / "Local/Packages/Claude_test/LocalCache/Roaming/Claude" / name)


@pytest.mark.parametrize("surface", ["cli", "dashboard"])
@pytest.mark.parametrize("existing", ["package", "both", "roaming", "package-folder"])
def test_msix_path_selection(home, monkeypatch, capsys, surface, existing):
    monkeypatch.setattr(sys, "platform", "win32")
    roaming, package = desktop_paths(home)
    package.parent.mkdir(parents=True)
    if existing in ("roaming", "both"):
        roaming.parent.mkdir(parents=True)
        roaming.write_bytes(b'{"which":"roaming"}')
    if existing in ("package", "both"):
        package.write_bytes(b'{"which":"package"}')
    expected = [p for p in (roaming, package) if p.exists()] or [package]
    before = {p: p.read_bytes() for p in expected if p.exists()}
    if surface == "cli":
        assert connect("claude-desktop") == 0
        preview = capsys.readouterr()
        if package in expected:
            assert str(package) in preview.err
        assert [p for p in expected if p.exists()] == list(before)
        assert connect("claude-desktop", "--write", "--yes") == 0
        output = capsys.readouterr()
        for path in expected:
            assert str(path) in output.out + output.err
    else:
        detected = next(s for s in server._detect_ai_clients() if s["name"] == "claude-desktop")
        assert detected["installed"] and detected["config_path"] == str(expected[0])
        result = server._connect_ai_client("claude-desktop")
        assert result["config_paths"] == list(map(str, expected))
    assert [p for p in (roaming, package) if p.exists()] == expected
    for path in expected:
        assert "uoink" in json.loads(path.read_bytes())["mcpServers"]
        if path in before:
            assert path.with_suffix(".json.bak").read_bytes() == before[path]


def test_two_configs_validated_before_either_write(home, monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    roaming, package = desktop_paths(home)
    for path, data in [(roaming, b"{}"), (package, b"broken")]:
        path.parent.mkdir(parents=True)
        path.write_bytes(data)
    assert connect("claude-desktop", "--write", "--yes") == 1
    assert roaming.read_bytes() == b"{}"
    assert package.read_bytes() == b"broken"
    assert not list(home.rglob("*.bak"))


class Terminal(io.StringIO):
    def isatty(self):
        return True


@pytest.mark.parametrize("answer,accepted", [("\n", False), ("no\n", False), ("y\n", True)])
def test_interactive_confirmation(home, monkeypatch, capsys, answer, accepted):
    monkeypatch.setattr(sys, "stdin", Terminal(answer))
    assert connect("cline", "--write") == (0 if accepted else 1)
    output = capsys.readouterr().err
    assert output.index("+ Add mcpServers.uoink") < output.index("[y/N]")
    assert bool(list(home.rglob("cline_mcp_settings.json"))) == accepted


def test_edit_during_confirmation_is_preserved(home, monkeypatch):
    cfg = home / ".cursor/mcp.json"
    cfg.parent.mkdir()
    cfg.write_bytes(b"{}")

    class ConcurrentEdit(Terminal):
        def readline(self):
            cfg.write_bytes(b'{"theme":"new"}')
            return "yes\n"

    monkeypatch.setattr(sys, "stdin", ConcurrentEdit())
    assert connect("cursor", "--write") == 1
    assert cfg.read_bytes() == b'{"theme":"new"}'
    assert not cfg.with_suffix(".json.bak").exists()


def test_restore_first_config_if_second_replace_fails(home, monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    roaming, package = desktop_paths(home)
    for path in (roaming, package):
        path.parent.mkdir(parents=True)
        path.write_bytes(b'{"theme":"original"}')
    replace = Path.replace

    def locked(path, target):
        if target == package:
            raise PermissionError("client has this file open")
        return replace(path, target)

    monkeypatch.setattr(Path, "replace", locked)
    assert connect("claude-desktop", "--write", "--yes") == 1
    assert roaming.read_bytes() == package.read_bytes() == b'{"theme":"original"}'


def test_missing_claude_prints_command(home, monkeypatch, capsys):
    monkeypatch.setenv("PATH", str(home / "empty-bin"))
    assert connect("claude-code", "--write") == 1
    output = capsys.readouterr()
    assert "claude mcp add --scope user" in output.out and "not found on PATH" in output.err
    assert "Restart" not in output.out


@pytest.mark.parametrize("exit_code", [0, 7])
def test_claude_on_path_receives_exact_arguments(home, monkeypatch, capsys, exit_code):
    bin_dir = home / "bin"
    bin_dir.mkdir()
    # The real interpreter, named claude, runs the fixture script named "mcp".
    record = home / "mcp"
    record.write_text("import json, sys\nfrom pathlib import Path\n"
                      "Path('args.json').write_text(json.dumps(sys.argv))\n"
                      f"sys.exit({exit_code})\n", encoding="utf-8")
    if os.name == "nt":
        interpreter = Path(sys._base_executable)
        shutil.copyfile(interpreter, bin_dir / "claude.exe")
        monkeypatch.setenv("PYTHONHOME", sys.base_prefix)
        monkeypatch.setenv("PATH", os.pathsep.join(map(str, (bin_dir, interpreter.parent))))
    else:
        fake = bin_dir / "claude"
        fake.write_text(f'#!/bin/sh\nexec {shlex.quote(sys.executable)} "$@"\n')
        fake.chmod(0o755)
        monkeypatch.setenv("PATH", str(bin_dir))
    monkeypatch.setattr(cli, "APP_DIR", home / "Fixture's & test install")
    python = cli.APP_DIR / "python" / ("python.exe" if os.name == "nt" else "bin/python3")
    python.parent.mkdir(parents=True)
    python.touch()
    monkeypatch.setattr(recipes, "python_command", lambda app: python)
    monkeypatch.setattr(cli.isolation, "child_argv", lambda: ["--isolated-profile", str(home / "profile"),
                                                              "--isolated-port", "18128"])
    monkeypatch.setattr(sys, "stdin", io.StringIO("y\n"))
    assert connect("claude-code", "--write") == 1
    assert "--yes" in capsys.readouterr().err
    assert not (home / "args.json").exists()
    assert connect("claude-code", "--write", "--yes", "--toolset", "search") == (1 if exit_code else 0)
    entry = recipes.server_entry("claude-code", cli.APP_DIR, python, cli.isolation.child_argv(), "search")
    argv = json.loads((home / "args.json").read_bytes())
    assert argv == ["mcp", "add", "--scope", "user", "-e", "PYTHONIOENCODING=utf-8",
                    "-e", "PYTHONUTF8=1", "-e", "UOINK_MCP_TOOLSET=search", "--transport", "stdio",
                    "uoink", "--", entry["command"], *entry["args"]]
    output = capsys.readouterr()
    assert ("Restart Claude Code" in output.out) == (exit_code == 0)


def test_codex_write_stays_manual(home, capsys):
    path = home / ".codex/config.toml"
    path.parent.mkdir()
    path.write_bytes(b'# keep this comment\nmodel = "example"\n')
    assert connect("codex", "--write", "--yes") == 1
    result = capsys.readouterr()
    assert "[mcp_servers.uoink]" in result.out and "printed recipe" in result.err
    assert path.read_bytes().startswith(b"# keep this comment\n")
    assert list(path.parent.iterdir()) == [path]


@pytest.mark.parametrize("client,platform,relative", [
    ("windsurf", "win32", "Roaming/devin/mcp_config.json"),
    ("zed", "linux", ".config/zed/settings.json"),
    ("zed", "darwin", None),
    ("lm-studio", "win32", ".lmstudio/mcp.json"),
    ("warp", "linux", ".warp/.mcp.json"),
    ("junie", "darwin", ".junie/mcp/mcp.json"),
    ("roo", "win32", ".roo/mcp.json"),
    ("boltai", "darwin", ".boltai/mcp.json"),
    ("anythingllm", "win32", "Roaming/anythingllm-desktop/storage/plugins/anythingllm_mcp_servers.json"),
    ("kiro", "linux", ".kiro/settings/mcp.json"),
    ("copilot-cli", "win32", "alternate copilot/mcp-config.json"),
    ("auggie", "linux", ".augment/settings.json"),
    ("factory-droid", "win32", ".factory/mcp.json"),
    ("qwen-code", "linux", ".qwen/settings.json"),
    ("antigravity", "darwin", ".gemini/config/mcp_config.json"),
    ("dive", "win32", None),
    ("kilo", "linux", None),
    ("open-webui", "linux", None),
])
def test_other_recipe_destinations(home, monkeypatch, capsys, client, platform, relative):
    monkeypatch.setattr(sys, "platform", platform)
    monkeypatch.setenv("COPILOT_HOME", str(home / "alternate copilot"))
    assert connect(client) == 0
    recipe = json.loads(capsys.readouterr().out)
    assert connect(client, "--write", "--yes") == (0 if relative else 1)
    files = [p for p in home.rglob("*") if p.is_file()]
    if relative:
        assert files == [home / relative]
        assert json.loads(files[0].read_bytes()) == recipe
    else:
        assert not files


def test_odr_registers_only_an_unpacked_manifest(home, monkeypatch, capsys):
    from types import SimpleNamespace
    monkeypatch.setattr(sys, "platform", "win32")
    manifest = home / "manifest.json"
    manifest.write_text('{"name":"uoink","server":{"entry_point":"uoink_mcp.py"}}')
    args = ["--write", "--yes", "--manifest", str(manifest)]
    calls = []
    (home / "odr.exe").touch()
    (home / "odr.exe").chmod(0o755)
    monkeypatch.setenv("PATH", str(home))

    def run(argv, *, shell, timeout):
        calls.append((argv, shell))
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(recipes.subprocess, "run", run)
    assert connect("windows-odr", *args) == 1
    assert calls == []
    (home / "uoink_mcp.py").touch()
    assert connect("windows-odr", *args) == 0
    assert calls == [([str(home / "odr.exe"), "mcp", "add", str(manifest)], False)]
    assert "odr.exe list" in capsys.readouterr().out
