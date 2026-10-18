**NOT ACCEPTED: AS-01, AS-02, AS-03 and AS-06 remain open. AS-04 and AS-05 are closed on this candidate.**

Run AS-2, codex/Astra independent review under the
[rerun brief](PHASE3-ACCEPTANCE-2-BRIEF-2026-09-08.md),
[first acceptance report](PHASE3-ACCEPTANCE-2026-09-08.md), and contract
`phase3-v1-2026-09-07`. Reviewed HEAD:
`cfc691b8ffc5af466a43bbf7f45137421b048a7a`, including AT-2 and Fable's
`_backend_call` resolution at `25e89e1`, and legacy alignment at `562ac70`.
The worktree was clean before this review. Production code is unchanged.

The original independent suite passes all 103 cases. Twelve new cases expose
remaining defects in the integrated repairs. Passing the original reproductions
does not close the broader repairs specified in AS. The final verdict rests on
these reproducible failures, not on the missing installed-build receipt alone.

| Independently executed group | Observed result | Pytest exit |
|---|---|---|
| Original `tests/library_work_astra/test_phase3_*.py`, strict mode | 103 passed; 1 warning; 15.98 s | 0 |
| Final independent suite, including AS-2 regressions | 103 passed, 12 failed; 4 warnings; 24.78 s; no skips or setup/teardown errors | 1 |
| `tests/test_source_subscriptions_*.py` | 111 passed; 5 warnings; 8.99 s | 0 |
| `tests/test_dashboard_sources_*.py` | 31 passed; 0.21 s | 0 |
| Legacy group from AS commands | 27 passed; 19 warnings; 1.25 s | 0 |
| Adapter/registry group from AS commands | 98 passed; 0.71 s | 0 |
| Podcast group from AS commands | 30 passed; 74 warnings; 2.20 s | 0 |
| Packaging group from AS commands | 6 passed; 0.75 s | 0 |

The six companion groups total **303 passed**, not the brief's reported 313.
These are the exact file groups listed in the first report; I found no supplied
command identifying ten additional cases. Fable should reconcile that count
against its collection list. Eighteen of the independent suite's 103 passes are
harness self-checks; 85 exercise implementation/migration behavior. None of the
twelve new failures is a harness setup failure.

All tests ran on Windows with Python 3.14.6. The independent suite retained its
network, process and database guards. Companion groups ran in separate Python
processes with plugin autoload disabled, profile/temp/output directories under
this worktree's `_scratch/as2-companion-*`, and fixture-only SQLite access. They
imported a byte-identical `server.py` copy with disposable token/log paths;
resource paths used this candidate. Audit guards blocked process launches,
external networking and non-fixture databases. Model imports were blocked;
podcast worker tests used their synthetic transcription injections. No resident
helper, model, port 5179, live index, commit or merge was used.

The first companion run had three isolation errors: one rejected a read-only
SQLite URI within the fixture directory; two rejected Windows asyncio's internal
socket pair. I corrected the wrapper to resolve and confine fixture URIs and
permit loopback socket-pair operations only inside the standard-library
`socketpair` call, still excluding 5179. Full legacy and adapter groups then
passed as recorded above. Those initial failures were not product defects.
Warnings in the successful runs concern existing `datetime.utcnow()` helpers.

The six repairs have the following disposition.

