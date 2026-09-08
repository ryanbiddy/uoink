**Run AX verdict: RECEIPTS REJECTED for proof acceptance.** The original run 2 archive is intact, and its independently replayed quality result is **P2-7 FAIL**: timed strict precision is 39/46 and text-only strict precision is 6/11. Both coverage gates pass. Specific 7 fails because the scorer accepts an unapproved taxonomy when its revision hash is absent. This rejection concerns the proof acceptance check; it does not allege altered receipts or invalidate the independently reconstructed counts below.

Codex audited C1–C4 of [the stage 2 plan](STAGE2-AUDIT-PLAN-2026-09-05.md), adapted to [the stage 4 gate](STAGE4-GATE-2026-09-07.md), plus all seven checks in [the AX brief](STAGE4-AUDIT-BRIEF-2026-09-08.md). Audit checkout: `65325b9184f4e4b58c5fb6bcbcefdb82d5114ffb`. Run 2 launch: `861b17a12fa0c70523776d70552b4a33a17c6e87`; finish: `76e03848e76ba487ab8c5ecdab060a9e62d49a6a`. The finish adds four Phase 4 documents; all six execution fingerprints are unchanged. The later scorer adapter is exactly commit `2727b45a74209a6c2b8ab3eab5a3ec8c30bc1045`.

All 17,504 files in the complete archive at `C:\Users\hello\AppData\Local\AgentControlRoom\proof-archives\run-stage4-2026-09-08-run2` were authenticated against the committed `SHA256SUMS` before staging under this worktree's `_scratch/proof/audit-ax/archive`. The replay used those originals, including HTTP history and database snapshots omitted from the committed copy. Database images were deserialized in memory. No model, helper, port 5179, or live index was used. No existing project file or archived artifact was edited; no commit or merge was made.

The [measurements](proof/audit-ax-measurements-2026-09-08.json) retain the per-call accounting, all completion boundaries, all 567 membership checks, 60 scoring decisions, 225 development outcomes, diagnostic decisions, input hashes, and negative-test commands and output. The [replay script](proof/audit-ax-2026-09-08.py) is a stage 4 parameterization of the untouched AO script. Its exit code 0 means the audit completed, not that P2-7 passed.

C1 verifies the freeze, selection, and chronology. The v3 sample is reconstructed from the original pool after excluding the old 60, the 225 development identities, and hold-out v2. Stage 4 reuses that sample; it does not select a replacement.

| Check | Observed | Expected | Verdict |
|---|---|---|---|
| C1.pool | 226 eligible: 58 timed, 168 text-only | Original v3 eligible pool | PASS |
| C1.freeze | Seed `0x294941ba84eec02b` reproduces all 47 timed and 13 text-only IDs; original receipt and freeze hashes match | Deterministic original identities, no substitutions | PASS |
| C1.seals | All 11 execution-record references match; 60 gold rows sealed | Frozen prompt, taxonomy, manifest, labels, mapping | PASS |
| C1.blind_packet | 60 complete v2 cards; expected packet fields; no predictions | Packet equals frozen cards and taxonomy | PASS |
| C1.feasibility | 47/47 timed and 13/13 text-only have eligible evidence; none dropped | Retain every selected identity | PASS |
| C1.revision | All 548 packets bind approved revision `8a1b1603…`; one prompt/policy hash | One approved taxonomy and frozen prompt | PASS |
| C1.manifest_bindings | All file, target, card, head, and receipt-input hashes reconcile | Frozen manifest identities | PASS |
| C1.containment | 60 prompt/induction input files checked; zero identity or excerpt matches | Hold-out absent from examples and induction inputs | PASS |
| C1.chronology | Execution record at 08:41:57.666 UTC; launch commit at 08:41:58; service run created at 08:42:16.193 | Freeze and code precede execution | PASS |
| C1.database_policy | Database binds frozen prompt, v3 version, and all-548 target hash | Service policy matches freeze | PASS |
| C1.implementation | Runner, service, cards, prompt, and validator match execution code after EOL normalization; scorer differs only by `2727b45` | Explain every code difference | PASS |
| C1.launch_finish | Clean launch/finish; 12 project fingerprint records match six archived originals; only four Phase 4 documents added | No execution-code drift | PASS |

The packet's contents and the label files' exposure declarations support the recorded blind workflow. They cannot prove what a labeller remembered. Both labellers and the adjudicator disclosed prior v3 exposure. The 60 identities remain reused evaluation data.

