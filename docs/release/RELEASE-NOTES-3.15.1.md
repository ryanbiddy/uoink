# Uoink 3.15.1

## What's new

This release adds update notices and fixes what the 3.15.0 Mac demo turned up.

- **Know when there's a new Uoink.** In Settings, Updates, turn on **Check for new versions once a day**. It is off by default; **Check now** works either way. When a newer version is out, a banner says so, and the Windows tray and Mac menu bar show **Update available**. The check asks `api.github.com` for the latest release tag and sends nothing else.
- **Update now.** On Windows, **Update now** downloads the new installer from the GitHub release, checks it against the release's `SHA256SUMS.txt`, and only then runs it; Uoink closes and starts again. On a Mac, **Download update** does the same check and opens the DMG for you to drag in. Nothing downloads unless you press the button. This release is the first with the button, so you install 3.15.1 the usual way; later versions can update from inside Uoink.
- **Check a podcast feed now.** Feed cards on Sources and feed rows in Settings have **Check now**. It skips the hourly wait once the feed has gone 2 minutes unchecked, and still respects backoff and a check already running.
- **Better podcast transcripts.** Whisper gets a short hint from the show and episode titles (or the channel and video titles), so niche names come out spelled right more often.
- **Claude Code stays connected after a big capture.** A tool reply over the 64 KiB reply frame used to be replaced with "Inbound request exceeds protocol limits", which left the session unusable. Replies are now trimmed to fit, with a note pointing to the full record. `uoink_x` returns the post text, author, counts and one best MP4 per video; the full evidence stays in the sidecar.
- **Search and Library.** The search box says whether it is using keyword or meaning search. Failed captures only show under a search they match. Highlights match whole words.
- **Podcasts look right.** Back-catalog episodes show as podcasts with the feed's artwork, cached locally once per feed; the dashboard still loads no remote images. After you allow a feed, the card shows its first check instead of stopping at "0 enrolled".
- **Research.** Any candidate already in your library shows **Use saved**. Reports say "1 channel cited".
- **Smaller fixes.** Insights leads with its numbers. For You waits for 10 library items before naming a gap. The "Uoink anything" paste box is first on Sources. X thumbnails no longer fail with 403, and X captures stop logging a failed channel lookup. Copy as Markdown leaves out unknown fields instead of printing dashes. `uoink --text` no longer crashes on a Windows console that can't print ♪.

## Install or update

**Windows 10/11**

1. Download `Uoink-Setup-3.15.1.exe` and `SHA256SUMS.txt`, then check the installer's SHA-256.
2. The Windows installer is unsigned, so SmartScreen may warn. Choose **More info -> Run anyway**.
3. New install: on first launch, use the setup splash to open `chrome://extensions` and copy the extension path. Turn on **Developer mode**, click **Load unpacked** and select that folder. Then click Chrome's puzzle-piece **Extensions** icon and pin **Uoink**.
4. Claude Desktop: install `uoink-3.15.1.mcpb`.
5. Claude Code: run `uoink connect claude-code` in a new terminal, then run the command it prints.

**Mac (Apple Silicon, macOS 15 or later; preview)**

1. Download `Uoink-3.15.1-macos-arm64.dmg` and check its SHA-256 against `SHA256SUMS.txt`.
2. Open the DMG, drag Uoink to Applications, eject the disk, then open Uoink from Applications.
3. In Chrome, open `chrome://extensions`, turn on **Developer mode** and click **Load unpacked**. The dashboard's **Get the extension** card copies the extension's folder path; in the picker, press ⌘⇧G, paste it and press Return.
4. Claude Desktop: install `uoink-3.15.1-macos.mcpb`.

See [docs/mac/INSTALL.md](https://github.com/ryanbiddy/uoink/blob/v3.15.1/docs/mac/INSTALL.md) for login startup, logs and uninstalling.

**Linux (headless)**

```sh
git clone https://github.com/ryanbiddy/uoink && sh uoink/scripts/linux/install.sh
```

See [docs/linux.md](https://github.com/ryanbiddy/uoink/blob/v3.15.1/docs/linux.md) for options, paths, the capture image and agent setup.

## Upgrading
- Your library and captures stay in place. Upgrading from 3.15.0 adds no database migrations.
- Reload the Uoink extension in `chrome://extensions` after updating.
- Claude Desktop: reinstall the 3.15.1 `.mcpb` and restart Desktop.

## Known limits

- The extension's Watch Later, X bookmarks and Reddit saved collectors have automated tests but have not yet been tried in a real browser. The file imports are the tested path.
- YouTube often blocks cloud IP addresses. On a Linux server or container, captions can fail, and the local Whisper fallback helps only when the audio download itself works.
- Research doesn't capture podcast episodes yet: it lists them, then skips them with `podcast_capture_later`. Podcast transcripts already in your library still count as evidence. Reddit search is not available in research yet.
- Linux is headless only: no tray, splash or dashboard window (the helper logs the dashboard URL instead). A host install needs ffmpeg and ffprobe on the system; without them media tools answer `media_requires_ffmpeg`. Podcast transcription on Linux uses CPU faster-whisper without speaker labels unless you install the optional WhisperX requirements.
- Update now works on Windows and Apple Silicon Macs from an installed build. Linux, source checkouts and isolated test installs link to the release page instead. The Windows installer is unsigned, so the update is checked against the release's published checksums, not a code signature.
- Mac: Apple Silicon only.
- Chrome (tested). Edge and Brave may work but are not tested.

## Checksums

| File | Size | SHA-256 |
| --- | --- | --- |
| `Uoink-Setup-3.15.1.exe` | TBD | TBD |
| `uoink-3.15.1.mcpb` | TBD | TBD |
| `Uoink-3.15.1-macos-arm64.dmg` | TBD | TBD |
| `uoink-3.15.1-macos.mcpb` | TBD | TBD |
