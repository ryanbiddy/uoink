# Phase 6 stale-publication refusal repair (Grok)

Worker: grok
Worktree: `C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library\d4d402e8-246\grok`
Branch: `control-room/d4d402e8-246-grok`
Base HEAD at start: `a74385cd0cca237c3c6bdbdb3c0676cad8a799e9`
Sealed corrected-tree failures retained:
`docs/library/proof/ryan-corrected-01-2026-09-09/`
(`4a3531642692736d4aaa4098077ab8fde464aeb4`, 2,174 passed / 20 failed).

No subagents. No existing test, assertion, fixture, skip or parameter edits.
No commits, pushes, main merge or other-worktree edits. No live index, port
5179, diarization, fetch, paid API or `ANTHROPIC_API_KEY`. Synthetic data
only. Isolated runner/guard from the sealed proof directory.

## Original tickets and failed outcomes (preserved)

Corrected-tree product brief section 5, unchanged assertions:

| Test | Expected | Observed on `4a35316` |
|---|---|---|
| `tests/test_phase6_bc2.py::test_bc2_publication_fence_refuses_every_stale_publisher` | `revision_unavailable` / `superseded_snapshot` on ticketless `_publish(conn, a)` after B committed | `invalid_request` / `publication_ticket_required` (`library_media.py` early omitted-ticket raise) |
| `tests/test_phase6_evaluation.py::test_phase6_rebuild_and_publication_recovery` | `revision_unavailable` on ticketless `_publish(conn, f)` after shorter committed | same early omitted-ticket raise |

