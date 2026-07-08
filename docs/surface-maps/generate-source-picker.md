# Surface map: Generate source picker

The "Source uoink" control at the top of the Generate tab's "Write from a
source" form (`assets/dashboard/index.html`). Rebuilt in U-02 (UX-08,
UX-05). This map describes the surface after that rebuild.

## What it is

A combobox that picks the saved uoink a draft will be grounded in. It has
two mutually exclusive visual states inside `#writingSourceCombo`:

- **Browse mode** (nothing selected): a search input
  (`#writingSourceSearch`, `role="combobox"`, placeholder "Browse saved
  uoinks, newest first") plus a dropdown (`#writingSourceOptions`,
  `role="listbox"`).
- **Selected mode**: the input hides and a two-line chip
  (`#writingSourceChip`) renders in its place: 88px thumbnail, title
  clamped to 2 lines, channel | topic | duration subtitle, and a separate
  clear button. The full title lives in the chip's `title` tooltip.

The actual selection is carried by a hidden input (`#writingSource`,
holding `writingRowId(row)`) and `state.writingSelectedSourceRow`. Every
downstream consumer (attribution line, screenshots, workspace,
`generateWriting` request `source_yoink_id`) reads those two; the visible
chip is display only.

## Data source

The picker owns a dedicated corpus list, separate from the Library tab:

- `state.writingSourceRows`, filled by `loadWritingSources()` via
  `GET /memory/search?limit=200` (token-gated, no filters, index order =
  newest first). Fetched on Generate tab open and on first focus; cached
  until `loadLibrary({reset:true})` invalidates it
  (`state.writingSourceLoaded = false`), so new saves show up.
- Fallback: if that fetch hasn't landed or failed, `writingSourceRowsAll()`
  serves `state.library` (paged, possibly filter-shaped) so the picker
  degrades instead of going empty.

The 200 cap matches the `/memory/search` server-side maximum. If a corpus
outgrows it, the picker shows the newest 200 and search still reaches them
all only within that window; revisit then.

## Behaviors and states

| Interaction | Result |
|---|---|
| Focus/click the input | Dropdown opens listing ALL sources newest-first (no display cap; the list scrolls at `max-height: 320px`). Input stays empty. Nothing is auto-selected, Generate stays disabled. |
| Type | Case-insensitive substring filter over title + channel/topic/duration subtitle + source URL. |
| No matches | "No matching uoinks." row with recovery copy. No hidden pick can survive here (see invariant below). |
| Empty corpus | "Nothing saved yet." row pointing at capture. |
| Click an option | Selection: hidden id + state row set, chip renders, input hides, dropdown closes, topic autofills from the source if the Topic field was empty, screenshots load. Generate enables. 2 clicks total from tab open. |
| ArrowDown / ArrowUp | Moves the `.active` option (wraps around), sets `aria-activedescendant` to the option id (`writingSourceOpt<n>`), scrolls it into view. Opens the list first if closed. |
| Enter | Picks the active option (or the first when none is active) while the list is open. |
| Escape | Closes the list. `preventDefault` stops the search input's native text-clear, whose `input` event would otherwise reopen it. |
| Click outside | Closes the list (global click handler on `#writingSourceCombo`). |
| Click chip body | Back to browse mode via `clearWritingSource({focus:true})`: selection dropped, input shown empty and focused, full list open. |
| Click chip x (`aria-label="Clear selected source"`) | Same clear, without refocus. |

## Invariants

1. **The selected title never becomes the filter text.** The input is never
   prefilled; selection renders as a chip, not as input text. (Root cause
   of the old 1-of-31 bug.)
2. **No hidden stale pick (G-01).** The input only exists while nothing is
   selected, and both paths back to it run `clearWritingSource()`, which
   clears `#writingSource` and the state row and disables Generate. A typed
   no-match query therefore cannot mask a lingering selection.
3. **The render pass is read-only on selection.** `syncWritingSourceOptions`
   never writes `#writingSource` or the input value.

## Routes consumed

- `GET /memory/search?limit=200` -- picker corpus list. Shape:
  `{ok, state, total, corpus_total, results: [row]}` where each row is an
  enriched uoink (`video_id`, `title`, `channel`, `topic`, `hook_type`,
  `duration_seconds`, `yoinked_at`, `source_url`, `thumbnail_path?`).
- `GET /yoinks/<id>/screenshots` -- fired by selection via
  `loadWritingScreenshots()`.
- Thumbnails render through the shared `data-file-img` loader
  (`GET /file?path=`).

## Thumbnail presentation

The dropdown option (`.combo-option`) and the selected chip
(`.source-chip-main`) share an 88px 16:9 `.combo-thumb` (bumped from 58px
so a user can actually recognise the source at a glance). Text sources
(X posts, articles) have no `thumbnail_path`, so `.combo-thumb` renders
empty; a `:empty::after` "no preview" glyph fills it instead of a dead
grey square. The writing screenshot picker (`.screenshot-picker`) sizes
its tiles with `repeat(auto-fill, minmax(158px, 1fr))` so they stay large
instead of shrinking to a fixed 4-across grid. Selection logic is
untouched -- this is presentation only.

## Tests / proof

- `tests/test_u02_source_picker.py` -- static contract (dedicated list, no
  prefill/auto-select/cap, chip markup, keyboard wiring).
- `tests/test_generate_picker_no_match.py` -- the G-01 stale-pick guarantee
  in its post-U-02 structural form.
- `handoff/qa-harness-playwright/u02-source-picker-check.js` -- live-drive
  proof: 31/31 on focus, newest first, 2-click pick, chip collapse,
  keyboard pick, no-match honesty, Escape close, at 1280/1100/900.

## Related, deliberately out of scope

- The Script tab's legacy `#scriptSourceOptions` picker is a separate
  control (hidden Build/Script surface) and still behaves the old way.
- Deep-linking into Generate with a pre-picked source is U-04; it should
  call `selectWritingSourceById(id)` after `loadWritingSources()` resolves.