1. **AS-01 remains open: publication presence is still mistaken for validity, and recovery misses an earlier durable stage.**

   The repair adds one service inspection path and production publisher hooks.
   It correctly stops the original partial-upsert, citations and clips-prefix
   fixtures from producing premature work. Podcast completion checks the episode
   linkage, and a stopped attempt with an existing corpus row can invoke the local
   publisher again. Requiring staged publication in the service tests is a valid
   correction to their former bare-success assumptions.

   `SourceSubscriptionService._publication_evidence` at
   `source_subscriptions.py:1601` nevertheless checks file existence and positive
   row counts. It does not parse the sidecar, establish the required provenance,
   validate timing or compare clips with their source citations. The real backend's
   YouTube completion inspection at `server.py:7497` accepts any citation row.
   Four new cases each reach `succeeded` with an outbox despite, respectively,
   malformed sidecar JSON, absent URL provenance plus wrong source type/platform,
   negative/reversed citation times, or a clip whose timing/text contradict its
   citation. These are completion-validation failures with a terminal executor,
   independent of AS-02.

   Recovery has a separate gap at `source_subscriptions.py:3195`: it calls
   `recover_publication` only when a corpus row exists. The new real-publisher
   reproduction interrupts `podcasts.episode_to_corpus` before `upsert_yoink`,
   after valid transcript, corpus and sidecar files exist. With a terminal job,
   reconciliation marks the attempt `failed`/`worker_lost`; it never tries the
   available local publisher under that attempt. The original repair explicitly
   covered files before the item upsert.

   Exact repair: validate readable artifacts and agreeing identity/provenance,
   finite nonnegative ordered source timing, and clips derived from the actual
   evidence. Tie publisher completion to those artifacts. Apply this rule at
   completion, restart and pre-existing linking. Inspect recoverable local stages
   even without a corpus row; after proving executor termination and acquiring
   the capture lock, finish valid local publication under the original start.
   Never create an outbox for invalid or unfinished publication.

   Clips ruling: the contract at lines 554–558 permits missing clips only when
   there is **no timed evidence**. The fixture's unconditional clip check is
   appropriate for its always-timed transcript, but is not a universal rule for
   untimed content. The worker's test `if transcript and not clips` is narrower
   than the contract: a timestamped screenshot is timed evidence even without
   transcript citations. The new screenshot-only case has a real fixture file
   and timestamp, no clips, and still succeeds. Conversely, `if not timed`
   rejects all untimed publications rather than implementing the stated
   exception. Neither predicate implements the complete contract rule.

   The existing `clips.py` builds transcript windows; manufacturing transcript
   text or timing from screenshots is not a repair. Under v1, preserve the timed
   evidence gate and leave unsupported publication incomplete. If the intended
   product behavior is to accept screenshot-only captures without clips, propose
   an explicit contract amendment defining that exception and its evidence
   requirements. That amendment is not present in this candidate; a substantive
   disagreement follows the orchestration dispute route to Ryan.

2. **AS-02 remains open: terminal ownership can still be bypassed.**

   Per-incarnation identities distinguish helper processes, and queued/running
   podcast jobs now prevent the original empty-registry death inference.
   `fail_capture` without a proof preserves an unknown/running attempt. These
   are real improvements, but they cover only part of the required fence.

   `complete_capture` at `source_subscriptions.py:2974` never calls
   `_worker_terminal` on the complete-evidence branch. A new case supplies
   complete artifacts while the real backend reports `unknown`; the ledger
   becomes `succeeded`, releasing active source ownership. The checked-proof
   path also fails: `server.py:7473` accepts `worker_finished` when the thread
   is absent. The new proof case turns an explicitly unknown attempt into
   `failed`. An empty registry has become death evidence again through a
   different method.

   `execute_started` at `source_subscriptions.py:2915` trusts its saved payload
   without re-reading ownership/state. A delayed payload for an already failed
   attempt still schedules the real YouTube backend's worker. The test records
   the scheduled callable without running extraction. Inspection of that worker
   shows no ledger recheck between lock acquisition and `_fetch_metadata` or
   publication. The podcast worker likewise skips acquisition of the manual
   lock whenever `source_start_id` is present, including restored jobs.

   Exact repair: require terminal executor evidence before success or failure
   releases active ownership. Keep publication visible while the attempt remains
   uncertain. Verify a proof against the executor, its incarnation, job/start
   binding and terminal evidence; absence of a local thread is insufficient.
   Atomically claim/revalidate the current start token/state before acquisition,
   recheck after waiting for the lock, and fence publication. Restored podcast
   jobs must obtain verified execution ownership before resuming.

   The original surviving-subprocess requirement also remains unestablished.
   `probe` checks parent incarnation liveness, while `_run_subprocess` does not
   persist child ownership or arrange containment in the reviewed code. Parent
   death releases the parent's file lock; it does not itself prove a yt-dlp or
   ffmpeg child stopped. Fable must supply child identity/containment and the
   disposable installed-process receipt required by the first repair. This run
   did not launch or kill a child to claim that evidence.

