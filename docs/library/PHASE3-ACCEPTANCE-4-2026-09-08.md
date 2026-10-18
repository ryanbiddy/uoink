**NOT ACCEPTED: AS-02 and AS-03 remain open with six reproducing failures.
AS-01 and AS-06 are closed. AS-04 and AS-05 remain closed.**

Run AS-4, codex/Astra independent acceptance review under the
[fourth-round brief](PHASE3-ACCEPTANCE-4-BRIEF-2026-09-08.md),
[AS-3 specifications](PHASE3-ACCEPTANCE-3-2026-09-08.md) and contract
`phase3-v1-2026-09-07`. Reviewed HEAD:
`5cd87a8e5cc6e8e0d923961099a538c71de44456`. The worktree was initially clean.
`git diff 0bb97c8 HEAD -- server.py source_subscriptions.py podcasts.py` is
empty: this review tests the integrated AT-4 implementation.

The original strict suite passes all 127 cases, including all twelve AS-3
reproductions. Nine additional cases check ownership, manual waiting and the
two disclosures. Three pass; six expose remaining violations of the requested
repairs. The rejection rests on these failures, independently of the missing
browser and installed-build receipts.

| Independently executed group | Observed result | Pytest exit |
|---|---|---|
| Original `tests/library_work_astra/test_phase3_*.py`, strict mode | 127 passed; 5 warnings; 26.16 s | 0 |
| First six AS-4 reproductions alone | 6 failed; 3.57 s | 1 |
| Final strict suite, including nine AS-4 cases | 130 passed, 6 failed; 6 warnings; 29.37 s | 1 |
| `tests/test_source_subscriptions_*.py` | 111 passed; 5 warnings; 10.60 s | 0 |
| `tests/test_dashboard_sources_*.py` | 31 passed; 0.47 s | 0 |
| Legacy group | 27 passed; 19 warnings; 2.01 s | 0 |
| Adapter/registry group | 98 passed; 1.05 s | 0 |
| Podcast group | 30 passed; 74 warnings; 2.95 s | 0 |
| Packaging group | 6 passed; 1.37 s | 0 |
| `tests/test_heartbeat_semantics.py` | 10 passed; 0.13 s | 0 |

The seven companion groups total **313 passed**. The earlier discrepancy is
resolved: AS-3's 303 plus the ten heartbeat cases equals 313. The current brief
and AT-4 commit message report 365 without selectors for the additional 52;
that larger count is not independently established here. It is an evidence
accounting question, not a reason for rejection. The 85-tool registry assertion
passes. AT-4's fixture change uses the real clip builder instead of a manually
constructed podcast link; the legacy podcast-watch change first verifies that
an unclaimed invocation does nothing, then claims before running. Both align
with the repaired contracts.

Tests ran on Windows with Python 3.14.6, plugin autoload and bytecode writes
disabled. Final runs had no skips or fixture setup/teardown errors. The original
127 includes harness self-checks; it is not 127 installed-system observations.
Companion groups ran in separate Python processes with disposable profiles,
output directories and pytest temporary directories under this worktree's
`_scratch/as4-companion-*`. Server-importing groups used byte-identical
`server.py` overlays for token/log paths and this checkout's resource paths.
Audit guards blocked external networking, product child-process launches,
model-runtime imports, non-fixture SQLite access and non-fixture file writes.
Only the standard-library loopback socket-pair operation was allowed, excluding
5179.

The first guard setup rejected pytest's default null-device log; an explicit
fixture log path corrected that. An initial legacy run rejected a fixture
`file:///` SQLite URI; decoding it before the fixture-path check corrected that
isolation error. Final server imports attempted a Windows subprocess probe and
a WhisperX availability import; the guards blocked both. The podcast group
also attempted DNS and two subprocess launches, all blocked. These are passing
guarded runs, not claims of zero attempted calls. No model, resident helper,
port 5179 or live index was used. Neither receipt launcher was executed in AS-4.

**AS-01 is closed against the AS-3 specification.**
`sidecar_evidence_projection` and `citation_projection_defect` compare ordered
records, text and timing; the common publication check also validates identity
and provenance. `clip_derivation_defect` uses the actual builder's `merge_cues`
and item-link derivation. It rejects invented/reordered text and expanded
intervals while accepting the real builder's lossless coarse slices. Missing
citation starts cannot pass as untimed when the artifact retains timing.
Completion, restart and linking share `_publication_evidence`. All seven AS-3
publication cases and the earlier local-stage recovery cases pass. The added
recovery observation also confirms a real podcast publication under the capture
lock, with one original start and one outbox row.

