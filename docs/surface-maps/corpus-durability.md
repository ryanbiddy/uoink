# Surface map: corpus durability (commits, export/import, rebuild)

C-03 (CRIT-3). "Own your data" was ~70% true: the .md/.json corpus lives
on disk, but engagement history, tags, taste, drafts, workspaces, and
style anchors lived only inside index.db; four write paths never
committed; and an index rebuild came back empty. This surface closes all
three gaps.

## 1. The four commits

`sqlite3.connect()` defaults to implicit transactions: without a
`commit()`, a write sits in an open transaction until some OTHER write
path happens to commit, and a process kill silently drops it. Fixed
writers (each now commits inside its lock):

| Writer | Data at risk |
|---|---|
| `Index.log_engagement` | every engagement event (the retention signal) |
| `Index.set_facets` | classifier facet columns |
| `Index.add_tags` | agent/user tags |
| `memory_layer.set_anchor` | taste anchors |

Test proof uses a second, independent connection to the same file: it
sees only committed data, exactly like the process that reopens the DB
after a kill.

## 2. Export / import of the SQLite-only tables

`Index.EXPORT_TABLES`: `engagement_events`, `yoink_tags`, `memory_layer`,
`writing_drafts`, `workspaces`, `style_anchors`.

- **Export** (`export_corpus_data()`): one JSON payload
  (`format: "uoink-corpus-export"`, `format_version: 1`, `exported_at`,
  `app_version`, `tables`) written to
  `<output_root>/_exports/uoink-export-<stamp>.json`. The point of the
  location: with the export beside the corpus files, the folder a user
  backs up IS their whole library.
- **Import** (`import_corpus_data(path)` -> `Index.import_payload`),
  merge rules conservative on purpose:
  - `engagement_events`: surrogate id dropped; identical
    (video_id, event_type, ts_utc, source) rows skipped.
  - `memory_layer`: newer `updated_at` wins; older imports never clobber.
  - id-keyed tables (drafts, workspaces, style_anchors): skipped when the
    id exists. Local work is never overwritten by an import.
  - `yoink_tags`: INSERT OR IGNORE on the (video_id, tag) PK. NOTE: tags
    FK onto `yoinks`, so tag rows import only when their yoink row exists;
    restore order is rebuild-then-import (the rebuild does this).
  - Unknown columns dropped; newer `format_version` rejected with copy
    telling the user to update first.
  - Re-import is a no-op (verified).

## 3. Rebuild from sidecars

`rebuild_index_from_disk(root=None)`:

1. Scans `root` (default: current output root) via the existing backfill
   (`_run_backfill(root)`, now parameterized) and indexes every
   `<Topic>/<slug>/<slug>.json` sidecar folder not already present. The
   explicit root exists because "rebuild came back empty" had a second
   cause: the corpus can live somewhere the configured root can't see.
2. Restores the newest `uoink-export-*.json` under `<root>/_exports`, so
   the SQLite-only tables come back too.

Returns `{scanned_root, rows_before, rows_after, indexed, restored}`.

## Entry points

| Surface | What |
|---|---|
| `python server.py --export-corpus` | export to the output root |
| `python server.py --import-corpus <file>` | restore an export |
| `python server.py --rebuild-index [root]` | full rebuild (sidecars + newest export), synchronous |
| `POST /corpus/export` (token-gated) | same as --export-corpus, returns `{ok, path, rows}` |
| `POST /corpus/import {path}` (token-gated) | same as --import-corpus, returns `{ok, path, report}` |

No automatic/scheduled export yet: that's a product decision (frequency,
retention) that belongs with the R-phase retention work, not smuggled in
here. The primitive is what C-03 gates.

## Tests / proof

`tests/test_c03_durability.py` (red on unpatched main: visibility tests
fail because uncommitted rows are invisible to a second connection;
export/import/rebuild helpers don't exist): the four commit proofs, full
export->import round trip across six tables, idempotent re-import,
newer-local-wins, junk-payload rejection, and a rebuild from three
sidecar folders + export restore against a fresh index. Full suite 177.
