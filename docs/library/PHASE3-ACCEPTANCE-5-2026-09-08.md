**NOT ACCEPTED. AS-02 and AS-03 remain open: twelve new reproductions fail.
AS-01, AS-04, AS-05 and AS-06 remain closed. The installed Inno receipt remains
a required condition, C22, for eventual acceptance.**

Run AS-5, codex independent review of AT-5 against the
[AS-4 specifications](PHASE3-ACCEPTANCE-4-2026-09-08.md) and contract
`phase3-v1-2026-09-07`. Reviewed clean HEAD:
`6d837e3e2f1db2a65df647e78da4fe3814c83195`. Candidate:
`9272e40a90880e7d0ba9557da22c6b0ac6bf2311`. The only intervening changes are
the S21 receipt, evidence database and checksum manifest. No production code
differs from that candidate.

All six AS-4 failures now pass. AT-5 implements the requested common child-status
gate, persists launch intent before `Popen`, propagates intent/registration write
failures, separates the two cleanup methods and reads manual prior state before
the first lock wait. The remaining failures concern the rest of those same
specifications: uncertain launch outcomes, damaged ownership evidence, lock
lifetime through settlement/reconciliation and publication completeness.

| Independently executed group | Observed result | Exit |
|---|---|---|
| Supplied strict Phase 3 suite | 136 passed; 6 warnings; 30.11 s | 0 |
| New AS-5 cases | 2 passed, 12 failed; 8.39 s | 1 |
| Full strict suite including AS-5 | 138 passed, 12 failed; 6 warnings; 39.12 s | 1 |
| Source subscription companions | 111 passed; 5 warnings; 9.73 s | 0 |
| Dashboard source companions | 31 passed; 0.54 s | 0 |
| Legacy companions | 27 passed; 19 warnings; 1.82 s | 0 |
| Adapter/registry companions | 98 passed; 0.96 s | 0 |
| Podcast companions | 30 passed; 74 warnings; 2.75 s | 0 |
| Packaging companions | 6 passed; 1.45 s | 0 |
| Heartbeat companions | 10 passed; 0.14 s | 0 |
| Additional Phase 0 CLI/provenance/X checks | 49 passed; 4.55 s | 0 |
| Opt-in real-child interruption probe | Live child incorrectly reported stopped; child reaped | 1 |

The seven AS-4 companion groups total **313 passed**. The additional three files
bring this review's companion total to **362 passed**. The reported 365 still
lacks an exact selector list; this review does not invent the remaining three
cases. The current registry assertion is **87 tools**, including the integrated
Phase 4 brief tools, and passes. Counts include fixture and static checks; they
are not counts of installed-system observations.

Tests used Windows/Python 3.14.6, `PHASE3_REQUIRE_IMPLEMENTATION=1`, disabled
plugin autoload and disabled bytecode writes. There were no final skips or
fixture setup/teardown errors. Companion groups ran in separate interpreters
with disposable profiles, output and temporary directories under
`_scratch/as5`. Server-importing groups used byte-identical `server.py` copies
for token/log isolation, with resource paths pointing into this worktree.
Audit guards blocked non-fixture database access and file writes, product child
launches, model imports and external networking. The standard-library loopback
socket-pair operation was allowed, excluding 5179.

Initial companion imports were stopped by an inherited output-directory
override; setting `UOINK_OUTPUT_DIR` and its legacy alias to the fixture fixed
the runner. Final import-time process probes hit the guarded null-device write,
and WhisperX availability imports were blocked. Podcast tests also attempted
DNS and process setup; the guards blocked them. These are guarded passing
runs, with attempted calls disclosed. No model, resident helper, port 5179 or
live index was used. S21 and the historical process-recovery launcher were not
rerun. The separate AS-5 launch probe ran only bounded Python fixture children.

**AS-02: terminal gates are repaired, but child-absence evidence remains unsafe.**
`_ServerCaptureBackend.probe` and `verify_proof` now require acceptable child
status before their terminal branches. The live/unknown terminal-job and
synchronous-return cases pass. The two new write-failure cases also pass:
failure to persist intent prevents spawning, and registration-write failure
propagates while the durable unresolved intent keeps the probe unknown.

Two remaining defects prevent closing AS-02:

| Defect and reproduction in `test_phase3_acceptance5.py` | Observed behavior | Required repair |
|---|---|---|
| **AS-02a**, `test_as5_s13_interruption_inside_popen_retains_launch_uncertainty` | `_run_subprocess` catches every `BaseException` from `Popen` and clears the intent. An interruption after OS child creation but before the constructor returns leaves `children='none'`, `probe='stopped'` and a failed ledger row. | Clear intent only on affirmative evidence that no child was created. Retain uncertainty on interrupted or otherwise indeterminate creation, or establish containment that proves child termination. Preserve the working pre-spawn and registration-write protections. |
| **AS-02b**, `test_as5_s13_structurally_damaged_child_record_is_not_absence` (3 variants) | Valid JSON with a missing `children` field, a non-object child entry or another `start_id` is accepted as no children. A dead-parent probe settles the attempt and removes its execution evidence. | Validate the child-record schema and start binding before interpreting absence. Missing/malformed required fields and invalid entries must remain unknown; write helpers must not silently replace damaged evidence with empty children. |

AS-02a is also independently reproduced with a **real Windows child through
the unchanged production `_run_subprocess`**. The opt-in launcher wraps Python's
real `Popen._execute_child`, delegates to OS creation, then injects
`KeyboardInterrupt` before `Popen` returns. A terminal fixture job makes the
production probe's settlement decision observable. Python's constructor
exception cleanup does not terminate that child. The retained command is:

```powershell
python -B tests/library_work_astra/test_phase3_acceptance5.py --execute-launch-probe
```

Observed on the final launcher run, exit 1:

```json
{
  "interrupt_propagated": true,
  "child_pid": 65676,
  "real_child_running": true,
  "child_status": "none",
  "probe": "stopped",
  "all_created_children_reaped": true
}
```

The child had a 15-second maximum script lifetime and was explicitly terminated
and waited for in `finally`. A preliminary disposable version produced the same
result and also reaped its child. This is an injected interruption with real
process liveness, not a spontaneous crash or installed-helper restart. The
launcher records command, interpreter and input hashes in
`_scratch/as5/real-launch-interrupt.json`. Production `server.py` SHA-256 is
`c6b85b4588b7bcd98958a09594a137e55576b75d5fa24279830a346ed5557c16`;
the final AS-5 test/launcher file at execution hashed to
`dd2345ef2e4a6ca7af53db43f9f889e00861053aa04443914fe707c75177137d`.

**AS-03: the shadowed method and first wait are repaired; cleanup and completeness
still need work.** `_release_dispatcher_ownership` and
`_release_execution_claim` are distinct. The consent-off-after-acquisition
case now releases both locks without dispatch or charge. `_advance_source`
retains locks for uncertain synchronous outcomes, and both original manual-wait
completion cases pass. The caller audit does not yet cover the whole lifetime:

| Defect and reproduction in `test_phase3_acceptance5.py` | Observed behavior | Required repair |
|---|---|---|
| **AS-03a**, `test_as5_s15_worker_exit_retains_locks_while_child_unsettled` (4 variants) | The YouTube worker's `finally` at `server.py:8149` and podcast settlement callback at `server.py:7668` release ownership even though the ledger stays uncertain and the execution claim remains. For both live and unknown children, a competing capture lock succeeds. Podcast variants use real podcast ledger rows. | Make callback cleanup consume the verified settlement result. Retain the capture lock, and the YouTube process lock, while child termination remains uncertain. Audit exceptions and stale callbacks as well as normal returns. |
| **AS-03b**, `test_as5_s15_reconciliation_settles_and_releases_retained_locks` (2 variants) | After a synchronous failure first retains ownership, child termination becomes established and `probe` says stopped. Without publication, recovery tries to acquire its own held lock and stays uncertain. With complete publication, reconciliation succeeds and removes the claim but leaves both locks held. | Reconciliation must recognize and safely reuse ownership retained for this start. Release dispatcher locks after verified terminal ledger commit as well as claim cleanup. Make cleanup idempotent and bound to the owning start; preserve ownership until termination is established. |
| **AS-03c**, `test_as5_s15_manual_waiter_does_not_report_partial_capture_success` (2 variants) | A publication stops after item upsert, or leaves a damaged sidecar, during the first manual wait. The actual completion check correctly fails the standing attempt. `_ManualOwnership.recheck` nevertheless returns `ok=True`, `reused=True`, `reason='captured_while_waiting'`. | Apply the common completeness/identity checks to manual reuse before returning success. Partial evidence needs recovery or an explicit failure. Establish deliberate refresh from the request's prior state without treating mere corpus-row presence as completed publication. |