**AS-02 remains open: child termination is not a prerequisite on every path.**
The observed-invocation repair closes the empty-registry
`executor_returned` bypass. The persisted O_EXCL claim prevents the AS-3
two-service replay from scheduling a second worker. YouTube checks the claim
after its lock wait and before extraction; podcast execution and its publisher
also check it. Those repairs pass their original reproductions.

Three new settlement cases still fail:

- `test_as4_s13_terminal_job_does_not_override_child_liveness[alive]` and
  `[unknown]`: `probe` at `server.py:8149` returns `stopped` for a terminal job
  before consulting children. The `job_terminal` proof also returns true.
  `fail_capture` changes the ledger to `failed` for both child states.
- `test_as4_s13_synchronous_return_does_not_prove_unknown_child_stopped`:
  a real `backend.run` invocation returns synchronously, but child liveness is
  `unknown`. `executor_returned` accepts anything other than `alive`, and the
  synchronous probe branch also lacks an affirmative child-stop requirement.
  The ledger becomes `failed` instead of retaining uncertain ownership.

Exact repair: make child status a common prerequisite for all terminal probe
and proof branches, including `worker_finished`, `job_terminal` and
`executor_returned`. A live child must prevent terminal settlement; unknown
child state must retain uncertain ownership. Keep claim and child records until
termination is established. Neither a job flag nor a parent callback overrides
that requirement. Preserve the working invocation/token/incarnation checks.

A fourth case exposes the child-registration crash window:
`test_as4_s13_child_spawn_before_record_is_not_stopped` executes the unchanged
`_run_subprocess` body at `server.py:3096` with a synthetic Popen boundary.
It models parent death after the child exists but before `record_child_start`
persists it. After the parent is reported dead, the production probe sees
`children='none'` and returns `stopped`. The real child was not launched by this
test; the reproduction establishes the ordering and resulting probe decision.
Inspection also finds that record-write errors are logged and ignored in
`record_child_start` and its caller.

Exact repair: persist an unresolved child-launch intent before spawning and
retain uncertainty until it is resolved, or establish OS child containment
before an uncontrolled child can survive its parent. A crash or write failure
between launch and registration must never become evidence of no children.
Distinguish missing, damaged and unresolved ownership records from verified
absence. Add real-process validation through `_run_subprocess`, including this
boundary and registration failure, while retaining the supplied successful
post-registration scenario. This is the AS-2/AS-3 surviving-child requirement.

**AS-03 remains open: cleanup and the first manual wait are incomplete.**
AT-4 callers now consume the manual ownership result, and the AS-3 test that
completes standing work during the OS-lock wait passes. Two other paths fail:

- `test_as4_s15_off_after_lock_releases_dispatcher_ownership`: turn consent off
  after the actual backend obtains its capture lock but before the started
  transition. The reservation correctly becomes uncharged `released` and no
  worker launches, yet the backend still owns the capture lock and
  `_extract_lock` remains locked. `SourceSubscriptionService` defines
  `_release_execution` twice: the lock-release method at line 3308 is shadowed
  by the claim-file cleanup method at line 3619. `_advance_source` therefore
  calls the wrong cleanup in its `finally` block. This can block later manual
  and standing YouTube work for the process lifetime.
- `test_as4_s15_manual_wait_on_process_lock_reuses_completion`: standing
  publication completes while the manual request waits on `_extract_lock`.
  `_manual_extraction_ownership` reads `existed_before` only after that wait,
  misclassifies the result as pre-existing deliberate re-extraction, and
  returns `reused=None`, `completed_while_waiting=False`. The consuming
  dispatcher consequently follows its acquisition path. The new test models
  the first lock boundary; the passing AS-3 case covers the second.

Exact repair: give capture-lock release and execution-claim cleanup distinct
methods and audit their callers. Release actual dispatcher ownership on
unstarted or verified-terminal exits, including consent rejection, synchronous
failure and claim-store failure before invocation. Preserve ownership for
uncertain or surviving execution.
Establish the manual request's prior state before either lock wait, then consume
the post-lock completeness/identity result. Completion during either wait must
reuse the capture. Keep a separately established explicit refresh action and
verify both manual/standing orderings, including podcast work. Do not equate
mere corpus-row presence with complete publication.

