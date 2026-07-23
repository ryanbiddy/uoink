# Surface map: `.mcpb` Claude Desktop bundle

The one-click Claude Desktop install path. Packages Uoink's stdio MCP server as
an `.mcpb` (MCP Bundle, formerly DXT) so users install it by double-clicking
instead of hand-editing `claude_desktop_config.json`.

## Files

| Path | Role |
|---|---|
| `.mcpb/manifest.json` | The bundle manifest (manifest_version `0.4`). Source of truth for the bundle. |
| `.mcpb/README.md` | User-facing install/usage doc, staged into the bundle. |
| `scripts/build-mcpb.ps1` | Primary build script (Windows). Validates + packs. |
| `scripts/build-mcpb.sh` | POSIX build script (parity). |
| `docs/mcpb-bundle.md` | Full build/design/release doc. |
| `dist/uoink-<version>.mcpb` | Build output (git-ignored; release asset). |

## Contract

- The bundle is a **thin launcher** (see `docs/mcpb-bundle.md` for why). It does
  NOT bundle Python or dependencies; it targets the installed Uoink helper.
- `manifest.server.mcp_config` MUST resolve to the working stdio command from
  `server.py::_mcp_stdio_command`:
  `<install>\python\python.exe  <install>\uoink_mcp.py`.
  Both build scripts assert this and fail the build if it drifts.
- `manifest.version` tracks the product `VERSION`. Two
  guards keep it from drifting (it was left at 3.2.8 during the 3.3.0 cycle):
  (1) both build scripts derive the bundle version from `VERSION` at build
  time and stamp the staged `manifest.json` with it, so
  `powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build-mcpb.ps1`
  always produces
  `dist/uoink-<VERSION>.mcpb`; and
  (2) `tests/test_release_version_v360.py` includes `.mcpb/manifest.json` in
  the cross-file version-parity contract, so CI fails if the committed value
  drifts from `VERSION`. Still bump `.mcpb/manifest.json` alongside the other
  version surfaces on release.
- `user_config.uoink_dir` default `${HOME}/AppData/Local/Uoink` == the standard
  Windows install location. If the installer ever changes the default install
  dir, update this default too.

## Dependencies / blast radius

- Depends on the stdio entry (`uoink_mcp.py`) staying importable on the bundled
  interpreter — guarded by `tests/test_c01_mcp_stdio.py` and `--doctor`'s
  `mcp_stdio` self-check (see `surface-maps/mcp-stdio.md`).
- Platform: `win32` only today (`compatibility.platforms`). Add `darwin` when the
  Mac helper ships, with a `platform_overrides` block for the mac paths.
- No CI job builds the bundle yet; it's a manual release step. If you add one,
  run `scripts/build-mcpb.ps1` and assert `dist/uoink-*.mcpb` exists + unzips
  with `manifest.json` at root.

## How it can regress

- Someone edits `_mcp_stdio_command` (renames the interpreter path or entry
  file) without updating the manifest → build scripts catch the mismatch.
- Someone changes the installer's default install dir → the `user_config`
  default silently points at nothing; the user must re-pick the dir. Keep them
  in sync.
