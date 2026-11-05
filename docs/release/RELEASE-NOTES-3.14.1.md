# Uoink 3.14.1

## What's new

- **Deep research finds your saved videos again.** In 3.14.0, videos captured outside a research run gave no excerpts. Research now repairs those items the first time it reads them, after checking their transcript and saved files. No migration runs.
- **Cleaner CLI output.** `--text` output for `search`, `recent` and `research` is easier to read. Timestamps use `m:ss` ranges and titles show normal quotes. Search results include the source and a verified quote; recent saves show the date, kind and source. Research shows a short "why" line; add `--explain` to see the full candidate score breakdown. JSON output is unchanged.
- **Research report fixes.** `report.md` uses Markdown escapes instead of HTML entities. Reports and share text say "1 claim" and "1 source" when the count is one.
- Research MCP tools now explain that `run_id` comes from `research_start`.
- Saves import headers show matching source labels and list titles only once in the CLI and dashboard.
- The Windows installer now bundles `filelock` 4.2.1.

## Install or update

**Windows 10/11**

1. Download `Uoink-Setup-3.14.1.exe` and `SHA256SUMS.txt`, then check the installer's SHA-256.
2. The Windows installer is unsigned, so SmartScreen may warn. Choose **More info -> Run anyway**.
3. New install: on first launch, use the setup splash to open `chrome://extensions` and copy the extension path. Turn on **Developer mode**, click **Load unpacked** and select that folder. Then click Chrome's puzzle-piece **Extensions** icon and pin **Uoink**.
4. Claude Desktop: install `uoink-3.14.1.mcpb`.
5. Claude Code: run `uoink connect claude-code` in a new terminal, then run the command it prints.

**Mac (Apple Silicon, macOS 15 or later; preview)**

1. Download `Uoink-3.14.1-macos-arm64.dmg` and check its SHA-256 against `SHA256SUMS.txt`.
2. Open the DMG, drag Uoink to Applications, eject the disk, then open Uoink from Applications.
3. In Chrome, open `chrome://extensions`, turn on **Developer mode** and click **Load unpacked**. The dashboard's **Get the extension** card copies the extension's folder path; in the picker, press ⌘⇧G, paste it and press Return.
4. Claude Desktop: install `uoink-3.14.1-macos.mcpb`.

See [docs/mac/INSTALL.md](https://github.com/ryanbiddy/uoink/blob/v3.14.1/docs/mac/INSTALL.md) for login startup, logs and uninstalling.

**Linux (headless)**

```sh
git clone https://github.com/ryanbiddy/uoink && sh uoink/scripts/linux/install.sh
```

See [docs/linux.md](https://github.com/ryanbiddy/uoink/blob/v3.14.1/docs/linux.md) for options, paths, the capture image and agent setup.

## Upgrading

- Your library and captures stay in place. Upgrading from 3.14.0 adds no database migrations.
- Reload the Uoink extension in `chrome://extensions` after updating.
- Claude Desktop: reinstall the 3.14.1 `.mcpb` and restart Desktop.

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
| `Uoink-Setup-3.14.1.exe` | 519,406,324 B | `cd80b892581a0dfa8586260f67cfa367280af7a6f689c569ca4b95a6bd4f822a` |
| `uoink-3.14.1.mcpb` | 117,591 B | `5e1918a4472677ae9eebd06e60feb70773bf16da90ab4d8ed71356b68fe4d6a9` |
| `Uoink-3.14.1-macos-arm64.dmg` | 696,894,936 B | `df79cbe77d2a12ca430015459bbaa6c6014f659a0a4421258955cb6c3cd4287d` |
| `uoink-3.14.1-macos.mcpb` | 114,124 B | `f09ae36ff9c2ede51bb37afc0b76c8b0b4a73658d225ddd9cccd0c30fd2024a0` |

The Mac DMG is signed with Developer ID and notarized (mac-qualify run 42044198598).
