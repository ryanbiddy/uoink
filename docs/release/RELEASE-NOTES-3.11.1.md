# Uoink 3.11.1

## What's new

- **Transcripts for X videos without captions.** Most X videos have no captions, and Uoink's local Whisper fallback never worked on them, because it got a video-only file. Now Uoink checks for audio and, when there is none, downloads the audio once and transcribes that. On one PC this had failed 529 times since July. If a video truly has no sound, the note says "No transcript" and why.
- **Saves that stick.** Some saves could report success and then disappear when the helper closed: tags, claims, style anchors, allowed sites, channels, writing drafts and workspaces. Until then, other apps found the library locked. Every save now commits right away.
- **The helper address opens the dashboard.** Typing `127.0.0.1:5179` into a browser now opens the dashboard instead of showing an error.
- **Better saved articles.** A built-in port of Mozilla Readability picks the main article and keeps headings, lists, quotes, code, tables and links, plus the title, author and date. Paywalls, login walls and empty pages are labeled failures instead of saved as articles.
- **Complete X posts.** Saved posts keep quote posts, photo alt text, video variants, expanded links and real counts, and say whether the text is complete or truncated.
- **The helper restarts itself.** If the Uoink helper crashes, a per-user scheduled task restarts it (up to 3 times in 10 minutes). Quit stays quit until you log in again or start it yourself.
- **Clearer tool descriptions** for AI apps and directories. Still 91 tools (35 in core mode).

## Install or update

1. Download `Uoink-Setup-3.11.1.exe` and `SHA256SUMS.txt`, then check the installer's SHA-256. Windows 10/11.
2. The Windows installer is unsigned, so SmartScreen may warn. Choose **More info -> Run anyway**.
3. New install: on first launch, use the setup splash to open `chrome://extensions` and copy the extension path. Turn on **Developer mode**, click **Load unpacked** and select that folder. Then click Chrome's puzzle-piece **Extensions** icon and pin **Uoink**.
4. Claude Desktop: install `uoink-3.11.1.mcpb`.
5. Claude Code: run `uoink connect claude-code` in a new terminal, then run the command it prints.

## Upgrading

- Your library and captures stay in place.
- The installer replaces the old startup entry with the per-user scheduled task.
- Reload the Uoink extension in `chrome://extensions`.
- Claude Desktop: reinstall `uoink-3.11.1.mcpb` and restart Desktop.
- X videos saved before this release without a transcript can be captured again to get one.

## Known limits

- Chrome (tested). Edge and Brave may work but are not tested.
- The Whisper fallback needs a Whisper model you have already downloaded in Settings. Uoink never downloads one during a capture.
- The Mac preview is not part of this release.

## Checksums

| File | SHA-256 |
| --- | --- |
| `Uoink-Setup-3.11.1.exe` | `a411f413342f7c0d0a1d75d0ffc445f6fa3fbe525de32233d4e4d3670fb98fd1` |
| `uoink-3.11.1.mcpb` | `4db1dd3d18f594bd72da34586da11499b0df7c95e2d9d3135ae3243c98ae07da` |
