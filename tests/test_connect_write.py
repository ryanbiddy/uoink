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

import agent_config_writer as writer
import server
import uoink_cli as cli
import uoink_connect as recipes


def test_dashboard_connect_feedback():
    script = Path(__file__).resolve().parent / "js/agent_connect_test.mjs"
    node = shutil.which("node")
    if node is None:
        if os.environ.get("CI"):
            pytest.fail("Dashboard connect tests require Node in CI")
        pytest.skip("Node is not installed")
    result = subprocess.run([node, "--test", str(script)], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr


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
        if target.resolve() == package.resolve():
            raise PermissionError("client has this file open")
        return replace(path, target)

    monkeypatch.setattr(Path, "replace", locked)
    assert connect("claude-desktop", "--write", "--yes") == 1
    assert roaming.read_bytes() == package.read_bytes() == b'{"theme":"original"}'
    assert list(roaming.parent.iterdir()) == [roaming]
    assert list(package.parent.iterdir()) == [package]


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
    bin_dir = home / "bin"
    bin_dir.mkdir()
    odr = bin_dir / "odr.exe"
    odr.touch()
    odr.chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_dir))
    if os.name != "nt":
        # Python 3.12+ which() applies its win32 PATHEXT rules from the patched
        # sys.platform but splits PATHEXT on the real os.pathsep (":"), so a
        # simulated .exe is never found on POSIX. Keep the real access check.
        monkeypatch.setattr(recipes.shutil, "which",
                            lambda cmd, *a, **k: cmd if os.access(cmd, os.X_OK) else None)

    def run(argv, *, shell, timeout):
        calls.append((argv, shell))
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(recipes.subprocess, "run", run)
    assert connect("windows-odr", *args) == 1
    assert calls == []
    assert capsys.readouterr().out == ""
    (home / "uoink_mcp.py").touch()
    assert connect("windows-odr", *args) == 0
    assert calls == [([str(odr), "mcp", "add", str(manifest)], False)]
    output = capsys.readouterr()
    assert "odr.exe list" in output.out and "PowerShell" in output.err


@pytest.mark.skipif(os.name != "nt", reason="uses real Windows batch argument parsing")
@pytest.mark.parametrize("extension,quoted_path", [("cmd", False), ("bat", True)])
def test_windows_shim_receives_exact_arguments(home, monkeypatch, extension, quoted_path):
    bin_dir = home / "npm shims"
    bin_dir.mkdir()
    recorder = bin_dir / "record.py"
    recorder.write_text("import json, sys\nfrom pathlib import Path\n"
                        "Path('received.json').write_text(json.dumps(sys.argv[1:]))\n")
    (bin_dir / f"claude.{extension}").write_text(
        f'@echo off\n>sixth.txt echo %~6\n"{sys.executable}" "%~dp0record.py" %*\n')
    # npm also installs an extensionless POSIX shell script beside its .cmd.
    (bin_dir / "claude").touch()
    monkeypatch.setenv("PATHEXT", f".{extension.upper()};.EXE")
    monkeypatch.setenv("PATH", f'"{bin_dir}"' if quoted_path else str(bin_dir))
    app = home / "Uoink install"
    monkeypatch.setattr(cli, "APP_DIR", app)
    python = app / "python/python.exe"
    monkeypatch.setattr(recipes, "python_command", lambda _: python)
    launched = []
    run = subprocess.run

    def record_launch(command, **options):
        launched.append((command, options))
        return run(command, **options)

    monkeypatch.setattr(subprocess, "run", record_launch)
    assert connect("claude-code", "--write", "--yes") == 0
    entry = recipes.server_entry("claude-code", app, python, cli.isolation.child_argv())
    assert json.loads((home / "received.json").read_bytes()) == recipes.claude_add_argv(entry)[1:]
    assert (home / "sixth.txt").read_text().strip() == "PYTHONIOENCODING=utf-8"
    command, options = launched[0]
    assert isinstance(command, str) and " /d /s /c " in command.lower()
    assert Path(options["executable"]).is_absolute() and options["shell"] is False


@pytest.mark.skipif(os.name != "nt", reason="Windows PATHEXT and batch argument rules")
@pytest.mark.parametrize("character", list(",;%!^&|<>\"'()") + ["\r", "\n"])
def test_batch_metacharacters_refused_before_launch(home, monkeypatch, capsys, character):
    bin_dir = home / "bin"
    bin_dir.mkdir()
    (bin_dir / "claude.cmd").touch()
    monkeypatch.setenv("PATH", str(bin_dir))
    monkeypatch.setenv("PATHEXT", ".CMD")
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: pytest.fail("batch was launched"))
    assert recipes._run_add(["claude", "value" + character], "Claude Code", True) == 1
    assert "batch launcher" in capsys.readouterr().err


