# Uoink 3.13.0

## What's new

- **Import a list.** Paste a list link in Sources > **Import a list** and Uoink queues every video in it for a normal capture, with transcripts. It reads a HackerTube playlist, category, area or the whole collection, a Hacker News thread, a Reddit thread or a YouTube playlist. You see a preview first ("Found 37 videos, 5 already in your library"), then one Import button. Imports go 50 videos at a time; **Next 50** works through long lists. Videos you already have are skipped. Each import keeps where it came from as a tag, and HackerTube's note on why Hacker News likes a video shows in the reader. From the command line: `uoink import-list <url> --preview`, then without `--preview` to queue. Agents get the new `import_list` MCP tool.
- **From lists you imported.** For You shows the imported videos you haven't opened yet, ranked by your own taste.
- **Card image.** Library and For You cards for saved videos now show a screenshot from the middle of the video instead of the thumbnail. Change it in Settings > Library and export. Older captures switch only when a screenshot near the halfway mark is already saved; nothing is downloaded again.
- **Silent updates restart Uoink.** A silent install or upgrade on Windows, such as `winget upgrade`, starts Uoink again if it was running before, with no splash, dashboard or toast. If you quit Uoink before the update, it stays quit.
- **Container fix.** The Linux container creates an empty library before it starts the MCP server, so a fresh container answers searches with no results instead of an error.
- 92 tools now (35 in core mode). `import_list` is the new one.

## Credits

HackerTube ([hackertube.org](https://hackertube.org)) is by Andrej Karpathy. Its data is built on the [open-index/hacker-news](https://huggingface.co/datasets/open-index/hacker-news) dataset (Hacker News data by Y Combinator) and is licensed ODC-By 1.0. Uoink fetches it when you import and bundles none of it, and every imported HackerTube item keeps the credit line.

## Install or update

**Windows 10/11**

1. Download `Uoink-Setup-3.13.0.exe` and `SHA256SUMS.txt`, then check the installer's SHA-256.
2. The Windows installer is unsigned, so SmartScreen may warn. Choose **More info -> Run anyway**.
3. New install: on first launch, use the setup splash to open `chrome://extensions` and copy the extension path. Turn on **Developer mode**, click **Load unpacked** and select that folder. Then click Chrome's puzzle-piece **Extensions** icon and pin **Uoink**.
4. Claude Desktop: install `uoink-3.13.0.mcpb`.
5. Claude Code: run `uoink connect claude-code` in a new terminal, then run the command it prints.

**Mac (Apple Silicon, macOS 15 or later; preview)**

1. Download `Uoink-3.13.0-macos-arm64.dmg` and check its SHA-256 against `SHA256SUMS.txt`.
2. Open the DMG, drag Uoink to Applications, eject the disk, then open Uoink from Applications.
3. In Chrome, open `chrome://extensions`, turn on **Developer mode** and click **Load unpacked**. The dashboard's **Get the extension** card copies the extension's folder path; in the picker, press ⌘⇧G, paste it and press Return.
4. Claude Desktop: install `uoink-3.13.0-macos.mcpb`.

See [docs/mac/INSTALL.md](https://github.com/ryanbiddy/uoink/blob/v3.13.0/docs/mac/INSTALL.md) for login startup, logs and uninstalling.

## Upgrading

- Your library and captures stay in place.
- Reload the Uoink extension in `chrome://extensions`.
- Claude Desktop: reinstall the 3.13.0 `.mcpb` and restart Desktop to get `import_list`.
- Card images change on their own where a mid-video screenshot exists. To keep thumbnails, pick **Original thumbnail** in Settings > Library and export.

## Known limits

- Chrome (tested). Edge and Brave may work but are not tested.
- Mac: Apple Silicon only. Uoink doesn't update itself yet, so install new versions from the DMG. macOS still shows Uoink's alerts as coming from Script Editor. Library mirroring is unavailable on Mac.
- Import a list needs the network at import time: HackerTube, the Algolia Hacker News API, Reddit or YouTube. A batch is at most 50 videos, and videos are captured one at a time.
- The phone inbox and launcher integrations are unchanged from 3.12.1.
