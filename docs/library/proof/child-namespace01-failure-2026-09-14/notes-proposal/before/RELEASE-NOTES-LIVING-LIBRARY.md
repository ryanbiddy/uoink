# Living Library 3.8.0 release candidate

Updated 2026-09-14. Release remains held. Website work and marketing are paused
until the council and integrator accept the product for market.

The latest complete source tree at `56d9d4c` records **2,796 passed, one failed
and three skipped cases, plus 13 passing subtests**. All 50 mirror regressions
from the previous complete run now pass. The missing historical AT6 child-exit
record remains a failure. Model-loading security, actual publisher signing and
verified Claude Desktop isolation are still open.

Reliability consent and settings were repaired afterward at `e8d058f`.
Ordinary checks require local files, a marker alone cannot make a model ready,
and model size/Turbo labels are corrected. Both worker and checkout pass all
53 focused cases plus 13 subtests. The complete tree above predates this change;
these focused passes do not qualify a new package, native model or installation.

Installer notice repair `71d3e70` adds the main notice index and both retained
upstream license texts to the Windows staging/Inno sources. A failed generation
now stops the build. Author and actual checkout each pass 20 Python cases and
10 isolated build-block cases. Existing assertions are unchanged. The eventual
candidate still needs a fresh installed inventory and exact installed notice
checks; see [the notice verdict](ASTRA-NOTICE-INTEGRATION-VERDICT-2026-09-13.md).

Generated reservation recovery at `f9ab6fe` passes 42 cases in each independent
copy, with zero failures or skips and 20 passing nested subtests. The component
retains uncertain ownership and requires explicit reconciliation before reuse.
These checks use fake workers and journals; they provide no qualification of
Windows handles, native recovery or real models. Gemini's partial report at
`870fa00` is supplemented at `2339a09`. Astra accepts the three component verdicts
with documented source and scope corrections; this is not market acceptance.

The approved Windows test correction is qualified at `8fc3219`: both fresh
copies pass 65 cases and 33 nested subtests, with zero failures or skips.
Only the two exception expectations Ryan approved changed. Every retention
assertion now executes successfully. The original 63-pass/2-fail observation
at `58335df` stays failed. These fake checks provide no native journal or
recovery qualification.

The later retained-handle transfer at `2f4311f` passes70 cases and35 nested
subtests in both copies. It preserves all corrected65 cases and adds five
ownership/failure controls. These use fake services; actual Windows journal
normal drain is now observed at `67887c3`: child exit0, empty job, four confirmed
phases/flushes and exact closed journal bytes. That observation does not qualify
crash/restart recovery or real models. Gemini's worker/journal report from brief
`d996dba` is preserved
with a failed accuracy verdict at `244cca5`. Scoped source review is completed
at `1c6ac4c` with an Astra addendum correcting the remaining claims in Gemini's
partial correction. The underlying test outcomes remain unchanged. A later
writer-exclusion observation failed overall with PersistenceUnconfirmed during
drain; its partial sharing-refusal result does not qualify recovery or release.
That failure is sealed at `c5e72a2` with 130 verified proof payloads. A separate
diagnostic at `cc6bb7c` also failed and identified mutable directory size in the identity
comparison. The repair is qualified at `d317a88`: both copies pass81 cases and72
nested subtests, with regular-file size checks and all original assertions
unchanged. Generated native writer exclusion and normal drain are accepted at
`f630264`: both exact processes exit0 with empty jobs, all four journal phases
and flushes complete, and the closed journal matches. All93 native proof
payloads match Git/disk. The two earlier writer observations remain failed.

Cancellation is now qualified in generated checks: `60b3bb5` passes the same
89 cases and 86 nested subtests in each root. Native observation `a25b34b`
produces one generated segment, acknowledges cancellation while the journal
remains WORKER_BOUND, then completes verified child/job retirement and all four
journal phases and flushes.

Retired-owner recovery at `a83ae1a` passes the same 22 cases and 21 nested subtests
in each root, with zero failures or skips. The separate native result at
`5671b51` accepts one fixed Python interruption after verified worker retirement
and before journal clear I/O. Explicit manager reconciliation completes CLEARED,
closes the journal and releases the gate; the old owner and token stay revoked.
It does not qualify recovery of an active uncertain worker, OS interruption,
crash/restart, power loss or real models. See [the native recovery verdict](ASTRA-NATIVE-RETIRED-OWNER-RECOVERY01-VERDICT-2026-09-13.md).

The later inaccurate council report remains failed at `89c1579`. The scoped
directory review at `a74e178` and writer review at `f32f0ca` are accepted only
with their mandatory [directory addendum](ASTRA-GEMINI-DIRECTORY-CORRECTION02-VERDICT-2026-09-13.md)
and [writer addendum](ASTRA-GEMINI-WRITER-CORRECTION02-VERDICT-2026-09-13.md).
These are limited source reviews; they add no execution or market clearance.

The worker runtime owner at `1f200eb` passes the same 11 generated cases in both
copies. It refuses result publication after VAD retirement, product/module
replacement or model-lease revocation. The actual factory method uses fake tensor
and model classes in these checks. Its actual worker-bootstrap connection is
qualified at `bbe10d6`: both copies pass the same 17 cases, including six new
construction, registration, retirement and failure controls. The connection now passes the same
33 generated cases in both roots at `3661608`. Generated native cancellation is
accepted at `3b8f9e0`. Native inference, protected model loading,
decoder/filter authority and the actual VAD-to-model link remain unqualified.
No production runtime migration is accepted.

