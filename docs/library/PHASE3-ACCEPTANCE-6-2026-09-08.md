**PHASE 3 NOT ACCEPTED. AS-02b remains open with four reproductions of false
child-absence evidence. AS-02a and AS-03a/b/c close for the reviewed repairs.
C20, the remaining C21 evidence, and the mandatory installed Inno receipt C22
are still required.**

Run AS-6, codex independent review of AT-6 against the
[AS-5 specifications](docs/library/PHASE3-ACCEPTANCE-5-2026-09-08.md) and contract
`phase3-v1-2026-09-07`. Reviewed HEAD:
`3344e356d172dc0add42df839305f36f498c6879`. Implementation candidate:
`1830b7aad1515d803b7ac4afaa9b0da037178864`. The two later commits add receipts,
screenshots and documentation; production code is identical to the candidate.
The worktree was clean before this review.

File-placement limitation: this report is staged at the worktree root because
both `apply_patch` and PowerShell were denied writes under `docs/library`.
The requested destination is `docs/library/PHASE3-ACCEPTANCE-6-2026-09-08.md`.
No permissions were changed. Links in this staged copy resolve from the root.

All twelve AS-5 failures now pass. The additional failures test the same AS-02b
requirement: malformed child evidence must remain unknown. AT-6 validates the
outer record, start binding and child-object shape, but accepts malformed fields
inside those objects as proof of termination.

| Independently executed group | Result | Exit |
|---|---|---|
| Supplied strict Phase 3 suite | 150 passed; 6 warnings; 42.29 s | 0 |
| New AS-6 cases | 5 passed, 4 failed; 4.06 s | 1 |
| Full strict suite including AS-6 | 155 passed, 4 failed; 6 warnings; 46.86 s | 1 |
| Source subscription companions | 111 passed; 5 warnings; 13.36 s | 0 |
| Dashboard source companions | 31 passed; 0.30 s | 0 |
| Legacy companions | 27 passed; 19 warnings; 1.67 s | 0 |
| Adapter/registry companions | 98 passed; 0.97 s | 0 |
| Podcast companions | 30 passed; 74 warnings; 3.32 s | 0 |
| Packaging companions | 6 passed; 1.13 s | 0 |
| Heartbeat companions | 10 passed; 0.11 s | 0 |
| Additional Phase 0 CLI/provenance/X checks | 49 passed; 6.44 s | 0 |
| Phase 4 acceptance set | 32 passed; 7.29 s | 0 |

The documented AS-5 companion selectors produce 362 passes; adding the Phase 4
acceptance set produces **394**. The reported 397 still needs selectors for
three additional cases. This is an evidence-count discrepancy, not three test
failures. There are no skips or setup/teardown errors in the final runs. Registry
checks pass with the integrated 87-tool assertion.

Tests ran on Windows/Python 3.14.6 with `PHASE3_REQUIRE_IMPLEMENTATION=1`, plugin
autoload disabled and bytecode writes disabled. Strict fixtures block real
network/process activity and non-fixture SQLite access. Companions ran in separate
guarded interpreters with profiles, output and temporary files inside this
worktree's `_scratch`. Server-importing groups used byte-identical copies of
`server.py` for token/log isolation, with resource paths in this worktree.

Initial companion runs exposed runner issues: pytest's null device, a fixture
SQLite URI, asyncio's Windows socket pair and a server log outside the fixture
were rejected. These were corrected before the final passes. The Phase 4 mirror
test needed a shorter fixture path to fit the existing path limit; it then passed
without changing the test or product. Final guards allowed the null device and
standard-library loopback socket pairs, excluding port 5179. They blocked an
import-time process probe, WhisperX availability imports, and podcast-test process
and DNS attempts, including a lookup for `127.0.0.1:5179`. No connection to that
port occurred. These are guarded runs with attempted calls disclosed.

No model, resident helper, port 5179 or live index was used. S21 and the two real
process launchers were reviewed as supplied evidence and were not rerun here.
All new AS-6 liveness observations are injected fixtures.

**The repair review closes four subissues and narrows AS-02b.**

