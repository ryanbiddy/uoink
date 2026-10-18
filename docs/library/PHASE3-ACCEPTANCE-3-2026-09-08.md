**NOT ACCEPTED: AS-01, AS-02, AS-03 and AS-06 remain open. AS-04 and AS-05 remain closed.**

Run AS-3, codex/Astra independent review under the
[AS-3 brief](PHASE3-ACCEPTANCE-3-BRIEF-2026-09-08.md),
[AS-2 specifications](PHASE3-ACCEPTANCE-2-2026-09-08.md) and contract
`phase3-v1-2026-09-07`. Reviewed HEAD:
`df9bd9da37eaccac575de162f75c9fc82ee7d0fe`. The worktree was clean before
review. `git log -- source_subscriptions.py server.py podcasts.py` identifies
`d47989990654b11a0babcf97d24f02ff6706a1e3` as their last change; the diff from
that commit to HEAD is empty for all three modules.

All 115 existing independent tests pass, including the twelve AS-2
reproductions. Twelve additional cases reproduce remaining violations of the
specified repairs. The verdict rests on those failures. The missing installed
receipt is a named release condition, not the sole reason for rejection.

| Independently executed group | Observed result | Pytest exit |
|---|---|---|
| Existing `tests/library_work_astra/test_phase3_*.py`, strict mode | 115 passed; 5 warnings; 25.94 s | 0 |
| New AS-3 reproductions alone | 12 failed; 5.24 s | 1 |
| Final independent suite, strict mode | 115 passed, 12 failed; 5 warnings; 24.97 s | 1 |
| `tests/test_source_subscriptions_*.py` | 111 passed; 5 warnings; 9.04 s | 0 |
| `tests/test_dashboard_sources_*.py` | 31 passed; 0.29 s | 0 |
| Legacy group from AS/AS-2 | 27 passed; 19 warnings; 1.78 s | 0 |
| Adapter/registry group from AS/AS-2 | 98 passed; 0.72 s | 0 |
| Podcast group from AS/AS-2 | 30 passed; 74 warnings; 2.23 s | 0 |
| Packaging group from AS/AS-2 | 6 passed; 1.05 s | 0 |

The six companion groups total **303 passed**. The reported 313 remains
unreconciled; neither brief supplies selectors for ten additional cases. The
adapter expectation of 85 registry tools passes on this tree. The AT-3 handoff
test changes correctly require an unknown executor to remain in flight after
publication, then allow completion once it is stopped.

Tests ran on Windows with Python 3.14.6, plugin autoload and bytecode writes
disabled. There were no skips or fixture setup/teardown errors in the final
independent run. Its network, subprocess and fixture-database guards remained
active. The new cases use the real service, actual podcast publisher and clip
builder, and selected unchanged production server definitions. YouTube thread
starts are recorded without executing their workers. The manual case replaces
the wait with a deterministic completion and stops at an instrumented metadata
call before I/O. These are fixture reproductions, not process-containment tests.

Companions ran in separate guarded Python processes with profile, output and
temporary paths under `_scratch/as3-companion-*`. Server-importing groups used a
byte-identical `server.py` overlay with disposable token/log locations and this
checkout's resource paths. Audit guards confined SQLite to fixture paths and
blocked process launches and external networking; model imports were blocked.
The initial adapter run had two failures because the guard did not recognize
Python 3.14's `_fallback_socketpair` name. Allowing only that standard-library
loopback socket-pair operation, still excluding 5179, produced the recorded
98-pass rerun. This was an isolation correction, not a product repair.

Blocked companion attempts were observable: a Windows version probe on server
import, plus a podcast-group DNS attempt and two notification process launches.
The guards stopped them before execution. A diagnostic podcast rerun confirmed
the callers and again passed all 30 tests. This run therefore claims no executed
external network/process activity, not zero attempted calls. No model, resident
helper, port 5179, live index, S21 helper, installation, commit or merge was used.

