# Corrected candidate: remaining product repairs

Authority: Ryan's 2026-09-09 ruling. Tested candidate:
`4a3531642692736d4aaa4098077ab8fde464aeb4`. **FAIL: 2,174 passed, 20 failed,
three skipped, one xfailed**, 183 warnings, 607.27 seconds. Only S21 was
excluded by the standing full-tree command. No further fixture edits are
authorized. This brief records product work; it does not waive a failure.

The [sealed result](proof/ryan-corrected-01-2026-09-09/summary.json),
[complete failure messages](proof/ryan-corrected-01-2026-09-09/failures.json)
and [case comparison](proof/ryan-corrected-01-2026-09-09/comparison.json)
bind every case below to the run. All 20 also failed on `6c313ea`; 72 other
cases failed there and passed here. Case membership is identical. Neither
observation changes the other's outcome. Twenty failed cases do not establish
twenty independent causes.

## 1. Phase 3 evidence retention: four failures

File: `tests/library_work_astra/test_phase3_acceptance7.py`.

- `test_as7_c21_at6_receipt_records_process_exit_status`: AT6 has no explicit
  successful process exit value.
- `test_as7_c21_all_at6_artifact_bytes_are_archived`: four expected artifact
  hashes have no retained matching bytes.
- `test_as7_c21_browser_run_has_retained_receipt_and_database[at6-browser]`:
  no receipt matches the screenshot's feed port 64703.
- `test_as7_c21_browser_run_has_retained_receipt_and_database[c21-pill-browser]`:
  no receipt matches feed port 49557.

Repair scope: recover original, hash-identical artifacts and verifiable launch
metadata from retained task archives, and repair the evidence producer's durable
receipt handling. Do not contact either historical feed, infer a zero exit from
a later success, invent an old database or rewrite historical measurements.
AS-8/AS-9 replacement evidence remains useful history but does not pass these
assertions. If original proof is unrecoverable, record exactly what is missing
and leave those failures open. A new observation needs a separate brief and
identity; it cannot become an AT6 observation retroactively. This is an open
product/evidence defect under Ryan's ruling, separate from installed C22.

Verify `test_phase3_acceptance7.py`, `test_phase3_acceptance8.py` and
`test_phase3_acceptance9.py` together under `tests/library_work_astra`, then
the strict Phase 3 suite excluding S21 and its named companion groups.

## 2. Phase 4 lifecycle: five failures

File: `tests/test_phase4_av5m4b_lifetime.py`.

- `test_job_assignment_failure_refuses_before_mutation`: after refused job
  assignment, `_foreign_vault_worker_alive` still reports true.
- `test_child_boundary_timeout_confirms_death_and_keeps_user_edit`
- `test_timed_out_parent_cannot_use_later_resync_session`
- `test_second_process_with_different_temp_root_is_excluded`
- `test_corrupt_lease_does_not_grant_destination`

The latter four fail at their initial ordinary export with
`destination_unavailable/OSError`. Captured event logging reports “operation
is no longer live.” The tree does not reach their later behavioral checks.
Investigate failed-start ownership and originating-thread session cleanup,
including conservative liveness queries after death. The shared-state cause
is not established by this full-tree output alone.

Repair the production lifecycle. Do not reset module globals from a fixture,
add test-order exceptions, grant foreign callers cleanup authority, assume a
missing PID proves death or relax the Windows lifetime exclusion. Verify this
whole file in its original order, the AV5m4b2 lifetime file, and all AW-5 through
AW-12 acceptance files that exist in `tests/library_work_astra`, including
AW-11's foreign-helper cases, before the broader mirror union/full tree.

## 3. Phase 4 interrupted writes and user ownership: eight failures

`tests/library_work_astra/test_phase4_aw2_acceptance.py`:

- `test_d13_replace_syscall_cannot_complete_after_timeout`

`tests/library_work_astra/test_phase4_aw3_acceptance.py`:

- `test_d12_retry_keeps_ownership_of_interrupted_temp`
- `test_d12_control_hard_purge_removes_unedited_recorded_temp`
- `test_d12_recorded_temp_path_does_not_authorize_deleting_user_replacement`
- `test_d13_timeout_never_publishes_or_rolls_back_over_user_bytes[visibility]`
- `test_d13_timeout_never_publishes_or_rolls_back_over_user_bytes[user_edit]`
- `test_d13_timed_out_writer_cannot_erase_a_later_successful_sync`