| Frozen identity | Recomputed SHA-256 |
|---|---|
| Original v3 hold-out file | `855749efcaca5e985c04a9efef2decc4ee2dca3b24c8c3871f01079a9acd314c` |
| Stage 4 manifest file bytes | `de99a902c45ffd7f78ffb67ad1a1b261bf1f9878214854dc3ce1eca780cf2abe` |
| Stage 4 manifest content | `61855bf8e9b309dd1e0e98a005296a73965c41ec0cbfcee0a8508b1be59a7c88` |
| Gold file | `7b9eb7c3880bcb321e5aade8f83a9561de048b56ade9ce172e69db3fb0fffbe6` |
| Mapping file | `f490bd6eddfe9d2a10fedbd50c269c1133f23caae046f13126c871f09ba1f388` |
| Approved normalized taxonomy revision | `8a1b16033eb4d6acd57c91c6a5d5e7f2af6d6f60f3adef92502b62d81ba28d04` |

The manifest content hash is an acyclic binding, distinct from the file-byte hash and the historical target/exclusion hash. Bindings, packet, and diff cite the recomputed content hash. Receipts bind the manifest's complete `hashes` object; the execution record separately binds its exact file bytes. The induction manifest has a CRLF checkout hash and the expected LF Git hash; both are retained in the measurements.

C2 reconstructs the execution record from call files, HTTP exchanges, registry rows, and database images.

| Check | Observed | Expected | Verdict |
|---|---|---|---|
| C2.archive_bytes | 17,504/17,504 checksum entries match | Exact original archive bytes | PASS |
| C2.artifact_references | 5,414 archive references resolve and rehash; project fingerprints checked separately in C1 | Every typed artifact reference resolves | PASS |
| C2.1 | 69 call records, stdin files, unique CLI sessions, and matching log entries; 548 uniquely owned attempts | Count actual processes once | PASS |
| C2.2 | All 69 batch prompts rebuild byte-for-byte; schema/argv/stdout/stderr and totals reconcile | Count bytes at process boundary | PASS |
| C2.execution_variables | Opus 5, no effort flag, batches at most 8, disabled tools/session persistence; API-key-unset assertion | Frozen stage 4 variables | PASS |
| C2.3 | Four CLI counters and both model ledgers reconcile; USD 41.3059685 estimate; paid cost null | Deduplicate usage/cost by process/session | PASS |
| C2.4 | Zero failures at all 548 completions, including 529 boundaries with N >= 20 | Distinct-failure v2/AO-G1 ratio <= 10% | PASS |
| C2.cleanup | Zero owned processes remain; helper stopped; no cleanup errors | Recorded cleanup complete | PASS |
| C2.5 | Peak concurrency 4; latest start 2,276,132 ms; wall 2,430,170 ms; zero retries/resends | <=4 calls, starts before 7,200,000 ms, <=1 retry | PASS |
| C2.6.history | 4,026 raw exchanges reconcile with 2,322 normalized claim/submit/preview events; no credential exposure | Original request/response history, endpoint 5180 | PASS |
| C2.6.redaction | Zero unredacted helper or lease-token fields in HTTP artifacts | Redacted HTTP contract | PASS |
| C2.7.registry | 548 work/manifest/attempt/submission rows and 567 proposals reconcile in both directions; no extra claims | Registry agrees with raw submissions and terminal states | PASS |
| C2.7.json_state | Identical before/after memberships, pins, policies, activation, projection 0; empty apply journal; apply disabled; preview refuses | Zero applied labels and unchanged projection state | PASS |
| C2.7.databases | Both original database images agree with state exports; after image agrees with every registry table | Independent database confirmation | PASS |
| C2.8.heads | All 548 original bounded heads match manifest and database policy hashes | Same source heads, <=8,192 bytes | PASS |
| C2.8.source | Original hash `2765cc35…4dfc`, schema 25; actual upgraded hash `37f1061e…99d31`, schema 28 | Original source retained; recorded upgraded duplicate | PASS |
| C2.9 | Current-checkout `--stage4 --require-real` exits 0 | Portable real validation without historical checkout reads | PASS |

The 4,026 raw exchanges comprise 1,773 claims, 548 submissions, 1,704 work-list reads, and one preview. Work-list reads explain the difference from the normalized history. This run has no rejected replies, third claims, cancellations, or releases to reproduce. Their absence agrees with zero retries and one completed attempt per target.

