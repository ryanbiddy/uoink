# Uoink agent kit

Uoink saves videos, podcasts, articles, posts, and notes on your disk. Agents
can search that library, quote returned evidence with timestamps, capture a
link, or save a note through MCP or the `uoink` CLI.

Install [Uoink for Windows](https://github.com/ryanbiddy/uoink/releases/latest)
first, with **Add the uoink command to PATH for AI agents** checked. Open a new
terminal and run `uoink status`. This kit contains instructions and MCP config;
it does not include Python, the app, or your library. The CLI requires the
agent-reach build of Uoink.

## Claude Code

After this kit is published as `ryanbiddy/uoink-agent-kit`:

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
The plugin's `0.0.0` version is a placeholder for the release process.

Before publication, run locally:

```powershell
claude plugin validate ./agent-kit
claude plugin validate ./agent-kit/plugins/uoink
```
