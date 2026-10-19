# Connect your agent to Uoink

Install [Uoink for Windows](https://github.com/ryanbiddy/uoink/releases/latest)
first. In the installer, leave **Add the uoink command to PATH for AI agents**
checked, then open a new terminal. The agent CLI ships with Uoink 3.10.0.
In PowerShell, check the install:

```powershell
uoink status
uoink connect --list
```

If PATH is unavailable, run `& "$env:LOCALAPPDATA\Uoink\cli\uoink.cmd" status`
for a default install. For a custom install, use its `cli\uoink.cmd` instead.
Local library reads need neither a provider API key nor a running Uoink window.
Capture and paid tools keep their own requirements.

## MCP clients

Run the command in your row. It prints config with absolute paths for the copy
of Uoink being invoked. The file location and notes go to stderr; stdout holds
only the config or shell command. Merge the printed server entry into the
existing file, then restart the client's MCP connection. `connect` never edits
another app's files. For Claude Code, run the printed command in PowerShell.

Every recipe here is **not yet tested** in its client. Parsing config and
validating a plugin do not prove that a client accepts it. The supplied
October 18/19 research used search snippets, not full primary-page review.
**Unverified** below means the research marked the detail unverified or did
not cover it. UI-only clients have no established file path in that research;
use their import form or enter the printed command, arguments and environment.

| Client | Generate config | Location and format | Status |
|---|---|---|---|
| Claude Code | `uoink connect claude-code` | Run the printed `claude mcp add --scope user --transport stdio uoink ...` command; Claude manages `~/.claude.json`. | not yet tested |
| Claude Desktop | `uoink connect claude-desktop` | `%APPDATA%\Claude\claude_desktop_config.json`, under `mcpServers`. | not yet tested |
| Cursor | `uoink connect cursor` | `~/.cursor/mcp.json`, under `mcpServers`. Output sets `UOINK_MCP_TOOLSET=core` for its tool cap. | not yet tested |
| Codex | `uoink connect codex` | `~/.codex/config.toml`, the `[mcp_servers.uoink]` and environment tables. | not yet tested |
| Gemini CLI | `uoink connect gemini` | `~/.gemini/settings.json`, under `mcpServers`. | not yet tested |
| VS Code | `uoink connect vscode` | Project `.vscode/mcp.json`, under `servers`, with `type: stdio`. | not yet tested |
| Windsurf | `uoink connect windsurf` | `~/.codeium/windsurf/mcp_config.json`, under `mcpServers`. | not yet tested |
| Cline | `uoink connect cline` | Open **MCP Servers > Configure MCP Servers** and merge into `cline_mcp_settings.json`. The disk location varies by editor/profile. | not yet tested |
| Zed | `uoink connect zed` | `%APPDATA%\Zed\settings.json` on Windows; `~/.config/zed/settings.json` elsewhere, under `context_servers`. See uncertainty below. | not yet tested |
| Goose | `uoink connect goose` | `~/.config/goose/config.yaml`, under `extensions`. See uncertainty below. | not yet tested |
| OpenCode | `uoink connect opencode` | `~/.config/opencode/opencode.json` or project `opencode.json`, under `mcp`, with `type: local`. | not yet tested |
| LM Studio | `uoink connect lm-studio` | `~/.lmstudio/mcp.json`, under `mcpServers`. Confirm the path in MCP settings. | not yet tested |
| Hermes Agent | `uoink connect hermes` | `~/.hermes/config.yaml`, under `mcp_servers`. See uncertainty below. | not yet tested |
| Warp | `uoink connect warp` | `~/.warp/.mcp.json` or project `.warp/.mcp.json`; JSON `mcpServers`. | not yet tested |
| JetBrains Junie | `uoink connect junie` | `~/.junie/mcp/mcp.json` or project `.junie/mcp/mcp.json`; JSON `mcpServers`. AI Assistant's Settings > Tools > AI Assistant > MCP JSON import is a separate, unverified route. | not yet tested |
| Amp | `uoink connect amp` | Windows `%APPDATA%/amp/settings.json`, elsewhere `~/.config/amp/settings.json`; JSON `amp.mcpServers`. Project `.amp/settings.json` needs client approval. Paths come from secondary research. | not yet tested |
| Roo Code | `uoink connect roo` | Project `.roo/mcp.json` or global `mcp_settings.json` opened from Roo's MCP settings; JSON `mcpServers`. | not yet tested |
| Kilo Code, newer | `uoink connect kilo` | `~/.config/kilo/kilo.jsonc` or project `kilo.jsonc`; `mcp.uoink`, `type: local`, command array and `environment`. | not yet tested; conflicting doc generations |
| Kilo Code, older | `uoink connect kilo-legacy` | Project `.kilocode/mcp.json` or global `mcp_settings.json` opened from Kilo's MCP settings; JSON `mcpServers`. Choose one format for your installed version. | not yet tested; conflicting doc generations |
| Cherry Studio | `uoink connect cherry-studio` | Settings > MCP Server > Add > STDIO or Import from JSON; `mcpServers`. No file path established. | not yet tested |
| Jan | `uoink connect jan` | Settings > MCP Servers > Add; candidate JSON `mcpServers` or enter the fields. No file path established. | not yet tested; unverified |
| LibreChat | `uoink connect librechat` | App's `librechat.yaml`; `mcpServers.uoink` with `type: stdio`. Run on this PC with access to the printed paths. | not yet tested; secondary research |
| Msty | `uoink connect msty` | Toolbox > MCP Tools > JSON; candidate `mcpServers`. No file path established. | not yet tested; unverified |
| BoltAI | `uoink connect boltai` | macOS app's MCP JSON import; candidate `mcpServers`. No file path established. Mac-later for Uoink. | not yet tested; unverified |
| Continue | `uoink connect continue` | `~/.continue/config.yaml` or `.continue/mcpServers/uoink.yaml`; YAML `mcpServers` list with `name`, `command`, `args`, `env`. Use agent mode; check the installed schema. | not yet tested; unverified |
| Raycast MCP | `uoink connect raycast` | Raycast AI MCP settings; command, args and env, or candidate JSON `mcpServers` import. No file path established. Research supports local stdio; import format and Windows availability remain unverified. | not yet tested |
| Open WebUI | `uoink connect open-webui` | Candidate local mcpo JSON config passed with `--config <chosen-config.json>`, then Open WebUI tool-server settings. See below. | not yet tested; unverified |
| AnythingLLM | `uoink connect anythingllm` | Desktop MCP settings; candidate `storage/plugins/anythingllm_mcp_servers.json` under its storage root, JSON `mcpServers`. Confirm the path in the installed app. | not yet tested; unverified |
| Ollama-based clients | `uoink connect ollama` | The MCP-capable client's own file or JSON import, candidate `mcpServers`; Ollama itself has no MCP client config. | not yet tested; client-specific, unverified |
| Smithery local | `uoink connect smithery-local` | Text guidance for a future `agent-kit/smithery.yaml`. Research supplies `target: local` but no complete stdio schema, so no manifest is shipped. | not yet tested; schema unverified |
| Windows On-Device Agent Registry | `uoink connect windows-odr` | Text guidance for `odr.exe mcp add` from a local MCPB `manifest.json`; see preview limits below. | not yet tested; local argument syntax unverified |
| Obsidian | `uoink connect obsidian` | Text guidance for Settings > Library > Library Mirror; writes Markdown into `<vault>/Uoink/`. | not yet tested in Obsidian |
| n8n self-hosted | `uoink connect n8n` | HTTP Request node on this PC; local HTTP API with `X-Uoink-Token`. | not yet tested |
| Make / Zapier | `uoink connect make` / `uoink connect zapier` | Text explanation only. Cloud runners cannot reach this PC's loopback API. | not yet tested; cloud route skipped |
| AutoHotkey v2 | `uoink connect autohotkey` | A user-created `.ahk` script calling the absolute `cli/uoink.cmd` path. | not yet tested |
| PowerToys Command Palette | `uoink connect powertoys` | Command/shortcut settings, where supported, calling `cli/uoink.cmd`; no extension or inline results. | not yet tested; UI route unverified |
| Alfred | `uoink connect alfred` | macOS workflow Run Script action calling the CLI; Mac-later. | not yet tested |

Goose, Hermes, Continue and LibreChat output uses JSON-form YAML, valid YAML 1.2. When
merging into an existing block-style YAML file, translate the same keys into
that style or use a YAML-aware editor. Do not append a separate JSON document.

Current formats could not be checked online in this pass. Specific uncertainty:
Zed's `command`/`args` shape versus its older nested command shape; Goose's
extension fields and config location; LM Studio's config location; and Hermes's
stdio `mcp_servers` fields. Cline's file location also varies. Each affected
recipe prints a note. Verify these against the installed client's settings.
All recipe choices live together in `uoink_connect.py` for easy correction.

## Cursor and VS Code install links

In **Settings > Agents (MCP) > Agent connection**, choose **Add to Cursor** or
**Add to VS Code**. Each button opens the installed client's review flow using
this Uoink install's absolute Python and stdio script paths. Cursor receives
the `core` toolset. The links contain only paths, isolation arguments when
active, and the UTF-8/toolset environment settings. They contain no API token.

The same links are available without opening a client:

```powershell
uoink connect cursor --deeplink
uoink connect vscode --deeplink
```

Both commands only print. The dashboard builds the links locally through its
existing authenticated config endpoint. Clicking makes no HTTP request and
does not write client config. The client decides whether to install the server;
Uoink cannot detect completion or whether a URL handler is installed. Buttons
stay disabled if config loading fails. Client acceptance is not yet tested.

## Local-model apps and preview registries

LM Studio, Jan, Cherry Studio, Msty and MCP-capable Ollama clients can use the
same local stdio process where their client supports it. The model also needs
tool-calling support. Ollama supplies a model runtime, not the client connection.
The handoff did not verify Open WebUI or AnythingLLM. Open WebUI's printed
recipe is a candidate **mcpo** bridge config; native MCP support was not verified.
Check the installed bridge before using it, bind it only to loopback and use
its authentication. A bridge running in Docker or on another PC cannot use
these Windows paths or treat its own `127.0.0.1` as the Uoink PC.

Windows On-Device Agent Registry is a **preview** needing Windows build 26220
or later; the research cites **26220.7262+**. Its local route consumes the
MCPB manifest from the bundle (`.mcpb/manifest.json` in the source tree). On a
supported build, inspect `odr.exe mcp add --help`, then use `odr.exe mcp add`
with the local manifest option shown there. The handoff did not establish that
option's spelling; `--uri` was documented only for remote servers. Do not treat
the source manifest's bundle-relative paths as a standalone executable package.
Registration and bundle acceptance are not yet tested. The installer never
runs `odr.exe`.

Smithery's secondary research mentions `target: local` but gives no complete
local stdio schema. `connect smithery-local` prints the local command details
and this limit. A `smithery.yaml` is deferred until that format is confirmed.
Uoink does not configure remote hosting, publish a listing, or expose a tunnel.
The research lists ChatGPT developer mode, claude.ai web connectors and Notion
AI as remote routes (the Notion detail is unverified). They are skipped for
this local-only integration.

## Obsidian vault mirror

Open **Settings > Library > Library Mirror**, enter the vault's root folder,
and choose **All current and future items** or **Allowlist only** with item IDs.
Select **Preview**, review the counts, then select **Enable** as confirmation.
The mirror is off by default. The backend stores `library_mirror_enabled` and
`library_mirror_consent` with destination, scope and allowlist. Enabling or
broadening scope requires the dashboard's preview and intent flow; changing
settings directly is not a substitute.

`library_mirror.py` writes a one-way generated view under `<vault>/Uoink/`:
evidence cards, shelf pages and accepted briefs. It does not copy the full media
library, read vault edits back, or sync Obsidian settings. **Resync** processes
bounded work; pending or stale counts can remain. The default batch is 20 files
with a two-second work budget, and individual files are capped at 64 KiB.
Conflicting user edits, unmanaged files and redirected paths can block writes
or deletions. **Disable** stops the mirror; it does not erase previously
exported files. Third-party indexes and synced copies remain outside Uoink's
deletion control.

The older `obsidian_vault_path` setting mirrors only `TASTE.md` and `USER.md`.
It is separate from Library Mirror and does not enable corpus export. No
Obsidian client connection was tested here. The research names no existing
MCP-capable Obsidian plugin, so there is no claimed plugin recipe. If you choose
one separately, verify that it can launch local stdio and use the printed
command/args/env; installing the mirror does not install an MCP plugin.

## Local automation and launchers

Only **self-hosted n8n on the same PC**, with access to the host loopback
interface, fits this recipe. In an HTTP Request node, use this existing read
endpoint from [the API reference](v2-api.md#get-memorysearch):

```http
GET http://127.0.0.1:5179/memory/search?q=memory&limit=5
X-Uoink-Token: <your local token>
```

Use your configured port if different. Store the token in n8n's credentials,
not in a URL, copied workflow JSON, chat or logs. Treat it as access to your
local library. This example was not sent during verification. Cloud n8n, Make,
Zapier and Pipedream cannot reach the PC's `127.0.0.1`; remote HTTPS bridges and
tunnels are skipped. Containers have their own loopback interface too.

For AutoHotkey v2, `uoink connect autohotkey` prints a `.ahk` hotkey with this
install's absolute launcher path. Its fixed action is:

```autohotkey
#Requires AutoHotkey v2.0
^!u::Run('uoink search "working memory" --text')
```

In PowerToys Command Palette, where your release supports a command or shortcut,
set its executable to the installed `cli/uoink.cmd` and arguments to
`search "working memory" --text`. This starts a CLI process; it does not provide
inline search results. That UI route is unverified. Alfred is Mac-later: a
future local Mac install could use a workflow Run Script action with
`uoink search "working memory" --text`. All three recipes are not yet tested.
Keep user-supplied queries out of shell command strings unless correctly quoted.

## Agent Skills clients

The same skill works with MCP tools or the CLI. `uoink skill path` prints the
installed source folder. `skill install --to` takes the **parent skills
directory** and copies into its `uoink` subfolder, including references. It
refuses an existing folder unless you add `--force`. Even with `--force`, it
refuses symlinks and Windows reparse points in the destination or its parents.
Remove the link yourself or choose a separate ordinary directory.

Run these PowerShell commands on the Windows machine that holds the library.
`~` in the paths below means your home directory. Restart the agent or reload
its skills after installation.

| Agent | Skill install command | Tool access | Tested |
|---|---|---|---|
| Claude Code | `uoink skill install --to "$env:USERPROFILE\.claude\skills"` | `uoink connect claude-code`, or the plugin below. | not yet tested |
| Codex | `uoink skill install --to "$env:USERPROFILE\.agents\skills"` | `uoink connect codex`; CLI fallback. Older setups may also use `~/.codex/skills`. | not yet tested |
| pi | `uoink skill install --to "$env:USERPROFILE\.pi\agent\skills"` | CLI from its shell; no built-in MCP required. | not yet tested |
| Hermes Agent | `uoink skill install --to "$env:USERPROFILE\.hermes\skills"` | CLI, or `uoink connect hermes`. | not yet tested |
| OpenClaw | `uoink skill install --to "$env:USERPROFILE\.openclaw\skills"` | CLI from its shell. | not yet tested |

For an agent running elsewhere, install the skill in that agent's environment
and arrange local execution on the Uoink machine. A copied skill alone cannot
give a remote agent access to Windows files or commands.

The small [agent kit](../agent-kit/README.md) contains a Claude Code marketplace
and plain skill copies for pi, Hermes taps, and ClawHub packaging. The marketplace
at `ryanbiddy/uoink-agent-kit` is published with this release. Install the Claude Code plugin:

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
`uoink call uoink_x url="URL"`; `x_text_capture_enabled` defaults **on**, and a
saved off setting still blocks that tool. A plain X post passed to `capture`
uses `uoink_url`'s media route, not `uoink_x`. The page allowlist and public-network
checks still apply to page captures, including pasted X article URLs.

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
`{app}\cli\uoink.cmd`. Its no-argument behavior starts the helper;
`uoink serve` does the same, and `uoink serve --doctor` forwards the old CLI.
Use the new command's `search` for in-process library reads. An extensionless
`{app}\cli\uoink` shell launcher also serves Bash-based agents on Windows.

## Installer and receipt isolation

The checked PATH task appends `{app}\cli` to **User PATH** only if absent. This
folder contains only the two agent launchers. FFmpeg and FFprobe stay in
`{app}\bin`, which the helper adds only to its own process PATH. The task
preserves existing entries, ordering, and the registry value type. A small
ownership marker records an entry the installer added. Uninstall removes one
exact matching owned entry; it leaves pre-existing entries alone. New terminals
receive the change through Inno's `ChangesEnvironment=yes`.

With `/ISOLATED=1`, both installation and persisted isolated uninstallation
skip PATH handling before reading the registry value. Receipt installs already
pass `/ISOLATED=1`, `/NOCLOSEAPPLICATIONS`, `/NORESTARTAPPLICATIONS`, and
`/TASKS=""`. `scripts/install_receipt/agent_install.ps1` checks
`{app}\cli\uoink.cmd`, invokes that absolute path with
`--isolated-from-install-dir <app> status`, and requires the returned data
directory to match the receipt profile. It never depends on or changes real
User PATH. Static tests cover PATH ownership and removal; this pass does not
run an installer or claim a registry mutation test.
