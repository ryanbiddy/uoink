# Phase 6 implementation brief, third increment (run BC-3, 2026-09-08)

Fable's dispatch under `ORCHESTRATION-V1-2026-09-04.md`. Contract `phase6-v1` as amended in
BD-0. Astra's BD verdict ([PHASE6-BD-2026-09-08.md](PHASE6-BD-2026-09-08.md)) is the
specification: its finding table BD-01..BD-09 names each failure, the file and line, and
the repair target; `tests/library_work_astra/test_phase6_bd_acceptance.py` holds the 14
reproductions. Base: the commit this brief lands in. Workers never commit; Fable integrates
and runs every suite. No worker runs a model, the resident helper, port 5179 or the live
index; no `ANTHROPIC_API_KEY`. Astra's tests (`test_phase6_evaluation.py` 19,
`test_phase6_bd_acceptance.py`) may not be edited; the worker's own `tests/test_phase6_bc2.py`
(14) may be extended.

| Finding | Repair target (from BD) | Files |
|---|---|---|
| BD-01 | Reject a missing build-time ownership ticket at both entry points (raw publisher and Index wrapper); carry ownership from the owning operation so a never-published stale build cannot overwrite a newer publication | `library_media.py` ~1739, `index.py` ~1872 |
| BD-02 | Export freshness: the final recheck must observe a change committed by a second WAL connection (soft delete, hard delete, title, media) and return the contract's deletion/revision refusal, not the old quote | `library_media.py` ~1252, ~2374 (`export_cited_range`) |
| BD-03 | Fence reconstruction through the publication ledger; settle disk and DB coherently so an old sidecar cannot roll back a newer annotation-only publication | `library_media.py` ~1502 (`rebuild_media_item` path) |
| BD-04 | Podcast publication must not commit citations before the fenced publication; on projector failure preserve the prior complete snapshot or a durable recovery state that cannot present the mixture as current | `podcasts.py` ~1283 |
| BD-05 | Recheck/merge preserved sidecar dependencies before replacing the full carrier, or refuse; another owner's unrelated key edit survives | `library_media.py` ~1739 |
| BD-06 | Protect the pre-materialization corpus bytes too: a user-edited legacy corpus is not overwritten on first materialization when a ticket exists | `library_media.py` (corpus-edit guard) |
| BD-07 | Validate the claimed source/run label against the original producer artifact (source labels, run assignments); digest validity alone does not establish attribution | `library_media.py` ~1125 |
| BD-08 | The capture seam propagates a publication refusal (`library_unavailable`) as a failure/recoverable result to the owner instead of logging and returning `True` | `server.py` ~2753 (`_index_yoink`) |
| BD-09 | An empty replacement (no transcript, chapters, screenshots) publishes an explicit empty snapshot through the complete operation so old transcript citations are removed | `server.py` (`_capture_media_plan`), `index.py` (`insert_citations` empty-list path) |

Grouping: BC-3a (claude or gemini): BD-01, BD-03, BD-05, BD-06 (`library_media.py`
ownership/fence); BC-3b (grok): BD-02, BD-07 (export freshness and label validation);
BC-3c (gemini): BD-04, BD-08, BD-09 (podcast precommit and server capture seam). Each run
targets its reproductions plus the whole `test_phase6_evaluation.py`, `test_phase6_bc2.py`,
`test_podcast_corpus_bridge.py`, `test_clips.py`, `test_library_resources.py` and the
Phase 3 suites (`PHASE3_REQUIRE_IMPLEMENTATION=1`) green.

Commands (`PYTHONDONTWRITEBYTECODE=1`, `PYTHONPATH=<worktree>`, no `ANTHROPIC_API_KEY`):

```
python -B -m pytest -q -p no:cacheprovider tests/library_work_astra/test_phase6_bd_acceptance.py -k "<your findings>"
python -B -m pytest -q -p no:cacheprovider tests/test_phase6_evaluation.py tests/test_phase6_bc2.py tests/test_podcast_corpus_bridge.py tests/test_clips.py tests/test_library_resources.py
PHASE3_REQUIRE_IMPLEMENTATION=1 python -B -m pytest -q -p no:cacheprovider tests/library_work_astra/test_phase3_publication.py tests/library_work_astra/test_phase3_integration.py tests/library_work_astra/test_phase3_recovery.py
```

After BC-3: BD-2 (Astra) on the integrated candidate; the supported-player observation
(BD-27) and the speaker gate (Ryan) are tracked in the BD verdict.
