# Surface map: Topics overview (Library)

The clickable topic-chip row above the Library grid, added in U-05
(UX-13). The first surface that answers "what topics have I uoinked, and
how much of it is untagged?" in one glance.

## Where it lives

`#topicOverview` in `assets/dashboard/index.html`, between the Library
summary line and `#libraryGrid`. Hidden (`.hidden`) whenever there are no
topic facets: empty corpus, facets fetch failed, or facets fallback mode.

## Data flow

- `loadLibraryFacets()` (called once at init and after settings changes)
  GETs **`/library/facets`** (token-gated) and stores `data.facets` on
  `state.facets`. The topic entries are corpus-wide:
  `{value, label, count}` per topic, counts over ALL saved uoinks, not the
  loaded page.
- `renderTopicOverview()` renders one chip per topic, sorted biggest
  count first. Re-rendered by `loadLibraryFacets()` and on every
  `renderLibrary()` pass so the active state tracks the filter however it
  was changed (chip click or the Topic dropdown).

## Chip anatomy and states

- Label + mono count, pill outline.
- **Active** (current `state.filters.topic` equals the chip's value):
  vermillion border + tinted fill, `aria-pressed="true"`.
- **Uncategorized**: dashed border, dimmed label, and a tooltip that
  names the debt: "N saved uoinks with no topic yet. Click to see them;
  topics live in Settings." This is the UX-13 hygiene surface (8/31 at
  audit time).
- Other chips tooltip: "Show the N saved uoinks in <topic>."

## Interactions

| Action | Result |
|---|---|
| Click a chip | Sets `#topicFilter` + `state.filters.topic` to the value and reloads the Library (`loadLibrary({reset: true})` -> `/memory/search?...&topic=<value>`). |
| Click the active chip | Clears the topic filter and reloads the full Library. |
| Change the Topic dropdown instead | Overview re-renders with the matching chip active (single source of truth: `state.filters.topic`). |

The click branch lives in the global click delegate as
`[data-topic-overview]` (named `overviewChip`; note `topicChip` was
already taken by the Generate topic chips in the same scope).

## Routes consumed

- `GET /library/facets` -- corpus-wide topic counts (shared with the
  filter dropdowns and Generate topic chips).
- `GET /memory/search?topic=...` -- via the normal Library reload.

## Tests / proof

- `tests/test_u05_topics_overview.py` -- static contract.
- `handoff/qa-harness-playwright/u05-topics-overview-check.js` -- live
  drive at 1280/1100/900: 5/5 chips with counts, biggest first,
  Uncategorized flagged + hinted, click fires a real `topic=` request and
  the grid filters, second click restores all 31.
