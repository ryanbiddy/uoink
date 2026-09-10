# Living Library 3.8.0 release candidate

Updated 2026-09-10. Candidate retained for review; not approved for ordinary upgrade or public release.

The library now supports bounded evidence retrieval, reviewable shelf proposals,
consented standing capture, native resources and prompts, an optional file mirror,
descriptive activity reports, and chapters with cited ranges. No merge to main or
public release has occurred. Installation is not a security certification.

## Package and verification

| Item | Recorded value |
|---|---|
| Installer | Uoink-Setup-3.8.0.exe |
| Build source | `6b5aed8cb60be3e826af5f308015393a72c60b0d` |
| Bytes | 388,987,465 |
| SHA-256 | `95123073516bf880858218ff8ca426206b15cafc12e2d07bc9f125e1ccc30e49` |
| Bundled runtime | Python 3.13.15, MCP 1.28.1, schema 30 |
| Build interval, UTC | 2026-09-10T05:55:50.0277909+00:00 to 2026-09-10T06:02:37.8930199+00:00; 407.867 seconds |
| Complete-tree source | `393010f80c53a95a6fa3c853a98b77924efa0250` |
| Complete-tree result | 2,493 passed, 1 failed, 2 skipped and 1 xfailed |
| Actual installation | Actual isolated install/reinstall observed; client and browser gate incomplete |

