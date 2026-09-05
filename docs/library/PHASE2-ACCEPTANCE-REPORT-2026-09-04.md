Phase 2 stage 1 acceptance, run M — 2026-09-04

**REJECT — candidate `f53adaf3206c22dadb8cd3ba48546d3535245810`.** The substrate passes the measured P2-0 through P2-5 checks. The shipped adapters cannot call the real service: list, claim and dashboard confirmation return `internal_error`, and health hides ready work behind an error state. This is finding M-1 below. The installed-client and product-proof gates remain unverified.

I reviewed under ORCHESTRATION-V1 rule 4 and contract `phase2-v1.2-2026-09-04`. The worktree began clean at `12ba709df81f82230b704f9af58727280292dffd`; `git diff --name-only f53adaf HEAD` returned only `docs/library/PHASE2-ACCEPTANCE-BRIEF-2026-09-04.md`. The tested production code and prompts therefore match the candidate. No production code, prompts or active migrations were changed. All results below were rerun here; prior worker receipts are not substituted for observations.

The unchanged suite returned **888 passed, 3 skipped, 1 xfailed in 61.22 seconds**. After adding six acceptance checks, the full suite returned **4 failed, 890 passed, 3 skipped, 1 xfailed in 61.03 seconds**. All four failures reproduce M-1; the two new passing cases check default-off apply and privilege/origin refusals. The failures remain ordinary assertions, without xfail. The [evidence JSON](PHASE2-ACCEPTANCE-EVIDENCE-2026-09-04.json) records counts, hashes and raw-artifact fingerprints.

Commands ran from this dedicated worktree with Python **3.14.6** and SQLite **3.50.4**. Test data, output and temporary roots were isolated with this PowerShell environment. Python's existing user-site dependency location remained available; relocating `APPDATA` in the first launch hid pytest and produced `No module named pytest` before collection. That launch supplied no test evidence.

```powershell
$runRoot = Join-Path (Get-Location) 'tests/.acceptance-run-m'
New-Item -ItemType Directory -Force -Path $runRoot, "$runRoot/local", "$runRoot/data", "$runRoot/output", "$runRoot/temp" | Out-Null
$env:PYTHONPATH='.'
$env:PYTHONDONTWRITEBYTECODE='1'
$env:LOCALAPPDATA="$runRoot/local"
$env:XDG_DATA_HOME="$runRoot/data"
$env:UOINK_OUTPUT_DIR="$runRoot/output"
$env:TEMP="$runRoot/temp"
$env:TMP="$runRoot/temp"
```

S, unchanged candidate suite, exit 0:

```powershell
python -m pytest -q tests/ -p no:cacheprovider -rsx --basetemp=tests/.acceptance-run-m/suite-tmp --junitxml=tests/.acceptance-run-m/suite.xml
```

I, independent and integration checks, exit 0, **232 passed in 15.96 seconds**:

```powershell
python -m pytest -q tests/test_library_work_leases.py tests/test_library_work_validation.py tests/test_library_work_apply_undo.py tests/test_library_work_recovery.py tests/test_library_work_rulings.py tests/test_library_service_audit.py tests/library_work_astra tests/test_library_adapters.py tests/test_openapi_bridge.py tests/test_installed_library_runtime.py tests/test_installer_files_complete.py -p no:cacheprovider -rsx --basetemp=tests/.acceptance-run-m/independent-tmp --junitxml=tests/.acceptance-run-m/independent.xml
```

I comprises Gemini's **33** original cases plus **8** R1–R5 cases, Claude's **20** service-audit cases, Astra's **68** collected cases, **94** adapter cases, **5** HTTP-bridge cases, **1** installed-tree runtime case and **3** packaging cases. Astra's count includes tests imported into multiple modules; it is a pytest case count, not 68 distinct independent claims. Gemini and Claude provide independent evidence for Astra's implementation.

M, migration and staged-import measurements, exit 0, **8.572840 seconds**:

```powershell
python tests/phase2_acceptance_run_m.py --out tests/.acceptance-run-m/migration-final
```

M requires a new output directory on each invocation. Its first draft stopped at a schema assertion after finding schema 25 in the hash-verified duplicate. The final probe explicitly prepares schema 26 before measuring 0027; the successful results below come from that run.

