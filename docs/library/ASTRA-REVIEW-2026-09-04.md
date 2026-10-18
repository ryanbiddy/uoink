# Astra review, 2026-09-04

I measured **548 active items, 3,216 clips, and 212 transcript-bearing items, all covered**. The isolated test suite returned **528 passed, 3 skipped, 167 warnings in 36.92 seconds**. G2 reproduced **3 weighted wins, 0 losses, 17 ties**. Two rebuilds reproduced the original clip payload exactly, in **1.824 and 1.817 seconds**, and the FTS integrity check passed. These are measurements from this run, against the supplied upgraded copy and this worktree at `a4a2e6b`.

My recommendation is to retain the library direction and hold the next release for repairs. Clip retrieval is useful now. The installer omits its runtime modules, and the proposed Librarian contract does not yet make retries, undo, or user corrections safe. The cost script's printed G4 PASS is an arithmetic result; a measured inference pass has not passed that gate.

The review covers the codex section of the run C brief. No production code, existing contract, installed application, or live index was changed. The security review belongs to the other worker; the overlapping issues below explain release and architecture decisions.

**Measurement record**

The authorized source was `C:\Users\hello\AppData\Local\AgentControlRoom\uoink-index-copy-2026-09-04-upgraded.db`, 71,733,248 bytes. Both requested scripts initially failed on their first query with `sqlite3.OperationalError: unable to open database file`. This is a WAL-mode database; no adjacent WAL or SHM file was present. A byte-for-byte duplicate inside this worktree let the unchanged scripts run with their normal read-only connections. Source and duplicate SHA-256 were identical:

```text
2765cc359805fb12f7a90aecd3dd0b34d884aa8cb3015785011bf400da3b4dfc
```

The source hash was unchanged when checked again. Database reads used `mode=ro` and `PRAGMA query_only=ON`; rebuilds used a separate disposable duplicate. I did not open `%LOCALAPPDATA%\Uoink\index.db`. The cost script and production card handler also read corpus markdown referenced by the copy, as required by their summary-hint behavior (`scripts/library/cost_model.py:134`, `uoink_mcp_tools.py:492`). Those are corpus reads, not reads of another project checkout. They make the DB hash alone insufficient to freeze an evidence-card experiment; future runs should hash the selected corpus excerpts too.

| Query or inspection | Result produced here |
|---|---|
| `SELECT max(version) FROM schema_version` | 25 |
| Active / total items; blank source types | 548 / 548; 0 |
| Transcript citations / distinct items | 134,500 / 212 |
| Screenshot citations / distinct items | 14,541 / 519 |
| Items with citations but no transcript citations | 314 |
| Items with no citations | 22 |
| Clip coverage of the full library | 212 / 548 = 38.6861% |
| Clip text characters / mean / maximum | 4,720,482 / 1,467.8116 / 20,437 |
| Clips over 120 / 125 / 180 seconds | 1,729 / 320 / 72 |
| Longest clip | 1,041.839 seconds; `_KNjASionIo`, seq 0, one input cue |
| Missing clip links / populated speakers | 0 / 0 |
| Uncategorized / null topic / claims | 283 / 8 / 0 |
| `PRAGMA quick_check`; `PRAGMA foreign_key_check` | `ok`; no rows |
| Podcast repair, dry run | 147 unrequested new episodes; 0 opted-in enabled feeds considered; 0 eligible, 0 changes |
| Runtime registry / AST-counted stdio tools | 71 / 23 |

Source-type groups were 486 X threads with 154 clip-bearing items, 58 YouTube videos with 54, one YouTube short with one, and three podcast episodes with three. Thus 88.6861% of this copy is classified as X threads. This is Ryan's existing corpus, not a representative sample of the recurring-source follower wedge. Zero blank provenance fields proves completeness, not classification correctness.