| Process accounting | Recomputed total |
|---|---:|
| Stdin/prompt bytes | 3,572,513 |
| Schema bytes | 101,016 |
| Serialized input bytes | 3,673,529 |
| Stdout bytes | 752,053 |
| Stderr bytes | 0 |
| CLI input tokens | 150 |
| CLI output tokens | 720,141 |
| CLI cache-read input tokens | 5,150,263 |
| CLI cache-creation input tokens | 1,952,898 |

`modelUsage` additionally reports Haiku: 1,193,082 input tokens, 900 output tokens, and USD 1.197582. Opus reports the four CLI counters above and USD 40.1083865. Together their estimates equal USD 41.3059685. These are CLI list-price estimates from subscription sessions, not invoices. No per-item view is added to the process totals.

C3 checks every accepted primary and secondary against its frozen packet and excerpt.

| Check | Observed | Expected | Verdict |
|---|---|---|---|
| C3 | 453 accepted attempts; 567 valid memberships: 453 primary, 114 secondary; zero identity, shelf, confidence, source, kind, basis, or occurrence errors | Valid video/source/card/packet/excerpt identity; approved shelf; confidence >=0.60; packet basis; one admissible excerpt | PASS |
| C3 quote cap, included above | Every quote has 1–22 normalized words; no raw model membership exceeds 24 | NFC, whitespace collapse, 1–24 words, <=1,000 characters | PASS |

The JSON contains every membership's count and the full word-count histogram. The 150 passing targeted tests include the service's 24/25-word boundary, secondary rejection, normalization, card budgets, and stage 4 validator cases. Grounded evidence establishes quotation support; it does not establish the correct shelf.

C4 uses `strict-mapped-primary-v2`: NFC-normalize and trim path segments, preserve case, map gold to the deepest unambiguous approved ancestor, and require exact primary equality. Every selected item stays in its original denominator.

| Stratum | N | Assigned / N | Strict correct / assigned | Required correct at actual A | Descendant-tolerant | Any exact membership |
|---|---:|---:|---:|---:|---:|---:|
| Timed | 47 | 46/47 = 0.979 PASS | 39/46 = 0.848 FAIL | 42 | 41/46 = 0.891 | 43/46 = 0.935 |
| Text-only | 13 | 11/13 = 0.846 PASS | 6/11 = 0.545 FAIL | 10 | 7/11 = 0.636 | 6/11 = 0.545 |
| Overall, diagnostic | 60 | 57/60 = 0.950 | 45/57 = 0.789 | No pooled gate | 48/57 = 0.842 | 49/57 = 0.860 |

Exact-path counts equal strict counts here. Descendant-tolerant credits a primary below the mapped gold path. Any-membership credits exact equality in any accepted membership, including the primary. Neither replaces the strict gate. Only the timed any-membership diagnostic reaches 0.90; neither alternative reaches 0.90 in text-only. The timed run needs three more correct primaries at its actual assignment count; text-only needs four more.

| Check | Observed | Expected | Verdict |
|---|---|---|---|
| C4.mapping | All 60 independently derived ancestor mappings equal sealed rows | Strict versioned mapping | PASS |
| C4.timed_evidence | Coverage 46/47; precision 39/46 | Coverage >=0.80 and precision >=0.90 | FAIL |
| C4.text_only | Coverage 11/13; precision 6/11 | Coverage >=0.80 and precision >=0.90 | FAIL |
| C4.regression | Historical old60 remains 34/60 assigned, 18/34 strict; all 225 development outcomes retained | Preserve historical score and complete development ledger | PASS |
| C4.scorer_agreement | CLI and independent replay agree on both strata's exact numerators/denominators | Agreement on actual frozen inputs | PASS |
| C4.scorer_refusal | Mock and artifact-stripped receipts both exit 1 | Refuse mock/unvalidated receipts | PASS |
| C4.taxonomy_refusal | Explicit v1 taxonomy exits 1 | Refuse a conflicting declared revision | PASS |
| C4.missing_taxonomy_refusal | Missing taxonomy file exits 1 | No missing-file fallback | PASS |