R, real-module reproductions, exit 1, **4 failed, 2 passed in 0.83 seconds**:

```powershell
python -m pytest -q tests/test_phase2_acceptance_m.py -p no:cacheprovider --tb=short --basetemp=tests/.acceptance-run-m/repro-final-tmp --junitxml=tests/.acceptance-run-m/repro-final.xml
```

F, final suite including R, exit 1:

```powershell
python -m pytest -q tests/ -p no:cacheprovider -rsx --tb=short --basetemp=tests/.acceptance-run-m/final-suite-tmp --junitxml=tests/.acceptance-run-m/final-suite.xml
```

The `.log` files beside these XML files retain console output. The three skips are POSIX build-script execution on Windows, unavailable symlink privilege, and ffmpeg absent from PATH. SEC-06 remains the existing expected failure for non-ASCII FTS queries. None is counted as a pass.

| Gate | Expected | Observed on this tree | Result |
|---|---|---|---|
| P2-0 | Empty and populated schema 26→27; repeat open unchanged; FK/FTS/integrity; installed imports without checkout; zero work/assignments; failed migration rolls back. | M upgraded both databases to **27**, added **16** tables, preserved **548** populated items, and left **0 work / 0 memberships**. Repeat snapshots and file hashes matched. Integrity returned `ok`, FK violations **0**, both FTS checks passed. Injected SQL failure retained schema **26** and the complete pre-upgrade snapshot; retry reached **27**. **8** staged modules imported with the checkout absent from `sys.path`. I also passed **1** runtime and **3** packaging cases plus the adapter packaging assertion. | PASS for migration and staged packaging; no installer/GUI receipt claimed. |
| P2-1 | One winner for concurrent claim; distinct item rows; expiry boundary, capped renewal, release/cancel, three-claim ceiling; no model/network execution. | I: Gemini leases **9/9**, Claude A1–A4 **4/4**, and Astra connection/process contention cases passed. Two processes yielded **1** leased packet; exact expiry was rejected; renewal stayed within **3,600 seconds**; claim **3** exhausted the row. The independent no-model/network lease check passed. | PASS at service boundary. |
| P2-2 | Reject malformed identities/results, non-finite confidence, foreign shelves, joined-excerpt quotes and stale revisions without current labels; retain rejections; exact receipt retry; changed-key conflict. | I: Gemini validation **10/10**, Claude A5/A6 **3/3**, plus Astra strict-input/evidence cases passed. Invalid outputs left **0 current memberships**; stored rejection/retry assertions passed, including exact replay after expiry and `idempotency_conflict` for changed payload. | PASS at service boundary. |
| P2-3 | Full manifest dispositions; refuse incomplete or stale/altered previews; exact forward delta and idempotent apply; distinct-item churn, initial/empty cases and enforced 15% ceiling. | I: Gemini preview/apply **4/4** and Claude A12/A14 **2/2** passed. Astra's reconciliation case measured **3/10 = 30%** churn: refused at **15%** and **29%**, applied only with trusted **30%** approval; refusal changed neither projection nor operation sequence. Empty/initial and zero-delta cases passed; zero delta retained **1** projection revision while recording **2** operation receipts. | PASS at service boundary. |
| P2-4 | Preserve pins and stable identity through transitions; exclusive move; complete inverse; stale-undo refusal; session-bound, expiring, non-reusable intent. | I: Gemini pin/undo **4/4**, Claude A15–A17 and rename/activation **4/4**, and independent R1 unpin/undo **2/2** passed. A **300,000 ms** intent boundary expired; wrong session and stale undo were refused. Inverse checks restored membership, primary, activation and exclusive policy. R's two guard cases passed, but real dashboard minting failed M-1. | PASS for service semantics; adapter delivery fails M-1. |
| P2-5 | Process termination at all three durable boundaries; replay once with exact receipt/revision; visible corruption; disposable DB reconstruction retaining orphan pins. | I: Gemini recovery **6/6**, Claude B1/B3/B4/B6/B8 **5/5**, and Astra's external-kill cases passed at **3** boundary types. Before publication reopened at revision **0**; the two later boundaries reopened at **1**. Retry returned one operation/receipt at revision **1**. Reconstruction retained **1** orphan, then restored its locked membership/exclusive policy with **0** orphans after identity rebuild. R2/R3 independent recovery-state tests **4/4** passed. | PASS for tested process/storage faults; power-loss durability unverified. |
| P2-6 | Working registry/supported transports, common validation, visible waiting, installed client claim/submit/reconnect. | I's **94** stand-in adapter cases pass. R's real module fails list parity, claim, health waiting and intent minting: **4** failures. Stdio advertises **25** canonical tools and no Phase 2 tools, as run J's explicit exposure ruling permits. Installed client/restart/GUI was not run. | FAIL for current adapters; installed portion UNVERIFIED. |
| P2-7 | Frozen-copy model dry run, independent quality/evidence audit, complete manifest, byte/usage receipts, unchanged labels and default-off apply. | **0 model calls**, **0 proof runs**, no quality/coverage/token/cost result. The migration duplicates contain **0 memberships / 0 work**; this is migration evidence, not proof quality. | UNVERIFIED. |

