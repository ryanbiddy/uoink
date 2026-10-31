# Uoink 3.12.0

## What's new

- **Transcripts with no setup.** Every download now includes Whisper's base transcription model. A video with no captions is transcribed on your computer from the first capture, with no model download. A model you downloaded yourself still takes precedence, and other sizes download only when you ask. The Windows installer is about 129 MB larger as a result.
- **Needs attention means something.** The badge names the problem (`No transcript`, `Comments failed`, `2 issues`). Click it for a drawer that says why and offers **Re-uoink**, which refreshes the item in place. Web pages, text posts and images are no longer flagged for a transcript, screenshots or comments they could never have. A row reads **Done** only when nothing is outstanding. Existing items are corrected the next time the Library loads.
- **Music isn't a missing transcript.** When Whisper hears no speech (music, silence), the row reads **Done · no speech found**, and the note says so instead of blaming missing captions.
- **Allow a site from the Library.** A page turned away by the site allowlist gets **Allow <site>** on its row. One click adds the site and saves the page. In Settings, Enter adds a site, and a pasted link saves just its host.
- **Light, Dark or Match Windows.** Settings > App > **Appearance**. The Uoink window and a browser tab follow the same choice.
- **Back stays in reach.** Reading an item, the Back row stays at the top as you scroll. Esc closes the reader, and Back returns you to the same place in the Library.
- **Screenshots at the right time.** Each screenshot used to be taken half an interval after its label. A clip shorter than half the interval got none, so re-capturing a short X clip failed. Both are fixed.
- **Fresh dashboard after an upgrade.** A tab left open across an upgrade now shows the new dashboard instead of the old one for up to five minutes.
- Still 91 tools (35 in core mode).

## Install or update

**Windows 10/11**

1. Download `Uoink-Setup-3.12.0.exe` and `SHA256SUMS.txt`, then check the installer's SHA-256.
2. The Windows installer is unsigned, so SmartScreen may warn. Choose **More info -> Run anyway**.
3. New install: on first launch, use the setup splash to open `chrome://extensions` and copy the extension path. Turn on **Developer mode**, click **Load unpacked** and select that folder. Then click Chrome's puzzle-piece **Extensions** icon and pin **Uoink**.
4. Claude Desktop: install `uoink-3.12.0.mcpb`.
5. Claude Code: run `uoink connect claude-code` in a new terminal, then run the command it prints.

**Mac (Apple Silicon, macOS 15 or later; preview)**

1. Download `Uoink-3.12.0-macos-arm64.dmg` and check its SHA-256 against `SHA256SUMS.txt`.
2. Open the DMG, drag Uoink to Applications, eject the disk, then open Uoink from Applications.
3. In Chrome, open `chrome://extensions`, turn on **Developer mode** and click **Load unpacked**. The dashboard's **Get the extension** card copies the extension's folder path; in the picker, press ⌘⇧G, paste it and press Return.
4. Claude Desktop: install `uoink-3.12.0-macos.mcpb`.

See [docs/mac/INSTALL.md](https://github.com/ryanbiddy/uoink/blob/v3.12.0/docs/mac/INSTALL.md) for login startup, logs and uninstalling.

## Upgrading

- Your library and captures stay in place.
- Reload the Uoink extension in `chrome://extensions`.
- Claude Desktop: reinstall `uoink-3.12.0.mcpb` and restart Desktop.
- Items saved without a transcript because no model was on the device can be captured again (Re-uoink in the drawer). They refresh in place.

## Known limits

- Chrome (tested). Edge and Brave may work but are not tested.
- Mac: Apple Silicon only. Uoink doesn't update itself yet, so install new versions from the DMG. macOS still shows Uoink's alerts as coming from Script Editor. Library mirroring is unavailable on Mac.
- Whisper runs only on videos without usable captions, and Uoink never downloads a model during a capture.

## Checksums

| File | SHA-256 |
| --- | --- |
| `Uoink-Setup-3.12.0.exe` | `59efed61221a7f7bddfa3a65d89c8ffc56f5ea6c309034d52f31dfa9b15824fa` |
| `uoink-3.12.0.mcpb` | `3708adcebd77e9f583e58649e3fd803f91b3e826affe4400710c9e8494d69c9f` |
| `Uoink-3.12.0-macos-arm64.dmg` | `f27778282eecf81d17e97b463510af942f14149d5a8420a09a18eea62eb27382` |
| `uoink-3.12.0-macos.mcpb` | `28973339991d666506e0518aa4ba1255e647d1a053c2078de0f6fa372693349f` |
