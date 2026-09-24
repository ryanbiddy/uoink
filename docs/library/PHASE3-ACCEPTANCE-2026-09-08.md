**NOT ACCEPTED: AS-01 through AS-06 require repair.**

Run AS, Astra independent review under
[orchestration v1](ORCHESTRATION-V1-2026-09-04.md) and
[the acceptance brief](PHASE3-ACCEPTANCE-BRIEF-2026-09-08.md).
Contract: `phase3-v1-2026-09-07`, with Fable's AM ruling that both YouTube
detectors use Atom. Reviewed candidate HEAD:
`320f47d065579ea477b0022971c94ca4fd9f9fdb`. The results below apply to that
candidate plus this uncommitted test alignment and the named fault hook.
They do not certify a later integrated SHA.

The final independent run reports **90 passed, 13 failed, zero skipped, zero
setup/teardown errors**, in 14.90 seconds (pytest exit 1). Eighteen passing cases are harness self-checks, including
the reference-DDL fixture; they are not implementation acceptance. The remaining
72 passing cases and 13 failures use the shipped implementation/migration.
The failures map to six defects below. One deprecation warning comes from the
existing podcast UTC timestamp helper.

All executed runtime checks used disposable databases under this worktree's
`_scratch`, fake acquisition and clocks, and guards against network, process
launches and non-fixture database access. No helper was imported or started by
the independent server tests: they compile the selected, unchanged class/function
bodies from this candidate's `server.py` into an explicit fixture namespace.
The real podcast publication reproduction does run `podcasts.episode_to_corpus`
on a synthetic transcript and disposable files. No model, resident helper,
port 5179, live index, commit or merge was used. S21 was syntax-checked and its
`--help` entry point checked; its helper procedure was **not executed**.

The brief reports 39 service, 31 dashboard, 38 aligned legacy and 22 adapter/registry
passes, plus passing packaging checks. Those are Fable's reported results on the
integrated candidate, not newly observed results from this review. Fable must
rerun them after integration, including review of the fault hook authored here.

The harness now uses `backend=`, adapter `poll(..., conditional=)` returning
`AdapterResult`/`Observation`, the service's `RequestContext` for source operations,
and Phase 2's own context for taxonomy/run operations. The small `ServiceDriver`
only maps prior test names to public service calls: `claim_poll`/`run_claimed_poll`,
`refresh_source`, `claim_start`, `mark_started`/`execute_started`,
`reconcile_on_startup`, `note_corpus_deleted`, and
`dispatch_classification_outbox`. It adds no liveness, deduplication or publication
checks. Startup import is called explicitly before reconciliation. Status assertions
read `classification.state`. The manual-capture case now exercises the actual
server backend instead of assuming an unimplemented fake lock API. Gate assertions
remain active; no implementation failure is skipped or marked xfail.

The only production-file change is `SourceSubscriptionService(...,
_test_fault_hook=None)` and its `_test_boundary(name)` helper. A missing callback
does nothing; no registry/HTTP argument exposes it. The boundaries are:

| Hook | Actual boundary |
|---|---|
| `after_backend_insert_before_binding` | After `backend.bind` returns, inside the started transaction, before its ledger binding update. |
| `before_started_commit` | After ledger/item/due-time updates, still inside that transaction. |
| `after_started_commit` | After the write context commits, before returning the dispatch payload. |
| `after_outbox_commit` | After the success/item/outbox transaction commits. |
| `after_prepare_run_before_outbox_ack` | After the real Phase 2 call returns, before outbox verification/acknowledgment. |

Callbacks either coordinate test barriers or raise `Crash(BaseException)`.
The two before-commit tests observe rollback through a second connection.
Reopening connections tests process-crash reconciliation; it does not establish
power-loss durability. `Publication` remains fixture evidence, not an invented
service constructor dependency. Its final marker represents the publisher's
completion evidence; the real-podcast reproduction below independently proves
the defect without that synthetic marker.

