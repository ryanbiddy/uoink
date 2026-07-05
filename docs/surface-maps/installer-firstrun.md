# Installer And First-Run Surface Map

The Windows installer is built from `installer/uoink.iss` through `build.ps1`. The build script stages the app under `installer/staging`, regenerates wizard art, rewrites `#define AppVersion`, then runs Inno Setup. After install, first-run setup moves through the local helper, splash window, tray, and dashboard.

## Installer Pages

Welcome:

- The stock Inno welcome page is skipped.
- `BuildWelcomePage()` creates the branded page.
- Labels are positioned with `ScaleY()` so 125 percent and 150 percent display scaling do not clip the headline or body copy.
- The page uses the cream surface color from the installer palette.
- The fake `STEP 1 OF 4` tracker was removed.
- The first-page Next button is widened to 112 scaled pixels, right-aligned, and labeled `Let's go ->`.
- When the wizard leaves the Welcome page, the default Next button caption, width, left edge, and Back button are restored.

Directory and Ready:

- These are stock Inno pages with Uoink copy from `[Messages]`.
- `UpdateReadyMemo()` prints the chosen install path on the Ready page.

Migration:

- `BuildMigratePage()` creates a legacy-install note for machines with the old local folder.
- `ShouldSkipPage()` hides it on clean installs.

Finish:

- The finish copy points users at the Uoink browser-button setup window.
- The checked finish action starts `server.py` without `--show-dashboard`.
- The dashboard is not forced open from the installer finish page.

## Verification

`CurStepChanged(ssPostInstall)` calls `VerifyInstalledHelper()`.

That procedure runs `installer/verify_install.ps1` as a files-only check. It does not launch `pythonw.exe`, does not start `server.py`, and does not probe `/health` unless a caller passes `-ProbeHealth` to the PowerShell script.

Verification checks:

- `VERSION` matches the expected installer version.
- Required top-level modules exist in the installed app folder.
- Required defaults exist under `defaults`.

Failure state:

- Setup logs the warning.
- The user may see an informational warning with the log location.
- Setup never raises after files are already copied.

## First Run After Finish

When the user keeps `Set up the browser button now` checked, Inno starts the helper once the wizard reaches the finish step.

Runtime order:

1. `server.py` starts the loopback helper.
2. The tray starts if pystray is available.
3. If `.first-run-done` does not match the current version, the splash subprocess starts.
4. While that splash is visible, the regular ready toast is skipped.
5. The splash owns browser-button setup. The dashboard opens later by user action or first capture.

This keeps first run to one primary window after the wizard closes.

## Splash Wrapper

`uoink_splash.py` is launched as a subprocess by `server.py` when the once-per-version sentinel is missing or stale. It opens `http://127.0.0.1:5179/splash` in a frameless pywebview window.

Native API:

- `extension_status()` returns the installed extension folder, manifest state, extension-loaded sentinel state, preferred browser, and detected browser list.
- `open_extensions_page(browser_id)` opens the matching browser extension settings page.
- `copy_extension_path()` copies the installed extension folder.
- `mark_extension_loaded()` writes the extension sentinel and dismisses the splash.
- `open_dashboard()` and `open_settings()` open dashboard windows and dismiss the splash.
- `close()` and `minimize()` are explicit dismiss actions and write the once-per-version splash sentinel.

Auto-close:

- The 8-second linger closes the splash window without writing `.first-run-done`.
- The sentinel is written only by explicit user actions that call `_dismiss()`, including close, minimize, opening dashboard/settings, or marking extension setup complete.

## Browser Guidance

The native wrapper detects the default HTTPS browser on Windows through the `UrlAssociations\https\UserChoice` registry key. It maps common Chromium browsers to their extension pages:

- Microsoft Edge, `edge://extensions/`
- Chrome, `chrome://extensions/`
- Brave, `brave://extensions/`
- Vivaldi, `vivaldi://extensions/`
- Opera GX, `opera://extensions/`
- Arc, `arc://extensions/`

If no supported browser is detected, the splash falls back to `your Chromium browser` with `chrome://extensions/` and keeps the Copy path button visible.

## Splash HTML

`assets/splash/index.html` asks the native API for extension status before it checks key status.

Extension mode:

- The headline names the detected browser.
- The primary button opens that browser's extension settings page.
- Steps show the matching extension URL, Developer mode, Load unpacked, and the installed extension folder.
- Copy path remains the universal fallback.

Other modes:

- Missing-key and bad-key modes send users to Settings.
- Happy mode offers YouTube and Dashboard.
- Failure mode points at diagnostics.

## Tray Menu

`uoink_tray.py` owns the Windows tray menu.

The stop action appears once as `Quit Uoink`. It calls `_on_stop()`, hides the icon, stops pystray, and asks the helper to shut down.

## Wizard Art

`installer/generate_bitmaps.py` writes 24-bit BMP files at 100, 125, 150, and 200 percent scale.

Large art:

- `wizard-large-100.bmp`
- `wizard-large-125.bmp`
- `wizard-large-150.bmp`
- `wizard-large-200.bmp`

Small art:

- `wizard-small-100.bmp`
- `wizard-small-125.bmp`
- `wizard-small-150.bmp`
- `wizard-small-200.bmp`

`installer/uoink.iss` references those files as comma lists in `WizardImageFile` and `WizardSmallImageFile`. The BMPs are ignored in git because `build.ps1` regenerates them before Inno compiles.

## Regression Checks

`tests/test_u11_installer_overhaul.py` guards:

- post-install verification does not spawn UI
- verification is files-only by default
- install verification is non-fatal
- finish launch does not force the dashboard
- welcome labels are DPI-safe
- the fake step tracker stays gone
- first-run splash suppresses the ready toast
- multi-scale wizard art is referenced and generated

`tests/test_u12_first_run_polish.py` guards:

- browser detection data includes per-browser extension URLs
- extension status returns browser metadata
- auto-close does not write the splash sentinel
- explicit close still writes the splash sentinel
- splash HTML has no Chrome-only setup copy
- the tray menu has one quit action and no duplicate stop row