The repaired interrupted-owner connection at `feee2f7` passes 28 fixed cases and 57
nested subtests in each independent copy, with no failures or skips. Author
`70e7f4` and independent `dd5dc7` return 0; root check `9cdc98` verifies identical
case objects, all 35 child-input hashes and all ten guards. Admission was
committed at `e2801a5`. The original Gemini source proposal remains rejected at
`0a1a211`. These new checks use inert system calls; native forced termination,
the real runtime, production migration and release remain unqualified. See
[the qualification verdict](ASTRA-INTERRUPTED-OWNER-FAKE28-VERDICT-2026-09-14.md).

The subsequent generated Windows interruption observation at source `3fc4cf7`
failed: outer exit 1, controller exit 0 and unchanged inputs. Its driver omitted
five required write-refusal checks while files were locked. The existing
ten-observation assertion remains unchanged. Repair brief `d04652a` adds the
missing checks and focused coverage; this result supplies no new acceptance.
See [the failure review](ASTRA-INTERRUPTED-NATIVE01-FAILURE-2026-09-14.md).

The repaired complete controller now passes **30 cases and 62 nested subtests
in each independent fake run**, with zero failures or skips. Admission `7316e53`
binds both inputs; root `50475b` verifies identical results and source hashes.
The two added cases cover probe ordering and each refusal position. The one
native02 observation admitted at `d1b0e61`, accepted at `99ce3c9`, returns
outer/controller exit 0.
Root `4b342d` and independent `f633ad` confirm all ten write observations, retained
primary exit 1/job count zero, fifteen retirement events and five journal frames.
All 160 native/integration evidence payloads match Git and disk. The child-final
receipt is absent, and no ordinary parent-guard claim is made. This qualifies
the fixed generated interruption only; real models and production migration
remain open. Native01 stays failed.
See [the focused qualification](ASTRA-PRELOCK30-QUALIFICATION-VERDICT-2026-09-14.md).
See [the native02 verdict](ASTRA-INTERRUPTED-NATIVE02-VERDICT-2026-09-14.md).

The following protected-constructor proposal failed source review at `22949dc`.
Ownership scope and retention, namespace authority, fallback and test-setup
defects remain repair work. Its 13 proposed checks were not executed. See
[the constructor review](ASTRA-PROTECTED-CONSTRUCTOR01-FAILURE-2026-09-14.md).

The smaller generated ownership repair passes **39 cases in each independent
copy**, with zero failures or skips. It preserves the original 33 cases and
retains returned constructor objects before later fallible steps. Both copies
have matching case results and all 38 child-source hashes, with ten valid guards.
These checks use inert objects and supply no separate subtest count. Real
namespace authentication and fixed backend construction remain the next work.
See [the ownership verdict](ASTRA-ENGINE-FAKE39-VERDICT-2026-09-14.md).

The dormant reliability caller now passes **11 cases and 15 subtests in each
independent copy**, with zero failures or skips. The results cover request
options, word normalization, context lifetime and cleanup with inert services.
Real media issuance, compute-policy binding and two legacy test contracts remain
open. Production is unchanged. See [the caller verdict](ASTRA-RELIABILITY-FAKE11-VERDICT-2026-09-14.md).

The completion-language extension passes **59 cases and 29 subtests in each
independent copy**, with zero failures or skips. All46 existing lifecycle cases
are preserved. The new checks cover session-bound metadata, closure, revocation
and failure handling with inert ports. An authenticated backend response and
real controller registry are still required; this is not a real transcription
or release measurement. See [the metadata verdict](ASTRA-COMPLETION-FAKE59-VERDICT-2026-09-14.md).

Ryan's approved D1 static checkpoint inspection is recorded at `4b38948`. One
guarded invocation verified the fixed hash, ZIP inventory and version bytes,
and found little-endian consistency in the two selected buffers. Only 1,002
payload bytes were interpreted; no pickle evaluation, conversion, model or
download ran. This resolves the inspection step. It does not authenticate the
writer, qualify other storage values or approve model/runtime execution.

The dormant D2 conversion adapter is qualified at `017b559`: two copies pass
the same 23 generated cases, with zero failures/errors/skips and valid guards.
All 124 proof payloads match Git/disk. Those checks did not exercise the real
conversion or model runtime. Ryan subsequently approved the exact local-only
conversion: actual2827f8 returned outer/parent/child0, with valid guards and one
checkpoint read. It produced54 ranges from23 storages in a5,896,708-byte file;
the parent verified output SHA8c15e718b6d502e7e351761f6cfee1a6917450e03c9a4c5318bc0d41d3fdd8c4.
Root948c0d confirms the receipts and unchanged inputs. Evidence atd13534f has64
payloads matching Git/disk. D2 local conversion is complete within Ryan's approved
scope. No model/reader activation, fetching or redistribution occurred. Native
model compatibility and release suitability remain unqualified.

Package 08 remains the latest built and installed review artifact. It includes
the native note and saved-media repairs at `d2caac5` and `60d203f`; its source
is `b8e44fb`. Its recorded installation, browser, CLI and native Uoink checks
apply to that package. The newer source has not been packaged or installed,
and no ordinary upgrade or public download is approved.

The library supports evidence retrieval, reviewable shelf proposals, consented
standing capture, native resources and prompts, an optional file mirror,
descriptive activity reports, and chapters with cited ranges. No main merge or
publication occurred. Installation is not a security certification.

