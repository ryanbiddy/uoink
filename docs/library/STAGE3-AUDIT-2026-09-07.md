**P2-7 FAIL.** Run 2 is an admissible measurement under the guard ruling below.
Timed coverage and precision fail; text-only precision fails. All 439 accepted
memberships pass the independent evidence replay. Apply remains disabled.

Auditor: Codex / GPT-6 Astra, run AO, under [orchestration v1](ORCHESTRATION-V1-2026-09-04.md)
and the [AO brief](STAGE3-AUDIT-AND-STAGE4-SKETCH-BRIEF-2026-09-07.md).
Reviewed HEAD: `b9d8c0937b8c50c964aa76b05dea79c04c43f473`.
The receipt records `d78e3140b6f892bdd8b6ca513c098726977243fd`; that SHA was
captured when writing the archive, not at launch. The pre-execution record names
`15dfb8ef5e2018496f53f3da93e5f642703d662f`. The chronology check below reconciles them.

The [replay script](proof/audit-ao-2026-09-07.py) parameterizes the run AH audit
without changing AH's files. Its [measurements](proof/audit-ao-measurements-2026-09-07.json)
contain every check, call's byte/usage totals, completion boundary under both
guard rules, membership word count, scoring decision, development outcome and
input hash. Script exit 0 means the audit completed; the JSON verdict is the gate result.

| Hold-out v3 stratum | N | Assigned | Coverage, required >=0.80 | Correct | Strict precision, required >=0.90 | Result |
|---|---:|---:|---|---:|---|---|
| Timed | 47 | 37 | 37/47 = 0.787234; requires 38 | 28 | 28/37 = 0.756757; requires 34 correct at this denominator | FAIL both |
| Text-only | 13 | 12 | 12/13 = 0.923077 | 7 | 7/12 = 0.583333; requires 11 correct | FAIL precision |
| Pooled diagnostic | 60 | 49 | 49/60 = 0.816667 | 35 | 35/49 = 0.714286 | Cannot replace either stratum |

**Guard rule v2: AMEND.** Accept counting each failed completion once. Keep the
anonymous-event term in the contract, and require the runner to implement it
before stage 4. A submission rejection and its linked transport record describe
one failed completion; summing them gives that same failure double weight.
This ruling changes the contract explicitly. It does not claim that run 2 passed
the old contract or erase run 1's abort.

At each completion boundary, let S be the set of completed attempt IDs. Count
the union of rejected/errored IDs in S and IDs in S with a transport event by
that timestamp, then add the number of anonymous transport events by that
timestamp. Event IDs must be unique. Stop when N >= 20 and `10 * numerator > N`;
equality is allowed. Retain every event for accounting even when several events
contribute only one failed attempt. Deadline, concurrency and retry limits remain separate.

| Guard check | Observed | Expected / ruling |
|---|---|---|
| Run 1 reproduction | At completion 49: 3 rejected attempts, 3 linked events; old 6/49 = 12.2449%, distinct 3/49 = 6.1224% | Reproduced. Run 1 remains aborted. No later call starts appear. |
| Run 1 tail | 24 transport events after the abort boundary; 80 completion rows but 52 retained attempts, with 28 tail IDs lacking an attempt record | Preserve this incomplete aborted record. Only the complete prefix through boundary 49 supports this reproduction; no full-pass or complete-tail certification. All 1,063 checksum entries match. |
| Run 2, old rule | First breach at completion 28: 4/28 = 14.2857%. Maximum 8/50 = 16%. Final 34/563 = 6.0391% | Under the old rule these receipts are REJECTED: later calls continued after the first breach. A passing final ratio would not cure it. |
| Run 2, amended rule | No breach in 563 boundaries. Maximum 4/50 = 8%; final 17/563 = 3.0195% | PASS for this run. All 17 events are linked; there are no anonymous events. |
| Anonymous-event reproduction, AO-G1 | With 20 successful completions and 3 anonymous failures, the current runner does not abort; validator rejects at 3/20 | Implementation mismatch. The declared anonymous term is absent from `proof_run.py::_check_error_guard`. Repair before stage 4. It affects no run 2 boundary. |
| Other offline guard probes | N=19, exact 2/20 with duplicate rejection/event representation, strict 3/20, and successful attempts with linked transport failures behave as expected | PASS. These are isolated method probes, with no runner startup, model or helper. |

