# Uoink agent kit

Uoink saves videos, podcasts, articles, posts, and notes on your disk. Agents
can search that library, quote returned evidence with timestamps, capture a
link, or save a note through MCP or the `uoink` CLI.

Install [Uoink for Windows](https://github.com/ryanbiddy/uoink/releases/latest)
first, with **Add the uoink command to PATH for AI agents** checked. Open a new
terminal and run `uoink status`. This kit contains instructions and MCP config;
it does not include Python, the app, or your library. The CLI requires the
3.10.0 release of Uoink or later.

On a Mac (Apple Silicon, macOS 15 or later; preview), follow [the Mac install guide](https://github.com/ryanbiddy/uoink/blob/main/docs/mac/INSTALL.md).
The CLI is `<installed Uoink.app>/Contents/Helpers/uoink`. Use a PATH symlink
to that shim, then run `uoink connect <client>` to print the actual app paths.
The command uses `Contents/Resources/Python/bin/python3 -B -s` and
`Contents/Resources/uoink_mcp.py`, including when the app lives outside
`/Applications`. Claude Desktop's file is
`~/Library/Application Support/Claude/claude_desktop_config.json`; Cursor uses
`~/.cursor/mcp.json` and Codex uses `~/.codex/config.toml`.

On Mac, use `uoink connect claude-code` with the standalone skill instead of
the static Windows plugin MCP entry below. For example,
`uoink skill install --to "$HOME/.claude/skills"`. For Codex, use
`uoink skill install --to "$HOME/.agents/skills"` and the printed Codex MCP
recipe. Claude Code passed Mac acceptance; other clients are untested there.

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

## Zing (video studio, optional)

[Zing](https://github.com/ryanbiddy/zing) studies reference videos, matches a
style from your Uoink library, renders local cuts with captions, color and
transitions, and makes memes. It is a separate tool. This marketplace also
carries its plugin:

```powershell
claude plugin install zing@uoink
```

The plugin launches `zing serve-mcp`, so install Zing first (it is not on
PyPI; see Zing's [CONNECT.md](https://github.com/ryanbiddy/zing/blob/main/docs/CONNECT.md))
and make sure `zing` is on PATH. Run `zing doctor` once. The plugin includes
the `zing` skill and the `uoink-zing` suite skill, which teaches the flow from
finding a reference in Uoink to rendering with Zing and saving the breakdown
back to Uoink. Both skills are also in `skills/` for other agents. The Zing
plugin is **not yet tested** in Claude Code beyond `claude plugin validate`.

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

Official documentation was checked on 2026-10-21. The table separates verified
formats and routes from remaining documentation gaps. All actual client
connections are **not yet tested**. UI routes do not imply a JSON import or an
undocumented file path. Platform-specific recipes refuse unsupported platforms.

See the [complete connection guide](https://github.com/ryanbiddy/uoink/blob/main/docs/connect-your-agent.md)
for merge instructions, the Windows Obsidian mirror and Mac read-only alternative,
both n8n routes, local-model setup and skipped clients. The table below is
generated from `uoink_connect.py`; do not edit it by hand.

<!-- BEGIN GENERATED CLIENTS -->
| Client | Platforms | Windows location or route | macOS location or route | Linux location or route | Verified docs | Official source | Checked |
|---|---|---|---|---|---|---|---|
| `uoink connect claude-code` | Windows, macOS, Linux | %USERPROFILE%/.claude.json (managed by claude mcp add) | ~/.claude.json (managed by claude mcp add) | ~/.claude.json (managed by claude mcp add) | Yes | [docs 1](https://code.claude.com/docs/en/mcp) | 2026-10-21 |
| `uoink connect claude-desktop` | Windows, macOS | %APPDATA%/Claude/claude_desktop_config.json | ~/Library/Application Support/Claude/claude_desktop_config.json | No recipe | Yes | [docs 1](https://modelcontextprotocol.io/docs/develop/connect-local-servers) | 2026-10-21 |
| `uoink connect cursor` | Windows, macOS, Linux | %USERPROFILE%/.cursor/mcp.json | ~/.cursor/mcp.json | ~/.cursor/mcp.json | Yes | [docs 1](https://cursor.com/docs/mcp) | 2026-10-21 |
| `uoink connect codex` | Windows, macOS, Linux | %USERPROFILE%/.codex/config.toml | ~/.codex/config.toml | ~/.codex/config.toml | Yes | [docs 1](https://developers.openai.com/codex/mcp) | 2026-10-21 |
| `uoink connect gemini` | Windows, macOS, Linux | %USERPROFILE%/.gemini/settings.json | ~/.gemini/settings.json | ~/.gemini/settings.json | Yes | [docs 1](https://geminicli.com/docs/tools/mcp-server/) | 2026-10-21 |
| `uoink connect vscode` | Windows, macOS, Linux | Project .vscode/mcp.json | Project .vscode/mcp.json | Project .vscode/mcp.json | Yes | [docs 1](https://code.visualstudio.com/docs/agents/reference/mcp-configuration) | 2026-10-21 |
| `uoink connect windsurf` | Windows, macOS, Linux | %APPDATA%/devin/mcp_config.json | ~/.config/devin/mcp_config.json | ~/.config/devin/mcp_config.json | Yes | [docs 1](https://docs.devin.ai/desktop/cascade/mcp) | 2026-10-21 |
| `uoink connect cline` | Windows, macOS, Linux | Cline > MCP Servers > Configure > Configure MCP Servers (cline_mcp_settings.json) | Cline > MCP Servers > Configure > Configure MCP Servers (cline_mcp_settings.json) | Cline > MCP Servers > Configure > Configure MCP Servers (cline_mcp_settings.json) | Yes | [docs 1](https://docs.cline.bot/mcp/mcp-overview) | 2026-10-21 |
| `uoink connect zed` | Windows, macOS, Linux | %APPDATA%/Zed/settings.json | Zed command palette > Open Settings File | ~/.config/zed/settings.json | No: The MCP shape is documented, but current official pages disagree on the macOS settings directory. Use Open Settings File. | [docs 1](https://zed.dev/docs/ai/mcp), [docs 2](https://github.com/zed-industries/zed/blob/main/docs/.doc-examples/configuration.md), [docs 3](https://zed.dev/docs/debugger) | 2026-10-21 |
| `uoink connect goose` | Windows, macOS, Linux | %APPDATA%/Block/goose/config/config.yaml | ~/.config/goose/config.yaml | ~/.config/goose/config.yaml | Yes | [docs 1](https://github.com/aaif-goose/goose/blob/main/documentation/docs/guides/config-files.md) | 2026-10-21 |
| `uoink connect opencode` | Windows, macOS, Linux | %USERPROFILE%/.config/opencode/opencode.json | ~/.config/opencode/opencode.json | ~/.config/opencode/opencode.json | Yes | [docs 1](https://opencode.ai/docs/mcp-servers/), [docs 2](https://opencode.ai/docs/config/) | 2026-10-21 |
| `uoink connect lm-studio` | Windows, macOS, Linux | %USERPROFILE%/.lmstudio/mcp.json | ~/.lmstudio/mcp.json | ~/.lmstudio/mcp.json | Yes | [docs 1](https://lmstudio.ai/blog/lmstudio-v0.3.17), [docs 2](https://lmstudio.ai/docs/app/mcp) | 2026-10-21 |
| `uoink connect hermes` | Windows, macOS, Linux | %LOCALAPPDATA%/hermes/config.yaml | ~/.hermes/config.yaml | ~/.hermes/config.yaml | Yes | [docs 1](https://hermes-agent.nousresearch.com/docs/user-guide/features/mcp), [docs 2](https://hermes-agent.nousresearch.com/docs/getting-started/installation/) | 2026-10-21 |
| `uoink connect warp` | Windows, macOS, Linux | %USERPROFILE%/.warp/.mcp.json | ~/.warp/.mcp.json | ~/.warp/.mcp.json | Yes | [docs 1](https://docs.warp.dev/agents/capabilities/mcp/) | 2026-10-21 |
| `uoink connect junie` | Windows, macOS, Linux | %USERPROFILE%/.junie/mcp/mcp.json | ~/.junie/mcp/mcp.json | ~/.junie/mcp/mcp.json | Yes | [docs 1](https://junie.jetbrains.com/docs/junie-cli-mcp-configuration.html) | 2026-10-21 |
| `uoink connect amp` | Windows, macOS, Linux | %USERPROFILE%/.config/amp/settings.json | ~/.config/amp/settings.json | ~/.config/amp/settings.json | Yes | [docs 1](https://ampcode.com/docs/customize/mcp), [docs 2](https://ampcode.com/docs/cli/settings) | 2026-10-21 |
| `uoink connect roo` | Windows, macOS, Linux | Project .roo/mcp.json | Project .roo/mcp.json | Project .roo/mcp.json | Yes | [docs 1](https://roocodeinc.github.io/Roo-Code/features/mcp/using-mcp-in-roo/) | 2026-10-21 |
| `uoink connect kilo` | Windows, macOS, Linux | %USERPROFILE%/.config/kilo/kilo.jsonc | ~/.config/kilo/kilo.jsonc | ~/.config/kilo/kilo.jsonc | Yes | [docs 1](https://kilo.ai/docs/automate/mcp/using-in-kilo-code) | 2026-10-21 |
| `uoink connect kilo-legacy` | Windows, macOS, Linux | Legacy Kilo extension config; no current path confirmed | Legacy Kilo extension config; no current path confirmed | Legacy Kilo extension config; no current path confirmed | No: Current docs describe kilo.jsonc, not the old .kilocode/mcp.json format. | [docs 1](https://kilo.ai/docs/automate/mcp/using-in-kilo-code) | 2026-10-21 |
| `uoink connect cherry-studio` | Windows, macOS, Linux | Settings > MCP > MCP Servers > Add (manual stdio fields) | Settings > MCP > MCP Servers > Add (manual stdio fields) | Settings > MCP > MCP Servers > Add (manual stdio fields) | Yes | [docs 1](https://docs.cherryai.com.cn/advanced-basic/extensions/mcp) | 2026-10-21 |
| `uoink connect jan` | Windows, macOS, Linux | Settings > MCP Servers > + | Settings > MCP Servers > + | Settings > MCP Servers > + | Yes | [docs 1](https://docs.jan.ai/desktop/mcp) | 2026-10-21 |
| `uoink connect librechat` | Windows, macOS, Linux | librechat.yaml in the LibreChat app directory | librechat.yaml in the LibreChat app directory | librechat.yaml in the LibreChat app directory | Yes | [docs 1](https://www.librechat.ai/docs/configuration/librechat_yaml/object_structure/mcp_servers) | 2026-10-21 |
| `uoink connect msty` | Windows, macOS, Linux | Toolbox > Tools > Add New Tool > STDIO / JSON > Tool Configuration | Toolbox > Tools > Add New Tool > STDIO / JSON > Tool Configuration | Toolbox > Tools > Add New Tool > STDIO / JSON > Tool Configuration | Yes | [docs 1](https://docs.msty.ai/studio/toolbox/tools) | 2026-10-21 |
| `uoink connect boltai` | macOS | Not available on Windows | ~/.boltai/mcp.json | No recipe | Yes | [docs 1](https://docs.boltai.com/docs/plugins/mcp-servers) | 2026-10-21 |
| `uoink connect continue` | Windows, macOS, Linux | Project .continue/mcpServers/uoink.yaml | Project .continue/mcpServers/uoink.yaml | Project .continue/mcpServers/uoink.yaml | Yes | [docs 1](https://docs.continue.dev/customize/deep-dives/mcp) | 2026-10-21 |
| `uoink connect raycast` | Windows, macOS | Install MCP Server command, or Manage MCP Servers > Install New Server | Install MCP Server command, or Manage MCP Servers > Install New Server | No recipe | Yes | [docs 1](https://manual.raycast.com/ai/model-context-protocol), [docs 2](https://www.raycast.com/changelog/windows) | 2026-10-21 |
| `uoink connect open-webui` | Windows, macOS, Linux | A chosen mcpo JSON file passed with --config | A chosen mcpo JSON file passed with --config | A chosen mcpo JSON file passed with --config | Yes | [docs 1](https://github.com/open-webui/mcpo), [docs 2](https://docs.openwebui.com/features/extensibility/mcp/) | 2026-10-21 |
| `uoink connect anythingllm` | Windows, macOS | %APPDATA%/anythingllm-desktop/storage/plugins/anythingllm_mcp_servers.json | ~/Library/Application Support/anythingllm-desktop/storage/plugins/anythingllm_mcp_servers.json | No recipe | Yes | [docs 1](https://docs.anythingllm.com/mcp-compatibility/desktop), [docs 2](https://docs.anythingllm.com/mcp-compatibility/overview), [docs 3](https://docs.anythingllm.com/installation-desktop/storage) | 2026-10-21 |
| `uoink connect ollama` | Windows, macOS, Linux | No MCP config in Ollama; configure its client instead | No MCP config in Ollama; configure its client instead | No MCP config in Ollama; configure its client instead | Yes | [docs 1](https://docs.ollama.com/capabilities/tool-calling), [docs 2](https://docs.openwebui.com/features/extensibility/mcp/), [docs 3](https://docs.continue.dev/guides/ollama-guide) | 2026-10-21 |
| `uoink connect smithery-local` | Windows, macOS, Linux | MCPB publishing docs; no smithery.yaml recipe | MCPB publishing docs; no smithery.yaml recipe | MCPB publishing docs; no smithery.yaml recipe | No: The current docs describe MCPB publishing, but a local smithery.yaml command/args schema was not established. | [docs 1](https://smithery.ai/docs/build/publish) | 2026-10-21 |
| `uoink connect windows-odr` | Windows | An unpacked MCPB bundle's manifest.json | Not available on macOS | No recipe | Yes | [docs 1](https://learn.microsoft.com/en-us/windows/ai/mcp/servers/mcp-manual) | 2026-10-21 |
| `uoink connect obsidian` | Windows, macOS | Uoink Settings > Library > Library Mirror; choose the vault root | Library Mirror is unavailable on macOS; use read-only CLI/MCP | No recipe | Yes | [docs 1](https://help.obsidian.md/uri) | 2026-10-21 |
| `uoink connect n8n` | Windows, macOS, Linux | Self-hosted n8n workflow UI on the Uoink host | Self-hosted n8n workflow UI on the Uoink host | Self-hosted n8n workflow UI on the Uoink host | Yes | [docs 1](https://docs.n8n.io/integrations/builtin/credentials/httprequest/), [docs 2](https://docs.n8n.io/integrations/builtin/cluster-nodes/sub-nodes/n8n-nodes-langchain.toolmcp/), [docs 3](https://github.com/n8n-io/n8n/releases/tag/n8n%401.114.0) | 2026-10-21 |
| `uoink connect make` | Windows, macOS, Linux | No direct localhost route from Make cloud runners | No direct localhost route from Make cloud runners | No direct localhost route from Make cloud runners | Yes | [docs 1](https://help.make.com/on-premise-agent) | 2026-10-21 |
| `uoink connect zapier` | Windows, macOS, Linux | No direct localhost route from Zapier cloud runners | No direct localhost route from Zapier cloud runners | No direct localhost route from Zapier cloud runners | Yes | [docs 1](https://help.zapier.com/hc/en-us/articles/44391646192397-Ways-to-make-API-requests-in-Zapier) | 2026-10-21 |
| `uoink connect autohotkey` | Windows | A user-created .ahk file (AutoHotkey v2) | Not available on macOS | No recipe | Yes | [docs 1](https://github.com/AutoHotkey/AutoHotkeyDocs/blob/v2/docs/lib/Run.htm) | 2026-10-21 |
| `uoink connect powertoys` | Windows | PowerToys Command Palette > Run commands | Not available on macOS | No recipe | Yes | [docs 1](https://learn.microsoft.com/en-us/windows/powertoys/command-palette/overview) | 2026-10-21 |
| `uoink connect alfred` | macOS | Not available on Windows | Workflow > Run Script (/bin/zsh) | No recipe | Yes | [docs 1](https://www.alfredapp.com/help/workflows/actions/run-script/) | 2026-10-21 |
| `uoink connect kiro` | Windows, macOS, Linux | %USERPROFILE%/.kiro/settings/mcp.json | ~/.kiro/settings/mcp.json | ~/.kiro/settings/mcp.json | Yes | [docs 1](https://kiro.dev/docs/mcp/configuration/) | 2026-10-21 |
| `uoink connect copilot-cli` | Windows, macOS, Linux | %USERPROFILE%/.copilot/mcp-config.json | ~/.copilot/mcp-config.json | ~/.copilot/mcp-config.json | Yes | [docs 1](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-mcp-servers) | 2026-10-21 |
| `uoink connect auggie` | macOS, Linux | Not native; WSL uses $HOME/.augment/settings.json inside WSL | ~/.augment/settings.json | ~/.augment/settings.json | Yes | [docs 1](https://docs.augmentcode.com/cli/integrations), [docs 2](https://docs.augmentcode.com/cli/setup-auggie/install-auggie-cli) | 2026-10-21 |
| `uoink connect factory-droid` | Windows, macOS, Linux | %USERPROFILE%/.factory/mcp.json | ~/.factory/mcp.json | ~/.factory/mcp.json | Yes | [docs 1](https://docs.factory.com/harness/mcp) | 2026-10-21 |
| `uoink connect qwen-code` | Windows, macOS, Linux | %USERPROFILE%/.qwen/settings.json | ~/.qwen/settings.json | ~/.qwen/settings.json | Yes | [docs 1](https://qwenlm.github.io/qwen-code-docs/en/users/features/mcp/) | 2026-10-21 |
| `uoink connect crush` | Windows, macOS, Linux | %USERPROFILE%/.config/crush/crushrc | ~/.config/crush/crushrc | ~/.config/crush/crushrc | Yes | [docs 1](https://github.com/charmbracelet/crush/blob/main/README.md) | 2026-10-21 |
| `uoink connect antigravity` | Windows, macOS, Linux | %USERPROFILE%/.gemini/config/mcp_config.json | ~/.gemini/config/mcp_config.json | ~/.gemini/config/mcp_config.json | Yes | [docs 1](https://www.antigravity.google/docs/mcp) | 2026-10-21 |
| `uoink connect chatbox` | Windows, macOS, Linux | Settings > MCP > Add Server > Local (stdio) | Settings > MCP > Add Server > Local (stdio) | Settings > MCP > Add Server > Local (stdio) | Yes | [docs 1](https://api.chatboxai.app/en/guide/work-mode/configuration) | 2026-10-21 |
| `uoink connect dive` | Windows, macOS, Linux | MCP server settings JSON editor | MCP server settings JSON editor | MCP server settings JSON editor | Yes | [docs 1](https://github.com/OpenAgentPlatform/Dive/blob/main/MCP_SETUP.md) | 2026-10-21 |
| `uoink connect perplexity` | macOS | Local MCP is not supported on Windows | Mac app > Plugins > Add custom > Simple (local MCP) | No recipe | Yes | [docs 1](https://www.perplexity.ai/help-center/en/articles/11502712-local-and-remote-mcps-for-perplexity) | 2026-10-21 |
<!-- END GENERATED CLIENTS -->
## Layout and maintenance

```text
.claude-plugin/marketplace.json
plugins/uoink/.claude-plugin/plugin.json
plugins/uoink/.mcp.json
plugins/uoink/skills/uoink/
plugins/zing/.claude-plugin/plugin.json
plugins/zing/.mcp.json
plugins/zing/skills/zing/
plugins/zing/skills/uoink-zing/
skills/uoink/
skills/zing/
skills/uoink-zing/
```

The two skill folders are generated copies. In the main Uoink repository, edit
`skills/uoink`, run `python scripts/build_agent_kit.py`, then run
`python scripts/build_agent_kit.py --check`. The test suite fails on drift.
The same script sets the plugin version from `VERSION` and regenerates the client
tables here and in `docs/connect-your-agent.md`; `--check` fails if either drifts.

The Zing skill folders are copies of `skills/zing` and `skills/uoink-zing` in
the [Zing repository](https://github.com/ryanbiddy/zing); `plugins/zing/SOURCE.md`
records the commit they were copied from.

Before publication, run locally:

```powershell
claude plugin validate ./agent-kit
claude plugin validate ./agent-kit/plugins/uoink
```