The source was the explicitly named `C:/Users/hello/AppData/Local/AgentControlRoom/uoink-index-copy-2026-09-04-upgraded.db`, source date **2026-09-04**, **71,733,248 bytes**. Its SHA-256 matched `2765cc359805fb12f7a90aecd3dd0b34d884aa8cb3015785011bf400da3b4dfc` before copying and after measurement. SQLite opened only local duplicates. The live index, resident helper and other project checkouts were never opened.

The source bytes contain schema **25**, **548** items, **149,041** citations and **3,216** clips. Preparing schema 26 with the candidate's migrations through 0026 repaired clips to **3,705**. Both states contain **212** items with clips and **336** without clips; no card/provenance stratum classification is inferred from those counts. The measured 26→27 step preserves all three source-table hashes and every pre-existing table count except the added migration-version row. It creates only the singleton `library_meta` row among the 16 new tables; the other 15 tables start empty.

| Measured duplicate state | SHA-256 |
|---|---|
| Prepared schema 26 | `4fc3179cd1167a3a664ff2dce2f3837c2501ba4b09e10bc1092cc58262b824b2` |
| Schema 27 after upgrade | `fd9db30deea7695a339a07d41b559748fd5a91514bcff64d47e9bad25b867661` |
| Schema 27 after repeat open | `fd9db30deea7695a339a07d41b559748fd5a91514bcff64d47e9bad25b867661` |
| Empty 26→27, both initial and repeat open | `272bf8bec2141f27710bdf04c8a7002defda3d693ca578f106c8beaf9892c41b` |

Migration timestamps make these receipts specific to this run. Reproduction requires stable before/after comparisons within the new run, not these exact newly generated database hashes. The named source hash must match exactly. M also imported `index`, `library_work`, `library_cards`, `provenance`, `clips`, `server`, `uoink_mcp_tools` and `uoink_mcp` under `python -I` from the installer staging inventory, then opened a schema-27 fixture and called the real service successfully with apply disabled. This was a staged runtime smoke, not an installation or connected-client test.

M-1: shipped adapters use a different service interface.

At `uoink_mcp_tools.py:3033`, `_library_invoke` calls `fn(dict(args), context)`. The resolved module is the real `library_work`, whose exported functions take `(index, context, args)`; for example `library_work.py:1484` immediately calls `index.library_service()`. The dictionary consequently raises **`AttributeError: 'dict' object has no attribute 'library_service'`**. Health repeats the same call shape at `uoink_mcp_tools.py:3246`. The adapter also supplies a dictionary context; the service endpoint requires `RequestContext` (`library_work.py:170`). Correcting only the argument count would leave that second mismatch.

R seeds one real fixture item, an approved taxonomy and one ready row, then clears the service override and asserts the resolved module is `library_work`. Direct service listing succeeds with `run_revision=1` and `waiting_for_client=true`. The registry, HTTP `/tools/list_library_work`, and HTTP MCP `tools/call` all return the same `internal_error`. Claim also returns `internal_error`. The real health block reports `status=error`, `waiting_for_client=false`, `ready=0` despite the ready row. An authenticated, same-origin dashboard confirmation fails to mint a capability, although the identical operation/session passes the direct service control.

The HTTP handler is exercised in process using the existing request probe; this reproduction uses no listener, installed client or fake library service. It preserves real token/origin checks but does not independently exercise Host validation. The failure occurs inside the service call, after those checks. The **94** original adapter tests inject `FakeLibraryService`, whose `(arguments, context)` convention matches the adapter; they cannot detect this mismatch.