The archived validator predates the replay amendment. Comparing its syntax tree
with the current validator finds only the guard replacement and the optional
`config.effort` schema addition. I accept that schema addition for the already
declared stage 3 variable: every actual process argv independently contains
`--effort high`. The archived validator hash remains
`0b4192c99df419cf6c3dd92eb1ebbd94319b4d56fd0bb0d8826502a9660cbfbf`;
the current replay validator hash is
`d4a2ac860255c5f07629de371038a4607cbe921894f1a22936cf76e798d0ac71`.
The runner, service, prompt and card builder match their archived bytes. The
scorer matches after LF normalization. This ruling does not silently substitute
the current validator for the execution fingerprint.

The C1 checks apply the [measured-pass audit plan](STAGE2-AUDIT-PLAN-2026-09-05.md)
to v3's frozen identities and approved taxonomy.

| Check | Observed | Expected | Verdict |
|---|---|---|---|
| C1 selection | Excluding the 225 induction IDs, old 60 and v2's 60 leaves 226 IDs: 58 timed, 168 text-only. Seed `0x294941ba84eec02b` reproduces all 47/13 selections. | Recorded algorithm; zero overlap with all three exclusions | PASS |
| C1 freeze | V3 hold-out hash `855749ef…314c`, manifest file `3aeec73f…a90b`, structured manifest `213ef46f…8d35`; all source/card/head identities and all 548 targets match stage 1. | Exact frozen identities and hashes; zero exclusions | PASS |
| C1 seal and packet | All 60 gold rows sealed; gold `a4d4c293…2731e`, mapping `ec55c31c…6e0c`, adjudication and both original labels match the execution record. Packet has the exact 60 archived cards and no predictions. | Labels and mapping fixed before execution | PASS |
| C1 chronology | Labels committed at 03:14:05Z; pre-record written at 03:23:14.690720Z; database run created at 03:23:29.653Z on September 8 UTC. Recorded SHA was committed at 03:37:03Z. | Frozen evidence/code must precede execution | PASS with the explicit SHA explanation below |
| C1 taxonomy / prompt | One approved v3 revision `8a1b1603…8d04`, one rendered prompt hash `e4ff0059…3aa9`, one matching packet policy throughout. All manifest file and structured hashes reproduce. | Approved taxonomy, one frozen prompt, matching service run policy | PASS |
| C1 feasibility / containment | All 47/13 selected cards have mechanically eligible evidence. Exact stdin reconstruction and the identity/distinctive-excerpt scan find no evaluation data in template examples or archived induction inputs. | No dropped cases or hold-out examples | PASS within the recorded scan scope |

For chronology, `proof_run.py` reads `git rev-parse HEAD` while building the
receipt. Between the pre-record candidate and the recorded SHA, Git shows only
the execution record and four phase 3 documents added. All six archived code
fingerprints match the pre-record candidate after explicit EOL normalization;
all sealed inputs precede the database run. The execution record itself was
committed as `3340dc3ab6513cb7302ba26a2f2f2ccbd9c03ca6` at 03:23:15Z.
This resolves the apparent late execution commit without claiming a launch-time
SHA observation that the runner did not make. Stage 4 must record launch and
finish identities separately. The containment scan cannot prove absence of
unknown prior exposure or every paraphrase; the exact rendered inputs are the
stronger evidence for what these model calls received.

