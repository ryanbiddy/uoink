# Surface map: Corpus Digest (R-01) + resume open-loop (R-02)

The retention surface: turn idle high-value uoinks into drafts, and give a
reopened app an obvious next step. Built on the existing `/resurface` route
and the U-04 [write-from-this](write-from-this.md) deep link. Lives in
`assets/dashboard/index.html`; backend in `server.py` + `index.py`.

## R-02: "resume where you left off"

A compact card at the top of the Library tab (the launch tab), `#resumeCard`.
Rendered on boot by `loadResume()` -> `renderResumeCard(payload)`.

### The route: `GET /resume`

New in R-02 (`_handle_resume` / `_resume_payload`). Token-gated, local only,
no AI. Reads two signals:

- `last_source` -- the most recently saved uoink, via the existing
  `index.list_recent(limit=1)`, projected to `{video_id, title, channel,
  topic, yoinked_at}`.
- `last_draft` -- the most recently touched draft, via the new
  `index.latest_writing_draft()` (ordered `updated_at DESC, id DESC`). Its
  `body` is collapsed to a `body_preview` capped at 160 chars, and its
  linked `yoink_id` (when present) is resolved to a source brief through
  `index.get_yoink`.
- `suggested.action` -- `continue_draft` when a draft exists, else
  `write_from_source` when a save exists, else `none`.

On an index error the route returns 503 and the card stays hidden. Copy
lives in the dashboard (Voice DNA); the route ships data + an action key.

### The card

- Draft present: kicker "Resume where you left off", the draft title (or
  `Your <kind> in progress`), a body preview, a source/age line, and a
  primary **Continue draft** button (`data-resume-draft`).
- No draft, a save present: kicker "Start from your last save", the source
  title, a channel/age line, and a primary **Write from this** button
  (`data-write-from`, the U-04 path).
- Nothing qualifies (empty corpus / failure): the card keeps its `.hidden`
  class. No fake state.

### Continue-draft deep link: `resumeContinueDraft(id, kind, videoId)`

`switchTab("writing")` -> `loadWritingSources()` -> preselect the linked
source through `selectWritingSourceById` (same machinery as write-from) ->
set the output-kind radio -> `GET /writing/draft/<id>` -> `setWritingOutput`
with the saved body and re-adopt the draft id (so a later Save updates in
place). Scrolls the content pane to top.

## R-01: Corpus Digest (For You)

Each resurfaced item now carries a prominent **Write from this** action. In
`insightCard(row, kicker, {writeFrom})` a `[data-write-from]` primary button
renders when the row has a video id. `renderForYou` passes `writeFrom: true`
for both `worth_revisiting` and the performing `anchors`, so every
resurfaced/anchor card is one click from a draft.

The button reuses the global `[data-write-from]` click delegate, which runs
before the `[data-folder]` card-open branch, so clicking Write from this
never opens the detail view. Topic connections and coverage gaps already
render from the `/resurface` payload (`connectionHtml`, `gapHtml`).

## Routes consumed

- `GET /resume` (new, R-02)
- `GET /resurface` (existing, the digest data)
- `GET /writing/draft/<id>` (existing, continue-draft)
- everything the write-from deep link already used (picker corpus +
  `/yoinks/<id>/screenshots`)

## Tests / proof

- `tests/test_resume_route.py` -- `GET /resume` contract: token gate, empty
  corpus shape, source-led vs draft-led payloads, source resolution, body
  preview truncation, unlinked-draft shape.
- `tests/test_resurface_route.py` -- the underlying `/resurface` payload.
- `tests/test_u04_write_from_this.py` -- the write-from deep link internals.
- Live drive against the running helper at 1280x800:
  `handoff/qa-harness-playwright/r01-corpus-digest-check.js`.
