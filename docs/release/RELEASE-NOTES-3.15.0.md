# Uoink 3.15.0

## What's new

This release polishes the everyday flows: search, reading, capture status, research and podcasts.

- **Search finds the moment.** Library search now matches all your words by default and sorts by relevance while you type. Each result shows the line that matched with its timestamp; click it to open the item at that point in the transcript. Switch to **Any words** for broader results.
- **A cleaner reader.** Black frames (a video fading in) are no longer used as screenshots in the reader or the Generate picker. Screenshots and transcript lines appear in time order.
- **Plain capture status.** Captures say "Getting transcript" or "Saving screenshots", then "Ready". Comments that are still loading no longer hold an item back. The "Start from your last save" card updates right after a save.
- **Clearer failures.** A failed capture leads with the plain reason, such as "This video is private or unavailable in your region." The raw downloader message is under **Details**. Brand names are capitalized.
- **One Activity row per podcast episode**, and one count in the sidebar that matches what Activity shows.
- **Research sources in one place.** Each source has one control. Items already in your library show **Use saved**; new ones show **Capture new**.
- **Sources page.** The paste box comes first, above Discover. Web pages ask for site permission inline before you capture, without moving the layout.
- **Podcasts show their real names.** Episodes use the feed's title instead of "Untitled podcast", including episodes you already saved; your saved files are not rewritten. New subscriptions show the feed title after you allow it, and Uoink doesn't read a feed until you allow it or press **Check now**. Podcast rows use the Podcast kind with a local placeholder image.
- **Copy as Markdown** puts the transcript first, leaves out empty sections such as "No tags", and uses full file links.
- **Smaller fixes.** The sidebar footer says "Running on this PC" (or Mac); details are in Settings. On a Mac, Uoink finds Claude Desktop in `/Applications` even before its first launch. **Write from this** and **Generate** say "Connect Claude first" until a writing agent is set up, and Script mode labels match the selected output. For You no longer pairs items only because both are uncategorized, and short notes aren't sorted into topics. Insights shows readable dates. The library empty state hides as soon as a capture starts.

## Install or update

**Windows 10/11**

1. Download `Uoink-Setup-3.15.0.exe` and `SHA256SUMS.txt`, then check the installer's SHA-256.
2. The Windows installer is unsigned, so SmartScreen may warn. Choose **More info -> Run anyway**.
3. New install: on first launch, use the setup splash to open `chrome://extensions` and copy the extension path. Turn on **Developer mode**, click **Load unpacked** and select that folder. Then click Chrome's puzzle-piece **Extensions** icon and pin **Uoink**.
4. Claude Desktop: install `uoink-3.15.0.mcpb`.
5. Claude Code: run `uoink connect claude-code` in a new terminal, then run the command it prints.

**Mac (Apple Silicon, macOS 15 or later; preview)**

1. Download `Uoink-3.15.0-macos-arm64.dmg` and check its SHA-256 against `SHA256SUMS.txt`.
2. Open the DMG, drag Uoink to Applications, eject the disk, then open Uoink from Applications.
3. In Chrome, open `chrome://extensions`, turn on **Developer mode** and click **Load unpacked**. The dashboard's **Get the extension** card copies the extension's folder path; in the picker, press ⌘⇧G, paste it and press Return.
4. Claude Desktop: install `uoink-3.15.0-macos.mcpb`.

See [docs/mac/INSTALL.md](https://github.com/ryanbiddy/uoink/blob/v3.15.0/docs/mac/INSTALL.md) for login startup, logs and uninstalling.

**Linux (headless)**

```sh
git clone https://github.com/ryanbiddy/uoink && sh uoink/scripts/linux/install.sh
```

See [docs/linux.md](https://github.com/ryanbiddy/uoink/blob/v3.15.0/docs/linux.md) for options, paths, the capture image and agent setup.

## Upgrading
- Your library and captures stay in place. Upgrading from 3.14.1 adds no database migrations.
- Reload the Uoink extension in `chrome://extensions` after updating.
- Claude Desktop: reinstall the 3.15.0 `.mcpb` and restart Desktop.

## Known limits

- The extension's Watch Later, X bookmarks and Reddit saved collectors have automated tests but have not yet been tried in a real browser. The file imports are the tested path.
- YouTube often blocks cloud IP addresses. On a Linux server or container, captions can fail, and the local Whisper fallback helps only when the audio download itself works.
- Research doesn't capture podcast episodes yet: it lists them, then skips them with `podcast_capture_later`. Podcast transcripts already in your library still count as evidence. Reddit search is not available in research yet.
- Linux is headless only: no tray, splash or dashboard window (the helper logs the dashboard URL instead). A host install needs ffmpeg and ffprobe on the system; without them media tools answer `media_requires_ffmpeg`. Podcast transcription on Linux uses CPU faster-whisper without speaker labels unless you install the optional WhisperX requirements.
- Mac: Apple Silicon only. Uoink doesn't update itself there yet, so install new versions from the DMG.
- Chrome (tested). Edge and Brave may work but are not tested.

## Checksums

| File | Size | SHA-256 |
| --- | --- | --- |
| `Uoink-Setup-3.15.0.exe` | TBD | `TBD` |
| `uoink-3.15.0.mcpb` | TBD | `TBD` |
| `Uoink-3.15.0-macos-arm64.dmg` | TBD | `TBD` |
| `uoink-3.15.0-macos.mcpb` | TBD | `TBD` |