Source work after package 08 includes signing receipts at `0b3629d`, the
accepted local NLTK wheel at `52d9f7d` and installer binding at `07084fe`,
owner/process repairs at `ff67b84` and `747fb6b`, and the ASR cache-consent guard
at `b96dbd0`. These changes are covered by the latest complete source tree.
The combined tokenizer and Hub-argument derivative now builds identically under
Python 3.13 and 3.14; it remains uninstalled. The fixed VAD factory and schema
are reviewed proposals. D2 local conversion is complete as recorded above;
reader/model integration and runtime qualification remain open.
The latest completed authorized branch-only backup is verified at `7f142e8`.
Later commits require a separate verified backup; no candidate-branch push,
main merge or publication follows.

The ASR manifest resolver and plain-state reader now pass 87 and 82 synthetic
cases respectively in both author and independent runs (`e6a2394`, `e826407`).
Their real asset/runtime paths remain disabled. Gemini's three-component source
review and Astra's qualified acceptance are archived at `a2e6e7c`; that review
adds no native model or installation result. The same commit records the Torch
source comparison and required pre-import controls. Real reader/model integration,
owned runtime services and numerical qualification still need to be completed.

The proposed ASR adapter and tensor bridge now pass 58 and 61 distinct cases
respectively in both author and independent runs. These use simulated services
and generated bytes; they do not exercise real model loading. The dormant D1
runner repair is qualified at `f0602f8`, and bridge evidence is committed at
`2b9068a`. The ASR runner's earlier null exit record remains failed, with its
diagnosed repair and fresh results retained. Protected real-model loading and
integration of owned runtime services with the WhisperX derivative remain open.
Gemini's follow-up source council is integrated at `cf5614d`; Astra accepts
its three limited-scope verdicts with documented corrections. It adds no native
execution, package, installation or market-readiness result.

The concrete CPU tensor port at `3801cee` passes 60 simulated cases in each
independent run, with all ten final guards intact. Its proof and
[Astra verdict](ASTRA-VAD-CPU-PORT-VERDICT-2026-09-13.md) preserve exact source
and outcomes. Native Torch behavior and factory independence remain untested;
the real entry point stays closed. These CPU-port checks do not qualify the
Windows worker or owned WhisperX runtime integration.

Owned WhisperX and lifecycle contracts are now integrated at `1935012`.
Each independent run passes the same 50 WhisperX and 46 lifecycle cases;
the original failed setup attempts remain preserved. Their 217- and 98-payload
proofs match Git and disk. These simulated checks cover ownership, output and
cleanup behavior. Later generated Windows observations are separate; real-model
compatibility and installation remain open. This does not approve release or
website/marketing work.

The exact owned WhisperX text wheel is built and independently byte-verified
at `93f4996`: 134,793 bytes, 22 members, both native build/verification exits
zero. Its [packaging verdict](ASTRA-OWNED-WHISPERX-BUILD-VERDICT-2026-09-13.md)
preserves the actual receipts. It has not been imported or installed and adds
no native-model acceptance. The later combined compatibility graph is recorded
below.

The concrete VAD factory and model registry at `803df4b` pass 59 simulated
cases independently in both roots. Registration now precedes the owned VAD
guard, failed construction revokes its authority, and an expired reference
cannot authorize a repeated release. The [factory verdict](ASTRA-VAD-FACTORY-PORT-VERDICT-2026-09-13.md)
records the remaining native and worker requirements. Gemini's review of these
components, the lifecycle and owned WhisperX is integrated at `488a7fd`.
Astra accepts its limited source verdicts with three wording corrections;
all 99 evidence payloads match Git and disk. This is component agreement,
not approval of the unfinished runtime, installation or market release.

Windows protocol and pipe contracts are accepted at `9c40271`: 54 simulated
cases pass independently in each root. The fourth actual Windows worker test
passes its generated-data communication, inherited file protection and shutdown
checks. Three earlier setup failures remain retained; those successful checks
do not qualify failure cleanup or actual model behavior. Exact local NLTK metadata
is accepted
at `e5b1ddd`. These observations do not clear the current installer or release.

The later timeout repair at `0d93186` retires confirmed broken-pipe I/O while
preserving logical quarantine. Child adoption at `428707d` verifies identity
before generated-file reads. The adapter at `d58bebe` passes six connected
cases per root. Two Windows observations at `7fba83a` then verify generated
stream completion and cancellation, with actual child exit before guard release.
They use a sentinel profile. A further observation at `7ced134` enters the
proposed adapter's actual session and cleanup methods through generated authority
seams and passes its Windows stream check. Later generated retired-owner recovery
is recorded above; crash/restart recovery and real transcription remain open.
No production runtime authority was enabled.

