# Surface map: path integrity + stale-path heal (C-05)

When the output folder moves (the Yoink->Uoink rename, a OneDrive shuffle,
a whole-corpus relocation), every `yoinks` row keeps pointing at the dead
root. Before C-05 each content action then failed one by one while
`/health` reported green; on the machine that motivated the fix, 31 of 31
corpus paths were dead. This surface makes the breakage visible and heals
it.

## The check: `_path_integrity_status()`

Scans every non-deleted row's `corpus_path` for existence
(`Index.list_content_paths()`), returns `{ok, checked, missing[, hint]}`.
Cached 60s (`_PATH_INTEGRITY_TTL`) because the extension polls `/health`
every few seconds; `force=True` rescans.

Surfaced in three places:

- **`GET /health`** -- `path_integrity` key in the payload. `ok: true` at
  the top level still means "the process answers"; a healthy install also
  needs `path_integrity.ok`. Consumers that only want liveness keep
  working; consumers that care about truth now have it.
- **`GET /diagnose`** -- a `path_integrity` check row (`ok`/`error`) plus
  a plain-language warning with the recovery step, so the popup can show
  specific copy instead of "helper offline".
- **`--doctor`** -- `path_integrity` key, always fresh (`force=True`).

## The heal: `heal_stale_corpus_paths(output_root=None)`

For each row whose `corpus_path` is missing, `_relink_candidate` grafts
progressively shorter tails of the old path onto the search root (longest
first, capped at 6 components), so `<old_root>\Topic\slug\slug.md` finds
`<new_root>\Topic\slug\slug.md` before any looser match. Sidecars relink
the same way, falling back to the sibling file beside the new corpus
location. Rules:

- A row only updates when its file is actually found. Nothing is guessed.
- Rows with no candidate stay in `unresolved` and the report says so
  (`ok: false` while any remain).
- The integrity cache invalidates so the next status call rescans.

## Entry points

| Trigger | Root searched | When |
|---|---|---|
| Boot pass (`_heal_stale_corpus_paths_at_boot`, runs in `main()` after the index opens) | current output root (`DESKTOP_ROOT`) | every launch; no-op when integrity is clean; never fatal |
| `python server.py --heal-paths` | current output root | manual triage |
| `python server.py --heal-paths <folder>` | the given folder | corpus moved somewhere the configured root can't see |

The explicit-root form exists because reality demanded it: the motivating
machine's configured root (`Desktop\Uoink`) is an empty shell and the
corpus actually lives in a repo checkout on another drive. The boot pass
can't know that; a human running `--heal-paths E:\...\Yoink` can. Verified
against a copy of that machine's real index: 31/31 missing -> 31 relinked,
0 unresolved, integrity ok after.

## Index API added

- `Index.list_content_paths()` -- `(video_id, corpus_path, sidecar_path)`
  for every non-deleted row.
- `Index.update_content_paths(video_id, corpus_path=, sidecar_path=)` --
  re-point one row, committed immediately.

## Limits, stated

- The heal matches by path-tail structure, so a move that also RENAMED
  topic or slug folders won't relink (the tail no longer exists anywhere).
  Those rows stay `unresolved` rather than being matched loosely.
- Screenshot paths inside `metadata_json` are not rewritten; screenshot
  lookups resolve relative to the corpus folder, which the heal fixes.

## Tests / proof

`tests/test_c05_stale_path_heal.py` (red on unpatched main: helpers and
the `/health` key don't exist): integrity counts 4/4 dead after a root
rename, `/health` surfaces it over a live server, heal relinks 3 and
honestly reports the deleted one, post-heal integrity counts only the
truly-gone row, the boot pass heals a moved library, doctor + diagnose +
CLI wiring pinned. Plus the real-index proof above (run against a copy,
never the live file).
