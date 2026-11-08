# Uoink 3.16.0

## What's new

This release connects Uoink to Zing and says plainly when YouTube blocks captions.

- **Make a Short with Zing.** When Zing is installed, the reader has a button that hands the open item to Zing and opens Zing's review page. Nothing shows if Zing is not installed. Zing needs the item's video. If Uoink kept the media, Zing uses it. If not, Zing downloads the video only after you click **Download** for that item, and shows progress while it does. Nothing downloads on its own.
- **Save a link from a sibling app.** A local app such as Zing can save one link into your library with `uoink.capture/1`. It uses the helper token and never recaptures a link that is already saved. It still asks for the page allowlist and the podcast consent first.
- **YouTube bot check, named.** When YouTube asks to confirm you are not a bot, the capture still finishes with local Whisper. The Library note and Activity row now say so. The saved capture records `captions_skipped_reason`, and `server.log` names the category instead of a generic error.
- **A pause after repeated bot checks.** After three bot checks in 15 minutes, Uoink stops asking YouTube for captions for 30 minutes and transcribes locally. The dashboard shows a notice you can dismiss, and `/health` reports `youtube_bot_check`. Uoink never adds browser cookies on its own.

## Install or update

**Update from 3.15.1.** Open Settings, Updates. On Windows press **Update now**. On a Mac press **Download update**. Uoink checks the download against the release's `SHA256SUMS.txt` before it runs or opens it. If you are on an older version, install the usual way below.

**Windows 10/11**

1. Download `Uoink-Setup-3.16.0.exe` and `SHA256SUMS.txt`, then check the installer's SHA-256.
2. The Windows installer is unsigned, so SmartScreen may warn. Choose **More info -> Run anyway**.
3. New install: on first launch, use the setup splash to open `chrome://extensions` and copy the extension path. Turn on **Developer mode**, click **Load unpacked** and select that folder. Then click Chrome's puzzle-piece **Extensions** icon and pin **Uoink**.
4. Claude Desktop: install `uoink-3.16.0.mcpb`.
5. Claude Code: run `uoink connect claude-code` in a new terminal, then run the command it prints.

**Mac (Apple Silicon, macOS 15 or later; preview)**

1. Download `Uoink-3.16.0-macos-arm64.dmg` and check its SHA-256 against `SHA256SUMS.txt`.
2. Open the DMG, drag Uoink to Applications, eject the disk, then open Uoink from Applications.
3. In Chrome, open `chrome://extensions`, turn on **Developer mode** and click **Load unpacked**. The dashboard's **Get the extension** card copies the extension's folder path; in the picker, press ⌘⇧G, paste it and press Return.
4. Claude Desktop: install `uoink-3.16.0-macos.mcpb`.

See [docs/mac/INSTALL.md](https://github.com/ryanbiddy/uoink/blob/v3.16.0/docs/mac/INSTALL.md) for login startup, logs and uninstalling.

**Linux (headless)**

```sh
git clone https://github.com/ryanbiddy/uoink && sh uoink/scripts/linux/install.sh
```

See [docs/linux.md](https://github.com/ryanbiddy/uoink/blob/v3.16.0/docs/linux.md) for options, paths, the capture image and agent setup.

## Upgrading
- Your library and captures stay in place. Upgrading from 3.15.1 adds no database migrations.
- Reload the Uoink extension in `chrome://extensions` after updating.
- Claude Desktop: reinstall the 3.16.0 `.mcpb` and restart Desktop.

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
| `Uoink-Setup-3.16.0.exe` | 519,455,821 B | `77c0b9533a7548c6735f1cd34c1f90f87d2113dda7b7a6779ee96cb17cb317a6` |
| `uoink-3.16.0.mcpb` | 119,679 B | `ee0d47f05632c8820bc0e618040eab9ab4784bc3576f6a226c27ff47786927f5` |
| `Uoink-3.16.0-macos-arm64.dmg` | 706,306,450 B | `be8a3b9b59108289228d788165ef6aab754431c0b5b34fc7d7547bc650284799` |
| `uoink-3.16.0-macos.mcpb` | 116,241 B | `438d485e1ee3a76557e0877024e782abba72f9b246bdbc9a278f1f8e779335c4` |

The Mac DMG is signed with Developer ID and notarized (mac-qualify run 42458248448).