1. **AS-01: partial publication becomes a successful capture and ready work.**
   `source_subscriptions.py:_reconcile_started_row` accepts any undeleted corpus
   row and calls `complete_capture`. It checks neither publication completion nor
   the files, provenance, citations and clips required by S16. `complete_capture`
   also accepts an arbitrary nonempty video ID without checking those artifacts.
   The item-upsert, citations and clips-prefix fixtures all become `enqueued`
   before their completion evidence exists. More decisively, the real podcast
   publisher is stopped after its corpus upsert and before `insert_citations`:
   citations and clips are both empty, yet restart creates an enqueued outbox and
   a real Phase 2 work row. Four failures belong to this defect.

   Repair: give the production backend a durable publication-inspection/recovery
   contract and use it in both completion and restart. Validate full identity,
   required files/provenance, timed citations/clips and the publisher's completion
   state. With an unknown worker, preserve uncertainty. Once stopped, finish valid
   local publication under the original attempt, or expose a partial-publication
   failure; renewed acquisition needs a new reservation. Insert the outbox only
   after verified publication. Apply the same completeness rule when linking an
   existing corpus row. Keep already published content visible if handoff fails.

   Reproduce all four failing cases with:

   ```powershell
   python -B -m pytest -q -p no:cacheprovider tests/library_work_astra/test_phase3_publication.py -k 'each_publication_prefix or real_podcast_upsert'
   ```

2. **AS-02: worker death is inferred or bypassed, allowing replacement work.**
   `fail_capture` makes a started/uncertain attempt terminal without consulting
   worker state or requiring proof of stopped execution. Both `unknown` and
   `alive` fixture owners become `failed`; another item can then reserve the
   source. Separately, `_ServerCaptureBackend.probe` returns `stopped` when the
   install-derived owner string matches and this process has no capture thread.
   That string is hostname plus data root, not a process identity. The result is
   also `stopped` with a queued or running podcast job, whose worker is not in
   `_source_capture_threads`. Five failures belong to this defect.

   Repair: persist a process identity that distinguishes process incarnations and
   account for the actual podcast job and surviving acquisition subprocesses.
   Require verified terminal execution before releasing active ownership. A
   callback may carry an explicit, checked completion proof from its executor;
   possession of the ledger token alone must not mean the worker stopped. Unknown
   or surviving execution stays uncertain/in flight. Fence replacement owners and
   stale callbacks through acquisition and publication, not only the final ledger
   update. Do not treat an empty in-memory thread dictionary as death evidence.

   ```powershell
   python -B -m pytest -q -p no:cacheprovider tests/library_work_astra/test_phase3_recovery.py::test_s13_surviving_or_unknown_worker_blocks_replacement_after_lease_expiry tests/library_work_astra/test_phase3_integration.py::test_s13_server_probe_does_not_infer_death_from_install_identity
   ```

3. **AS-03: a manual capture does not exclude a charged standing start.**
   Hold the real dispatcher lock used by manual extraction, then call
   `advance_source` with `_ServerCaptureBackend`. The ledger still commits a
   charged start and schedules a YouTube thread. The worker takes `_extract_lock`
   only afterward. That lock is process-local, and the worker does not recheck
   corpus identity after acquiring it. Podcast manual-job adoption likewise
   happens after the standing start/download. One independent case fails before
   any extraction runs.

   Repair: make manual and standing dispatchers share a cross-process lock keyed
   by canonical capture identity. Acquire it before the standing started
   transition, recheck the corpus and consent/owner, and hold it through publication.
   A busy manual owner leaves the observation eligible without a charge; a manual
   completion links without a standing outbox. Exercise both orderings and a
   surviving subprocess on the disposable installed candidate. The fixture case
   proves today's early charge, not an OS-lock implementation.

   ```powershell
   python -B -m pytest -q -p no:cacheprovider tests/library_work_astra/test_phase3_recovery.py::test_s15_concurrent_manual_capture_lock_waits_then_links_without_charge
   ```