Route repair to the adapter owner. Resolve the real index/service, construct a trusted `RequestContext` with explicit authenticated client/session mapping, call the frozen `(context, args)` instance surface, and bind the apply setting through the same service seam. Keep user authority confined to confirmed dashboard operations. Verify real claim→submit→preview, mint→pin→undo, error parity, health and receipt replay before presenting a replacement SHA. This review does not implement or certify that repair.

The default-off checks pass: `server.py:872` defaults apply to false, normalization accepts only JSON `true`, dashboard settings cannot enable it, and R observes `apply_disabled` before the broken service call. Registry arguments containing `actor`, `operator` or `local_user_confirmed` are rejected. Wrong helper token, foreign origin and cross-site confirmation return **403** and mint **0** intents. The stdio inventory remains the permitted 25 tools; no Phase 2 mutation or intent-minting tool was added. Successful end-to-end capability consumption remains blocked by M-1.

I reviewed `8f43313c38062db0aacedae018c2bb85a880cb4b` in full. Its sole production edit changes direct `tools.LIBRARY_TOOL_NAMES` access to `getattr(tools, "LIBRARY_TOOL_NAMES", ())`, allowing older test doubles through the existing generic validator. The real module still supplies all six names and takes the strict validation branch. I reran **5** HTTP-bridge and **94** adapter cases, including malformed input and duplicate/non-finite JSON. No separate failing case was found for this edit; it does not repair M-1.

I reviewed the relocation recorded in `7893034`: package markers, the `conftest.py` path insertion, all relocated fixture/subprocess paths, and the three child programs. They resolve production imports from this checkout, use disposable `_work` roots, and execute the claim, exit and external-kill checks after relocation. **68** collected cases passed in I and again in F. The original ignored scratch files are not available as predecessor Git blobs here, so byte-for-byte equivalence to that unpublished source is not claimed. Acceptance uses the relocated tests as they exist on this candidate, alongside Gemini's and Claude's independent checks. The new 26→27 measurement also independently verifies migration behavior. No failure is attributed to relocation.

Run N first needs a repaired integrated SHA and a fresh affected-gate acceptance run. Keep `librarian_apply_enabled=false`. For P2-6, use the reserved Claude Code HTTP client against an isolated helper on **5180**, its own data root and dedicated Windows/browser profile. Build/install that candidate, drive the extension/dashboard, demonstrate actual claim/submission and reconnect after helper restart, show waiting with no client, open `search_clips`/`get_evidence_card` links, check capture deduplication and watchdog recovery. Record the installed version, transport, revisions and computer-use receipt. Never touch the resident helper on **5179**.

For P2-7, verify the named-copy bytes again and freeze the approved taxonomy, prompt/card/source hashes, manifest, client configuration, held-out IDs and labels before execution. Ratify the per-stratum sample sizes and **0.80 coverage / 0.90 precision** thresholds, keeping held-out labels out of prompts/examples/taxonomy definitions. Drive the full manifest through the real client with the reserved two-hour, subscription-only scope and at most one model-result retry; no paid API spend is authorized. Account for every target and failed attempt, independently audit quote identity and held-out judgments, and record exact input/output bytes, elapsed time and reported usage. Keep unavailable usage, estimates and paid cost separate. Verify memberships, pins, activation, projection revision and proof-created applies are unchanged. This review supplies no product-quality or cost measurement.

Status: review complete; replacement candidate required. Files added are this report, the evidence JSON, the migration/staged-import probe, six real-module acceptance checks and a scratch-output ignore file. Artifact syntax, JSON and whitespace checks passed. `git add` failed because Git could not create the shared worktree metadata's `index.lock` (`Permission denied`); all five files remain untracked and uncommitted for the integrator. No merge or push was attempted. The open action is M-1 repair followed by fresh acceptance; no clarification is needed to route it.

**REJECT — candidate `f53adaf3206c22dadb8cd3ba48546d3535245810`.**

## Run N re-acceptance — 2026-09-04