The repaired metadata checker rejects the earlier upgrade proposal: five
WhisperX conflicts, two missing dependencies and three wheel failures, including
a yanked Transformers release. That result does not establish that a different
migration is impossible. See the [captured graph verdict](RUNTIME-GRAPH-BOUNDARY-REVIEW-2026-09-12.md).
The later candidate02 graph has 144 selections, 282 active edges and zero
missing targets, but still fails five WhisperX caps and two source-only wheel
checks. Its exact-version advisory observation has one raw entry/one alias
group; that is an uninstalled proposal, not clean-security credit for the
shipping runtime. See [the current security scope](ASTRA-RUNTIME-SECURITY-SCOPE-2026-09-13.md).
Candidate03 at `4827288` removes those version conflicts using the exact local
derivatives. Its complete graph remains **FAIL**: 144 pins, 287 active edges,
zero conflicts or missing targets, and two source-only wheel gaps. Its final
metadata interface passes the same 59 cases in each independent root. Existing
cached ANTLR 4.9.3 and proxy-tools 0.1.0 wheels now pass whole-file and complete
RECORD verification at `95a7f29`; that inspection did not supply their missing
license texts.
The later source-notice evidence at `d887f8a` preserves both complete upstream
texts and the proxy-tools MIT/BSD metadata conflict. The five-record checker
at `616f670` passes 68 cases in each independent run; its fresh complete graph
passes with 144 pins, 287 edges and no diagnostic gaps. The earlier failed
graph remains unchanged. Missing Requires-Python declarations stay null, and
metadata closure does not establish runtime compatibility. See
[the candidate03 verdict](ASTRA-RUNTIME-CANDIDATE03-GRAPH-VERDICT-2026-09-13.md)
and [the five-record graph verdict](ASTRA-FIVE-WHEEL-GRAPH-VERDICT-2026-09-13.md).
Gemini's next council review is integrated at `ca61046`, with Astra's three
documentary corrections. It accepts the Windows timeout/adoption, connected
adapter and graph/notice components within their measured scope. It adds no
wheel-signature requirement and grants no market acceptance.
The last reviewed public GitHub release was v3.7.0; branch backup did not
publish 3.8.0.

## Package and verification

| Item | Recorded value |
|---|---|
| Installer | Uoink-Setup-3.8.0.exe, package-08 |
| Build and complete-tree source | `b8e44fbc0a16950a22b29ead66951fcb80b2d6e8` |
| Bytes | 389,570,940 |
| SHA-256 | `69a5394d842dc7fb5ac770d65954894231b03533bc99db922f34793f372fd06c` |
| Bundled runtime | Python 3.13.15, MCP 1.28.1, schema 30 |
| Build interval, UTC | 2026-09-12T18:37:24.8886211+00:00 to 2026-09-12T18:44:18.8153632+00:00; 413.928 seconds |
| Complete-tree result | 2,579 passed, 1 historical failure, 2 skipped; 2,582 cases |
| Actual installation | Same-account Agent Install 08: Setup/reinstall exit 0; all 32,497 files match |

The [package seal](proof/candidate-package-08-2026-09-12/SHA256.json) records
32,506 compiler inputs: 32,497 installed destinations, eight wizard images and
one setup-only script. All 142 source bindings match. The installed comparison
matches all destinations and accounts for three expected generated files.
All 140 runtime pins and 283 active requirements match, as do 983 compared
repair-wheel payloads. Installation-rewritten RECORD files are excluded explicitly.

Fifty license fields use exact packaged License-Expression metadata; seven
missing declarations stay unknown. Original generated notices are retained.
Notices are outside the installer payload. No packaged source changed after
the full tree. See [the package verdict](ASTRA-PACKAGE-08-VERDICT-2026-09-12.md)
and the [runbook](INSTALL-RECEIPT-RUNBOOK-2026-09-09.md). Preserve completed
agent stages and earlier installers/ZIPs.

## What the phases deliver

| Phase | Delivered behavior | Scope and limits |
|---|---|---|
| 0–1: capture and evidence | Health/doctor reporting, capture registry and CLI repairs, Unicode search, clip retrieval, canonical evidence cards, source/timing provenance and opt-in Recall context | Historical foundation acceptance retains its recorded exceptions; the watchdog still requires an owner action |
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
| Unicode search | `41c0d1d` | 137 passes in each root with original assertions and explicit --runxfail; 18 new retrieval regressions |
| Capture revision and recovery display | `15e3f7e` | 316 passes / one historical AT6 failure in each root; real JavaScript renderer and new installed browser review |
| Lightning 2.6.6 | `63f7de9` | 16 passes in each root; three native overlay checks; both verified wheel payloads match staging |
| Required setuptools runtime and notices | `9ea755b` | 19 passes in each root; final 140-pin / 283-requirement graph has no missing edge |
| SQLite deadline cleanup | `d812785` | 97 passes in each root; four old-code failures / one pass, then all five regressions pass in the complete tree |
| Native note display and readiness | `d2caac5` | 60 passes in each root; 16 new negative/positive cases, original worker shortcuts rejected |
| Saved media details and truthful timing | `60d203f` | 58 passes in each root; 23 new cases cover authenticated bounded reads, stale selection, private metadata and unsupported timestamps |
| Local NLTK path-policy wheel and installer binding | `52d9f7d`, `07084fe` | 43 wheel checks and 51 binding checks in each root; local version 3.10.3+uoink.pathsec1 remains explicitly labeled |
| Mirror owner reservation and process authority | `ff67b84`, `747fb6b` | All 50 prior mirror failures pass in tree09; final process union has 233 passes in each root |
| Complete local ASR cache before construction | `b96dbd0` | 144 focused passes plus 13 subtests in each root; synthetic cache/constructor seams, no model execution |

