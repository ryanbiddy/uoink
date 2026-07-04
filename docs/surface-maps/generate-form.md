# Surface map: Generate form ("Write from a source")

The left-column form on the Generate tab (`assets/dashboard/index.html`,
panel `#tab-writing`). Redesigned in U-03 (UX-10, UX-11) around the mental
model *pick source > pick output > generate > refine*. The right column
(Preview, X composer, Screenshots, Style anchors manager) is a separate
surface; the source picker itself has its own map
([generate-source-picker.md](generate-source-picker.md)).

## First screen (everything a first draft needs)

Order inside `.panel-body`, all visible in one 1280x800 window with the
disclosure closed (proven live: Generate button bottom = 756px):

1. **Source uoink** -- `#writingSourceCombo` (see its own map).
2. **Output** -- `#writingModePicker`, radios `tweet | thread | blog |
   newsletter | script` (name `writingMode`, default `tweet`).
3. **Script options** -- `#generateScriptOptions`, hidden unless
   Output=Script (`syncGenerateModeUi` toggles `.hidden`). Sits directly
   under the Output picker so choosing Script reveals its controls where
   the click happened (the old layout revealed them at y=914, below the
   fold). Contains: length presets (`#generateLengthPresets`), custom
   seconds (`#generateScriptLength`), CTA target (`#generateScriptCta`) +
   recent-CTA chips, past-performance checkbox
   (`#generatePastPerformance`), "Surface audience questions" button.
4. **Topic** -- `#generateTopicInput` + corpus topic chips with counts
   (`#generateTopicChips`, fed by `/library/facets`). Autofills from the
   picked source when empty.
5. **Advanced options** -- ONE `<details id="generateAdvanced"
   class="advanced-disclosure">`, closed by default. Summary row: rotating
   arrow (`.advanced-arrow`, rotates 90deg on `[open]`), label, and a
   muted "angle - hook - style" hint that hides while open.
6. **Generate** -- `#generateWriting`, disabled until a source is picked.
7. **Agent status card** -- `#agentSetupCard`.

## Inside the Advanced disclosure

Everything optional for a first draft, in `.advanced-body`:

- **Angle** -- `#writingAngle`, free text.
- **Channel pattern** -- `#generateChannelCombo` combobox over
  `/corpus/channels`.
- **Hook pattern** -- `#generateHookLensPicker`, radios (name
  `generateHookLens`): `informative | curiosity_gap |
  disappointment_contrarian | stakes | question_open_loop |
  failure_lesson`. NOTE: this lens taxonomy is not the 9-type
  classification taxonomy served by `/hooks/guide`; reconciling the two is
  U-06.
- **Style** -- `#writingStyleMode` radios (`default | anchors | specific`)
  plus the inline anchor list `#writingAnchorList`. Deduping this against
  the right-column anchor manager is U-07 (UX-12).
- **Voice DNA toggles** -- `#writingShowWarnings` (default on),
  `#writingSkipWarnings` (default off).

Moving these into the disclosure changes no behavior: ids, names, and the
JS that reads them are untouched; only the markup nesting and CSS are new.
Hidden-while-closed means `display: none`-equivalent (Chrome uses
`content-visibility: hidden`; probe with `checkVisibility()`, not rect
heights).

## What Generate sends

`generateWriting` POSTs with `source_yoink_id` (hidden `#writingSource`),
`kind: mode` from the Output radios, topic, angle, channel, hook lens,
style mode + anchors, script extras when Output=Script, and the warning
toggles. Field collection is unchanged by U-03; consult
`generateWriting()` in the dashboard JS for the exact payload.

## States

- **No source picked**: Generate disabled; attribution line reads "Pick a
  source to build the credit line."
- **Output=Script**: script options visible under Output; other outputs
  hide them.
- **Disclosure closed** (default): advanced fields unrendered but their
  values still submit (details content stays in the DOM).
- **Disclosure open**: arrow rotates, hint hides, fields flow in the same
  10px grid rhythm as the rest of the form.

## Layout/craft details added in U-03

- `.advanced-disclosure` bordered drawer; native `<details>` for free
  keyboard and a11y semantics.
- `label.inline-row` keeps a checkbox beside the first line of its label
  text (box was dropping the sentence underneath it).

## Tests / proof

- `tests/test_u03_generate_redesign.py` -- static order + containment
  contract.
- `handoff/qa-harness-playwright/u03-generate-redesign-check.js` -- live
  fold proof at 1280 (source/output/topic/Generate all above 800px),
  disclosure containment/closure, script-options adjacency (gap to Output
  <= 40px), screenshots at 1280/1100/900.
- At 1100/900 the gate is screenshot evidence; measured Generate bottom is
  ~830px there (single-column stacking below 980px pushes it down; the
  shipped pywebview window is 1280x800).