**AS-06 is closed against the AS-3 specification.**
`podcast_identity_conflict` at `source_subscriptions.py:1124` checks available
feed URL and GUID fields independently of each other and of an agreeing capture
key. It retains affirmative full-identity binding and the shared
service/publisher check, including episode provenance and reverse legacy links.
Both partial-provenance reproductions and the earlier collision and reverse-link
cases pass without overwriting the conflicting row. AS-04/05 remain closed;
poll-lease recovery, bounded selection and claim-before-fetch still pass.

The two disclosures have these rulings:

| Disclosure | AS-4 ruling |
|---|---|
| Local recovery publishes under the capture lock without taking an execution claim. | **Permitted for local publication after verified executor termination.** The contract preserves the original start and charge when completing validated local output. No new acquisition/transcription is allowed under this exception. `test_as4_s16_local_recovery_uses_capture_lock_without_execution_claim` passes with the actual podcast publisher, lock held, no claim, one publication and one outbox. This ruling does not excuse the false termination decisions in AS-02. |
| The ledger/claim-file gap can leave an unexecuted intent uncertain. | **Permitted conservative behavior, with a correction to the disclosure.** The two variants of `test_as4_s13_unclaimed_intent_keeps_charge_without_redispatch` pass: a current owner with no claim stays uncertain; a proven-dead owner with no child evidence becomes failed. Both retain the original charged start/day/slot and dispatch nothing. The contract does not require an atomic filesystem/ledger transaction or refund this started intent. Repair the child-evidence gap above before relying on absence of child records as proof. |

The [AT-4 S21 receipt](proof/s21-2026-09-08/receipt-at4-candidate-0bb97c8.json)
supports the reported automated fixture outcome: one download, one synthetic
transcript, one charged success, a future-eligible committed episode, its
12.5–21.75-second clip, one prepare observation after commit and
`waiting_for_client`, with zero reported model calls or forbidden attempts.
Its four input hashes match this checkout byte for byte. All eight entries in
[SHA256SUMS](proof/s21-2026-09-08/SHA256SUMS) also match. I inspected both
screenshots: they show the historical unfiled podcast card and an on-source
with 1/10 starts and 0/25 enrollment. They do not establish the full S20 matrix
or a browser rerun on AT-4.

The recorded evidence database, artifacts and logs remain outside the supplied
proof package. Their scratch paths point to another checkout, which this review
did not access. The rerun used the old fixed `s21-disposable` instance and had
no ownership observations. It cannot close those AS-3 requirements by itself.

AS-4 extends [the S21 launcher](../../tests/library_work_astra/test_phase3_s21.py)
to use the real incarnation and inspect its persisted record; assert claim
ownership and OS-lock exclusivity at download, transcription and publication;
assert claim cleanup and lock availability after settlement; and compare
feed/GUID/capture-key/episode bindings across the ledger, source item, episode,
metadata and sidecar. It records those observations, launcher/publisher input
hashes, command, interpreter, optional candidate SHA and retained artifact
hashes. The publisher wrapper observes and delegates to the original function.
Syntax and collection checks pass. These new runtime assertions remain for
Fable to execute; AS-4 does not claim an updated S21 pass.

The [process-recovery receipt](proof/procrec-2026-09-08/receipt.json) adds useful,
narrow S13 evidence. It records a real parent and child alive, a dead parent with
a surviving child and `probe='running'`, then both dead and `probe='stopped'`.
I inspected [its launcher](../../tests/library_work_astra/process_recovery_receipt.py):
it explicitly calls `subprocess.Popen`, then `record_child_start`, and compiles
the production backend probe with fixture globals. It does not exercise
`_run_subprocess`, a real subscription ledger/restart, a terminal job with a
surviving child, or death before child registration. Thus it validates the
registered-child branch without covering the four new AS-02 failures. The JSON
contains no candidate or launcher hash; the accompanying receipt document pins
the run to `0bb97c8`. It is supplied evidence, not an AS-4 rerun or an
installed-process certification.

The [S22 staged-tree receipt](PHASE3-S22-RECEIPT-2026-09-08.md) remains useful
evidence for the production copy list, staged imports, migration 0028 and the
described stdio session. It explicitly excludes the Inno installation, embedded
interpreter, bundled dependencies and upgrade path. Its staging tree was removed.
Six independently passing packaging checks do not supply that missing runtime
qualification. The historical empty-index finding belongs to Phase 4; this
report makes no new ruling on it.

