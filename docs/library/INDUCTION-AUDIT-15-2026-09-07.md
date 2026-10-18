**REJECT taxonomy-v3-2026-09-07 as delivered.** The decision has broken and
incomplete development-case bindings (AI-R1), the Education/Frontier teaching
precedence is narrower than R1 (AI-R2), and assignment rule 5 lets a chosen quote
determine the subject (AI-R3). Exact repairs follow. The hold-out v3 identity
freeze is complete and remains usable for the successor. Apply stays disabled.

Auditor: Codex / GPT-6 Astra, plan owner and independent auditor under
[orchestration v1](ORCHESTRATION-V1-2026-09-04.md). Scope: the Codex section of the
[run-AI brief](PHASE2-STAGE3-BRIEF-2026-09-07.md). Reviewed base:
`f1ee10f7f0aef6d8b86ffd8f6d7194dcd932c27c`. Final offline projection observation:
`2026-09-08T02:40:25.859682+00:00`; filenames retain the dispatch date. This is a
content audit of Fable's candidate and prompt, not acceptance of Astra's own
validator implementation or of a later integrated execution SHA.

| Bound input | Exact-file SHA-256 |
|---|---|
| [V3 revision decision](proof/taxonomy-v3-revision-decision-2026-09-07.json), 26,697 bytes | `db0a84c4fcce3701478d7e09b588e64010a3519f2ec22bdc590a779821779c66` |
| [V3 candidate](taxonomy-v3-2026-09-07.json), 15,188 bytes | `57bce9fed47eb4fc38dae65ded847fbc23d18a3712a6bb5512e67821b443bcc2` |
| [Approved v2 parent](taxonomy-v2-2026-09-05.json) | `015260a496f45322609573956401139f15522d0497e45b263b7e5b8b269696e6` |
| [Composer](../../scripts/librarian/compose_taxonomy_v3.py), checkout bytes | `d85e0987d096acefc12d96ca170133af42272e8e625ad5c329bfb5c5e065c3d8` |
| [Assignment prompt](../../scripts/librarian/prompts/assign.md), 6,877 checkout bytes | `7b9fb6b01378d33a19253907690536d4a82e34e4ea6977de591b6941c3e091cc` |
| [Service](../../library_work.py), checkout bytes | `4dcc2122bf6292d46cf6a088fe887fa2d6018d371409e6661ffab1bbbc75ed09` |
| [Frozen v3 identities](proof/holdout-v3-2026-09-07.json) | `855749efcaca5e985c04a9efef2decc4ee2dca3b24c8c3871f01079a9acd314c` |

| Check | Observed | Verdict |
|---|---|---|
| Composer reproduction | `compose_taxonomy_v3.py --check` exits 0. Separate serialization reproduces both files byte for byte, including the decision hash in the candidate wrapper. | PASS |
| Complete edit inventory | Exactly 12 changed fields on six shelves; replaying every recorded `before`/`after` field reconstructs the complete candidate. No other field changed. | PASS |
| Identity and structure | All 11 shelf IDs, paths, names, parents and retired flags unchanged. | PASS |
| Definitions and cues | The six modified shelves retain their stated subjects. Education's broader teaching definition lacks complete Frontier precedence in operative cues; see AI-R2. | FAIL for R1 |
| Case provenance | Three declared IDs are not corpus or v2 identities. R5's declared case appears in zero edit records. Mixed-rule field edits omit relevant case groups. | FAIL, AI-R1 |
| Projection and rendering | Independent eight-field projection equals the composer, validator normalization and complete service-returned nodes. Every definition/include/exclude survives prompt rendering. | PASS for preservation; semantic defects also survive |
| Service lineage | Direct service calls on a fresh synthetic index approve v1, v2 and v3 with the expected revisions. No helper, HTTP endpoint, corpus source or live index is used. | PASS, synthetic observation only |
| Leakage review | Eleven corrected development identities and all 60 v3 identities: no ID or normalized eight-token card-text overlap in the cues or prompt. No case-specific names, figures or copied passages found in the authored changes. | PASS within the stated inspection limits |
| Prompt amendment | Git diff confirms only rules 4 and 5 changed. Rule 4 expresses both parent/child directions. Rule 5 uses the selected quote as the subject denominator. | FAIL, AI-R3 |

