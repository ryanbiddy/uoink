# Phase 6 BC-3f session (grok)

Worker: grok
Run: BC-3f (enforce capture dependencies inside publication)
Findings: frozen BD-4 (`test_bd4_capture_dependency_changed_at_publish_entry_is_preserved`)
Base: `ae40b57` on this dedicated worktree (`Phase 6 (run BD-4, codex): retain publisher-entry race and brief BC-3f`).
BC-3e is integrated as intermediate work. Do not commit. Astra independently
verifies both roots and completes the broader BD-2 review afterward.

## Status

Complete as an implementation candidate. The frozen BD-4 publisher-entry
caption loss is repaired inside the Index/raw publication operation, not
by another standalone caller check. BC-3e consumed-input binding and
existing tests are preserved. Frozen acceptance files were not edited,
including `tests/library_work_astra/test_phase6_bd4_acceptance.py`. Named
Phase 6 and Phase 3 companion suites were run in full. Unchanged
omitted-ticket helper refusals remain failed for Ryan's existing fixture
ruling. This run does not claim Phase 6 accepted.

## Repair

BD-4: after every standalone owner check, a pending caption correction B
arrives at `Index.publish_media_snapshot` entry. The publisher overwrote
it with held caption A. That is content loss, not a formatting
discrepancy. A check in `_publish_capture_media` before invoking the
publisher cannot close it: the race is inside the publication boundary.

Inspected `server._publish_capture_media` → `Index.publish_media_snapshot`
→ `library_media.publish_transcript` together, including ledger/corpus
writes, the final sidecar `os.replace`, and `MediaError` rollback.
`podcasts.episode_to_corpus` shared the same gap for its transcript file.

Repair: carry the original immutable dependency binding, ticket and exact
owned paths through the publication operation.

- `PublicationTicket` now holds `capture_binding` (consumed sidecar
  inputs), `sidecar_path` (exact carrier path) and `input_bindings`
  (extra owned files, currently the podcast transcript bytes).
- `begin_publication` / `Index.begin_media_publication` freeze disk
  capture inputs and the sidecar path at mint. The capture owner also
  passes the consumed binding it already holds so a later disk change is
  not adopted. The podcast owner passes the exact transcript path/bytes.
- `publish_transcript` (raw and Index) snapshots the **pre-merge**
  published binding from the artifact sidecar. After the ownership fence
  and `BEGIN IMMEDIATE`, and before any publication write, it rechecks
  disk against that frozen mint binding and the original published
  binding. Immediately before the final sidecar replacement it rechecks
  again against the exact bytes about to be replaced.
- Disk may still match the mint binding (intentional replacement of
  unchanged files, including empty replacement) or the original published
  binding (crash-retry after that carrier was already written). Any other
  consumed-input state — changed caption, changed `transcript_source`,
  sidecar removal, foreign sidecar, changed podcast transcript bytes —
  refuses `revision_unavailable` (`publication_input_changed`) without
  replacing the current sidecar or committing a newer snapshot. The
  publisher does not mint a replacement ticket and does not silently
  adopt the changed dependency into the artifact binding.
- Non-owned sidecar keys are still merged (BD-05) after the consumed-
  input check; a late `unrelated_owner` edit is not a capture input.
- BC-3e caller checks after mint and at the `_publish_capture_media`
  boundary before `publish_media_snapshot` are unchanged. They do not
  replace the publisher-side lock.

Preserve: first publication, identical retry, explicit empty replacement,
sealed study overrides with bound consumed inputs, non-owned sidecar
edits and removals, crash recovery, and the Phase 3 S16 empty-citation
seam.

## Transaction / file boundary

| Point | What is checked | What has been written |
|---|---|---|
| After `BEGIN IMMEDIATE` and the generation/history fence, before ledger | Frozen capture binding, exact sidecar path, extra input files vs current disk | Nothing |
| Immediately before final sidecar `os.replace` | Same checks against the exact sidecar bytes about to be replaced | Ledger claim, owned artifacts/corpus (sidecar still previous) |
| `MediaError` | `conn.rollback()`; sidecar and DB snapshot stay the refused state | Sidecar not replaced. If the final check fires, ledger/artifacts/corpus may already match an interrupted publication, same as a crash between those writes and the carrier. |

