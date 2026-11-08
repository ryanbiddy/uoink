# Uoink 3.16.1

## What's new

This release lets YouTube capture solve YouTube's player challenges, adds a sixth research playbook and makes a bot check wait instead of failing a capture.

- **Deno ships with the Windows installer.** yt-dlp needs a JavaScript runtime to solve YouTube's player challenges, so the installer now includes Deno. It runs YouTube's player code with no file or network access. Uoink downloads nothing for it at runtime, turns off Deno's update check and keeps its small cache in the Uoink folder. The installer grows by about 29 MB. On Mac and Linux, Uoink uses a Deno 2.3 or newer that is already on your PATH.
- **Thesis check, the sixth research playbook.** Give it a claim and a selection of saved captures. Your AI gets a cited packet of the clips that match, the opening of each source and the top comments. It asks for the assumptions the sources share, the evidence for and against, and what your library does not cover. Every point carries a citation, and clip citations carry the timestamp. It is also in the Generate research list.
- **A bot check pauses a capture.** When YouTube asks for a bot check at the details or media step, Uoink now queues the capture and retries it after 30 minutes, then 1 hour, then 4 hours. Library shows the row as Paused with the retry time. After three attempts the capture fails with bot-check wording instead of "HTTP 429". The "Retry with cookies" control is gone, because Uoink never signs in or uses cookies.
- **yt-dlp ignores your personal config file on Windows and Linux too.** The Mac app already did. Options in that file, such as browser cookies or a forced player client, no longer change what Uoink sends.
- **Smaller fixes.** yt-dlp is now 2026.10.21. Make a Short with Zing works when your library is on a mapped network drive. Failed rows you dismiss in Library stay dismissed after a reload.

The MCP server still exposes 99 tools by default, 36 with `UOINK_MCP_TOOLSET=core`, 9 with `search` and 7 with `research`.

## Install or update

**Update from 3.15.1 or later.** Open Settings, Updates. On Windows press **Update now**. On a Mac press **Download update**. Uoink checks the download against the release's `SHA256SUMS.txt` before it runs or opens it. If you are on an older version, install the usual way below.

**Windows 10/11**

1. Download `Uoink-Setup-3.16.1.exe` and `SHA256SUMS.txt`, then check the installer's SHA-256.
2. The Windows installer is unsigned, so SmartScreen may warn. Choose **More info -> Run anyway**.
3. New install: on first launch, use the setup splash to open `chrome://extensions` and copy the extension path. Turn on **Developer mode**, click **Load unpacked** and select that folder. Then click Chrome's puzzle-piece **Extensions** icon and pin **Uoink**.
4. Claude Desktop: install `uoink-3.16.1.mcpb`.
5. Claude Code: run `uoink connect claude-code` in a new terminal, then run the command it prints.

**Mac (Apple Silicon, macOS 15 or later; preview)**

1. Download `Uoink-3.16.1-macos-arm64.dmg` and check its SHA-256 against `SHA256SUMS.txt`.
2. Open the DMG, drag Uoink to Applications, eject the disk, then open Uoink from Applications.
3. In Chrome, open `chrome://extensions`, turn on **Developer mode** and click **Load unpacked**. The dashboard's **Get the extension** card copies the extension's folder path; in the picker, press ⌘⇧G, paste it and press Return.
4. Claude Desktop: install `uoink-3.16.1-macos.mcpb`.

See [docs/mac/INSTALL.md](https://github.com/ryanbiddy/uoink/blob/v3.16.1/docs/mac/INSTALL.md) for login startup, logs and uninstalling.

**Linux (headless)**

```sh
git clone https://github.com/ryanbiddy/uoink && sh uoink/scripts/linux/install.sh
```

See [docs/linux.md](https://github.com/ryanbiddy/uoink/blob/v3.16.1/docs/linux.md) for options, paths, the capture image and agent setup.

## Upgrading
- Your library and captures stay in place. Upgrading from 3.16.0 adds no database migrations.
- Reload the Uoink extension in `chrome://extensions` after updating.
- Claude Desktop: reinstall the 3.16.1 `.mcpb` and restart Desktop.

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
| `Uoink-Setup-3.16.1.exe` | TBD | TBD |
| `uoink-3.16.1.mcpb` | TBD | TBD |
| `Uoink-3.16.1-macos-arm64.dmg` | TBD | TBD |
| `uoink-3.16.1-macos.mcpb` | TBD | TBD |