The 12 changes are Education definition/include/exclude; Developer Tools
definition/exclude; Frontier Models include/exclude; Industry include/exclude;
Security include; and AI and ML definition/include. News and Current Events,
Space and Science, AI Agents and Automation, Generative Media and Spaceflight
are unchanged as complete nodes. No node addition, deletion, reparenting or
retirement occurred.

The following boundary review covers both directions after projection. Each cue
is read as a claim about the established subject, consistent with prompt rule 1;
a passing mention does not trigger a different primary shelf.

| Rule and boundary | Direction one | Reverse direction | Ruling |
|---|---|---|---|
| R1, Education / Developer Tools | Education explicitly takes precedence for hands-on teaching; its definition includes conceptual teaching. | Developer Tools' definition excludes taught material and its exclusion sends tutorials/workshops/lectures to Education. Education excludes non-teaching announcements. | PASS |
| R1, Education / Frontier Models | Hands-on teaching explicitly wins; the separate conceptual-explanation include has no precedence clause. | Frontier's directed teaching exclusion adds `with brief performance claims`, which R1 does not require. Its architecture/evaluation includes remain operative. | FAIL, AI-R2 |
| R2, AI and ML parent / children | Parent is primary only when no child subject is established; generic task-fit and passing company mentions stay broad. | Prompt rule 4 requires the child when its subject is established; Developer Tools, Frontier and Industry return the named generic cases to the parent. | PASS, subject-selection repair AI-R3 still required |
| R2b, Industry / parent | Industry explicitly includes adoption/labour/task economics and chip competition with company implications. | Parent's fallback requires no established child subject; passing company/acquisition references return to the parent from Industry. | PASS; R2b metadata needs AI-R1 |
| R3, Industry / Frontier Models | Frontier includes dominant scaling/post-training/pipeline discussion; Industry excludes that case when economics is secondary. | Frontier sends dominant adoption/labour/task economics or accelerator competition to Industry; Industry includes those subjects and excludes technical model evaluation. | PASS at the cue level; AI-R3 affects choosing the dominant subject |
| R4, Security / parent | Security explicitly includes catastrophic/existential AI-risk warnings and takes precedence over the parent. | General AI discussion without that subject remains eligible for the parent only when no other child applies. | PASS |
| R5, Developer Tools / Agents | Developer Tools sends personal assistance for non-engineers to Agents; Agents retains sensing/acting assistants and non-engineering task execution. | Agents excludes coding-specific harnesses/IDEs/SDKs to Developer Tools. | PASS in operative fields; provenance fails AI-R1 |