There are three timed and two text-only sibling errors. Both unmappable gold items remain unassigned: zero over-assignments out of two. The third abstention has a mapped gold shelf. Whole-library outcomes are 453 accepted, 70 unmapped, and 25 unsupported: 453/548 = 0.827 assigned. The 0.950 coverage figure belongs to the 60-item hold-out.

| Preserved diagnostic | Timed coverage; strict precision | Text-only coverage; strict precision | Overall coverage; strict precision |
|---|---|---|---|
| Historical stage 1 old60, original v1 | 30/47; 15/30 | 4/13; 3/4 | 34/60; 18/34 |
| Stage 4 on old60, old labels mapped to v3 | 38/47; 10/38 | 7/13; 4/7 | 45/60; 14/45 |
| Stage 4 on v2, original v2 labels mapped to v3 | 46/47; 41/46 | 13/13; 13/13 | 59/60; 54/59 |
| Historical stage 3 v3, original labels/cards | 37/47; 28/37 | 12/13; 7/12 | 49/60; 35/49 |
| Stage 4 predictions against stage 3 gold | 46/47; 38/46 | 11/13; 9/11 | 57/60; 47/57 |

These are diagnostic replays, not new acceptance sets. Old60 overlaps development by 23 items; current v3 overlaps neither development nor v2. All 16 probe items are development items and none is in v3. Development outcomes are 149 accepted, 65 unmapped, and 11 unsupported. All per-item decisions remain in the JSON.

The seven stage 4 specifics resolve as follows.

| Specific | Observed | Expected | Verdict |
|---|---|---|---|
| S4.1 | `check_stage4_references` succeeds; bindings reconstruct exactly; all 60 original IDs/source revisions/strata retained and all 60 hashes rebound | Complete binding, packet, two-label, adjudication, gold, mapping graph | PASS |
| S4.2 | All 548 complete `diff_cards` results reproduce: 394 metadata-only, 97 added prose, 57 displaced timed excerpt; maximum 6 excerpts, 240 characters/excerpt, 8,190 wrapped bytes | Exact diff classifications/details and v2 budgets | PASS |
| S4.3 | Probe status contract is `PROBE_ONLY_VALID_AUDIT_REQUIRED`, quality items 0, whole-manifest false, product-pass false; scorer refuses it; all 16 independently repeated in run 2 | Probe contributes no acceptance result | PASS |
| S4.4 | `f72786a` changes the client schema to two closed alternatives; service file unchanged; all 69 raw outputs pass repaired schema; assigned-plus-reason fixture fails | Output-shape repair preserves assigned-result service contract | PASS |
| S4.5 | Gold sealed 05:39:24 UTC; committed 05:41:47; probe helper log begins 05:42:31.241; run 2 created 08:42:16.193; all hash bindings match | Seal precedes probe and full pass; committed manifest identity | PASS |
| S4.6 | Archived harness and independent guard agree at all 548 completions; validator agrees; five synthetic cases include 2/20 equality, 3/20 excess, and anonymous events | v2/AO-G1 enforcement and zero retries/rejections | PASS |
| S4.7.binding | Actual mapping, approved taxonomy, and independently hashed normalized nodes all name `8a1b1603…` | Correct archived revision binding | PASS |
| S4.7 | CLI accepts foreign version/content when taxonomy revision is absent, exits 0 and emits a score | Accept only the bound approved taxonomy revision | FAIL — AX-1 |

The committed probe contains receipts and six call files, all of which match its checksum inventory. Its database/HTTP originals are absent there. This audit exercises the partial-status function with its full-validation dependency isolated, and separately proves the real scorer refuses the 16-item receipt before artifact loading. It does not claim a fresh full validation of the original probe. Run 2 receives full real validation from the complete archive.

AX-1 is reproducible without a model or service. `verify_frozen_mapping` compares revision hashes only when both are present. `validate_receipts_for_scoring` also makes the taxonomy hash comparison conditional. The CLI validates the frozen manifest, then loads its separate `--taxonomy` argument without binding that file back to the approved nodes. The negative fixture removes the taxonomy's revision fields, sets `version_id` to `foreign-ax-fixture`, and changes one node's definition while retaining shelf paths. The CLI still reports the 60-row mapping as verified. Explicitly wrong hashes are rejected, so that negative test alone misses the bypass.

The actual archive uses the approved taxonomy and all 60 mapping rows replay correctly. AX-1 therefore leaves the numerical FAIL unchanged. It prevents the required stronger conclusion that the acceptance path admits that revision and nothing else. Under the retained AO verdict logic, a non-quality audit failure yields `RECEIPTS REJECTED`; a quality-only failure would yield `P2-7 FAIL`.