4. **AS-04: an expired poll lease is stranded by the server tick.**
   Claim a poll, advance the clock 120,001 ms, and execute the actual scheduler
   definitions. The token remains set indefinitely. `_standing_due_polls` calls
   `claim_due_polls`, whose due query excludes every owned row; unlike
   `detection_pass`, the tick never expires poll leases. `capture_pass` only
   reconciles reservations. One case fails.

   Repair: perform bounded poll-lease reconciliation on every tick before due
   selection. Persist `poll_timeout`, preserve validators and successful revision,
   clear the expired owner and apply backoff. A late result must remain fenced.
   Also ensure errors while claiming cannot bypass the tick's completion/failure
   heartbeat handling.

   ```powershell
   python -B -m pytest -q -p no:cacheprovider tests/library_work_astra/test_phase3_integration.py::test_s09_server_tick_recovers_expired_poll_ownership
   ```

5. **AS-05: serial polling consumes leases before the fetch begins.**
   The tick claims all due polls at once, then fetches serially. With 16 sources
   taking a simulated eight seconds each, the last two valid responses reach
   commit at or after the 120-second lease deadline and fail. No invocation exceeds
   its adapter budget. The service's standalone `detection_pass` also builds the
   complete claims list before iterating it. One case fails.

   Repair: bound each tick's work and acquire each lease immediately before its
   fetch, or claim only a bounded group that can start within its lease. Base
   deadline calculations on the actual claim time; do not renew leases merely to
   cover a backlog. Keep capture and outbox progress independent of a large due
   detection set. Rerun the 16-source case and the two-connection ownership cases.

   ```powershell
   python -B -m pytest -q -p no:cacheprovider tests/library_work_astra/test_phase3_integration.py::test_s09_server_tick_does_not_expire_queued_polls_before_fetch
   ```

6. **AS-06: a shortened podcast-ID collision silently links another identity.**
   Seed a corpus row at the incoming episode's deterministic `episode_<suffix>`
   ID but with a different full feed/GUID identity, then detect the incoming
   episode. `_preexisting_capture` links it as committed. It never compares the
   full identity. This is an adversarial collision/import-corruption fixture,
   not a claim that a natural collision was found. One case fails.

   Repair: persist/derive the full normalized feed URL plus entry ID (or its
   collision-resistant capture key) in publication provenance. Check it before
   linking, resuming or overwriting a shortened corpus ID, including the podcast
   publisher. A mismatch must remain a visible blocked identity conflict, with
   neither charge nor replacement of the existing item. Preserve tombstones.

   ```powershell
   python -B -m pytest -q -p no:cacheprovider tests/library_work_astra/test_phase3_integration.py::test_s15_podcast_short_id_collision_is_visible_and_never_links
   ```

The persisted reservation tests pass: real `BEGIN IMMEDIATE` races permit only
one last-slot reservation;
off wins before start and releases unstarted work atomically; start wins before
off and retains its charge; UTC rollover releases an old-day reservation; failed
attempts keep their slots and stop after three. Queue insertion/binding rolls
back together, stale ledger callbacks leave terminal rows unchanged, and source
consent/token/receipt/release rollback is atomic. These passing cases do not
repair AS-02 or establish production process fencing.

Cross-source standing claims and committed/deleted tombstones pass, including
manual captures that were already complete. The post-commit outbox also passes
real `prepare_run` replay after a crash before acknowledgment, two-dispatcher
replay, video/taxonomy/prompt/source-revision conflicts, and preservation of an
existing frozen manifest. The failure is the publication precondition feeding
that outbox, not the demonstrated deterministic replay behavior.

The adapter edits were reviewed with the scheduler. `podcasts.add_feed` projects
capture off; the linked legacy boolean route refuses consent changes; linked
polls delegate through refresh; archive preserves source history. Managed
`mobile_playlists.poll_playlist` returns through the source refresh route before
yt-dlp listing/taste/enqueue, and registration does not infer capture consent
from `enabled`. Both YouTube adapters use the AM-authorized Atom detector.
The old module-level playlist description still describes pre-Phase-3 enqueue
behavior and should be corrected when Fable repairs that owned surface.
These paths are plausible by inspection; the legacy/adapter reruns remain
required. The production capture boundary still has AS-01/02/03/06.