1. **AS-01 remains open: artifacts and clips can disagree while publication succeeds.**

   AT-3 parses sidecars, validates corpus presence/content, checks source kinds
   and YouTube URL identity, rejects negative/reversed numeric timing, and
   requires clips when indexed timed evidence exists. Recovery now considers
   local stages before a corpus upsert and acquires the shared lock. The actual
   podcast pre-upsert recovery test passes under its original start and charge.
   These parts meet AS-2's repair.

   `_evidence_defect` at `source_subscriptions.py:1771` reduces clip and citation
   text to case-folded word sets. It accepts a clip with one invented word among
   ten, a clip with every source word reversed, and a clip spanning 0–99,999
   seconds that merely overlaps a 12.5–21.75-second citation. All three new cases
   become `succeeded` and create a pending outbox.

   `_ServerCaptureBackend.inspect_publication` at `server.py:7683` compares
   citation counts by kind with sidecar array counts. It does not compare their
   contents. Two more cases retain one row on each side but change the sidecar's
   transcript text or its interval to 100–110 seconds. Both succeed. A sixth
   case removes the citation start and clips while the sidecar still contains
   timed evidence; the `if not timed` return treats this damaged index as the
   untimed exception and succeeds. These failures have a stopped executor, so
   they do not depend on AS-02.

   The threshold also rejects legitimate output. The seventh case passes one
   1,500-character word through the real `clips.build_clips_for_video`; it emits
   two lossless coarse slices of 1,200 and 300 characters with the original
   interval. Their concatenation equals the source text. Publication fails
   because neither slice is a complete word in the citation's word set.

   Exact repair: validate the persisted citation records against the publisher's
   actual artifact projection, including text, timing and provenance, rather
   than counts. Establish the absence of timed evidence from agreeing source
   artifacts and index data; a lost start value is not an untimed source.
   Validate clips against the deterministic output of the existing clip builder
   or an equivalent derivation check respecting its de-overlap rules, ordered
   text, source intervals and links. Recognize its lossless coarse slicing without
   permitting unrelated words or expanded timing. Apply this same rule at
   completion, restart and pre-existing linking. Retain the working local-stage
   recovery and prohibit outbox creation until validation succeeds.

   Reproductions: the six variants of
   `test_as3_s16_publication_requires_artifact_and_clip_agreement` and
   `test_as3_s16_real_coarse_clip_slices_are_valid_derivation`.

2. **AS-02 remains open: one proof label and service-local dispatch state still bypass ownership.**

   AT-3 correctly makes base `verify_proof` return `False`, retains the four
   other `_backend_call` defaults, requires terminal evidence before complete
   publication releases ownership, and rejects absent-thread
   `worker_finished` proofs. A terminal start payload no longer dispatches.
   The YouTube worker rechecks ledger state after obtaining its lock. Restored
   podcast jobs now attempt shared-lock acquisition and recheck the start.

   The production `executor_returned` proof branch at `server.py:7663` still
   accepts an empty registry without evidence that an executor returned. The
   new case uses the real current incarnation and an explicitly `unknown`
   probe, supplies only that proof label and binding, and changes the ledger to
   `failed`. Renaming the evidence does not establish termination.

   `claim_execution` at `source_subscriptions.py:3142` only reads the row;
   `execute_started` at line 3166 records dispatch in a service-local set.
   Passing the same active payload through two service instances on separate
   database connections schedules two real-backend worker callables. Both
   return `in_flight` for one ledger start. The recorded launches are the
   reproduction; no extraction worker was run.

   Exact repair: verify synchronous completion against an observed invocation
   and its return, bound to the start, token and incarnation. An arbitrary
   `executor_returned` label must fail verification. Make the execution claim
   atomic and shared across service instances, with executor ownership checked
   before acquisition, after lock waits and before publisher writes. Replaying
   an active start must not schedule a second executor. Recovery must distinguish
   an unexecuted intent from an already executing or uncertain attempt; it must
   not introduce another uncharged invocation under the same start.

   The earlier surviving-child requirement is also unresolved. `probe` at
   `server.py:7619` treats a dead parent incarnation as stopped, while
   `_run_subprocess` at line 2752 persists no child ownership and establishes no
   child containment. Parent lock release does not prove yt-dlp/ffmpeg stopped.
   The new worker code still calls `_run_extraction` or `episode_to_corpus`
   before the final ledger fence; that fence alone cannot prevent stale writes.
   Complete AS-2's executor/child fencing repair and supply the disposable
   process-recovery receipt. Neither supplied receipt exercises parent death
   with a surviving child. This is an inspection finding carried forward, not
   a claim that AS-3 launched or killed such a process.

   Reproductions: `test_as3_s13_empty_registry_does_not_verify_executor_returned`
   and `test_as3_s14_two_service_instances_cannot_dispatch_one_start_twice`.

