"""Offline agent CLI parsing, dispatch/stdio parity, recipes and packaging."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tomllib

import pytest

import uoink_cli as cli
import uoink_connect as connect
import uoink_mcp_tools as registry

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("args", [
    ["unknown"], ["--text"], ["call"], ["search"], ["connect"], ["connect", "unknown"],
    ["connect", "codex", "--list"], ["tools", "--toolset", "invalid"],
    ["connect", "codex", "--deeplink"], ["connect", "--list", "--deeplink"],
    ["call", "search_library", "--args", "[]"],
    ["call", "search_library", "--args", '{"query":"a","query":"b"}'],
    ["call", "search_library", "--args", '{"limit":NaN}'],
    ["call", "search_library", "--args", '{"limit":1e999}'],
    ["call", "search_library", "--args", "{broken"],
    ["call", "search_library", "query=a", "--args", "{}"],
    ["call", "search_library", "query=a", "query=b"],
    ["call", "search_library", "query"], ["skill", "install"],
])
def test_usage_errors_do_not_import_backend(args, capsys, monkeypatch):
    monkeypatch.setattr(cli, "backend", lambda: pytest.fail("usage must not load backend"))
    assert cli.main(args) == 2
    output = capsys.readouterr()
    assert output.out == "" and output.err.startswith("uoink:")


def test_argument_sources_and_types(tmp_path):
    expected = {"query": "two words", "limit": 3, "enabled": False, "list": [1, "x"]}
    path = tmp_path / "arguments with spaces.json"
    path.write_text(json.dumps(expected), encoding="utf-8-sig")
    for args in (["--args", json.dumps(expected)], ["--args-file", str(path)],
                 ["query=two words", "limit=3", "enabled=false", 'list=[1,"x"]']):
        assert cli.arguments(cli.parser().parse_args(["call", "example", *args])) == expected
    with pytest.raises(cli.UsageError):
        cli.arguments(cli.parser().parse_args(["call", "x", "--args-file", str(path.parent / "missing")]))


def test_note_text_is_not_the_output_mode():
    ns = cli.parser().parse_args(["note", "long note " * 200])
    assert ns.text == "long note " * 200
    assert not getattr(ns, "text_output", False)
    ns = cli.parser().parse_args(["note", "a note", "--text"])
    assert ns.text == "a note" and ns.text_output is True


@pytest.mark.parametrize("tool", ["uoink_playlist", "transcribe_podcast_episode"])
def test_one_shot_call_finishes_background_capture(tool, tmp_path):
    # A real subprocess would discard unfinished daemon work at exit. Use only
    # synthetic workers, including a finite child spawned by the playlist.
    marker = tmp_path / "finished.txt"
    code = r'''
import json, queue, sys, threading, time
from pathlib import Path
from types import SimpleNamespace
import uoink_cli as cli
import uoink_agent_runtime as runtime
tool, marker = sys.argv[1], Path(sys.argv[2])
jobs = queue.Queue()
def finish():
    time.sleep(0.05)
    marker.write_text('completed', encoding='utf-8')
def worker():
    if tool == 'transcribe_podcast_episode':
        jobs.get()
        finish()
        jobs.task_done()
    else:
        time.sleep(0.05)
        threading.Thread(target=finish, name='hook-type-cli-test', daemon=True).start()
def dispatch(*args):
    if tool == 'transcribe_podcast_episode':
        jobs.put('synthetic-job')
    name = 'uoink-podcast-transcription' if tool == 'transcribe_podcast_episode' else 'playlist-cli-test'
    threading.Thread(target=worker, name=name, daemon=True).start()
    return {'ok': True, 'job_id': 'synthetic-job'}
cli.backend = lambda: SimpleNamespace(_podcast_transcription_queue=jobs)
runtime.call_tool = dispatch
raise SystemExit(cli.main(['call', tool]))
'''
    result = subprocess.run([sys.executable, "-B", "-c", code, tool, str(marker)],
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"ok": True, "job_id": "synthetic-job"}
    assert marker.read_text(encoding="utf-8") == "completed"


def test_tools_schemas_and_text(capsys):
    assert cli.main(["tools", "--toolset", "core", "--json"]) == 0
    tools = json.loads(capsys.readouterr().out)["tools"]
    assert tuple(t["name"] for t in tools) == registry.stdio_tool_names("core")
    for tool in tools:
        assert tool["inputSchema"] == registry.client_input_schema(registry.TOOL_REGISTRY[tool["name"]].input_schema)
    assert cli.main(["tools", "--text"]) == 0
    assert "search_library:" in capsys.readouterr().out


def test_real_cli_and_stdio_envelopes(tmp_path):
    from tests.test_c01_mcp_stdio import _StdioClient, _isolated_env
    env = _isolated_env(str(tmp_path))
    def run(*args):
        return subprocess.run([sys.executable, "-P", str(ROOT / "uoink_cli.py"), *args],
                              cwd=tmp_path, env=env, capture_output=True, text=True,
                              encoding="utf-8", timeout=60)
    note = run("note", "Offline agent fixture about memory", "--title", "CLI parity")
    assert note.returncode == 0, note.stderr
    assert json.loads(note.stdout)["ok"] is True
    child = _StdioClient([sys.executable, "-P", str(ROOT / "uoink_mcp.py")], tmp_path, env)
    try:
        child.send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2024-11-05", "capabilities": {},
            "clientInfo": {"name": "agent-cli-test", "version": "0"}}})
        assert "result" in child.wait_for(1)
        child.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        requests = [
            ("search_library", {"query": "memory"}, 0),
            ("pin_shelf", {"video_id": "video-0", "shelf_id": "shelf-1", "action": "pin",
                           "expected_projection_revision": 7, "operation_key": "pin-op-1"}, 1),
            ("poll_monitored_playlist", {"playlist_id": 1}, 1),
            ("nonexistent_tool", {}, 1),
        ]
        for request_id, (name, args, exit_code) in enumerate(requests, 2):
            child.send({"jsonrpc": "2.0", "id": request_id, "method": "tools/call",
                        "params": {"name": name, "arguments": args}})
            text = child.wait_for(request_id)["result"]["content"][0]["text"]
            # MCP surrounds successful Library JSON with its text trust fence.
            if "<untrusted_uoink_library_context>\n" in text:
                text = text.split("<untrusted_uoink_library_context>\n", 1)[1].rsplit("\n</untrusted_uoink_library_context>", 1)[0]
            stdio = json.loads(text)
            result = run("call", name, "--args", json.dumps(args))
            assert result.returncode == exit_code, result.stderr
            assert json.loads(result.stdout) == stdio
            if exit_code:
                assert result.stderr
        status = run("status")
        assert status.returncode == 0, status.stderr
        payload = json.loads(status.stdout)
        assert payload["data_dir"] == str((tmp_path / "profile").resolve())
        assert payload["helper_running"] is False
        assert payload["tool_counts"] == {"full": 91, "core": 35}
    finally:
        child.close()


def test_discovery_credit_refusal_matches_stdio(tmp_path, monkeypatch, capsys):
    from types import SimpleNamespace
    import sqlite3
    import index
    import discovery_scrapecreators as discovery
    import server
    from tests.test_mcp_full_toolset import call as stdio_call
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    index._run_migrations(conn)
    idx = index.Index(conn, tmp_path / "unused.db")
    settings = server._default_settings()
    settings.update(scrapecreators_enabled=True, scrapecreators_agent_calls_enabled=True)
    fake = SimpleNamespace(DATA_ROOT=tmp_path, _get_index=lambda: idx,
                           _read_settings=lambda: settings,
                           _get_saved_scrapecreators_key=lambda: "synthetic-test-key")
    service = discovery.DiscoveryService(fake, transport=lambda *a, **k: pytest.fail("credit refusal must not fetch"))
    monkeypatch.setattr(server, "_get_discovery_service", lambda: service)
    monkeypatch.setattr(cli, "backend", lambda: server)
    monkeypatch.setattr(registry, "_backend", server)
    monkeypatch.setattr(registry.TOOL_REGISTRY["discover_candidates"].rate_limiter, "_calls", [])
    args = {"mode": "creator", "platform": "youtube", "handle": "@fixture", "confirm_credits": 2}
    try:
        expected = stdio_call("discover_candidates", args)
        assert expected["ok"] is False and expected["error"]["details"]["reason"] == "confirm_credits_mismatch"
        assert cli.main(["call", "discover_candidates", "--args", json.dumps(args)]) == 1
        assert json.loads(capsys.readouterr().out) == expected
    finally:
        conn.close()


def test_isolated_install_marker_before_backend(tmp_path):
    from tests.test_c01_mcp_stdio import _isolated_env
    env = _isolated_env(str(tmp_path))
    env.pop("UOINK_ISOLATED_PROFILE")
    env.pop("UOINK_ISOLATED_PORT")
    app = tmp_path / "installed app"
    app.mkdir()
    profile = tmp_path / "profile"
    (app / "isolated-install.json").write_text(json.dumps({"mode": "isolated", "profile": str(profile),
        "port": 5187, "host": "127.0.0.1", "app_dir": str(app)}), encoding="utf-8")
    result = subprocess.run([sys.executable, "-P", str(ROOT / "uoink_cli.py"),
        "--isolated-from-install-dir", str(app), "status"], env=env, capture_output=True,
        text=True, encoding="utf-8", timeout=60)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["data_dir"] == str(profile)
    bad = subprocess.run([sys.executable, str(ROOT / "uoink_cli.py"),
        "--isolated-profile", str(profile), "--isolated-port", "5179", "status"],
        env=env, capture_output=True, text=True, timeout=60)
    assert bad.returncode == 2 and bad.stdout == ""


@pytest.mark.parametrize("client", connect.CLIENTS)
def test_connect_formats_parse_and_paths_are_absolute(tmp_path, client):
    app = tmp_path / "O'Brien install with spaces 🪁"
    python = app / "python" / "python.exe"
    if sys.platform == "darwin":
        python = connect.python_command(app)
    spec = connect.CLIENTS[client]
    if sys.platform not in spec.platforms:
        with pytest.raises(ValueError, match="no recipe"):
            connect.render(client, app, python)
        return
    output = connect.render(client, app, python)
    if spec.format == "text":
        assert output and "<ENTRY>" not in output and "<CLI>" not in output
        return
    if spec.format == "shell":
        tokens = re.findall(r"'((?:[^']|'')*)'", output) if os.name == "nt" else []
        flags = ["-B", "-s"] if sys.platform == "darwin" else []
        paths = [s.replace("''", "'") for s in tokens] if tokens else shlex.split(output)[-(2 + len(flags)):]
        assert paths == [str(python), *flags, str(app / "uoink_mcp.py")]
    elif spec.format == "crushrc":
        tokens = shlex.split(output)
        assert tokens[:3] == ["mcp", "add", "uoink"]
        assert tokens[4] == str(python)
        flags = ["-B", "-s"] if sys.platform == "darwin" else []
        assert tokens[6:tokens.index("--env")] == [*flags, str(app / "uoink_mcp.py")]
    else:
        # YAML clients receive JSON-form YAML (a strict YAML 1.2 subset).
        data = tomllib.loads(output) if spec.format == "toml" else json.loads(output)
        entry = (data if spec.shape == "entry" else data["mcpServers"][0]
                 if spec.shape == "list" else data[spec.shape]["uoink"])
        if spec.shape == "mcp":
            paths = entry["command"]
        else:
            paths = [entry.get("command", entry.get("cmd")), *entry["args"]]
        flags = ["-B", "-s"] if sys.platform == "darwin" else []
        assert paths == [str(python), *flags, str(app / "uoink_mcp.py")]
        assert all(Path(p).is_absolute() for p in paths if p not in flags)
        env = entry.get("env", entry.get("envs", entry.get("environment")))
        assert env["PYTHONUTF8"] == "1" and env["PYTHONIOENCODING"] == "utf-8"
        if client == "cursor":
            assert env["UOINK_MCP_TOOLSET"] == "core"


def test_connect_stdout_only_config_and_notes_on_stderr(capsys):
    for client in connect.CLIENTS:
        if sys.platform not in connect.CLIENTS[client].platforms:
            assert cli.main(["connect", client]) == 2
            output = capsys.readouterr()
            assert not output.out and "no recipe" in output.err
            continue
        assert cli.main(["connect", client]) == 0
        output = capsys.readouterr()
        assert "File:" in output.err and "not yet tested" in output.err
        assert connect.client_spec(client).location in output.err
        assert "Official docs verified:" in output.err and "Checked: 2026-10-21" in output.err
        if connect.CLIENTS[client].format != "shell":
            assert "Tested:" not in output.out


@pytest.mark.parametrize("url,tool,key", [
    ("https://youtu.be/abcdefghijk", "uoink_video", "url"),
    ("https://youtube.com/playlist?list=PLabcdefghijk", "uoink_playlist", "url"),
    ("https://x.com/example/status/1234567890123456789", "uoink_url", "url"),
    ("https://x.com/example/article/123456789", "uoink_page", "url"),
    ("https://reddit.com/r/example/comments/abc123/example", "uoink_reddit_thread", "url"),
    ("https://feeds.example.com/show.xml", "add_podcast_feed", "feed_url"),
    ("https://example.com/article", "uoink_page", "url"),
])
def test_capture_uses_existing_classifier(url, tool, key):
    import server
    name, args = cli.friendly_call(cli.parser().parse_args(["capture", url]), server)
    assert name == tool and args == {key: server._classify_capture_url(url)["canonical"]}


def test_skill_copy_refuses_overwrite_and_preserves_references(tmp_path, capsys):
    assert cli.main(["skill", "install", "--to", str(tmp_path)]) == 0
    capsys.readouterr()
    assert (tmp_path / "uoink/references/library-evidence.md").is_file()
    assert cli.main(["skill", "install", "--to", str(tmp_path)]) == 2
    capsys.readouterr()
    assert cli.main(["skill", "install", "--to", str(tmp_path), "--force"]) == 0
    assert (tmp_path / "uoink/SKILL.md").read_bytes() == (ROOT / "skills/uoink/SKILL.md").read_bytes()


def test_legacy_launcher_unchanged_and_serve_forwards(monkeypatch):
    from types import SimpleNamespace
    seen = []
    monkeypatch.setattr(cli, "backend", lambda: SimpleNamespace(run_cli=lambda args: seen.append(args) or 0))
    assert cli.main([]) == 0
    assert cli.main(["serve", "--doctor"]) == 0
    assert seen == [[], ["--doctor"]]
    assert '"%UOINK_ROOT%server.py" %*' in (ROOT / "uoink.cmd").read_text()
    launcher = (ROOT / "cli/uoink.cmd").read_text()
    assert '"%~dp0..\\python\\python.exe" "%~dp0..\\uoink_cli.py" %*' in launcher
    assert "exit /b %ERRORLEVEL%" in launcher
    shell = (ROOT / "cli/uoink").read_text()
    assert '"$uoink_root/python/python.exe"' in shell
    assert 'exec "$uoink_python" "$uoink_root/uoink_cli.py" "$@"' in shell


def test_agent_kit_copies_cannot_drift():
    import runpy
    build = runpy.run_path(str(ROOT / "scripts/build_agent_kit.py"))["build"]
    assert build(check=True) == []
    assert len((ROOT / "skills/uoink/SKILL.md").read_text().splitlines()) < 200


def test_agent_kit_version_drift_fails_check_and_build_repairs_it(tmp_path, monkeypatch, capsys):
    import runpy
    build = runpy.run_path(str(ROOT / "scripts/build_agent_kit.py"))["build"]
    source = tmp_path / "skills/uoink"
    source.mkdir(parents=True)
    (source / "SKILL.md").write_text("Fixture skill\n", encoding="utf-8")
    manifest = tmp_path / "agent-kit/plugins/uoink/.claude-plugin/plugin.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text('{"name": "uoink", "version": "0.0.0"}\n', encoding="utf-8")
    (tmp_path / "VERSION").write_text("3.10.0\n", encoding="utf-8")
    for relative in ("docs/connect-your-agent.md", "agent-kit/README.md"):
        document = tmp_path / relative
        document.parent.mkdir(parents=True, exist_ok=True)
        document.write_text("<!-- BEGIN GENERATED CLIENTS -->\n" + connect.client_table()
                            + "<!-- END GENERATED CLIENTS -->\n", encoding="utf-8")
    monkeypatch.setitem(build.__globals__, "ROOT", tmp_path)
    monkeypatch.setitem(build.__globals__, "SOURCE", source)
    monkeypatch.setitem(build.__globals__, "DESTINATIONS", ())
    before = manifest.read_bytes()
    assert build(check=True) == [str(manifest.relative_to(tmp_path))]
    monkeypatch.setattr(sys, "argv", ["build_agent_kit.py", "--check"])
    assert build.__globals__["main"]() == 1
    assert "plugin.json" in capsys.readouterr().err
    assert manifest.read_bytes() == before
    assert build() == []
    assert json.loads(manifest.read_text(encoding="utf-8")) == {"name": "uoink", "version": "3.10.0"}
    assert build(check=True) == []


def test_installer_path_ownership_isolation_and_exact_removal():
    source = (ROOT / "installer/uoink.iss").read_text(encoding="utf-8")
    assert "ChangesEnvironment=yes" in source
    task = next(line for line in source.splitlines() if line.startswith('Name: "agentpath"'))
    assert "unchecked" not in task and "Check: not IsolatedInstall" in task
    def block(start, end):
        return source.split(start, 1)[1].split(end, 1)[0]
    add = block("procedure AddAgentPath();", "procedure RemoveAgentPath();")
    remove = block("procedure RemoveAgentPath();\nvar", "procedure CurUninstallStepChanged")
    for body in (add, remove):
        assert body.index("if IsolatedInstall() then Exit;") < body.index("AgentReadPath(")
    assert "Target := ExpandConstant('{app}\\cli');" in add
    assert add.index("if Found then Exit") < add.index("SaveStringToFile") < add.index("AgentWritePath")
    assert remove.index("if not LoadStringFromFile(Marker, Saved) then Exit;") < remove.index("AgentReadPath(")
    assert "Target := Utf8Decode(Saved);" in remove
    assert "if not (AgentSameEntry(AgentExpandedEntry(Target), ExpandConstant('{app}\\cli')) or\n" in remove
    assert "AgentSameEntry(AgentExpandedEntry(Target), ExpandConstant('{app}\\bin'))) then Exit;" in remove
    assert "AgentFilterPath(Value, Target, True, Found)" in remove
    assert "AgentWritePath(Updated, ValueType)" in remove
    assert "if CurUninstallStep = usUninstall then RemoveAgentPath();" in source
    filtering = block("function AgentFilterPath(", "procedure AddAgentPath();")
    assert "Copy(Value, Start, I - Start)" in filtering
    assert "(not Found) and AgentSameEntry(Entry, Target)" in filtering
    assert "Result := Result + Entry" in filtering and "First := False" in filtering
    assert "StringChange" not in filtering and "Pos(" not in filtering
    writing = block("function AgentWritePath(", "function AgentSameEntry(")
    assert "RegWriteExpandStringValue(HKCU, 'Environment', 'Path', Value)" in writing
    assert "RegWriteStringValue(HKCU, 'Environment', 'Path', Value)" in writing
    assert "if ValueType = 2" in writing
    assert "RegQueryValueExW@advapi32.dll" in source


def test_installer_migrates_only_marker_owned_legacy_path_before_adding_cli():
    code = (ROOT / "installer/uoink.iss").read_text(encoding="utf-8").split("[Code]", 1)[1]
    add = code.split("procedure AddAgentPath();", 1)[1].split("procedure RemoveAgentPath();", 1)[0]
    migration = (
        "if LoadStringFromFile(Marker, Saved) then\n"
        "    if AgentSameEntry(AgentExpandedEntry(Utf8Decode(Saved)), ExpandConstant('{app}\\bin')) then\n"
        "      RemoveAgentPath();"
    )
    assert migration in add
    assert add.index("if IsolatedInstall() then Exit;") < add.index(migration)
    assert add.index(migration) < add.index("if not WizardIsTaskSelected('agentpath') then Exit;")
    assert add.index(migration) < add.index("AgentReadPath(") < add.index("if Found then Exit")
    assert add.index("if Found then Exit") < add.index("SaveStringToFile(Marker, Utf8Encode(Target), False)")
    remove = code.split("procedure RemoveAgentPath();\nvar", 1)[1].split("procedure CurUninstallStepChanged", 1)[0]
    assert remove.index("IsolatedMarkerFileExists") < remove.index("LoadStringFromFile")
    assert remove.index("LoadStringFromFile") < remove.index("if not (AgentSameEntry") < remove.index("AgentReadPath(")
    assert remove.index("AgentFilterPath(Value, Target, True, Found)") < remove.index("if Found and not AgentWritePath") < remove.index("DeleteFile(Marker)")
    # Expand the marker only for ownership validation. Removal matches its raw
    # spelling, preserving other equivalent entries, duplicates and prefixes.
    same = code.split("function AgentSameEntry(", 1)[1].split("function AgentFilterPath(", 1)[0]
    assert "CompareText(RemoveBackslash(RemoveQuotes(Trim(Entry)))," in same
    assert "RemoveBackslash(RemoveQuotes(Trim(Target)))) = 0" in same
    assert "AgentExpandedEntry" not in same
    expanded = code.split("function AgentExpandedEntry(", 1)[1].split("function AgentSameEntry(", 1)[0]
    assert "AgentExpandEnvironmentStrings(" in expanded
    assert "(Written = 0) or (Written > Size)" in expanded
    assert "ExpandEnvironmentStringsW@kernel32.dll stdcall" in code
    filtering = code.split("function AgentFilterPath(", 1)[1].split("procedure RemoveAgentPath(); forward;", 1)[0]
    assert "Drop := (not Found) and AgentSameEntry(Entry, Target);" in filtering
    assert "if not (Remove and Drop) then" in filtering
    assert "Result := Result + Entry;" in filtering
    assert "AgentExpandedEntry" not in filtering


def test_receipt_uses_installed_launcher_and_isolated_profile():
    source = (ROOT / "scripts/install_receipt/agent_install.ps1").read_text()
    assert "'/ISOLATED=1'" in source and "'/TASKS=\"\"'" in source
    assert "& $taskAgentCli --isolated-from-install-dir $taskApp status" in source
    assert "$taskCliStatus.data_dir -ine $taskProfile" in source
    assert "'cli\\uoink.cmd'" in (ROOT / "installer/verify_install.ps1").read_text()
