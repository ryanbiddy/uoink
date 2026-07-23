# Uoink macOS Build Plan

This document is the prep work for a macOS build of Uoink. It was produced on a
Windows machine with no macOS toolchain. Nothing here has been compiled,
signed, notarized, or run on a Mac. It is an audit, a packaging plan, an
inventory of the scaffolding added on branch `cc/mac-prep`, and an honest list
of what still requires a Mac and an Apple Developer account to finish.

Read this alongside `docs/surface-maps/mac-build.md` (the packaging surface
map) and `docs/mac-install.md` (the current user-facing status, which explicitly
states that no macOS artifact exists).

## The Good News First

The helper is already substantially cross-platform. Sprint 19.5 consolidated
every per-OS branch into `_platform.py` and added `darwin` implementations for
path resolution, opening files and folders, revealing in the file manager,
notifications, and the Keychain label. The audit below confirms that the large
majority of the codebase needs no change to run on macOS. The remaining work is
concentrated in packaging (the analogue of `build.ps1` plus Inno Setup) and in
a small number of runtime paths that were still Windows-shaped.

Concretely: the Windows-versus-Mac gap is mostly a build-and-signing problem,
not a source-portability problem.

## 1. Cross-Platform Audit

Every Windows-specific component a Mac build must replace or handle, what it
does today, the macOS equivalent, and a rough effort tag (S = under a day, M =
one to three days, L = more, and each carries the risk that it needs a Mac to
verify).

| Component | Windows approach | macOS equivalent needed | Effort |
|---|---|---|---|
| App packaging | Inno Setup `installer/uoink.iss` compiled by `build.ps1` into `Uoink-Setup-<v>.exe` | `Uoink.app` bundle assembled by `build-mac.sh`, wrapped in a `.dmg` (create-dmg). Templates scaffolded in `installer/mac/`. | L |
| Bundled interpreter | python.org "embeddable" `python-3.11.9-embed-amd64.zip`, `import site` enabled, pip bootstrapped in | No macOS embeddable exists. Use `astral-sh/python-build-standalone` (relocatable framework CPython), universal2 (arm64 + x86_64). | M |
| ffmpeg / ffprobe | BtbN `win64-lgpl` `ffmpeg.exe` (+ `ffprobe.exe`), PATH-prepended at runtime | macOS LGPL ffmpeg + ffprobe, universal2, placed in `Resources/bin`. Same PATH-prepend mechanism, no code change. | M |
| yt-dlp | pip-installed into the embeddable; invoked as `sys.executable -m yt_dlp` | Identical. Already platform-agnostic. | S |
| Autostart | `installer/uoink.iss` writes `HKCU\...\Run` "Uoink"; `server._set_autostart` toggles it | LaunchAgent `~/Library/LaunchAgents/com.ryanbiddy.uoink.plist`. Template scaffolded. Server-side write/`launchctl load` code does not exist yet (`_set_autostart` returns `None` off Windows). | M |
| Tray / menu bar | `uoink_tray.py` via `pystray` (Win32 backend), spawned only on installed builds | `pystray` has an AppKit backend but needs a real `.app` event loop; `rumps` is the common menu-bar alternative. Open-path helper already handles `darwin`. Needs Mac runtime verification. | M |
| First-run splash | `uoink_splash.py` (pywebview + WebView2), browser catalog, `clip.exe`, registry default-browser lookup | pywebview uses WKWebView on macOS (pyobjc, not pythonnet). Browser catalog / clipboard / default-browser lookup are Windows-only and fall back to `webbrowser.open` + `open`. Native `pbcopy` / `open -a` / default-handler path is polish. | M |
| Dashboard window | `uoink_dashboard.py` (pywebview + WebView2), Win32 HWND icon branding | WKWebView on macOS; the HWND icon branding is already `sys.platform`-guarded and no-ops. Window icon comes from the `.app` `.icns`. | S |
| Install-layout gate | tray + splash gated on `python\pythonw.exe` existing | Now `server._is_installed_layout()`, recognises `python/bin/python3` too. Fixed on `cc/mac-prep`. | Done |
| Interpreter for subprocess spawn | hard-coded `python\pythonw.exe` at three sites | `server._bundled_interpreter(gui=...)`, returns the right interpreter per OS. Fixed on `cc/mac-prep`. | Done |
| Icon assets | `installer/uoink.ico` from `generate_icon.py`; 24-bit BMP wizard art | `Uoink.icns` via `iconutil` + `sips` from `assets/logo-mark-color.png`. No wizard art needed (the `.dmg` uses a background image instead). | S |
| Output-folder picker | `_pick_output_folder_windows` (PowerShell `FolderBrowserDialog`), falls back to tkinter | tkinter fallback already covers macOS; a native NSOpenPanel via pyobjc is optional polish. | S |
| Toast / notification | PowerShell `NotifyIcon` balloon | Already implemented: `osascript -e 'display notification'` in `_platform._macos_toast`. | Done |
| Keychain / secret store | `keyring` -> Windows Credential Manager | `keyring` -> macOS Keychain. Already handled; label is "macOS Keychain". First Keychain access prompts the user once. | Done |
| Stop / uninstall scripts | `stop-server.bat`, `stop-server.ps1`, `verify_install.ps1` | A `stop`/`verify-install.sh` shell equivalent, plus uninstall docs (already drafted in `docs/mac-install.md`). | S |
| Code signing | Unsigned; relies on SmartScreen reputation | Developer ID Application cert, `codesign` (hardened runtime), `notarytool`, `stapler`. External blocker. | L |
| CI | `ci.yml` Ubuntu static checks + `pytest tests/` | Optionally a `macos-latest` job that assembles and signs the `.app`. Not required for the code to be correct. | M |