AS-03a allows manual work to cross the lock boundary while a standing child may
still execute. AS-03b can block later YouTube work for the process lifetime.
AS-03c reports damaged output as complete. These outcomes violate AS-4's explicit
requirements to preserve uncertain ownership, release verified-terminal ownership
and distinguish complete publication from a corpus row.

The earlier disclosures retain their AS-4 rulings. Local recovery after verified
termination may publish under the capture lock without taking a new execution
claim, preserving the original start and charge. A crash in the ledger/claim
gap may conservatively retain the charged intent without redispatch. Neither
exception permits false termination evidence or the lock failures above.

**The extended S21 receipt materially improves the evidence, with limits.** I
read the [AT-5 receipt](proof/s21-2026-09-08/receipt-at5-candidate-9272e40-extended-launcher.json)
and opened its supplied [evidence database](proof/s21-2026-09-08/evidence-at5-candidate-9272e40.db)
using SQLite `mode=ro&immutable=1`. Integrity is `ok`, foreign-key violations are
empty, and its SHA-256 matches the receipt:
`46dbdfc263e918116b80742075b5f66f40332da07c1b8103f8e23c53393e89b4`.
All ten [SHA256SUMS](proof/s21-2026-09-08/SHA256SUMS) entries match.

The database independently establishes one charged succeeded start, one committed
future-eligible item, one podcast episode/corpus row, one citation and one
12.5–21.75-second clip. Feed/GUID/capture-key/episode bindings agree across the
source item, episode and corpus metadata. The ledger's incarnation and token
hash agree with the receipt's claim observations. There is one outbox row, one
run and one ready work row, zero client attempts and zero shelf memberships.
This supports the unfiled/waiting-for-client result.

The receipt names candidate `9272e40`, records the real incarnation and reports
exclusive capture-lock and claim ownership at download, transcription,
publication and publication return, followed by claim cleanup and lock
availability at settlement. It reports one fixture download, one synthetic
transcript, prepare after commit, zero model calls and no forbidden attempts.
Those observations support the successful controlled capture; they do not
exercise child-launch interruptions or the failing cleanup paths above.

Ten of the twelve recorded input hashes match this checkout byte for byte.
Migration 0028 matches after CRLF-to-LF normalization. The **launcher hash remains
unresolved**: receipt `d17a84c65d126abc60774ccb5fe1b63f6195faca4435f6d2a8e8f116e326b3a7`;
checked-out file `be212fe55ff13d1475dc1d8b89dd397256e71669e1bffff7946c10cd977ba635`;
LF-normalized file `e4649df0ca1278c2ce509536e45dbcf7899481be271c789ed7e780316ec5dff5`.
There is no Git difference between candidate and HEAD for that launcher.
Mixed line endings could be involved, but the executed bytes are not supplied
and this review cannot establish that explanation.

Six hashed artifacts remain outside the supplied package: the transcript,
server log, incarnation file, podcast markdown/sidecar and generated taxonomy.
Their originating paths were not followed into another checkout. Sidecar
provenance and the ownership observations therefore have receipt support, with
database cross-checks where possible, rather than full artifact reinspection.
The receipt also lacks an explicit exit-code field.

I inspected both supplied screenshots. They are unchanged historical images;
the Sources image names feed port 51563, while this AT-5 receipt uses 49194.
They show an unfiled podcast card and an on-source with 1/10 starts and 0/25
enrollment. They do not demonstrate the AT-5 browser run or the full S20 matrix.
The receipt itself says browser observation is still required.

The historical process-recovery receipt still supports its registered-child
scenario. Its launcher calls `Popen` followed by registration directly; it does
not certify the repaired `_run_subprocess` launch boundary or an installed
restart. The AS-5 real-child observation supplies direct evidence of the
remaining interruption defect. The staged S22 receipt retains its limited
copy-list/import/stdio value.