The final test command was `python -m pytest -q tests/ -p no:cacheprovider -rs`, with `PYTHONPATH=.` and existing workspace-local directories for `LOCALAPPDATA`, `XDG_DATA_HOME`, `UOINK_OUTPUT_DIR`, `TEMP`, and `TMP`. The first two full runs each produced 527 passes and one X persistence failure: the output override pointed to a directory that did not yet exist, so the helper selected Desktop. The code requires an already-writable override (`server.py:1393`, `server.py:1413`); the test does not supply its own output root (`tests/test_u15_x_capture.py:262`). Creating the directory fixed the environment without changing tests. The final process took 37.3442 seconds. Skips were POSIX bundle execution, unavailable Windows symlink privilege, and ffmpeg missing from PATH. This was not an installer, WhisperX, or native UI run.

I ran the requested scripts unchanged with `--db <local-duplicate>` for `scripts/library/bm25_eval.py` and `--index <local-duplicate> --json` for `scripts/library/cost_model.py`. For handler verification I constructed `Index(read_only_connection, copy_path)` and bound `uoink_mcp_tools` to a backend exposing only `_get_index`. This avoids importing or starting the real helper (`index.py:385`, `uoink_mcp_tools.py:31`). Both examples below went through `call_tool`; the full 548-card comparison invoked the same production card handler directly to avoid its interactive rate limiter (`uoink_mcp_tools.py:3634`).

| Real handler request | Observed result |
|---|---|
| `search_clips`, query `blue line purple detector tracker`, item `WgPbbWmnXJ8` | One hit, 7069.38–7199.689 seconds; `https://youtube.com/watch?v=WgPbbWmnXJ8&t=7069s`; one invocation took 0.5510 ms |
| `get_evidence_card`, same item | `ok=true`; 116 available clips, 10 selected, 25,624 selected text characters |
| `search_clips`, query `site side by side verbose skills`, item `episode_9ddb44f98b2` | One hit, 1718.38–1787.98 seconds; `https://www.latent.space/p/chatgpt-work#t=1718`; one invocation took 0.3869 ms |
| `get_evidence_card`, same episode | `ok=true`; 64 available clips, 10 selected, 18,197 selected text characters |

These single-call timings are observations, not latency percentiles. Returned text matches the queried subject and carries a source-appropriate link. I did not open either media player, so podcast seek behavior remains unverified. The rebuild payload hash, excluding unstable `clip_id`, was `feeba0526d04d7b8f8391ef8d7eac349bc8b73f553f029a122357bf504b6bc30` before and after both rebuilds (`clips.py:278`).

**Release findings, in priority order**

1. **High — the installer cannot deliver this implementation.** `build.ps1:488` stages explicit sibling modules; `installer/uoink.iss:105` lists them explicitly. Neither file contains `clips.py` or `provenance.py`; neither includes `uoink.cmd` or `install-watchdog.ps1`. The new imports are deferred inside `Index` (`index.py:294`, `index.py:413`, `index.py:510`, `index.py:1697`), so the guard that only scans top-level imports in `server.py` misses them (`tests/test_installer_files_complete.py:23`). In an isolated package-shaped directory containing the shipped index module and migrations, a missing-source-type write raised `ModuleNotFoundError: No module named 'provenance'`; reopening after inserting a transcript citation raised `ModuleNotFoundError: No module named 'clips'`. This is a dependency reproduction, not an executed installer build. Add runtime modules and the intended CLI/watchdog assets to staging and installation, then smoke-test a populated upgrade with only installed files. The existing registry-key autostart remains in the installer (`installer/uoink.iss:238`); committing a watchdog script does not install supervision.