| Gate | Expected result and evidence on this candidate |
|---|---|
| S01 | Observed pass: shipped 0028 replay/rollback, legacy receipt and cutover hold. |
| S02 | Default off and legacy conversion reviewed; full service/legacy results reported by Fable, rerun required. |
| S03 | Cohort/enrollment covered by Fable's reported service suite; full independent matrix not rerun here. |
| S04–S06 | Observed pass in the independent consent, rollback, revocation and resume fixtures. |
| S07–S08 | Partial/delayed detection has independent coverage; full parser/failure matrix requires Fable's service rerun. |
| S09 | Service due-time races pass; actual server scheduler fails AS-04/05. |
| S10–S12 | Observed independent allowance, charged failures, three-attempt cap, UTC/DST and clock rollback passes; service suite must retain preflight/retry coverage. |
| S13 | Reservation/started-commit restart tests pass; surviving-owner protection fails AS-02. |
| S14 | Injected durable queue rollback and ledger callback fencing pass; production queue/process/publication ownership remains subject to AS-02/03 and installed verification. |
| S15 | Standing deduplication and deletion history pass; manual exclusion and full podcast identity fail AS-03/06. |
| S16 | Fails AS-01, including the actual podcast publisher's interrupted upsert. Outbox-write failure/after-commit replay pass with complete fixture evidence. |
| S17 | Observed pass: actual Phase 2 preparation, replay, collision rejection and frozen-manifest preservation. |
| S18 | `waiting_for_client` observed for complete fixtures. Full waiting/configuration/deleted/pinned/recovery cases require Fable's handoff suite. |
| S19 | Frozen registry input-schema comparison passes. Full HTTP/MCP/adversarial parity needs the service/dashboard/adapter reruns. |
| S20 | Dashboard tests reported passing; no browser receipt observed in AS. |
| S21 | Executable procedure supplied below; not run. |
| S22 | Module entries in `build.ps1` and `installer/uoink.iss` observed; packaging tests reported passing. Installed tree and protected-scope runtime checks still pending. |

Fable must run these commands from the integrated candidate's project root in
PowerShell. The wildcard expansion is intentional: PowerShell does not expand
pytest path globs the way a POSIX shell does. The first group reproduces this
review and must become fully green after repairs.

```powershell
$env:PHASE3_REQUIRE_IMPLEMENTATION = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'
$phase3Tests = (Get-ChildItem -LiteralPath 'tests/library_work_astra' -Filter 'test_phase3_*.py').FullName
python -B -m pytest -q -ra --tb=short -p no:cacheprovider $phase3Tests
```

Run the remaining groups in Fable's disposable test environment with profile/data
paths isolated before importing helper modules. Record each exit code; do not
let a later command mask a failure. The counts above are not promised counts
for a repaired tree.

```powershell
$serviceTests = (Get-ChildItem -LiteralPath 'tests' -Filter 'test_source_subscriptions_*.py').FullName
python -B -m pytest -q -ra -p no:cacheprovider $serviceTests
$dashboardTests = (Get-ChildItem -LiteralPath 'tests' -Filter 'test_dashboard_sources_*.py').FullName
python -B -m pytest -q -ra -p no:cacheprovider $dashboardTests
python -B -m pytest -q -ra -p no:cacheprovider tests/test_auto_uoink_poll.py tests/test_phase0_liveness.py tests/test_phase0_podcast_repair.py tests/test_podcast_watch.py tests/test_quiet_notifications.py
python -B -m pytest -q -ra -p no:cacheprovider tests/test_library_adapters.py tests/test_phase0_registry_capture.py
python -B -m pytest -q -ra -p no:cacheprovider tests/test_podcast_durability.py tests/test_podcast_corpus_bridge.py tests/test_podcast_background_jobs.py tests/test_podcast_workflow_truth.py tests/test_podcast_url_validation.py
python -B -m pytest -q -ra -p no:cacheprovider tests/test_installer_files_complete.py tests/test_build_guide_accuracy.py
git diff --check
```

S21 is implemented as an explicit launcher in
[test_phase3_s21.py](../../tests/library_work_astra/test_phase3_s21.py).
Pytest collection does not execute it. Fable runs it on the reviewed candidate
after inspecting the procedure and closing the defects:

```powershell
python -B tests/library_work_astra/test_phase3_s21.py --execute-s21 --hold-seconds 180
```

