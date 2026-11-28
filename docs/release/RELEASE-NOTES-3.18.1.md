# Uoink 3.18.1: pin the moment, save Hacker News, cleaner transcripts

## What's new

Save a YouTube video partway through and Uoink now pins the moment you were watching. Open the item later to copy that quote with a link that lands two seconds before that moment, so you hear it in context. Each save keeps up to 20 pins, and Claude can read them too.

- **Save Hacker News discussions.** Paste or Uoink a thread to keep its nested replies, each with its own link. Saving a comment link puts that reply first. **Save linked story** captures the article or video the thread is about.
- **Cleaner transcripts.** Whisper sometimes invents a "Thanks for watching!" over silence. Uoink now holds those lines back from search, citations and exports, and **Show them** puts them in view. `uoink tidy-transcripts` checks older saves. YouTube auto-captions read as sentences instead of repeating rolling lines, and `uoink repair-captions` fixes older saves while keeping the original.
- **Follow Apple Podcasts links.** Paste a show link to follow its feed, or an episode link to save just that episode. Episodes sort by release date even when a show changes its date format, and same-titled episodes keep their own audio.
- **Connect your agent in one step.** `uoink connect claude-code --write` adds Uoink through the Claude CLI. For Claude Desktop, Cursor, Cline and others, `--write` previews the change and backs up your settings first. Desktop setup also finds the Microsoft Store install on Windows.
- **One dashboard window on Windows.** Opening Uoink from the Start menu or tray brings the dashboard you already have forward instead of starting a second one.
- **Pick up unfinished captures.** Your agent can list interrupted captures and tell you whether Finish can reuse the video on disk.
- **Fixes from 3.18.0.** Podcast episodes open in the reader again, **Transcribe again** saves its transcript, and on a Mac `uoink connect --write` saves your client's settings.
- **Security.** A full review fixed issues around linked library folders, media links and thumbnails, startup diagnostics, phone pairing, private session names and approval for new capture sites. Dependencies were updated, including HTTPX2, Pydantic and python-multipart.

The MCP server still exposes 99 tools by default, 36 with `UOINK_MCP_TOOLSET=core`, 9 with `search` and 7 with `research`.

## Install or update

**Update from 3.15.1 or later.** Open Settings, Updates. On Windows press **Update now**. On a Mac press **Download update**. Uoink checks the download against the release's `SHA256SUMS.txt` before it runs or opens it. If you are on an older version, install the usual way below.

**Windows 10/11**

1. Download `Uoink-Setup-3.18.1.exe` and `SHA256SUMS.txt`, then check the installer's SHA-256.
2. The Windows installer is unsigned, so SmartScreen may warn. Choose **More info -> Run anyway**.
3. Press **Install**. To choose the folder or shortcuts, tick **Choose the install folder and shortcuts** first.
4. New install: on first launch, use the setup splash to open `chrome://extensions` and copy the extension path. Turn on **Developer mode**, click **Load unpacked** and select that folder. Then click Chrome's puzzle-piece **Extensions** icon and pin **Uoink**.
5. Claude Desktop: install `uoink-3.18.1.mcpb`.
6. Claude Code: run `uoink connect claude-code` in a new terminal, then run the command it prints.

**Mac (Apple Silicon, macOS 15 or later; preview)**

1. Download `Uoink-3.18.1-macos-arm64.dmg` and check its SHA-256 against `SHA256SUMS.txt`.
2. Open the DMG, drag Uoink onto Applications, eject the disk, then open Uoink from Applications.
3. In Chrome, open `chrome://extensions`, turn on **Developer mode** and click **Load unpacked**. The dashboard's **Get the extension** card copies the extension's folder path; in the picker, press Command-Shift-G, paste it and press Return.
4. Claude Desktop: install `uoink-3.18.1-macos.mcpb`.

See [docs/mac/INSTALL.md](https://github.com/ryanbiddy/uoink/blob/v3.18.1/docs/mac/INSTALL.md) for login startup, logs and uninstalling.

**Linux (headless)**

```sh
git clone https://github.com/ryanbiddy/uoink && sh uoink/scripts/linux/install.sh
```

See [docs/linux.md](https://github.com/ryanbiddy/uoink/blob/v3.18.1/docs/linux.md) for options, paths, the capture image and agent setup.

## Upgrading

Your library stays in place. Upgrading from 3.18.0 applies migrations 0040 and 0041 for podcast episode order and moment pins. Reload the extension in `chrome://extensions`. For Claude Desktop, reinstall the bundle for your platform and restart Desktop. Older saves keep their transcripts until you run `uoink tidy-transcripts --apply` or `uoink repair-captions ID --apply`.

## Known limits

- Moment pins come from YouTube saves. Other sources save without a pin.
- Transcript review judges Whisper lines by their speech scores. Older saves stored without speech scores are only checked for labels such as [Music] and for closing phrases.
- The Windows installer is unsigned. The Mac build requires Apple Silicon and macOS 15 or later. Linux runs headless.

## Checksums

| File | Size | SHA-256 |
| --- | --- | --- |
| `Uoink-Setup-3.18.1.exe` | 577,842,445 B | `471cac170787dbe22f1eaa9ccf9a5d086be801f72b43eb74ccd95ff334cea822` |
| `uoink-3.18.1.mcpb` | 124,958 B | `0e964c769d7d7b19dbdadd5b5cb5c797142827684b79b316b3668096e8801eec` |
| `Uoink-3.18.1-macos-arm64.dmg` | TBD | TBD |
| `uoink-3.18.1-macos.mcpb` | TBD | TBD |
