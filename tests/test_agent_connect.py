"""Offline recipe and install-link contracts. No real client launches."""
import base64
import json
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

import pytest

import server
import uoink_cli as cli
import uoink_connect as connect


def test_recipe_documentation_covers_the_table():
    doc = (Path(__file__).resolve().parents[1] / "docs/connect-your-agent.md").read_text(encoding="utf-8")
    for name in connect.CLIENTS:
        assert f"uoink connect {name}`" in doc
    assert "not yet tested" in doc


@pytest.mark.parametrize("client", ["cursor", "vscode"])
def test_cli_dashboard_deeplinks_match_and_round_trip(tmp_path, monkeypatch, capsys, client):
    app = tmp_path / "O'Brien & spaces + Unicode \u96ea"
    python = app / "python" / "python.exe"
    python.parent.mkdir(parents=True)
    python.touch()
    args = ["--isolated-profile", str(tmp_path / "profile with spaces"), "--isolated-port", "5187"]
    monkeypatch.setattr(cli, "APP_DIR", app)
    monkeypatch.setattr(server, "HERE", app)
    monkeypatch.setattr(cli.isolation, "child_argv", lambda: args)
    monkeypatch.setattr(connect, "python_command", lambda _: python)
    assert cli.main(["connect", client, "--deeplink"]) == 0
    output = capsys.readouterr()
    assert "not yet tested" in output.err
    link = output.out.strip()
    assert link == server._mcp_config_payload()["install_links"][client]
    if client == "cursor":
        query = parse_qs(urlsplit(link).query)
        assert query["name"] == ["uoink"]
        entry = json.loads(base64.b64decode(query["config"][0]).decode("utf-8"))
        assert entry["env"]["UOINK_MCP_TOOLSET"] == "core"
    else:
        entry = json.loads(unquote(link.split("?", 1)[1]))
        assert entry.pop("name") == "uoink" and entry.pop("type") == "stdio"
    assert entry["command"] == str(python)
    assert entry["args"] == [str(app / "uoink_mcp.py"), *args]
    assert entry["env"] == ({"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
                            | ({"UOINK_MCP_TOOLSET": "core"} if client == "cursor" else {}))


def test_all_requested_recipes_are_in_the_single_table():
    assert {"warp", "junie", "amp", "roo", "kilo", "kilo-legacy", "cherry-studio", "jan",
            "librechat", "msty", "boltai", "continue", "raycast", "smithery-local", "windows-odr",
            "obsidian", "open-webui", "anythingllm", "lm-studio", "ollama", "n8n", "make", "zapier",
            "autohotkey", "powertoys", "alfred"} <= connect.CLIENTS.keys()
    for name in ("jan", "msty", "boltai", "continue", "open-webui", "anythingllm", "ollama"):
        assert "unverified" in connect.CLIENTS[name].note.lower()


@pytest.mark.parametrize("kind", ["file", "directory", "dangling", "root", "parent", "junction"])
def test_forced_skill_install_refuses_links_before_any_copy(tmp_path, kind):
    import os
    import subprocess
    parent = tmp_path / "skills"
    destination = parent / "uoink"
    destination.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "library-evidence.md"
    sentinel.write_text("leave this alone", encoding="utf-8")
    own = destination / "SKILL.md"
    own.write_text("keep before refusal", encoding="utf-8")
    link = destination / "references"
    target = outside
    if kind == "file":
        link.mkdir()
        link = link / sentinel.name
        target = sentinel
    elif kind == "dangling":
        target = outside / "missing"
    elif kind == "root":
        own.unlink()
        destination.rmdir()
        link = destination
    elif kind == "parent":
        parent = tmp_path / "linked-parent"
        link = parent
    if kind == "junction":
        if os.name != "nt":
            pytest.skip("Windows junction")
        quote = lambda p: "'" + str(p).replace("'", "''") + "'"
        subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                        f"New-Item -ItemType Junction -Path {quote(link)} -Target {quote(target)} | Out-Null"], check=True)
    else:
        try:
            link.symlink_to(target, target_is_directory=kind != "file")
        except OSError as exc:
            pytest.skip(f"symlink creation unavailable: {exc}")
    with pytest.raises(cli.UsageError, match="link or reparse point"):
        cli.install_skill(parent, force=True)
    assert sentinel.read_text(encoding="utf-8") == "leave this alone"
    assert not (outside / "SKILL.md").exists()
    if kind not in ("root", "parent"):
        assert own.read_text(encoding="utf-8") == "keep before refusal"


def test_skill_cannot_install_inside_its_source():
    with pytest.raises(cli.UsageError, match="separate"):
        cli.install_skill(cli.APP_DIR / "skills" / "uoink" / "nested", force=True)