2. **High — D-17 remains open.** Entity extraction still starts on key presence alone (`server.py:3778`), and the sidecar still reports pending by the same condition (`server.py:4508`). `_anthropic_messages` returns a response consumed as text without persistent usage accounting (`server.py:1294`, `server.py:1336`, `server.py:3718`). Ryan already chose a named default-off flag in `DECISIONS-2026-09-04.md:13`; no grandfathering decision needs reopening. Add the flag, its setting/UI, and sidecar parity. Meter actual per-call usage atomically with model identity and pricing provenance. A post-call meter is not a pre-call spending cap, and an unrecorded response must not look like zero usage.

3. **High before installation — Recall introduces third-party speech directly into prompt context.** The hook builds `additionalContext` from titles, channels, clip text, and URLs without an explicit trust boundary (`scripts/recall_hook.py:119`). It also opens SQLite without an explicit short deadline or connection close, and its final count query is outside the error handler (`scripts/recall_hook.py:110`, `scripts/recall_hook.py:118`). Adopt the hardening work in the reach memo, including escaping the delimiter itself; a fence alone is not an injection defense. Add a total deadline, bounded output, opt-out, fail-open JSON behavior, and adversarial fixtures. Do not install it as a prerequisite for every prompt until those checks pass.

4. **High for evaluation — the local benchmark can award success to the wrong item.** For the first real gold item I supplied its correct shelf and quote with `video_id='WRONG_ITEM_ID'`. `evaluate_single_item` returned `l1_match=true`, `l2_match=true`, and `evidence_valid=true`. Its fallback chooses the first assignment when no ID matches (`scripts/librarian/bench_local.py:173`). Also, `format_card_for_prompt` passes embedded cards through unchanged (`scripts/librarian/bench_local.py:74`): all 47 non-null embedded cards omit `video_id`. The 13 null cards use a separate stub that does include it. Fix the packet identity and reject missing, duplicate, or unexpected result IDs; test those cases before trusting any model score. Measure latency after reading the response body, not before (`scripts/librarian/bench_local.py:119`). Report missing token usage explicitly instead of silently substituting word counts (`scripts/librarian/bench_local.py:124`).

5. **Medium — the 120-second clip boundary is not a bound.** The window closes after a whole cue is appended (`clips.py:215`, `clips.py:222`). Long paragraph cues therefore produce long clips; the longest measured example is over seventeen minutes. The test explicitly accepts 121 seconds (`tests/test_clips.py:100`). Most overruns are smaller, but 72 clips exceed 180 seconds. Preserve real timestamp granularity: split only when finer source timing exists; otherwise mark the coarse source interval and cap the excerpt. Never invent second-level word timing by dividing a long paragraph evenly. Document actual granularity in search and card responses.

6. **Medium — a successful scheduler timestamp is only a completed-loop heartbeat.** A forced feed exception returned `ok=false` yet set `_last_successful_tick_at` (`server.py:6931`). Distinguish tick completion, last successful poll, ingest completion, and freshness. The scheduled task retries nonzero process exits; it does not detect a hung process or a dead scheduler thread (`scripts/install-watchdog.ps1:34`, `server.py:6947`). The duplicate-process probe also accepts any HTTP 200 at `/health`, without checking identity (`server.py:14259`). Test process death, wrong listener, scheduler failure, and exhausted retries separately before calling liveness repaired.

7. **Medium — provenance migration precedence differs from write-time classification.** An in-memory row with platform `x`, metadata `source_type='x_article'`, and a status URL became `x_thread` under migration 0025, while `derive_source_type` returned `x_article`. SQL considers platform before explicit metadata kind (`migrations/0025_source_type_backfill.sql:27`); Python gives explicit kinds priority (`provenance.py:87`). The later backfill only visits empty fields (`provenance.py:155`), so it cannot repair that disagreement. Align the rules and add a follow-up reconciliation migration; do not rewrite an already-dispatched migration and assume existing installs replay it. This probe demonstrates a possible misclassification, not a measured count of affected real items.

