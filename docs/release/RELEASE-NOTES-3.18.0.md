# Uoink 3.18.0: finish old saves, capture whole shows and free memory after transcription

## What's new

If you saved a video and later found “No captions available” where its transcript should be, open **Settings > Library and export > Transcribe saves that have no words**. Uoink shows which videos it can use from disk and which it needs to download again. Start the repair and keep saving other things. New captures go first. You can pause, and the repair picks up after a restart. For an interrupted capture, **Finish** reuses the files already on your computer.

- **Capture a back catalog.** In Sources, choose **Save a whole show** and paste a YouTube channel, playlist or podcast feed. Review up to 5,000 episodes and the estimated time and disk space before you start. YouTube runs save captions first. You can opt into local transcription for videos without captions. Podcast episodes use local transcription and keep their audio by default.
- **Save the full text from X.** Save a long post from its open tab, or use **Uoink this article** for an X Article. For pasted links, you can enable FxTwitter in Capture settings. That service receives the post ID and your internet address. Leave it off to use the extension. **Fix cut-off X posts** can repair older saves when FxTwitter is enabled.
- **Keep the web page you read.** On a signed-in or JavaScript-heavy page, click **Uoink this page**. The extension uses Defuddle in your tab to extract the clean text you see. When a pasted link leads to a sign-in or a robot check, Uoink explains what happened and offers to open the page.
- **Put saves on the right shelf.** Uoink uses the text, author and items already on your shelves. Imported folders and playlists become shelves. Open **Tidy Uncategorized** to see suggested moves and the reason for each. Choose individual saves or a whole group. You can undo the move, and a shelf you pick survives a later transcript or index rebuild.
- **Choose how to transcribe.** Local transcription runs in its own processes and frees their memory after two idle minutes. In Capture settings, compare **English, quick** and **English, best** by size and estimated speed. Balanced is included and works offline. To transcribe again, open the saved item and choose **Re-transcribe with** the model you picked. The previous transcript stays available if the job fails.
- **Search by publish date.** Use `published_from` and `published_to` on `/memory/search` to find something by when it came out, even if you saved it months later. Clip tools can read timed cues, including word timings where available, with `uoink cues <id>`.
- **Nine fixes from the smoke tests.** Videos without captions have readable search snippets. Short notes appear under Uncategorized. Library card titles work from the keyboard, and closing a dialog returns focus to its opener. Closing the dashboard or popup frees an activity stream, and repeated dashboard loads can recover from a token request limit. Lite saves explain skipped comments. Settings can show and clean up podcast audio, and extension setup points to the right page for your browser.
- **Capture and security updates.** Video downloads use yt-dlp 2026.10.26. The installer updates cryptography, Starlette and python-multipart. Saved pages strip unsafe links and raw HTML before they reach the reader.

The MCP server still exposes 99 tools by default, 36 with `UOINK_MCP_TOOLSET=core`, 9 with `search` and 7 with `research`.

## Install or update

**Update from 3.15.1 or later.** Open Settings, Updates. On Windows press **Update now**. On a Mac press **Download update**. Uoink checks the download against the release's `SHA256SUMS.txt` before it runs or opens it. If you are on an older version, install the usual way below.

**Windows 10/11**

1. Download `Uoink-Setup-3.18.0.exe` and `SHA256SUMS.txt`, then check the installer's SHA-256.
2. The Windows installer is unsigned, so SmartScreen may warn. Choose **More info -> Run anyway**.
3. Press **Install**. To choose the folder or shortcuts, tick **Choose the install folder and shortcuts** first.
4. New install: on first launch, use the setup splash to open `chrome://extensions` and copy the extension path. Turn on **Developer mode**, click **Load unpacked** and select that folder. Then click Chrome's puzzle-piece **Extensions** icon and pin **Uoink**.
5. Claude Desktop: install `uoink-3.18.0.mcpb`.
6. Claude Code: run `uoink connect claude-code` in a new terminal, then run the command it prints.

**Mac (Apple Silicon, macOS 15 or later; preview)**

1. Download `Uoink-3.18.0-macos-arm64.dmg` and check its SHA-256 against `SHA256SUMS.txt`.
2. Open the DMG, drag Uoink onto Applications, eject the disk, then open Uoink from Applications.
3. In Chrome, open `chrome://extensions`, turn on **Developer mode** and click **Load unpacked**. The dashboard's **Get the extension** card copies the extension's folder path; in the picker, press Command-Shift-G, paste it and press Return.
4. Claude Desktop: install `uoink-3.18.0-macos.mcpb`.

See [docs/mac/INSTALL.md](https://github.com/ryanbiddy/uoink/blob/v3.18.0/docs/mac/INSTALL.md) for login startup, logs and uninstalling.

**Linux (headless)**

```sh
git clone https://github.com/ryanbiddy/uoink && sh uoink/scripts/linux/install.sh
```

See [docs/linux.md](https://github.com/ryanbiddy/uoink/blob/v3.18.0/docs/linux.md) for options, paths, the capture image and agent setup.

## Upgrading

Your library stays in place. Upgrading from 3.17.0 applies migrations 0037, 0038 and 0039 for manual shelf choices, publish dates and podcast follows. Reload the extension in `chrome://extensions`. For Claude Desktop, reinstall the bundle for your platform and restart Desktop.

## Known limits

- A missing source cannot be transcribed unless its media is still on disk. YouTube can delay a whole-show run, and local transcription needs a downloadable audio track.
- Two simultaneous transcription jobs can hold two models in memory. The English model downloads are optional and require internet access.
- The Windows installer is unsigned. The Mac build requires Apple Silicon and macOS 15 or later. Linux runs headless.

## Checksums

| File | Size | SHA-256 |
| --- | --- | --- |
| `Uoink-Setup-3.18.0.exe` | 577,568,664 B | `2b2cd9d423935432cdf74076bc49f1a39fdd5b6e4a12e6c55d1c481f2d14d160` |
| `uoink-3.18.0.mcpb` | 121,468 B | `f9868fca1d57c9d2dc5b0b0304c7e2862f69ec22bdde6213a2f2adbf2623e092` |
| `Uoink-3.18.0-macos-arm64.dmg` | 542,603,875 B | `5e1c656dacee1b928f559148c4c3492bf6a6c0fc392b1cb4592eb4afceb87be6` |
| `uoink-3.18.0-macos.mcpb` | 117,917 B | `29ed2b4bd30236563b9f3f8e4e266025582f86c9126a9daf4a6bfbd0f364eb64` |
