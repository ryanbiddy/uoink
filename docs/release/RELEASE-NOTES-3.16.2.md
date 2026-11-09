# Uoink 3.16.2

## What's new

This release puts Deno inside the Mac app, makes the Deno check in Diagnose stricter and refreshes libraries to clear open security alerts.

- **Deno ships inside the Mac app.** YouTube capture on a Mac can now solve YouTube's player challenges without you installing anything, like Windows since 3.16.1. Deno is signed with one extra permission, allow-jit, which it needs to run JavaScript under macOS's hardened runtime. No other file in the app gets any extra permission. The DMG grows by about 18 MB.
- **Diagnose checks that Deno can run JavaScript.** It no longer only checks that Deno starts. A Deno that cannot run code, for example one blocked by macOS code signing, shows as a warning.
- **Security.** The Windows installer's bundled libraries are refreshed to clear open alerts: PyJWT 2.15.1, aiohttp 3.14.5, urllib3 2.8.0, setuptools 84.2.1, Mako 1.4.3, multidict 6.9.1, yarl 1.25.1 and the OpenTelemetry packages 1.45.1. NLTK moves to upstream 3.10.4. crawl4ai is no longer installed by default in source installs. Neither installer ever shipped it. Uoink uses it only if you install it yourself.
- **Linux** still uses a Deno 2.3 or newer on your PATH.

The MCP server still exposes 99 tools by default, 36 with `UOINK_MCP_TOOLSET=core`, 9 with `search` and 7 with `research`.

## Install or update

**Update from 3.15.1 or later.** Open Settings, Updates. On Windows press **Update now**. On a Mac press **Download update**. Uoink checks the download against the release's `SHA256SUMS.txt` before it runs or opens it. If you are on an older version, install the usual way below.

**Windows 10/11**

1. Download `Uoink-Setup-3.16.2.exe` and `SHA256SUMS.txt`, then check the installer's SHA-256.
2. The Windows installer is unsigned, so SmartScreen may warn. Choose **More info -> Run anyway**.
3. New install: on first launch, use the setup splash to open `chrome://extensions` and copy the extension path. Turn on **Developer mode**, click **Load unpacked** and select that folder. Then click Chrome's puzzle-piece **Extensions** icon and pin **Uoink**.
4. Claude Desktop: install `uoink-3.16.2.mcpb`.
5. Claude Code: run `uoink connect claude-code` in a new terminal, then run the command it prints.

**Mac (Apple Silicon, macOS 15 or later; preview)**

1. Download `Uoink-3.16.2-macos-arm64.dmg` and check its SHA-256 against `SHA256SUMS.txt`.
2. Open the DMG, drag Uoink to Applications, eject the disk, then open Uoink from Applications.
3. In Chrome, open `chrome://extensions`, turn on **Developer mode** and click **Load unpacked**. The dashboard's **Get the extension** card copies the extension's folder path; in the picker, press ⌘⇧G, paste it and press Return.
4. Claude Desktop: install `uoink-3.16.2-macos.mcpb`.

See [docs/mac/INSTALL.md](https://github.com/ryanbiddy/uoink/blob/v3.16.2/docs/mac/INSTALL.md) for login startup, logs and uninstalling.

**Linux (headless)**

```sh
git clone https://github.com/ryanbiddy/uoink && sh uoink/scripts/linux/install.sh
```

See [docs/linux.md](https://github.com/ryanbiddy/uoink/blob/v3.16.2/docs/linux.md) for options, paths, the capture image and agent setup.

## Upgrading
- Your library and captures stay in place. Upgrading from 3.16.1 adds no database migrations.
- Reload the Uoink extension in `chrome://extensions` after updating.
- Claude Desktop: reinstall the 3.16.2 `.mcpb` and restart Desktop.

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
| `Uoink-Setup-3.16.2.exe` | 548,622,064 B | `895e0379e6c9d97d8e1eec5fa8d823b7afb8b54b5b3afc52aad6b4dd702d5a1e` |
| `uoink-3.16.2.mcpb` | 119,763 B | `944da127e8324948bd9e8ad5d57a59c7bf54df40c3e8a900e1c3f6101c886d04` |
| `Uoink-3.16.2-macos-arm64.dmg` | 735,192,482 B | `e89572108fdabb7e6079accc39319dad1f598169ee687e298069eae92f0a7a02` |
| `uoink-3.16.2-macos.mcpb` | 116,301 B | `0556330205fbffad2a61839c32a0c010aa748ec01f4be758edf323e0f88c9ae0` |

The Mac DMG is signed with Developer ID and notarized (mac-qualify run 42623218976).
