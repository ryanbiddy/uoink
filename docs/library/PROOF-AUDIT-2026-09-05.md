# Run R proof audit, 2026-09-05

**P2-7: REJECTED — receipts are not trustworthy as a complete, contract-compliant measurement record. Candidate: `b1eed2a8d0213b6043e3169f3e8ed4ce212e13ad`.** The quality gate remains **FAIL**: coverage is 34/60 and mapped precision is 18/34. The accepted assignments pass the archived evidence checks. Rejection rests on reproducible accounting errors, a breached execution stop condition, and missing evidence needed to verify the execution independently.

This review follows [ORCHESTRATION-V1](ORCHESTRATION-V1-2026-09-04.md), the [run R brief](PROOF-AUDIT-BRIEF-2026-09-05.md), and the eight checks in [PROOF-PLAN](PROOF-PLAN-2026-09-05.md). I ran every check reported below in the dedicated worktree. No model, helper, installed application, live index, or other checkout was opened. Three synthetic service probes created disposable databases inside `_scratch/proof/audit-r`; they applied no labels. Production code, prompts and archived receipts are unchanged.

The archived receipt hash matches the brief: `2b4e824ea9f93999de6c5108406e60a5c81f108de0b279c52fee2e96d622469c`. The [reproduction script](proof/audit-r-2026-09-05.py) and [measurement record](proof/audit-r-measurements-2026-09-05.json) retain the calculations, all 60 scoring decisions, and artifact/code fingerprints. Script exit 0 means the audit completed, including reproduction of the defects; it does not mean P2-7 passed.

| Required check | Independently observed | Assessment |
|---|---|---|
| Original validator, `--require-real` | Exit 1: `Isolation root must be below _scratch/proof` | Archive portability defect: execution paths name the original checkout. No evidence of live-index use follows from this failure. |
| Receipt validation after a lexical path translation | `RECEIPTS_VALID_AUDIT_REQUIRED`; 548 targets, 559 attempts, 11 retries | The audit translates only the isolation configuration passed to that check, in memory. All other checks use the unchanged receipts and local frozen files. It never opens an archived path. This is a qualified diagnostic rerun, not an unmodified CLI success. |
| Frozen files, targets and split | All 11 file hashes match; 548 ordered source pairs, no exclusions, 60 distinct holdout IDs; packet/card hashes and all receipt input aliases match | PASS for archived bindings. Actual source-file, upgraded-file and corpus-head bytes are unavailable here. |
| Strata from archived excerpts | Full scope: 212 timed, 336 text-only. Holdout: 47 timed, 13 text-only | PASS; counts were recomputed from cards, not copied from the split summary. |
| Evidence replay | 290 accepted items, 352 memberships checked; holdout 34 items, 45 memberships; quotes 2–24 words | PASS for identity, approved shelf/path, confidence, packet basis, verbatim occurrence within one excerpt, evidence kind and text-source eligibility. All four accepted text-only holdout items are `x_thread`. |
| Work/result/preview reconciliation | Final receipt outcomes: 290 accepted, 225 unmapped, 32 unsupported, 1 rejected. Preview contains exactly the 290 accepted IDs and 352 matching proposals, including primary order and enriched timing | PASS within the archive. The preview records the remaining item as cancelled; its third claim/cancel response is absent. No independent registry database export is archived. |
| Before/after state and zero apply | Full snapshots identical: revision 0; empty memberships, pins and item policies; active version `taxonomy-v1-2026-09-04`; apply flag false; applied-label and proof-apply counts 0 | PASS **from receipts**. Preview is nonactivating and `can_apply=false`, with `apply_disabled`, `preview_approval_required` and one cancelled-item `incomplete_manifest` reason. Independent DB/journal verification is unavailable. |
| Scorer and independent quality arithmetic | Both strata fail coverage and precision; 18 strict matches out of 34 assignments | FAIL retained. Scorer exit 0 means report generation succeeded. Its evidence check alone does not verify identity or quotation occurrence. |
| Usage, bytes and elapsed-time accounting | Call-level usage can be reconciled; published cost and process/input totals are wrong; elapsed time lacks an independently replayable timeline | FAIL as detailed below. |
| Execution/recovery boundaries | Archived completion order exceeds the operational error guard. No guard is implemented in the real batch loop | FAIL. Prior run O recovery acceptance is historical evidence, not a new run R recovery measurement. |

