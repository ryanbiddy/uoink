# Surface map: quick notes / musings capture

Captures a **note the user wrote to themselves** into the local corpus as a
first-class uoink with `source_type='note'` on `platform='note'`, authored by
**You**. First item-model extension toward the context layer
(`handoff/CONTEXT-LAYER-VISION-2026-07-08.md`, build sequence item 1).

A note is the same universal item as everything else: source + author +
extracted content + topic + timestamp. No new corpus shape, no new query path.
It reads back through `/recent`, `/memory/search`, `/library/facets`, and every
MCP tool with no special-casing.

## Taxonomy choice

Reuses the v3.5.0 taxonomy (platform / source-type / author / topic):

- **`source_type = "note"`** and **`platform = "note"`**, kept 1:1 the way every
  other source maps (`x_thread` -> `x`, `page` -> `web`, `episode` -> `podcast`).
  A note is not from a source network, but it slots into the Platform facet so
  it filters like any other uoink. `platform="personal"` was considered and
  rejected: "personal" implies an umbrella (musings, voice memos, ...) we have
  not built, so naming the platform after a future bucket would mislabel later
  items. The tag stays honest at `note`.
- **`author`** = the user. There is no user-identity setting in the corpus yet,
  so the default is the plain, honest **"You"**. `POST /notes` accepts an
  optional `author` override for when an identity setting lands.
- **`topic`** = classified over the note text via the existing keyword
  classifier (`server._classify_topic`), the same one X / Reddit / web captures
  use. An unclassified note carries no topic and reads as **Uncategorized** in
  the UI, never a hard failure.

Both new tags are registered in `page_extractor` (`PLATFORM_NOTE`,
`_SOURCE_TYPE_PLATFORM["note"]`, `author_for` note branch) so the whole taxonomy
agrees on them, and labeled in `server._FACET_LABELS` (platform + source_type ->
"Note") so the Library facet dropdowns read cleanly.

## Module: `notes.py`

Owns the pure note logic (transport lives in `server.py`); standalone and
unit-testable, mirroring `x_article_extractor.py` / `reddit_extractor.py`.

- **`build_note(text, title=None, author=None)`** -> `{ok, video_id, slug,
  title, author, markdown, yoinked_at}` or `{ok: False, code: "empty", error}`.
  Derives the title from the first non-blank line (leading `#` / `>` / list
  markers stripped) when none is given; defaults author to `"You"`; mints a
  unique `note_<uuid>` id + a readable `<title-slug>-<uuid8>` slug. Empty text
  fails honestly, nothing is saved.
- **`persist_note(idx, note, *, data_root, topic_classifier=None)`** -> the
  `video_id`. Classifies a topic over the text, writes the corpus + sidecar,
  and upserts the row with the same field set every capture uses
  (`idx.upsert_yoink` + FTS content), so readers treat it identically.

## Route: `POST /notes` (token-gated)

`{text, title?, author?}` -> `_handle_create_note` (`server.py`). Validates via
`notes.build_note`, persists via `notes.persist_note(data_root=DESKTOP_ROOT,
topic_classifier=_classify_topic)`. Token gate is `do_POST`'s unconditional
`_require_token`.

| Case | Status | Body |
|---|---|---|
| Saved | 200 | `{ok:true, video_id, slug, title, author, source_type, platform}` |
| Empty text | 200 | `{ok:false, code:"empty", error}` (honest, nothing saved) |
| Persist failed | 500 | `{ok:false, error}` |
| No/bad token | 403 | |

## Storage root (v3.3.2 discipline)

The corpus lands under the configured output root
(`DESKTOP_ROOT` / `UOINK_OUTPUT_DIR`) at
`<output_root>/Notes/<title-slug>-<id>/<slug>.md` plus a `<slug>.json` sidecar.
It does **not** write to `%LOCALAPPDATA%` (`DATA_ROOT`). The corpus file is
named after the folder slug (`<slug>.md`), so the disk-walk fallback
(`server._resolve_corpus_path` / MCP `_iter_yoink_folders`) resolves it too, not
just the index. Pinned by `test_persist_note_writes_under_output_root`.

## Dashboard UI

A **"Jot a note"** compose box (`#noteCapture`) sits with the capture surfaces
on the Sources tab, right under the universal "Uoink anything" URL box: an
optional title field, a markdown textarea, and a **Save note** button (enabled
once there is text; Ctrl/Cmd+Enter also saves). On save it `POST`s `/notes`,
clears, toasts "Saved your note. It's in your Library.", then reloads the
Library + facets so the note is immediately visible and filterable. The Library
card renders source-type **"note"** (`sourceTypeLabel`), platform chip
**"Note"** (`platformChipLabel`), and author **"You"**, like any uoink.

## MCP

No new tools. The note is an ordinary indexed row + corpus file, so
`search_uoinks` (FTS) finds it and `get_uoink_corpus` reads it by slug with no
special-casing. Verified by `test_route_persists_and_surfaces_everywhere`.

## Tests / proof

`tests/test_notes_capture.py` (red on main: `notes` module absent, `POST /notes`
404s, no `note` facet label):

- `build_note`: title from first line, default author You, empty text fails.
- `persist_note`: corpus **under the output root** (not `%LOCALAPPDATA%`) as
  `source_type='note'`, `author='You'`, topic classified-or-empty, file named
  `<slug>.md` under `Notes/`.
- Route: token gate, honest empty-error relay.
- The note surfaces in `/recent`, `/memory/search` (by text + `source_type=note`
  filter), `/library/facets`, and the MCP tools (`search_uoinks` +
  `get_uoink_corpus`).

Playwright drove the real dashboard against an isolated temp corpus on a spare
port: composed a note, saw it in the Library, and filtered to source-type =
Note, card showing "note" + "You". No console errors.

## Follow-up (out of scope here)

An extension popup affordance to jot a quick note without a source tab was left
for later: the popup's capture model is source-tab-driven, and a free-text note
composer there is a meaningful UI addition better scoped on its own. Notes are
reachable today from the dashboard compose box and `POST /notes` directly.
Short-video / images / Spotify are separate later sequence items.