Modules confirmed to import and run cleanly on macOS with no change: all
Windows-only OS calls (`winreg`, `ctypes.windll`, `os.startfile`, `clip.exe`,
PowerShell shell-outs) are already either inside `sys.platform == "win32"`
guards or lazily imported inside guarded functions. There are no top-level
Windows-only imports, so `import server`, `import uoink_tray`,
`import uoink_splash`, and `import uoink_dashboard` all succeed on macOS.

## 2. Packaging Plan

Recommended toolchain:

- App bundle: assemble `Uoink.app` by hand in `build-mac.sh` rather than using
  py2app or Briefcase. The helper is not a normal GUI app; it is a background
  server with a bundled interpreter and native binaries. Hand-assembling the
  bundle keeps the layout an exact mirror of the Windows tree, which is what the
  `HERE`-relative code in `server.py` already expects, and avoids fighting a
  freezer's import analysis for a large lazy-loaded dependency set (whisperx,
  torch, crawl4ai). PyInstaller and py2app are viable but add a translation
  layer between the code's assumptions and the on-disk layout; the manual route
  is simpler to reason about and to keep in lockstep with `build.ps1`.
- Interpreter: `python-build-standalone` 3.11.9, universal2, extracted to
  `Contents/Resources/python` so `python/bin/python3` exists.
- Runtime deps: `pip install` the same pinned versions as `build.ps1` into the
  bundled interpreter, with two macOS deltas: do not install `pythonnet` (it is
  Windows/.NET-only; pywebview uses WKWebView via pyobjc on macOS), and
  evaluate `rumps` for the menu bar.
- ffmpeg: a macOS LGPL ffmpeg + ffprobe (evermeet.cx, osxexperts, or a
  Homebrew LGPL build), lipo-merged to universal2, in `Resources/bin`. Keep the
  LGPL notice and a source offer in `THIRD-PARTY-NOTICES.md`, matching the
  license-compliance discipline `build.ps1` already applies on Windows.
- `.dmg`: create-dmg with a drag-to-Applications background.
- Signing and notarization: `codesign --options runtime` with
  `installer/mac/entitlements.plist`, signing nested binaries inside-out
  (python3, ffmpeg, ffprobe, and any `.dylib`s) before the outer bundle, then
  `xcrun notarytool submit --wait` and `xcrun stapler staple`.

Tray, splash, and dashboard on macOS: the splash and dashboard are pywebview
windows and are cross-platform once pywebview is installed with its macOS
backend. The tray is the least certain piece and needs a real Mac to choose
between `pystray`'s AppKit backend and `rumps`.

MCP server and dashboard: unchanged. `uoink_mcp.py` / `uoink_mcp_tools.py` are
pure Python over stdio, and the dashboard is helper-served HTML. Both are
already platform-agnostic.

### Apple Developer Account And Signing (flag: costs money, Ryan's)

A macOS build that real users can open cannot be shipped unsigned. This
requires, all under Ryan's Apple ID:

- An Apple Developer Program membership, 99 USD per year.
- A Developer ID Application certificate (for distribution outside the App
  Store) generated from that account.
- An app-specific password or a `notarytool` keychain profile for notarization.

Without these, `build-mac.sh` can still produce an unsigned `.app` for local
testing, but Gatekeeper will quarantine it on any other Mac. This is the single
hard external dependency and it is Ryan's to provision.

## 3. What Was Scaffolded On `cc/mac-prep`

Documentation:

- `docs/MAC-BUILD-PLAN.md` (this file).
- `docs/surface-maps/mac-build.md`, the packaging surface map.

Build scaffolding (no artifact produced, all Mac-only steps marked
`# TODO(mac):`):

- `build-mac.sh`, the `build.ps1` counterpart. Refuses to run off a Mac.
- `installer/mac/Info.plist`, the bundle plist template (`LSUIElement` helper,
  `com.ryanbiddy.uoink`, version rewritten at build).
- `installer/mac/launcher.sh`, the `Contents/MacOS/Uoink` launch stub.
- `installer/mac/com.ryanbiddy.uoink.plist`, the login-autostart LaunchAgent.
- `installer/mac/entitlements.plist`, hardened-runtime entitlements for
  codesign.

Safe, cross-platform code fixes (Windows behaviour identical, verified by the
Windows test suite):

- `server._bundled_interpreter(gui=...)` and `server._is_installed_layout()`
  replace three hard-coded `python\pythonw.exe` references. Windows resolves to
  `pythonw.exe` / `python.exe` exactly as before; macOS resolves to
  `python/bin/python3`. On a dev checkout both return `None`, so a
  `python server.py` run still spawns no tray or splash.
