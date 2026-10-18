# Phase 6 BC-3b session (grok)

Worker: grok
Run: BC-3b (Phase 6 third increment)
Findings: BD-02 (export freshness), BD-07 (label validation)
Base: `bc76595` on `cc/living-library` (`control-room/b5040ae4-d3e-grok`)
Do not commit. Fable integrates.

## Repair

`library_media.py` only.

- **BD-02.** `_ReadTransaction.refresh()` ends the coherent-read deferred
  snapshot and begins a new one before `_recheck_snapshot`. A second WAL
  connection's committed soft delete, hard delete, title change, or media
  revision is then visible and export returns the contract refusal
  (`resource_deleted` / `resource_not_found` / `revision_unavailable`)
  instead of the old quote. Rollback-journal writers still cannot commit
  while the original snapshot is held (BC-2 concurrent-delete fixture).
- **BD-07.** `_verify_artifacts` requires the claimed speaker on the
  producer record. Source labels use the existing locator plus `speaker`.
  Run labels use the run artifact's `transcript` or `segments` list at the
  same `seq`. Digest validity alone does not attribute speech.

## Commands and observed counts

Environment: `PYTHONDONTWRITEBYTECODE=1`, `PYTHONPATH=<worktree>`,
`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`, no `ANTHROPIC_API_KEY`. No model,
helper, port 5179, or live index.

```
python -B -m pytest -q -p no:cacheprovider tests/library_work_astra/test_phase6_bd_acceptance.py -k "bd02 or bd07"
```

**6 passed**, 8 deselected, 2.46 s
(`test_bd02` × 4: soft_delete, hard_delete, title, media;
`test_bd07` × 2: source, run).

```
python -B -m pytest -q -p no:cacheprovider tests/test_phase6_evaluation.py tests/test_phase6_bc2.py tests/test_podcast_corpus_bridge.py tests/test_clips.py tests/test_library_resources.py
```

**111 passed**, 46 warnings, 89.09 s
(evaluation 19, bc2 14, podcast bridge 13, clips 15, library_resources 50).

```
PHASE3_REQUIRE_IMPLEMENTATION=1 python -B -m pytest -q -p no:cacheprovider tests/library_work_astra/test_phase3_publication.py tests/library_work_astra/test_phase3_integration.py tests/library_work_astra/test_phase3_recovery.py
```

**36 passed**, 1 warning, 13.47 s.

Astra's tests were not edited. No commit.