AI-R1: repair the case identities and bind every rule represented in a field edit.
The [stage 2 audit's complete error table](STAGE2-AUDIT-2026-09-06.md) and archived
cards identify these exact replacements in `DEV_CASES`:

| Current string | Required full identity |
|---|---|
| `2086120621734326` | `2086120621734326272` |
| `2091248592774369` | `2091248592774369280` |
| `2094184640873373` | `2094184640873373696` |

The current strings match no frozen identity. Each has exactly one prefix match,
shown above, but a prefix is not an identity. After correction all 11 cases are
members of hold-out v2 and none is a v3 identity.

The `developer-tools.exclude` edit is labelled only R1, although its new entries
implement R1, R5 and R2. `DEV_CASES['R5']` contains `2091537085874520064`, but that
case is absent from every recorded edit. The same loss affects the mixed-rule
Frontier and Industry exclusions. Add an explicit `rules` list to the edit
records, retaining `rule` if consumers need it, with these values:

| Field edit | Required `rules` |
|---|---|
| `developer-tools.exclude` | `["R1", "R2", "R5"]` |
| `frontier-models.exclude` | `["R1", "R2", "R3"]` |
| `ai-industry-and-business.include` | `["R2b", "R3"]` |
| `ai-industry-and-business.exclude` | `["R2", "R3"]` |
| All other existing edits | A one-element list containing the current rule |

Set each edit's `development_cases` to the sorted unique union of the corrected
`DEV_CASES` groups named in its `rules`. Add
`R2b: "Industry subject established by adoption/labour/task economics or accelerator competition; child over parent"`
to `evidence.rules`. Validate exact membership of every development ID in the
frozen v2 identity set and in the archived cards, and require each declared rule
to occur in an edit. Regenerate the decision and candidate through the composer;
do not manually patch generated JSON.

AI-R2: encode all of R1's teaching precedence, including conceptual explanations.
The current Frontier exclusion is:

> a tutorial or explanation whose purpose is to teach, with brief performance claims -> AI and ML / Education

R1 in the composer header has no `brief performance claims` condition. A
conceptual lesson can explain architecture through examples and give a detailed
capability evaluation. Education includes that lesson, while Frontier still
includes its architecture/evaluation subject and only directs teaching with brief
claims away. The conceptual Education include has no explicit precedence, unlike
the hands-on include. This leaves the required general teaching boundary
unresolved after projection.

A synthetic review case makes the gap concrete: "Today's conceptual explanation
teaches how a transformer architecture works. The examples trace attention
weights and explain the model's information flow. A detailed benchmark evaluation
then develops that explanation across twelve tasks." R1 requires Education. The
current operative fields do not state that priority for this conceptual case.
This is a semantic counterexample, not an observed model prediction or a v3 card.

Replace the first `frontier-models.exclude` entry with exactly:

```text
a tutorial, workshop, lecture or conceptual explanation whose purpose is to teach, even when it discusses a specific model, architecture or capability evaluation -> AI and ML / Education
```

Replace the final `education.include` entry with exactly:

```text
conceptual explanation of how a technique, architecture or orchestration pattern works, with examples (takes precedence over AI and ML / Developer Tools and AI and ML / Frontier Models when the excerpt's purpose is to teach)
```

These repairs change two existing edited fields and preserve the 11-node set.
Retain the other include/exclude boundaries and record their corrected R1 case
bindings under AI-R1. Recheck both teaching and non-teaching directions before
approval.

AI-R3: choose the subject from the input excerpts before selecting evidence.
Rule 5 currently defines dominance as `what most of the quoted words are about`.
Rule 3 makes the evidence quote an output chosen by the model. That creates a
circular decision rule.

Development card `2095783502306545664` supplies a reproducible case. Its unchanged
excerpts contain both `with like an affordable amount of spend on tokens` and
`we had figured out a new kind of post-training`. Each is an exact nine-word
substring of one excerpt and meets the quote-length requirement. Selecting the
first quote makes the quoted words economic; selecting the second makes them
technical. The input subject has not changed. Stage 2's adjudicated primary is
Frontier Models; the amendment must not let the evidence selection recreate the
Industry error. No model was run to demonstrate this inconsistency.

Replace the second bullet of assignment rule 5 with exactly:

```text
When the supplied excerpts support two shelves, apply the taxonomy's explicit precedence and exclusions first. Otherwise choose the primary from the dominant subject of all supplied excerpts, before choosing a supporting quote. Judge what the excerpt set teaches, describes or evaluates; do not count words in the selected evidence quote. Teaching takes precedence over Developer Tools and Frontier Models when that is the excerpt set's purpose, including conceptual explanations, tutorials, workshops and step-by-step walkthroughs.
```

Keep rule 4 and the remaining prompt contract unchanged. This is an instruction
to the prompt owner; this worker did not edit the prompt. The replacement is
derived from R1-R5 and development evidence, with no v3 content used as an example.

The projection checks pass independently of these findings. Projection retains
`shelf_id`, NFC `path`, `definition`, `include` and `exclude`; derives `name` and
`parent_shelf_id`; retains the false retired flags; and sorts by depth, path, ID.
Canonical hashes use sorted-key UTF-8 JSON, `ensure_ascii=False`, separators
`(',', ':')`, and no trailing newline unless specified. The prompt renderer
escapes `>` as `\u003e` inside JSON; decoding the rendered taxonomy preserves
every node and directed cue exactly. That escape is not a dropped boundary.

| Observed projection identity | Value |
|---|---|
| Parent v2 revision | `bd9e7f9d572a709a9e0f939b5433932fb36840278929946c2c6870ac0158dd97` |
| Candidate v3 revision, independently calculated and returned by the synthetic service | `f0a2d53384b2559847f92313511b15173a7cdac3c079ab24c133593e615d56f6` |
| Canonical service document plus LF, 12,001 bytes | `4c4ddca248d62c8d288ce94122dba82b648f85e9b2a8326deb3a1c17db6c5ed4` |
| Canonical v3 approval request in the synthetic probe | `0614960502f0effd1b43ca5a97a125be141705ad41f3bc9448aa138f64ce8d89` |
| Canonical v3 service response in the synthetic probe | `25257a9046931b8734aaf5f2cb66fe7ecd83c78621d06782ca66538055c4d9ac` |

The probe called `LibraryWorkService.approve_taxonomy` directly on a new empty
SQLite index under this worktree's `_scratch/proof/run-ai/`, passing normalized
v1, v2 and v3 documents in order. It observed all three complete responses and
closed and removed that temporary index/store. It did not activate a taxonomy or
start a library-work run. The execution database's service response is still
pending. This rejection supplies no `--approved-by` / `--approval-record` export
arguments and no approved-file hash; a successor ruling must provide them after
the repaired content reproduces.

For leakage checking, a local script compared all definitions/include/exclude
strings and the entire prompt against the corrected 11 development cards and 60
selected v3 cards. It scanned identity strings and contiguous eight-token windows
from titles, channels, summary hints and excerpts, using NFC, case folding and
Unicode word tokens. Matches: zero. V3 card contents were processed locally and
not printed or used to author repairs; no v3 labels were opened. The review of
authored changes found generic subject rules, without copied names, statistics
or passages. This supports absence of direct copying; lexical checks cannot
prove absence of every possible paraphrase or unknown prior exposure.

The [stage 3 gate](STAGE3-GATE-2026-09-07.md) binds the full hold-out and thresholds.
`stage3_freezes()` first verifies the v2/induction reservations, pins the stage 2
archive's exact hash, validates all 548 card/source bindings and selects from the
226 remaining identities. Its CLI refuses writes without `--mock` and refuses
to overwrite a differing reservation. Verification compares every field. The
timed-shortfall branch preserves the actual denominator; insufficient text-only
availability refuses a new draw. Feasibility reports evidence availability and
does not remove ineligible rows.

Validation completed:

```powershell
python -B scripts/librarian/compose_taxonomy_v3.py --check
python -B tests/validate_proof_receipts.py --freeze-stage3 --mock
python -B tests/validate_proof_receipts.py --verify-stage3-freezes
python -B tests/validate_proof_receipts.py --verify-stage2-freezes
python -B tests/validate_proof_receipts.py --self-test --mock
python -B -m pytest -q _scratch/proof/run-ai/test_stage3_freezes.py tests/library_work_astra/test_induction_contract.py tests/library_work_astra/test_receipts_v2.py -p no:cacheprovider --basetemp _scratch/proof/run-ai/pytest --junitxml _scratch/proof/run-ai/tests.xml
python -B -m pytest -q _scratch/proof/run-ai/test_stage3_freezes.py -p no:cacheprovider --basetemp _scratch/proof/run-ai/pytest-final --junitxml _scratch/proof/run-ai/stage3-final.xml
python -B _scratch/proof/run-ai/audit_v3.py
git diff --check
```

Commands ran with `PYTHONUTF8=1`, `PYTHONDONTWRITEBYTECODE=1` and `PYTHONPATH` set to
this worktree. The combined suite passed 141 tests (125 existing receipt/induction
tests and 16 initial v3 probes). After adding the ineligible-evidence probe and
tightening the CLI byte assertion, all 17 v3 probes passed. They cover independent
manifest-based selection and full card hashing, exclusions, 46/0 timed
shortfalls, text-only shortage, ineligible evidence without replacement, source
and metadata tampering, CLI refusal, idempotence and conflicting identity flags.
The existing self-test passed 167 cases, with zero model/helper calls. The audit
probe required three local fixes before passing: JSON escape-aware comparison,
nullable card text handling, and v1 retired-flag normalization matching the
existing runner. None required a project implementation change.

The local replay, probes, measurements and JUnit files are ignored artifacts under
`_scratch/proof/run-ai/`; they are not additional delivery files. The final
validator's checkout SHA-256 is
`0b4192c99df419cf6c3dd92eb1ebbd94319b4d56fd0bb0d8826502a9660cbfbf`,
and its LF-normalized SHA-256 is
`cde4d189aed1894024f4f3a2c8f38eabc4f2d80752c737fd6102da8f70cca3aa`.
These implementation checks require independent review after integration; they
do not certify Astra's patch by themselves. The full repository suite,
installed-client acceptance, stage 3 execution-manifest freeze and measured pass
were outside this run.

Delivered files are the validator, hold-out v3 JSON, stage 3 gate and this ruling.
No runner, composer, prompt, scorer, candidate or decision was edited. No model,
helper, network client, port 5179, live index, commit or merge was used. Fable owns
the three finding repairs and a successor audit before approval, blind labelling,
sealing and execution; the frozen v3 identities must stay unchanged.
