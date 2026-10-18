**RECEIPTS REJECTED.** Run AH finds two execution-contract defects: supplemental HTTP exports retain lease tokens, and the scorer accepts receipts without their original execution artifacts. The independently recomputed quality result also fails: timed precision is **31/41 (75.61%)**, below the required **37/41**. Text-only passes. P2-7 remains unestablished and apply stays disabled.

Auditor: Codex / GPT-6 Astra, independent auditor and plan owner under [orchestration v1](ORCHESTRATION-V1-2026-09-04.md). Scope: C1–C4 of the [audit plan](STAGE2-AUDIT-PLAN-2026-09-05.md), as dispatched in the [run AH brief](STAGE2-MEASURED-AUDIT-BRIEF-2026-09-06.md), using the [stage-2 gate](STAGE2-GATE-2026-09-05.md). Reviewed candidate: `b0c896acaa5a976f10a514e8c255890a08224491`. Measured execution: `746045dcdb4900bbb7aaf2a78ad7fe58d723409a`; pre-execution integration: `9de497e7eb4d87ecb42956fb4b6d8d7ea4ed521c`.

The [replay script](proof/audit-ah-2026-09-06.py) produces the [measurements](proof/audit-ah-measurements-2026-09-06.json): 31 checks, every process's bytes and reported usage, 557 completion boundaries, the concurrency sweep, 431 membership checks, all 60 scoring decisions, all 225 development outcomes, both old-set reports, CLI refusal probes and hashes of every input read. Exit 0 means the audit completed; the JSON verdict controls acceptance.

| Bound artifact | SHA-256 |
|---|---|
| Measured receipt, original bytes | `294941ba84eec02bf607aa7044ed45454634f99b8dcbf0b4adc9fe35349017b4` |
| Archive SHA256SUMS, including location footer | `c5862079b4055b736d9e17a3a22a67c5308f107e83134f33d081d73ee32e5730` |
| AH replay script | `bec572cddbadb2a8688de83155db63f2346b8e9db3372014259b51c136b5f480` |
| AH measurements | `0ae42d57b1e26454fdc8cad33834e25fef9dc5399045c8a89aeb2c9c630924fa` |

The checkout omits eight database/WAL files by design. The `SHA256SUMS` footer identifies their original location as `C:/Users/hello/AppData/Local/AgentControlRoom/proof-archives/run-stage2-2026-09-06/state`. I verified those bytes and staged a complete archive under `_scratch/proof/audit-ah/archive`. All **6,905 checksum entries** and **2,780 receipt artifact references** match. The initial missing-file validator result was resolved by staging; it is not an outstanding finding. The original archive and all tracked inputs remain unchanged. No other checkout, live index, model, helper or network endpoint was opened; no commit or merge was made.

C1 verifies the freeze and its use by the service.