| Gate | AS-5 disposition |
|---|---|
| S01–S12 | Existing migration, consent, detection, allowance, retry and clock checks pass. AS-04/05 remain closed. |
| S13–S14 | Original ownership cases pass; AS-02a/b prevent acceptance. |
| S15 | Identity checks remain closed under AS-06. AS-03a/b/c block acceptance. |
| S16 | AS-01 publication and derivation checks pass. Recovery still depends on correct ownership/lock settlement. |
| S17–S19 | Handoff, waiting state and adapter/registry checks pass within fixture scope. |
| S20 | API/static coverage and historical images credited; C20 remains. |
| S21 | Extended ownership/provenance receipt and retained database credited; C21 is narrowed but remains. |
| S22 | Packaging tests and staged receipt credited; actual Inno qualification remains C22. |

After the code defects are repaired, these acceptance conditions remain:

- **C20:** supply the disposable candidate's browser matrix for default off,
  pending/actual enrollment, exhaustion, refresh errors, off with in-flight work,
  lost response, stale confirmation and restart, matched to persisted state.
- **C21:** reconcile the exact executed launcher bytes/hash, record command and
  exit, and archive the missing artifacts/logs. Supply candidate-matched browser
  observations of identity, episode link, provenance, unfiled status and
  waiting-for-client. The supplied database already satisfies that retention
  requirement; the new ownership and incarnation observations are credited.
- **C22, Ryan:** supply the actual disposable Windows Inno installation receipt,
  with package/candidate hashes, bundled interpreter/dependencies, installed
  paths, migration/upgrade replay, registry schemas, unrelated one-off capture,
  both manual/standing orderings and process recovery through the real launch
  path, including launch/registration failure. Record protected Phase 2
  input/state preservation and isolation from models, the resident helper/port
  and live index. **Yes, this is a mandatory condition of eventual Phase 3
  acceptance.** Source staging does not complete it.

Reproduce the strict tests from this worktree:

```powershell
$env:PHASE3_REQUIRE_IMPLEMENTATION = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
$phase3Tests = (Get-ChildItem -LiteralPath 'tests/library_work_astra' -Filter 'test_phase3_*.py').FullName
python -B -m pytest -q -ra --tb=short -p no:cacheprovider $phase3Tests
```

Use only `tests/library_work_astra/test_phase3_acceptance5.py` as the pytest
selector for the fourteen new cases. The separate `--execute-launch-probe`
command above is opt-in and never runs through pytest. Companion selectors,
expanded and run separately through guarded `pytest.main` with a fixture log
and unique fixture `--basetemp`, were:

```text
service:   tests/test_source_subscriptions_*.py
dashboard: tests/test_dashboard_sources_*.py
legacy:    tests/test_auto_uoink_poll.py tests/test_phase0_liveness.py tests/test_phase0_podcast_repair.py tests/test_podcast_watch.py tests/test_quiet_notifications.py
adapter:   tests/test_library_adapters.py tests/test_phase0_registry_capture.py
podcast:   tests/test_podcast_durability.py tests/test_podcast_corpus_bridge.py tests/test_podcast_background_jobs.py tests/test_podcast_workflow_truth.py tests/test_podcast_url_validation.py
packaging: tests/test_installer_files_complete.py tests/test_build_guide_accuracy.py
heartbeat: tests/test_heartbeat_semantics.py
extra:     tests/test_phase0_cli.py tests/test_phase0_provenance.py tests/test_phase0_x_full_text.py
```

Local logs, guard runner and receipt checks remain under `_scratch/as5`.
Handoff: AS-5 complete; **NOT ACCEPTED**. Added this report, fourteen acceptance
cases and the opt-in real-child probe. Evidence: original 136/136; final 138
passed/12 failed; companions 362 passed; real live-child false-stop reproduced;
S21 database and ten manifest hashes verified. Files changed: this report and
`tests/library_work_astra/test_phase3_acceptance5.py`. Open work: AS-02a/b,
AS-03a/b/c, C20/C21/C22 and the remaining companion-selector discrepancy.
Production and protected Phase 2 files are unchanged. No commit or merge.