3. **AS-03 remains open: the manual corpus recheck does not change dispatch.**

   The OS-lock error fallbacks have been removed from standing acquisition,
   `_ensure_ownership`, the manual wrapper and manual podcast acquisition.
   Standing lock failure leaves the reservation unstarted and uncharged; manual
   failures return/requeue a failure or use the declared 900-second shared-lock
   wait. The existing lock-error reproduction passes.

   `_manual_extraction_ownership` at `server.py:7120` now sets
   `already_captured`, but no caller consumes it. Its log declares every such
   request a deliberate re-extraction. In the new case, standing publication
   completes during the manual wait; the actual `/extract` handler at line
   15197 obtains the lock, sees that corpus row, and still calls
   `_fetch_metadata`. The test records that duplicate acquisition boundary
   without performing it.

   Exact repair: consume the post-lock completeness/identity result on manual
   dispatcher paths. A request waiting behind a successful capture must reuse
   its completed result; an identity conflict must block before overwrite.
   Preserve any separately established explicit refresh semantics, but do not
   infer a fresh re-extraction request merely from having waited. Verify both
   manual-first and standing-first orderings, including podcast work, with one
   acquisition/publication and the correct standing charge/outbox behavior.

   Reproduction: `test_as3_s15_manual_waiter_reuses_standing_completion`.

4. **AS-06 remains open: a correct capture key hides contradictory partial provenance.**

   The service and podcast publisher now share `podcast_identity_conflict` at
   `source_subscriptions.py:988`. The reverse legacy episode-link reproduction
   passes, and an entirely unverifiable row is rejected. The publisher calls
   the shared check before writing files or upserting content.

   The check compares stored feed URL and GUID only when both are strings.
   With an agreeing capture key, a wrong feed URL alone or a wrong GUID alone
   is ignored. Each new real-publisher case seeds one such contradictory row;
   `episode_to_corpus` returns without raising and overwrites its content.
   This violates AS-2's requirement to check all available bindings.

   Exact repair: compare every available feed URL, GUID, capture key and
   episode binding independently. Incomplete metadata can lack proof, but a
   present contradictory field cannot be discarded because its partner is
   absent. Require an affirmative full-identity binding, reject disagreement
   before any write, and preserve the existing row/files and deletion history.
   Keep the shared service/publisher path and rerun the original collision,
   reverse-link and both new partial-provenance cases.

   Reproductions: both variants of
   `test_as3_s15_podcast_publisher_checks_each_available_identity_field`.

AS-04 and AS-05 remain closed: per-tick poll-lease recovery, bounded due
selection and claim-before-fetch continue to pass. This review specifies no
additional repair for either.

The worker's three disclosed questions have these rulings:

| Question | AS-3 ruling |
|---|---|
| Is 90% cited-word overlap acceptable for coarse clips? | **No.** It admits invented/reordered text and fails the actual mid-word slicing it was intended to tolerate. Use exact derivation as specified under AS-01. |
| May the manual corpus recheck be informational? | **No for a request waiting behind concurrent capture.** The recheck must prevent that duplicate dispatch. An independently established explicit refresh is a separate user action; the wrapper cannot assume it. See AS-03. |
| May a caption-less video with timed screenshots consume three starts before blocking? | **The bounded publication-failure path is permitted under v1 and does not independently block acceptance.** Timed screenshots still require clips; no transcript/timing may be invented and no success/outbox may be reported. A real failed start stays charged; a renewed acquisition needs a new row, verified termination, the 15/60-minute retry delays, source cadence and daily capacity. Stop after three actual starts and preserve counts across off/on. A known terminal unsupported/private/deleted item must still block immediately under the contract. Earlier termination of a deterministically unpublishable capture is allowed. This ruling derives from the current failure path and passing retry tests; AS-3 did not acquire a real caption-less video. |

The S21 evidence establishes the automated fixture outcome but does not close
all of S20–S22. I read both receipt documents and the retained JSON, inspected
both screenshots, and verified all seven files in
[SHA256SUMS](proof/s21-2026-09-08/SHA256SUMS). The AT-3 receipt's four input
hashes match this worktree byte for byte: `server.py`, `source_subscriptions.py`,
taxonomy v3 and `assign.md`.