| Check | Observed | Expected | Verdict |
|---|---|---|---|
| Original archive and identity freezes | Stage-1 receipt rehashes to `2b4e824e…469c`. Induction and holdout reproduce their gate LF hashes, `20122edb…9840` and `28fdb16a…8d78`. Exact CRLF checkout hashes are recorded separately. | Original receipt plus unchanged frozen identities. | PASS |
| Selection pool and draw | 225 induction IDs; 23 overlap the old 60. Excluding both sets leaves 286: 105 timed, 181 text-only. One seeded RNG reproduces every selected ID, 47 timed then 13 text-only. | Seed `0x2b4e824ea9f93999`, sorted pools and selected strata; no replacement. | PASS |
| Seals and chronology | Gold/mapping sealed at commit `9de497e`, 06:12:29 UTC; execution record written 06:12:42.409939 UTC and committed as `746045d`. Database run creation is 06:12:57.795 UTC. All bound file hashes match. | Labels, mapping, approval and frozen execution inputs precede execution. | PASS |
| Blind labelling packet | Packet 12 contains exactly the 60 original frozen cards and candidate taxonomy, with no prediction fields; packet-12 carry-forward is the existing audit-13/14 ruling. Labeller files and adjudication predate execution. | Label preparation without measured predictions. | PASS |
| Feasibility | 47/47 timed and 13/13 text-only have eligible evidence. All 60 remain targets. The pre-execution holdout already records this bound. | Report feasibility before execution; drop none. | PASS |
| Taxonomy and prompt | Every packet has revision `bd9e7f9d572a709a9e0f939b5433932fb36840278929946c2c6870ac0158dd97`. Prompt text hash is `662e8ee8133110beefb59b948e4dcebf9e64104c1e6f97deb08aee4000221ae1`. Every packet policy, archived claim and database run policy binds these inputs. | One approved service-returned revision and one frozen prompt across all attempts. | PASS |
| Prompt containment | 60 prompt/template/induction-stdin files scanned; zero holdout IDs, card hashes, excerpt IDs or distinctive excerpt matches. Assignment stdin is rebuilt exactly from the fixed template and its input cards. | No holdout example or induction/tuning input. | PASS within archived scope |
| Implementation identity | Runner, scorer, service, prompt and card-builder bytes equal their archived fingerprints. Validator differs only in checkout line endings; LF bytes agree. | Review the execution implementation; distinguish file-byte and text identity. | PASS |

Containment covers all librarian prompt templates and archived induction stdin found in this checkout. Measured assignment cards necessarily appear in their own assignment input. Evaluation packets, labels and this audit are evaluation material. No assertion is made about unrecorded private tuning or historical OS egress telemetry.

C2 replays the execution record. Reported CLI token counts are observed envelope fields, not an independent tokenizer measurement; dollar amounts are CLI estimates, with paid cost unavailable.

| Check | Observed | Expected | Verdict |
|---|---|---|---|
| Archive bytes | All 6,905 checksum entries and 2,780 receipt references match after original database staging. | Available, portable original bytes for every archived input. | PASS |
| C2.1 Calls/processes | 71 unique calls, stdin files and harness-log completions; 557 uniquely owned attempts. Log duration, exit and stdout-byte values agree. Per-item usage remains unavailable. | Count processes once; retain item views without summing them as process input. | PASS |
| C2.2 Boundary bytes | Exact reconstruction of all 71 stdin files. Prompt 3,276,715 B; schema 88,963 B; combined input 3,365,678 B; stdout 690,185 B; stderr 0 B. Raw results and schemas agree. | Raw byte lengths and call sums equal receipt totals. | PASS |
| C2.3 Usage/cost | Four counters reconcile exactly; all Sonnet and Haiku entries preserved. 71 distinct sessions; CLI estimate $23.2390076; paid cost null. | Sum once per call/session, preserving every model and estimate provenance. | PASS |
| C2.4 Error guard | Maximum after N≥20 is 4/89, **4.49%**. Final is 22/557, **3.95%**: 11 rejections plus 11 linked submit-failure events. No strict breach at any of 557 completion boundaries. | Strictly greater than 10% triggers stop; equality does not. | PASS |
| C2.5 Deadline/concurrency | Peak four open calls; last call starts 2,586,665 ms after start; total 2,628,284 ms. Nine retries, maximum two reasoning attempts/item; zero identical-payload resends. | Four calls, two-hour start deadline, one reasoning retry. | PASS |
| C2.6 HTTP completeness | 1,371 original exchanges: 440 claims, 557 submits, four cancels, one preview, 369 list/status exchanges. The 1,002 claim/submit/cancel/preview pairs reconcile with normalized history. No helper credential exposure found. | Preserve every exchange, failures and cancellation history. | PASS |
| C2.6 HTTP redaction, AH-R1 | **1,264 supplemental HTTP files contain 2,240 unredacted `attempt_token` fields.** Main `http-*` wrappers are redacted. | Gate requires nested lease tokens redacted in HTTP exports. | **FAIL** |
| C2.7 Registry | 548 work/manifest rows, 559 service attempts, 557 submissions, 431 proposals. All five tables match the after database; supplementary export agrees. Two extra attempts are third claims, both cancelled. | Bidirectional agreement, including original submissions and service terminal states. | PASS |
| C2.7 State | Both database images and JSON snapshots agree: zero memberships, pins, policies and applies; projection revision 0; v2 active. Journal empty; apply flag false; preview `can_apply=false`. | No projection/state mutation or apply. | PASS |
| C2.8 Source/upgrade | Source SHA is `2765cc35…4dfc`, schema 25; upgraded image `4e7fb5ae…c25e`, schema 27. Original source hash agrees with both recorded before/after claims. | Named source and measured upgraded duplicate authenticated. | PASS |
| C2.8 Heads | 548 original bounded heads match both manifest raw hashes and database `corpus_head_hashes` after recorded decoding. | Complete private archive, maximum 8,192 B/head. | PASS |
| C2.9 Portability | On the complete scratch copy, `--stage2 --require-real` exits 0: `RECEIPTS_VALID_AUDIT_REQUIRED`, 548 targets, 557 attempts, nine retries, 60 measured items. | Validate inside this checkout without reading historical checkout paths. | PASS |

