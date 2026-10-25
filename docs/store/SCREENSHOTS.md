# Screenshot recapture list for 3.11

All five existing files are 1280x800 and were inspected on 2026-10-24.
They are July references, not approved 3.11 listing images. No replacement
screenshots were fabricated or added in this pass.

| Existing file | What is outdated | Exact 1280x800 recapture |
|---|---|---|
| `screenshots/01-uoink-button-on-youtube.png` | Old button styling, black padding and an unrelated ad in the player. | On a YouTube watch page for a video you own or may save, show the current Uoink button and source title. Wait until any ad has ended. Capture the page edge to edge without black bars. Keep this filename. |
| `screenshots/02-your-local-library.png` | July sidebar and card grid, including the old Generate navigation. | In the 3.11 helper, open `/dashboard#library` with a small library of permitted sources. Show the current navigation and readable saved items. Keep this filename. |
| `screenshots/03-write-from-your-corpus.png` | July Generate/X composer, old controls and generated claims that are unnecessary for a capture listing. | Replace with `03-read-a-saved-source.png`: open a real saved item from Library at `/dashboard#item/<saved-id>` and show its reader, source attribution and timestamped text. |
| `screenshots/04-search-your-corpus.png` | July search layout and old card styling. | In `/dashboard#library`, search for a term that occurs in a permitted saved source. Show the query and real matching results in the current layout. Keep this filename. |
| `screenshots/05-auto-organized-by-topic.png` | Near-duplicate of #2; it does not demonstrate automatic topic organization. | Replace with `05-helper-setup.png`: open `chrome-extension://<actual-extension-id>/setup.html?source=offline` with the helper stopped in a test environment. Show the helper requirement, Offline state and disabled capture button. |

These route paths identify the screens; this pass did not open the installed
helper or use Ryan's library. Use a separate review profile/library for new
captures. Keep private paths, keys, account menus and unrelated personal tabs
out of frame. Use actual UI and actual source results, with no invented counts.

No visible `uoink.video` text was found in these five images. #3 visibly uses
`uoink.app`. The old domain remains in the historical handoff drafts; if a
recapture or a different asset shows it, replace that asset before upload.

The three promo tiles were also inspected. They contain brand copy, no old
domain or UI screenshot. The 440x280 small tile and 1400x560 marquee are usable
as optional brand artwork. The 920x680 large tile is a spare, not a current CWS
upload field. Use `extension/icons/icon128.png` for the store icon.

Google requires at least one screenshot and permits up to five. For a shorter
submission, use fresh #1 plus #5, then add the other recaptures when ready.
Use full-bleed PNGs at 1280x800, square corners, with no padding. See Google's
[image requirements](https://developer.chrome.com/docs/webstore/images).
