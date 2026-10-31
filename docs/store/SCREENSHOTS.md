# Store screenshots, 3.12.0

The five files in `screenshots/` are Uoink 3.12.0 captures from 2026-10-31
(`main` at `d5c2b8b`). Each is a 1280x800 PNG, edge to edge, light theme, with
square corners and no padding. They replace the July references. Upload them
in this order.

Every saved source in frame is Creative Commons or public domain. Titles,
URLs, licenses and the shots each appears in are in
[screenshots/SOURCES.md](screenshots/SOURCES.md).

| File | What it shows |
|---|---|
| `screenshots/01-uoink-button-on-youtube.png` | A CC BY lecture on a YouTube watch page in theater mode, with no ad showing. The current Uoink button sits beside Like, Share and Save with its green connected dot. |
| `screenshots/02-your-local-library.png` | `/dashboard#library` with the 8-item review library sorted Title A to Z: current navigation, topics and readable saved items. |
| `screenshots/03-read-a-saved-source.png` | The reader at `/dashboard#item/V9w3Fhh9BkM`: source title and channel, timestamped transcript and a captured frame. |
| `screenshots/04-search-your-corpus.png` | A Library search for `orbit` with its 5 real matches across videos and pages. |
| `screenshots/05-helper-setup.png` | `setup.html?source=offline` with no helper running: the helper requirement, Download for Windows and the "Uoink is offline" state. |

## How they were made

- The dashboard shots come from an isolated 3.12.0 helper with an empty review
  profile, never Ryan's library. Each source was saved through the helper's
  own capture routes. Counts, times and results are what the app showed.
- Shots 01 and 05 use a disposable browser profile with a temporary copy of
  `extension/`. The copy points at the isolated helper (01) or at a port with
  nothing listening (05). The repository's extension is unchanged.
- No account was signed in. No bookmarks, other tabs, notifications, local
  paths or keys are in frame. No `uoink.video` text is visible.

## Known limits

- **01:** The narrow black bands beside the video are YouTube's own theater
  mode player at a 16:10 window size. They are not padding. Theater mode keeps
  YouTube's unrelated recommendations out of frame.
- **05:** The disabled "Uoink this video" button is below the frame. Step 3
  of the setup page suggests a named podcast episode, and that block sits
  directly above the button. To show the button, recapture after that
  suggestion changes to a Creative Commons source.

## Other images

The three promo tiles were also inspected. They contain brand copy, no old
domain or UI screenshot. The 440x280 small tile and 1400x560 marquee are usable
as optional brand artwork. The 920x680 large tile is a spare, not a current CWS
upload field. Use `extension/icons/icon128.png` for the store icon.

Google requires at least one screenshot and permits up to five. See Google's
[image requirements](https://developer.chrome.com/docs/webstore/images).