The unchanged service, index, migrations, server and registry have no diff from run O candidate `de51277c63f35ceebde16d3958a564daad29e453`. Its P2-0–P2-5 and adapter-delivery acceptance remains the recorded prior review. This audit does not re-certify crash recovery or installed-client behavior. P2-6's installed portion still needs its own receipt; there is no computer-use verification in this audit.

The source metadata names the 2026-09-04 copy, 71,733,248 bytes, SHA-256 `2765cc359805fb12f7a90aecd3dd0b34d884aa8cb3015785011bf400da3b4dfc`. Receipts declare that hash before copying and after execution, schema 25→27, and upgraded-copy hash `b679f8e43fda27d5241d633c14011ed316d4cba68693db419f416d6c476bff09`. I verified these declarations against the manifest. I could not rehash those actual files: the archive contains only `receipts.json`, `harness.log` and `report.md`, and local frozen heads are absent. The corpus-head index hash can be recomputed; the underlying heads, full source revisions and pre-truncation excerpt IDs cannot be regenerated from selected excerpts. Reconstructed prompts contain only the frozen template, taxonomy and cards. There is no original invocation/stdin archive to establish that those were the entire client input.

The following findings block acceptance:

1. **R-1 — the run continued beyond its error guard.** The plan requires stopping above 10% after at least 20 completed reasoning attempts, counting rejected attempts plus linked transport events. In archived attempt order the numerator reaches 6 at attempt 47: **6/47 = 12.77%**. Even treating a whole batch as the completion boundary gives **6/48 = 12.50%**. Further batch boundaries also exceed the limit; the final **24/559 = 4.29%** hides those earlier breaches. `proof_run.py` records the limit in configuration but never evaluates it in `_batched_worker` or `run_proof_loop`; the validator checks only the final ratio. There are no event timestamps to certify the exact concurrent completion order, but neither archive order nor the implementation supports the claimed continuously enforced guard. The two-hour deadline is likewise recorded rather than enforced by a shared run deadline; this run's declared duration is below it. Future execution must stop, preserve partial receipts and terminate owned work on either condition.

2. **R-2 — process, byte and cost fields do not describe the actual calls.** There are **72** call records and distinct CLI sessions: 68 batches of eight, one of seven, one of six, and two singletons, covering 559 item attempts. `totals.model_calls=559` is therefore wrong under the plan's actual-process definition. The validator enforces that incorrect attempt-count formula. Single-card prompt fields are reconstructed per-item views; no process received those views for the multi-item batches.

   | Quantity | Archived total | Audit result |
   |---|---:|---|
   | Card bytes across all attempts | 2,166,288 | Exact match |
   | Single-card prompt bytes | 7,243,685 | Exact sum of reconstructed per-item views |
   | Prompt plus schema bytes | 7,944,112 | Exact sum of per-item views, not call input |
   | Batch prompt UTF-8 bytes | Call records only | **2,821,238**, reconstructed independently; all 72 call counts match |
   | Batch prompt plus schema | Absent | **2,911,454** = batch prompts + 72 × 1,253 schema bytes; reconstructed logical input, not independently captured stdin |
   | Response bytes | 5,616,155 | Exact size of reserialized, repeated, modified envelopes; original stdout bytes are unavailable |
   | CLI cost estimate | $0.0000 | **$19.5262464**, summing `total_cost_usd` once per distinct CLI session |
   | Invoice-confirmed paid cost | `null` | Unavailable; subscription use and an unset-key assertion do not prove a $0 invoice |

   The cost bug is reproducible in `write_receipts`: it sums `total_cost_usd` from `call.usage`, which never contains that key, defaulting each value to zero. The raw envelope estimates remain recoverable. The harness log's 675,525 total “B” counts are actually `len(res.stdout)` characters, not a byte measurement.

   The four top-level CLI counters reconcile once per call: **214 input, 908,541 output, 8,315,787 cache-read and 1,938,051 cache-create tokens** (11,162,593 total). They match Sonnet's entries. `modelUsage` additionally reports **1,020,637 input and 882 output tokens for `claude-haiku-4-5-20251001`**, with a $1.025047 estimate; Sonnet's estimate is $18.5011994. These are separate reported model entries within the 72 CLI invocations. I make no claim about the auxiliary model's purpose. Do not count repeated per-attempt usage again or describe the Sonnet-only sum as complete CLI usage.