8. **Medium — registry reuse still couples business logic to HTTP handlers.** `uoink_url` constructs a fake `Handler` subclass to capture a response (`uoink_mcp_tools.py:1666`). It works with the current route but makes future request-field assumptions easy to break. Put extraction orchestration in a service function and let both adapters call it. Validation also differs: plain HTTP validates its schema (`server.py:12543`), while JSON-RPC calls the registry directly (`server.py:12010`, `uoink_mcp_tools.py:3634`). The current validator does not recurse into nested object requirements; an invalid nested object passed my probe (`openapi_bridge.py:69`). Phase 2 needs domain validation shared by every transport, regardless of JSON Schema support.

**What the product and architecture have earned**

The direction is strongest where it follows the data: deterministic local retrieval, stable source identity, citations, and replaceable calling clients. The clip table uses FTS external content and synchronization triggers (`migrations/0024_clips.sql:34`); search joins back to live items, supports item/channel filters, and orders ties deterministically (`index.py:648`). The current library homepage is already active (`assets/dashboard/index.html:3386`, `assets/dashboard/index.html:3914`). Those are useful foundations.

The implementation does not yet deliver the full promise in the positioning sentence. Dashboard library search still calls `/memory/search` (`assets/dashboard/index.html:7820`); the clip tools live in the broader HTTP registry (`uoink_mcp_tools.py:2513`) and are absent from the 23 stdio wrappers (`uoink_mcp.py:78`). The HTTP MCP capability object advertises tools only (`server.py:7542`). The new library work queue is proposed SQL in a document, not a migration. A model that connects through the recommended stdio entry point cannot discover clip search today. CI's tool-count assertion is bookkeeping, not a product reason to preserve that gap.

The code boundaries are uneven. I counted 15,052 lines in `server.py`, 3,648 in the tool module, and 11,653 in the dashboard HTML. Size alone is not a defect, but shared server globals and fake HTTP handlers make independent changes harder to integrate. Keep the helper as the resident service; place new card construction and library state transitions in small modules with explicit inputs and transactions. Do not create another transport-specific implementation.

I would revise these claims in the direction document:

- The claim that searchable clips unlock every citation-bearing item conflates screenshots with transcript text. Current coverage is all 212 transcript-bearing items, not all 526 items with any citation. Show the missing-evidence groups in the UI and evaluation.
- A sampled card cannot prove that an older item never discussed a concept. Selected production clip text is 42.3970% of all clip text on this copy; the truncated dry-run packet is smaller still. Use cards to screen, then retrieve additional evidence for uncertain or proposed assignments. Do not require a full reassignment merely because a shelf's wording changed.
- A copied opening paragraph is not the proposed structured summary. Of 548 production hints, 534 begin with `##`; the filter removes `# ` but not general Markdown headings (`uoink_mcp_tools.py:485`, `uoink_mcp_tools.py:505`). Some hints begin with promotions. Treat this as an excerpt and label it honestly, or create an evidenced client-produced summary.
- A cloud client's ability to parse OpenAPI does not establish access to this machine's loopback helper (`server.py:140`, `openapi_bridge.py:205`). Define supported client/transport combinations and test them. Keep the pure client-run decision, with visible waiting-for-client status for unattended work.
- Remove universal competitor claims and unsourced build-time promises from release criteria. This review did not re-audit the market landscape. The code can establish retrieval quality and local durability; it cannot establish that nobody else re-shelves or that this is a defensible market position.

**Cost model and gold set**

The size measurements are reproducible. The copied cost-model clip selection matched the production handler on all 548 cards. The dry-run and production selection algorithms differed on 59 items even when both requested six clips (`scripts/librarian/dryrun.py:114`, `uoink_mcp_tools.py:523`). Reconciliation therefore needs shared selection and rendering as well as an explicit `clip_chars` parameter.

| Representation measured here | Characters |
|---|---:|
| Production handler JSON, `json.dumps(..., ensure_ascii=False)` | 2,716,281 |
| Cost-model rendered card text | 2,425,715 |
| Dry-run rendered card text | 271,337 |
| Production selected clip text | 2,001,344 |
| Dry-run selected clip text | 176,344 |
| Production summary hints | 320,874 |

