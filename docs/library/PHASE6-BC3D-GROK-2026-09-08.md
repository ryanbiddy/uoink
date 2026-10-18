# Phase 6 BC-3d session (grok)

Worker: grok
Run: BC-3d (bind owning publication inputs before they become stale)
Findings: BD2-01 (capture owner rebases already-read cues onto a newer
publication), BD2-02 (podcast owner publishes never-seen stale transcript A
over completed B)
Base: `90151e7` on `cc/living-library` (`control-room/31d2ed06-d4c-grok`).
Do not commit. Astra independently verifies both roots and finishes BD-2.

## Status

Complete as an implementation candidate. The two owning-input races are
repaired at the real capture and podcast call sites. Frozen acceptance
files were not edited, including
`tests/library_work_astra/test_phase6_bd2_acceptance.py`. Named Phase 6
and Phase 3 companion suites were run in full. Unchanged omitted-ticket
helper refusals remain failed for Ryan's existing fixture ruling. This
run does not claim Phase 6 accepted.

## Repair

Inspected owning call sites, not the isolated helper:

- `server._index_yoink` built `_capture_media_plan` from the in-memory
  sidecar, then `_publish_capture_media` minted. A completed newer
  capture inserted immediately before that mint was overwritten by the
  old plan.
- `podcasts.episode_to_corpus` loaded the transcript file and built
  citation inputs, then minted. Never-published input A replaced
  completed newer B after acquiring B's base. The previously-published
  podcast control already passed because ledger history rejected A;
  history cannot protect an unseen target.

Repair: consume the mutable inputs, mint, then validate those exact
consumed inputs under the ownership boundary. A dependency change
refuses `revision_unavailable` (`publication_input_changed`) before any
publication write and leaves the current snapshot. Do not mint a current
ticket as a license to publish already-read stale cues. Do not rebuild
old cues under a newer base or hash. The publisher still never mints.

- **BD2-01.** `_index_yoink` no longer builds the capture plan before the
  ticket. `_publish_capture_media` mints first, then
  `require_unchanged_capture_inputs` compares the consumed sidecar's
  transcript cores and `source_chapters` to disk. A caller-supplied plan
  is kept only when it still matches the owned plan (sealed study
  artifact override). Mismatch refuses; `_index_yoink` logs
  `revision_unavailable` and still returns True after the row is present
  (BC-2 compatibility). The newer snapshot is preserved.
- **BD2-02.** `episode_to_corpus` reads the transcript bytes once, mints,
  then `require_unchanged_input_bytes` before building and again before
  upsert/publish. A changed transcript file refuses
  `revision_unavailable`. First publication, identical republish, empty
  capture replacement, crash recovery (Phase 3 S16), sidecar
  preservation and the previously-published podcast control are
  unchanged.

Omitted-ticket helpers stay refused. No empty/first/evaluation
exception was reintroduced.

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
passing. BD-2 is 3/3.

## Commands and observed counts

Interpreter: `C:\Python314\python.exe` (3.14.6). Worktree cwd. PowerShell.

Environment: `PYTHONDONTWRITEBYTECODE=1`, `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`,
`PYTHONNOUSERSITE=1`, `ANTHROPIC_API_KEY` unset, `librarian_apply_enabled`
untouched. `PYTHONPATH` is the worktree plus the resolved installed
user-site (`C:\Users\hello\AppData\Roaming\Python\Python314\site-packages`
and its `win32` / `win32\lib` / `pythonwin` subdirs). Disposable roots
under worktree `.bc3d-scratch\` (`TEMP`/`TMP`, `LOCALAPPDATA`, `APPDATA`,
`USERPROFILE`/`HOME`). Phase 3 also `PHASE3_REQUIRE_IMPLEMENTATION=1`. No
model, helper, port 5179, live index, or paid API. Apply remains false.
Logs and JUnit XML: `_scratch/bc3d-w`.

```
python -B -m pytest -q -p no:cacheprovider tests/library_work_astra/test_phase6_bd2_acceptance.py
```

**3 passed**, 8 warnings, 9.44 s
(capture owner; previously-published podcast control; never-published
podcast A after newer B).

```
python -B -m pytest -q -p no:cacheprovider tests/test_phase6_bc3a3.py
```

**5 passed**, 1.38 s
(empty omitted-ticket raw and Index; ticketed reconstruction fence;
removed/late-edited sidecar keys; final-write revalidation).

```
python -B -m pytest -q -p no:cacheprovider tests/library_work_astra/test_phase6_bd_acceptance.py
```

**11 passed, 3 failed**, 4 warnings, 14.46 s.
Failed: `test_bd01` raw, `test_bd01` Index, `test_bd03` (all omitted-ticket
setup). Passed: BD-02×4, BD-04, BD-05, BD-06, BD-07×2, BD-08, BD-09.

```
python -B -m pytest -q -p no:cacheprovider tests/test_phase6_evaluation.py tests/test_phase6_bc2.py tests/test_podcast_corpus_bridge.py tests/test_clips.py tests/test_library_resources.py
```

**103 passed, 8 failed**, 46 warnings, 37.45 s
(evaluation 17 passed / 2 failed, bc2 8 passed / 6 failed, podcast bridge
13, clips 15, library_resources 50).

```
PHASE3_REQUIRE_IMPLEMENTATION=1 python -B -m pytest -q -p no:cacheprovider tests/library_work_astra/test_phase3_publication.py tests/library_work_astra/test_phase3_integration.py tests/library_work_astra/test_phase3_recovery.py
```

**36 passed**, 1 warning, 7.50 s
(publication 15, integration 6, recovery 15, including
`test_s16_real_podcast_upsert_crash_does_not_enqueue`).

Warnings are `datetime.utcnow()` deprecation from `podcasts.py` /
`memory_layer.py`. Retained.

## Limitations

- Frozen evaluation/BC-2/BD helpers that omit a ticket still refuse at
  the boundary. That is the intended production contract. Those files
  stay unchanged until Ryan authorizes setup to acquire and carry the
  ticket while preserving every behavioral assertion.
- A ticketless call on a corrupt ledger or a contradictory sidecar
  reports `publication_ticket_required` first. Ticketed
  `begin_publication` still surfaces `publication_ledger_corrupt`.
- Capture ownership compares transcript cores and `source_chapters` on
  the consumed sidecar against disk after mint. Other sidecar keys
  remain BD-05 merge/revalidation. Podcast ownership compares the exact
  transcript file bytes consumed before mint.
- `library_unavailable` is still the only capture-seam code re-raised;
  `revision_unavailable` still returns True after a logged refusal. The
  newer snapshot is preserved in that compatibility return.
- First-publication podcast still hits `insert_citations` with `[]`
  before the fence (Phase 3 S16 seam). Replacement does not.
- Astra's tests were not edited. No commit. Phase 6 is not claimed
  accepted. Astra verifies both roots and finishes BD-2.

## Files

`library_media.py`, `podcasts.py`, `server.py`,
`docs/library/PHASE6-BC3D-GROK-2026-09-08.md`.
