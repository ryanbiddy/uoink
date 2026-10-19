# Uoink 3.10.0

Agents can now use `uoink` from a local shell to search your saved sources,
read evidence, capture URLs, save notes, and call any registry tool. Try
`uoink search "working memory" --limit 5` or `uoink recent --limit 10`.
Local reads work without the helper running. Capture and paid tools keep
their existing requirements and consent gates. The MCP server still exposes
91 tools by default.

The portable Uoink skill includes instructions for Claude Code, Codex, pi,
Hermes Agent, and OpenClaw. Use `uoink skill path` to find it, or
`uoink skill install --to <skills-directory>` to copy it with its references.
The Claude Code plugin marketplace at `ryanbiddy/uoink-agent-kit` is
published with this release. It bundles the skill and MCP config for a default install.

`uoink connect` provides setup recipes for 38 clients and integrations.
It prints config or instructions and tells you where they belong; it never
edits another app's settings. The dashboard's **Add to Cursor** and
**Add to VS Code** buttons open the client's review flow. See
[Connect your agent](../connect-your-agent.md) for recipes and known limits.

TODO-ORCH: Tested: Claude Code, Codex CLI, Gemini CLI, pi (see release notes)
This is a placeholder, not a test result. Replace it with confirmed client
results before release. Other recipes remain unverified unless stated here.

This release makes no data or settings changes besides the optional PATH
entry. There is no new index or migration. Installing over the previous
release keeps your library and saved captures.

## Installing

1. Download `Uoink-Setup-3.10.0.exe` from this release. Windows 10/11 is supported.
   The installer is unsigned, so SmartScreen may warn. Check the file's SHA-256
   against the value on this release page, then choose **More info -> Run anyway**.
2. Run the installer. It defaults to `%LOCALAPPDATA%\Uoink\` with no admin
   required. Leave **Add the uoink command to PATH for AI agents** checked
   to use `uoink` in new terminals, or uncheck it to keep User PATH unchanged.
   The finish page can launch the helper, and autostart runs it on login.
3. On first launch, use the setup splash to open `chrome://extensions` and copy
   the installed extension path. Turn on **Developer mode**, click **Load unpacked**,
   and select that folder. The Chrome Web Store listing is pending.
4. Click Chrome's puzzle-piece **Extensions** icon and pin **Uoink** so its
   button stays visible.

Chrome (tested); other Chromium browsers such as Edge and Brave may work but are not tested.

## After updating

Open `chrome://extensions` and reload the Uoink extension. If its ID changes,
reapply its preferences; your helper library and captures stay in place.

Claude Desktop users should reinstall `uoink-3.10.0.mcpb` and restart Desktop
to use the current bundle. If you connected Claude Desktop through
`claude_desktop_config.json` instead, restarting Desktop is enough. Cursor users may want `UOINK_MCP_TOOLSET=core` in their
MCP server environment. It keeps the previous 35-tool set for clients that
cap tool counts. Full mode is the default and keeps those 35 tools first.

## Setting up with an agent

An agent with a shell can install and connect Uoink. Verify the installer
against `SHA256SUMS.txt`, then install silently (per user, no admin):

```powershell
Start-Process -Wait -FilePath .\Uoink-Setup-3.10.0.exe -ArgumentList '/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART'
```

Open a new terminal for the updated PATH, then run:

```powershell
uoink status
uoink connect --list
uoink connect claude-code
```

Run the printed Claude Code command in PowerShell. For other clients, use
`uoink connect <client>` and merge the printed entry into the location shown
on stderr, then restart the client's MCP connection. For an existing shell,
use `& "$env:LOCALAPPDATA\Uoink\cli\uoink.cmd" status` at the default install path.
The [agent installation steps](../../llms-install.md) include checksum commands
and Cline's config location.

The MCP connection and local CLI reads work without the helper running.
A silent install does not start the helper; start **Uoink** from the Start
menu for the dashboard and the browser button. Loading and pinning the
Chrome extension remain steps for the person.

## Checksums

| File | SHA-256 |
| --- | --- |
| `Uoink-Setup-3.10.0.exe` | `<sha256 pending>` |
| `uoink-3.10.0.mcpb` | `<sha256 pending>` |
