# Uoink 3.9.2

Every Uoink tool is now available through the standard connection used by
Claude Desktop (.mcpb), Claude Code and Cursor: 91 tools, up from 35. Agents
can capture pages, X posts, Reddit threads, notes and images; use writing,
script and workspace tools; and work with sources and the Library queue.
Consent gates are unchanged.

This release makes no data or settings changes. Installing over 3.9.1 keeps
your library and saved captures.

## Installing

1. Download `Uoink-Setup-3.9.2.exe` from this release. Windows 10/11 is supported.
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

Claude Desktop users should reinstall `uoink-3.9.2.mcpb` and restart Desktop
to get the new tools. Cursor users may want `UOINK_MCP_TOOLSET=core` in their
MCP server environment. It keeps the previous 35-tool set for clients that
cap tool counts. Full mode is the default and keeps those 35 tools first.

## Checksums

| File | SHA-256 |
| --- | --- |
| `Uoink-Setup-3.9.2.exe` | `<sha256 pending>` |
| `uoink-3.9.2.mcpb` | `<sha256 pending>` |
