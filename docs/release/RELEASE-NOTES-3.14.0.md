# Uoink 3.14.0

## What's new

- **Deep research.** Ask a question and Uoink finds talks, videos and podcast episodes about it, captures the transcripts you pick, and hands your agent short, cited excerpts. The agent writes the claims. Before Uoink saves the report, it checks that every quote and timestamp is really in the source. Start it from the dashboard's **Research** tab, with `uoink research "<question>"`, or from an agent with the `deep-research` prompt and the six `research_*` tools. Searching the web for sources is off until you turn on the sources you want. See [docs/research.md](https://github.com/ryanbiddy/uoink/blob/v3.14.0/docs/research.md).
- **Import your saves.** Bring in YouTube Watch Later, X bookmarks and Reddit saved posts. Import a file with **Import a saves file** in the dashboard or `uoink import <file>`: a Google Takeout playlist CSV for Watch Later, Reddit's export CSVs, or a list of X status links. Or open the page in Chrome and let the extension's Uoink panel scroll and collect them. Saves already in your library are skipped, and the rest are tagged `watch later`, `reddit saved` or `x bookmarks`.
- **Know when a saved source goes offline.** Once a week Uoink politely checks whether your saved videos, posts, podcasts and pages are still up, from your own machine. When something disappears, you still have your copy: a badge, a **Gone from the web** filter and a monthly notice show what is now only in Uoink. Turn the checks off in Settings with **Check if saved sources go offline**.
- **`get_transcript`.** A YouTube transcript tool that doesn't fail silently. It uses your saved copy first, then the captions, then transcribes the audio locally with the bundled Whisper model when YouTube refuses. Every result says where the words came from. It works as a drop-in for the popular YouTube transcript MCP servers.
- **Linux (headless).** `scripts/linux/install.sh` installs Uoink on Linux with no tray or windows, so an agent in Docker, Codespaces or a cloud sandbox can run `uoink mcp`. There is also a capture image, `docker/capture.Dockerfile`. See [docs/linux.md](https://github.com/ryanbiddy/uoink/blob/v3.14.0/docs/linux.md).
- A smaller tool set for clients with a tool limit: `UOINK_MCP_TOOLSET=search` (9 tools), and `uoink connect <client> --toolset search` writes it into the client's config.
- Security: the installer bundles Pillow 13.0.0 (a JPEG decoder fix) and marks saved third-party text in MCP results as untrusted. Upgrading no longer shows "Uoink could not register crash recovery".
- 99 tools now (36 in core mode, 9 in search mode, 7 in research mode).

## Install or update

**Windows 10/11**

1. Download `Uoink-Setup-3.14.0.exe` and `SHA256SUMS.txt`, then check the installer's SHA-256.
2. The Windows installer is unsigned, so SmartScreen may warn. Choose **More info -> Run anyway**.
3. New install: on first launch, use the setup splash to open `chrome://extensions` and copy the extension path. Turn on **Developer mode**, click **Load unpacked** and select that folder. Then click Chrome's puzzle-piece **Extensions** icon and pin **Uoink**.
4. Claude Desktop: install `uoink-3.14.0.mcpb`.
5. Claude Code: run `uoink connect claude-code` in a new terminal, then run the command it prints.

**Mac (Apple Silicon, macOS 15 or later; preview)**

1. Download `Uoink-3.14.0-macos-arm64.dmg` and check its SHA-256 against `SHA256SUMS.txt`.
2. Open the DMG, drag Uoink to Applications and eject the disk.
3. This Mac build is not signed or notarized, so macOS blocks the first open. Open Uoink from Applications once, then go to **System Settings > Privacy & Security** and click **Open Anyway** next to the Uoink message.
4. In Chrome, open `chrome://extensions`, turn on **Developer mode** and click **Load unpacked**. The dashboard's **Get the extension** card copies the extension's folder path; in the picker, press ⌘⇧G, paste it and press Return.
5. Claude Desktop: install `uoink-3.14.0-macos.mcpb`.

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
- Linux is headless only: no tray, splash or dashboard window.
- The Mac build in this release is unsigned (see the install steps). Mac is Apple Silicon only, and Uoink doesn't update itself there yet.
- Chrome (tested). Edge and Brave may work but are not tested.