Every raw model response is schema-valid. Two omit their requested item row; both original envelopes remain present beside generated client-error submissions. Nine other rejected attempts fail one-excerpt quote occurrence. There are no observed malformed-schema replies, over-cap quotes or transport resends to exercise those branches in this run. The 11 events called transport failures by the receipt are linked submit failures; the guard above includes them exactly as the declared formula requires. Cleanup records zero owned processes, stopped helper and no cleanup errors. No guard breach occurred, so emergency termination is not claimed as exercised.

| CLI usage source | Input | Output | Cache read | Cache creation | Estimated USD |
|---|---:|---:|---:|---:|---:|
| Top-level counters, 71 envelopes | 222 | 1,034,756 | 9,260,888 | 2,478,488 | 23.2390076 |
| `modelUsage`: claude-sonnet-5 | 222 | 1,034,756 | 9,260,888 | 2,478,488 | 22.1141336 |
| `modelUsage`: claude-haiku-4-5-20251001 | 1,120,514 | 872 | 0 | 0 | 1.1248740 |

The top-level token sum is **12,774,354**. The model rows are a separate accounting view and are not added to that sum. Haiku's entries are retained even though the top-level counters match the Sonnet entries.

AH-R1 reproduces without printing a token: parse `http/00001_claim_library_work_response.json` and test whether `body.result.work[0].attempt_token` equals `[REDACTED]`; it does not. The matching combined exchange file repeats the exposure. All affected file names and JSON field paths, without token values, are in `http.unredacted_http_files` in the measurements. This is an HTTP-export defect, not a claim that the helper authentication secret leaked. The validator checks receipt-referenced normalized wrappers and therefore does not detect these supplemental exports.

C3 checks every accepted membership, beyond the 53 assigned holdout items shown in the scorer report.

| Check | Observed | Expected | Verdict |
|---|---|---|---|
| Card/packet identity | Every one of 557 packets rehashes; card bytes match the frozen original cards and source/card identities. Claims, submissions and stored packets agree. | Correct video, source revision, card and packet identity. | PASS |
| All memberships | 378 accepted primaries and 53 secondaries, 431 total; each matches its approved shelf ID/path. Minimum confidence 0.62; all bases `packet`. | Every membership checked, confidence ≥0.60. | PASS |
| Excerpt/source validity | 207 timed and 224 text-only memberships; kind, source eligibility, timing and occurrence within one identified excerpt pass. | Eligible source; no cross-excerpt support. | PASS |
| Quotes | All 431 quotes pass NFC + `str.split()` + single-space normalization, case/punctuation retained; maximum 24 words, with the defensive character cap enforced. | 1–24 words and ≤1,000 characters. | PASS |
| Over-cap rejection evidence | No original model membership exceeds 24 words. The independent service word-cap suite passes all 27 synthetic tests. | Preserve any real over-cap rejection; do not invent a measured probe. | Not exercised in measured pass |

