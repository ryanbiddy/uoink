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

## Client recipes and documentation checks

`uoink connect <client>` prints a recipe with this installation's absolute paths.
It does not read or edit client config files, launch clients, or contact the
running helper. Location, documentation status, sources and check date go to
stderr. Stdout contains the config, command or setup steps. Merge entries into
an existing config without replacing unrelated settings or servers.

**Verified docs: Yes** means the linked official documentation establishes the
printed format or UI route. For Ollama, Obsidian, Make and Zapier it describes
the documented route or limit, not an MCP config file. Every client connection
is still **not yet tested** in the actual client. A source check and a config
parse do not establish end-to-end acceptance. **No** rows state the missing
evidence. The documentation review is dated **2026-10-21**. Linux is listed
where the recipe has a Linux path or a platform-neutral route. A missing Linux
recipe does not establish whether the client itself supports Linux. Unless a
row's sources name a Linux path, its Linux location reuses the documented POSIX
spelling and was not separately checked against Linux documentation.

The table is generated from `CLIENTS` in `uoink_connect.py`. Windows home paths
use `%USERPROFILE%`; `%APPDATA%` is the roaming application-data directory.
On macOS and Linux, `~` is your home directory. Project paths are relative to the workspace
opened in the client. An explicit UI route means there is no file to locate or
JSON import to assume. Platform-specific recipes refuse unsupported platforms.

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

On macOS, follow [the Mac install guide](mac/INSTALL.md). Run the installed
`Uoink.app/Contents/Helpers/uoink` shim, or its PATH symlink. Generated MCP
commands use the app's bundled `Contents/Resources/Python/bin/python3 -B -s`
and `Contents/Resources/uoink_mcp.py`, including custom app locations. BoltAI,
Alfred and Perplexity local MCP are Mac-only. Auggie documents Windows through
WSL; Uoink does not print a native Windows recipe or guess WSL path translation.

Claude Code prints a PowerShell command on Windows and a shell command on Mac.
Crush prints a line for its current **crushrc** file, interpreted by Crush's
built-in Bash on both platforms. Do not run that line in PowerShell. Current
Antigravity uses `~/.gemini/config/mcp_config.json`, shared by its App, IDE and
CLI. Current Kilo uses `mcp` with a command array in `kilo.jsonc`; the retained
`kilo-legacy` entry explains why it no longer prints the old unverified format.

Goose, Hermes, Continue and LibreChat output JSON-form YAML, valid YAML 1.2.
Translate the keys into the existing file's YAML style or use a YAML-aware
editor. Do not append a second JSON document. Continue's standalone workspace
file includes `name`, `version`, `schema: v1` and a `mcpServers` list. In an
existing global `~/.continue/config.yaml`, merge only the list and retain the
agent's metadata and models. MCP needs Continue's Agent mode. The dashboard's
old Continue JSON writer now refuses the edit and points to this manual route.
It does not migrate or overwrite an existing Continue configuration.
Detection reads global `~/.continue/config.yaml` on macOS and Linux, or
`%USERPROFILE%/.continue/config.yaml` on Windows. If YAML is absent, it reads
legacy `config.json` in the same directory, using
`experimental.modelContextProtocolServers[].transport`. YAML takes precedence.
The dashboard reports connected only when an entry's command and arguments
match this Uoink install. Malformed or unreadable files report disconnected
with a reason. Detection does not scan workspace configs or resolve Continue
Hub references.

## Local-model apps

The MCP client starts Uoink. The model must also support tool calls. Ollama is
the model runtime and has no Uoink MCP config. Pair it with Open WebUI or Continue
and configure the Ollama provider separately. `uoink connect ollama` prints
those client choices.