3. **R-3 — execution evidence is incomplete.** The archive has no source duplicate, bounded corpus heads, registry work/attempt/submission export, independent state/journal snapshot, raw stdin/stdout files, or per-call start/end timestamps. Its log corroborates 72 successful process exits and helper startup on 5180, but does not log the claim/submit exchanges. Two schema-invalid submissions have null `submit_response`; their transport records retain a reason and lengths, not the original response. The third claim/cancel is represented only by a log line and the preview's cancelled disposition. These omissions prevent the independent execution reconciliation required by checklist items 2, 3 and 7. Preserve the archive; repair its evidence package from retained originals if available, without rewriting history or running a model to fill gaps.

Call wall totals are internally plausible: **9,037,957 ms** at call level, **9,037,716 ms** after per-attempt integer division, with **241 ms** discarded. The log's inner timing totals **9,037,948 ms**, nine milliseconds less than the outer call measurements. Both fit four-process capacity of **9,339,196 ms** for the declared **2,334,799 ms** run (38m 54.799s). That supports an attribution calculation, not measured per-item latency or independent verification of elapsed time, concurrency, startup/cleanup coverage or budget enforcement.

My rulings on the five execution decisions are:

| Ruling | Decision and evidence |
|---|---|
| 1. Deepest mapped gold ancestor | **Accept.** PROOF-PLAN checklist item 5 already specifies this rule. Keep strict equality to that mapped path as the gate. All 60 items remain in coverage; unmappable assigned items are incorrect. |
| 2. Eight-card batching and envelope/wall attribution | **Reject as the receipt-contract implementation.** Multiple single-item leases can be reasoned about together, but that does not authorize fictional per-process inputs or `model_calls=559`. Divided wall time is acceptable only as labeled attribution. Preserve one immutable call record, raw output and input bytes, then reference it from attempts. The current `response_text` is reconstructed: three absent model results and one over-length quote become harness-generated errors in the narrowed output. |
| 3. Reject/retry over-length quotes | **Accept the outcome policy.** `zYGDpG-pTho` attempt 1 has a 25-word quote in its retained batch result, becomes a client-error rejection, and receives one retry. All accepted memberships have fewer than 25 words. Keep the original model result distinct from the submitted error. |
| 4. Cancel a third claim without reasoning | **Accept the retry-ceiling policy, with the execution receipt unverified.** `2046008958511702016` has exactly two recorded reasoning attempts, both rejected; the log names claim 3 cancellation, and preview blocks activation on that cancelled row. Archive the claim and cancel request/response; keep model outcome `rejected` separate from terminal service state `cancelled`. |
| 5. Service `error` → receipt `rejected` | **Accept.** This is explicit in PROOF-PLAN. Four client-error submissions preserve raw service `outcome=error`; each maps to a rejected attempt and retains its reason. Schema and evidence rejections remain in the history. |

The quote service gap is confirmed, not repaired here. Three synthetic submissions with 24, 25 and 26 whitespace-separated words were all **accepted**, with one staged membership and zero current memberships each. `library_work.py` checks occurrence and a 1,000-character schema limit, but no word cap. The proof rule is **under 25 words, maximum 24**; the scorer's `<=25` is also inconsistent. Stage 2 must enforce the same word count in the service, client and receipt validator, with the scorer relying on full validated evidence.

The quality calculations are:

