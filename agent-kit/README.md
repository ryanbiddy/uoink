# Uoink agent kit

Uoink saves videos, podcasts, articles, posts, and notes on your disk. Agents
can search that library, quote returned evidence with timestamps, capture a
link, or save a note through MCP or the `uoink` CLI.

Install [Uoink for Windows](https://github.com/ryanbiddy/uoink/releases/latest)
first, with **Add the uoink command to PATH for AI agents** checked. Open a new
terminal and run `uoink status`. This kit contains instructions and MCP config;
it does not include Python, the app, or your library. The CLI requires the
3.10.0 release of Uoink or later.

## Claude Code

The marketplace at `ryanbiddy/uoink-agent-kit` is published with this release:

```powershell
claude plugin marketplace add ryanbiddy/uoink-agent-kit
claude plugin install uoink@uoink
```

Restart Claude Code and enable the plugin's Uoink MCP server when prompted.
The plugin includes the skill and launches the installed Python and
`uoink_mcp.py` under `${LOCALAPPDATA}\Uoink`. Claude Code expands that variable.
For a custom installation, use `uoink connect claude-code` and install the
standalone skill into `~/.claude/skills` instead of enabling the plugin.

## Codex, pi, Hermes Agent, and OpenClaw

Use the same skill folder in each agent. These PowerShell commands copy the
installed skill, including references, into the indicated home directory:

| Agent | Command | Access |
|---|---|---|
| Codex | `uoink skill install --to "$env:USERPROFILE\.agents\skills"` | MCP from `uoink connect codex`, or CLI. Older setups may use `~/.codex/skills`. |
| pi | `uoink skill install --to "$env:USERPROFILE\.pi\agent\skills"` | CLI; no built-in MCP needed. |
| Hermes Agent | `uoink skill install --to "$env:USERPROFILE\.hermes\skills"` | CLI, or `uoink connect hermes`. |
| OpenClaw | `uoink skill install --to "$env:USERPROFILE\.openclaw\skills"` | CLI. |

Restart the agent or reload its skills. `--to` names the parent directory;
the result is `<directory>/uoink/SKILL.md`. An existing copy needs `--force` to
overwrite. You can also copy this repo's entire `skills/uoink` folder to the
same location. That plain path is provided for Hermes `skills tap add`, pi
packages, and ClawHub packaging; tap/registry command syntax varies by version,
so check the installed harness's help before registering it.

The agent must be able to execute Uoink on the Windows machine holding the
library. Copying a skill into a remote environment does not expose local files.

## Other MCP clients

```powershell
uoink connect --list
uoink connect cursor
uoink connect codex
```

`connect` prints an absolute-path config and tells you where it belongs.
Merge the entry into your existing config and reconnect. It never edits other
apps' files. Cursor's recipe uses the smaller `core` toolset.

All client connections are **not yet tested** for this kit. JSON/TOML/YAML
syntax checks and local plugin validation do not prove client acceptance.
Zed's command shape, Goose's extension fields/location, LM Studio's location,
and Hermes's MCP fields need confirmation against the installed releases.
Cline's location varies by editor/profile. The affected recipes print notes.

Use this table to choose the MCP config, skill, plugin or CLI path. Every row
is **not yet tested** in the named client. Full recipes and limits are in
[`docs/connect-your-agent.md`](https://github.com/ryanbiddy/uoink/blob/main/docs/connect-your-agent.md).
The generator keeps all client choices in one table in `uoink_connect.py`.

| Harness | Path and format |
|---|---|
| Claude Code | Plugin: `plugins/uoink` via `.claude-plugin/marketplace.json`. Standalone skill: `~/.claude/skills/uoink/`. MCP: `claude mcp add` manages `~/.claude.json`. |
| Claude Desktop | `%APPDATA%/Claude/claude_desktop_config.json`, JSON `mcpServers`; or the separate MCPB bundle. |
| Codex | `~/.codex/config.toml`, `mcp_servers`; skill `~/.agents/skills/uoink/` (older setups: `~/.codex/skills/uoink/`). |
| Gemini CLI | `~/.gemini/settings.json`, JSON `mcpServers`. |
| Cursor | `~/.cursor/mcp.json`, JSON `mcpServers`; `uoink connect cursor --deeplink`, core toolset. |
| VS Code | Project `.vscode/mcp.json`, JSON `servers` with stdio type; `uoink connect vscode --deeplink`. |
| Windsurf | `~/.codeium/windsurf/mcp_config.json`, JSON `mcpServers`. |
| Cline | MCP settings opens `cline_mcp_settings.json`, JSON `mcpServers`; editor/profile decides the directory. |
| Warp | `~/.warp/.mcp.json` or project `.warp/.mcp.json`, JSON `mcpServers`. |
| JetBrains Junie | `~/.junie/mcp/mcp.json` or project `.junie/mcp/mcp.json`, JSON `mcpServers`; AI Assistant's JSON import is unverified. |
| Amp | `%APPDATA%/amp/settings.json` or `~/.config/amp/settings.json`; project `.amp/settings.json` needs approval. JSON `amp.mcpServers`. |
| Roo Code | `.roo/mcp.json`, or global `mcp_settings.json` via MCP settings; JSON `mcpServers`. |
| Kilo Code | Newer: `~/.config/kilo/kilo.jsonc` or project `kilo.jsonc`, `mcp` local command array. Older: `.kilocode/mcp.json` or global `mcp_settings.json`, `mcpServers`. Both recipes ship; choose the installed format. |
| Zed | Windows `%APPDATA%/Zed/settings.json`, elsewhere `~/.config/zed/settings.json`; `context_servers`. Command shape unverified. |
| Goose | `~/.config/goose/config.yaml`, `extensions`; fields/path unverified. |
| OpenCode | `~/.config/opencode/opencode.json` or project `opencode.json`, `mcp` local command array. |
| Continue | `~/.continue/config.yaml` or `.continue/mcpServers/uoink.yaml`, YAML `mcpServers` list; unverified. |
| Cherry Studio | Settings > MCP Server > STDIO / Import from JSON, `mcpServers`; no file path established. |
| Jan / Msty / BoltAI | Jan MCP Servers UI / Msty Toolbox MCP Tools / BoltAI MCP JSON import; candidate `mcpServers`, paths not established, unverified. BoltAI is Mac-later. |
| LibreChat | App's `librechat.yaml`, `mcpServers` with stdio type; same PC, accessible host paths. |
| LM Studio | Candidate `~/.lmstudio/mcp.json`, `mcpServers`; confirm path in MCP settings. |
| Open WebUI | Candidate mcpo JSON file selected with `--config`, then tool-server UI; unverified, including native MCP support. |
| AnythingLLM | Desktop MCP UI; candidate `storage/plugins/anythingllm_mcp_servers.json`, `mcpServers`; storage root/schema unverified. |
| Ollama-based clients | MCP-capable client's config/UI, candidate `mcpServers`; client-specific and unverified. Ollama itself is only the runtime. |
| Raycast MCP | AI MCP settings with command/args/env; no file path established. JSON import and Windows availability unverified. |
| Smithery local | Future `smithery.yaml` at kit root. Deferred: research gives `target: local` but no complete local stdio format. |
| Windows On-Device Agent Registry | Local MCPB `manifest.json` via `odr.exe mcp add`; preview, build 26220+ (research cites 26220.7262+), exact local flag unverified. Documentation only; never run by installer. |
| pi | `~/.pi/agent/skills/uoink/`; CLI. Kit `skills/uoink/` can be packaged. |
| Hermes Agent | `~/.hermes/skills/uoink/`; CLI or `~/.hermes/config.yaml` `mcp_servers` (unverified). Kit `skills/uoink/` for taps. |
| OpenClaw / ClawHub | `~/.openclaw/skills/uoink/`; CLI. Kit `skills/uoink/` for ClawHub packaging. |
| Obsidian | Uoink Settings > Library > Library Mirror exports Markdown to `<vault>/Uoink/`. No MCP plugin was named in the research. |
| n8n self-hosted | Same-PC HTTP Request node, `/memory/search` with `X-Uoink-Token` in credentials. |
| Make / Zapier | Cloud runners cannot reach this PC's loopback; no remote HTTPS recipe. |
| AutoHotkey / PowerToys Command Palette | User `.ahk` script / command or shortcut settings calling `{app}/cli/uoink.cmd`. PowerToys UI route unverified. |
| Alfred | macOS workflow Run Script calling `uoink`; Mac-later. |

ChatGPT developer mode, claude.ai web and Notion AI remote connectors are
skipped. A local skill or config file does not make a cloud runner local.

## Layout and maintenance

```text
.claude-plugin/marketplace.json
plugins/uoink/.claude-plugin/plugin.json
plugins/uoink/.mcp.json
plugins/uoink/skills/uoink/
skills/uoink/
```

The two skill folders are generated copies. In the main Uoink repository, edit
`skills/uoink`, run `python scripts/build_agent_kit.py`, then run
`python scripts/build_agent_kit.py --check`. The test suite fails on drift.
The same script sets the plugin version from `VERSION`; `--check` fails if it drifts.

Before publication, run locally:

```powershell
claude plugin validate ./agent-kit
claude plugin validate ./agent-kit/plugins/uoink
```
