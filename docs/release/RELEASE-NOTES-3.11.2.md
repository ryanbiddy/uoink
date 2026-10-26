# Uoink 3.11.2

## What's new

- **Uoink for Mac (preview).** Apple Silicon Macs on macOS 15 or later can now run Uoink. The app and the DMG are signed with a Developer ID and notarized by Apple, so macOS only asks its usual question about apps downloaded from the internet. On a Mac, the dashboard and setup steps say Mac things: Finder, Applications, and the ⌘⇧G trick for Chrome's **Load unpacked** picker, which hides `~/Library`.
- **A failed save no longer breaks later saves.** A write that failed (for example on a duplicate folder name during startup) left the library's transaction open, and every save after it failed until the helper restarted. Each write now rolls back its own failure.
- **Re-capturing an older item updates it.** Capturing something saved by an older version refreshes that item instead of making a second folder. Duplicate folder names are skipped with one warning, and `uoink doctor` lists them.
- **Cleaner transcripts.** Captions that run past the end of the video are cut at the end, and YouTube's hard-space and censor markers are removed.
- **Long MCP requests get an answer.** A request over 64 KiB (for example a long note) is refused with its own ID, so the AI app stops waiting.
- **Setup splash fixes.** No white corners, the bottom button is no longer cut off, and the footnote no longer covers a button. Chrome is listed first and Comet is detected. When a browser won't open its extensions page from the splash, Uoink copies the address for you to paste.
- **Ready for the Chrome Web Store.** The helper already trusts Uoink's store listing ID, so the store version will connect once the listing is approved. Until then, the extension loads unpacked as before.
- Still 91 tools (35 in core mode).

## Install or update

**Windows 10/11**

1. Download `Uoink-Setup-3.11.2.exe` and `SHA256SUMS.txt`, then check the installer's SHA-256.
2. The Windows installer is unsigned, so SmartScreen may warn. Choose **More info -> Run anyway**.
3. New install: on first launch, use the setup splash to open `chrome://extensions` and copy the extension path. Turn on **Developer mode**, click **Load unpacked** and select that folder. Then click Chrome's puzzle-piece **Extensions** icon and pin **Uoink**.
4. Claude Desktop: install `uoink-3.11.2.mcpb`.
5. Claude Code: run `uoink connect claude-code` in a new terminal, then run the command it prints.

**Mac (Apple Silicon, macOS 15 or later; preview)**

1. Download `Uoink-3.11.2-macos-arm64.dmg` and check its SHA-256 against `SHA256SUMS.txt`.
2. Open the DMG, drag Uoink to Applications, eject the disk, then open Uoink from Applications.
3. In Chrome, open `chrome://extensions`, turn on **Developer mode** and click **Load unpacked**. The dashboard's **Get the extension** card copies the extension's folder path; in the picker, press ⌘⇧G, paste it and press Return.
4. Claude Desktop: install `uoink-3.11.2-macos.mcpb`.

See [docs/mac/INSTALL.md](https://github.com/ryanbiddy/uoink/blob/v3.11.2/docs/mac/INSTALL.md) for login startup, logs and uninstalling.

## Upgrading

- Your library and captures stay in place.
- Reload the Uoink extension in `chrome://extensions`.
- Claude Desktop: reinstall `uoink-3.11.2.mcpb` and restart Desktop.

## Known limits

- Chrome (tested). Edge and Brave may work but are not tested.
- Mac: Apple Silicon only. Uoink doesn't update itself yet, so install new versions from the DMG. Until 3.12, macOS shows Uoink's alerts as coming from Script Editor. Library mirroring is unavailable on Mac.
- The Whisper fallback needs a Whisper model you have already downloaded in Settings. Uoink never downloads one during a capture.

## Checksums

| File | SHA-256 |
| --- | --- |
| `Uoink-Setup-3.11.2.exe` | `81f7d385f300fc3964c7dd7239566fe7241718e18ef9858b9a84cc6cb841828d` |
| `uoink-3.11.2.mcpb` | `0a8973ad50348b8a9e7d17f58436edf5d0a4e9fcd0a46030aeef8e2f8673fb1b` |
| `Uoink-3.11.2-macos-arm64.dmg` | `e0645c3380f8877bed9f84b1ec1392a96664536010201ba39019b61f9a7d49ab` |
| `uoink-3.11.2-macos.mcpb` | `9476ac551bf0b6e3286aced4bda9ed97d91744c2789ad0ad864074623be5ae6f` |