| Check | Observed | Expected | Verdict |
|---|---|---|---|
| C2 archive / references | Complete named archive staged into this worktree: 13,695/13,695 checksum entries and 4,482/4,482 receipt/head artifact references match | Original bytes, portable paths, no historical checkout access | PASS |
| C2.1 processes | 71 call records, 71 stdin files, 71 matching log entries; 563 uniquely linked attempts | Count actual processes once | PASS |
| C2.2 bytes | Stdin 3,593,880; schema 88,963; combined input 3,682,843; stdout 681,235; stderr 0 bytes. Every batch prompt rebuilt exactly. | Raw call-boundary bytes and sums | PASS |
| C2.3 accounting | 71 distinct sessions; four CLI counters and every `modelUsage` entry reconciled once per call | Reported counters and estimates kept separate from paid cost | PASS |
| C2.4 guard / C2.5 limits | Amended guard maximum 8%; peak concurrency 4; 15 reasoning retries, at most one per item; zero resends; latest launch 2,013,232 ms; total 2,136,820 ms | Guard at every completion; <=4 calls; launches within 7,200,000 ms | PASS under ruling |
| C2 execution variables | Every argv uses `claude-sonnet-5`, high effort, disabled tools and session persistence; largest batch 8; API-key-unset assertion present | Frozen subscription configuration | PASS |
| C2.6 HTTP | 3,067 raw exchanges: 1,289 claim/cancel, 563 submit, 1,214 list, 1 preview. The 1,853 normalized events reconcile, including failures and 4 cancel operations. All 12,907 HTTP JSON files scanned; no unredacted credential/lease fields found. | Complete exchange history and redaction | PASS |
| C2.7 registry | 548 work rows, 565 attempt rows, 563 submissions, 439 proposals. Two extra third claims are cancelled. Exports match both directions and the after database. | Distinguish model disposition from terminal service state | PASS |
| C2.7 state | Before/after memberships, pins and policies empty; projection 0; active v3 unchanged; zero applies; empty journal; apply false; preview cannot apply | Unchanged full projection state | PASS |
| C2.8 source / heads | Original source `2765cc35…4dfc`, schema 25; archived upgrade schema 27; 548 bounded heads match manifest and database policy hashes | Authorized source copy and original bounded heads | PASS |
| C2.9 portability / cleanup | Current validator exits 0 with `RECEIPTS_VALID_AUDIT_REQUIRED`; records show no owned children, stopped helper, no cleanup errors | Portable real-receipt validation and cleanup record | PASS |

The source and snapshots were read as bytes and deserialized into in-memory,
query-only SQLite connections. No original database was opened in place. The
supplementary committed `harness.log` is absent from `SHA256SUMS`; the replay
hashes it separately as `c84a77d9…9f6a7` and reconciles its 71 process lines. It
does not replace a call artifact. Historical cleanup is an archived assertion;
this audit did not observe old OS processes or exercise run 2's emergency stop.

| Reported usage | Value |
|---|---:|
| Input tokens | 226 |
| Output tokens | 799,989 |
| Cache-read input tokens | 10,059,305 |
| Cache-creation input tokens | 2,125,871 |
| Sonnet `modelUsage` estimated USD | 18.515687 |
| Haiku `modelUsage` estimated USD | 1.201237 |
| Total CLI estimated USD | 19.716924 |
| Paid cost | Unavailable; no invoice evidence |

Haiku also reports 1,196,692 input and 909 output tokens, with zero cache counters.
Those model-specific values are preserved separately; they are not added to the
four top-level CLI counters. Byte counts and elapsed time are independently
measured from artifacts; tokens and cost are provider-reported counters and estimates.

| Check | Observed | Expected | Verdict |
|---|---|---|---|
| C3 accepted evidence | 408 accepted primaries plus 31 secondaries; all 439 have matching packet/card/source/excerpt identities, approved shelf/path, confidence >=0.60, packet basis, eligible kind and one-excerpt quote occurrence | Validate every accepted membership | PASS |
| C3 word cap | Accepted quotes range from 1 to 24 words. Two raw secondary quotes on `-JXwa-WlkU8` have 28 and 26 words; both attempts are rejected and originals retained. | NFC + whitespace normalization; cap 24; preserve rejection provenance | PASS; client cap exercised |
| C4 mapping | All 60 mappings reproduce deepest approved ancestor; all selected items remain in coverage | Strict mapped primary equality | PASS |
| C4 quality | Timed 37/47, 28/37; text-only 12/13, 7/12 | Coverage >=0.80 and precision >=0.90 separately | FAIL |
| C4 scorer / refusals | Real scorer agrees with the independent numerators. Mock, stripped-artifact, wrong-taxonomy and missing-taxonomy inputs are refused. | Real validation before scoring; no taxonomy fallback | PASS |
| C4 regression / development | Historical old60 stays 34/60 coverage, 18/34 precision. V2 historical precision stays 31/41 and 11/12. All 225 development outcomes published. | Preserve prior results and all development rows | PASS |

The two over-cap raw replies became client-error submissions. The service
preserved that reason and staged no memberships from either attempt. They do
not demonstrate the service's own cap rejection on a submitted long quote;
the independent offline word-cap tests cover that branch. All 71 raw envelopes
are schema-valid, but five omit their requested unique result row. Those
envelopes and the resulting client errors remain separately recorded.

