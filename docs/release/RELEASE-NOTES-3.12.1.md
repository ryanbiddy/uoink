# Uoink 3.12.1

## What's new

- **Share from your phone.** Uoink Relay is a phone inbox you deploy to your own Render account with one button. Share a link to it from an iOS Shortcut or an Android share target, and Uoink on your computer captures it the next time it checks, then deletes it from the relay. The relay holds only the link and an optional note, for up to 7 days. It is off until you set it up in Settings > Capture > **Phone inbox**. See [docs/relay.md](https://github.com/ryanbiddy/uoink/blob/v3.12.1/docs/relay.md).
- **Uoink from your launcher.** A Raycast extension (macOS and Windows), a Flow Launcher plugin (Windows), an Alfred workflow (macOS) and an Obsidian plugin search your library, copy citations that link to the timestamp, and save links. They are in `integrations/` and not in their stores yet. winget manifests and a Homebrew cask are in `packaging/`.
- **`uoink mcp`.** Any MCP client can start Uoink with `"command": "uoink", "args": ["mcp"]`, with no install path. On Windows, a client that cannot start `.cmd` files uses `cmd /c uoink mcp`.
- **Wikipedia works.** Wikipedia articles capture instead of failing as an empty JavaScript page, and they are titled with the article name instead of its short description.
- **Thumbnails for pages and X videos.** Captured web pages save their preview image as a thumbnail, and an X post with a video shows the video's poster. An X or Reddit video post opens in the reader as a video, with its transcript.
- **Newest first is newest first.** In a library that mixes videos with pages, posts or notes, the sort order no longer depends on your time zone.
- **Topics match whole words.** A page that says "average" no longer files under AI and ML for containing "RAG".
- **One set of buttons.** The dashboard, the extension popup, the setup page and the in-page Uoink buttons share one button style with visible hover, press, focus and disabled states in light and dark.
- Smaller fixes: italics in the article reader, Generate's Newsletter output no longer breaks mid-word, the sidebar shows one selected page, Settings links land on their section, and the Sources page offers **Allow <site>** when the allowlist turns a page away.
- Still 91 tools (35 in core mode).

## Install or update

**Windows 10/11**

1. Download `Uoink-Setup-3.12.1.exe` and `SHA256SUMS.txt`, then check the installer's SHA-256.
2. The Windows installer is unsigned, so SmartScreen may warn. Choose **More info -> Run anyway**.
3. New install: on first launch, use the setup splash to open `chrome://extensions` and copy the extension path. Turn on **Developer mode**, click **Load unpacked** and select that folder. Then click Chrome's puzzle-piece **Extensions** icon and pin **Uoink**.
4. Claude Desktop: install `uoink-3.12.1.mcpb`.
5. Claude Code: run `uoink connect claude-code` in a new terminal, then run the command it prints.

**Mac (Apple Silicon, macOS 15 or later; preview)**

1. Download `Uoink-3.12.1-macos-arm64.dmg` and check its SHA-256 against `SHA256SUMS.txt`.
2. Open the DMG, drag Uoink to Applications, eject the disk, then open Uoink from Applications.
3. In Chrome, open `chrome://extensions`, turn on **Developer mode** and click **Load unpacked**. The dashboard's **Get the extension** card copies the extension's folder path; in the picker, press ⌘⇧G, paste it and press Return.
4. Claude Desktop: install `uoink-3.12.1-macos.mcpb`.

See [docs/mac/INSTALL.md](https://github.com/ryanbiddy/uoink/blob/v3.12.1/docs/mac/INSTALL.md) for login startup, logs and uninstalling.

## Upgrading

- Your library and captures stay in place. Stored save times are unchanged; only the sort reads them differently.
- Reload the Uoink extension in `chrome://extensions`.
- Claude Desktop: reinstall the 3.12.1 `.mcpb` and restart Desktop.
- Wikipedia pages that failed before can be captured again.

## Known limits

- Chrome (tested). Edge and Brave may work but are not tested.
- Mac: Apple Silicon only. Uoink doesn't update itself yet, so install new versions from the DMG. macOS still shows Uoink's alerts as coming from Script Editor. Library mirroring is unavailable on Mac.
- The phone inbox needs a Render account and checks the relay every 5 minutes by default (Settings offers 2 to 30), so a shared link is captured the next time Uoink checks while it is running.
- The launcher integrations are not in the Raycast Store, Alfred Gallery, Flow Launcher plugin store or Obsidian community plugins yet.

## Checksums

| File | Size | SHA-256 |
| --- | --- | --- |
| `Uoink-Setup-3.12.1.exe` | 519,291,783 B | `2f258d36d23b5604e1d41e04ffd1bcf297e365dbe17b98d88d58be628632d071` |
| `uoink-3.12.1.mcpb` | 106,563 B | `e16d6a2021e51094b1c20fbc8c2b7156f391c4f93599603ccec33b67d5540b48` |
| `Uoink-3.12.1-macos-arm64.dmg` | 711,443,160 B | `5fb2597672c6d8124d153d00d077bb2f1ac053efc5bc9ed2dd8b34fa89cb2a76` |
| `uoink-3.12.1-macos.mcpb` | 103,375 B | `49ba35aa7462ed32f5f651580b2cef621fa1066fb2d2b049ef2e4797a6083ca3` |