**REJECT — candidate `a6725de56b46f47563d7ccd3fe63834d3e114cb9`.** M-1's call-shape failure is repaired: all six original checks pass. A remaining session mismatch prevents the shipped pin and undo adapters from consuming dashboard capabilities or replaying their receipts. Six new failing cases establish N-1 below. P2-0 through P2-5 still pass at the service boundary; P2-6 fails on adapter delivery, and its installed-client portion and P2-7 remain unverified.

The worktree began clean at this candidate. Its only difference from repair commit `5f586ca09ebf14cdfd012ffcbe88530d38e4b94d` is the Run N brief. I reviewed that repair in full under ORCHESTRATION-V1 and contract `phase2-v1.2-2026-09-04`. No production code, prompts or migrations were edited. This review adds ten real-module test cases and lets the existing migration probe accept `--candidate`, preserving its Run M default so the new receipt names the tree actually reviewed. [Run N evidence](PHASE2-RE-ACCEPTANCE-EVIDENCE-2026-09-04.json) contains fresh measurements, test outcomes and artifact hashes; Run M's evidence is preserved.

N-1: dashboard minting and tool consumption use different sessions.

`server.py:613` derives the dashboard session from the per-install helper token. Minting passes that hash through `library_mint_user_intent` into `_library_dispatch`. At `uoink_mcp_tools.py:3044`, dispatch uses the hash when present, but otherwise falls back to the transport string. The common tool path at `uoink_mcp_tools.py:3094` supplies no session hash. Registry, HTTP `/tools/*` and HTTP MCP `tools/call` all reach the registry handler and therefore receive `session_id="registry"`. The real service correctly rejects that different session at `library_work.py:1084` and again during receipt replay at `library_work.py:1183`.

`test_dashboard_capability_consumption_and_receipt_replay` tests an exclusive move and an undo across all three paths. Each same-origin, authenticated dashboard request mints a valid token. Each first tool call returns `invalid_user_intent: Capability does not bind this operation and session`, changing neither projection revision nor operation sequence. The identical token and operation succeed through the real service with the dashboard session, advancing both counters exactly once. Tool retry then returns `invalid_user_intent: Original user session required for retry`; direct-service retry returns the exact original receipt. All six cases fail ordinary success/parity assertions, without xfail. These are disposable fixtures; the HTTP probe retains token/origin checks but bypasses Host validation and uses no listener.

Route N-1 to the adapter owner. Derive the same trusted helper/dashboard session at capability consumption and receipt replay, without accepting a session or authority override in tool JSON. Preserve refusal for another session and for token rotation. Rerun the six new cases, the original M checks and affected gates on the next integrated SHA. This review does not implement the repair.

Rule 1 routing was appropriate. Connecting the adapter to the frozen service signature and restoring a leaked test override are routine integration repairs. They do not change the contract, resolve a substantive dispute by preference, or substitute the integrator's receipt for independent acceptance. The reproduced N-1 failure is the reason acceptance remains withheld.

The rest of the repair review found:

- Authority comes from the adapter's trusted context: regular tool calls receive neither operator nor local-confirmation authority; health's server actor receives operator authority for `list_work`; the confirmed dashboard actor receives local-confirmation authority for minting. Caller-supplied `actor`, `operator` and `local_user_confirmed` are rejected, and wrong-token/foreign-origin/cross-site confirmations mint zero intents. `client_id` is copied from validated arguments and remains a client label under the shared helper credential; a distinct authenticated identity per client is not established by this mapping. Attempt-token and owner checks remain in the service.
- Real dispatch refreshes the cached service instance's apply flag from trusted settings. The new preview check observes enabled only for JSON `true`, then disabled for `false`, `"true"` and `1`. The default-off apply refusal still passes. An early apply refusal or cached health response can return without dispatching; the next real dispatch refreshes the instance. No apply bypass was reproduced.
- The `RequestContext`/`LibraryWorkService` attribute check selects the real module's `(index, context, args)` call. The injected stand-in keeps `(args, context_dict)`; callers cannot select that branch through JSON. Its 94 passing adapter cases remain fixture evidence. The five bridge cases pass, and the subsequent real-handler tests pass their M checks after the resolver is restored in `finally`.

All commands ran here with Python **3.14.6**, SQLite **3.50.4**, `PYTHONPATH=.`, `PYTHONDONTWRITEBYTECODE=1`, and `LOCALAPPDATA`, `XDG_DATA_HOME`, `UOINK_OUTPUT_DIR`, `TEMP` and `TMP` redirected to the corresponding `local`, `data`, `output` and `temp` directories under `_scratch/run-n`. Existing user-site dependencies remained available. Console logs and JUnit XML are retained there.