The complete newer snapshot is the DB citation/clip/media/chapter rows
plus the sidecar. A refused BD-4 write leaves caption B's exact sidecar
bytes and the previously committed rows.

## Binding fields

Sidecar binding (`capture_sidecar_inputs`), frozen on the ticket and
rechecked inside publication:

| Input | Bound as |
|---|---|
| Cue text | `start`, `end`, `text` |
| Cue links | presence and value of `source_url`, `source_deep_link`, `youtube_deep_link` |
| Speaker | `speaker` only with a provenance object; provenance JSON |
| Transcript kind/provider | raw sidecar `transcript_source` |
| Source/playback identity | `video_id`, `source_type`, `source_url`, `url` |
| Chapters | full `source_chapters` list (extra keys change the archived artifact) |
| Artifact metadata | `yoinked_at`, `duration_seconds` |

Podcast extra binding: exact transcript-file path and bytes on
`ticket.input_bindings`. Non-owned sidecar keys remain BD-05 merge.

## Frozen-suite classification

Every named-suite failure below is an omitted-ticket helper call in an
unchanged acceptance file. None is relabelled passed. Ryan's ruling in
`INTEGRATOR-CONTRACT-CONFLICTS-2026-09-08.md` is required before those
helpers may acquire and carry tickets. No existing test, helper, or
setup was edited.

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

No frozen test failed a behavior assertion after a ticketed setup, other
than those two later ticketless calls. BD-02/04/05/06/07/08/09 remain
passing. BD-2 is 3/3. BD-3 is 1/1. BD-4 is 1/1.

## Independent implementation tests

`tests/test_phase6_bc3f.py` (new file). Frozen acceptance files are not
replaced or deselected.

- `test_bc3f_publisher_entry_preserves_late_caption_correction`: BD-4 twin
  through the real capture owner; caption B at `publish_media_snapshot`
  entry keeps its exact sidecar bytes.
- `test_bc3f_raw_publisher_entry_preserves_late_caption_correction`: same
  race on raw `publish_transcript`; DB rows unchanged.
- `test_bc3f_final_sidecar_replace_preserves_late_caption_correction`:
  caption B written during the ledger `os.replace`; the final carrier
  write refuses and leaves B and the prior DB snapshot.
- `test_bc3f_publisher_refuses_sidecar_removal_without_replacing_it`:
  unlink at publisher entry; the file stays gone.
- `test_bc3f_publisher_entry_preserves_changed_transcript_source`: a
  consumed non-transcript field changed at entry is not adopted and not
  overwritten.
- `test_bc3f_podcast_publisher_entry_preserves_changed_transcript_file`:
  podcast transcript bytes changed at `publish_media_snapshot` entry;
  source file B and the current published snapshot remain.

## Commands and observed counts

Interpreter: `C:\Python314\python.exe` (3.14.6). Worktree cwd. PowerShell.