| Gate | AS-4 disposition |
|---|---|
| S01–S12 | Existing migration, consent, detection, allowance, retry and clock fixtures pass; AS-04/05 remain closed. |
| S13 restart ownership | Original cases pass and the process receipt supports registered-child liveness; four new child-settlement/registration cases fail AS-02. |
| S14 queue/fencing | Original two-service replay and stale-payload cases pass; unsafe child termination still prevents closing the ownership guarantee. |
| S15 deduplication/identity | AS-06 closes; two cleanup/manual-wait cases leave AS-03 open. |
| S16 publication | Artifact/clip derivation and local recovery pass; AS-01 closes. Recovery still requires truthful terminal evidence. |
| S17–S19 | Handoff, waiting-state and service/adapter/registry fixtures pass. |
| S20 consent UI | 31 API/static-UI cases and historical screenshots support partial coverage; C20 remains. |
| S21 integrated capture | AT-4 automated receipt credited; updated launcher execution, retained artifacts and matching browser observations remain C21. |
| S22 installed/protected scope | Packaging tests and limited staged receipt credited; actual installed qualification remains C22. |

After AS-02/03 are repaired, the AS-3 evidence conditions remain:

- **C20:** run the disposable candidate's browser matrix for default off,
  pending/actual enrollment, exhausted allowance, refresh errors, off with
  in-flight work, lost mutation response, stale confirmation and restart.
  Match browser state to persisted state.
- **C21:** Fable reruns the extended launcher on the repaired candidate and
  repeats browser observations for identity, episode link, provenance, unfiled
  status and waiting-for-client. Retain candidate/launcher hashes, exact command
  and exit, evidence database, artifacts, incarnation/ownership records and logs
  in the supplied proof package. Set `$env:S21_CANDIDATE_SHA = git rev-parse HEAD`
  before `python -B tests/library_work_astra/test_phase3_s21.py --execute-s21 --hold-seconds 180`.
- **C22:** Ryan/Fable supplies the actual disposable Windows Inno installation
  receipt, including package/candidate hashes, bundled interpreter/dependencies,
  installed paths, migration/upgrade replay, registry schemas, unrelated one-off
  capture, both manual/standing orderings and process recovery through the real
  launch path. Record protected Phase 2 input/state preservation and isolation
  from models, the resident helper/port and the live index.

The reproduction file is
[test_phase3_acceptance4.py](../../tests/library_work_astra/test_phase3_acceptance4.py).
Run from this worktree in PowerShell:

```powershell
$env:PHASE3_REQUIRE_IMPLEMENTATION = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
$phase3Tests = (Get-ChildItem -LiteralPath 'tests/library_work_astra' -Filter 'test_phase3_*.py').FullName
python -B -m pytest -q -ra --tb=short -p no:cacheprovider $phase3Tests
```

Companion selectors, each expanded where needed and run through guarded
`pytest.main` with `-q -ra --tb=short -p no:cacheprovider`, a fixture log path
and a unique fixture `--basetemp`:

```text
service:   tests/test_source_subscriptions_*.py
dashboard: tests/test_dashboard_sources_*.py
legacy:    tests/test_auto_uoink_poll.py tests/test_phase0_liveness.py tests/test_phase0_podcast_repair.py tests/test_podcast_watch.py tests/test_quiet_notifications.py
adapter:   tests/test_library_adapters.py tests/test_phase0_registry_capture.py
podcast:   tests/test_podcast_durability.py tests/test_podcast_corpus_bridge.py tests/test_podcast_background_jobs.py tests/test_podcast_workflow_truth.py tests/test_podcast_url_validation.py
packaging: tests/test_installer_files_complete.py tests/test_build_guide_accuracy.py
heartbeat: tests/test_heartbeat_semantics.py
```

Handoff: AS-4 complete; **NOT ACCEPTED**. Added this report and nine acceptance
cases; extended S21 ownership/provenance evidence. Evidence: original 127/127,
final 130 passed/6 failed, companions 313 passed, all eight S21 manifest entries
verified. Files changed: this report, `test_phase3_acceptance4.py` and
`test_phase3_s21.py`. Open work: AS-02/03 repairs, C20/C21/C22 receipts and
selectors explaining the reported additional 52 companion cases. Production
files and protected Phase 2 surfaces were not changed. No commit or merge.