| Words | Memberships | Words | Memberships | Words | Memberships |
|---:|---:|---:|---:|---:|---:|
| 1 | 1 | 9 | 34 | 17 | 27 |
| 2 | 2 | 10 | 40 | 18 | 14 |
| 3 | 2 | 11 | 41 | 19 | 21 |
| 4 | 3 | 12 | 36 | 20 | 17 |
| 5 | 5 | 13 | 33 | 21 | 12 |
| 6 | 8 | 14 | 23 | 22 | 6 |
| 7 | 30 | 15 | 27 | 23 | 5 |
| 8 | 24 | 16 | 19 | 24 | 1 |

C4 uses `strict-mapped-primary-v2`: NFC-normalize and trim each path segment, preserve case, map gold to its deepest unambiguous approved ancestor, and require strict primary equality. All 60 sealed mapping rows reproduce. Every selected item remains in its stratum denominator. Exact-path and descendant-tolerant counts below are diagnostics only.

| Stratum | N | Assigned A | Correct C | Coverage A/N | Precision C/A | Required C at actual A | Verdict |
|---|---:|---:|---:|---:|---:|---:|---|
| Timed | 47 | 41 | 31 | 87.23% | 75.61% | 37 | **FAIL, AH-Q1** |
| Text-only | 13 | 12 | 11 | 92.31% | 91.67% | 11 | PASS |
| Overall diagnostic | 60 | 53 | 42 | 88.33% | 79.25% | — | No pooled substitute |

| Diagnostic | Timed | Text-only | Overall |
|---|---:|---:|---:|
| Exact-path correct / assigned | 31/41 | 11/12 | 42/53 |
| Descendant-tolerant correct / assigned | 33/41 | 11/12 | 44/53 |
| Sibling errors / assigned | 6/41 | 0/12 | 6/53 |
| Unassigned / selected | 6/47 | 1/13 | 7/60 |

There is one gold row marked `unmappable`, `2090888779125116928`; the model leaves it unmapped, so over-assignment is **0/1**. Its sealed deepest ancestor is `AI and ML`. Separately, zero v2 gold rows lack an approved ancestor, so over-assignment on that definition is **0/0 (not applicable)**. The two definitions must not be conflated.

These are all 11 assigned primary errors; they account for the complete precision shortfall. Paths below omit the common `AI and ML` prefix; “parent” means that prefix itself.

| Video ID | Stratum | Sealed mapped primary | Observed primary | Error |
|---|---|---|---|---|
| `2083664004506145276` | Timed | parent | Frontier Models | Over-specific child |
| `2086120621734326272` | Timed | Education | Developer Tools | Sibling |
| `2089011298621399260` | Timed | Education | Developer Tools | Sibling |
| `2091208884786520487` | Timed | Education | Developer Tools | Sibling |
| `2091248592774369280` | Timed | AI Industry and Business | parent | Parent too broad |
| `2091537085874520064` | Timed | AI Agents and Automation | Developer Tools | Sibling |
| `2094184640873373696` | Text-only | AI Industry and Business | parent | Parent too broad |
| `2094227178032599040` | Timed | parent | AI Industry and Business | Over-specific child |
| `2095783502306545664` | Timed | Frontier Models | AI Industry and Business | Sibling |
| `FLcrvMfHUJM` | Timed | Security | parent | Parent too broad |
| `ub2xbSlay7g` | Timed | Education | Frontier Models | Sibling |

The unchanged historical old-60 regression reproduces **34/60 coverage and 18/34 strict precision**. Timed is 30/47 coverage and 15/30 precision; text-only is 4/13 and 3/4. The original split, labels, taxonomy and result remain unchanged. Historical exact-path is 0/34 and descendant-tolerant is 25/34; seven assignments have no approved gold ancestor.

