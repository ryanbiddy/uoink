# Surface map: hooks explainer + the two hook taxonomies

Added in U-06 (UX-14). Hook vocabulary shows up on library card badges,
the Library Hook filter, and Generate's Hook pattern picker; this surface
is where the app finally defines it, plus the reconciliation between the
two hook taxonomies the product uses.

## The two taxonomies (read this before touching either)

| | Classification | Generation lens |
|---|---|---|
| Source of truth | `server._HOOK_TYPE_DEFINITIONS` / `HOOK_TYPES` | `writing_studio.HOOK_LENS_TYPES` |
| Served by | `GET /hooks/guide` (public) | (values validated by `normalize_hook_lens`, 400 on anything else) |
| Question it answers | "How did this saved video open?" (evidence, stamped by the detector) | "How should the draft I'm about to generate open?" (directive) |
| Members (9 each) | curiosity_gap, question, contrarian, story_open, promise_list, demo, authority, stakes, other | informative, curiosity_gap, question_open_loop, disappointment_contrarian, stakes, success_case_study, failure_lesson, engagement_bait, frame_shift |

**Decision (2026-07-04, logged in handoff/DECISIONS-LOG.md): map, don't
unify.** The explicit map lives in the dashboard's `HOOK_LENS_CATALOG`
(each lens's `classification` field):

- curiosity_gap -> curiosity_gap
- question -> question_open_loop
- contrarian -> disappointment_contrarian
- stakes -> stakes
- story_open, promise_list, demo, authority, other -> no lens counterpart
  (explainer-only)

The map exists to decorate lens options with corpus counts. It fixed a
real defect: the picker used to be seeded with raw classification facet
values (authority, demo), and submitting one as `hook_type_lens` got a
400 from `normalize_hook_lens`.

## The explainer modal

`#hookExplainer` (modal-backdrop pattern, focus-trapped, Esc/x/backdrop
close). Content:

- Intro: "A hook is how a video earns its first 10 seconds." plus where
  the vocabulary appears.
- The 9 classification definitions, fetched once per session from
  `GET /hooks/guide` (plain fetch; the route is public) and cached on
  `state.hookGuide`. Fetch failure renders honest retry copy, never a
  blank panel.
- A closing note that Generate's picker is a directive list, not this
  taxonomy.

`openHookExplainer(hookId)` highlights and scrolls to the given hook.

## Entry points (data-hook-explain)

- **Library card hook badges** -- now `<button class="hook-chip"
  data-hook-explain="<hook_type>">`; opens the explainer with that hook
  highlighted. The delegation branch runs before the card-open branch so
  a badge click never opens the detail view.
- **Library summary line** -- "What's a hook?" link next to the filter
  status.
- **Generate > Advanced > Hook pattern label** -- "what's a hook?" link.

## The Generate lens picker after U-06

`renderGenerateHookChoices()` renders all 9 `HOOK_LENS_CATALOG` entries
(no longer whatever the corpus happened to contain):

- Value: always a valid `HOOK_LENS_TYPES` key.
- Tooltip: the lens's directive (kept byte-identical to
  `writing_studio.HOOK_LENS_TYPES`; `test_u06_hooks_explainer.py` fails
  if they drift).
- Count: corpus count from `/library/facets` `hook_type` facets,
  translated through the classification map; tooltip "N saved uoinks open
  this way". Label + count render as one non-wrapping unit (UX-06).
- The static markup fallback lists the same 9 radios.

The Script tab's `scriptHookLensPicker` already used the correct 9 lens
values statically and is untouched.

## Routes consumed

- `GET /hooks/guide` -- classification definitions (public, U-01).
- `GET /library/facets` -- corpus hook counts (shared).

## Tests / proof

- `tests/test_u06_hooks_explainer.py` -- explainer wiring, entry points,
  catalog/backend mirror, decision-log presence.
- `handoff/qa-harness-playwright/u06-hooks-explainer-check.js` -- live at
  1280/1100/900: badge click opens explainer (not detail) with the right
  hook highlighted, 9 definitions, Esc closes, Library + Generate links
  work, lens picker holds exactly the 9 valid lens values with mapped
  counts (authority/demo cannot leak in), every option carries its
  directive tooltip.
