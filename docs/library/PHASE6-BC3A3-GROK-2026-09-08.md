# Phase 6 BC-3a3 session (grok)

Worker: grok
Run: BC-3a3 (remove publication exceptions and finish ownership guards)
Findings: BD-01 (build-time tickets at raw and Index, no empty/first/evaluation
exceptions), BD-03 (ledger-fenced reconstruction), BD-05 (removed and
late-edited unrelated sidecar keys at the final carrier write), BD-06
(pre-materialization corpus bytes)
Base: `79f6961` on `cc/living-library` (`control-room/855b1d16-104-grok`).
BC-3a2 (`5aca8450`) is rejected; its complete diff is
`docs/library/patches/bc3a2-grok-rejected-2026-09-08.patch`. Production
portions of that patch were three-way applied onto this HEAD, then repaired.
Do not commit. Astra verifies and integrates before BD-2.

## Status

Complete as an implementation candidate. The assigned production repairs
are in place. Frozen acceptance files were not edited. Independent
implementation tests with explicit build-time tickets pass. Named Phase 6
and Phase 3 companion suites were run in full. Several frozen helpers still
omit tickets; those refusals are recorded for Ryan as fixture-setup
incompatibility, not as passes. This run does not claim Phase 6 accepted.

## Repair

Production hunks from the retained BC-3a2 patch were applied only to
`library_media.py` and `index.py` (the report and `tests/test_phase6_bc2.py`
edits were skipped). Then:

- **BD-01.** Both entry points require the original build-time ticket.
  `Index.publish_media_snapshot` and raw `publish_transcript` refuse an
  omitted ticket (`invalid_request` / `publication_ticket_required`). The
  publisher never mints. `_ticket_for_omitted` and `_empty_media_snapshot`
  are gone. There is no empty, first-publication, or evaluation-helper
  exception. An idempotent retry carries its original ticket. Owning
  callers (`podcasts.episode_to_corpus`, `server._index_yoink`) already
  acquire a ticket before building.
- **BD-03.** `rebuild_item` takes `BEGIN IMMEDIATE`, reads the publication
  ledger, and refuses a sidecar whose media revision is not the ledger
  current (and a disk sidecar that disagrees with that current) before any
  DB write. A refusal rolls back so rows, files and transaction state stay
  coherent.
- **BD-05.** `PublicationTicket` snapshots non-owned sidecar keys at mint.
  Intervening edits, keys that exist only on disk, and keys removed after
  mint are merged onto the published carrier. Unchanged snapshotted keys
  leave a publisher replacement in place (podcast title/speakers). Owned
  keys (`media_depth`, `transcript`) are not taken from disk. Dependencies
  are revalidated at the final sidecar write after ledger/artifact work, not
  only earlier. A removed unrelated key is not resurrected.
- **BD-06.** The corpus-edit guard no longer requires a current media
  block. User-edited pre-materialization bytes whose digest is not the
  recorded current corpus refuse `revision_unavailable` before any write.

## Independent implementation tests

`tests/test_phase6_bc3a3.py` (new file). Successful setup acquires tickets
explicitly. Frozen acceptance files are not replaced or deselected.

- `test_bc3a3_stale_empty_build_without_a_ticket_is_refused` (raw and Index):
  publish a newer snapshot with a ticket, then submit a stale empty build
  with no ticket. Both entry points refuse `publication_ticket_required`
  and leave the newer snapshot. The same empty replacement then succeeds
  when it carries a ticket.
- `test_bc3a3_stale_sidecar_reconstruction_refuses_after_ticketed_publication`:
  ticketed publication of a newer snapshot, then `rebuild_item` of the old
  sidecar. `revision_unavailable`; rows/files unchanged; no open transaction.
  This is the BD-03 behavior the frozen reproduction could not reach because
  its setup helper omits a ticket.
- `test_bc3a3_publication_preserves_removed_and_late_edited_sidecar_keys`:
  after mint, remove `unrelated_owner` and add `late_owner` on disk. Ticketed
  publication keeps the removal and the late edit.
- `test_bc3a3_final_sidecar_write_revalidates_intervening_dependency_edits`:
  another owner edits/removes keys while the ledger claim is being written.
  The final carrier write still preserves those disk keys.

## Frozen-suite classification

Every named-suite failure below is an omitted-ticket helper call in an
unchanged acceptance file. None is relabelled passed. Ryan's ruling in
`INTEGRATOR-CONTRACT-CONFLICTS-2026-09-08.md` is required before those
helpers may acquire and carry tickets. No existing test, helper, or setup
was edited.

### Fixture-setup incompatibility (legacy helper omits the ticket)

