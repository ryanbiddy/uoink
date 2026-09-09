# Living Library integration candidate

Integration candidate, 2026-09-09. **Release is not ready yet.** The complete
integrated product tree on `263b7e4` has **2,193 passed, nine failed, three
skipped and one xfailed**, 183 warnings, 728.37 seconds. Eleven of the
previous 20 failures now pass, with no new failures or missing test cases.
Eight new regression cases pass. Existing tests remain unchanged since
Ryan's five authorized corrections; the further mirror-hook proposal is
pending and has not been applied. The installer and executable receipt kits
are being repaired before the final build and Ryan's installed session.

Subsequent recovery `239dbbd` closes three Phase 3 archive gaps in focused
verification: AS-7/8/9 is 22 passed / one failed, strict Phase 3 is 181 passed /
one failed. The original AT6 child exit status remains missing. These focused
results do not replace the corrected full tree. Follow-on mirror repair
`1063843` has 163 passed / eight failed in both roots. The reviewed SDK repair
at `0ad33d4` has 267 passes in both roots. The Phase 6 refusal repair at
`512fecb` has
71 passes in both roots, including both originally failing stale-publication
checks. No omitted ticket is minted or allowed to publish. Installation isolation and executable receipt
kits are in progress; no new package is sealed yet. Default style seeding
at `db95457` now commits before standing-capture startup and rolls back a
partial seed; its three new ownership/durability checks pass in the full tree.

The later existing-preview repair prevents a read from initializing storage or
replaying recovery. Nine new checks pass, including unchanged files and SQLite
contents through the original stdio entry after restart. Its broader companion
run has 212 passed / the same eight mirror-hook failures. It still needs the
final complete-tree and bundled-runtime observations.

## Package and scope

Application version: 3.8.0. Branch `cc/living-library-candidate`, cut from
`9217846da45cecbf1b91614d9031fd7a16b7d16f`. Installer build source:
`e47e4f2e8e1b6a83ecb1171436092b9077186430`. That retained package predates the
current mirror and SDK repairs. Production source changed after the corrected
tree; a new build and seal are required after the remaining verified integrations.
The original installer and proof remain retained as historical artifacts.
Checkpoint `512fecb` is backed up on `origin/cc/living-library`;
the remote SHA was independently verified. This is a branch backup of a failed
candidate, with no merge to main or artifact publication.

Local artifact: [Uoink-Setup-3.8.0.exe](../../build/Uoink-Setup-3.8.0.exe),
339,042,658 bytes (323.3 MiB). SHA-256:
`9defc2a98ba680f8b4cdf06bdd09eadbb1153f2028070881b5472ce97f7e927d`.
Compilation completed on 2026-09-09 at 00:30 PDT after 368.93 seconds.
This package has not been installed, published or merged to main. The authorized
branch backup is separate from artifact publication. Label application remains
disabled. **Do not install this artifact under the current receipt constraints:**
Inno preparation probes port 5179, and the ordinary helper launcher probes/binds
it. Silent installation and a throwaway account do not remove that behavior.
The [runbook](INSTALL-RECEIPT-RUNBOOK-2026-09-09.md) stops before installation;
the [product repair brief](INSTALL-ISOLATION-REPAIR-BRIEF-2026-09-09.md) defines
the required repair and operator kit. Installed C22/Phase 4 remain unexecuted.

The build verified the exact 142-package dependency lock, schema 30, version
3.8.0 in the helper and extension, and packaged tray, dashboard, splash and
WhisperX imports. The separate original-entry stdio observation used the
bundled Python 3.11.9 and MCP 1.27.1 with a synthetic one-item database. It
observed 32 tools, five resource templates, four prompts, equal complete card
contents through native and fallback reads, a native consult prompt and a
successful small activity request. Its child exited zero with both output
drains complete. This does not establish installed behavior, model inference
or speaker quality.

The first stdio attempt remains failed: its isolation guard also blocked
Windows Python's internal event-loop socket pair. A
[documented guard repair](CANDIDATE-PACKAGED-RUNTIME-REPAIR-BRIEF-2026-09-09.md)
permitted only that standard-library loopback pair, with port 5179 still
forbidden, before observation 02. Both original attempts are retained in
the [28-file package receipt seal](proof/candidate-package-01-2026-09-09/SHA256.json).
The archive inventories 32,202 staged input files and binds 141 source files
to the frozen checkout. It is not an extraction of the installer. The
post-observation token and log are excluded from that inventory because
Inno's explicit source list does not package them; their metadata is retained
separately and the task-created token was removed. No token contents or
fixture databases are in the archive.