| AS-5 requirement | AT-6 review and disposition |
|---|---|
| AS-02a: preserve indeterminate launch intent | **Closed.** `_run_subprocess` retains intent for interrupted/indeterminate creation and only clears it for its selected no-child errors. The AS-5 interruption and intent/registration write-failure tests pass. The supplied real-child interruption receipt reports a surviving child, `children=unknown`, `probe=unknown`, and all created children reaped. |
| AS-02b: validate child evidence before inferring absence | **Open, narrowed.** Missing `children`, non-object children and wrong-start records now stay unknown. New tests confirm write helpers preserve wrong-start evidence. Field-level validation still fails in the four cases below. |
| AS-03a: retain locks through uncertain or failed settlement | **Closed for this repair.** Both worker paths consume settlement outcomes. All four AS-5 live/unknown-child cases pass. Two new cases make settlement itself raise; the claim and capture lock remain, as does the YouTube process lock. |
| AS-03b: reuse retained ownership and release after terminal commit | **Closed for this repair.** Both AS-5 reconciliation cases pass: absent publication settles failed, complete publication settles succeeded, and each releases the claim and both locks. The new stale-release/idempotency case confirms another start ID cannot release the held lease. |
| AS-03c: check completeness before manual reuse | **Closed.** Manual reuse calls `publication_evidence_for_reuse`; common publication/identity checks reject the item-upsert-only and damaged-sidecar cases. Existing complete-publication/manual-wait checks also pass. |

AS-01, AS-04, AS-05 and AS-06 remain closed. AS-03's cleanup repairs still depend
on truthful child-status evidence; closing those implementations does not excuse
the remaining AS-02b false-stop decisions.

**AS-02b still converts syntactically valid, damaged records into termination
evidence.** In `source_subscriptions.py`, `_child_record_bound` checks only that
each child is a dictionary. `child_ownership_liveness` then skips a child whenever
`ended_ms` is non-null, before validating its identity. It also interprets
`unresolved_launch` by truthiness without checking its type.

The four variants of
`test_as6_s13_malformed_child_fields_cannot_certify_exit` in
[test_phase3_acceptance6.py](tests/library_work_astra/test_phase3_acceptance6.py)
exercise the production backend probe and service settlement:

| Injected record damage | Observed result |
|---|---|
| A registered child has `ended_ms=false` | Child is skipped; false absence permits settlement. |
| A registered child has `ended_ms="not-an-exit-time"` | Child is skipped; false absence permits settlement. |
| A child contains only `{"ended_ms":456}`, with its identity fields missing | The dictionary passes validation and is skipped. |
| Empty children plus `unresolved_launch=[]`, with unresolved launch instance/time retained | The malformed flag is treated as false, erasing launch uncertainty. |

Every variant yields this observed state:

```json
{
  "before": {"children": "none", "probe": "stopped"},
  "outcome": "failed",
  "state": "failed",
  "claim_retained": false
}
```

The fixture supplies a dead parent and a live-child probe; the invalid exit-marker
branches never consult that probe. The launch-flag variant represents unresolved
creation, where no registered child exists to inspect. These are injected record
corruption cases, not observations of spontaneous disk corruption or a new
real-process run. They reproduce AS-5's explicit requirement that malformed
fields and invalid entries stay unknown under S13.

Required repair: validate all fields used to establish child identity, exit and
unresolved launch state before accepting absence. An exit marker must be null or
a valid non-boolean timestamp attached to a valid child record; an optional launch
flag must have its defined boolean type when present. Preserve damaged evidence
through write helpers. Invalid evidence must keep the attempt uncertain and
retain its claim/ownership. Preserve compatibility with legitimate older records
through an explicit rule, and retain the passing launch and registration-write
protections. The five passing AS-6 cases guard repaired write-helper and cleanup
behavior while this is fixed.

**The receipts establish runtime observations within their recorded scope.**
All 15 entries in the S21 checksum manifest and all three in the process manifest
match. I opened the supplied
[AT-6 evidence database](docs/library/proof/s21-2026-09-08/evidence-at6-candidate-1830b7a.db)
using SQLite `mode=ro&immutable=1`: integrity is `ok`, foreign-key violations are
empty, and its SHA-256 matches the receipt:
`eb193f5eec1e3fb963476235f404e0f9b99b8bdd24bd1a78cb5d3f17624b1dc6`.