| Diagnostic | Timed coverage; strict precision | Text-only coverage; strict precision |
|---|---|---|
| V3 exact-path score | 37/47; 28/37 | 12/13; 7/12 |
| V3 predicted-descendant score | 37/47; 31/37 | 12/13; 8/12 |
| Current run on old60 | 37/47; 9/37 | 7/13; 4/7 |
| Current run on v2 | 40/47; 35/40 | 13/13; 12/13 |

There are five sibling errors in v3: four timed, one text-only. Four gold rows
have no approved ancestor; one is assigned incorrectly. In these v3 labels that
set equals the four `unmappable` rows; those definitions differ in older sets.
All 548 terminal model dispositions are 408 accepted, 124 unmapped, 14
unsupported and 2 rejected. The last two have cancelled terminal service work.
The 225 induction identities yield 116 accepted, 107 unmapped and 2 unsupported;
23 overlap old60, none overlap v2 or v3. These are development diagnostics.

The [result document](PHASE2-STAGE3-RESULT-2026-09-07.md) needs two corrections in
its causal reading. The ten timed non-assignments comprise nine `x_thread`
prose/clip cases and the video with rejected secondary quotes. Of the nine,
seven have assigned gold; `2091993721768116224` and `2093359169139326976` are
unmappable in the sealed gold, so assigning them would not recover correct
coverage. The fourteen incorrect primaries comprise thirteen mapped-path errors
and one unmappable over-assignment, `2090106310385688577`. High effort's causal
effect is unmeasured because stage 2 used a different hold-out and taxonomy.

The prose asymmetry is real: the old builder emits original prose as an excerpt
only when there are no clips, while the blind labellers could use eligible
`summary_hint` prose to determine a subject. Their mandatory clip quote could be
incidental. The old cards expose 96 prose-eligible timed cards with a nonempty
hint across the corpus, including 21 in v3. That count is a candidate repair
scope, not a measured card-v2 output or prediction of accuracy gains.

| Original blind labels versus sealed gold | Timed assigned / N; strict correct / assigned | Text-only assigned / N; strict correct / assigned |
|---|---|---|
| Grok | 46/47; 42/46 = 0.913043 | 11/13; 7/11 = 0.636364 |
| Gemini | 47/47; 39/47 = 0.829787 | 11/13; 9/11 = 0.818182 |

These values reproduce, but they establish no statistical ceiling. The gold was
adjudicated from these same labels, and their subject-evidence allowance differs
from the assignment contract. The two files have 42/60 exact outcome/path
agreements, including 37/47 timed and 5/13 text-only; proposed paths on unmappable
rows are included in that comparison. Neither label set meets text-only precision.
The [stage 4 sketch](PHASE2-STAGE4-SKETCH-2026-09-07.md) keeps 0.90 and requires
new labels under equal evidence rules.

Reproduce from this worktree in PowerShell:

```powershell
$env:PYTHONPATH = '.'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONUTF8 = '1'
python -B docs/library/proof/audit-ao-2026-09-07.py --self-test
python -B docs/library/proof/audit-ao-2026-09-07.py --source-archive 'C:\Users\hello\AppData\Local\AgentControlRoom\proof-archives\run-stage3-2026-09-07-run2' --aborted-source-archive 'C:\Users\hello\AppData\Local\AgentControlRoom\proof-archives\run-stage3-2026-09-07-run1-aborted'
python -B tests/validate_proof_receipts.py --self-test --mock
python -B tests/validate_proof_receipts.py --verify-stage3-freezes
python -B tests/validate_proof_receipts.py --verify-stage2-freezes
python -B -m pytest -q tests/test_library_word_cap_audit.py tests/library_work_astra/test_receipts_v2.py -p no:cacheprovider --basetemp=_scratch/proof/audit-ao/pytest-temp --junitxml=_scratch/proof/audit-ao/tests.xml
git diff --check
```

After staging, use `--archive _scratch/proof/audit-ao/archive` for offline replay.
The audit self-test passes 14 evidence cases and five guard probes, including
the reproduced runner mismatch. The validator passes 167 self-tests; both
identity freezes reproduce; 73 selected tests pass. Early audit-script attempts
needed UTF-8 handling, the separately committed log, and explicit handling of
run 1's incomplete tail; no producer artifact was changed to make replay pass.
No model, helper, network client, port 5179 or live index was used. Earlier files
and archives are untouched. No commit or merge was made. Fable owns collection
and the stage 4 dispatch; AO-G1 must be repaired and independently reviewed first.
