# Phase 6 BC-3e session (grok)

Worker: grok
Run: BC-3e (bind all consumed capture inputs)
Findings: frozen BD-3 (`test_bd3_capture_owner_cannot_replace_newer_provenance_with_identical_cue_text`)
Base: `d9ccba5` on `cc/living-library` (`control-room/21cb8de9-dfa-grok`).
BC-3d integrated at `897f0d2`. Do not commit. Astra independently verifies
both roots and completes the broader BD-2 review afterward.

## Status

Complete as an implementation candidate. Capture ownership now binds every
input the real capture plan consumes, not only start/end/text. Frozen
acceptance files were not edited, including
`tests/library_work_astra/test_phase6_bd3_acceptance.py`. Named Phase 6
and Phase 3 companion suites were run in full. Unchanged omitted-ticket
helper refusals remain failed for Ryan's existing fixture ruling. This
run does not claim Phase 6 accepted.

## Repair

BC-3d compared transcript cores `(start, end, text)` and chapter triples
after mint. A complete newer owner that kept those cores and corrected
`transcript_source` passed the check, acquired the current base, and
overwrote the newer provenance.

Inspected the real owner (`server._index_yoink`) and publisher
(`_publish_capture_media` → `Index.publish_media_snapshot`) together.
`_capture_media_plan` consumes cue links, attributed speaker/provenance,
transcript kind/provider, source/playback identity, held chapters (the
full list archived in the producer artifact) and artifact metadata
(`video_id`, `url`/`source_url`, `yoinked_at`, `duration_seconds`).
Comparing only start/end/text cannot certify unchanged input.

Repair: freeze that consumed sidecar binding, mint, then validate the
binding under the ownership fence. Recheck it at the actual publication
boundary (after `capture_snapshot`, immediately before
`publish_media_snapshot`) by re-reading disk and rebuilding the owned
plan from those bytes. A standalone file check after mint is not a lock
on a later write. A dependency change refuses `revision_unavailable`
(`publication_input_changed`) before any publication write and leaves
the current complete snapshot.

- **BD-3.** `capture_sidecar_inputs` now includes `transcript_source`
  (kind/provider), so identical cue text with a corrected provider
  refuses. The frozen reproduction passes.
- **Caller-supplied plan.** `capture_plan_matches` binds cues (including
  `source_url`, `source_deep_link`, `youtube_deep_link`, speaker and
  provenance), `chapter_rows`, `playback`, `transcript_kind` and
  `transcript_provider`. Artifact bytes, digest, markdown and the sealed
  block are not in that binding: a supported sealed-study override may
  replace producer bytes only while those consumed inputs remain bound.
  It is not an exemption from ownership.
- **Other consumed fields.** Cue-link, speaker-provenance, playback-
  identity and extra chapter-metadata changes with identical cue text
  also refuse. Non-owned sidecar keys are still merged (BD-05), not
  treated as plan inputs.
- First publication, identical retry, explicit empty replacement, newer
  publications, sidecar edit/removal preservation and Phase 3 S16 crash
  recovery are unchanged. Omitted-ticket helpers stay refused.

## Binding fields

Sidecar binding (`capture_sidecar_inputs`), compared after mint and at
the publication boundary:

| Input | Bound as |
|---|---|
| Cue text | `start`, `end`, `text` |
| Cue links | presence and value of `source_url`, `source_deep_link`, `youtube_deep_link` |
| Speaker | `speaker` only with a provenance object; provenance JSON |
| Transcript kind/provider | raw sidecar `transcript_source` |
| Source/playback identity | `video_id`, `source_type`, `source_url`, `url` |
| Chapters | full `source_chapters` list (extra keys change the archived artifact) |
| Artifact metadata | `yoinked_at`, `duration_seconds` |

Plan binding (`capture_plan_inputs`) additionally requires matching
`playback`, `transcript_kind` and `transcript_provider`. Non-owned
sidecar keys are excluded.

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
passing. BD-2 is 3/3. BD-3 is 1/1.

## Independent implementation tests

`tests/test_phase6_bc3e.py` (new file). Frozen acceptance files are not
replaced or deselected.

- `test_bc3e_capture_owner_binds_every_consumed_input` (5): identical cue
  text, competing complete owner before mint changes `transcript_source`,
  cue links, speaker/provenance, playback identity, or extra chapter
  metadata. Newer snapshot preserved.
- `test_bc3e_sealed_artifact_override_requires_bound_consumed_inputs`:
  extra producer-artifact key publishes while inputs match; the same
  override with a changed `transcript_source` after a newer owner
  refuses and leaves that newer snapshot.