3. **AS-03 remains open: failure to obtain the shared lock permits a charged start.**

   `CaptureLock` implements an OS file lock keyed by capture identity, and the
   ordinary standing path obtains it before `mark_started`, which rechecks the
   corpus and consent. The original busy-manual-lock fixture now passes.

   At `server.py:7274–7280`, an `OSError` acquiring that lock becomes
   `lock=None, busy=False`. The new `PermissionError` case reaches `in_flight`,
   charges the ledger and schedules a YouTube worker. Equivalent fallbacks in
   `_ensure_ownership`, `_manual_extraction_ownership` and the manual podcast
   worker proceed with only process-local serialization. The manual YouTube
   wrapper also does not recheck the corpus after waiting, so the standing-first
   ordering has not received the common-dispatcher recheck specified in AS.

   Exact repair: treat every failed shared-lock acquisition as unavailable
   ownership. Standing work releases its unstarted reservation and stays eligible
   without charge; manual work returns a retryable failure or waits within a
   defined bound. Hold verified ownership through publication, including recovery
   and resumed jobs. Recheck canonical corpus identity on both dispatcher paths
   after acquiring the lock, and exercise both orderings on the installed
   disposable candidate. Do not substitute a Python lock after an OS-lock error.

4. **AS-04 is closed on this candidate.**

   `_standing_due_polls` now expires poll leases before due selection, bounded
   to 100 rows. The real tick reproduction observes cleared ownership,
   `poll_timeout` and backoff. The implementation preserves successful revision
   and validators and fences late results. Due-selection exceptions enter the
   tick's failure/heartbeat handling. Service detection and legacy liveness
   suites also pass. No further repair is specified for AS-04.

5. **AS-05 is closed on this candidate.**

   The server selects at most 25 due IDs and claims each immediately before
   its fetch; deadlines use claim time. `detection_pass()` similarly claims
   during iteration. The independent 16-source/eight-seconds-per-fetch case
   passes, along with the ownership race cases. The server's finite batch
   bounds the delay before capture and outbox progress. No further repair is
   specified for AS-05's production tick path.

6. **AS-06 remains open in the podcast publisher's legacy fallback.**

   New publications persist normalized feed URL, GUID and capture key in both
   sidecar and metadata. The original explicit feed/GUID collision fixture
   blocks without charge, and the publisher raises `CorpusIdentityConflict`
   when those stored fields disagree.

   `_check_corpus_identity` at `podcasts.py:992` checks a legacy episode only
   through `metadata_json.episode_id`. It does not query episode rows already
   linked by `yoink_video_id`. The new real-publisher case seeds a corpus row
   with empty legacy metadata and a durable reverse link to a different
   feed/GUID. Publishing the incoming episode overwrites that corpus row and
   links the incoming episode instead of raising. The service's reverse-link
   check does not protect direct publication or recovery.

   Exact repair: use one full-identity check for linking, recovery and
   `episode_to_corpus`, including reverse episode links, and run it before any
   overwrite. Check all available bindings for disagreement; if identity cannot
   be established, expose a blocked identity-verification/conflict state rather
   than treating the shortened ID as proof. Preserve existing content and
   deletion tombstones. Rerun both the original collision test and this actual
   publisher reproduction.

Fable's `_backend_call` resolution is mechanically correct Python binding, but
**is not sound as an unrestricted compatibility rule for asynchronous backends**.
The dependency claim is accurate: these base methods need only existing
`published_video_id`/`kind` members. The behavioral claim is not. The supplied
fake is asynchronous; with its worker reporting `running`, an arbitrary matching
`CompletionProof(..., evidence='unsupported_claim')` passes the inherited base
verification and makes `fail_capture` terminal. The new duck-backend case
reproduces this directly. Having enough attributes to bind a method does not
establish executor termination.

