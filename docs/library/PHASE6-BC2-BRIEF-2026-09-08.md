# Phase 6 implementation brief, second increment (run BC-2, 2026-09-08)

Fable's dispatch under `ORCHESTRATION-V1-2026-09-04.md`. Contract `phase6-v1` as amended in
BD-0 (migration 0030 with `IF NOT EXISTS`). Astra's early review of BC-1
([PHASE6-BD0-2026-09-08.md](PHASE6-BD0-2026-09-08.md)) is the specification for this
increment: its seven rulings and its "Further BC-2 requirements from inspection" section
name each gap with file and function. Base: the commit this brief lands in. No worker runs
a model, a transcription engine, the resident helper, or touches port 5179 or the live
index. Do not commit; Fable integrates and runs every test.

## Scope

1. **Publication ownership fence** (ruling 1): a generation or expected-base fence carried by
   an internal service wrapper, checked under the shared capture/item lock before file
   replacement and held through settlement; recheck deletion, corpus bytes and sidecar
   dependencies there; an old publisher refuses `revision_unavailable` before touching files;
   a retry of the same authorized publication recovers from each file/DB boundary; the raw
   helper offers no unfenced bypass.
2. **Complete publication operation with Phase 2 invalidation** (ruling 2): production
   publication and reconstruction commit one coherent source/citation/media/clip snapshot
   and invoke the existing Phase 2 invalidation service; empty/shorter replacements covered;
   projection/invalidation failure propagates with a recoverable state. `podcasts.episode_to_corpus`
   and the YouTube path route through it.
3. **Artifact retention** (ruling 3): prune obsolete owned `.media-inputs` after successful
   settlement under the ownership rules; retain current inputs, retained-run artifacts,
   original capture files and other owners' files; interrupted cleanup retryable; reads never
   clean; hard purge covered.
4. **Seek kinds** (ruling 4): production podcast publication records `seek_kind="none"`, null
   seek URL and null exported player command; tests verify them.
5. **Export completion** (ruling 5 and inspection): `export_cited_range` validates original
   artifacts by bytes (missing inputs `library_unavailable`, corrupt bytes or bindings
   `invalid_source_data`, through the shared validator); one coherent bounded read with a
   final source/media recheck, lock waits inside the shared 2 s deadline via Phase 4's
   admission guard (no second pool); registry and stdio adapters (`export_cited_range` in
   `TOOL_REGISTRY` and `uoink_mcp.py`; inventories become 32 stdio and 88 registry in
   `tests/test_c01_mcp_stdio.py`, `tests/test_phase4_stdio.py`, `tests/test_stdio_clip_tools.py`,
   `.mcpb/manifest.json`, `docs/v2-mcp.md`, `docs/v2-api.md`, README/CHANGELOG counts, the
   count tests); exact input rejection before storage access; untrusted-data rendering;
   actual wrapped response sizes verified.
6. **Production capture paths** (inspection): `chapters_from_metadata` called from the
   helper's capture path for already-held YouTube metadata; `server.py` calls the shared
   media publisher, snapshot builder and renderer; podcast publication uses the shared
   renderer; `clips.build_clips_for_video` does not swallow `MediaError` into replaced clips.
7. **Virtual view** (ruling 6): `unsupported`/`not_materialized` only for text-only items;
   an empty or failed timed capture is not a prose item; both cases tested.
8. **Sidecar link fields** (ruling 7): new writers persist actual stored link values including
   nulls and `youtube_deep_link`; legacy recovery only on exact cue-revision and hash match.

## Owners

| Owner | Files |
|---|---|
| claude (Fable 5.1 worker) or gemini | `library_media.py`, `index.py`, `podcasts.py`, `server.py` capture path, `clips.py`, `yt_extract.py`, the `export_cited_range` adapters and inventories, `tests/test_phase6_bc2.py` (new tests for each item above; Astra's `tests/test_phase6_evaluation.py` must stay 19/19 and may not be edited) |
| Astra | BD: acceptance on the integrated candidate plus the measured navigation study |
| Fable | integration; the measured-copy chapter inventory (35 items) and study workspace for BD |

Budget rule for the Claude worker: no subagents; targeted searches; write early. Report
observed counts and exact commands; note at the top of `library_media.py` anything not
implemented exactly.