## Phases 0 and 1: reliable capture and searchable evidence

Phase 0 added truthful health/doctor failures, source-type backfill, podcast
eligibility repairs, capture-tool registry coverage, CLI entry points and a
watchdog installer. Watchdog installation remains an owner action. Phase 1
added clip retrieval, canonical bounded evidence cards, source/timing
provenance and opt-in Recall context for client sessions.

Run I accepted the repaired foundation with listed exceptions on `d83be1f`;
see [the historical acceptance report](ACCEPTANCE-REPORT-2026-09-04.md).
The held 548-item copy had 3,216 original clips and 3,705 after the reviewed
schema-26 repair, covering the same 212 items with clips. These are archived
copy measurements, not current live-library counts. The original security,
benchmark, runtime and installation exceptions remain in that report unless
a later cited phase receipt explicitly closes them.

## Phase 2: reversible Librarian shelves

The [Phase 2 contract](PHASE2-CONTRACT-2026-09-04.md) supplies the work queue,
leases, strict evidence validation, report-only previews, approved apply/undo,
pins and recovery. It separates proposed assignments from accepted changes.
Service acceptance and later stage audits are recorded in
[the Phase 2 report](PHASE2-ACCEPTANCE-REPORT-2026-09-04.md) and
[Stage 4 audit](STAGE4-AUDIT-2026-09-08.md).

Stage 4 P2-7 quality remains **failed**: 39/46 timed and 6/11 text judgments.
Ryan selected option 3 on 2026-09-09: retain 0.90 for autonomous filing and
ship proposals as reviewable suggestions. `librarian_apply_enabled` remains
false. This scope decision does not change the failed quality measurement.

## Phase 3: standing capture

The `phase3-v1-2026-09-07` contract separates source discovery from capture
authorization. Automatic starts require durable source consent, enrollment
and an atomic reservation. Source capture remains off by default, with at
most 25 back-catalog items and 10 starts per source per UTC day. Successful
publication exposes an unfiled item before assignment scheduling. Source
opt-in does not enable model downloads or label application.

AS-9, integrated at `6807361`, historically accepted this phase subject to C22, Ryan's
installed Inno receipt. Independent confirmation passed 11 tests in both
roots; the strict suite had 178 passes and four retained assertions against
superseded evidence. Companion suites passed 394 and dashboard tests 35 in
both roots. Replacement AT7 evidence was verified; the old failed assertions
were preserved. See `PHASE3-ACCEPTANCE-9-2026-09-08.md` and the handoff.
Recovery `239dbbd` restores the original artifact bytes and closes three of
those checks in the complete `263b7e4` tree. The original AT6 child exit
status remains unrecorded: its shell wrapper discarded that status. Neither
the replacement observation nor the wrapper's exit can supply it. This
remaining audit failure is separate from installed C22.

## Phase 4: bounded access and optional mirror

The `phase4-v1-2026-09-08` contract adds bounded library reads, five resource
templates and four prompts, with revision-bound card, excerpt, corpus, shelf
and brief identities. Tools and resources use the same representation.
Client-produced briefs retain input and citation bindings. The optional
mirror requires separate consent, tracks file ownership and preserves user
edits through conflicts and deletion recovery.

Implementation closed at `6858b81` after B7 and the independent AW-12
correction: both roots had 286 passes and nine retained frozen failures;
the broader AW-4 check passed 113. The shared Windows writer gate conservatively
serializes unrelated mirror destinations. It retains exclusion for the actual
writer owner's lifetime, binds helpers to an operation/thread and verifies
file ownership before cleanup. POSIX identity publication refuses. The
two-second publication budget does not promise bounded total process startup
and cleanup. See [AW-12](PHASE4-AW12-2026-09-08.md) and
[final AW-4](PHASE4-AW4-FINAL-2026-09-08.md).

The required Claude Code/stdio behavior is accepted with conditions at
`9217846`; see [the final client disposition](PHASE4-CLIENT-02-2026-09-09.md).
Complete native/fallback cards, excerpts, text corpus and synthetic brief
matched. Both required native prompts, explicit reconnect, storage refusals,
a 10.003-second transport timeout, hostile-input action evidence and silent
Recall failure were observed. Client streams contain no unauthorized action.
All fixture state was preserved or restored. The disconnected/edited/deleted
vault cases retain exact pending/conflict accounting.