The publication fallback is appropriate for this fake because
`published_video_id` already verifies its durable fixture marker. Its no-op
lock methods model no external dispatcher, and unsupported recovery returning
false is conservative. Those choices do not certify production locking or
recovery. Exact repair for the proof default: return false unless executor
completion is established, letting the service's stopped probe decide; require
an explicit backend override for stronger callback proofs. If the fake needs
such proofs, implement verification against its worker state explicitly. Do not
add five ceremonial methods merely to hide `AttributeError`, and do not retain
the current permissive proof default merely to preserve the 103-pass count.

The two disclosed operational limits do not independently block acceptance.
Old `owner_instance` strings cannot identify a process incarnation and correctly
probe as `unknown`; preserve their ownership/charge until a valid executor report
or separately verified recovery resolves them. They may remain stuck if that
evidence never arrives. Document that upgrade behavior and inspect outstanding
work during cutover; never infer death from the old hostname/data-root string or
reset the ledger to make progress. This ruling does not excuse AS-02's proof
bypasses. Unpruned incarnation files cost one small record per process/data-root
incarnation and are read by token, not scanned to select work. Retention is a
maintenance item, not an acceptance blocker. Any later pruning must preserve
records referenced by unresolved attempts.

| Gate | AS-2 disposition |
|---|---|
| S01 | Migration, import/replay and rollback tests pass. |
| S02 | Default-off, legacy consent boundary and archive alignment pass. |
| S03 | Initial cohort/enrollment cases pass in the service suite. |
| S04–S06 | Consent, revocation, resume and atomic rollback cases pass. |
| S07–S08 | Detection/parser/error/partial coverage cases pass. |
| S09 | Scheduler lease recovery and claim-before-fetch cases pass; AS-04/05 closed. |
| S10–S12 | Allowance, retries, preflight, UTC rollover and clock cases pass. |
| S13–S14 | Existing restart/queue cases pass; new executor/proof/stale-dispatch cases fail AS-02. |
| S15 | Original deduplication cases pass; OS-lock error and legacy publisher collision fail AS-03/06. Both process orderings remain an installed check. |
| S16 | Original publication prefixes pass; validity, clips exception and pre-upsert recovery fail AS-01. |
| S17–S18 | Deterministic handoff/replay and waiting/configuration cases pass once valid publication is supplied. |
| S19 | Service registry, dashboard API, adapter and frozen-schema cases pass. |
| S20 | 31 dashboard API/UI tests pass; no browser receipt was produced here. |
| S21 | Launcher help/syntax checked; controlled helper/browser procedure not executed. |
| S22 | 6 packaging/source checks pass; installation, protected-scope runtime and process-recovery receipts remain required. |

The test alignments reviewed in `25e89e1` correctly replace arbitrary completion
IDs and bare corpus rows with staged evidence, use deterministic podcast corpus
IDs and keep partial S16 publication out of the outbox. The four legacy updates
in `562ac70` correctly encode registry count 81, archive-on-removal and refusal
of ungated polling for a managed feed without network I/O. These changes do not
erase the new failures above.

Reproduce the final independent result from this worktree in PowerShell:

```powershell
$env:PHASE3_REQUIRE_IMPLEMENTATION = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'
$phase3Tests = (Get-ChildItem -LiteralPath 'tests/library_work_astra' -Filter 'test_phase3_*.py').FullName
python -B -m pytest -q -ra --tb=short -p no:cacheprovider $phase3Tests
exit $LASTEXITCODE
```

The twelve added cases are in
[test_phase3_repairs.py](../../tests/library_work_astra/test_phase3_repairs.py):
four `test_as2_s16_production_inspection_rejects_invalid_evidence` variants;
`test_as2_s16_timed_screenshot_does_not_get_the_no_timed_evidence_exception`;
`test_as2_s16_recovery_reuses_valid_files_before_corpus_upsert`;
`test_as2_s13_publication_does_not_release_an_unknown_executor`;
`test_as2_s13_empty_registry_does_not_verify_worker_finished_proof`;
`test_as2_s13_duck_backend_fallback_does_not_certify_a_running_worker`;
`test_as2_s14_terminal_start_payload_cannot_dispatch_again`;
`test_as2_s15_lock_error_keeps_start_uncharged`; and
`test_as2_s15_podcast_publisher_checks_reverse_legacy_episode_link`.
The unchanged `server_parts` helper compiles selected production definitions
into guarded fixture globals; scheduled YouTube threads are recorded, not run.
The two podcast cases call the actual publisher on synthetic local transcripts.

