# Uoink `.mcpb` one-click Claude Desktop bundle

`.mcpb` (MCP Bundle, formerly DXT / "Desktop Extension") is Anthropic's package
format for one-click MCP server installation in Claude Desktop. This doc covers
how Uoink's bundle is designed, built, and released.

- **Spec:** https://github.com/modelcontextprotocol/mcpb (`MANIFEST.md`, manifest_version `0.4`)
- **Bundle source:** [`.mcpb/manifest.json`](../.mcpb/manifest.json), [`.mcpb/README.md`](../.mcpb/README.md)
- **Build scripts:** [`scripts/build-mcpb.ps1`](../scripts/build-mcpb.ps1) (primary), [`scripts/build-mcpb.sh`](../scripts/build-mcpb.sh)
- **Output:** `dist/uoink-<version>.mcpb`

## What a `.mcpb` is

A `.mcpb` file is a plain **ZIP archive** with `manifest.json` at its root. Claude
Desktop reads the manifest, prompts the user for any `user_config` values, and
writes the resulting `mcpServers` entry into its own config — no manual JSON
editing.

## Design decision: thin launcher, not self-contained

The mcpb spec assumes a self-contained bundle (server code + dependencies zipped
together). Uoink's server can't practically be self-contained: `uoink_mcp.py`
imports `server.py`, `uoink_mcp_tools.py`, and dozens of sibling modules, plus
heavy runtime deps (yt-dlp, the MCP SDK, keyring, Whisper). All of that already
ships in the installed helper at `%LOCALAPPDATA%\Uoink`.

So Uoink's bundle is a **thin launcher**:

- `server.type` = `"python"`, `entry_point` = `uoink_mcp.py`.
- `mcp_config.command` = `${user_config.uoink_dir}/python/python.exe`
- `mcp_config.args` = `["${user_config.uoink_dir}/uoink_mcp.py"]`
- `mcp_config.env.PYTHONPATH` = `${user_config.uoink_dir}`
- `user_config.uoink_dir` is a `directory` field defaulting to
  `${HOME}/AppData/Local/Uoink` — which is exactly `%LOCALAPPDATA%\Uoink` on a
  standard install. The user only changes it if they installed elsewhere.

This resolves to Uoink's canonical working stdio command
(`server.py::_mcp_stdio_command`):

```
<install>\python\python.exe   <install>\uoink_mcp.py
```

The bundle carries reference copies of `uoink_mcp.py` and `uoink_mcp_tools.py`
(so `entry_point` resolves structurally) plus `icon.png`, but the **runtime**
always uses the installed copy. That keeps the bundle tiny and guarantees it
can never drift from the helper the user is actually running.

**Prerequisite:** the Uoink helper must be installed first
(https://uoink.app/install). This matches the product — the browser extension
already requires the helper — so it's not a new ask.

## Building

```powershell
# Windows (primary)
pwsh scripts\build-mcpb.ps1
```
```bash
# POSIX
bash scripts/build-mcpb.sh
```

Both scripts:
1. Validate `manifest.json` is valid JSON.
2. Assert the entry command matches the working stdio command
   (`…/python/python.exe … uoink_mcp.py`) and `entry_point == uoink_mcp.py`.
3. Stage `manifest.json`, `icon.png`, `README.md`, and reference `.py` files.
4. Pack with the official `mcpb` CLI if present (`npm i -g @anthropic-ai/mcpb`),
   otherwise fall back to ZIP + rename to `.mcpb` (identical container).

Output: `dist/uoink-<version>.mcpb`.

## Releasing

Attach `dist/uoink-<version>.mcpb` to the GitHub release. This same file is also
referenceable from the MCP Registry `server.json` as an `mcpb` package (see
`handoff/DISTRIBUTION-CHECKLIST-2026-07-07.md`).

## Verifying an install

1. `pwsh scripts\build-mcpb.ps1` → confirm `dist/uoink-<VERSION>.mcpb` exists
   (the script derives `<VERSION>` from the repo `VERSION` file).
2. Double-click it in Claude Desktop → accept the install dir → restart.
3. In Claude, confirm Uoink tools list and run `list_recent_uoinks`.
4. If it fails, run `python.exe uoink_mcp.py --doctor` from the install dir; the
   `mcp_stdio` self-check drives the same handshake (see
   [`surface-maps/mcp-stdio.md`](surface-maps/mcp-stdio.md)).
