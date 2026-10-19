"""Print-only MCP client recipes. Keep format and location choices in one table.

These are offline templates, not claims of client acceptance. JSON is also valid
YAML 1.2, so YAML clients receive a JSON-form YAML document without a dependency.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import shlex


@dataclass(frozen=True)
class Client:
    format: str
    location: str
    shape: str = "mcpServers"
    note: str = ""


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
}


def render(client: str, app_dir: Path, python: Path, isolation_args=()) -> str:
    spec = CLIENTS[client]
    command = str(python.resolve())
    args = [str((app_dir / "uoink_mcp.py").resolve()), *isolation_args]
    env = {"PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    if client == "cursor":
        env["UOINK_MCP_TOOLSET"] = "core"
    entry = {"command": command, "args": args, "env": env}
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
    if spec.shape == "servers":
        entry = {"type": "stdio", **entry}
    elif spec.shape == "extensions":
        entry = {"name": "uoink", "type": "stdio", "enabled": True,
                 "cmd": command, "args": args, "envs": env, "timeout": 300}
    elif spec.shape == "mcp":
        entry = {"type": "local", "command": [command, *args],
                 "environment": env, "enabled": True}
    return json.dumps({spec.shape: {"uoink": entry}}, indent=2, ensure_ascii=False)
