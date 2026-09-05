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