| Run | Command / scope | Observed |
|---|---|---|
| S | `python -m pytest -q tests/ -p no:cacheprovider -rsx --tb=short --basetemp=_scratch/run-n/suite-tmp --junitxml=_scratch/run-n/suite.xml`, before adding N checks | Exit 0; **894 passed, 3 skipped, 1 xfailed; 61.47 s** |
| I | Same independent test-file list as Run M's I command, with `--basetemp=_scratch/run-n/independent-tmp --junitxml=_scratch/run-n/independent.xml` | Exit 0; **232 passed; 16.07 s** |
| R | `python -m pytest -q tests/test_phase2_acceptance_m.py tests/test_phase2_acceptance_n.py -p no:cacheprovider -rsx --tb=short --basetemp=_scratch/run-n/repro-tmp --junitxml=_scratch/run-n/repro.xml` | Exit 1; **6 failed, 10 passed; 1.74 s**. M: 6/6 pass; N: 4 pass, 6 fail |
| M | `python tests/phase2_acceptance_run_m.py --candidate a6725de56b46f47563d7ccd3fe63834d3e114cb9 --out _scratch/run-n/migration` | Exit 0; **8.618457 s** |
| F | S command after adding N checks, using `final-suite-tmp` and `final-suite.xml` | Exit 1; **6 failed, 898 passed, 3 skipped, 1 xfailed; 62.27 s** |

I again contains Gemini's **33 + 8** cases, Claude's **20**, Astra's **68 collected cases**, **94** stand-in adapter cases, **5** bridge cases, **1** staged-runtime case and **3** packaging cases. Imported Astra tests count as collected cases, not distinct independent claims. The three skips remain POSIX build execution, unavailable Windows symlink privilege and absent ffmpeg; SEC-06 remains the non-ASCII FTS expected failure. None counts as a pass.

| Gate | Expected | Fresh observation | Result |
|---|---|---|---|
| P2-0 | Empty/populated 26→27, repeat stability, integrity, rollback, staged imports, zero work/assignments | Both duplicates reached **27**; **16** tables added, only `library_meta` initially populated. **548** items preserved; **0 work / 0 memberships**. Repeat snapshots and byte hashes matched. Integrity `ok`, **0** FK violations, both FTS checks passed. Injected failure preserved the entire schema-26 snapshot; retry reached 27. **8** staged modules imported with checkout absent from `sys.path`. | PASS for migration/staged packaging |
| P2-1 | Contention, distinct rows, exact expiry, renewal cap, release/cancel, attempt ceiling; no model execution | I passed **9** Gemini lease cases, Claude A1–A4 and Astra contention cases. Two-process contention produced **1** leased packet; expiry rejected at the boundary, renewal capped at **3,600 s**, and the third claim exhausted the row. No-model/network lease check passed. | PASS at service boundary |
| P2-2 | Strict identity/evidence validation, stored rejections, exact receipt replay and changed-key conflict | I passed **10** Gemini validation cases, **3** Claude A5/A6 cases and Astra strict-input/evidence cases. Invalid output wrote **0** current memberships. R's three real transport loops accepted valid evidence, replayed the receipt after expiry, rejected changed-key content and left **0** memberships. | PASS at service boundary and tested submit paths |
| P2-3 | Complete preview, stale/altered refusal, exact/idempotent apply, distinct-item churn and 15% ceiling | Preview/apply cases and Claude A12/A14 passed. Astra again measured **3/10 = 30%**, refused **15%** and **29%** approvals, and accepted trusted **30%** approval. Empty/initial and zero-delta cases passed; zero delta kept revision **1** with **2** operation receipts. R previews stayed default-off. | PASS at service boundary |
| P2-4 | Pin preservation, stable identity, exclusive policy, full inverse, stale undo and session-bound intent | Pin/undo, rename/activation and both independent R1 invalidation cases passed. **300,000 ms** expiry and wrong-session refusal passed. Full inverses restore membership, primary, activation and policy. N's direct controls advance revision/sequence once and replay exactly. Adapter consumption/replay fails N-1. | PASS at service boundary; delivery FAIL |
| P2-5 | Kill at three durable boundaries, replay once, visible corruption, DB reconstruction and orphan retention | Gemini's **6** recovery cases, Claude's **5** B cases and Astra's external-kill checks passed. Reopened revisions were **0 / 1 / 1** across the three boundaries. Retry produced one operation at revision **1**. Reconstruction retained **1** orphan, then restored its pin/exclusive policy with **0** orphans after identity rebuild. R2/R3 recovery checks passed. | PASS for tested process/storage faults |
| P2-6 | Working supported adapters, waiting state, installed claim/submit/reconnect | M now verifies real list parity, claim, waiting health (**1 ready**), and minting. R adds passing claim/submit/retry/preview on three paths. Pin/undo and their retries fail on all three. Stdio remains the permitted **25** tools without Phase 2 exposure. | FAIL N-1; installed portion UNVERIFIED |
| P2-7 | Frozen-copy model proof, independent quality/evidence audit, usage receipts and zero applied labels | **0 model calls / 0 proof runs**. No quality, coverage, token or cost measurement. Migration and fixture outcomes supply no product-quality denominator. | UNVERIFIED |