`tests/library_work_astra/test_phase4_aw_acceptance.py`:

- `test_purge_removes_intent_owned_actual_temp_name`

D13's parent replacement event is never entered; D12 observes no allocated
temporary file, and the final purge probe observes no orphan. The production
writer now runs in an isolated child. Ryan authorized the D13 user-edit ordering
only; changing these remaining interception boundaries is outside that ruling.
All eight remain product defects for this gate, even when a setup boundary
explains where the assertion fails.

Review whether a supported production fault-observation boundary can satisfy
the fixed contracts while preserving cancellable child I/O and actual file
identity checks. Do not restore unbounded parent writes, introspect test callback
closures, simulate an entered event, or publish/erase personal bytes to satisfy
a probe. Document any contract incompatibility explicitly instead of producing
a test-specific workaround. Verify the three complete named files plus
`tests/test_library_mirror.py` and the Phase 4 lifetime/identity/binding repair
files. Keep the corrected D15 persistence test in the union; it passed this run.

## 4. Phase 5 actual SDK serialization: one failure

`tests/library_work_astra/test_phase5_ba4_acceptance.py::test_ba4_actual_sdk_serialization_retains_admission_and_deadline`
observed a successful result after delayed SDK serialization, with active
admissions `[0]`. Its later deadline-envelope and admission assertions are not
reached. The corrected unary-clock final-wire test passed separately.

Review the low-level SDK server route exercised by this fixed test and retain
admission until actual serialization/deadline settlement on supported routes.
Do not call the historical “old route” classification a pass, modify installed
third-party files, or inspect callback closures. Preserve full evidence and
pagination. Verify the complete BA-4 file, `test_phase5_acceptance3.py`, all
Phase 5 acceptance files, `tests/test_library_analysis*.py` and
`tests/test_phase5*.py` before the full tree. Part B remains deferred. The
24,576-byte dashboard target remains a separate failed measurement; this
brief does not authorize relabeling or repeating it without its own repair.

## 5. Phase 6 refusal semantics: two failures

- `tests/test_phase6_bc2.py::test_bc2_publication_fence_refuses_every_stale_publisher`
- `tests/test_phase6_evaluation.py::test_phase6_rebuild_and_publication_recovery`

Both receive `invalid_request` where the unchanged assertion requires
`revision_unavailable`. Their intentionally ticketless stale publication
reaches `publication_ticket_required`; successful setup now has original
build-time tickets. These are failures, not accepted refusal substitutions.

Repair the product's refusal precedence if it can satisfy both contracts:
require original publication authority, reject genuinely malformed/missing
authority, and report stale committed input truthfully. Do not mint a ticket
for an already-built snapshot or allow stale publication. Examine all explicit
missing/foreign/malformed-ticket cases before changing validation order. Verify
both complete named files, `tests/test_phase6_bc3f.py` and all BD/BD-2 acceptance
files under `tests/library_work_astra`, then the full Phase 6 union/tree. No
diarization, speaker-accuracy claim or new source fetch is authorized.

## Execution and completion

Each package above requires a reviewed production diff and documented repair
before a new run. A narrower diagnostic must have its own stated question and
receipt; passing it cannot erase this full-tree result. Resolve file selectors
against the repository before dispatch. Control Room workers use the handoff's
worktree verification, patch integration, checkout verification and commit
sequence. Do not change any existing test again.

The final corrected-tree command remains the isolated runner against `tests`
with only `--ignore=tests/library_work_astra/test_phase3_s21.py`. Preserve the
tested commit, complete outcomes, runner/guard, interpreter provenance and
raw bytes. Use a fresh label and update the handoff after integration.

Installation has an additional, separately observed source defect described in
[INSTALL-ISOLATION-REPAIR-BRIEF-2026-09-09.md](INSTALL-ISOLATION-REPAIR-BRIEF-2026-09-09.md).
It is not a twenty-first test failure. If production source changes, verify
that source and rebuild/reseal the candidate before issuing executable installed
receipt commands. The existing package and failed measurements remain retained.