Environment: `PYTHONDONTWRITEBYTECODE=1`, `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`,
`PYTHONNOUSERSITE=1`, `ANTHROPIC_API_KEY` unset, `librarian_apply_enabled`
untouched (not set). `PYTHONPATH` is the worktree plus the resolved installed
user-site (`C:\Users\hello\AppData\Roaming\Python\Python314\site-packages`
and its `win32` / `win32\lib` / `pythonwin` subdirs). Disposable roots
under worktree `_scratch/bc3f-roots\` (`TEMP`/`TMP`, `LOCALAPPDATA`,
`APPDATA`, `USERPROFILE`/`HOME`). Phase 3 also
`PHASE3_REQUIRE_IMPLEMENTATION=1`. No model, helper, port 5179, live
index, or paid API. Apply remains false. Logs and JUnit XML:
`_scratch/bc3f-w`.

```
python -B -m pytest -q -p no:cacheprovider tests/test_phase6_bc3f.py tests/library_work_astra/test_phase6_bd4_acceptance.py tests/test_phase6_bc3e.py tests/library_work_astra/test_phase6_bd3_acceptance.py
```

**16 passed**, 4 warnings, 111.21 s
(BD-4 caption-at-entry; six BC-3f publisher-entry/final-carrier cases;
BC-3e five consumed-field races, sealed override, publication-boundary
reread, non-owned sidecar key; BD-3 provenance).

```
python -B -m pytest -q -p no:cacheprovider tests/library_work_astra/test_phase6_bd2_acceptance.py
```

**3 passed**, 8 warnings, 12.66 s
(capture owner; previously-published podcast control; never-published
podcast A after newer B).

```
python -B -m pytest -q -p no:cacheprovider tests/test_phase6_bc3a3.py
```

**5 passed**, 2.01 s
(empty omitted-ticket raw and Index; ticketed reconstruction fence;
removed/late-edited sidecar keys; final-write revalidation).

```
python -B -m pytest -q -p no:cacheprovider tests/library_work_astra/test_phase6_bd_acceptance.py
```

**11 passed, 3 failed**, 4 warnings, 18.53 s.
Failed: `test_bd01` raw, `test_bd01` Index, `test_bd03` (all omitted-ticket
setup). Passed: BD-02×4, BD-04, BD-05, BD-06, BD-07×2, BD-08, BD-09.

```
python -B -m pytest -q -p no:cacheprovider tests/test_phase6_evaluation.py tests/test_phase6_bc2.py tests/test_podcast_corpus_bridge.py tests/test_clips.py tests/test_library_resources.py
```

**103 passed, 8 failed**, 46 warnings, 43.16 s
(evaluation 17 passed / 2 failed, bc2 8 passed / 6 failed, podcast bridge
13, clips 15, library_resources 50).

```
PHASE3_REQUIRE_IMPLEMENTATION=1 python -B -m pytest -q -p no:cacheprovider tests/library_work_astra/test_phase3_publication.py tests/library_work_astra/test_phase3_integration.py tests/library_work_astra/test_phase3_recovery.py
```

**36 passed**, 1 warning, 8.17 s
(publication 15, integration 6, recovery 15, including
`test_s16_real_podcast_upsert_crash_does_not_enqueue`).

Named-suite union for this run: **174 passed, 11 failed**. The eleven
failures are the same omitted-ticket fixtures as BC-3e. The seven new
passing cases are BD-4 plus the six BC-3f implementation tests.

Warnings are `datetime.utcnow()` deprecation from `podcasts.py` /
`memory_layer.py`. Retained. `git diff --check` on the production files
was clean.

## Limitations

- Frozen evaluation/BC-2/BD helpers that omit a ticket still refuse at
  the boundary. That is the intended production contract. Those files
  stay unchanged until Ryan authorizes setup to acquire and carry the
  ticket while preserving every behavioral assertion.
- A ticketless call on a corrupt ledger or a contradictory sidecar
  reports `publication_ticket_required` first. Ticketed
  `begin_publication` still surfaces `publication_ledger_corrupt`.
- Capture ownership binds the sidecar fields listed above. Other sidecar
  keys remain BD-05 merge/revalidation. Podcast ownership still compares
  the exact transcript file bytes consumed at mint, now also inside
  publication.
- `library_unavailable` is still the only capture-seam code re-raised;
  `revision_unavailable` still returns True after a logged refusal. The
  newer snapshot / pending disk correction is preserved in that
  compatibility return.
- First-publication podcast still hits `insert_citations` with `[]`
  before the fence (Phase 3 S16 seam). Replacement does not.
- The publisher-side disk reread is not a file lock; SQLite
  `BEGIN IMMEDIATE` still does not protect pre-read files by itself. The
  two checks close the BD-4 window at publisher entry and at the final
  carrier write in this thread.
- A final-carrier refusal after the ledger claim can leave owned
  artifacts/corpus ahead of the unreplaced sidecar (the same interrupted
  state as a crash between those writes). Retry with the original ticket
  still refuses if consumed inputs remain changed, so caption B is not
  overwritten.
- Astra's tests were not edited. No commit. Phase 6 is not claimed
  accepted. Astra verifies both roots and finishes BD-2.

## Files

`library_media.py`, `index.py`, `server.py`, `podcasts.py`,
`tests/test_phase6_bc3f.py`,
`docs/library/PHASE6-BC3F-GROK-2026-09-08.md`.