Actual sessions used Claude Code 2.1.261, Haiku 4.5 via Max, Python 3.14.6
and MCP 1.28.1. They do not establish installed runtime or Desktop acceptance.
Native template discovery was not requested by the client; five templates
remain source/stdio-test evidence. The original timed YouTube link played,
while the text-only source's original X URL returned HTTP 403 and stays
blocked. Null card source metadata and text-only timing were preserved.
Ryan retained the X HTTP 403 as a documented blocked-link condition, with no
access repair or new fetch. The five lifetime failures pass after `1063843`,
including in the complete `263b7e4` tree. Eight parent-interception checks
still fail; the exact three-file fixture proposal preserves all 150 assertion
syntax trees and awaits Ryan's explicit approval. The proposal is unapplied.
The installed receipt additionally awaits the isolated installation repair.

## Phase 5: descriptive library activity

The `phase5-v1` Part A reports saved-item activity, recorded shelf changes
and source observations with explicit populations, UTC intervals, clocks,
coverage, revisions and supporting evidence. Capture activity does not imply
a publication trend. Creator hints are not verified person identities.
Evidence pagination preserves the metric's denominator. Unsupported ratios
remain null. Engagement analysis and Part B remain absent.

Part A's historical acceptance at `a39c7e6` had 574 passes and two retained
failures in both roots. Ryan authorized the unary/clock correction; that test
now passes. The original SDK-route deadline/admission failure closes at
`0ad33d4`, with 267 focused passes in both roots and a pass in the complete
`263b7e4` tree. Settlement belongs to the actual outgoing response frame;
serializing a local copy cannot release the request early. The shared SDK
serializer is unchanged.
Part B is explicitly deferred.

G2's sealed synthetic measurements include full responses and evidence
pagination, plus an independent transport supplement. Primary serialized
response sizes were 64,732 and 64,601 bytes before the newline. The
24,576-byte dashboard target was missed. Traced heap runs, including the
30-second 10k diagnostic, are not normal service-latency evidence. Actual
SDK serialization was observed through in-memory I/O; those measurements
are not a real-client or installed-package receipt. See the final disposition
in `PHASE5-BA4-2026-09-08.md`, `PHASE5-AZ5G2-INTEGRATOR-2026-09-08.md`,
and the G2 and supplement proof directories.

## Phase 6: chapters and cited ranges

Ryan's 2026-09-09 release ruling: Phase 6 ships chapters and cited ranges
without speaker attribution claims. The speaker gate stays blocked and no
diarization run is authorized. Stored local-label support is not evidence of
verified identity or attribution accuracy.

The `phase6-v1` contract adds revision-bound media annotations while
preserving stored clip text, boundaries and excerpt identities. Publication
checks the producer's original tickets and every consumed input at entry
and before final carrier replacement. Missing tickets refuse publication.
Unsupported podcast seeking has null fields; coarse timing does not acquire
precise range-export authority. Annotation retention and virtual unsupported
views preserve the accepted source and deletion behavior.

The historical BD-2 disposition accepted Phase 6 subject to the omitted-ticket
fixture ruling and speaker material. BC-3f `986b555` produced 174 passes and
11 retained omitted-ticket failures in each root. The final broader check
passed 382 tests with four superseded AS-7 evidence failures.
Ryan authorized the setup correction. The subsequent refusal repair passes
all 71 named checks in both roots. Validated snapshots already in committed
history receive the expected stale-revision refusal; other omitted tickets
remain invalid and cannot publish. The failed full-tree result remains until
the new complete tree runs. Speaker material stays blocked under the explicit
release scope above.

The frozen navigation study reduced mean absolute error from 72.06 seconds
to zero over all 50 tasks. BD-27 playback was observed in normal Comet at
the requested chapter, with playback, chapter-list and exact 0:34 screenshots
retained at `1217dbf` and byte preservation at `82d81d1`. The earlier Chrome
503 attempts remain partial. This does not establish speaker accuracy or
subsecond player timing. See `PHASE6-BD2-2026-09-08.md` and
`PHASE6-BD27-PLAYER-RECEIPT-2026-09-08.md`.

## Combined verification

Integrated product checkpoint `263b7e422a4cb5b0c3357a86e4ac957eec28a4cf`:
**2,193 passed, nine failed, three skipped, one xfailed**, 183 warnings,
**728.37 seconds**. Only S21 is excluded. Compared by exact JUnit case
identity with `4a35316`, eleven failures now pass, eight new regressions pass,
no earlier case is missing and no new failure appears. All nine failures
remain failed. See `proof/ryan-integrated-tree-01-2026-09-09/SHA256.json`.
This uses the native Python 3.14.6 private verification runtime, with vendor
hashes and inherited guard proof retained separately. It precedes the pending
installer/kit integrations and their required final complete-tree check.