The [AT-3 S21 JSON](proof/s21-2026-09-08/receipt-at3-candidate-d479899.json)
records one download, one synthetic transcript, one charged succeeded start,
one committed future-eligible episode, its 12.5–21.75-second clip, an unfiled
item, and one Phase 2 prepare observation after commit. It reports
`waiting_for_client`, zero model calls and no forbidden attempts. The launcher
asserts one ready work row and replay without another start/run. I credit this
as reported automated integrated-capture evidence on the matching backend
bytes. I did not rerun its helper.

The screenshots establish a historical unfiled podcast card and an on-source
with 1/10 starts and 0/25 enrollment. They do not show the complete S20 consent
scenario matrix, browser-visible waiting-for-client/provenance detail, or a
browser rerun on AT-3. The claim that the dashboard is unchanged needs a
narrower scope: between `61eeb07` and `d479899`, its HTML gained 708 lines of
Phase 5 activity UI. The earlier Sources screenshot is useful evidence for
that surface, but it cannot certify the later full Library page.

AS-2 also instructed S21 to use the actual incarnation, assert capture-lock
ownership during acquisition/publication and after settlement, and verify
feed/GUID/capture-key provenance. The current launcher still uses
`instance_id='s21-disposable'` at line 195 and contains no such lock assertions.
Its existing provenance assertions cover type/platform and episode URL, not
the full identity fields. The receipt contains no incarnation-file or launcher
hash. The recorded database hash cannot be independently checked here: the
database, corpus/sidecar/transcript and logs are not in the supplied proof
directory. Their referenced scratch paths belong to another checkout, which
this review did not access. The prior WhisperX availability-probe accounting
repair remains appropriate; it does not supply these missing observations.

The [S22 staged-tree receipt](PHASE3-S22-RECEIPT-2026-09-08.md) is useful
documentary evidence for the production copy list, staged module imports,
migration 0028 and a real stdio session in a disposable profile. Its stated
limitations are material: no Inno installation, embedded interpreter, bundled
site-packages or upgrade path was exercised; the stdio session used the user's
Python packages. The staging tree was removed, and no independently rehashable
S22 tree or raw transcript is supplied here. I credit the described staged
exercise without relabeling it an installed-build pass. The reported empty
index substitution is the separately assigned Phase 4 D7 defect; this report
does not close it or add a new Phase 3 repair for it.

| Gate | AS-3 disposition against the required observation |
|---|---|
| S01 migration/replay | Existing migration/import/rollback tests pass. |
| S02 default off/legacy conversion | Consent-boundary and legacy-alignment tests pass. |
| S03 initial cohort | Bounded cohort, pending/empty enrollment and coverage fixtures pass. |
| S04 durable consent | Off/on/restart and receipt persistence fixtures pass. |
| S05 revocation race | Both start/off transaction orderings pass. |
| S06 resume gap | Metadata-only gap and future eligibility fixtures pass. |
| S07 independent detection | Durable observations, repeated identities and partial batch fixtures pass. |
| S08 failure/coverage | Parser, timeout, error and validator preservation fixtures pass. |
| S09 due-time concurrency | Per-tick lease recovery and claim-before-fetch pass; AS-04/05 closed. |
| S10 daily allowance | Atomic reservations and per-source cap fixtures pass. |
| S11 failure/retry accounting | Preflight release, charged failures, retry delays and exhaustion fixtures pass. |
| S12 UTC/clock | Rollover and clock-regression fixtures pass. |
| S13 restart ownership | Earlier reproductions pass; `executor_returned` bypass fails AS-02. Surviving-child proof remains owed. |
| S14 queue/fencing | Earlier transaction and stale-payload tests pass; two-instance replay schedules twice, failing AS-02. |
| S15 deduplication/identity | Lock-error and reverse-link repairs pass; waiting-manual and partial-provenance cases fail AS-03/06. |
| S16 publication | Prefix/recovery tests pass; six invalid publications succeed and valid coarse clips fail, leaving AS-01 open. |
| S17 Phase 2 handoff | Existing deterministic handoff/replay tests pass with valid publication. Invalid evidence reaching an outbox remains AS-01. |
| S18 waiting state | Configuration/waiting fixtures pass; S21 JSON reports waiting-for-client without a model. |
| S19 registry parity | Existing service/schema/adapter tests pass, including the current registry count. |
| S20 real consent UI | 31 API/static-UI tests pass and historical screenshots show two states. Full browser matrix remains C20. |
| S21 controlled capture | Automated fixture outcome supported on matching AT-3 bytes. Updated ownership/provenance and browser receipt remain C21. |
| S22 installed/protected scope | Six source packaging checks pass; staging receipt adds limited runtime evidence. Actual installed qualification remains C22. |