The database contains one charged succeeded start, one committed future-eligible
item, one podcast episode/corpus row, one citation and one 12.5–21.75-second clip.
Feed/GUID/capture-key/episode bindings agree across the retained rows and receipt;
the ledger incarnation and owner-token hash agree with the claim observations.
There is one enqueued outbox, one run, one ready work row, zero client attempts
and zero shelf memberships.

The [S21 receipt](docs/library/proof/s21-2026-09-08/receipt-at6-candidate-1830b7a.json)
names `1830b7a` and reports one fixture download, one synthetic transcript, prepare
after commit, no repeat charge/capture, zero model calls and no forbidden attempts.
It records exclusive capture-lock and claim ownership at download, transcription,
publication and publication return, then claim cleanup and lock availability at
settlement. This supports S15/S16/S21's successful controlled path. It does not
exercise damaged child records.

C21's exact-command portion is satisfied for the archived automated run: its JSON
records `C:\Python314\python.exe -B tests/library_work_astra/test_phase3_s21.py
--execute-s21 --hold-seconds 5`. Ten input hashes match this worktree byte for byte;
migration 0028 matches the candidate Git blob and LF-normalized worktree file.
The launcher remains unresolved:

| Launcher bytes | SHA-256 |
|---|---|
| Recorded as executed | `d17a84c65d126abc60774ccb5fe1b63f6195faca4435f6d2a8e8f116e326b3a7` |
| This worktree | `be212fe55ff13d1475dc1d8b89dd397256e71669e1bffff7946c10cd977ba635` |
| Candidate Git blob; also LF-normalized worktree | `e4649df0ca1278c2ce509536e45dbcf7899481be271c789ed7e780316ec5dff5` |

The receipt document's description of the first hash as committed bytes does not
reconcile these values. Supply the executed bytes or another run with retained,
matching bytes. The receipt has no explicit exit-code field. Seven hashed
non-database artifacts remain outside the supplied package: transcript, server
log, incarnation file, podcast sidecar/markdown, retained media-input JSON and
generated taxonomy. I did not follow their paths into another checkout.

I inspected all three new browser screenshots. They show one Uncategorized
podcast item, podcast identity and episode source link, and an on/healthy
subscription with 1/10 daily starts and 0/25 back-catalog enrollment. The
[receipt document](docs/library/PHASE3-S21-RECEIPT-2026-09-08.md) attributes these
to a held run on the candidate. They use fixture feed port **64703**; the archived
automated receipt/database use **60407**. Credit them as the supplied candidate
browser observation, while retaining that distinction between runs. No
corresponding 64703 receipt/database is supplied to bind the images to persisted
state.

The item-detail image also shows `Transcript preview unavailable` and a transcript
file message that its markdown path is outside the Uoink folder. It therefore
does not demonstrate readable transcript content in that view. This review does
not infer a new capture failure from the screenshot alone. As disclosed,
`waiting_for_client` is in the recorded API response, not the dashboard source
row; the retained ready work row corroborates it. The per-item waiting state
remains a browser affordance/evidence gap under C21, not proof that classification
ran or that capture failed.

The [process-recovery receipt](docs/library/proof/procrec-2026-09-08/receipt-at6-candidate-1830b7a.json)
reports running with both processes alive, running with a dead parent and live
registered child, and stopped after both die. Its launcher calls `Popen` and
registration directly and compiles the production probe with fixture globals.
It does not run a subscription-ledger restart through the installed helper, and
its JSON lacks candidate/input hashes; the accompanying document supplies the
candidate attribution.

The [real-child interruption receipt](docs/library/proof/procrec-2026-09-08/real-launch-interrupt-at6-candidate-1830b7a.json)
does exercise the unchanged production `_run_subprocess` with an interruption
injected after OS creation. Server/service hashes match this worktree; its AS-5
launcher hash matches after LF normalization. A surviving child produces unknown
child/probe state and is then reaped. That directly supports closing AS-02a. It
does not cover AS-02b record corruption or replace installed recovery evidence.