The launcher creates a fresh, retained `_scratch/s21-*` directory; no source
database is copied. It loads a byte-identical copy of `server.py` with disposable
token/log/asset paths, points the actual helper at a fresh migrated index, and
serves the actual HTTP handler/dashboard plus a local RSS feed on two ephemeral
`127.0.0.1` ports. It does not call `server.main`, install a watchdog or run the
resident startup path. Socket guards permit only those two ports and reject
5179. Database guards permit only this fixture root. Process launch and model
imports/Anthropic execution are forbidden. The fixture-only private-address
allowance is injected directly into the two address-check functions for the
literal host `127.0.0.1`; other checks remain active. No registry parameter
enables that allowance in production.

Its acquisition injection downloads a small placeholder from the local enclosure
URL. Its transcription injection returns one explicitly synthetic cue,
12.5–21.75 seconds. The preflight installation probes are fixture successes.
The actual podcast queue, transcription worker's surrounding logic, transcript
writer, corpus publisher, citation/clip construction, ledger and Phase 2 service
remain in the path. Receipt counters distinguish one fixture transcription from
zero model calls. This tests the configured pipeline, not ASR quality or live
provider availability.

The procedure imports the approved `taxonomy-v3-2026-09-07` nodes through the real
Phase 2 service and configures the source policy through the operator API. It
pins these candidate bytes and refuses changed input:

| Input | SHA-256 |
|---|---|
| `docs/library/taxonomy-v3-2026-09-07.json` | `c3fdb4fb0c3f89c68b06676f7613c75d3a293787d28c32b0a5adb9fa91e4fdf7` |
| `scripts/librarian/prompts/assign.md` | `cd22a3c1819f693bc921033847e21b18dfac6bbac138da6162af3a0244d12f32` |

The prompt file hash matches the frozen stage 3 run 2 template specified in
[the stage 4 sketch](PHASE2-STAGE4-SKETCH-2026-09-07.md). This procedure uses that
file hash, not its distinct text-mode hash.

The HTTP scenario registers the source off, mints and consumes its bound consent
intent, completes an empty initial boundary, then exposes one new GUID on the
next due poll. Acquisition checks a started row from another connection before
its first side effect. The wrapped real `prepare_run` checks the succeeded ledger,
files and committed item/citations/clips before proceeding. Repeated detection
and reconciliation must leave one capture, one charged ledger row, one outbox,
one run/manifest/ready work row and zero attempts or shelf assignments. Provenance
must say `episode`/`podcast` and preserve the fixture episode URL and cue timing.
Source status must say `future` and `waiting_for_client`.

While the launcher holds the disposable helper open, Fable opens only its printed
dashboard URL in a dedicated browser profile and records screenshots showing the
captured item in the unfiled library view, its source/provenance, and the source's
waiting-for-client/allowance state. Confirm the visible item ID agrees with the
receipt and that the local episode link resolves. Capture the browser receipt
before the hold expires. Do not infer a visible UI pass from the SQL assertions.
The script retains `receipt.json`, `evidence.db` with its SHA-256, corpus/sidecar/
transcript files and helper logs. It closes its HTTP servers on exit. Record
candidate SHA, launcher hash, exact command, exit code and screenshot paths with
that receipt. A runtime error in this unexecuted procedure is unresolved evidence,
not permission to replace the real queue, publisher or `prepare_run` with success
stubs.

S22 still needs a separate installed-build receipt: package/candidate hashes,
loaded module/migration/registry paths, extension/dashboard behavior, unrelated
one-off capture regression, process recovery, and the cross-process/manual
deduplication scenarios. The S21 overlay is not an installed tree. The current
AS ban on port 5179 takes precedence over older verification sketches that used
that default. Use the disposable binding and profile throughout.

Changed files are the source-service fault seam, the independent support,
publication and recovery tests, the new integration reproductions, the S21
launcher and this report. Existing concurrency, migration and harness test files
remain unchanged. Production repairs to the server/adapters are proposed here
for Fable's dispatch; they were outside this worker's edit scope. Fable must
review the new seam, integrate the authorized changes, repair AS-01–AS-06, rerun
the named tests on the final SHA, and return S20/S21/S22 receipts for a new ruling.