Gemini's cache review is integrated at `9d25ed`. Its empty-buffer finding is
repaired in the inert B2 tokenizer derivative, with ten synthetic cases passing
in author and independent runs. The original B1 boundary result remains six
passed/four failed. The Windows casing finding was rejected after a native
Path equality probe disproved its premise. See [Astra's disposition](ASTRA-ASSET-COUNCIL-VERDICT-2026-09-13.md)
and [the unapplied B2 scope](ASTRA-COMPANION-B2-PREPARATION-VERDICT-2026-09-13.md).

The B2 builder passes 62 synthetic cases independently in both runs. Actual
Python 3.13 and 3.14 builds produce the same 1,387,859-byte wheel, SHA256
`d64027be41a352117199ecedfa1e9eed48d323140aa4e2c77065111f288b7883`.
All 16 members and RECORD pass byte checks; the license and opaque ONNX asset
are unchanged. The private Python 3.13 runtime uses verified no-site startup.
No package or model was imported or installed. This qualifies packaging only.
See [the reproduction verdict](proof/companion-b2-reproduction-2026-09-13/VERDICT.md).

The combined B3 derivative includes both the tokenizer repair and the one-line
Hub-argument removal. Its 68 synthetic cases pass in both independent runs.
Actual Python 3.14/3.13 builds each produce 1,388,022 bytes, SHA256
`97bdde2d33fe71660b4cf8a318853e2e1b647ad900918e7e24397990162f29e4`,
with all exits zero and identical output bytes. All 16 members, RECORD, license
and opaque asset checks pass. This localassets2 wheel is uninstalled and does
not qualify the target dependency stack. See [the combined packaging verdict](proof/companion-b3-reproduction-2026-09-13/VERDICT.md).

Bounded static inspection of the packaged VAD checkpoint is archived at
`01163e1`. Runs01/02 refused; reviewed runs03/04 completed without constructing
objects or tensors. PyanNet literals alone do not establish configuration,
provenance or compatibility. The fixed-loader draft remains unqualified.
See [the static evidence verdict](ASTRA-VAD-STATIC-PREPARATION-VERDICT-2026-09-13.md).

The later selected-root diagnostic at `ba8d2c8` preserves the strict cycle
refusal and actual reader/outer exit 2. Its separately validated acyclic closure
contains 1,069 nodes and 54 tensor argument descriptors, with recorded model
configuration available as partial, untrusted metadata. Both synthetic runs
pass 63 cases. No object, tensor or model was constructed; provenance and
native compatibility remain open. See [the projection verdict](ASTRA-VAD-SELECTED-PROJECTION-VERDICT-2026-09-13.md).

The subsequent fixed-factory proposal at `de07dfe` maps all 54 declarations
across 23 storage groups and explicitly records its proposed version bridge.
Independent review found no schema mismatch. That proposal has not loaded model
data. The later D1 inspection and D2 local conversion above complete only their
approved steps; native factory integration and numerical qualification remain
open. See [the factory verdict](ASTRA-VAD-FIXED-FACTORY-VERDICT-2026-09-13.md).

Package 08 contains Pillow 12.3.0, MCP 1.28.1, cryptography 50.0.1 and NLTK 3.10.3.
The September 11 exact-version OSV observation of all 140 top-level pins retains
**19 advisory entries / 15 alias-connected issues across four packages**. The
earlier baseline had 95 entries / 55 issues across seven. The new raw scan is
not clean; Lightning's verified code repair is documented separately from its
inconsistent advisory record. A separate query of the 12 distributions vendored
inside setuptools returns zero entries. This does not cover every native or
embedded library. See [the fresh audit and graph](proof/repaired-lock-audit-2026-09-11/SHA256.json).

| Retained package | Distinct issues | Applicability and repair limit |
|---|---:|---|
| Lightning 2.6.6 | 1 raw scanner group | Both namespaces contain the verified upstream instantiation checks; OSV still reports an inconsistent 2022.6.15 fixed event. Raw findings are retained, without a clean-scan claim |
| NLTK 3.10.3 | 1 | Model-artifact path APIs remain affected; the observed Uoink/WhisperX sentence-tokenization call path does not expose those APIs |
| Torch 2.8.0 | 8 | WhisperX's published dependency constraint prevents a direct move to the patched newer line |
| Transformers 4.57.6 | 5 | Patched 5.x needs a Hugging Face Hub version incompatible with the current WhisperX constraint; affected model/training/export APIs are not first-party Uoink call sites |

Ordinary transcription uses PyAnnote voice detection and loads a checkpoint
packaged with WhisperX. Disabling speaker attribution does not bypass every
checkpoint loader. The new package contains the same 17,719,103-byte checkpoint,
SHA-256 `0b5b3216d60a2d32fc086b47ea8c67589aaeb26b7e07fcbe620d6d0b83e209ea`.
No model download, checkpoint inference or diarization was run for this
verification. The Lightning overlay checked refusal behavior and imports,
not actual checkpoint compatibility; it retains one denied socket.bind attempt.
The September 12 Gemini backport review is integrated at `43b42bc` after
Astra corrected unsupported reachability claims. Separating the verified Lightning
patch leaves 18 entries / 14 groups; the raw 19 / 15 is retained without suppression.
Default VAD reaches weights_only=False before the speaker branch. That trace
does not prove every advisory is reachable. Safetensors is already installed;
simply switching a loader flag is not a qualified migration.

The remaining migration needs Ryan's exact authorization for the frozen Torch
2.8.0 / WhisperX 3.8.6 compatibility assertions and an isolated checkpoint/model
qualification protocol. Current scope prohibits that execution. No unverified
version list or proposed test weakening is adopted. Read
[the corrected feasibility review](ASTRA-SECURITY-BACKPORT-REVIEW-2026-09-12.md).
Remaining model-loader advisories require a release decision. See the
[current Lightning verdict](ASTRA-LIGHTNING-266-VERDICT-2026-09-11.md),
[corrected Gemini review](ASTRA-DEPENDENCY-CLOSURE-REVIEW-2026-09-11.md) and
[earlier reachability analysis](ASTRA-DEPENDENCY-SECURITY-VERDICT-2026-09-09.md).

Defender's custom scan of this exact new EXE exits zero and reports no threats;
its before/after hashes match. The EXE is unsigned. Antivirus, firewall and
cloud/sample policies were not changed. A no-threat scan does not prove absence
of exploitable defects. Exact pinned versions are recorded, but the dependency
resolver does not use wheel download hash locks.

The reviewed install uses a separate app/data path and credential namespace in
the existing non-elevated Windows account, with a separate uninstall entry and
Start Menu group. It does not sandbox same-user malware. Sky's app inventory returned no Windows Sandbox entry; no separate account/VM
is prepared. This does not establish that every VM option is unavailable. No
elevation, system-feature installation or protection downgrade was used. Actual receipts retain the real account identity and effects.

## Current package-08 installed observations

Setup and same-version reinstall each exit zero. All 32,497
installed destinations match the seal, with 3 recognized generated files.
Observed ordinary registry, startup and shortcut state is unchanged. This is a
separate app/data/credential namespace in the same non-elevated Windows account.
The earlier isolated package-07 app was uninstalled; its receipt profiles remain.

C22 retains 11 passed, 0 failed
and 3 unexecuted manual placeholders. The separate
Setup and four actual browser images support the independent review. Consent,
charge and worker_lost recovery state agree before viewing, afterward and after
stop. Raw placeholders remain unchanged. Installed synthetic decoder and
encryption checks pass with exact restoration of temporary instrumentation.

The Phase 4 collector retains 15 passed, zero failed, one blocked, five unobserved
and two pending-review rows. Two actual CLI sessions each have 20/20 exact packet
comparisons. Native prompts and the production-published chapter export have
separate observed results. The five actual subscription sessions record
44 calls and 44 successful terminal
hooks, with 0 failed hooks and zero sentinel calls.
Sentinel discovery requests (15) are separate from calls.
The client Recall hook is silent in 47.6993 ms, with no diagnostic cause recorded;
it establishes no positive context injection. Its raw replacement-index field
measures file presence, and the fixture creates that database beforehand. The
separate missing-index scenario passes in 48.3258 ms without creating a replacement.
See the installed verdict for this correction to the original timing description.

The fresh native Uoink GUI observation is reviewed separately in
[the native verdict](NATIVE-GUI-PACKAGE-08-OBSERVATION-2026-09-12.md).
It uses the installed dashboard, a new synthetic profile and port 18484.
Its original images and action records establish only the enumerated flows;
no native AI-client citation, brief or chapter-player interaction is inferred.
The original package-07 note/media defects and Desktop failure stay retained.

See [the installed verdict](ASTRA-INSTALLED-PACKAGE-08-VERDICT-2026-09-12.md),
[installed proof](proof/ryan-agent-installed-08-2026-09-12/SHA256.json) and
[native proof](proof/native-gui-package08-2026-09-12/SHA256.json).

## Desktop isolation incident and acceptance boundary

The earlier Claude Desktop attempt was not isolated as claimed. Packaged Claude
discarded the proposed user-data override and launched the ordinary Uoink and
filesystem connectors. Their earlier live-index or port-5179 effects are unknown.
The owned job was empty and the test interpreter guard restored afterward;
those cleanup facts cannot establish absence of earlier effects. Astra told Ryan
and withdrew the claim. No live-index, ordinary auth/config or resident-port
probe was made to investigate.

The package-08 native driver exposes only the separately guarded Uoink dashboard.
Desktop GUI acceptance remains blocked until a supported isolation method is
verified before launch, or a clean separate Windows account/VM is prepared with
only the test connector and human sign-in. Do not bypass vendor checks or reuse
the failed override. The verified CLI configuration path remains a separate
CLI observation. Read [the incident](NATIVE-CLIENT-ISOLATION-INCIDENT-2026-09-12.md)
and [Astra's correction of Gemini's review](ASTRA-NATIVE-CLIENT-ISOLATION-REVIEW-2026-09-12.md).

## Historical package-07 installed observations

Setup and same-version reinstall each exit zero. All 32,497 installed files
match; ordinary observed registry/shortcut state is unchanged. This is a separate
app/data/credential namespace in the same Windows account, not an ordinary upgrade.
C22 records 11 passed, zero failed and three raw manual placeholders. Separate
Setup and four original dashboard images support the independent installation/
visual verdict. Consent revision, charges and worker_lost recovery match unchanged
before/after/stop state. Owned children are gone and runtime guards restore exactly.

The original Phase 4 collector records 15 passed, zero failed, one blocked,
five unobserved and two pending-review rows. Independent review of the two actual
client sessions finds 20/20 exact packet comparisons each, no missing fields
and no frame faults. Both native prompts pass separately. The raw combined
client flags remain false; client template discovery and GUI citation/brief/
chapter interactions are not established. Recall's 93.5668 ms silent result
does not establish positive context injection. The earlier prose attributing
that silence to unavailable storage is withdrawn; a silent hook alone does not
identify its cause. The separately declared missing-index scenario is distinct.

The separate production-publication scenario exports its stored synthetic cue,
chapter and current revisions successfully after a measured 2.100142-second
protocol delay. The actual client's first export also succeeds; its own delay
was 1.985696 seconds and is not counted as the greater-than-two-second probe.
Speaker labels and unsupported seek fields remain absent/null. Recorded main-
database, item and configuration hashes match; WAL/SHM files were not separately
frozen. No source fetch, inference or original P4 fixture edit occurred.

Five actual subscription sessions have 44 tool calls and 44 successful terminal
hooks, with no sentinel call. Fifteen sentinel discovery requests and three
synthetic permission probes are separate. Prepared configuration/sentinel hashes
match and all owned runtimes restore. This is bounded hostile-input evidence,
not a universal security guarantee. Raw model cost fields are list-price estimates,
not billing receipts. Authentication and extra-paid-usage-off are already resolved.

The [installed verdict](ASTRA-INSTALLED-PACKAGE-07-VERDICT-2026-09-12.md) and
[480-payload proof](proof/ryan-agent-installed-07-2026-09-12/SHA256.json) retain
the raw statuses, actual frames, images, independent review and one corrected
evidence-reader path error. No product observation was rerun for that correction.

## Historical package-06 installed observations

Actual Setup and same-version reinstall each exit zero in **Agent Install 06**,
outside the checkout under the same non-elevated Windows account. All 32,497
installed file hashes match. The only three extras are Inno's uninstaller/data
and the isolation marker. Actual shortcut targets, separate uninstall entry and
empty Tasks settings match the reviewed installer. Ordinary observed settings
are unchanged. The OneDrive-redirected Desktop is recorded by metadata without
traversing its contents; no desktopicon task was selected.

Installed C22 records **11 passed / zero failed / three unexecuted manual
placeholders**. Every owned child is confirmed dead. No unexpected helper errors
remain, and guard/interpreter bytes are restored. The raw placeholders are not
rewritten by the separate Setup and visual observations.

The independent browser review **passes**. Actual PNGs show consent on at rev 1,
enrollment 1/25, one charged start out of ten, the settled worker_lost failure
and eligible retry at attempt 1/3. Activity shows zero running or queued jobs.
The same persisted state is unchanged before viewing, after viewing and after
stop; only labels and timestamps differ. Original images and UTC records are
retained. The helper exits zero, frees its port and restores its startup bytes.
The old package-05 partial visual receipt remains partial in its own archive.

Installed image/encryption and product-loader WAV observations pass with
temporary no-site instrumentation and byte-exact restoration. These establish
instrumented decoder compatibility. No model or checkpoint inference occurred.

The actual installed Phase 4 route observes 32 tools, five resource templates
and four prompts. Collection records **15 passed / zero failed / one blocked /
seven unobserved**, with zero product findings. Native packets/prompts,
reconnect, storage refusal, Recall silence, protected bytes and mirror/deletion
checks have separate executable evidence. The blocked row carries X's prior
403 disposition without a new fetch. The collector's overall installed_credit
stays false because client acceptance is incomplete. Terminated transport exit
one remains recorded; no graceful client exit is claimed.

A separate **p4-client/profile** subsequently completed isolated subscription
sign-in, and Ryan confirmed extra usage off. Six actual client sessions are
retained in the September 12 addendum: 45 successful and three failed tool
events, with no sentinel calls. No ordinary credentials were copied. The raw
collector's seven unobserved rows remain its original result: local citation,
brief and chapter visuals, optional
external player navigation, hostile client actions and ordinary/Recall client
streams. They are not seven newly failing product features. The prior BD-27
player observation remains historical; no external source was fetched again.

See [the 300-payload installed seal](proof/ryan-agent-installed-06-2026-09-11/SHA256.json)
and [Astra's installed verdict](ASTRA-INSTALLED-PACKAGE-06-VERDICT-2026-09-11.md).
The export's first relative-path refusal and all earlier package-05 failed or
partial attempts remain retained. The corrected export reran no product test.

Same-version reinstall does not establish an ordinary or cross-version binary
upgrade. The isolated route skips the ordinary upgrade-preparation script;
legacy-data migration is a separate C22 observation. Synthetic acquisition,
transcripts and prepared P4 evidence stay labeled as fixtures.

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
| `56d9d4c` (explicit --runxfail; 13 passing subtests separate) | 2,796 | 1 | 3 | 0 | 1521.100 |
| `b8e44fb` (explicit --runxfail) | 2,579 | 1 | 2 | 0 | 1473.237 |
| `a25e3be` (explicit --runxfail) | 2,556 | 1 | 2 | 0 | 1500.638 |
| `6a89189` (explicit --runxfail) | 2,540 | 1 | 2 | 0 | 1779.570 |
| `6697dff` (explicit --runxfail) | 2,535 | 1 | 2 | 0 | 1452.312 |
| `393010f` | 2,493 | 1 | 2 | 1 | 1451.129 |
| `9a62e84` | 2,489 | 1 | 2 | 1 | 1464.698 |
| `7109182` (monolithic) | 2,484 | 3 | 2 | 1 | 1568.94 |
| `80a4fa8` | 2,451 | 1 | 3 | 1 | 1427.78 |
| `12ce8a5` | 2,429 | 13 | 3 | 1 | 1542.35 |
| `8fc6a40` | 2,254 | 10 | 3 | 1 | 573.49 |
| `263b7e4` | 2,193 | 9 | 3 | 1 | 728.37 |

Tree09 accounts for all 2,800 collected cases, with only the existing S21 file
excluded. Its 13 subtests are additional outcomes, not extra collected cases.
Main and media pytest times were 1,505.07 and 4.12 seconds; the table records
aggregate wall time including collection. The overall result is FAIL. See
[the complete tree09 verdict](ASTRA-COMBINED-TREE09-VERDICT-2026-09-13.md).

Package 08 accounted for all 2,582 cases once: the prior 2,559 plus 23 media regressions,
with none missing. The aggregate remains FAIL because the historical AT6 exit
assertion fails. Existing tests and fixture guards are unchanged. See
[the qualification verdict](ASTRA-PACKAGE-08-VERDICT-2026-09-12.md) and
[tree seal](proof/ryan-final-partitioned-06-2026-09-12/SHA256.json).

The original AT6 shell wrapper discarded the child exit status. Recovered
artifacts and a successful replacement AT7 cannot recreate that old status;
the original audit assertion remains failed. SEC-06's original Unicode assertions now pass. Its strict expected-failure
marker was not edited: the earlier normal focused run therefore retains a
strict XPASS failure. The new complete run explicitly uses --runxfail to execute
the unchanged assertion bodies. This is a new measurement, not a rewrite of
the old xfail. Platform-specific skips remain disclosed.
See [final verification](FINAL-RELEASE-VALIDATION-2026-09-09.md).

## Open release decisions and limits

- Ryan's disposition of the missing historical AT6 exit and retained dependency
  advisories; neither is presented as a pass or clean security clearance.
- D1 inspection and D2 local conversion are complete only within their recorded
  approvals. D3 fetching and D4 stack/native execution remain unapproved. The
  exact migration patch, artifact/loader policy and quality protocol still need
  review and Ryan's decision; no target stack is approved.
- The latest production source change is `71d3e70`. After runtime integration, a fresh committed
  full tree, rebuilt/resealed package, installed notice inventory and client
  checks are still required. Tree `56d9d4c` predates both later production repairs;
  package 08 remains `b8e44fb`, with no current-source package/install credit.
- Publisher certificate/identity and HTTPS timestamp service remain Ryan's
  choices. A clean standard Windows account or VM and normal Claude Desktop
  sign-in are still required; the failed profile override cannot be reused.
- Package-08 installation and bounded CLI observations are complete. Native Uoink dashboard checks are separate. Desktop citation/brief/chapter acceptance remains blocked by the documented isolation failure; positive Recall injection and per-session combined prompt/template completeness are not claimed.
- No speaker-attribution claims; speaker material stays blocked. Phase 5 Part B
  is deferred. The failed shelf-quality and dashboard-size measurements remain.
- Main merge and publication require Ryan's decision. Only the authorized
  `origin/cc/living-library` backup is pushed; no candidate-branch push or main
  merge is included.

The live index and resident port remain prohibited. The earlier Desktop attempt
violated the intended connector boundary; its prior effects are unknown as stated
above. No paid API, live label application, X access repair or new source-media
fetch is authorized by these instructions. The [handoff](ORCHESTRATION-HANDOFF-2026-09-08.md) retains each integration,
failed/partial observation and remaining action.

## Package-08 review kit

The verified kit is `build/Uoink-Living-Library-3-8-0-Review-Kit-08-2026-09-12.zip`,
438,081,038 bytes, SHA-256
`343afc763b724c2f5030e4b856081639b2dbf297006796836d1b43a7fa236130`.
All 3,659 ZIP and extracted payload hashes match. Review source `e1be40e` binds
build/validation source `b8e44fb`. It pairs the installer with matching notes,
receipt tools and evidence, with release_ready=false. Its external `.receipt.json`
and BUNDLE-SHA256.json bind the archive and payloads. This paragraph follows the
immutable ZIP. See [the delivery record](RELEASE-DELIVERY-08-2026-09-12.md).

## Historical review kit (package-07)

The local kit is `build/Uoink-Living-Library-3-8-0-Review-Kit-07-2026-09-12.zip`,
425,699,322 bytes, SHA-256
`7bd525f785f9ddaef2ec1b1e4317b5401eadfd9e083483d4b9ce5f61417206fe`.
All 2,603 ZIP and extracted payload hashes match. Review source `81e4495` binds
build/validation source `6a89189`. The kit contains the matching installer,
receipt tools, notes and retained evidence, with release_ready=false.
See [the delivery record](RELEASE-DELIVERY-07-2026-09-12.md). Its final transport
receipt lives beside the ZIP; only origin/cc/living-library is backed up.

## Previous review kit (package-06)

Review kit filename: `build/Uoink-Living-Library-3-8-0-Review-Kit-06-2026-09-11.zip`.
It is 417,747,018 bytes, SHA-256
`f1e14fcbeab1109f5708082fb404c1a94fdf4eb2a0dff371b8077da0443c8837`.
All 1,715 ZIP and extracted payload hashes match. Review source `8ea633c`
binds installer and validation source `6697dff`; see [the delivery record](RELEASE-DELIVERY-06-2026-09-11.md).
The accompanying `.receipt.json` records the ZIP hash, byte count and source
commits; `BUNDLE-SHA256.json` records every payload. It pairs package-06 with
the matching receipt tools, notices, notes and evidence, with release_ready=false.
The earlier package-05 EXE and review ZIP remain preserved. No ordinary upgrade,
main merge or publication is included in delivery.

On2026-09-14 the next real-constructor source proposal failed review after a
completed Gemini delivery. Its15 proposed tests were not executed. Qualified
generated ownership remains39/0/0 in each copy at9e3a77d. The new source's trust,
factory connection and retained-object defects must be repaired before runtime
qualification. Production and package status are unchanged; website and marketing
remain held. See ASTRA-REAL-ENGINE-CONNECTION01-FAILURE-2026-09-14.md.
