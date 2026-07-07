# macOS Build And Packaging Surface Map

This map describes the macOS packaging surface as scaffolded on branch
`cc/mac-prep`. It is the counterpart to `installer-firstrun.md`, which covers
the shipped Windows installer. No macOS artifact has been built or tested yet;
this documents the intended layout and the files that exist to support it. The
authoritative plan, effort estimate, and blocker list live in
`docs/MAC-BUILD-PLAN.md`.

## Scope

The Windows product ships as an Inno Setup `.exe` that installs a bundled
Python, ffmpeg, and the helper source under `%LOCALAPPDATA%\Uoink`. The macOS
product ships the same helper as a `Uoink.app` bundle inside a `.dmg`. The
helper code, the loopback HTTP API, the MCP server, the dashboard, and the
Chrome extension are cross-platform and do not change between the two.

## Files In This Repo

Build orchestrator:

- `build-mac.sh` at the repo root is the macOS counterpart to `build.ps1`. It
  is a skeleton: every macOS-only step is marked `# TODO(mac):` and the script
  refuses to run off a Mac. It produces no artifact yet.

Bundle templates under `installer/mac/`:

- `Info.plist` is the `Contents/Info.plist` template. It sets `LSUIElement`
  true so Uoink is a menu-bar/background helper with no Dock icon, matching the
  Windows tray-only presence. `CFBundleIdentifier` is `com.ryanbiddy.uoink`.
- `launcher.sh` is the `Contents/MacOS/Uoink` launch stub. It sets the working
  directory to `Contents/Resources` and execs the bundled `python3` on
  `server.py`, so the `HERE`-relative layout resolves the same as on Windows.
- `com.ryanbiddy.uoink.plist` is the LaunchAgent template for login autostart,
  the macOS equivalent of the Windows `HKCU\...\Run` value.
- `entitlements.plist` is the hardened-runtime entitlements template used at
  codesign time.

## Intended Installed Layout

Windows installs a flat tree under `%LOCALAPPDATA%\Uoink`. macOS nests the same
tree inside the app bundle:

```
Uoink.app/
  Contents/
    Info.plist                 <- installer/mac/Info.plist (version rewritten)
    MacOS/
      Uoink                     <- installer/mac/launcher.sh
    Resources/
      python/                   <- relocatable framework Python (bin/python3)
      bin/                      <- ffmpeg, ffprobe (LGPL, universal2)
      server.py, index.py, _platform.py, ...   <- the helper source tree
      helper/, uoink_core/, skills/, voice_dna/, assets/, defaults/,
      migrations/, extension/
      Uoink.icns
```

The launcher runs `Resources/python/bin/python3 Resources/server.py`. This
exact path is why `server.py`'s `_bundled_interpreter()` looks for
`python/bin/python3` on non-Windows layouts.

## Runtime Data Locations

These are already implemented cross-platform in `_platform.py` and need no new
code:

- User data (`index.db`, `settings.json`, `server.log`, `token.txt`,
  `.first-run-done`): `~/Library/Application Support/Uoink`.
- Uoinked corpora output: `~/Desktop/Uoink`.
- API key: macOS Keychain via the `keyring` package, service `Uoink`.

## Interpreter, ffmpeg, And PATH

`server.py` prepends `HERE/bin` to `PATH` at import when that directory exists,
then invokes `ffmpeg` by bare name. This mechanism is identical on macOS; only
the bundled binary differs (a macOS LGPL ffmpeg instead of the BtbN Windows
build). `yt-dlp` runs as `sys.executable -m yt_dlp`, which is already
platform-agnostic.

## Tray, Splash, And Dashboard Gate

On Windows the ambient tray and the first-run splash are gated on the presence
of the bundled interpreter. Before `cc/mac-prep` that gate hard-coded
`python\pythonw.exe`, so it was permanently false on any non-Windows layout and
the tray plus splash were dead. The gate now runs through
`server._is_installed_layout()`, which recognises both the Windows
(`python\pythonw.exe`) and macOS (`python/bin/python3`) bundle layouts. The
three subprocess spawn sites (dashboard window, splash, tray) resolve their
interpreter through `server._bundled_interpreter(gui=...)`, and the splash
spawn no longer passes a Windows-only non-zero `creationflags` on macOS.

The behaviour change is Windows-identical: the macOS branch can only match when
a macOS bundle actually exists on disk. `tests/test_mac_layout_prep.py` locks
this, including the case that a stray `python/bin/python3` on a Windows box
does not count as installed.

The tray itself (`uoink_tray.py`) already handles `darwin` in its open-path
helper and uses `pystray`, whose macOS backend needs a running app event loop.
Whether `pystray` renders correctly from inside the `.app`, or whether `rumps`
is the better menu-bar library, is an open runtime question flagged in the
plan. Nothing about the tray has been verified on a Mac.

## Splash Browser Guidance On macOS

`uoink_splash.py`'s browser catalog, clipboard copy, and default-browser lookup
are Windows-only (registry `UserChoice`, `clip.exe`, `PROGRAMFILES` executable
paths). On macOS these return empty and the splash falls back to
`webbrowser.open`. A native macOS path (`pbcopy` for clipboard, `open -a` and
`/Applications` detection for browsers, the `LSCopyDefaultHandler` default) is
listed as a polish item in the plan, not a blocker.

## Signing And Distribution

Unlike the Windows build, which currently ships unsigned and relies on
SmartScreen reputation, a macOS build cannot be distributed unsigned in
practice. Gatekeeper quarantines an unsigned or un-notarized `.app`. Shipping
requires an Apple Developer account, a Developer ID Application certificate,
`codesign` with the hardened runtime, `notarytool` submission, and `stapler`.
This is the hard external blocker; see `docs/MAC-BUILD-PLAN.md`.

## What Is NOT Scaffolded

- The `.icns` icon generation (needs `iconutil` and `sips`, macOS-only).
- A `verify-install.sh` equivalent of `verify_install.ps1`.
- The first-run code that writes and loads the LaunchAgent (server-side).
- Any CI job that builds the `.app` (the current `ci.yml` is Ubuntu-only static
  checks plus the stdlib test suite).