Corrected candidate `4a3531642692736d4aaa4098077ab8fde464aeb4`: **2,174 passed,
20 failed, three skipped, one xfailed**, 183 warnings, **607.27 seconds**.
Only S21 was excluded under the standing command. The six authorized fixture
files retain all 690 assertion syntax trees. Python 3.14.6, pytest 9.1.1 and
MCP 1.28.1 were used in the isolated checkout run; this is not the bundled
Python 3.11.9/MCP 1.27.1 installed-runtime receipt.

The 20 failures comprise four Phase 3 evidence checks, thirteen Phase 4 mirror
checks, one Phase 5 SDK serialization check and two Phase 6 refusal checks.
All 20 also failed in the previous tree; 72 previous failures pass in this
separate observation. No test cases were added, removed or additionally
deselected. See the [complete sealed result](proof/ryan-corrected-01-2026-09-09/SHA256.json)
and [product repair brief](CORRECTED-TREE-PRODUCT-REPAIR-BRIEF-2026-09-09.md).
The result is failed, with no further fixture-correction round.

Historical candidate `6c313ea` full tree: **2,102 passed, 92 failed, three skipped,
one existing xfail**, 550.41 seconds. Only S21 was excluded; every closed
Phase 4 reproduction was included. This is a failed full-tree result.

All 67 additional mirror failures had passed in the prior focused union on
the same production source. A reduced ordered pair demonstrates why the
first ordinary export fails: AW-11's private-helper fixture directly terminates
its session and drops the Mirror pointer, leaving a dead thread-local I/O
binding for the next fixture. No process or exclusion lock remains. Production
stop/kill cleanup forgets that binding; four independent lifecycle controls
succeeded without resetting global state. The tests were unchanged for that run.

Ryan authorized consistent fixture teardown and four other narrow corrections
on 2026-09-09. Their corrected full-tree result is recorded separately above.
The 67 failures remain failed; neither the diagnosis nor the controls
turn them into passes. The old D15 assertion did not fail in this contaminated
run, which does not override its earlier frozen failure. See
[the investigation brief](CANDIDATE-MIRROR-ORDER-BRIEF-2026-09-09.md) and
`proof/candidate-full-01-2026-09-09/summary.json` for the complete comparison,
two failed order diagnostics and lifecycle control.

The latest pre-Phase-4 closure run on `44968d9` had 2,106 passes, 26 failures,
three skips and one existing xfail in 514.25 seconds. S21 and the then-open
AW-5/AW-7 reproduction files were excluded. Its 26 failures comprise four
superseded AS-7 assertions, nine frozen Phase 4 setup cases, eleven omitted-
ticket Phase 6 calls, one Phase 5 unary/clock case and the old BA-4 SDK
route. No additional failure appeared. The final candidate result must
identify its actual exclusions and failures separately from this baseline.

Proof files retain full outputs and hashes. Rejected worker patches and
failed or partial measurements remain archived. The authorized setup/cleanup
diff and review are retained; behavior assertions were not changed.

## Open decisions and receipts for Ryan

- Phase 2 strict precision remains failed: 39/46 timed and 6/11 text cases.
  Ryan chose option 3: reviewable suggestions, 0.90 retained for autonomous
  filing, and label application disabled. This decision is resolved.
- Nine checks remain failed in the latest complete tree: eight mirror
  interception cases and the missing historical AT6 child exit status. The
  reviewed mirror-fixture proposal awaits Ryan; no waiver or edit is inferred.
  The installed-path and kit repairs remain product/instrument work.
- Installed Inno receipts for Phase 3 C22 and Phase 4, after the product repair
  supplies a safe, exact operator kit. The current runbook is blocked before
  installation and does not yet provide executable installed scenario commands.
- Phase 4's original X source remains a documented HTTP 403 blocked-link
  condition under Ryan's ruling. No access repair or new fetch.
- The five fixture corrections are authorized and documented in
  `INTEGRATOR-CONTRACT-CONFLICTS-2026-09-08.md`. All behavior assertions
  remain unchanged. Any residual full-tree failure is a product defect,
  with a repair brief required and no further fixture edits permitted.
- Speaker gate remains blocked. Phase 6 ships chapters and cited ranges
  without speaker attribution claims; no diarization runs.
- Any new fetch scope and merge to main. Standing orchestration signature,
  watchdog installation, PR strategy and adapter allow-list decisions
  remain in the handoff.

No live index or resident helper was used for integration verification.
No paid API was used, and no live labels were applied.
