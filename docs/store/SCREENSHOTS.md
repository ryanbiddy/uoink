# Store screenshots, 3.17.0

Everything in `screenshots/` is a 1280x800 PNG. Google requires at least one
and allows five. Upload these five in this order:

| # | File | What it shows |
|---|---|---|
| 1 | `01-uoink-button-on-youtube.png` | A CC BY lecture on a YouTube watch page with the Uoink button beside Like, Share and Save and its green connected dot. |
| 2 | `02-your-local-library.png` | The local Library with 8 saved items, navigation and topics. |
| 3 | `03-read-a-saved-source.png` | The reader: source title and channel, timestamped transcript, a captured frame. |
| 4 | `04-popup-connected-3.17.0-2026-11-12.png` | The toolbar popup when the app is running: this tab, paste a link, recent captures with Read and Copy Markdown. |
| 5 | `05-setup-needs-app-3.17.0-2026-11-12.png` | The setup tab a store install opens: "Uoink needs its free desktop app", why, what happens next, the download. |

Spares, not for the five slots: `06-setup-connecting-3.17.0-2026-11-12.png`
(waiting for the app), `07-setup-connected-3.17.0-2026-11-12.png` (Connected and
what to try first), `08-setup-intel-mac-3.17.0-2026-11-12.png` (the Intel Mac
note), `09-popup-offline-3.17.0-2026-11-12.png`, and `10-search-your-corpus.png`
(a library search for "orbit"). Use a spare in place of any of 1 to 5 if you want
a different story, for example 07 to show the finished setup.

## Which are new and which are kept

- 04 to 09 were captured 2026-11-12 from this repo's 3.17.0 build with mock data
  (see below). They match the shipped setup page and popup.
- 01, 02, 03 and 10 are the 3.12.0 captures from 2026-10-31. They need a real
  helper and a captured library, which a build lane cannot make, so they were
  not retaken. Before submitting, open the 3.17.0 app, look at the Library and
  reader, and swap in a fresh capture if the look has changed enough to mislead.
  Their sources and licenses are in `screenshots/SOURCES.md`.

## How the 3.17.0 shots were made

`node scripts/store_screenshots.mjs <output-folder>` serves `extension/` from a
throwaway local server, opens each page in headless Chrome, and replaces the
`chrome.*` APIs and the helper's HTTP replies with in-page stubs. No helper ran,
nothing was installed, no library or account was touched. The popup is the real
`popup.html` centered on a neutral 1280x800 canvas. Mock data: two saved items
from the Creative Commons sources listed in `screenshots/SOURCES.md` and the
current tab being the OpenStax Mercury lecture. Rerun the script after any
setup page or popup change and copy the files over.

## Known limits

- Shot 01: the narrow black bands beside the video are YouTube's own theater
  mode at a 16:10 window. They are not padding.
- The popup in 04 will look different once the "After a save" lane's popup
  changes land. Rerun the script on the final build before uploading.
- The YouTube thumbnail in the popup is loaded live from YouTube for that CC video.

## Other images

The three promo tiles in `tiles/` contain brand copy, no old domain or UI
screenshot. The 440x280 small tile and 1400x560 marquee are optional artwork.
The 920x680 large tile is a spare. Use `extension/icons/icon128.png` for the
store icon. See Google's [image requirements](https://developer.chrome.com/docs/webstore/images).