The named source was `C:/Users/hello/AppData/Local/AgentControlRoom/uoink-index-copy-2026-09-04-upgraded.db`, source date **2026-09-04**, **71,733,248 bytes**. Its SHA-256 was `2765cc359805fb12f7a90aecd3dd0b34d884aa8cb3015785011bf400da3b4dfc` both before copying and after measurement. SQLite opened only worktree-local duplicates. Source schema **25** contained **548** items, **149,041** citations and **3,216** clips; preparation to schema 26 produced **3,705** clips. The measured 26→27 step preserved source-table hashes and prior table counts except the migration-version row. Both source/prepared states had **212** items with clips and **336** without; these counts do not establish proof strata.

| Fresh duplicate | SHA-256 |
|---|---|
| Prepared schema 26 | `5560227b127dcdebac2b3884ef054d10f0328a043c7f20f16ec13629697f6019` |
| Populated schema 27, initial and repeat | `ad58ad07e68d6b0cbb50b0a9e15ea4406536450518d6a69d277f84483008b435` |
| Empty schema 27, initial and repeat | `ec70a32afa5f890a0600ae84181dafa563229a9b866c047199d813f291ea1e06` |

Run O first needs N-1 repaired and independently re-accepted on its integrated SHA. Keep `librarian_apply_enabled=false`. P2-6 then needs the reserved Claude Code HTTP client against an isolated helper on **5180**, separate data root and dedicated Windows/browser profile: build/install, drive extension/dashboard, demonstrate claim/submission and reconnect after restart, observe waiting without a client, open `search_clips`/`get_evidence_card` links, verify capture deduplication and watchdog recovery. Record installed version, transport, revisions and the computer-use receipt. Neither this review's staged imports nor its handler probes provide that receipt. Power-loss durability also remains unverified.

For P2-7, rehash the named copy and freeze taxonomy, prompts/cards/source hashes, full manifest, client configuration and held-out IDs/labels before execution. Ratify per-stratum sample sizes and the **0.80 coverage / 0.90 precision** thresholds; keep held-out labels out of prompts, examples and taxonomy definitions. Use the reserved two-hour subscription-only scope, at most one model-result retry and no paid API spend. Account for every target and failed attempt, independently audit evidence and held-out judgments, and record exact input/output bytes, elapsed time and available reported usage. Keep unavailable usage, estimates and paid cost separate. Verify unchanged memberships, pins, activation and projection revision, with zero proof-created applies.

The live index, resident helper on **5179** and other project checkouts were never opened. No merge or push was attempted. No clarification is needed to route N-1; the proof's sample sizes and threshold ratification remain decisions for its dispatch.

Review complete. Python syntax, evidence JSON, candidate/artifact hashes, append-only report preservation and `git diff --check` passed. `git add` exited **128** because the shared worktree metadata's `index.lock` could not be created (`Permission denied`), so no commit was created. The report and migration probe are modified; the Run N evidence JSON and ten-case test file are new. All four files remain in this worktree for the integrator, with raw logs and disposable measurements under ignored `_scratch/run-n`.

**REJECT — candidate `a6725de56b46f47563d7ccd3fe63834d3e114cb9`.**
