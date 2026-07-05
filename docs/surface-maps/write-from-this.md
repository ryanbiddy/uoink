# Surface map: "Write from this" deep link

The primary path from a saved source to a draft, added in U-04 (UX-09).
Before it, the only route was Generate tab > re-find the same video in the
picker. Lives in `assets/dashboard/index.html`.

## Entry points

1. **Every Library card** -- `.card-write` button at the bottom of
   `.card-body`, rendered by `cardHtml(row)` with
   `data-write-from="<video_id>"`. Outlined at rest (so a grid of cards
   isn't a grid of orange alarms), fills vermillion on card hover, button
   hover, or keyboard focus. Clicking it must NOT open the detail view:
   in the global click delegate, the `[data-write-from]` branch runs
   before the `[data-folder]` card-open branch and returns.
2. **Uoink detail page-head** -- `#yoinkWriteFrom`, now the row's single
   primary button (Evidence stepped down to ghost). Disabled when no row
   is loaded or the row has no video id. Reads
   `videoIdOf(state.selectedYoink)` at click time.

## The deep link: `writeFromSource(videoId)`

1. `switchTab("writing")` -- Generate tab activates (its `loadWriting()`
   also warms the picker corpus).
2. `await loadWritingSources()` -- ensures the picker's dedicated list
   (see [generate-source-picker.md](generate-source-picker.md)) is loaded.
3. Resolves the row by `videoIdOf` from the picker list, falling back to
   `state.library` (cards can exist before the picker fetch lands).
4. `selectWritingSourceById(writingRowId(row))` -- the normal picker
   selection path: chip renders, hidden id set, topic autofills when
   empty, screenshots load, Generate enables.
5. Scrolls the content pane to the top so the picked chip is in view.

Why the two-step id resolution: cards carry `video_id`, but picker rows
key on `writingRowId` (which prefers `row.id` when the backend row has
one). Resolving the row first and re-keying through `writingRowId` keeps
the deep link correct regardless of which key the backend included.

**Failure state** (source in neither list, e.g. deleted between render and
click): drops to browse mode via `clearWritingSource({focus: true})` and
toasts "Couldn't preselect that source. It's in the list." No silent wrong
pick is possible; Generate stays disabled until a real selection exists.

## Routes consumed

None directly. Everything goes through the picker's existing machinery
(`/memory/search?limit=200` for the corpus, `/yoinks/<id>/screenshots` on
selection).

## Tests / proof

- `tests/test_u04_write_from_this.py` -- static contract (CTA on every
  card, detail primary, deep-link internals, click-delegation order).
- `handoff/qa-harness-playwright/u04-write-from-this-check.js` -- live
  drive at 1280/1100/900: CTA on 12/12 cards, card click lands on Generate
  with the right chip + Generate enabled, detail CTA same, card-open still
  works when clicking the card body.
