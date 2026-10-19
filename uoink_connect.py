"""Print-only agent connection recipes. Keep format and location choices in one table.

These are offline templates, not claims of client acceptance. JSON is also valid
YAML 1.2, so YAML clients receive a JSON-form YAML document without a dependency.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import base64
import json
import os
from pathlib import Path
import shlex
import sys
from urllib.parse import quote, urlencode


@dataclass(frozen=True)
class Client:
    format: str
    location: str
    shape: str = "mcpServers"
    note: str = ""
    guide: str = ""


CLIENTS = {
    "claude-code": Client("shell", "~/.claude.json (managed by claude mcp add)", "command"),
    "claude-desktop": Client("json", "%APPDATA%/Claude/claude_desktop_config.json"),
    "cursor": Client("json", "~/.cursor/mcp.json", note="Uses UOINK_MCP_TOOLSET=core for Cursor's tool cap."),
    "codex": Client("toml", "~/.codex/config.toml", "mcp_servers"),
    "gemini": Client("json", "~/.gemini/settings.json"),
    "vscode": Client("json", ".vscode/mcp.json", "servers"),
    "windsurf": Client("json", "~/.codeium/windsurf/mcp_config.json"),
    "cline": Client("json", "Cline > MCP Servers > Configure MCP Servers (cline_mcp_settings.json)",
                    note="Config file location varies by editor/profile; use Cline's config button."),
    "zed": Client("json", "~/.config/zed/settings.json (Windows: %APPDATA%/Zed/settings.json)",
                  "context_servers", "Uncertain: this uses command/args; older Zed versions use a nested command. Verify in your installed Zed."),
    "goose": Client("yaml", "~/.config/goose/config.yaml", "extensions",
                    "Uncertain: Goose extension fields and config location vary by release; verify with goose configure."),
    "opencode": Client("json", "~/.config/opencode/opencode.json (or project opencode.json)", "mcp"),
    "lm-studio": Client("json", "~/.lmstudio/mcp.json",
                        note="Uncertain: confirm mcp.json location in your LM Studio MCP settings."),
    "hermes": Client("yaml", "~/.hermes/config.yaml", "mcp_servers",
                     "Uncertain: verify mcp_servers stdio fields against your installed Hermes Agent release."),
    "warp": Client("json", "~/.warp/.mcp.json or project .warp/.mcp.json"),
    "junie": Client("json", "~/.junie/mcp/mcp.json or project .junie/mcp/mcp.json",
                    note="Junie recipe. AI Assistant JSON import is unverified in the research."),
    "amp": Client("json", "%APPDATA%/amp/settings.json or ~/.config/amp/settings.json; project .amp/settings.json",
                  "amp.mcpServers", "Workspace config needs client approval. Paths are from secondary research."),
    "roo": Client("json", ".roo/mcp.json or global mcp_settings.json via Roo's MCP settings"),
    "kilo": Client("jsonc", "~/.config/kilo/kilo.jsonc or project kilo.jsonc", "mcp",
                   "Newer Kilo format. Research found conflicting generations; choose the one your installed client uses."),
    "kilo-legacy": Client("json", ".kilocode/mcp.json or global mcp_settings.json via Kilo's MCP settings",
                          note="Older Kilo extension format; do not combine it with kilo.jsonc."),
    "cherry-studio": Client("json", "Settings > MCP Server > Add > STDIO / Import from JSON (no file path established)"),
    "jan": Client("json", "Settings > MCP Servers > Add (no file path established)",
                  note="Unverified in the research: confirm JSON import or enter command, args and env in the UI."),
    "librechat": Client("yaml", "librechat.yaml beside the self-hosted LibreChat app", "mcpServers",
                        "Run on this PC with access to these paths; Docker/container localhost and paths differ."),
    "msty": Client("json", "Toolbox > MCP Tools > JSON (no file path established)",
                   note="Unverified in the research: confirm fields in your installed Msty."),
    "boltai": Client("json", "BoltAI MCP settings / JSON import (macOS; no file path established)",
                     note="Unverified in the research. Mac-later: the current Uoink installer is Windows-only."),
    "continue": Client("yaml", "~/.continue/config.yaml or .continue/mcpServers/uoink.yaml", "list",
                       "Unverified in the research: mcpServers list, agent mode; check the installed schema before merging."),
    "raycast": Client("json", "Raycast AI > MCP settings (no config file path established)",
                      note="Local stdio is documented in the research; JSON import and Windows availability are unverified. Enter command/args/env if needed."),
    "open-webui": Client("json", "Local mcpo --config <chosen-config.json>; Open WebUI tool-server settings",
                         note="Unverified: the supplied research did not verify Open WebUI's native MCP or mcpo. This is a candidate mcpo stdio config; confirm with the installed bridge. Keep mcpo on loopback and authenticate it."),
    "anythingllm": Client("json", "AnythingLLM Desktop MCP settings; candidate storage/plugins/anythingllm_mcp_servers.json",
                          note="Unverified: not covered by the supplied research. Confirm the storage root and schema in your installed client."),
    "ollama": Client("json", "MCP-capable Ollama client settings (client-specific file or JSON import)",
                     note="Unverified client route. Ollama itself is the model runtime, not an MCP client. Use a tool-capable client and model on this PC."),
    "smithery-local": Client("text", "agent-kit/smithery.yaml (deferred until local schema is confirmed)",
                             note="Unverified local stdio schema; research only establishes target: local from a secondary source.",
                             guide="Smithery local: the research gives target: local but no command/args schema.\nNo smithery.yaml is shipped. Confirm the local stdio schema first, then use:\n<ENTRY>\nDo not publish this private install path or select remote hosting."),
    "windows-odr": Client("text", ".mcpb/manifest.json from the Uoink bundle; Windows ODR registration",
                          note="Preview, not yet tested. Windows build 26220 or later; research cites 26220.7262+. Local manifest argument syntax is unverified.",
                          guide="Documentation only. Inspect odr.exe mcp add --help on a supported Windows build,\nthen use odr.exe mcp add with the local .mcpb/manifest.json and the manifest\noption shown by that build. The research only supplies --uri for remote servers;\ndo not use that remote route. Uoink's installer never runs ODR."),
    "obsidian": Client("text", "Uoink Settings > Library > Library Mirror; destination is your vault folder",
                       guide="Choose the vault root, select all items or an item-ID allowlist, Preview, then\nselect Enable to confirm. Uoink writes evidence cards, shelf pages and accepted\nbriefs under <vault>/Uoink/. This is an opt-in one-way export, not full-media or\ntwo-way sync. The research names no MCP-capable Obsidian plugin; no plugin recipe is claimed."),
    "n8n": Client("text", "Self-hosted n8n HTTP Request node on the Uoink PC (workflow UI)",
                  guide="GET http://127.0.0.1:5179/memory/search?q=memory&limit=5\nHeader: X-Uoink-Token: <your local token, stored in n8n credentials>\nUse the configured port if different. Never put the token in a URL, workflow\nexport, chat, or log. Containers and other machines have their own localhost.\nCloud n8n, Make and Zapier cannot reach this PC's 127.0.0.1."),
    "make": Client("text", "No local recipe for Make cloud runners",
                   guide="Make cloud runners cannot reach Uoink's 127.0.0.1. Remote HTTPS/tunnels are skipped.\nUse uoink connect n8n for same-PC self-hosted automation."),
    "zapier": Client("text", "No local recipe for Zapier cloud runners",
                     guide="Zapier cloud runners cannot reach Uoink's 127.0.0.1. Remote HTTPS/tunnels are skipped.\nUse uoink connect n8n for same-PC self-hosted automation."),
    "autohotkey": Client("text", "A user-created .ahk file (AutoHotkey v2)",
                         guide='#Requires AutoHotkey v2.0\n^!u::Run(\'"<CLI>" search "working memory" --text\')'),
    "powertoys": Client("text", "PowerToys Command Palette > command/shortcut settings (release-dependent)",
                        note="Unverified in the research: confirm command support in your installed version.",
                        guide='Configure a command or shortcut target as "<CLI>" with arguments:\nsearch "working memory" --text\nThis launches the CLI. It does not add inline search results or an extension.'),
    "alfred": Client("text", "Alfred workflow > Run Script (macOS)",
                     guide='Mac-later: Uoink currently ships for Windows. A future local Mac install could\nuse this fixed Run Script action: uoink search "working memory" --text\nDo not pass unquoted clipboard or query text into a shell.'),
}


def client_spec(client: str) -> Client:
    spec = CLIENTS[client]
    if sys.platform == "darwin":
        if client == "claude-desktop":
            return replace(spec, location=str(Path.home() / "Library/Application Support/Claude/claude_desktop_config.json"))
        if client in {"cursor", "codex"}:
            return replace(spec, location=str(Path(spec.location).expanduser()))
        if client == "boltai":
            return replace(spec, note="Unverified: confirm JSON import in your installed BoltAI.")
        if client == "alfred":
            return replace(spec, guide='Use a fixed Run Script action: uoink search "working memory" --text\nDo not pass unquoted clipboard or query text into a shell.')
    return spec


def bundle_resources(app_dir: Path) -> Path | None:
    if sys.platform != "darwin":
        return None
    app_dir = app_dir.resolve()
    if app_dir.suffix == ".app":
        return app_dir / "Contents/Resources"
    if app_dir.name == "Resources" and app_dir.parent.name == "Contents" and app_dir.parent.parent.suffix == ".app":
        return app_dir
    return None


def python_command(app_dir: Path) -> Path:
    resources = bundle_resources(app_dir)
    if resources is not None:
        bundled = resources.parent / "Frameworks/Python/bin/python3"
        if not bundled.is_file() or not (resources / "uoink_mcp.py").is_file():
            raise FileNotFoundError(f"Uoink installation is incomplete at {resources.parent.parent}. Reinstall Uoink.app from the DMG.")
        # Keep the documented bin/python3 launch path even if it is a symlink.
        return bundled
    bundled = app_dir / "python" / ("python.exe" if sys.platform == "win32" else "bin/python3")
    return (bundled if bundled.is_file() else Path(sys.executable)).resolve()


def server_entry(client: str, app_dir: Path, python: Path, isolation_args=()) -> dict:
    command = str(python.resolve())
    args = [str((app_dir / "uoink_mcp.py").resolve()), *isolation_args]
    if sys.platform == "darwin":
        resources = bundle_resources(app_dir) or app_dir.resolve()
        command = str(python_command(resources))
        args = ["-B", "-s", str(resources / "uoink_mcp.py"), *isolation_args]
    env = {"PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    if client == "cursor":
        env["UOINK_MCP_TOOLSET"] = "core"
    return {"command": command, "args": args, "env": env}


def deeplink(client: str, app_dir: Path, python: Path, isolation_args=()) -> str:
    entry = server_entry(client, app_dir, python, isolation_args)
    if client == "cursor":
        config = base64.b64encode(json.dumps(entry, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).decode("ascii")
        return "cursor://anysphere.cursor-deeplink/mcp/install?" + urlencode({"name": "uoink", "config": config})
    if client == "vscode":
        return "vscode:mcp/install?" + quote(json.dumps({"name": "uoink", "type": "stdio", **entry}, ensure_ascii=False, separators=(",", ":")), safe="")
    raise ValueError("deeplinks require cursor or vscode")


def render(client: str, app_dir: Path, python: Path, isolation_args=()) -> str:
    spec = client_spec(client)
    entry = server_entry(client, app_dir, python, isolation_args)
    command, args, env = entry["command"], entry["args"], entry["env"]
    if spec.format == "text":
        launcher = str((app_dir / "cli" / "uoink.cmd").resolve())
        if client == "autohotkey":
            launcher = launcher.replace("`", "``").replace("'", "`'")
        return spec.guide.replace("<ENTRY>", json.dumps(entry, indent=2, ensure_ascii=False)).replace("<CLI>", launcher)
    if spec.format == "shell":
        # PowerShell single quotes preserve spaces, $, backticks and apostrophes.
        quote = (lambda s: "'" + s.replace("'", "''") + "'") if os.name == "nt" else shlex.quote
        return ("claude mcp add --scope user --transport stdio uoink "
                "-e PYTHONIOENCODING=utf-8 -e PYTHONUTF8=1 -- "
                + " ".join(quote(s) for s in [command, *args]))
    if spec.format == "toml":
        return ("[mcp_servers.uoink]\ncommand = " + json.dumps(command, ensure_ascii=False)
                + "\nargs = " + json.dumps(args, ensure_ascii=False)
                + "\n\n[mcp_servers.uoink.env]\n"
                + "\n".join(f"{key} = {json.dumps(value)}" for key, value in env.items()))
    if spec.shape == "list":
        return json.dumps({"mcpServers": [{"name": "uoink", **entry}]}, indent=2, ensure_ascii=False)
    if spec.shape == "servers" or client == "librechat":
        entry = {"type": "stdio", **entry}
    elif spec.shape == "extensions":
        entry = {"name": "uoink", "type": "stdio", "enabled": True,
                 "cmd": command, "args": args, "envs": env, "timeout": 300}
    elif spec.shape == "mcp":
        entry = {"type": "local", "command": [command, *args],
                 "environment": env, "enabled": True}
    return json.dumps({spec.shape: {"uoink": entry}}, indent=2, ensure_ascii=False)