| Stratum | Coverage | Strict mapped precision | Exact-path precision | Predicted-descendant diagnostic | Abstentions |
|---|---|---|---|---|---|
| Timed | 30/47 = 63.83% | 15/30 = 50.00% | 0/30 | 21/30 = 70.00% | 17 unmapped |
| Text-only | 4/13 = 30.77% | 3/4 = 75.00% | 0/4 | 4/4 = 100.00% | 6 unmapped, 2 unsupported, 1 rejected |
| Overall | 34/60 = 56.67% | 18/34 = 52.94% | 0/34 | 25/34 = 73.53% | 26 |

The descendant diagnostic accepts any predicted child beneath the mapped gold path. It is not the gate: it rewards over-specific choices without gold support. The result document misses one such case, text-only item `2081888077858140160` (mapped `AI and ML`, predicted `AI and ML / Frontier Models`). There are **seven**, not six, over-specific assignments. The full confusion count is 18 right + 20 unmappable abstentions + 7 unmappable assignments + 7 over-specific assignments + 2 sibling errors + 6 mappable abstentions = 60. On the 33 mappable items, coverage is 27/33, strict precision 18/27, and descendant-tolerant precision **25/27 = 92.59%**, not 24/27. None of these subset calculations replaces the frozen per-stratum gate.

Taxonomy v1 contains **seven nodes, two top-level shelves**, not seven top shelves. The Phase 2 brief explicitly derived it from the same 60 gold items later called held-out. That proof-only reservation explains the construction, but those labels were not independent of taxonomy selection. Retain this score as a diagnostic benchmark. Stage 2 needs a fresh, sequestered evaluation set and a mapping rule fixed before execution; it must not tune on these results and call the old set unseen.

Commands run from the candidate worktree:

```powershell
python tests/validate_proof_receipts.py --receipts docs/library/proof/run-2026-09-05/receipts.json --require-real
# Exit 1: archived isolation path is outside this worktree.
python tests/validate_proof_receipts.py --verify-inputs --mock
# Exit 0: FROZEN_INPUTS_VALID, 548 targets.
python tests/validate_proof_receipts.py --self-test --mock
# Exit 0: 39 cases, zero model/helper calls.
python scripts/librarian/proof_score.py --receipts docs/library/proof/run-2026-09-05/receipts.json --holdout docs/library/holdout-split-2026-09-04.json --out _scratch/proof/audit-r/scorer
# Exit 0; quality FAIL in both strata.
python docs/library/proof/audit-r-2026-09-05.py --service-probe
# Exit 0; measurements.json includes independent replay and the three service probes.
```

The focused test command was `python -m pytest -q tests/test_library_work_validation.py tests/test_proof_run.py::test_refusal_when_anthropic_api_key_set tests/test_proof_run.py::test_refusal_when_port_5179_targeted -p no:cacheprovider --basetemp _scratch/proof/audit-r/pytest --junitxml _scratch/proof/audit-r/pytest.xml`: **12 passed in 0.79s**. All five data/output/temp environment roots were redirected below `_scratch/proof/audit-r/test-roots`; bytecode writes were disabled. The first test launch failed because redirecting APPDATA hid user-installed pytest. Adding its existing `C:/Users/hello/AppData/Roaming/Python/Python314/site-packages` directory to PYTHONPATH resolved that without installation. No full suite, helper smoke run, source recopy, installed build or model pass was attempted; none can substitute for the missing archived execution evidence.

Apply remains disabled. The next work is the [stage 2 contract sketch](PHASE2-STAGE2-SKETCH-2026-09-05.md), preceded by receipt/guard repair. Any acceptance dispute should go to Ryan with R-1–R-3 and this exact candidate; a valid JSON schema result cannot resolve them.

Final checks passed for Python syntax, measurement JSON, document links, whitespace, artifact fingerprints and report arithmetic. Git staging of exactly the four new audit/sketch/script/measurement files failed: `Unable to create .../.git/worktrees/codex14/index.lock: Permission denied`. Commit was not reached. The four files remain uncommitted in this worktree; no merge or push occurred. Candidate HEAD remains `b1eed2a8d0213b6043e3169f3e8ed4ce212e13ad`.