Proposed repair for the scorer owner: bind the supplied taxonomy to the validated manifest, recompute its normalized-node revision, require that revision to match both the manifest and mapping, and reject a missing identity. Retain explicit wrong-hash, missing-hash, and altered-content negative cases. This is a proposal only; the scorer was not edited.

One additional traceability gap remains in the supplied record. The named 16-item probe uses schema `9eee173a…` at `b5988db…`, before `f72786a`; run 2 uses schema `479f384f…`. The result asserts a separate schema probe, but its raw receipts and a newly reviewed 16-item probe are not supplied in the named record. The run 2 execution record still points to a `pending` probe receipt. Gate step 8 requires a new freeze and reviewed probe after a repair. Preserve that evidence or record an explicit disposition; this audit does not infer that the old probe exercised the repaired schema. This gap is disclosed separately and is not an additional automated rejection check.

The [result document](PHASE2-STAGE4-RESULT-2026-09-08.md) needs narrower interpretations in three places. Cards, model/effort, and eight gold outcome/path rows changed together; this run cannot isolate which change caused the score movement. With stage 3 gold held fixed, the stage 4 text-only score is 9/11, versus 6/11 under the relabelled gold. The sample is small, but 0.90 is attainable: 10/11 would pass. Finally, labeller agreement is not a demonstrated ceiling. Against the fresh stage 4 gold, both labellers score 43/47 timed; Gemini scores 9/12 text-only and Grok 8/12. The assigner is below those fresh rates. These comparisons include the labellers whose judgments informed adjudication and cannot establish an independent upper bound.

The seven timed misses also are not all parent/Frontier ambiguities after removing the four exact-secondary recoveries. The remaining three are `2080368030136107009` (AI parent versus Agents), `2092386459282182144` (Frontier versus AI parent), and `hPJYSxsHDtQ` (Frontier versus Industry). Every primary, gold path, and diagnostic flag is retained in `quality.decisions`.

My recommendation to Ryan is **option 3, limited to proposals that the owner reviews before applying**. Keep the strict 0.90 target for autonomous filing and preserve this failed measurement. A review workflow can be useful at these measured rates, but this audit establishes neither unreviewed activation nor the apply/undo product acceptance gates. The five text-only misses among eleven assignments make that distinction consequential. Repair AX-1 and resolve the probe traceability record before treating the proof pipeline as accepted; activation remains Ryan's decision.

| Ryan's option | Recommendation and reason |
|---|---|
| 1. Keep 0.90 strict and iterate | Retain it for autonomous filing. If another measurement is authorized, freeze a larger fresh hold-out and targeted boundary work before execution. Repeated tuning on these 60 reused identities will not establish generalization. |
| 2. Credit secondaries or descendants | Do not change the acceptance rule to rescue this run. Descendant precision is still 41/46 timed and 7/11 text-only; any exact membership is 43/46 and 6/11. A product-driven change needs a prespecified rule and fresh hold-out. |
| 3. Ship with review | Preferred development direction: show proposed shelves and evidence, require owner review before applying, and keep the separate activation/recovery gates. Do not relabel this result as P2-7 PASS. |

Replay from the complete archive:

```powershell
python -B docs/library/proof/audit-ax-2026-09-08.py --self-test
python -B docs/library/proof/audit-ax-2026-09-08.py --source-archive C:\Users\hello\AppData\Local\AgentControlRoom\proof-archives\run-stage4-2026-09-08-run2
```

For a subsequent replay of the authenticated local copy:

```powershell
python -B docs/library/proof/audit-ax-2026-09-08.py --archive _scratch/proof/audit-ax/archive
```

That command also creates and executes the AX-1 fixture; see `cli_probes.foreign_unhashed_taxonomy_scorer` for its full command and exit-0 output. C4 failures reproduce from `quality.decisions` and the real scorer's output in the same replay. The self-test passes 14 evidence cases and five guard cases. Targeted pytest validation passes 150 tests with its temporary directory inside this worktree; the initial default-temp attempt had permission-related setup errors, resolved by that relocation.

Open decisions: the scorer owner's disposition of AX-1, the missing post-repair probe evidence, and Ryan's choice of review-only delivery versus further strict-gate work. Apply remains disabled.