def test_lookup_skips_cwd_and_relative_entries(home, monkeypatch, capsys):
    name = "claude.exe" if os.name == "nt" else "claude"
    (home / name).touch()
    (home / "relative").mkdir()
    (home / "relative" / name).touch()
    monkeypatch.setenv("PATH", os.pathsep.join(["", ".", "relative", str(home), ""]))
    monkeypatch.setattr(shutil, "which", lambda *a, **kw: pytest.fail("searched outside an absolute PATH directory"))
    assert recipes._run_add(["claude"], "Claude Code", True) == 1
    assert "not found on PATH" in capsys.readouterr().err


@pytest.mark.skipif(os.name != "nt", reason="npm Windows launcher")
def test_standard_npm_shim_uses_native_node(home, monkeypatch):
    node = shutil.which("node.exe")
    if node is None and not os.environ.get("CI"):
        pytest.skip("Node is not installed")
    assert node, "Node is required for the npm launcher test in CI"
    bin_dir = home / "npm prefix"
    script = bin_dir / "node_modules/@anthropic-ai/claude-code/cli.js"
    script.parent.mkdir(parents=True)
    script.write_text("require('fs').writeFileSync('received.json', JSON.stringify(process.argv.slice(2)))")
    # Generated by npm's cmd-shim 8.0.0 from a plain /usr/bin/env node shebang.
    shutil.copyfile(Path(__file__).with_name("fixtures") / "npm-claude.cmd", bin_dir / "claude.cmd")
    monkeypatch.setenv("PATHEXT", ".CMD;.EXE")
    monkeypatch.setenv("PATH", os.pathsep.join([str(bin_dir), str(Path(node).parent)]))
    run = subprocess.run

    def native(argv, **options):
        assert argv == [node, str(script), "mcp", "add", "two words"]
        assert options["shell"] is False
        return run(argv, **options)

    monkeypatch.setattr(subprocess, "run", native)
    assert recipes._run_add(["claude", "mcp", "add", "two words"], "Claude Code", True) == 0
    assert json.loads((home / "received.json").read_bytes()) == ["mcp", "add", "two words"]


@pytest.mark.skipif(os.name != "nt", reason="Python 3.11's Windows which semantics")
def test_pathext_order_with_exact_path_lookup(home, monkeypatch):
    from types import SimpleNamespace
    folder = home / "tools"
    folder.mkdir()
    for name in ("claude", "claude.cmd", "claude.exe"):
        (folder / name).touch()
    monkeypatch.setenv("PATH", str(folder))
    monkeypatch.setattr(shutil, "which", lambda path: path if Path(path).is_file() else None)
    calls = []

    def launch(argv, **options):
        calls.append(argv)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(subprocess, "run", launch)
    for pathext, expected in [(".EXE;.CMD", "claude.exe"), (".CMD;.EXE", "claude.cmd"), (".BAT", None)]:
        monkeypatch.setenv("PATHEXT", pathext)
        assert recipes._run_add(["claude"], "Claude Code", True) == (0 if expected else 1)
        if expected:
            assert str(folder / expected) in calls.pop()
        assert not calls


def test_cli_timeout_keeps_registration_status_unknown(home, monkeypatch, capsys):
    bin_dir = home / "bin"
    bin_dir.mkdir()
    exe = bin_dir / ("claude.exe" if os.name == "nt" else "claude")
    exe.touch()
    exe.chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_dir))

    def timeout(argv, *, shell, timeout):
        assert shell is False and timeout == 30
        raise subprocess.TimeoutExpired(argv, timeout)

    monkeypatch.setattr(subprocess, "run", timeout)
    assert connect("claude-code", "--write", "--yes") == 1
    output = capsys.readouterr()
    assert "Check its server list before retrying" in output.err and "Restart" not in output.out


