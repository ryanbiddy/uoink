# Installer And First-Run Surface Map

This map covers the first-run pieces that start after the Windows installer launches the local helper.

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

## Regression Checks

`tests/test_u12_first_run_polish.py` guards:

- browser detection data includes per-browser extension URLs
- extension status returns browser metadata
- auto-close does not write the splash sentinel
- explicit close still writes the splash sentinel
- splash HTML has no Chrome-only setup copy
- the tray menu has one quit action and no duplicate stop row