Companion runs used `pytest.main` with `-q -ra --tb=short -p no:cacheprovider`
and a unique `--basetemp` inside the guarded process described above. Selectors
were exactly:

```text
service:   tests/test_source_subscriptions_*.py (expanded and sorted)
dashboard: tests/test_dashboard_sources_*.py (expanded and sorted)
legacy:    tests/test_auto_uoink_poll.py tests/test_phase0_liveness.py tests/test_phase0_podcast_repair.py tests/test_podcast_watch.py tests/test_quiet_notifications.py
adapter:   tests/test_library_adapters.py tests/test_phase0_registry_capture.py
podcast:   tests/test_podcast_durability.py tests/test_podcast_corpus_bridge.py tests/test_podcast_background_jobs.py tests/test_podcast_workflow_truth.py tests/test_podcast_url_validation.py
packaging: tests/test_installer_files_complete.py tests/test_build_guide_accuracy.py
```

S21 remains Fable-owned. After integrating the named repairs and obtaining a
green rerun, use the original local-fixture scenario with these updates: replace
the launcher's fixed `instance_id='s21-disposable'` at line 184 with the real
`server._source_instance_id()` after setting the disposable data root; record
that identity and incarnation-file hash; assert that the canonical capture lock
is held during acquisition/publication and is released after verified settlement;
check normalized feed URL, GUID and capture key in corpus and sidecar provenance.
Keep the real backend/proof path. These launcher changes are instructions for
Fable, not edits made in this review's restricted test-addition scope.

```powershell
python -B tests/library_work_astra/test_phase3_s21.py --execute-s21 --hold-seconds 180
```

The procedure must still use a fresh retained `_scratch/s21-*` database and
byte-identical helper overlay, two ephemeral `127.0.0.1` ports excluding 5179,
and only its explicit local feed/enclosure allowance. Register off, consume
bound consent, establish an empty initial boundary, expose one new GUID, and
capture it through the real scheduler, ledger, podcast queue, publisher and
Phase 2 `prepare_run`. Acquisition remains a placeholder download and one
synthetic transcript cue at 12.5–21.75 seconds; no model/client executes.
Verify one charge, one capture, one outbox and one ready work row, future
eligibility and `waiting_for_client`; replay detection/reconciliation without
duplicates or shelf assignments. The taxonomy/prompt bytes remain pinned:

| Input | SHA-256 |
|---|---|
| `docs/library/taxonomy-v3-2026-09-07.json` | `c3fdb4fb0c3f89c68b06676f7613c75d3a293787d28c32b0a5adb9fa91e4fdf7` |
| `scripts/librarian/prompts/assign.md` | `cd22a3c1819f693bc921033847e21b18dfac6bbac138da6162af3a0244d12f32` |

During the hold, Fable must open the printed disposable dashboard URL and retain
screenshots of the visible unfiled item, source/provenance, waiting-for-client
state and allowance. Match item ID to the receipt and resolve the local episode
link. Retain `receipt.json`, database/hash, corpus/sidecar/transcript files,
helper logs, candidate and launcher hashes, exact command, exit code and browser
receipt. The reviewed, unmodified launcher's SHA-256 is
`b867e478e020c4cddf127d2b1457ec9f5392fb234d13b8420b4405fff91cb2b3`;
its instructed updates will require a new hash. S21 still does not substitute
for S22's installed module/migration/registry, unrelated capture, protected
scope, surviving-process and both manual/standing ordering checks.

Handoff: review complete; verdict NOT ACCEPTED. Files added are this report and
`tests/library_work_astra/test_phase3_repairs.py`; existing tests and production
files are unchanged. Open items for Fable are the four named repairs, the proof
fallback correction, the 303-versus-313 collection discrepancy, any proposed
clips contract amendment, and S20/S21/S22 receipts on the repaired candidate.
Syntax and whitespace checks pass. No commit or merge was made.