For **LM Studio**, open the Program tab, then **Install > Edit mcp.json**.
Merge the printed `mcpServers.uoink` entry and save. Its documented locations
are `%USERPROFILE%/.lmstudio/mcp.json` on Windows and `~/.lmstudio/mcp.json`
on Mac. [LM Studio's setup and path documentation](https://lmstudio.ai/blog/lmstudio-v0.3.17).

For **AnythingLLM Desktop**, click the version number and choose **Open storage**
to confirm the storage root shown in the table. Merge into
`plugins/anythingllm_mcp_servers.json`, then choose **Agent Skills > Refresh**.
Use `@agent` in chat. The server may be configured correctly even when the model
cannot call it. [Desktop MCP setup](https://docs.anythingllm.com/mcp-compatibility/desktop).

**Jan**, **Cherry Studio** and **Chatbox** have documented command, argument and
environment fields. Their recipes print a field reference, not a claimed JSON
import. **Msty** instead accepts a bare `command`/`args`/`env` object in
**Toolbox > Tools > Add New Tool > STDIO / JSON > Tool Configuration**; name it
`uoink`. **BoltAI** uses its MCP JSON editor on Mac.

**Open WebUI** has two documented routes:

1. Native MCP: on version 0.6.31 or later, open **Settings > Admin > Integrations >
   External Tool Servers**, add an **MCP (Streamable HTTP)** connection, and use
   `http://127.0.0.1:5179/mcp/v1`. Set the `X-Uoink-Token` custom header through
   the connection's authentication/header settings. Use the configured Uoink
   port if different. This route requires Open WebUI's server process to run on
   the same host and reach that loopback interface.
2. mcpo bridge: `uoink connect open-webui` prints the official `mcpServers`
   config for a chosen JSON file. Pass that file with mcpo's `--config` option.
   Run the bridge locally with authentication. In Open WebUI, add its OpenAPI
   tool-server URL for the named `/uoink` route. The bridge must be able to
   execute the printed Python and script paths.

See [native MCP](https://docs.openwebui.com/features/extensibility/mcp/) and
[mcpo's README](https://github.com/open-webui/mcpo). Neither route was connected
during verification. A container's `127.0.0.1` and filesystem are its own;
these host paths and URLs are not a Docker recipe.

## Raycast and Mac launchers

Run **Install MCP Server**, or **Manage MCP Servers > Install New Server**.
Choose **Stdio**, name it `uoink`, and copy the command and environment fields
from `uoink connect raycast`. Paste the `args` JSON array intact into Arguments
so spaces remain part of each path. Raycast Pro is required. This form is
documented; a `mcpServers` JSON import is not claimed. The Windows changelog
also confirms MCP support. [Raycast MCP](https://manual.raycast.com/ai/model-context-protocol),
[Windows changelog](https://www.raycast.com/changelog/windows).

On Mac, Perplexity's **Plugins > Add custom > Simple** local setup requires its
PerplexityXPC helper. Paste the full command from `uoink connect perplexity`,
save, wait for **Running**, then enable it under Sources. The website's remote
connectors cannot run that local command.
[Perplexity local MCP](https://www.perplexity.ai/help-center/en/articles/11502712-local-and-remote-mcps-for-perplexity).

`uoink connect alfred` prints a fixed Run Script action using the installed
Mac CLI shim. AutoHotkey v2 and PowerToys Command Palette recipes are
Windows-only. PowerToys uses **Run commands** (`>`). These launch the CLI;
they do not add inline library search results. Keep arbitrary clipboard or
query text out of shell command strings.

## Obsidian on Windows and macOS

On **Windows**, open the vault in Obsidian once, then open Uoink's
**Settings > Library > Library Mirror**. Set the destination to the vault root,
for example `C:\Users\you\Documents\Research Vault`, not its `.obsidian` folder.
Choose **All current and future items** or **Allowlist only** with item IDs.
Choose **Preview**, review the scope and counts, then **Enable**. The mirror is
off by default; the dashboard's preview and consent flow enables it.

The mirror writes Markdown under `<vault>/Uoink/`: `Library.md` is the index,
`Library/` contains evidence cards, `Shelves/` contains shelf pages, and `Briefs/`
contains accepted briefs. It exports one way. It does not copy the whole media
library, import vault edits, or synchronize Obsidian settings. Resync processes
bounded work, so pending items can remain. Disable stops future writes and
leaves existing exported notes in place. Conflicting edits and unmanaged files
can block writes. Mirror behavior is unchanged by these integration recipes.

Open the generated index with this link after replacing the vault name:

```text
obsidian://open?vault=Research%20Vault&file=Uoink%2FLibrary
```

For an evidence card, use its actual vault-relative path from the exported
index as the `file` value, with percent encoding. Do not derive the hashed
filename from its title. Obsidian opens these Markdown files normally; no
plugin is needed. The URI also works on Mac for notes that already exist.
[Obsidian URI parameters](https://help.obsidian.md/uri), checked 2026-10-21.

On **macOS**, Library Mirror is gated off in `_platform.library_mirror_capability`.
There is no automatic vault export in the current Mac build. The read-only
alternative is the local CLI or an MCP client on the Mac:

```sh
uoink search "working memory" --limit 5
uoink recent --limit 10
uoink get "ITEM_ID_FROM_SEARCH"
```

Read the returned evidence and copy selected results into an Obsidian note
manually if needed. These commands do not write vault notes. The older
`obsidian_vault_path` setting for `TASTE.md` and `USER.md` is separate from
Library Mirror and does not enable a Mac corpus mirror. No Obsidian MCP plugin
is claimed or installed.

## n8n, Zapier and Make

Run **self-hosted n8n on the same host as Uoink**, with access to its loopback
interface. This applies to both Windows and Mac. A cloud worker, remote worker
or ordinary container cannot use its own `127.0.0.1` to reach the Uoink host.
These are setup recipes; no request was sent during verification.

For the **HTTP Request node**:

1. Create a **Header Auth** credential. Set Name to `X-Uoink-Token` and enter
   your local Uoink token in its credential value field.
2. Add an HTTP Request node with method **GET** and URL
   `http://127.0.0.1:5179/memory/search`.
3. Set query parameters `q` to `working memory` and `limit` to `5`.
4. Set Authentication to **Generic Credential Type**, select **Header Auth**,
   and select the saved credential. Execute the node when ready.

Keep the token in n8n credentials, not node JSON, a URL, a workflow export,
chat or logs. See [n8n HTTP credentials](https://docs.n8n.io/integrations/builtin/credentials/httprequest/)
and [Uoink's search endpoint](v2-api.md#get-memorysearch).

For the **MCP Client Tool node**, attach it to an AI Agent's tool connection.
Choose **HTTP Streamable**, use `http://127.0.0.1:5179/mcp/v1` as the endpoint,
and select **Header Auth** with the saved `X-Uoink-Token` credential. Choose
only the tools needed by that workflow, then check tool discovery. Use the
configured Uoink port if different. This node has no documented stdio launch
route. Its current reference still describes an SSE field; n8n's official
1.114.0 release notes explicitly establish HTTP Streamable as the default.
If your node only offers SSE, update it before trying this recipe. Client
acceptance with Uoink's `/mcp/v1` endpoint remains not yet tested.
[n8n MCP Client Tool reference](https://docs.n8n.io/integrations/builtin/cluster-nodes/sub-nodes/n8n-nodes-langchain.toolmcp/),
[official transport release note](https://github.com/n8n-io/n8n/releases/tag/n8n%401.114.0).

Zapier and Make cloud runners cannot reach this PC's `127.0.0.1`. Make documents
a separate Enterprise on-prem agent, but this guide does not claim a tested
Uoink integration with it. No tunnel or public API exposure is configured.
[Make on-prem agent](https://help.make.com/on-premise-agent),
[Zapier HTTP actions](https://help.zapier.com/hc/en-us/articles/44391646192397-Ways-to-make-API-requests-in-Zapier).

## Preview registries and clients not added

On Windows build **26220.7262 or later**, the preview ODR command accepts a
local unpacked MCPB manifest as a positional argument:

```powershell
odr.exe mcp add "C:\path with spaces\uoink-bundle\manifest.json"
odr.exe list
```

Keep the bundle files beside that manifest. The source tree's `.mcpb/manifest.json`
has bundle-relative paths and is not a standalone installed package. Registration
and client acceptance are not yet tested. Uoink's installer does not run ODR.
[Microsoft's manual registration guide](https://learn.microsoft.com/en-us/windows/ai/mcp/servers/mcp-manual).

Smithery now documents local MCPB publishing, but no current local `smithery.yaml`
command/args schema was established. The existing entry remains unverified and
prints guidance only. It does not publish the user's private installation.

These requested clients were checked on **2026-10-21** and skipped. MCP support
alone is not enough to infer a config format or path.

| Client | Official source checked | Why no recipe was added |
|---|---|---|
| Trae | [MCP docs](https://docs.trae.ai/ide/model-context-protocol) | The official page repeatedly failed to load. The current schema and paths could not be verified. |
| Witsy | [Official README](https://github.com/Kochava-Studios/witsy/blob/main/README.md) | It confirms MCP support, but the documentation reviewed did not establish a local config/import schema. |
| 5ire | [Docs](https://5ire.app/docs), [official README](https://github.com/nanbingxyz/5ire) | The reviewed docs describe tools and remote setup but do not establish a complete local config/import schema. |
| DeepChat | [Official repository docs](https://github.com/ThinkInAIXYZ/deepchat/tree/main/docs) | The reviewed README and architecture docs confirm MCP support but do not establish a user-facing local config/import schema. A CLI guide fetch also failed. |

ChatGPT web, claude.ai web and remote-only connectors are outside these local
recipes. A local skill or file does not give a cloud runner access to this host.

## Cursor and VS Code install links

The dashboard's **Settings > Agents (MCP) > Agent connection** section offers
**Add to Cursor** and **Add to VS Code**. They open each client's review flow
with the current installation's absolute paths. Cursor receives the `core`
toolset. The links contain paths, isolation arguments when active, and UTF-8
settings, with no API token. These commands only print the same links:

```powershell
uoink connect cursor --deeplink
uoink connect vscode --deeplink
```

The client decides whether to install the server. Uoink cannot detect completion
or a missing URL handler. Client acceptance is not yet tested.
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
their existing HTTP search and maintenance commands. They hand the agent
subcommands (`tools`, `call`, `capture`, `recent`, `get`, `note`, `status`,
`connect`, `skill`, `serve`) to this CLI, so a source checkout can run
`./uoink status`; `search` stays the helper's HTTP search. The new PATH
command is `{app}\cli\uoink.cmd`. Its no-argument behavior starts the helper;
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