For completeness, applying the current stage-2 predictions to those same old IDs and labels, mapped under v2, gives a separate development diagnostic: **43/60 coverage and 14/43 strict precision**. Timed is 36/47 and 10/36; text-only is 7/13 and 4/7. Exact-path is 0/43, descendant-tolerant is 23/43, with seven sibling errors and 13 assignments among 27 rows without an approved ancestor. This does not replace the historical regression or the v2 gate.

All **225 development items** are listed individually in the measurements: **101 accepted, 109 unmapped, 15 unsupported**. Across all 548 targets, final reasoning dispositions are 378 accepted, 130 unmapped, 38 unsupported and two rejected; those last two have cancelled terminal service states. Outcome counts are not development accuracy labels.

| Scorer contract check | Observed | Expected | Verdict |
|---|---|---|---|
| Strict mapping | All 60 frozen mappings agree; independent raw-submission score matches the archived report. | Strict equality, fixed strata and denominators. | PASS |
| Mock refusal, AH-R2 | Changing only `mode` to `mock` returns exit 0 and writes a report. It correctly labels that result `FIXTURE_EVALUATION_ONLY`. | Plan C4 explicitly requires refusing to run on mock receipts. | **FAIL** |
| Unvalidated receipt refusal, AH-R2 | Remove `calls`, `http_history`, `state_artifacts`, `completion_order` and `execution`; scorer still exits 0, reports measured usage and writes a gate `FAIL` report. | Require real validated original artifacts before scoring. | **FAIL** |
| Taxonomy substitution | Supplying v1 with the sealed v2 mapping exits 1: mapping names a different taxonomy version. | No fallback or substituted taxonomy. | PASS |

AH-R2 is in `scripts/librarian/proof_score.py`, `validate_receipts_for_scoring` and its CLI caller. The negative fixtures and exact commands/output are generated under `_scratch/proof/audit-ah/` and copied into `cli_probes` in the measurements. The unvalidated fixture keeps numeric summaries but removes the originals; it still receives the same 31/41 and 11/12 score. No archive file is edited to reproduce this failure.

Reproduce the complete audit, including authenticated database staging, from the worktree root:

```powershell
$env:PYTHONUTF8 = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'
python -B docs/library/proof/audit-ah-2026-09-06.py --database-archive 'C:/Users/hello/AppData/Local/AgentControlRoom/proof-archives/run-stage2-2026-09-06/state'
python -B docs/library/proof/audit-ah-2026-09-06.py --self-test
```

For later offline replay of the staged bytes, use `--archive _scratch/proof/audit-ah/archive`. Staging copies only the eight checksum-named database/WAL files from the external archive; it copies the other archive files from this checkout. SQLite images are queried in memory, with WAL header mode changed only in the in-memory image after hashing the original bytes.

Validation completed: replay self-checks pass, including 14 evidence-boundary cases; validator `--self-test --mock` passes **167 cases**, reporting zero model and helper calls; `--verify-stage2-freezes` passes; `tests/test_library_word_cap_audit.py` passes **27 tests**. The suite XML is `_scratch/proof/audit-ah/word-cap-tests.xml`. The scorer negative probes fail their required refusals as described above; those are audit findings, not passing tests. The full repository suite and installed-client acceptance were outside this C1–C4 replay.

Fable should route AH-R1 to the export owner and AH-R2 to the scorer owner. Preserve this archive as the failing evidence. A successor audit export must redact every HTTP representation, identify its unchanged private originals and bind new hashes; the scorer must require full real receipt validation and reject the recorded negative fixtures. Both repairs can be reviewed without model execution. AH-Q1 remains a quality failure even after record repair. Any further measured model pass requires a documented repair and new dispatch under the existing gate, with no subset rerun, changed denominator or reuse of these holdout errors as tuning examples. This audit authorizes no new execution or apply.