- `test_bc3e_publication_boundary_rereads_disk_after_mint`: a complete
  newer owner inserted during `capture_snapshot` (after the post-mint
  check) is still refused at the publication boundary.
- `test_bc3e_non_owned_sidecar_key_is_not_a_consumed_capture_input`:
  `unrelated_owner` edited at mint is merged, not treated as a plan
  input.

## Commands and observed counts

Interpreter: `C:\Python314\python.exe` (3.14.6). Worktree cwd. PowerShell.

Environment: `PYTHONDONTWRITEBYTECODE=1`, `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`,
`PYTHONNOUSERSITE=1`, `ANTHROPIC_API_KEY` unset, `librarian_apply_enabled`
untouched. `PYTHONPATH` is the worktree plus the resolved installed
user-site (`C:\Users\hello\AppData\Roaming\Python\Python314\site-packages`
and its `win32` / `win32\lib` / `pythonwin` subdirs). Disposable roots
under worktree `_scratch/bc3e-roots\` (`TEMP`/`TMP`, `LOCALAPPDATA`,
`APPDATA`, `USERPROFILE`/`HOME`). Phase 3 also
`PHASE3_REQUIRE_IMPLEMENTATION=1`. No model, helper, port 5179, live
index, or paid API. Apply remains false. Logs and JUnit XML:
`_scratch/bc3e-w`.

```
python -B -m pytest -q -p no:cacheprovider tests/library_work_astra/test_phase6_bd3_acceptance.py tests/test_phase6_bc3e.py
```

**9 passed**, 81.52 s
(BD-3 provenance; five consumed-field races; sealed override bound vs
unbound; publication-boundary reread; non-owned sidecar key).

```
python -B -m pytest -q -p no:cacheprovider tests/library_work_astra/test_phase6_bd2_acceptance.py
```

**3 passed**, 8 warnings, 9.93 s
(capture owner; previously-published podcast control; never-published
podcast A after newer B).

```
python -B -m pytest -q -p no:cacheprovider tests/test_phase6_bc3a3.py
```

**5 passed**, 1.36 s
(empty omitted-ticket raw and Index; ticketed reconstruction fence;
removed/late-edited sidecar keys; final-write revalidation).

```
python -B -m pytest -q -p no:cacheprovider tests/library_work_astra/test_phase6_bd_acceptance.py
```

**11 passed, 3 failed**, 4 warnings, 17.34 s.
Failed: `test_bd01` raw, `test_bd01` Index, `test_bd03` (all omitted-ticket
setup). Passed: BD-02×4, BD-04, BD-05, BD-06, BD-07×2, BD-08, BD-09.

```
python -B -m pytest -q -p no:cacheprovider tests/test_phase6_evaluation.py tests/test_phase6_bc2.py tests/test_podcast_corpus_bridge.py tests/test_clips.py tests/test_library_resources.py
```

**103 passed, 8 failed**, 46 warnings, 37.69 s
(evaluation 17 passed / 2 failed, bc2 8 passed / 6 failed, podcast bridge
13, clips 15, library_resources 50).

```
PHASE3_REQUIRE_IMPLEMENTATION=1 python -B -m pytest -q -p no:cacheprovider tests/library_work_astra/test_phase3_publication.py tests/library_work_astra/test_phase3_integration.py tests/library_work_astra/test_phase3_recovery.py
```

**36 passed**, 1 warning, 8.26 s
(publication 15, integration 6, recovery 15, including
`test_s16_real_podcast_upsert_crash_does_not_enqueue`).

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
  the exact transcript file bytes consumed before mint.
- `library_unavailable` is still the only capture-seam code re-raised;
  `revision_unavailable` still returns True after a logged refusal. The
  newer snapshot is preserved in that compatibility return.
- First-publication podcast still hits `insert_citations` with `[]`
  before the fence (Phase 3 S16 seam). Replacement does not.
- The publication-boundary disk reread is in the owning capture
  publisher, immediately before `publish_media_snapshot`. It is not a
  file lock; SQLite `BEGIN IMMEDIATE` still does not protect pre-read
  files by itself.
- Astra's tests were not edited. No commit. Phase 6 is not claimed
  accepted. Astra verifies both roots and finishes BD-2.

## Files

`library_media.py`, `server.py`, `tests/test_phase6_bc3e.py`,
`docs/library/PHASE6-BC3E-GROK-2026-09-08.md`.