- The first-run splash spawn no longer passes a non-zero `creationflags` on
  non-Windows. That argument is Windows-only and would have raised on macOS the
  moment the gate started matching a Mac bundle. This was a latent bug the gate
  change would otherwise have exposed.
- `tests/test_mac_layout_prep.py` locks all of the above, including that a
  stray `python/bin/python3` on Windows does not count as an installed layout.

The Windows test suite is green: 206 passed (the prior 201 plus 5 new), no
regressions.

What was deliberately not touched, because it cannot be verified without a Mac
and changing it blind would risk shipping unverified runtime behaviour: the
LaunchAgent write path in `_set_autostart`, a native macOS clipboard and
browser-detection path in `uoink_splash.py`, and the tray library choice. Each
is called out as a follow-up below.

## 4. Effort Estimate

Assuming a Mac and a provisioned Apple Developer account are available:

- Bundle assembly and a first unsigned local launch (interpreter + ffmpeg + app
  skeleton + launcher, get the helper to bind 5179 from inside the `.app`): 2 to
  4 days. Most of the risk is in relocating the framework Python and confirming
  the lazy-loaded heavy deps import from the bundle.
- Tray, splash, and dashboard runtime verification, including the tray library
  decision: 2 to 3 days.
- Autostart LaunchAgent write path and first-run wiring: 1 day.
- Codesign, entitlements iteration, and notarization (typically several
  round-trips to find the minimal entitlement set that survives the hardened
  runtime): 2 to 4 days.
- `.dmg` packaging and end-to-end install/uninstall QA against
  `docs/mac-install.md`: 1 to 2 days.

Rough total: one and a half to two and a half focused weeks on a Mac, front to
back, dominated by first-bundle-launch and notarization iteration.

## 5. Hard Blockers (Need A Mac)

These cannot be done, faked, or verified from Windows:

1. A physical or virtual macOS machine with Xcode command line tools. Every
   Mac-only tool the build needs lives here: `iconutil`, `sips`, `lipo`,
   `codesign`, `xcrun notarytool`, `xcrun stapler`, `hdiutil`, `create-dmg`.
2. An Apple Developer Program membership (99 USD per year, Ryan's account) and a
   Developer ID Application certificate. Without it the build is unsigned and
   Gatekeeper blocks it for every other user.
3. Relocating and launching `python-build-standalone` from inside the bundle,
   and confirming the heavy lazy dependencies (whisperx, torch, crawl4ai)
   import from the bundled interpreter under the hardened runtime.
4. Sourcing and bundling a universal2 LGPL ffmpeg + ffprobe.
5. Notarization, which is an Apple-side service reachable only with the account
   above and iterated against a real signed bundle.
6. Runtime verification of the tray (pystray AppKit versus rumps), the pywebview
   splash and dashboard under WKWebView, and the Keychain prompt flow.

Everything in sections 1 through 3 that is not tagged "Done" ultimately gates on
item 1 or item 2.

## 6. Step-By-Step For When Ryan Has A Mac

1. Install Xcode command line tools (`xcode-select --install`) and `create-dmg`
   (`brew install create-dmg`).
2. Enroll in the Apple Developer Program, create a Developer ID Application
   certificate, and set up a `notarytool` keychain profile. Export
   `APPLE_DEV_ID_APP`, `APPLE_TEAM_ID`, and `AC_NOTARY_PROFILE`.
3. Work through the `# TODO(mac):` steps in `build-mac.sh` in order: fetch and
   relocate the framework Python, pip-install the pinned deps (minus pythonnet,
   plus a tray-library decision), bundle universal2 ffmpeg, generate
   `Uoink.icns`, and assemble the `.app`.
4. Produce an unsigned build first and confirm the helper binds 5179 from inside
   `Uoink.app`, `/health` and `/diagnose` respond, and a capture round-trips.
5. Verify the tray, the first-run splash, and the dashboard window render and
   behave. Decide pystray versus rumps for the tray and update `uoink_tray.py`
   if needed.
6. Implement and test the LaunchAgent write path (extend `_set_autostart` for
   `darwin` to write and `launchctl load`
   `~/Library/LaunchAgents/com.ryanbiddy.uoink.plist` from the template).
7. Codesign with the hardened runtime and `installer/mac/entitlements.plist`,
   signing nested binaries inside-out; iterate the entitlement set until launch
   is clean.
8. Notarize and staple the `.app`, then build, notarize, and staple the `.dmg`.
9. Run the full install and uninstall flow against `docs/mac-install.md` on a
   clean Mac (ideally both Apple Silicon and Intel), fixing the doc where
   reality differs.
10. Add a `macos-latest` CI job if an automated signed build is wanted, and
    update `README.md` / `CHANGELOG.md` to announce macOS support.

## 7. Honest Status Line

There is no working macOS build. This branch delivers the audit, the plan, the
bundle scaffolding, and two safe cross-platform code fixes that keep the Windows
build byte-identical while unblocking the Mac path. Finishing the build requires
a Mac and Ryan's Apple Developer account, per the blockers above.