def test_partial_desktop_connection(home, monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    roaming, store = desktop_paths(home)
    for target in (roaming, store):
        target.parent.mkdir(parents=True)
        target.write_bytes(b"{}")
    server._connect_ai_client("claude-desktop")
    assert server._client_is_connected(roaming)
    store.write_bytes(b"{}")
    result = next(x for x in server._detect_ai_clients() if x["name"] == "claude-desktop")
    assert result["installed"] and not result["connected"]


def test_crlf_and_utf8_bom_backup(home):
    cfg = home / ".cursor/mcp.json"
    cfg.parent.mkdir()
    original = b'\xef\xbb\xbf{\r\n  "theme": "caf\xc3\xa9"\r\n}\r\n'
    cfg.write_bytes(original)
    assert connect("cursor", "--write", "--yes") == 0
    saved = cfg.read_bytes()
    assert json.loads(saved.decode("utf-8"))["theme"] == "caf\u00e9"
    assert saved.endswith(b"\r\n") and b"\n" not in saved.replace(b"\r\n", b"")
    assert cfg.with_suffix(".json.bak").read_bytes() == original


def test_jsonc_explains_manual_merge(home, capsys):
    cfg = home / ".vscode/mcp.json"
    cfg.parent.mkdir()
    original = b'{\n // keep this note\n "servers": {}\n}'
    cfg.write_bytes(original)
    assert connect("vscode", "--write", "--yes") == 1
    message = capsys.readouterr().err.lower()
    assert "comments" in message and "without --write" in message
    assert cfg.read_bytes() == original and list(cfg.parent.iterdir()) == [cfg]


def file_link(link, target, monkeypatch):
    try:
        link.symlink_to(target)
    except OSError as exc:
        if getattr(exc, "winerror", None) != 1314:
            raise
        # Windows runners without CreateSymbolicLink privilege still test the refusal.
        link.write_bytes(target.read_bytes())
        is_link = Path.is_symlink
        monkeypatch.setattr(Path, "is_symlink", lambda p: p == link or is_link(p))


def test_refuses_linked_config(home, monkeypatch, capsys):
    cfg = home / ".cursor/mcp.json"
    cfg.parent.mkdir()
    target = home / "original.json"
    target.write_bytes(b"{}")
    file_link(cfg, target, monkeypatch)
    assert connect("cursor", "--write", "--yes") == 1
    assert "symbolic link" in capsys.readouterr().err
    assert target.read_bytes() == b"{}" and list(cfg.parent.iterdir()) == [cfg]


@pytest.mark.parametrize("bad", ["missing", "invalid", "linked-manifest", "linked-entry"])
@pytest.mark.parametrize("flags", [(), ("--write", "--yes")], ids=["preview", "write"])
def test_invalid_odr_manifest_never_prints_a_command(home, monkeypatch, capsys, bad, flags):
    monkeypatch.setattr(sys, "platform", "win32")
    bundle = home / "bundle"
    bundle.mkdir()
    manifest = bundle / "manifest.json"
    entry = bundle / "main.py"
    valid = b'{"name":"uoink","server":{"entry_point":"main.py"}}'
    if bad == "invalid":
        manifest.write_bytes(b"{")
    elif bad.startswith("linked"):
        outside = home / "outside"
        if bad == "linked-manifest":
            outside.write_bytes(valid)
            file_link(manifest, outside, monkeypatch)
            entry.touch()
        else:
            outside.touch()
            file_link(entry, outside, monkeypatch)
            manifest.write_bytes(valid)
    assert connect("windows-odr", "--manifest", str(manifest), *flags) == 1
    output = capsys.readouterr()
    assert output.out == "" and "unpacked Uoink bundle" in output.err


def test_odr_entry_must_resolve_inside_bundle(home, monkeypatch, capsys):
    monkeypatch.setattr(sys, "platform", "win32")
    outside = home / "outside"
    outside.mkdir()
    (outside / "main.py").touch()
    bundle = home / "bundle"
    bundle.mkdir()
    linked_dir = bundle / "files"
    if os.name == "nt":
        # A directory junction works without Windows symlink privileges.
        import _winapi
        _winapi.CreateJunction(str(outside), str(linked_dir))
    else:
        linked_dir.symlink_to(outside, target_is_directory=True)
    manifest = bundle / "manifest.json"
    manifest.write_text('{"name":"uoink","server":{"entry_point":"files/main.py"}}')
    assert connect("windows-odr", "--manifest", str(manifest)) == 1
    assert capsys.readouterr().out == ""


def test_read_only_config_preserves_original_and_backup(home):
    cfg = home / "settings.json"
    cfg.write_bytes(b"{}")
    backup = cfg.with_suffix(".json.bak")
    backup.write_bytes(b"older")
    cfg.chmod(0o444)
    try:
        with pytest.raises(writer.ConfigError, match="read.only"):
            writer.apply_edits([writer.plan_edit(cfg, "Client", "servers", {})], "Client")
        assert cfg.read_bytes() == b"{}" and backup.read_bytes() == b"older"
        assert set(home.iterdir()) == {cfg, backup}
    finally:
        cfg.chmod(0o600)


def test_cleanup_of_read_only_staging_preserves_backup_error(home, monkeypatch):
    cfg = home / "settings.json"
    cfg.write_bytes(b"{}")
    original_error = PermissionError("fixture copy failure")

    def failed_copy(source, staged):
        staged.chmod(0o400)
        raise original_error

    monkeypatch.setattr(shutil, "copy2", failed_copy)
    with pytest.raises(writer.ConfigError, match="back up") as error:
        writer.apply_edits([writer.plan_edit(cfg, "Client", "servers", {})], "Client")
    assert error.value.__cause__ is original_error
    assert cfg.read_bytes() == b"{}" and list(home.iterdir()) == [cfg]


def test_existing_backup_link_never_modifies_its_target(home, monkeypatch):
    cfg = home / "settings.json"
    cfg.write_bytes(b"{}")
    edit = writer.plan_edit(cfg, "Client", "servers", {})
    outside = home / "archive"
    outside.write_bytes(b"older backup")
    try:
        edit.backup.symlink_to(outside.name)
    except OSError as exc:
        if getattr(exc, "winerror", None) != 1314:
            raise
        # If Windows denies creating a rollback link, abort before publication.
        edit.backup.touch()
        is_link = Path.is_symlink
        monkeypatch.setattr(Path, "is_symlink", lambda p: p == edit.backup or is_link(p))
        monkeypatch.setattr(Path, "readlink", lambda p: Path(outside.name))
        with pytest.raises(writer.ConfigError, match="back up"):
            writer.apply_edits([edit], "Client")
        assert cfg.read_bytes() == b"{}" and edit.backup.read_bytes() == b""
    else:
        with monkeypatch.context() as patch:
            replace = Path.replace

            def locked(staged, dest):
                if dest.resolve() == cfg.resolve():
                    raise PermissionError("locked")
                return replace(staged, dest)

            patch.setattr(Path, "replace", locked)
            with pytest.raises(writer.ConfigError):
                writer.apply_edits([edit], "Client")
        assert edit.backup.is_symlink() and edit.backup.readlink() == Path(outside.name)
        writer.apply_edits([edit], "Client")
        assert not edit.backup.is_symlink() and edit.backup.read_bytes() == b"{}"
    assert outside.read_bytes() == b"older backup"
    assert set(home.iterdir()) == {cfg, edit.backup, outside}


def test_late_change_keeps_both_previous_backups(home):
    edits = []
    for cfg in (home / "one.json", home / "two.json"):
        cfg.write_bytes(b"{}")
        edit = writer.plan_edit(cfg, "Client", "servers", {})
        edit.backup.write_bytes(b"previous backup")
        edits.append(edit)
    edits[-1].path.write_bytes(b'{"client":"edit"}')
    with pytest.raises(writer.ConfigError, match="changed"):
        writer.apply_edits(edits, "Client")
    assert edits[0].path.read_bytes() == b"{}"
    assert edits[-1].path.read_bytes() == b'{"client":"edit"}'
    assert all(e.backup.read_bytes() == b"previous backup" for e in edits)
    assert len(list(home.iterdir())) == 4


def test_rollback_continues_after_one_restore_fails(home, monkeypatch):
    edits = []
    for name in ("first", "second", "third"):
        cfg = home / (name + ".json")
        cfg.write_bytes(b"{}")
        edit = writer.plan_edit(cfg, "Client", "servers", {})
        edit.backup.write_bytes(b"earlier backup")
        edits.append(edit)
    first, second, third = edits
    replace = Path.replace
    original_error = PermissionError("locked during save")

    def locked(staged, dest):
        if dest.resolve() == third.path.resolve():
            raise original_error
        if dest.resolve() == second.path.resolve() and dest.read_bytes() == second.replacement:
            raise PermissionError("locked during restore")
        return replace(staged, dest)

    monkeypatch.setattr(Path, "replace", locked)
    with pytest.raises(writer.ConfigError) as error:
        writer.apply_edits(edits, "Client")
    assert first.path.read_bytes() == third.path.read_bytes() == b"{}"
    assert second.path.read_bytes() == second.replacement and second.backup.read_bytes() == b"{}"
    assert first.backup.read_bytes() == third.backup.read_bytes() == b"earlier backup"
    assert "restore" in str(error.value) and error.value.__cause__ is original_error
    assert len(list(home.iterdir())) == 6


def test_fsync_failure_stops_before_any_replace(home, monkeypatch):
    cfg = home / "settings.json"
    cfg.write_bytes(b"{}")
    edit = writer.plan_edit(cfg, "Client", "servers", {})
    synced = []

    def fail_second_sync(fd):
        synced.append(os.fstat(fd).st_size)
        if len(synced) == 2:
            raise OSError("sync failed")

    monkeypatch.setattr(os, "fsync", fail_second_sync)
    monkeypatch.setattr(Path, "replace", lambda *a: pytest.fail("replaced before both files synced"))
    with pytest.raises(writer.ConfigError):
        writer.apply_edits([edit], "Client")
    assert sorted(synced) == sorted([len(edit.original), len(edit.replacement)])
    assert cfg.read_bytes() == b"{}" and list(home.iterdir()) == [cfg]