Rendered-text size differs by 8.9399 times; clip text differs by 11.3491 times. These are character ratios, not token ratios. Both card builders and the cost renderer are cited above; production output comes from `uoink_mcp_tools.py:571`.

The unchanged cost script printed a modeled Haiku batch total of $0.916964, or $0.836646 per 500 items; its twelve-card list-price scenario printed $2.109848 for 548, or $1.925044 per 500. These are calculated outputs using `chars/4`, 400 assumed assignment output tokens per card, and 6,000 assumed taxonomy tokens (`scripts/library/cost_model.py:42`, `scripts/library/cost_model.py:170`, `scripts/library/cost_model.py:285`). No tokenizer was available and no inference ran. The current official Haiku list and batch rates agree with the constants; this verifies rates, not usage. [Anthropic pricing](https://platform.claude.com/docs/en/about-claude/pricing).

Packing is invalid even on that proxy. The algorithm sizes every batch from the global average and reserves only 1,000 tokens (`scripts/library/cost_model.py:344`). Its first batch of 173 cards is 277,503.75 input proxy tokens against its own 200,000 context assumption, before the assumed 69,200 output tokens. The next two input-plus-output totals are 228,202.75 and 219,940.75. Pack actual serialized requests, reserve output capacity, and enforce the model's output limit. A twelve-card client request is a different execution path from a provider Batch API job; the subscription-only decision does not authorize switching to metered API execution because its price looks cheaper.

Grok followed run A's narrower instruction to price measured characters plus assumed output (`docs/library/DISPATCH-2026-09-04.md:79`). That explains the PASS; it does not satisfy the direction document's measured inference gate. Retain the arithmetic as a forecast, mark operational G4 pending, and measure request/response usage, retries, successful-item coverage, quality, and wall time on the chosen client before applying labels.

The gold set contains 60 unique real IDs: 27 YouTube, 30 X, three podcasts; 23 short, 26 medium, 11 long. No channel exceeds five items. All IDs and titles match the copy. All 47 non-metadata evidence quotes occur in both their stored card and current clips. All embedded clip lists match current production selections. That is valuable evidence work. Thirteen labels are explicitly metadata-only. The set has 57 distinct shelf paths, 55 represented once, so it is poorly suited to measuring shelf stability or per-leaf quality. The schema records labels, rationales, and confidence but no human adjudicator or disagreement history (`docs/library/gold-set-2026-09-04.json:1`). Treat it as an agent-labeled evaluation seed until independently adjudicated. Do not call it a human gold standard.

The benchmark derives the taxonomy from those same labels and fabricates definitions from path names (`scripts/librarian/bench_local.py:58`). That can measure assignment into a supplied vocabulary, but cannot validate induction or performance on unseen shelves. Freeze a separate taxonomy with real inclusion/exclusion cues, separate calibration from held-out examples, report all shelf paths rather than only the primary path, and include the metadata-only cases as a distinct stratum. The local endpoint was not contacted in this review; no model-quality or throughput number is claimed.

**The four Claude contracts**

| Document | Keep | Required revision before implementation |
|---|---|---|
| `D-17-2026-09-04.md` | Explicit flag, sidecar parity, actual usage accounting | The memo says two background jobs comply while also finding all metering absent (`D-17-2026-09-04.md:57`, `D-17-2026-09-04.md:70`); distinguish flag compliance from full D-17 compliance. Make usage updates atomic and model-specific. Default-off was already decided; remove the grandfathering approval loop (`:143`). |
| `WORK-QUEUE-CONTRACT-2026-09-04.md` | Separate submission/application; inverse journal; evidence by content rather than ephemeral clip ID | Replace the incomplete state machine before coding it. See the concrete cases below. |
| `MCP-REACH-2026-09-04.md` | Hook hardening, bounded resources, one-way generated mirror | Update 67/23 snapshot counts; prioritize client reach. A mirror adds deletion, filename, write-conflict, and recovery cases despite the claim of no new failure mode (`:254`). The protocol change needs more than another version string (`:349`). |
| `DECISION-MEMO-2026-09-04.md` | Flags card mismatch and unsafe Recall before deployment | Retract the unchanged-phase-order conclusion (`:12`), the unmeasured cheap-mirror claim (`:79`), and the reopened default-off question (`:18`). The four documents are design inputs, not implementation acceptance. |

The queue contract's missing cases are specific:

- A lease expires and the same `client_id` claims again. The old response can satisfy the new lease because submission carries no per-attempt token (`WORK-QUEUE-CONTRACT-2026-09-04.md:265`, `:304`). Add a fencing token and content/taxonomy revision hashes. Count attempts once; reaping and claiming currently both increment them (`:233`, `:278`). Define exhaustion and renewal.
- A successful submit is followed by a timed-out apply and retry. Submission idempotency does not make application idempotent. Add an apply operation key, expected projection revision, and stored response (`:323`, `:343`). Compare normalized result hashes on repeated submission; reject a changed payload under an old key.
- Undoing the first assignment must delete newly inserted rows. An inverse made only of overwritten/deleted rows cannot express that (`:368`). Include inverse operations for additions and version activation. Reject stale undo after a later apply or user pin, rather than replaying over newer work (`:378`).
- Locked rows can retain an old version/path after a shelf rename; the proposed assignment primary key also cannot stage both versions of an identical path (`:148`). Define stable shelf identity, draft assignment staging, activation coverage, and pin semantics through rename/merge. Count changed items once in churn; define the empty-catalog denominator and distinguish initial filing from disruptive moves (`:363`).
- The contract requires quotes in clips, while the assignment prompt permits `metadata-only` for empty cards (`:327`; `scripts/librarian/prompts/assign.md:15`). That affects 336 items in this copy. Add an explicit evidence kind and an honest unsupported/unmapped result; do not silently invent a quote exception.
- Losing the database cannot preserve user corrections just by rerunning a model. The recovery row assumes pins were mirrored, while mirroring is optional and later work (`:470`; `memory_layer.py:288`). Define an authoritative local correction journal and recovery before promising immutable user work. Also define partial rejection/requeue, tombstones, payload limits, and retention of referenced apply history.

The reach memo correctly distinguishes HTTP from the FastMCP stdio process (`server.py:11986`, `uoink_mcp.py:36`). Its suggestion to wait for SDK support is stale: the official July release says Python support shipped. New HTTP requirements include request routing headers, cache fields, and response metadata, not merely removing initialize; opted-in notification streams still exist. Spike the supported SDK before prescribing a rewrite. [MCP release](https://blog.modelcontextprotocol.io/posts/2026-07-28/), [official SDK migration details](https://ts.sdk.modelcontextprotocol.io/v2/migration/support-2026-07-28).

**Commit-by-commit disposition**

I inspected `git log 3e06c65..HEAD`, worker diffs, and the integration resolutions. That range contains 14 commits; `3e06c65` itself is excluded by Git's range syntax. Its clip, card, and Recall code was nevertheless inspected as the substrate being reviewed. File citations elsewhere in this review refer to the final `a4a2e6b` tree, not obsolete line numbers in worker snapshots.

| Commit | Review |
|---|---|
| `61fae99` | Direction/decisions/briefs only. Preserve the ratified decisions; correct coverage, release gates, and ordering as above. |
| `1744d3d` | Policy memo only. Detection/capture separation and explicit defaults are useful inputs. I did not independently re-audit each platform's terms and do not adopt its legal conclusions as verified findings. |
| `5e0c2d8` | Cost harness is read-only and reproducible; duplicated card logic, average-based packing, and the G4 label need revision (`scripts/library/cost_model.py:104`, `:197`, `:329`, `:484`). |
| `4e5f745` | Rates unchanged, verification date refreshed (`server.py:451`, `:1189`). Official pricing agrees. This fixes stale dating, not metering. |
| `a19dd63` | Real source-backed evaluation seed and useful prompt constraints. Wrong-ID acceptance, missing packet IDs, synthetic taxonomy definitions, and timing scope prevent benchmark acceptance (`scripts/librarian/bench_local.py:58`, `:74`, `:119`, `:173`). |
| `155c011` | Good populated-upgrade, FTS cascade, repeatability, and handler tests (`tests/test_clips.py:145`, `:167`, `:190`, `:272`). Exposed stable item IDs in both new tools. No installed-tree dependency check; G2 covers item search, not clip retrieval. |
| `0a0799a` | Useful explicit contracts; no shipped implementation. Queue durability and retry cases above must be resolved. Its statement that no other endpoint sends model text is too broad once `scripts/librarian/bench_local.py:99` exists; scope it to resident server egress. |
| `322e014` | Integrates codex Phase 1 work; registry remains HTTP-only for clips (`docs/v2-mcp.md:23`). Integration retained the product access gap. |
| `8085f02` | Integrates Grok cost/policy/rate work. The forecast still consumes prompt files that the next merge changes (`scripts/library/cost_model.py:378`). |
| `f6d2247` | Integrates Gemini prompt changes. Today's rerun produces 75,222 induction proxy tokens and 569.5 prompt-only proxy tokens; the recorded cost memo's earlier prompt counts are no longer current. Regenerate measurements after prompt changes. |
| `200560d` | Integrates Claude docs without reconciling evidence-card shape or implementation ownership. A green code suite cannot validate these documents' invariants. |
| `16222bb` | Useful bounded podcast eligibility repair, provenance helper, CLI, and exit status changes (`podcasts.py:672`, `provenance.py:76`, `server.py:14974`, `server.py:14379`). Packaging, provenance precedence, heartbeat semantics, and registry coupling remain. FxTwitter enrichment checks matching IDs and keeps syndication fallback, but calls the supplement on every fetched post, not only known truncations (`x_extractor.py:156`, `:186`); verify live provider behavior separately from the fixture. |
| `0bead71` | Reconciles tool count to 71 and schema upgrade tests to the newest migration (`tests/test_docs_live_contracts.py:32`, `tests/test_clips.py:223`). Replay correctly removes markers from 24 onward (`tests/test_clips.py:252`). Counts and tests integrate successfully; contract mismatches persist. |
| `a4a2e6b` | Review and orchestration briefs only. This is the frozen review base; no implementation delta. |

**Gate decision and limits**

Accept G0 for the exercised source-tree fixture and copy rebuild. Accept G2 on its fixed item-search set. Accept local handler retrieval and all-transcript-item coverage as the narrower G1 result; full citation coverage and actual player seeking remain open. G3's import checks pass for their named modules (`tests/test_clips.py:353`), but neither transport equivalence nor whole-product zero egress follows. G4 remains pending operational measurement. No labels should be applied on the strength of the current cost or benchmark PASS paths.

I did not run an installer, install the watchdog, kill a resident helper, inspect the user's live index, load the extension, play the returned links, call a model, measure local GPU performance, or perform the other worker's security/egress audit. The phase plan names the verification that closes those gaps.

Handoff state: all three requested documents passed formatting and file/line-target checks. Git staging failed because the shared worktree metadata denied `index.lock` creation; no commit was made. Automatic approval review also rejected removal of the verified workspace-local `.review-run-c` directory with “blocked by policy.” Its disposable databases, measurement JSON, logs and probe scripts remain available locally for inspection and cleanup. Commit only the three requested Markdown deliverables, not that scratch directory. No merge or push was attempted.
