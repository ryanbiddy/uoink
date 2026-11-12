# Uoink 3.17.0

## What's new

This release makes Uoink easier to come back to, easier to set up from a phone, and quieter when you save.

- **Saving stays out of your way.** Saving no longer opens a Claude tab or overwrites your clipboard. Your save goes to your library, where your AI can already search it. The notification offers **Copy for Claude** and **Copy for ChatGPT** if you want to paste it somewhere, and the YouTube button turns into "Saved. Copy for Claude" for a few seconds. Prefer the old way? The new **After a save** setting (toolbar popup, or Settings > Capture) has Copy then open Claude, Copy then open ChatGPT and Copy only.
- **Rediscover what you saved.** A Rediscover shelf on the Library shows up to four saves each day: one from about a week ago, one from about a month ago, one saved on this day in an earlier year, or one you never opened. **Idea starters** group saves that share a topic ("You saved 3 things about onboarding. Compare what they say.") with Write from these and Copy prompt. It all runs on your computer, with no network and no AI calls. A Settings switch turns both off.
- **Podcast episodes picked for you.** Turn on **Suggest podcasts** in Settings and the For You tab shows episodes that match what you save, each with the reason ("Because you saved 3 things about pricing"). **Save** pulls in just that episode and its transcript without following the show. **Follow show** and **Not interested** are separate. It's off until you turn it on: when on, Uoink sends a few topic words (never titles, links or transcripts) to Apple's podcast search about once a day, and the setting shows you the exact words.
- **Phone inbox setup you can follow.** Settings > Phone inbox is now three numbered steps: make your relay (one Deploy to Render button), connect it (with a clear Connected or Not connected and the reason), and scan a QR code with your phone. The QR code opens a page on your own relay where you can paste links, add Uoink to the Android share sheet, or follow the one-time iPhone Shortcut steps. The QR code is drawn on your computer, and the key in it never reaches a server log. If your relay is older than this release, Uoink tells you to update it (Render > uoink-relay > Manual Deploy).
- **Install from your terminal.** `npx uoink` downloads the official installer, checks it against the release's `SHA256SUMS.txt`, installs Uoink and points you at `uoink connect`. Once Uoink is installed, `npx uoink <command>` runs the Uoink CLI. (The npm package goes live shortly after this release.)
- **Ready for the Chrome Web Store.** A store install opens a setup page that finds the desktop app, or links the right download for your computer and connects by itself once Uoink starts. (The listing goes live after Google's review. Until then, load the extension from the setup splash as before.)
- **A stress test of every screen.** We fed the dashboard, the toolbar popup, the YouTube button, the tray, the command line and the AI tool errors the worst data we could find (long names, unbreakable links, right-to-left text, emoji, thousands of items) and fixed what broke:
  - Titles longer than 300 characters are cut at a safe point, never inside an emoji or accent, for every source.
  - Long error messages, addresses, topics and author names wrap or end in an ellipsis with the full text on hover.
  - Long transcripts show the first 200 paragraphs with Show more.
  - The speaker timeline covers the whole talk.
  - The YouTube button no longer grows with a long research session name.
  - AI tool errors no longer show file paths and say what to do next.
  - `uoink serve --help` prints help instead of starting the helper.

The MCP server still exposes 99 tools by default, 36 with `UOINK_MCP_TOOLSET=core`, 9 with `search` and 7 with `research`.

## Install or update

**Update from 3.15.1 or later.** Open Settings, Updates. On Windows press **Update now**. On a Mac press **Download update**. Uoink checks the download against the release's `SHA256SUMS.txt` before it runs or opens it. If you are on an older version, install the usual way below.

**Windows 10/11**

1. Download `Uoink-Setup-3.17.0.exe` and `SHA256SUMS.txt`, then check the installer's SHA-256.
2. The Windows installer is unsigned, so SmartScreen may warn. Choose **More info -> Run anyway**.
3. Press **Install**. To choose the folder or shortcuts, tick **Choose the install folder and shortcuts** first.
4. New install: on first launch, use the setup splash to open `chrome://extensions` and copy the extension path. Turn on **Developer mode**, click **Load unpacked** and select that folder. Then click Chrome's puzzle-piece **Extensions** icon and pin **Uoink**.
5. Claude Desktop: install `uoink-3.17.0.mcpb`.
6. Claude Code: run `uoink connect claude-code` in a new terminal, then run the command it prints.

**Mac (Apple Silicon, macOS 15 or later; preview)**

1. Download `Uoink-3.17.0-macos-arm64.dmg` and check its SHA-256 against `SHA256SUMS.txt`.
2. Open the DMG, drag Uoink onto Applications, eject the disk, then open Uoink from Applications.
3. In Chrome, open `chrome://extensions`, turn on **Developer mode** and click **Load unpacked**. The dashboard's **Get the extension** card copies the extension's folder path; in the picker, press ⌘⇧G, paste it and press Return.
4. Claude Desktop: install `uoink-3.17.0-macos.mcpb`.

See [docs/mac/INSTALL.md](https://github.com/ryanbiddy/uoink/blob/v3.17.0/docs/mac/INSTALL.md) for login startup, logs and uninstalling.

**Linux (headless)**

```sh
git clone https://github.com/ryanbiddy/uoink && sh uoink/scripts/linux/install.sh
```

See [docs/linux.md](https://github.com/ryanbiddy/uoink/blob/v3.17.0/docs/linux.md) for options, paths, the capture image and agent setup.

## Upgrading

- Your library and captures stay in place. Upgrading from 3.16.3 adds one database migration (0034: when you last opened an item, for Rediscover).
- Reload the Uoink extension in `chrome://extensions` after updating.
- Claude Desktop: reinstall the 3.17.0 `.mcpb` and restart Desktop.
- Phone inbox users: open your relay in Render and choose **Manual Deploy** to get the phone page and QR pairing. Your existing phone Shortcut keeps working either way.
- After a save now defaults to Stay on the page. If you liked the old copy-and-open-Claude flow, pick **Copy, then open Claude** in the toolbar popup.

## Known limits

- The phone page's Android share target and iPhone Home Screen behavior were tested in a desktop browser, not yet on real phones.
- Podcast suggestions come from words and phrases in your saved titles, so a small or very mixed library gets broader picks. Not interested hides that one episode; it doesn't yet learn from it.
- "You haven't opened this yet" on Rediscover can show items you opened before this update, until Uoink has seen you open them once.
- The notification's Copy for Claude and Copy for ChatGPT buttons copy the saved markdown without embedded screenshots. The in-page button and the copy choices in After a save still copy the full paste version.
- The extension's Watch Later, X bookmarks and Reddit saved collectors have automated tests but have not yet been tried in a real browser. The file imports are the tested path.
- YouTube often blocks cloud IP addresses. On a Linux server or container, captions can fail, and the local Whisper fallback helps only when the audio download itself works.
- Research doesn't capture podcast episodes yet: it lists them, then skips them with `podcast_capture_later`.
- Linux is headless only: no tray, splash or dashboard window.
- The Windows installer is unsigned, so updates are checked against the release's published checksums, not a code signature.
- Mac: Apple Silicon only.
- Chrome (tested). Edge, Brave, Arc, Opera and Vivaldi install Chrome Web Store extensions, but are not tested.

## Checksums

| File | Size | SHA-256 |
| --- | --- | --- |
| `Uoink-Setup-3.17.0.exe` | WIN_EXE_SIZE B | `WIN_EXE_SHA256` |
| `uoink-3.17.0.mcpb` | WIN_MCPB_SIZE B | `WIN_MCPB_SHA256` |
| `Uoink-3.17.0-macos-arm64.dmg` | MAC_DMG_SIZE B | `MAC_DMG_SHA256` |
| `uoink-3.17.0-macos.mcpb` | MAC_MCPB_SIZE B | `MAC_MCPB_SHA256` |

The Mac DMG is signed with Developer ID and notarized (mac-qualify run MAC_RUN_ID).
