# Uoink 3.14.0

## What's new

- **Deep research.** Ask a question and Uoink searches your library and, once you allow them, YouTube, Hacker News, HackerTube and podcasts. It captures the video transcripts you pick, within a per-run transcription budget, and hands your agent short, cited excerpts. The agent writes the claims. Before Uoink saves the report, it checks that every quote and timestamp is really in the source. Start it from the dashboard's **Research** tab, with `uoink research "<question>"`, or from an agent with the `deep-research` prompt and the six `research_*` tools. Searching the web for sources is off until you turn on the sources you want. See [docs/research.md](https://github.com/ryanbiddy/uoink/blob/v3.14.0/docs/research.md).
- **Import your saves.** Bring in YouTube Watch Later, X bookmarks and Reddit saved posts. Import a file with **Import a saves file** in the dashboard or `uoink import <file>`: a Google Takeout playlist CSV for Watch Later, Reddit's export CSVs, or a list of X status links. Or open the page in Chrome: the extension's Uoink panel collects what you scroll past (or click **Auto-scroll**) and sends it to Uoink 50 at a time. Saves already in your library are skipped, and the rest are tagged `watch later`, `reddit saved` or `x bookmarks`.
- **Know when a saved source goes offline.** Once a week Uoink politely checks whether your saved videos, posts, podcasts and pages are still up, from your own machine. When something disappears, you still have your copy: a badge, a **Gone from the web** filter and a monthly notice show what is now only in Uoink. Turn the checks off in Settings with **Check if saved sources go offline**.
- **`get_transcript`.** A YouTube transcript tool that doesn't fail silently. It uses your saved copy first, then the captions, then transcribes the audio locally with the bundled Whisper model when YouTube refuses. Every result says where the words came from. It works as a drop-in for the popular YouTube transcript MCP servers.
- **Linux (headless).** `scripts/linux/install.sh` installs Uoink on Linux with no tray or windows, so an agent in Docker, Codespaces or a cloud sandbox can run `uoink mcp`. There is also a capture image, `docker/capture.Dockerfile`. See [docs/linux.md](https://github.com/ryanbiddy/uoink/blob/v3.14.0/docs/linux.md).
- A smaller tool set for clients with a tool limit: `UOINK_MCP_TOOLSET=search` (9 tools), and `uoink connect <client> --toolset search` writes it into the client's config.
- Security: the installer bundles Pillow 13.0.0 (a JPEG decoder fix) and marks saved third-party text in MCP results as untrusted. Upgrading no longer shows "Uoink could not register crash recovery".
- 99 tools now (36 in core mode, 9 in search mode, and 7 in the new research mode: the six research tools plus `uoink_url`).

## Install or update

**Windows 10/11**

1. Download `Uoink-Setup-3.14.0.exe` and `SHA256SUMS.txt`, then check the installer's SHA-256.
2. The Windows installer is unsigned, so SmartScreen may warn. Choose **More info -> Run anyway**.
3. New install: on first launch, use the setup splash to open `chrome://extensions` and copy the extension path. Turn on **Developer mode**, click **Load unpacked** and select that folder. Then click Chrome's puzzle-piece **Extensions** icon and pin **Uoink**.
4. Claude Desktop: install `uoink-3.14.0.mcpb`.
5. Claude Code: run `uoink connect claude-code` in a new terminal, then run the command it prints.

**Mac (Apple Silicon, macOS 15 or later; preview)**

1. Download `Uoink-3.14.0-macos-arm64.dmg` and check its SHA-256 against `SHA256SUMS.txt`.
2. Open the DMG, drag Uoink to Applications, eject the disk, then open Uoink from Applications.
3. In Chrome, open `chrome://extensions`, turn on **Developer mode** and click **Load unpacked**. The dashboard's **Get the extension** card copies the extension's folder path; in the picker, press ⌘⇧G, paste it and press Return.
4. Claude Desktop: install `uoink-3.14.0-macos.mcpb`.

See [docs/mac/INSTALL.md](https://github.com/ryanbiddy/uoink/blob/v3.14.0/docs/mac/INSTALL.md) for login startup, logs and uninstalling.

**Linux (headless)**

```sh
git clone https://github.com/ryanbiddy/uoink && sh uoink/scripts/linux/install.sh
```

See [docs/linux.md](https://github.com/ryanbiddy/uoink/blob/v3.14.0/docs/linux.md) for options, paths, the capture image and agent setup.

## Upgrading

- Your library and captures stay in place. The upgrade adds one database migration (`0033_source_availability.sql`), which stores availability next to your saves without changing them.
- Reload the Uoink extension in `chrome://extensions` to get the saves panel.
- Claude Desktop: reinstall the 3.14.0 `.mcpb` and restart Desktop to get the new tools.

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
| `Uoink-Setup-3.14.0.exe` | 519,322,824 B | `b9e5acf346b252bd34cf00ee223a68b2b9fa65cf0dfd932603d14f3b8a957a52` |
| `uoink-3.14.0.mcpb` | 117,589 B | `44c6a794de07d4d327fb149ecaa481dd5808aa4fae215082f4c0a74ec60429ef` |
| `Uoink-3.14.0-macos-arm64.dmg` | 695,008,714 B | `2591ea57a39667c59216b1ba96f50532a7edb88716205a432594da5ba5742dd1` |
| `uoink-3.14.0-macos.mcpb` | 114,114 B | `ed674f182195370b4c06af5829e46faeb21ee44a05f8dfdd6f5ac75007318626` |
