"""Print-only agent connection recipes. Keep format and location choices in one table.

Documentation verification is separate from client acceptance. JSON is also valid
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
    mac_location: str = ""
    platforms: tuple[str, ...] = ("win32", "darwin", "linux")
    sources: tuple[str, ...] = ()
    checked: str = "2026-10-21"
    verified: bool = True
    reason: str = ""


def recipe(format: str, location: str, source: str, shape="mcpServers", **kwargs) -> Client:
    """Use explicit Windows homes while retaining the documented POSIX spelling."""
    mac = kwargs.pop("mac_location", location)
    extra_sources = kwargs.pop("sources", ())
    return Client(format, location.replace("~/", "%USERPROFILE%/"), shape,
                  mac_location=mac, sources=(source, *extra_sources), **kwargs)


UI_FIELDS = ("Name: uoink. Transport: stdio. Enter these command, args and env values\n"
             "in the client's separate fields. Each args element is one argument;\n"
             "keep paths with spaces together. This is a field reference, not an import file.\n<ENTRY>")

N8N_GUIDE = (
    "Run self-hosted n8n on the same host as Uoink. Containers have their own localhost.\n"
    "HTTP Request node: GET http://127.0.0.1:5179/memory/search\n"
    "Query parameters: q=working memory, limit=5. Authentication: Generic Credential\n"
    "Type > Header Auth. Store X-Uoink-Token and its value in n8n credentials.\n"
    "MCP Client Tool (connected to an AI Agent): select HTTP Streamable and endpoint\n"
    "http://127.0.0.1:5179/mcp/v1. Select Header Auth credentials for X-Uoink-Token.\n"
    "Choose only the tools the workflow needs. No stdio route is documented for this node.\n"
    "Use the configured port if different. Client acceptance is not yet tested.\n"
    "Never put the token in a URL, workflow export, chat, or log. Cloud runners cannot\n"
    "reach this PC's 127.0.0.1. See docs/connect-your-agent.md for both node recipes."
)


CLIENTS = {
    "claude-code": recipe("shell", "~/.claude.json (managed by claude mcp add)",
                          "https://code.claude.com/docs/en/mcp", "command"),
    "claude-desktop": recipe("json", "%APPDATA%/Claude/claude_desktop_config.json",
                             "https://modelcontextprotocol.io/docs/develop/connect-local-servers",
                             mac_location="~/Library/Application Support/Claude/claude_desktop_config.json"),
    "cursor": recipe("json", "~/.cursor/mcp.json", "https://cursor.com/docs/mcp",
                     note="Uses UOINK_MCP_TOOLSET=core to reduce the tool count."),
    "codex": recipe("toml", "~/.codex/config.toml", "https://developers.openai.com/codex/mcp", "mcp_servers",
                    note="Use CODEX_HOME/config.toml if you set CODEX_HOME."),
    "gemini": recipe("json", "~/.gemini/settings.json", "https://geminicli.com/docs/tools/mcp-server/"),
    "vscode": recipe("json", "Project .vscode/mcp.json",
                     "https://code.visualstudio.com/docs/agents/reference/mcp-configuration", "servers"),
    "windsurf": recipe("json", "%APPDATA%/devin/mcp_config.json", "https://docs.devin.ai/desktop/cascade/mcp",
                       mac_location="~/.config/devin/mcp_config.json",
                       note="Current Windsurf docs redirect to Devin Desktop's legacy Cascade. Older Windsurf uses ~/.codeium/windsurf/mcp_config.json. Devin Local uses a different setup; this recipe is for Cascade."),
    "cline": recipe("json", "Cline > MCP Servers > Configure > Configure MCP Servers (cline_mcp_settings.json)",
                    "https://docs.cline.bot/mcp/mcp-overview",
                    note="Use the IDE's config button; the directory depends on editor and profile. Cline CLI uses ~/.cline/data/settings/cline_mcp_settings.json."),
    "zed": recipe("json", "%APPDATA%/Zed/settings.json", "https://zed.dev/docs/ai/mcp", "context_servers",
                  mac_location="Zed command palette > Open Settings File",
                  sources=("https://github.com/zed-industries/zed/blob/main/docs/.doc-examples/configuration.md",
                           "https://zed.dev/docs/debugger"),
                  verified=False,
                  reason="The MCP shape is documented, but current official pages disagree on the macOS settings directory. Use Open Settings File.",
                  note="Merge context_servers into the user settings file opened by Zed. The older docs example lists ~/.config/zed/settings.json on Mac; the current debugger reference lists Application Support."),
    "goose": recipe("yaml", "%APPDATA%/Block/goose/config/config.yaml",
                    "https://github.com/aaif-goose/goose/blob/main/documentation/docs/guides/config-files.md",
                    "extensions", mac_location="~/.config/goose/config.yaml"),
    "opencode": recipe("json", "~/.config/opencode/opencode.json", "https://opencode.ai/docs/mcp-servers/", "mcp",
                       sources=("https://opencode.ai/docs/config/",), note="Project opencode.json is also supported."),
    "lm-studio": recipe("json", "~/.lmstudio/mcp.json", "https://lmstudio.ai/blog/lmstudio-v0.3.17",
                        sources=("https://lmstudio.ai/docs/app/mcp",),
                        note="Program tab > Install > Edit mcp.json. Save to reload; use a model that can call tools."),
    "hermes": recipe("yaml", "%LOCALAPPDATA%/hermes/config.yaml",
                     "https://hermes-agent.nousresearch.com/docs/user-guide/features/mcp", "mcp_servers",
                     mac_location="~/.hermes/config.yaml",
                     sources=("https://hermes-agent.nousresearch.com/docs/getting-started/installation/",),
                     note="Paths are for the source/CLI install. HERMES_HOME overrides the data directory; desktop packages can use their platform data directory."),
    "warp": recipe("json", "~/.warp/.mcp.json", "https://docs.warp.dev/agents/capabilities/mcp/",
                   note="Project .warp/.mcp.json is also supported."),
    "junie": recipe("json", "~/.junie/mcp/mcp.json", "https://junie.jetbrains.com/docs/junie-cli-mcp-configuration.html",
                    note="Junie CLI; project .junie/mcp/mcp.json is also supported. This is not an AI Assistant import recipe."),
    "amp": recipe("json", "~/.config/amp/settings.json", "https://ampcode.com/docs/customize/mcp", "amp.mcpServers",
                  sources=("https://ampcode.com/docs/cli/settings",),
                  note="Project .amp/settings.json is also supported. Run Amp locally so it can launch Uoink."),
    "roo": recipe("json", "Project .roo/mcp.json", "https://roocodeinc.github.io/Roo-Code/features/mcp/using-mcp-in-roo/",
                  note="For global mcp_settings.json, use Roo's MCP settings button; editor/profile determines its directory."),
    "kilo": recipe("jsonc", "~/.config/kilo/kilo.jsonc", "https://kilo.ai/docs/automate/mcp/using-in-kilo-code", "mcp",
                   note="Current format. Project kilo.jsonc or .kilo/kilo.jsonc is also supported."),
    "kilo-legacy": recipe("text", "Legacy Kilo extension config; no current path confirmed",
                          "https://kilo.ai/docs/automate/mcp/using-in-kilo-code", verified=False,
                          reason="Current docs describe kilo.jsonc, not the old .kilocode/mcp.json format.",
                          guide="Use uoink connect kilo for current Kilo. The old .kilocode/mcp.json\nrecipe is unverified and is no longer printed. Check the docs for your older\nextension version before migrating its settings."),
    "cherry-studio": recipe("text", "Settings > MCP > MCP Servers > Add (manual stdio fields)",
                            "https://docs.cherryai.com.cn/advanced-basic/extensions/mcp", guide=UI_FIELDS),
    "jan": recipe("text", "Settings > MCP Servers > +", "https://docs.jan.ai/desktop/mcp",
                  note="Enable tool use for the selected model, then approve tool calls as needed.", guide=UI_FIELDS),
    "librechat": recipe("yaml", "librechat.yaml in the LibreChat app directory",
                        "https://www.librechat.ai/docs/configuration/librechat_yaml/object_structure/mcp_servers",
                        note="Merge mcpServers into the existing file. The process must have access to Uoink's paths. A container cannot use host paths unchanged."),
    "msty": recipe("json", "Toolbox > Tools > Add New Tool > STDIO / JSON > Tool Configuration",
                   "https://docs.msty.ai/studio/toolbox/tools", "entry",
                   note="Paste the bare command/args/env object, then name the tool uoink. Do not wrap it in mcpServers."),
    "boltai": recipe("json", "Not available on Windows", "https://docs.boltai.com/docs/plugins/mcp-servers",
                     mac_location="~/.boltai/mcp.json", platforms=("darwin",),
                     note="Settings > Plugins > + opens the MCP configuration editor. Reload Config after an external edit."),
    "continue": recipe("yaml", "Project .continue/mcpServers/uoink.yaml",
                       "https://docs.continue.dev/customize/deep-dives/mcp", "list",
                       note="IDE Agent mode. For global config.yaml, merge only the mcpServers list into your existing config; keep its metadata and models."),
    "raycast": recipe("text", "Install MCP Server command, or Manage MCP Servers > Install New Server",
                      "https://manual.raycast.com/ai/model-context-protocol", guide=UI_FIELDS,
                      sources=("https://www.raycast.com/changelog/windows",),
                      note="Requires Raycast Pro. Choose Stdio; Arguments accepts a JSON array, so paste the args array intact. No JSON config import is claimed."),
    "open-webui": recipe("json", "A chosen mcpo JSON file passed with --config",
                         "https://github.com/open-webui/mcpo", sources=("https://docs.openwebui.com/features/extensibility/mcp/",),
                         note="Verified mcpo stdio bridge format. Open WebUI 0.6.31+ also documents native Streamable HTTP. Keep the bridge local and authenticated; see the guide for both routes."),
    "anythingllm": recipe("json", "%APPDATA%/anythingllm-desktop/storage/plugins/anythingllm_mcp_servers.json",
                          "https://docs.anythingllm.com/mcp-compatibility/desktop",
                          mac_location="~/Library/Application Support/anythingllm-desktop/storage/plugins/anythingllm_mcp_servers.json",
                          sources=("https://docs.anythingllm.com/mcp-compatibility/overview", "https://docs.anythingllm.com/installation-desktop/storage"),
                          note="Desktop only. Click the app version > Open storage to confirm the root. Agent Skills > Refresh reloads servers; use @agent in chat."),
    "ollama": recipe("text", "No MCP config in Ollama; configure its client instead",
                     "https://docs.ollama.com/capabilities/tool-calling",
                     sources=("https://docs.openwebui.com/features/extensibility/mcp/", "https://docs.continue.dev/guides/ollama-guide"),
                     guide="Ollama is a model runtime, not an MCP client. Use Open WebUI or Continue\nas the MCP client with an Ollama model that supports tools:\n  uoink connect open-webui\n  uoink connect continue\nConfigure the model provider separately in that client. No Ollama mcp.json is needed."),
    "smithery-local": recipe("text", "MCPB publishing docs; no smithery.yaml recipe",
                             "https://smithery.ai/docs/build/publish", verified=False,
                             reason="The current docs describe MCPB publishing, but a local smithery.yaml command/args schema was not established.",
                             guide="No smithery.yaml is shipped. Smithery documents local MCPB publishing;\nUoink's private install path is not a distributable server artifact.\nUse the agent kit or a direct uoink connect recipe for local setup."),
    "windows-odr": recipe("text", "An unpacked MCPB bundle's manifest.json",
                          "https://learn.microsoft.com/en-us/windows/ai/mcp/servers/mcp-manual", platforms=("win32",),
                          mac_location="Not available on macOS",
                          note="Windows preview, build 26220.7262 or later. Registration and acceptance have not been run.",
                          guide='On a supported Windows build, register a valid unpacked local MCPB bundle:\nodr.exe mcp add "C:\\path with spaces\\uoink-bundle\\manifest.json"\nodr.exe list\nThe manifest path is positional, not --uri. Keep its relative bundle files\nbeside it. A repository manifest alone is not an installed bundle.\nUoink\'s installer never runs ODR.'),
    "obsidian": recipe("text", "Uoink Settings > Library > Library Mirror; choose the vault root",
                       "https://help.obsidian.md/uri", mac_location="Library Mirror is unavailable on macOS; use read-only CLI/MCP",
                       guide="Windows: choose the vault root, choose all items or an item-ID allowlist,\nPreview, then Enable. Uoink writes evidence cards, shelves and accepted briefs\nunder <vault>/Uoink/. This is an opt-in one-way Markdown export, not full-media\nor two-way sync. Open its index with (replace and URL-encode your vault name):\nobsidian://open?vault=Research%20Vault&file=Uoink%2FLibrary\nmacOS: Library Mirror is gated off. Use uoink search, recent and get, or a\nlocal MCP client, to read the library. Copy selected results into notes manually.\nNo Obsidian MCP plugin or automatic Mac mirror is claimed."),
    "n8n": recipe("text", "Self-hosted n8n workflow UI on the Uoink host",
                  "https://docs.n8n.io/integrations/builtin/credentials/httprequest/",
                  sources=("https://docs.n8n.io/integrations/builtin/cluster-nodes/sub-nodes/n8n-nodes-langchain.toolmcp/",
                           "https://github.com/n8n-io/n8n/releases/tag/n8n%401.114.0"), guide=N8N_GUIDE),
    "make": recipe("text", "No direct localhost route from Make cloud runners", "https://help.make.com/on-premise-agent",
                   guide="Make cloud runners cannot reach this PC's 127.0.0.1. Make documents a\nseparate Enterprise on-prem agent; no Uoink recipe for it has been tested.\nUse uoink connect n8n for same-host self-hosted automation."),
    "zapier": recipe("text", "No direct localhost route from Zapier cloud runners",
                     "https://help.zapier.com/hc/en-us/articles/44391646192397-Ways-to-make-API-requests-in-Zapier",
                     guide="Zapier's cloud HTTP actions cannot reach this PC's 127.0.0.1.\nUse uoink connect n8n for same-host self-hosted automation.\nNo public endpoint or tunnel is configured by Uoink."),
    "autohotkey": recipe("text", "A user-created .ahk file (AutoHotkey v2)",
                         "https://github.com/AutoHotkey/AutoHotkeyDocs/blob/v2/docs/lib/Run.htm", platforms=("win32",),
                         mac_location="Not available on macOS",
                         guide='#Requires AutoHotkey v2.0\n^!u::Run(\'"<CLI>" search "working memory" --text\')'),
    "powertoys": recipe("text", "PowerToys Command Palette > Run commands",
                        "https://learn.microsoft.com/en-us/windows/powertoys/command-palette/overview", platforms=("win32",),
                        mac_location="Not available on macOS",
                        guide='In Command Palette, use Run commands (>), then enter:\n"<CLI>" search "working memory" --text\nThis launches the CLI; it does not provide inline library search results.'),
    "alfred": recipe("text", "Not available on Windows", "https://www.alfredapp.com/help/workflows/actions/run-script/",
                     mac_location="Workflow > Run Script (/bin/zsh)", platforms=("darwin",),
                     guide='Use this fixed Run Script action:\n<CLI_COMMAND> search "working memory" --text\nDo not interpolate clipboard or query text into the script.'),
    "kiro": recipe("json", "~/.kiro/settings/mcp.json", "https://kiro.dev/docs/mcp/configuration/",
                   note="Project .kiro/settings/mcp.json is also supported. Review tool approvals in Kiro."),
    "copilot-cli": recipe("json", "~/.copilot/mcp-config.json",
                          "https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-mcp-servers",
                          note="COPILOT_HOME overrides the directory. This is GitHub Copilot CLI, not VS Code's servers format."),
    "auggie": recipe("json", "Not native; WSL uses $HOME/.augment/settings.json inside WSL",
                     "https://docs.augmentcode.com/cli/integrations", mac_location="~/.augment/settings.json",
                     sources=("https://docs.augmentcode.com/cli/setup-auggie/install-auggie-cli",), platforms=("darwin", "linux"),
                     note="Native Windows is not documented. A Windows Uoink path cannot be used unchanged inside WSL; no WSL launch recipe is claimed."),
    "factory-droid": recipe("json", "~/.factory/mcp.json", "https://docs.factory.com/harness/mcp",
                            note="Project .factory/mcp.json is also supported."),
    "qwen-code": recipe("json", "~/.qwen/settings.json", "https://qwenlm.github.io/qwen-code-docs/en/users/features/mcp/",
                        note="Project .qwen/settings.json is also supported."),
    "crush": recipe("crushrc", "~/.config/crush/crushrc", "https://github.com/charmbracelet/crush/blob/main/README.md", "command",
                    note="Current crushrc format uses Crush's built-in Bash interpreter on both platforms. Paste into the file, not PowerShell. XDG_CONFIG_HOME can override .config; project .crushrc or crushrc is also supported."),
    "antigravity": recipe("json", "~/.gemini/config/mcp_config.json", "https://www.antigravity.google/docs/mcp",
                          note="Current shared App/IDE/CLI config. Project .agents/mcp_config.json is also supported. IDE: MCP Servers > Manage MCP Servers > View raw config."),
    "chatbox": recipe("text", "Settings > MCP > Add Server > Local (stdio)",
                      "https://api.chatboxai.app/en/guide/work-mode/configuration", guide=UI_FIELDS,
                      note="Desktop only. Test the connection before saving, then enable the server."),
    "dive": recipe("json", "MCP server settings JSON editor", "https://github.com/OpenAgentPlatform/Dive/blob/main/MCP_SETUP.md",
                   note="Merge the uoink server into mcpServers and enable it. No filesystem path is claimed."),
    "perplexity": recipe("text", "Local MCP is not supported on Windows",
                         "https://www.perplexity.ai/help-center/en/articles/11502712-local-and-remote-mcps-for-perplexity",
                         mac_location="Mac app > Plugins > Add custom > Simple (local MCP)", platforms=("darwin",),
                         guide="Install the PerplexityXPC helper from the Mac app's local MCP setup.\nAdd a custom local connector; in the Simple tab enter name uoink and command:\n<SHELL_COMMAND>\nSave, wait for Running, then enable it under Sources. Local MCP is Mac-only;\nremote connectors in the web app cannot launch this command."),
}


def client_spec(client: str) -> Client:
    spec = CLIENTS[client]
    if sys.platform == "darwin":
        location = spec.mac_location
        if location.startswith("~/") and " (" not in location:
            location = str(Path(location).expanduser())
        return replace(spec, location=location)
    return spec


def require_platform(client: str) -> None:
    spec = CLIENTS[client]
    if sys.platform not in spec.platforms:
        names = {"win32": "Windows", "darwin": "macOS", "linux": "Linux"}
        supported = ", ".join(names[p] for p in spec.platforms)
        raise ValueError(f"{client}: no recipe for {names.get(sys.platform, sys.platform)}. "
                         f"Documented platforms: {supported}. {spec.note}")


def client_table() -> str:
    """Generated into the guide and the distributable kit, including audit gaps."""
    rows = ["| Client | Platforms | Windows location or route | macOS location or route | Verified docs | Official source | Checked |",
            "|---|---|---|---|---|---|---|"]
    for name, spec in CLIENTS.items():
        platforms = ", ".join(label for key, label in (("win32", "Windows"), ("darwin", "macOS")) if key in spec.platforms)
        status = "Yes" if spec.verified else "No: " + spec.reason
        links = ", ".join(f"[docs {i + 1}]({url})" for i, url in enumerate(spec.sources))
        rows.append(f"| `uoink connect {name}` | {platforms} | {spec.location} | {spec.mac_location} | {status} | {links} | {spec.checked} |")
    return "\n".join(rows) + "\n"

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
        from _platform import MAC_BUNDLE_PYTHON
        bundled = resources.parent / MAC_BUNDLE_PYTHON
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
    require_platform(client)
    spec = client_spec(client)
    entry = server_entry(client, app_dir, python, isolation_args)
    command, args, env = entry["command"], entry["args"], entry["env"]
    if spec.format == "text":
        launcher = str((app_dir / "cli" / "uoink.cmd").resolve())
        resources = bundle_resources(app_dir)
        if resources is not None:
            launcher = str(resources.parent / "Helpers/uoink")
        if client == "autohotkey":
            launcher = launcher.replace("`", "``").replace("'", "`'")
        shell_command = shlex.join(["/usr/bin/env", *(f"{k}={v}" for k, v in env.items()), command, *args])
        return (spec.guide.replace("<ENTRY>", json.dumps(entry, indent=2, ensure_ascii=False))
                .replace("<CLI>", launcher).replace("<CLI_COMMAND>", shlex.quote(launcher))
                .replace("<SHELL_COMMAND>", shell_command))
    if spec.format == "shell":
        # PowerShell single quotes preserve spaces, $, backticks and apostrophes.
        quote = (lambda s: "'" + s.replace("'", "''") + "'") if sys.platform == "win32" else shlex.quote
        return ("claude mcp add --scope user "
                "-e PYTHONIOENCODING=utf-8 -e PYTHONUTF8=1 --transport stdio uoink -- "
                + " ".join(quote(s) for s in [command, *args]))
    if spec.format == "crushrc":
        return shlex.join(["mcp", "add", "uoink", "--command", command, "--args", *args,
                           *(part for key, value in env.items() for part in ("--env", key, value))])
    if spec.format == "toml":
        return ("[mcp_servers.uoink]\ncommand = " + json.dumps(command, ensure_ascii=False)
                + "\nargs = " + json.dumps(args, ensure_ascii=False)
                + "\n\n[mcp_servers.uoink.env]\n"
                + "\n".join(f"{key} = {json.dumps(value)}" for key, value in env.items()))
    if spec.shape == "list":
        return json.dumps({"name": "Uoink", "version": "1.0.0", "schema": "v1",
                           "mcpServers": [{"name": "uoink", **entry}]}, indent=2, ensure_ascii=False)
    if spec.shape == "entry":
        return json.dumps(entry, indent=2, ensure_ascii=False)
    if spec.shape == "servers" or client == "librechat":
        entry = {"type": "stdio", **entry}
    elif spec.shape == "extensions":
        entry = {"name": "uoink", "type": "stdio", "enabled": True,
                 "cmd": command, "args": args, "envs": env, "timeout": 300}
    elif spec.shape == "mcp":
        entry = {"type": "local", "command": [command, *args],
                 "environment": env, "enabled": True}
    elif client == "copilot-cli":
        entry = {"type": "local", **entry, "tools": ["*"]}
    elif client == "factory-droid":
        entry = {"type": "stdio", **entry}
    elif client == "dive":
        entry = {**entry, "enabled": True}
    return json.dumps({spec.shape: {"uoink": entry}}, indent=2, ensure_ascii=False)
