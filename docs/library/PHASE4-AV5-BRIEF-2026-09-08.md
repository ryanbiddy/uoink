# Phase 4 repair brief, fourth round (runs AV-5r, AV-5m1, AV-5m2, 2026-09-08)

Fable's dispatch under `ORCHESTRATION-V1-2026-09-04.md`. Contract `phase4-v1`
([PHASE4-CONTRACT-2026-09-08.md](PHASE4-CONTRACT-2026-09-08.md)). Astra's AW-3 verdict
([PHASE4-ACCEPTANCE-3-2026-09-08.md](PHASE4-ACCEPTANCE-3-2026-09-08.md)) is the
specification: its D01-D15 rows name the exact remaining repair with file and line, and
`tests/library_work_astra/test_phase4_aw3_acceptance.py` holds the 16 reproductions (one
control passes). Base: the commit this brief lands in. Workers never commit; Fable integrates
and runs every suite. No worker runs a model, the resident helper, port 5179 or the live
index; no `ANTHROPIC_API_KEY`. Astra's tests may not be edited; the AW and AW-2 sets (60)
and the Phase 4 unit suites (`tests/test_library_resources.py`, `test_library_prompts.py`,
`test_library_briefs.py`, `test_library_mirror.py`, `test_library_mirror_wiring.py`,
`test_phase4_stdio.py`, `test_c01_mcp_stdio.py`) must stay green.

| Run | Engine | Items | Reproductions | Files and the AW-3 repair |
|---|---|---|---|---|
| AV-5r | grok | D01, D02, D03 | `test_d01_cold_database_open_obeys_deadline`, `test_d02_prompt_rechecks_cards_after_remaining_metadata_reads`, `test_d03_punctuation_and_symbol_led_absolute_paths_are_redacted` (3 cases) | `library_resources.py`, `library_prompts.py`: carry the remaining deadline into the cold `Index.open` and its initial SQLite work; prompt fan-out rechecks previously built cards after later metadata reads change their source; `_POSIX_FIRST` admits explicit absolute paths whose first segment starts with punctuation, symbols or non-ASCII. Write the code early; a session without the files is a failed run. |
| AV-5m1 | gemini | D07, D08, D09, D10 | `test_d07_publication_excludes_an_independent_sqlite_writer`, `test_d08_unreadable_day_retains_local_brief_cleanup_retry`, `test_d09_resync_reexports_explicitly_readmitted_scope_item`, `test_d10_brief_source_revision_rechecked_at_replace` | `library_mirror.py`: publication exclusion must hold against an independent SQLite writer, not only users of the same Index object; a date-directory enumeration error keeps the cleanup retry instead of reporting completion; an explicitly readmitted scope item leaves the source-purge ledger and is re-exported on resync; the final check before replace compares bound source revisions, not only liveness and scope. |
| AV-5m2 | grok, after AV-5m1 lands | D12, D13, D14, D15 | `test_d12_retry_keeps_ownership_of_interrupted_temp`, `test_d12_recorded_temp_path_does_not_authorize_deleting_user_replacement`, `test_d13_timeout_never_publishes_or_rolls_back_over_user_bytes` (2 cases), `test_d13_timed_out_writer_cannot_erase_a_later_successful_sync`, `test_d14_index_intent_matches_exact_published_bytes`, `test_d15_failed_destination_binding_persistence_does_not_allow_readoption` | `library_mirror.py`: a new intent does not overwrite an old `temp_rel` before that temp is cleaned; a recorded temp path authorises deleting only the bytes it recorded, never a user replacement; a timed-out writer neither publishes nor rolls back over user bytes and cannot erase a later acknowledged sync; the `Library.md` intent hash is the exact published bytes; a failed durable destination-binding write refuses initialization and never acknowledges export. |

Commands (`PYTHONDONTWRITEBYTECODE=1`, `PYTHONPATH=<worktree>`, no `ANTHROPIC_API_KEY`):

```
python -B -m pytest -q -p no:cacheprovider tests/library_work_astra/test_phase4_aw3_acceptance.py -k "<your items>"
python -B -m pytest -q -p no:cacheprovider tests/library_work_astra/test_phase4_aw_acceptance.py tests/library_work_astra/test_phase4_aw2_acceptance.py tests/library_work_astra/test_phase4_aw3_acceptance.py
python -B -m pytest -q -p no:cacheprovider tests/test_library_resources.py tests/test_library_prompts.py tests/test_library_briefs.py tests/test_library_mirror.py tests/test_library_mirror_wiring.py tests/test_phase4_stdio.py tests/test_c01_mcp_stdio.py
```

After AV-5m2: AW-4 (Astra), then Fable's real-client rerun per AW-3's five numbered
requirements (P4-14/P4-15).
