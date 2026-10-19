# Uoink 3.9.3

HTTP MCP now flattens the three tool schemas with a top-level `oneOf`:
`claim_library_work`, `apply_reshelving` and `set_source_consent`. Clients
that pass these schemas to a model no longer drop Uoink's tools because of
their shape. Both MCP transports advertise the same schemas, and the server
still checks every call against the exact frozen contract.

Activity and Phase 5 measurement reads take less time on large libraries.
Across seven local runs per size, median time fell from 40.3 to 30.8 ms at
548 items, and from 461.4 to 285.5 ms at 10,000 items: 23% and 38% less time.
Results are byte-identical, and the 2-second deadline is unchanged. These
measurements are local, not a guarantee for every machine.

Uoink is now listed in the official MCP registry as `io.github.ryanbiddy/uoink`,
so MCP clients and directories that read the registry can find it.

This release makes no data or settings changes and adds no index or migration.
Installing over 3.9.2 keeps your library and saved captures.

## Installing

1. Download `Uoink-Setup-3.9.3.exe` from this release. Windows 10/11 is supported.
   The installer is unsigned, so SmartScreen may warn. Check the file's SHA-256
   against the value on this release page, then choose **More info -> Run anyway**.
2. Run the installer. It defaults to `%LOCALAPPDATA%\Uoink\` with no admin
   required. The finish page can launch the helper, and autostart runs it on login.
3. On first launch, use the setup splash to open `chrome://extensions` and copy
   the installed extension path. Turn on **Developer mode**, click **Load unpacked**,
   and select that folder. The Chrome Web Store listing is pending.
4. Click Chrome's puzzle-piece **Extensions** icon and pin **Uoink** so its
   button stays visible.

Chrome (tested); other Chromium browsers such as Edge and Brave may work but are not tested.

## After updating

Open `chrome://extensions` and reload the Uoink extension. If its ID changes,
reapply its preferences; your helper library and captures stay in place.

Claude Desktop users should reinstall `uoink-3.9.3.mcpb` and restart Desktop
to use the current bundle. If you connected Claude Desktop through
`claude_desktop_config.json` instead, restarting Desktop is enough. Cursor users may want `UOINK_MCP_TOOLSET=core` in their
MCP server environment. It keeps the previous 35-tool set for clients that
cap tool counts. Full mode is the default and keeps those 35 tools first.

## Setting up with an agent

An agent with a shell can install and connect Uoink. Verify the installer
against `SHA256SUMS.txt`, then install silently (per user, no admin):

```powershell
Start-Process -Wait -FilePath .\Uoink-Setup-3.9.3.exe -ArgumentList '/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART'
```

Connect Claude Code with absolute paths:

```powershell
claude mcp add --scope user --transport stdio uoink -e PYTHONIOENCODING=utf-8 -e PYTHONUTF8=1 -- "$env:LOCALAPPDATA\Uoink\python\python.exe" "$env:LOCALAPPDATA\Uoink\uoink_mcp.py"
```

The MCP connection works without the Uoink helper running. A silent install
does not start the helper; start **Uoink** from the Start menu for the
dashboard and the browser button. Loading the Chrome extension stays a manual
step for the person.

## Checksums

| File | SHA-256 |
| --- | --- |
| `Uoink-Setup-3.9.3.exe` | `<sha256 pending>` |
| `uoink-3.9.3.mcpb` | `<sha256 pending>` |