| Test | Stop |
|---|---|
| `test_bd01` raw | `_publish(newer)` before the stale-A assertion |
| `test_bd01` Index | `_seed_index` (`publish_media_snapshot` without a ticket) |
| `test_bd03` | `_publish(newer)` before reconstruction |
| `test_phase6_rebuild_and_publication_recovery` | `_publish(shorter)` after clip-only/reconstruct (those earlier rebuilds ran) |
| `test_phase6_stale_citation_and_delete_refusals` | `_publish(replacement)` |
| `test_bc2_publication_fence_refuses_every_stale_publisher` | ticketless `_publish(b)` |
| `test_bc2_index_publication_commits_one_snapshot_and_invalidates_phase2_work` | `_seed_index` |
| `test_bc2_clip_build_refuses_instead_of_replacing_a_materialized_snapshot` | raw clip-build assertions ran; Index `_seed_index` then refused |
| `test_bc2_retention_prunes_obsolete_owned_inputs_after_settlement` | ticketless `_publish(b)` |

### Fixture-setup incompatibility on a later ticketless call (earlier ticketed behavior ran)

| Test | What ran | Stop |
|---|---|---|
| `test_bc2_fenced_retry_recovers_from_each_boundary_and_a_corrupt_ledger_refuses` | crash-retry with the original ticket settled; `begin_publication` on a corrupt ledger refused `publication_ledger_corrupt` | ticketless `_publish` expected `invalid_source_data`, received `invalid_request` / `publication_ticket_required` |
| `test_bc2_sidecar_link_fields_are_stored_values_and_legacy_recovery_is_exact` | reconstruct/refuse paths on `rebuild_item` | ticketless `publish_transcript` of a contradictory sidecar expected `invalid_source_data`, received `invalid_request` / `publication_ticket_required` |

No frozen test failed a behavior assertion after a ticketed setup, other than
those two later ticketless calls.

BD-05 and BD-06 in the frozen BD file passed (they already mint a ticket
before the edit). BD-02/04/07/08/09 remain closed from BC-3b/BC-3c.

## Commands and observed counts

Interpreter: `C:\Python314\python.exe` (3.14.6). Worktree cwd. PowerShell.

Environment: `PYTHONDONTWRITEBYTECODE=1`, `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`,
`PYTHONNOUSERSITE=1`, `ANTHROPIC_API_KEY` unset, `librarian_apply_enabled`
untouched. `PYTHONPATH` is the worktree plus the resolved installed
user-site (`C:\Users\hello\AppData\Roaming\Python\Python314\site-packages`
and its `win32` / `win32\lib` / `pythonwin` subdirs). Disposable roots
under worktree `.bc3a3-scratch\` (`TEMP`/`TMP`, `LOCALAPPDATA`, `APPDATA`,
`USERPROFILE`/`HOME`). Phase 3 also `PHASE3_REQUIRE_IMPLEMENTATION=1`. No
model, helper, port 5179, live index, or paid API.

```
python -B -m pytest -q -p no:cacheprovider tests/test_phase6_bc3a3.py
```

**5 passed**, 1.36 s
(empty omitted-ticket raw and Index; ticketed reconstruction fence;
removed/late-edited sidecar keys; final-write revalidation).

```
python -B -m pytest -q -p no:cacheprovider tests/library_work_astra/test_phase6_bd_acceptance.py
```

**11 passed, 3 failed**, 4 warnings, 15.28 s.
Failed: `test_bd01` raw, `test_bd01` Index, `test_bd03` (all omitted-ticket
setup). Passed: BD-02×4, BD-04, BD-05, BD-06, BD-07×2, BD-08, BD-09.

```
python -B -m pytest -q -p no:cacheprovider tests/test_phase6_evaluation.py tests/test_phase6_bc2.py tests/test_podcast_corpus_bridge.py tests/test_clips.py tests/test_library_resources.py
```

**103 passed, 8 failed**, 46 warnings, 37.87 s
(evaluation 17 passed / 2 failed, bc2 8 passed / 6 failed, podcast bridge 13,
clips 15, library_resources 50).

```
PHASE3_REQUIRE_IMPLEMENTATION=1 python -B -m pytest -q -p no:cacheprovider tests/library_work_astra/test_phase3_publication.py tests/library_work_astra/test_phase3_integration.py tests/library_work_astra/test_phase3_recovery.py
```

**36 passed**, 1 warning, 7.37 s
(publication 15, integration 6, recovery 15, including
`test_s16_real_podcast_upsert_crash_does_not_enqueue`).

Warnings are `datetime.utcnow()` deprecation from `podcasts.py` /
`memory_layer.py`. Retained.

## Limitations

- Frozen evaluation/BC-2/BD helpers that omit a ticket now refuse at the
  boundary. That is the intended production contract. Those files stay
  unchanged until Ryan authorizes setup to acquire and carry the ticket
  while preserving every behavioral assertion.
- A ticketless call on a corrupt ledger or a contradictory sidecar reports
  `publication_ticket_required` first. Ticketed `begin_publication` still
  surfaces `publication_ledger_corrupt`.
- Sidecar merge prefers disk for non-owned keys that changed or were
  removed after mint. Unchanged snapshotted keys leave the publisher's
  replacement (podcast title/speakers). `media_depth` and `transcript`
  stay with this publication.
- Astra's tests were not edited. No commit. Phase 6 is not claimed
  accepted. Astra verifies before BD-2.

## Files

`library_media.py`, `index.py`, `tests/test_phase6_bc3a3.py`,
`docs/library/PHASE6-BC3A3-GROK-2026-09-08.md`.