Successful setup already carries original build-time tickets (Ryan's 2026-09-09 fixture correction). The failing calls are the intentionally ticketless stale publications. They remain ticketless in the frozen tests.

## Explicit ticket contracts reviewed

| Case | File | Required refusal |
|---|---|---|
| Ticketless publish of a snapshot already in ledger history (seeded A, then fenced B) | `test_bc2_publication_fence_refuses_every_stale_publisher` | `revision_unavailable` / `superseded_snapshot` |
| Ticketed A after B | same | `revision_unavailable` / `publication_superseded` |
| Ticketed D after E with an older ticket | same | `revision_unavailable` / `publication_superseded` |
| Foreign or malformed ticket (`PublicationTicket` for another item, `"ticket"`, `7`) | same | `invalid_request` (`ticket_identity`) |
| Deleted item, ticketed publish / mint | same | `resource_deleted` |
| Ticketless never-published empty snapshot after a newer ticketed publication | `test_bc3a3_stale_empty_build_without_a_ticket_is_refused` (raw and Index) | `invalid_request` / `publication_ticket_required` |
| Ticketless stale A that was never committed (BD-01 raw and Index) | `test_bd01_never_published_stale_snapshot_requires_original_ticket` | `invalid_request` or `revision_unavailable`; must not write |
| Ticketed retry / crash settle | `test_bc2_fenced_retry_recovers_from_each_boundary_and_a_corrupt_ledger_refuses` | original ticket; corrupt ledger `invalid_source_data` / `publication_ledger_corrupt` |
| User-edited corpus after a ticketed publication | `test_phase6_rebuild_and_publication_recovery` | `revision_unavailable` (`corpus_edited`); no overwrite |
| Reconstruction of a superseded sidecar | `test_bc3a3_stale_sidecar_reconstruction_refuses_after_ticketed_publication`, BD-03 | `revision_unavailable` |

These are not the same request. Ledger history membership is a committed fact. A never-published empty or other new snapshot is not in that history.

## Repair (documented before the verification run)

No contract conflict: the product can distinguish obsolete committed input from a malformed new request without minting a ticket, allowing a stale write, detecting callers/tests, falling back to a fresh ticket, unconditionally allowing a missing ticket, or relabeling an unverified snapshot.

Change, `library_media.publish_transcript`:

1. Foreign/malformed tickets still refuse `invalid_request` / `ticket_identity` before storage.
2. An omitted ticket no longer returns immediately. The request still validates the media block (so `media_revision` is the sealed hash, not a claimed string), artifacts, sidecar identity and corpus binding, then takes `BEGIN IMMEDIATE`.
3. Under that lock, after `_publication_state`:
   - if `ticket is None` and the validated target is in the ledger `history`, refuse `revision_unavailable` / `superseded_snapshot`;
   - if `ticket is None` otherwise, refuse `invalid_request` / `publication_ticket_required`.
4. File replacement, ledger claim, sidecar merge, bound-input checks and DB writes still require a `PublicationTicket`. Omitted-ticket paths never reach them. Rollback on `MediaError` is unchanged.

Change, `Index.publish_media_snapshot`: drop the extra omitted-ticket raise so both entry points use the same publisher classification. The Index wrapper still does not mint a ticket, still refuses an active caller transaction, and still runs Phase 2 invalidation only after a successful publisher return.

Not done:

- No ticket mint at publication time.
- No write when `ticket is None`.
- No treatment of "different from current" as stale (that would misclassify BC-3a3's never-published empty snapshot).
- No history check on an unvalidated block.
- No caller/test detection.
- No change to deletion, annotation retention, sidecar merge, clip identity, crash retry, or final-replacement input rechecks.

## Isolated verification

Runner: `docs/library/proof/ryan-corrected-01-2026-09-09/integrator_verify.py`
Guard: that directory's `sitecustomize.py` / `ig_paths.py` (copied by the runner into the disposable scratch).
Interpreter: `C:\Python314\python.exe` (3.14.6). `ANTHROPIC_API_KEY` unset.
Resolved selectors (all `tests/test_phase6*.py` files plus named BD/BD-2 files, and BD-3/BD-4 companions):

- `tests/test_phase6_bc2.py`
- `tests/test_phase6_evaluation.py`
- `tests/test_phase6_bc3f.py`
- `tests/test_phase6_bc3a3.py`
- `tests/test_phase6_bc3e.py`
- `tests/library_work_astra/test_phase6_bd_acceptance.py`
- `tests/library_work_astra/test_phase6_bd2_acceptance.py`
- `tests/library_work_astra/test_phase6_bd3_acceptance.py`
- `tests/library_work_astra/test_phase6_bd4_acceptance.py`

Command:

```
C:\Python314\python.exe -B docs/library/proof/ryan-corrected-01-2026-09-09/integrator_verify.py --root <worktree> --label p6-refusal-01 tests/test_phase6_bc2.py tests/test_phase6_evaluation.py tests/test_phase6_bc3f.py tests/test_phase6_bc3a3.py tests/test_phase6_bc3e.py tests/library_work_astra/test_phase6_bd_acceptance.py tests/library_work_astra/test_phase6_bd2_acceptance.py tests/library_work_astra/test_phase6_bd3_acceptance.py tests/library_work_astra/test_phase6_bd4_acceptance.py
```

Outcome, label `p6-refusal-01`: **71 passed, 0 failed, 0 skipped**, 20 datetime warnings, 213.03 seconds, runner exit 0. JUnit `errors="0" failures="0" skipped="0" tests="71"`. Receipts: `_scratch/p6-refusal-01/tests.log`, `tests.xml`, `results.json`. Disposable profile under `_scratch/p6-refusal-01`; live index and 5179 not contacted.

Both originally failing tests passed in that XML:

- `tests.test_phase6_bc2::test_bc2_publication_fence_refuses_every_stale_publisher` (0.519 s)
- `tests.test_phase6_evaluation::test_phase6_rebuild_and_publication_recovery`

BC-3a3 omitted-ticket empty-build (raw and Index), foreign/malformed ticket cases, crash-retry, reconstruction, BD-01/02/03/05/06, BD-2/3/4 and BC-3e/3f all passed in the same union.

## Line-ending restore (not a product repair)

After the passing union, `search_replace` had rewritten `index.py` as CRLF (HEAD is mixed LF with 9 CRLF lines) and `library_media.py` as CRLF (HEAD is LF). Restored `index.py` from HEAD and re-applied the same five-line Index change as raw LF bytes. Converted `library_media.py` back to LF. Semantic diff unchanged. Confirmation run of the originally failing tests plus omitted-ticket Index/raw cases follows; reason: bytes on disk after the restore, not a new product change.

Command, label `p6-refusal-02`:

```
C:\Python314\python.exe -B docs/library/proof/ryan-corrected-01-2026-09-09/integrator_verify.py --root <worktree> --label p6-refusal-02 tests/test_phase6_bc2.py::test_bc2_publication_fence_refuses_every_stale_publisher tests/test_phase6_evaluation.py::test_phase6_rebuild_and_publication_recovery tests/test_phase6_bc3a3.py::test_bc3a3_stale_empty_build_without_a_ticket_is_refused tests/library_work_astra/test_phase6_bd_acceptance.py::test_bd01_never_published_stale_snapshot_requires_original_ticket
```

Outcome: **6 passed**, 5.81 seconds, runner exit 0. Receipts: `_scratch/p6-refusal-02/`.

## Source diff (worktree, uncommitted)

`library_media.py` (28 lines): omitted tickets are classified under `BEGIN IMMEDIATE` after `validate_media_block`. History membership → `revision_unavailable` / `superseded_snapshot`. Otherwise `invalid_request` / `publication_ticket_required`. Foreign/malformed tickets remain `ticket_identity` before storage. No mint, no write without a ticket.

`index.py` (5 lines): `publish_media_snapshot` no longer raises omitted-ticket itself; it forwards `ticket` to `publish_transcript`. Active-transaction refusal and post-success invalidation unchanged.

No existing tests edited.

## Limits

- This worker does not rerun the sealed full tree and does not replace
  `proof/ryan-corrected-01-2026-09-09`.
- Phase 6 release claims remain chapters/cited ranges only. No speaker
  attribution.
- Astra verifies independently in both roots before integrating.
- No commit or push from this worktree.