The [S22 staged-tree receipt](docs/library/PHASE3-S22-RECEIPT-2026-09-08.md)
retains its copy-list/import/migration/stdio value on its older candidate. It
explicitly excludes actual Inno installation, bundled Python/dependencies and
upgrade qualification. Packaging tests do not supply that missing evidence.

| Gate | AS-6 disposition |
|---|---|
| S01–S12 | Existing migration, consent, detection, allowance, retry and clock checks pass. |
| S13 restart ownership | AS-02a repaired and supported by real-child receipt; four AS-02b record-validation cases still fail. |
| S14 queue/fencing | Existing replay and stale-owner checks pass; unknown ownership must still be preserved under AS-02b. |
| S15 deduplication/ownership | AS-03a/b/c repairs and identity checks pass; terminal cleanup still relies on correct S13 evidence. |
| S16 publication | Completeness, timing/clip derivation and local recovery pass. The rule permitting local recovery after verified termination, under the capture lock and original charge, stands. |
| S17–S19 | Handoff, waiting-state and adapter/registry fixture checks pass. |
| S20 consent UI | API/static checks pass; supplied browser images cover only part of the matrix. C20 remains. |
| S21 controlled capture | Automated receipt/database and supplied candidate browser observation credited. C21 remains narrowed as specified below. |
| S22 installed/protected scope | Packaging and staged evidence credited; mandatory actual installation qualification remains C22. |

The conservative ledger/claim-gap ruling also stands: an unexecuted intent may
remain charged and uncertain without redispatch. That does not authorize a
false terminal decision from damaged evidence.

After AS-02b is repaired, the remaining conditions are:

- **C20:** supply the disposable candidate's full browser matrix: default off,
  pending/actual enrollment, exhausted allowance, refresh errors, off with
  in-flight work, lost mutation response, stale confirmation and restart. Match
  visible state to persisted service state.
- **C21:** reconcile executed launcher bytes/hash; record exit status; archive
  the seven missing artifacts/logs; and retain the browser run's receipt/state
  binding. Demonstrate per-item waiting-for-client in a browser-visible surface,
  or explicitly resolve that affordance requirement. Database retention,
  ownership observations and the automated command already receive credit.
- **C22, Ryan:** supply the actual disposable Windows Inno installation receipt,
  with package/candidate hashes, bundled interpreter/dependencies, installed
  paths, migration/upgrade replay, registry schemas, unrelated one-off capture,
  both manual/standing orderings and recovery through the real launch path,
  including launch/registration failure. Record protected Phase 2 input/state
  preservation and isolation from models, the resident helper/port and live
  index. This remains mandatory for eventual Phase 3 acceptance.

Reproduce the strict suite from this worktree in PowerShell:

```powershell
$env:PHASE3_REQUIRE_IMPLEMENTATION = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
$phase3Tests = (Get-ChildItem -LiteralPath 'tests/library_work_astra' -Filter 'test_phase3_*.py').FullName
python -B -m pytest -q -ra --tb=short -p no:cacheprovider --basetemp=_scratch/as6/repro $phase3Tests
```

Use only `tests/library_work_astra/test_phase3_acceptance6.py` as the selector to
reproduce the nine added cases. The retained
[companion runner](tests/library_work_astra/run_phase3_companions.py) contains the
exact selectors and isolation guards. Run each group in a fresh interpreter:

```powershell
foreach ($group in 'service','dashboard','legacy','adapter','podcast','packaging','heartbeat','extra','phase4') {
    python -B tests/library_work_astra/run_phase3_companions.py $group
    if ($LASTEXITCODE -ne 0) { throw "Companion group failed: $group" }
}
```

Local logs, group result JSON and read-only receipt audits remain under
`_scratch/as6`. Handoff: AS-6 review complete; **PHASE 3 NOT ACCEPTED**. Added this
staged report, nine acceptance cases and the reproducible companion runner.
Evidence: original 150/150; final 155 passed/4 failed; companions 394 passed;
18 manifest entries and the S21 database verified. Open work: AS-02b, C20/C21/C22,
selectors for the three-count companion discrepancy, and placing this report at
its requested destination once `docs/library` permits writes. Production and
protected Phase 2 files are unchanged. No commit or merge.
