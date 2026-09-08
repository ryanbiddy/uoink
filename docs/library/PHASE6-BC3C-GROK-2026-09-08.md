# Phase 6 BC-3c session (grok)

Worker: grok
Run: BC-3c (Phase 6 third increment)
Findings: BD-04 (podcast precommit publication), BD-08 (capture refusal
propagation), BD-09 (explicit empty replacement through complete publication)
Base: `fc99942` on `cc/living-library` (`control-room/ff01d490-7f7-grok`)
Do not commit. Astra verifies and integrates.

## Status

Complete. Three targeted reproductions pass. Companion suites named in
`PHASE6-BC3-BRIEF-2026-09-08.md` pass. No commit.

## Repair

- **BD-04.** `podcasts.episode_to_corpus` no longer writes replacement
  citations before the fenced publisher. First publication still invokes
  `Index.insert_citations` with an empty batch after the yoink row so
  Phase 3 S16 can inject its crash at that seam and leave the yoink
  without citations. Replacement skips that write; `publish_media_snapshot`
  commits citations with the snapshot. A projector failure therefore
  preserves the prior complete citation/clip/media rows and the old
  corpus bytes.
- **BD-08.** `server._index_yoink` re-raises `library_unavailable` from
  the capture publication path instead of logging it and returning
  `True`. Other publication refusals (`revision_unavailable` and similar)
  still log, leave the existing snapshot, and return `True` after the
  row is present (BC-2 stale-ticket capture fixture).
- **BD-09.** `_capture_media_plan` returns an explicit empty snapshot for
  a Phase 6 writer with neither cues nor chapters. That snapshot is
  published through `publish_media_snapshot`, which replaces transcript
  citations and chapters. `Index.insert_citations([])` is an explicit
  empty replacement (delete every citation for the video and rebuild
  clips) so leftover non-transcript kinds are also removed.

## Commands and observed counts

Environment (PowerShell, worktree cwd): `PYTHONDONTWRITEBYTECODE=1`,
`PYTHONPATH=<worktree>`, `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`,
`ANTHROPIC_API_KEY` unset. Phase 3 also `PHASE3_REQUIRE_IMPLEMENTATION=1`.
Interpreter: `C:\Python314\python.exe` (3.14.6). No model, helper, port
5179, live index, or `librarian_apply_enabled` change.

```
python -B -m pytest -q -p no:cacheprovider tests/library_work_astra/test_phase6_bd_acceptance.py -k "bd04 or bd08 or bd09"
```

**3 passed**, 11 deselected, 4 warnings, 14.05 s
(`test_bd04`, `test_bd08`, `test_bd09`).

```
python -B -m pytest -q -p no:cacheprovider tests/test_phase6_evaluation.py tests/test_phase6_bc2.py tests/test_podcast_corpus_bridge.py tests/test_clips.py tests/test_library_resources.py
```

**111 passed**, 46 warnings, 52.44 s
(evaluation 19, bc2 14, podcast bridge 13, clips 15, library_resources 50).

```
PHASE3_REQUIRE_IMPLEMENTATION=1 python -B -m pytest -q -p no:cacheprovider tests/library_work_astra/test_phase3_publication.py tests/library_work_astra/test_phase3_integration.py tests/library_work_astra/test_phase3_recovery.py
```

**36 passed**, 1 warning, 10.71 s
(including `test_s16_real_podcast_upsert_crash_does_not_enqueue`).

Warnings are `datetime.utcnow()` deprecation from `podcasts.py` /
`memory_layer.py`. Retained.

## Limitations

- The other 11 BD reproductions were not run here (BD-01/03/05/06 are
  BC-3a; BD-02/07 were closed in BC-3b at this HEAD).
- First-publication podcast still hits `insert_citations` with `[]`
  before the fence (Phase 3 S16 seam). Replacement does not.
- `library_unavailable` is the only capture-seam code re-raised;
  `revision_unavailable` still returns `True` after a logged refusal.
- Astra's tests were not edited. No commit.

## Files

`podcasts.py`, `server.py`, `index.py`, `library_media.py` (comment),
`docs/library/PHASE6-BC3C-GROK-2026-09-08.md`.
