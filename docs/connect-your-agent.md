# Connect your agent to Uoink

Install [Uoink for Windows](https://github.com/ryanbiddy/uoink/releases/latest)
first. In the installer, leave **Add the uoink command to PATH for AI agents**
checked, then open a new terminal. The agent CLI described here ships with the
agent-reach build. In PowerShell, check the install:

```powershell
uoink status
uoink connect --list
```

If PATH is unavailable, run `& "$env:LOCALAPPDATA\Uoink\bin\uoink.cmd" status`
for a default install. For a custom install, use its `bin\uoink.cmd` instead.
Local library reads need neither a provider API key nor a running Uoink window.
Capture and paid tools keep their own requirements.

## MCP clients

Run the command in your row. It prints config with absolute paths for the copy
of Uoink being invoked. The file location and notes go to stderr; stdout holds
only the config or shell command. Merge the printed server entry into the
existing file, then restart the client's MCP connection. `connect` never edits
another app's files. For Claude Code, run the printed command in PowerShell.

These are offline configuration recipes. **Tested** records a real client
connection in this pass, not a syntax check or plugin validation.

| Client | Generate config | Where to use it | Tested |
|---|---|---|---|
| Claude Code | `uoink connect claude-code` | Run the printed `claude mcp add --scope user --transport stdio uoink ...` command; Claude manages `~/.claude.json`. | not yet |
| Claude Desktop | `uoink connect claude-desktop` | `%APPDATA%\Claude\claude_desktop_config.json`, under `mcpServers`. | not yet |
| Cursor | `uoink connect cursor` | `~/.cursor/mcp.json`, under `mcpServers`. Output sets `UOINK_MCP_TOOLSET=core` for its tool cap. | not yet |
| Codex | `uoink connect codex` | `~/.codex/config.toml`, the `[mcp_servers.uoink]` and environment tables. | not yet |
| Gemini CLI | `uoink connect gemini` | `~/.gemini/settings.json`, under `mcpServers`. | not yet |
| VS Code | `uoink connect vscode` | Project `.vscode/mcp.json`, under `servers`, with `type: stdio`. | not yet |
| Windsurf | `uoink connect windsurf` | `~/.codeium/windsurf/mcp_config.json`, under `mcpServers`. | not yet |
| Cline | `uoink connect cline` | Open **MCP Servers > Configure MCP Servers** and merge into `cline_mcp_settings.json`. The disk location varies by editor/profile. | not yet |
| Zed | `uoink connect zed` | `%APPDATA%\Zed\settings.json` on Windows; `~/.config/zed/settings.json` elsewhere, under `context_servers`. See uncertainty below. | not yet |
| Goose | `uoink connect goose` | `~/.config/goose/config.yaml`, under `extensions`. See uncertainty below. | not yet |
| OpenCode | `uoink connect opencode` | `~/.config/opencode/opencode.json` or project `opencode.json`, under `mcp`, with `type: local`. | not yet |
| LM Studio | `uoink connect lm-studio` | `~/.lmstudio/mcp.json`, under `mcpServers`. Confirm the path in MCP settings. | not yet |
| Hermes Agent | `uoink connect hermes` | `~/.hermes/config.yaml`, under `mcp_servers`. See uncertainty below. | not yet |

Goose and Hermes output uses JSON-form YAML, which is valid YAML 1.2. When
merging into an existing block-style YAML file, translate the same keys into
that style or use a YAML-aware editor. Do not append a separate JSON document.

Current formats could not be checked online in this pass. Specific uncertainty:
Zed's `command`/`args` shape versus its older nested command shape; Goose's
extension fields and config location; LM Studio's config location; and Hermes's
stdio `mcp_servers` fields. Cline's file location also varies. Each affected
recipe prints a note. Verify these against the installed client's settings.
All recipe choices live together in `uoink_connect.py` for easy correction.

## Agent Skills clients

The same skill works with MCP tools or the CLI. `uoink skill path` prints the
installed source folder. `skill install --to` takes the **parent skills
directory** and copies into its `uoink` subfolder, including references. It
refuses an existing folder unless you add `--force`.

Run these PowerShell commands on the Windows machine that holds the library.
`~` in the paths below means your home directory. Restart the agent or reload
its skills after installation.

| Agent | Skill install command | Tool access | Tested |
|---|---|---|---|
| Claude Code | `uoink skill install --to "$env:USERPROFILE\.claude\skills"` | `uoink connect claude-code`, or the plugin below. | not yet |
| Codex | `uoink skill install --to "$env:USERPROFILE\.agents\skills"` | `uoink connect codex`; CLI fallback. Older setups may also use `~/.codex/skills`. | not yet |
| pi | `uoink skill install --to "$env:USERPROFILE\.pi\agent\skills"` | CLI from its shell; no built-in MCP required. | not yet |
| Hermes Agent | `uoink skill install --to "$env:USERPROFILE\.hermes\skills"` | CLI, or `uoink connect hermes`. | not yet |
| OpenClaw | `uoink skill install --to "$env:USERPROFILE\.openclaw\skills"` | CLI from its shell. | not yet |

For an agent running elsewhere, install the skill in that agent's environment
and arrange local execution on the Uoink machine. A copied skill alone cannot
give a remote agent access to Windows files or commands.

The small [agent kit](../agent-kit/README.md) contains a Claude Code marketplace
and plain skill copies for pi, Hermes taps, and ClawHub packaging. Once the kit
is published as `ryanbiddy/uoink-agent-kit`, install the Claude Code plugin:

```powershell
claude plugin marketplace add ryanbiddy/uoink-agent-kit
claude plugin install uoink@uoink
```

The plugin bundles both the skill and stdio config. It uses
`${LOCALAPPDATA}\Uoink`, so custom installations should use `uoink connect
claude-code` plus the standalone skill instead. Avoid adding the same server
twice through a plugin and a manual MCP entry.

## CLI commands and tool mappings

```powershell
uoink search "working memory" --limit 5
uoink recent --limit 10
uoink get "ITEM_ID_FROM_SEARCH"
uoink note "A useful thought" --title "Research note"
uoink capture "https://example.com/article"
uoink tools --toolset full --json
uoink call search_library query="working memory" limit=5
uoink call search_library --args-file .\arguments.json
```

For the last command, `arguments.json` contains
`{"query":"working memory","limit":5}`. `--args` accepts the same JSON object
inline; shell quoting differs between PowerShell versions, so a file is easiest
for nested objects. Do not combine argument styles. `key=value` parses valid
JSON values and otherwise keeps a string. Duplicate keys and non-finite JSON
numbers are usage errors.

| Verb | Registry call |
|---|---|
| `search` | `search_library`, bounded results with stored evidence timing |
| `get` | `get_library_item(video_id=...)`; `--slug` selects by slug |
| `recent` | `list_recent_uoinks` |
| `note` | `uoink_note` |
| `capture` YouTube video / playlist | `uoink_video` / `uoink_playlist` |
| `capture` short video or X post | `uoink_url`, matching the extension's media route |
| `capture` Reddit thread | `uoink_reddit_thread` |
| `capture` feed-shaped podcast URL | `add_podcast_feed`, audio off by default |
| `capture` article, X article, or other page | `uoink_page`, with the existing allowlist checks |
| `status` | Local version, resolved data directory, process-identity helper check, and registry counts; no HTTP call |

Capture uses the existing URL classifier. A podcast episode page without a
feed-shaped URL becomes a page capture. X articles behind login may need the
extension's in-page capture. For explicit X text capture, use
`uoink call uoink_x url="URL"`; its default-off setting still applies.

Calls print one JSON envelope. Exit codes are 0 for `ok: true`, 1 for a tool
refusal/failure, and 2 for CLI usage errors. Errors also go to stderr.
`--text` gives a short human display. `tools` includes names and one-line
descriptions; `--json` also includes the same client schemas as stdio.
`connect` prints native config and `skill path` prints a path rather than an
envelope. `call` can invoke any registry tool, including tools outside `core`.

The CLI waits for capture workers started by its call, including playlist work,
podcast transcription, and capture follow-up analysis. This keeps a one-shot
process from abandoning daemon workers. It preserves the registry's envelope:
a returned job ID means the queue accepted the job. Use `get_job_status` to
inspect its final result, including failures. MCP sessions retain their usual
asynchronous behavior.

The original root `uoink.cmd` and POSIX `uoink` still run `server.py`, including
their existing HTTP search and maintenance commands. The new PATH command is
`{app}\bin\uoink.cmd`. Its no-argument behavior starts the helper;
`uoink serve` does the same, and `uoink serve --doctor` forwards the old CLI.
Use the new command's `search` for in-process library reads. An extensionless
`{app}\bin\uoink` shell launcher also serves Bash-based agents on Windows.

## Installer and receipt isolation

The checked PATH task appends `{app}\bin` to **User PATH** only if absent. It
preserves existing entries, ordering, and the registry value type. A small
ownership marker records an entry the installer added. Uninstall removes one
exact matching owned entry; it leaves pre-existing entries alone. New terminals
receive the change through Inno's `ChangesEnvironment=yes`.

With `/ISOLATED=1`, both installation and persisted isolated uninstallation
skip PATH handling before reading the registry value. Receipt installs already
pass `/ISOLATED=1`, `/NOCLOSEAPPLICATIONS`, `/NORESTARTAPPLICATIONS`, and
`/TASKS=""`. `scripts/install_receipt/agent_install.ps1` checks
`{app}\bin\uoink.cmd`, invokes that absolute path with
`--isolated-from-install-dir <app> status`, and requires the returned data
directory to match the receipt profile. It never depends on or changes real
User PATH. Static tests cover PATH ownership and removal; this pass does not
run an installer or claim a registry mutation test.