[Package-05's seal](proof/candidate-package-05-2026-09-09/SHA256.json) records
32,063 compiler inputs: 32,054 installed file destinations, eight wizard images
and one setup-only script. Its 142 source bindings comprise 141 installed source
files and the separate `dontcopy` script. Compiling a file is not evidence that
Setup installed it; the installed comparison is recorded separately below.

All 139 runtime pins match the actual build metadata, with no extra distributions.
The generated notices were reviewed at `45cd6f7`; they are outside the installer
payload. Later evidence and documentation commits do not change packaged source.
The earlier packages and receipt ZIP remain retained historical artifacts.
Use the new package and its matching [runbook](INSTALL-RECEIPT-RUNBOOK-2026-09-09.md).

## What the phases deliver

| Phase | Delivered behavior | Scope and limits |
|---|---|---|
| 0–1: capture and evidence | Health/doctor reporting, capture registry and CLI repairs, clip retrieval, canonical evidence cards, source/timing provenance and opt-in Recall context | Historical foundation acceptance retains its recorded exceptions; the watchdog still requires an owner action |
| 2: Librarian shelves | Work queue, leases, validated previews, reviewed assignments, pins, apply/undo and recovery | Proposals ship as reviewable suggestions; autonomous filing retains 0.90 and `librarian_apply_enabled=false` |
| 3: standing capture | Durable source consent, separate discovery/enrollment, atomic start reservation, deduplication and recovery | Capture starts off; up to 25 back-catalog items and 10 starts per source per UTC day; source opt-in does not permit model downloads or label application |
| 4: bounded access and mirror | Five resource templates, four prompts, bounded card/excerpt/corpus/shelf/brief reads, revision-bound citations and separately consented mirror export | Tools and resources share representations; user edits and ownership survive conflicts and deletion recovery; X remains blocked with HTTP 403 |
| 5: activity descriptions | Part A reports saved-item activity, recorded shelf changes and source observations with populations, UTC intervals, coverage and supporting evidence | Capture activity does not prove publication trends; unsupported ratios remain null; Part B and engagement analysis are deferred |
| 6: media navigation | Revision-bound chapters and cited ranges, producer/input ticket checks and stale-input refusal | No speaker attribution claim or diarization; unsupported seeking stays null and coarse timing does not grant precise range export |

The archived 548-item copy had 3,216 clips before the reviewed schema-26 repair
and 3,705 afterward, across the same 212 items with clips. These are historical
copy measurements, not the current live library. See the
[foundation acceptance](ACCEPTANCE-REPORT-2026-09-04.md).

Phase 2's quality measurement remains **failed**: 39/46 timed and 6/11 text
judgments. Ryan selected suggestions-only release scope on September 9; that
decision does not turn the measurement into a pass. See the
[Stage 4 audit](STAGE4-AUDIT-2026-09-08.md).

Phase 4's historical real-client sessions used Claude Code 2.1.261, Haiku 4.5
through Max, Python 3.14.6 and MCP 1.28.1. They observed both native prompts,
complete native/fallback evidence, reconnect/refusal paths, hostile-input action
records and silent Recall failure. They do not establish the new installed
runtime or Desktop acceptance. The source client's template discovery was not
observed. See the [client disposition](PHASE4-CLIENT-02-2026-09-09.md).

Phase 5's primary serialized responses measured 64,732 and 64,601 bytes, missing
the 24,576-byte dashboard target. Traced heap diagnostics are not normal service
latency measurements. The original SDK settlement defect is repaired at
`0ad33d4`, with 267 focused passes in each root and a complete-tree pass. See
[the Part A disposition](PHASE5-BA4-2026-09-08.md).

Phase 6's frozen navigation study reduced mean absolute error from 72.06 seconds
to zero across 50 tasks. BD-27's historical Comet observation retained playback,
chapter-list and exact 0:34 images at `1217dbf`; earlier Chrome 503 attempts stay
partial. The result does not establish speaker accuracy or subsecond player
timing. See [the navigation disposition](PHASE6-BD2-2026-09-08.md) and
[player receipt](PHASE6-BD27-PLAYER-RECEIPT-2026-09-08.md).

## Security review and repairs

Gemini reviewed installer boundaries, application security, dependency findings
and the receipt procedure. Its final decoder repair run exhausted the subscription
quota without producing a change; Astra completed and verified that repair. Astra checked the reports against source and repeated
the named suites in worker and checkout. Worker statements of airtight isolation
or complete safety are not adopted.

| Repair | Commit | Independent verification |
|---|---|---|
| Approved mirror and ordered-read setup corrections | `c3da3f6` | 180 mirror passes and 74 ordered-read passes; all 163 behavior assertion trees preserved |
| Separate isolated credential namespace | `ddfd316` | 117 passes / one existing xfail in each root; reads, writes, migration and invalid-key resets cannot fall back to ordinary/legacy storage |
| Four dependency updates | `c711feb` | 23 focused passes in each root; the earlier Python 3.11 graph had 142 pins; the qualified Python 3.13 graph has 139 |
| Isolated Start Menu group and installation evidence | `76f9824` | 93 passes; exact-source dummy compilation and driver parse succeed; actual effects are recorded separately |
| Receipt setup corrections | `9ea7d08` | 172 passes in each root; all 17 original scenario assertions preserved |
| Python 3.13.15 and FFmpeg updates | `9ce27a2`, `e1d81bc`, `6b5aed8` | 139 exact runtime packages; static LGPL 8.1.2 plus shared LGPL 7.1.5; 42 repair checks pass in both roots and product-loader WAV decoding passes |
| Setup-only payload classification | `86bfede` | 35 passes in each root; 34 new regressions reject missing/changed app files, traversal and improper exemptions |

Pillow is now 12.3.0, MCP 1.28.1, cryptography 50.0.1 and NLTK 3.10.3.
The revised-lock OSV observation reports **19 advisory entries / 15 distinct
alias-connected issues across four packages**, down from 95 entries / 55 issues
across seven. This audit is not clean.

| Retained package | Distinct issues | Applicability and repair limit |
|---|---:|---|
| Lightning 2.6.5 | 1 | Affected checkpoint loading; no available upstream release contains the reported repair |
| NLTK 3.10.3 | 1 | Model-artifact path APIs remain affected; the observed Uoink/WhisperX sentence-tokenization call path does not expose those APIs |
| Torch 2.8.0 | 8 | WhisperX's published dependency constraint prevents a direct move to the patched newer line |
| Transformers 4.57.6 | 5 | Patched 5.x needs a Hugging Face Hub version incompatible with the current WhisperX constraint; affected model/training/export APIs are not first-party Uoink call sites |

Ordinary transcription uses PyAnnote voice detection and loads a checkpoint
packaged with WhisperX. Disabling speaker attribution does not bypass every
checkpoint loader. The new package contains the same 17,719,103-byte checkpoint,
SHA-256 `0b5b3216d60a2d32fc086b47ea8c67589aaeb26b7e07fcbe620d6d0b83e209ea`.
No model download or diarization was run for this verification. Retained
checkpoint-loader advisories require a release decision; consent or a local file
path does not repair unsafe deserialization. See
[Astra's dependency verdict](ASTRA-DEPENDENCY-SECURITY-VERDICT-2026-09-09.md).

Defender's custom scan of this exact new EXE exits zero and reports no threats;
its before/after hashes match. The EXE is unsigned. Antivirus, firewall and
cloud/sample policies were not changed. A no-threat scan does not prove absence
of exploitable defects. Exact pinned versions are recorded, but the dependency
resolver does not use wheel download hash locks.

The reviewed install uses a separate app/data path and credential namespace in
the existing non-elevated Windows account, with a separate uninstall entry and
Start Menu group. It does not sandbox same-user malware. This host has no Windows
Sandbox; no elevation, system-feature installation or protection downgrade was
used. Actual receipts retain the real account identity and effects.

## Actual installed observations

Actual Setup and same-version reinstall each exit zero in Agent Install 05,
outside the checkout under the same non-elevated Windows account. All 32,054
installed file hashes match. The original installer observer refused the
OneDrive-redirected Desktop before Setup; the reviewed supplement records its
metadata without traversing contents, verifies actual empty Tasks settings and
checks the actual Inno/shortcut/registry effects. Ordinary Uoink was not replaced.

Installed C22 records **11 passed / zero failed / three unexecuted manual
placeholders**. Four actual browser images are paired with the same persisted
state before, after and after stop. Only labels/timestamps change. The visible
source/allowance/idle state agrees; consent revision and the worker_lost outcome
are not shown, so the visual receipt remains **partial**. The helper exits zero,
its port is freed, and guard/interpreter bytes are restored. See the bounded
[browser repair brief](BROWSER-RECOVERY-UX-REPAIR-BRIEF-2026-09-10.md).

Installed image/encryption and product-loader WAV observations pass using
temporary no-site instrumentation, with byte-exact interpreter restoration.
They establish instrumented decoder compatibility. The original launcher and
startup-flag failures are retained; no model download or inference occurred.

After receipt repair `393010f`, the original installed Phase 4 route observes
32 tools, five resource templates and four prompts. Its collector records
**15 passed / zero failed / eight unobserved**, with zero product findings.
Native packets/prompts, reconnect, storage refusal, Recall silence, protected
bytes and mirror/deletion checks have separate evidence. The raw collector's
overall installed_credit remains false; it is not a completed client gate.
Owned transport termination retains exit one and is not described as a graceful
client exit. The first prepare import failure and missing-input collection
refusal remain recorded.

See [the installed evidence seal](proof/ryan-agent-installed-05-2026-09-09/SHA256.json)
and [Astra's installed verdict](ASTRA-INSTALLED-CANDIDATE-VERDICT-2026-09-10.md).

The isolated same-version reinstall exercises replacement by the same version.
It deliberately skips the ordinary upgrade-preparation script and does not
establish a cross-version binary upgrade. Legacy-data migration is a separate
C22 observation. Synthetic acquisition/transcripts and prepared P4 evidence stay
labeled as fixtures; they do not become live-source quotations.

Fresh isolated client configuration is prepared, empty and unsigned-in.
No ordinary credentials were read or copied, and no client/model was invoked.
Fresh subscription sign-in and confirmation that extra paid usage is off remain
user-controlled prerequisites. Actual ordinary/Recall client streams, hostile
client actions, and visual citation/brief/chapter flows remain unobserved. X's
historical HTTP 403 and BD-27's earlier player observation retain their separate
scope; neither was fetched again. The eight unobserved collector rows include
the optional player row and are not eight newly failing product features.

## Full-tree results and retained history

The final native run uses the private Python 3.14.6 verification environment,
pytest 9.1.1 and MCP 1.28.1. It is a complete two-process partitioned tree:
all cases except two media tests run in the first process; those exact two run
in a fresh guarded process with verified private GPL FFmpeg tools. Only S21 is
absent. The retained P4 parent guard cannot safely be removed. The GPL test
tools do not ship; the installer contains the separately verified LGPL builds.
Installed Python 3.13.15 observations are separate.

| Source | Passed | Failed | Skipped | Xfailed | Seconds |
|---|---:|---:|---:|---:|---:|
| `393010f` | 2,493 | 1 | 2 | 1 | 1451.129 |
| `9a62e84` | 2,489 | 1 | 2 | 1 | 1464.698 |
| `7109182` (monolithic) | 2,484 | 3 | 2 | 1 | 1568.94 |
| `80a4fa8` | 2,451 | 1 | 3 | 1 | 1427.78 |
| `12ce8a5` | 2,429 | 13 | 3 | 1 | 1542.35 |
| `8fc6a40` | 2,254 | 10 | 3 | 1 | 573.49 |
| `263b7e4` | 2,193 | 9 | 3 | 1 | 728.37 |

All 2,497 cases are accounted for once. Four new embedded-probe regressions were added after `9a62e84`, with no prior case missing. The aggregate remains FAIL; the historical AT6 exit assertion is still failed. No existing test or fixture guard changed. See [the complete-tree seal](proof/ryan-final-partitioned-02-2026-09-10/SHA256.json).

The original AT6 shell wrapper discarded the child exit status. Recovered
artifacts and a successful replacement AT7 cannot recreate that old status;
the original audit assertion remains failed. SEC-06 is the existing strict
expected failure for non-ASCII search queries; it is an unresolved functional
limitation, not a security repair. Platform-specific skips remain disclosed.
See [final verification](FINAL-RELEASE-VALIDATION-2026-09-09.md).

## Open release decisions and limits

- Ryan's disposition of the missing historical AT6 exit and retained dependency
  advisories; neither is presented as a pass or clean security clearance.
- Complete the bounded browser recovery/revision display repair and fresh installed visual pair. Real-client authentication, client streams and citation/brief/chapter observations remain open; no release approval is inferred.
- No speaker-attribution claims; speaker material stays blocked. Phase 5 Part B
  is deferred. The failed shelf-quality and dashboard-size measurements remain.
- Main merge and publication require Ryan's decision. Only the authorized
  `origin/cc/living-library` backup is pushed; no candidate-branch push or main
  merge is included.

No live library index, resident helper on 5179, paid API or live label application
belongs to this verification. No X access repair or new source-media fetch is
included. The [handoff](ORCHESTRATION-HANDOFF-2026-09-08.md) retains each integration,
failed/partial observation and remaining action.