After the four code repairs pass a new independent run, these named evidence
conditions remain before an unconditional installed-release acceptance:

- **C20 — consent UI:** run the S20 browser matrix on the repaired disposable
  candidate: default off, pending and actual enrollment, exhausted allowance,
  refresh errors, off with in-flight work, lost mutation response, stale
  confirmation and restart. Record matching persisted state and browser state.
- **C21 — integrated receipt:** update the S21 launcher as AS-2 specified, run it
  with the real incarnation and backend/proof path, assert lock ownership and
  full feed/GUID/capture-key agreement, and repeat the browser observations on
  the same candidate. Retain candidate/launcher hashes, exact command and exit,
  database plus hash, artifacts and logs within the supplied proof package.
  Include item identity, resolved episode link, provenance and waiting state.
- **C22 — installed build:** Ryan/Fable must supply a disposable Windows
  installation receipt for the actual Inno package, with package/candidate
  hashes, bundled interpreter and dependency versions, installed module paths,
  migration 0028/upgrade replay and registry schemas. Exercise unrelated
  one-off capture, both manual/standing orderings, and parent termination with
  a surviving acquisition child or demonstrated child containment. Record
  unchanged protected Phase 2 inputs/state and instrumentation proving no
  watcher model/client spawn or resident-port/live-index access. A source-only
  copy with host Python cannot satisfy this condition.

C22 is a named release condition; its absence alone would permit an
`ACCEPTED WITH CONDITIONS` ruling after the code and other evidence are sound.
It does not excuse the current reproducing failures or turn this verdict into
conditional acceptance. Child-ownership implementation remains part of AS-02,
with the installed experiment as its required validation.

All twelve added cases are in
[test_phase3_acceptance3.py](../../tests/library_work_astra/test_phase3_acceptance3.py).
Reproduce the final independent result from this worktree in PowerShell:

```powershell
$env:PHASE3_REQUIRE_IMPLEMENTATION = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
$phase3Tests = (Get-ChildItem -LiteralPath 'tests/library_work_astra' -Filter 'test_phase3_*.py').FullName
python -B -m pytest -q -ra --tb=short -p no:cacheprovider $phase3Tests
exit $LASTEXITCODE
```

Companion selectors were exactly those recorded in AS-2, each through
`pytest.main` with `-q -ra --tb=short -p no:cacheprovider` and a unique fixture
`--basetemp` in the guarded process described above:

```text
service:   tests/test_source_subscriptions_*.py (expanded and sorted)
dashboard: tests/test_dashboard_sources_*.py (expanded and sorted)
legacy:    tests/test_auto_uoink_poll.py tests/test_phase0_liveness.py tests/test_phase0_podcast_repair.py tests/test_podcast_watch.py tests/test_quiet_notifications.py
adapter:   tests/test_library_adapters.py tests/test_phase0_registry_capture.py
podcast:   tests/test_podcast_durability.py tests/test_podcast_corpus_bridge.py tests/test_podcast_background_jobs.py tests/test_podcast_workflow_truth.py tests/test_podcast_url_validation.py
packaging: tests/test_installer_files_complete.py tests/test_build_guide_accuracy.py
```

Handoff: AS-3 review complete; **NOT ACCEPTED**. Added this report and twelve
reproductions in one new test file; existing tests and production files are
unchanged. Evidence: final strict suite 115 passed/12 failed, companions 303
passed, seven S21 manifest hashes verified. Open work: AS-01/02/03/06 repairs,
C20/C21/C22 receipts, and the 303-versus-313 collection reconciliation. Test
syntax, report links, table structure, code fences and whitespace checks pass.
No commit or merge was made.
