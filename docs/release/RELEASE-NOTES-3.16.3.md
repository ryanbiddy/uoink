# Uoink 3.16.3

## What's new

This release makes installing Uoink look like installing an official app, on Windows and on the Mac, and fixes the buttons in the Windows installer.

- **The Windows installer's buttons read right again.** In recent Windows installers, the Next, Install and Finish buttons showed `*` instead of their names. They say Next, Install and Finish again.
- **A one-screen Windows install.** Setup opens on one screen with the Uoink icon and an Install button, then shows its progress, then "Uoink is installed". To pick the install folder, the desktop shortcut or the PATH option for AI agents, tick **Choose the install folder and shortcuts** first. Setup follows Windows light and dark mode. Over an existing install, it says **Update Uoink**.
- **The Mac app has its icon.** Finder, the Dock and Launchpad showed the generic app icon for Uoink. They now show the Uoink icon.
- **A real Mac install window.** The DMG opens to a window with Uoink on the left, Applications on the right and an arrow between them. Drag Uoink across and you're done. The DMG is also about TBD MB smaller, from tighter compression. The app inside is the same size.
- **One icon everywhere.** Setup, the Start menu and desktop shortcuts, the uninstaller, notifications and the dashboard window use the same icon as the uoink.app download page.

The MCP server still exposes 99 tools by default, 36 with `UOINK_MCP_TOOLSET=core`, 9 with `search` and 7 with `research`.

## Install or update

**Update from 3.15.1 or later.** Open Settings, Updates. On Windows press **Update now**. On a Mac press **Download update**. Uoink checks the download against the release's `SHA256SUMS.txt` before it runs or opens it. If you are on an older version, install the usual way below.

**Windows 10/11**

1. Download `Uoink-Setup-3.16.3.exe` and `SHA256SUMS.txt`, then check the installer's SHA-256.
2. The Windows installer is unsigned, so SmartScreen may warn. Choose **More info -> Run anyway**.
3. Press **Install**. To choose the folder or shortcuts, tick **Choose the install folder and shortcuts** first.
4. New install: on first launch, use the setup splash to open `chrome://extensions` and copy the extension path. Turn on **Developer mode**, click **Load unpacked** and select that folder. Then click Chrome's puzzle-piece **Extensions** icon and pin **Uoink**.
5. Claude Desktop: install `uoink-3.16.3.mcpb`.
6. Claude Code: run `uoink connect claude-code` in a new terminal, then run the command it prints.

**Mac (Apple Silicon, macOS 15 or later; preview)**

1. Download `Uoink-3.16.3-macos-arm64.dmg` and check its SHA-256 against `SHA256SUMS.txt`.
2. Open the DMG, drag Uoink onto Applications, eject the disk, then open Uoink from Applications.
3. In Chrome, open `chrome://extensions`, turn on **Developer mode** and click **Load unpacked**. The dashboard's **Get the extension** card copies the extension's folder path; in the picker, press ⌘⇧G, paste it and press Return.
4. Claude Desktop: install `uoink-3.16.3-macos.mcpb`.

See [docs/mac/INSTALL.md](https://github.com/ryanbiddy/uoink/blob/v3.16.3/docs/mac/INSTALL.md) for login startup, logs and uninstalling.

**Linux (headless)**

```sh
git clone https://github.com/ryanbiddy/uoink && sh uoink/scripts/linux/install.sh
```

See [docs/linux.md](https://github.com/ryanbiddy/uoink/blob/v3.16.3/docs/linux.md) for options, paths, the capture image and agent setup.

## Upgrading
- Your library and captures stay in place. Upgrading from 3.16.2 adds no database migrations.
- Reload the Uoink extension in `chrome://extensions` after updating.
- Claude Desktop: reinstall the 3.16.3 `.mcpb` and restart Desktop.

## Known limits

- The extension's Watch Later, X bookmarks and Reddit saved collectors have automated tests but have not yet been tried in a real browser. The file imports are the tested path.
- YouTube often blocks cloud IP addresses. On a Linux server or container, captions can fail, and the local Whisper fallback helps only when the audio download itself works.
- Research doesn't capture podcast episodes yet: it lists them, then skips them with `podcast_capture_later`. Podcast transcripts already in your library still count as evidence. Reddit search is not available in research yet.
- Linux is headless only: no tray, splash or dashboard window (the helper logs the dashboard URL instead). A host install needs ffmpeg and ffprobe on the system; without them media tools answer `media_requires_ffmpeg`. Podcast transcription on Linux uses CPU faster-whisper without speaker labels unless you install the optional WhisperX requirements.
- Update now works on Windows and Apple Silicon Macs from an installed build. Linux, source checkouts and isolated test installs link to the release page instead. The Windows installer is unsigned, so the update is checked against the release's published checksums, not a code signature.
- Make a Short with Zing needs Zing installed. Uoink keeps media for short videos only, so a longer video goes through the Download step.
- Mac: Apple Silicon only.
- Chrome (tested). Edge and Brave may work but are not tested.

## Checksums

| File | Size | SHA-256 |
| --- | --- | --- |
| `Uoink-Setup-3.16.3.exe` | TBD | TBD |
| `uoink-3.16.3.mcpb` | TBD | TBD |
| `Uoink-3.16.3-macos-arm64.dmg` | TBD | TBD |
| `uoink-3.16.3-macos.mcpb` | MACTBD | TBD |

The Mac DMG is signed with Developer ID and notarized (mac-qualify run TBD).
