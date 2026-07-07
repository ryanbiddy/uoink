# Uoink — Claude Desktop MCP bundle

This bundle connects **Claude Desktop** to Uoink's local MCP server in one click,
so you don't have to hand-edit `claude_desktop_config.json`.

## Install

1. Install the Uoink helper first from **https://uoink.app/install** (Windows 10/11).
   The helper carries the bundled Python interpreter and all dependencies this
   bundle launches.
2. Double-click `uoink-<version>.mcpb` (or drag it into **Claude Desktop →
   Settings → Extensions**).
3. When prompted for the **Uoink install directory**, accept the default
   (`%LOCALAPPDATA%\Uoink`) unless you installed Uoink somewhere else.
4. Restart Claude Desktop. Uoink's tools (`uoink_video`, `search_uoinks`,
   `find_mentions`, …) appear automatically.

## What this bundle is (and isn't)

It's a **thin launcher**. At runtime it runs the working stdio command:

```
<install>\python\python.exe  <install>\uoink_mcp.py
```

against your **already-installed** Uoink helper — that's where the sibling
modules and heavy dependencies (yt-dlp, the MCP SDK, keyring, Whisper, …) live.
The bundle itself only carries the manifest, an icon, and reference copies of
the two entry modules. It does **not** bundle a second Python runtime, so it
stays tiny and can never drift from your installed helper.

If you'd rather configure the server by hand, or use Cursor / Cline / Continue,
see https://uoink.app/developers.

## Rebuilding

```
# Windows
pwsh scripts/build-mcpb.ps1
# POSIX
bash scripts/build-mcpb.sh
```

Output lands in `dist/uoink-<version>.mcpb`. See
[`docs/mcpb-bundle.md`](../docs/mcpb-bundle.md) for the full build + release notes.
