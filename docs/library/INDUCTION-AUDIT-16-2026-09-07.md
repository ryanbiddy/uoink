**APPROVE taxonomy-v3-2026-09-07.** AI-R1, AI-R2 and AI-R3 from
[audit 15](INDUCTION-AUDIT-15-2026-09-07.md) are resolved. The approved export must
have SHA-256 `c3fdb4fb0c3f89c68b06676f7613c75d3a293787d28c32b0a5adb9fa91e4fdf7`
and revision `8a1b16033eb4d6acd57c91c6a5d5e7f2af6d6f60f3adef92502b62d81ba28d04`.
Labels produced against the frozen run-AJ packet remain valid for that export,
subject to individual label validation and adjudication. Apply stays disabled;
the stage 3 execution prerequisites below remain outstanding.

Auditor: Codex / GPT-6 Astra, independent auditor and plan owner under
[orchestration v1](ORCHESTRATION-V1-2026-09-04.md). Scope: the Codex section of the
[run-AJ brief](PHASE2-STAGE3-LABELLING-BRIEF-2026-09-07.md). Reviewed HEAD:
`29f79113fb13157c28b9dd1caba167c8ccb6cb5d`, containing repair commit `20608ae`.
Comparison base: run AI's `f1ee10f7f0aef6d8b86ffd8f6d7194dcd932c27c`.
The independent content probe passed at `2026-09-08T02:56:42.581847+00:00`;
the filename retains the dispatch date. This ruling approves the bound taxonomy
and prompt repairs. Acceptance of the final execution SHA still requires its
own evidence, including independent review of Astra's earlier validator changes.

| Artifact | Exact-file SHA-256 |
|---|---|
| [Reviewed candidate](taxonomy-v3-2026-09-07.json), 15,390 bytes | `eaada74c3a5847024b422107d46e6214d0cf939a84ab048f3aea6b075c1004bd` |
| [Revision decision](proof/taxonomy-v3-revision-decision-2026-09-07.json), 28,164 bytes | `ee16c1426287f3c2271dbe37bb67c7eae9dc091f7fe9eb0bfd7855c5fd575589` |
| Approved export, 15,470 UTF-8/LF bytes; reproduced in scratch | `c3fdb4fb0c3f89c68b06676f7613c75d3a293787d28c32b0a5adb9fa91e4fdf7` |
| [Labelling packet](proof/holdout-v3-labelling-packet-2026-09-07.json), 343,011 bytes | `9bfb7901753377bd18b76ec3927240aa28871594a09784c422ae9416539b5063` |
| [Frozen hold-out v3](proof/holdout-v3-2026-09-07.json), 19,407 bytes | `855749efcaca5e985c04a9efef2decc4ee2dca3b24c8c3871f01079a9acd314c` |
| [Assignment prompt](../../scripts/librarian/prompts/assign.md), 7,162 checkout bytes | `d1a36d6896180ba886b90eb50606300cfd8282db74b279417afd3ee0cba938fd` |

Fable can reproduce the approved export with this exact command, from the
project root, after creating `_scratch/proof/run-aj` if absent:

```powershell
python -B scripts/librarian/compose_taxonomy_v3.py --approved-by "Codex / GPT-6 Astra (INDUCTION-AUDIT-16)" --approval-record docs/library/INDUCTION-AUDIT-16-2026-09-07.md --decision-out _scratch/proof/run-aj/taxonomy-v3-revision-decision-2026-09-07.json --taxonomy-out _scratch/proof/run-aj/taxonomy-v3-approved-2026-09-07.json
```

This command and the same command with `--check` both exited 0 here. The emitted
decision is byte-identical to the bound decision; the approved export matches
the independent calculation above. The composer refuses to overwrite a differing
existing file, so using only the approval flags against the canonical candidate
would refuse. Fable must preserve the reviewed candidate bytes as history, then
promote the verified export to `docs/library/taxonomy-v3-2026-09-07.json` during
integration. Preserve the decision and packet bytes. Only `status`,
`approval.approved_by` and `approval.approval_record` differ between candidate
and approved export. The approval record is a path in that wrapper; Fable must
also hash this report's final bytes in the separate execution record.

The repair checks passed as follows:

| Finding | Observed evidence | Ruling |
|---|---|---|
| AI-R1: full identities | `2086120621734326272`, `2091248592774369280` and `2094184640873373696` replace the three truncated strings. All 11 development IDs are exact v2 identities with matching archived card IDs, source revisions and card hashes; none is in v3. | Resolved |
| AI-R1: rule bindings | All 12 edits carry `rules`. The four mixed-rule lists equal audit 15 exactly; each other list contains its original rule. Every `development_cases` array is the sorted unique union of those rule groups. `evidence.rules.R2b` equals the required string. Every declared rule occurs in an edit, including R5. | Resolved |
| AI-R1: validation | The composer rejects each of the three truncated IDs, an archive with all R5-case attempts removed, and edits with R5 removed from their rule lists. These five negative probes changed in-memory inputs only. | Resolved |
| AI-R2: teaching precedence | Frontier's first exclusion and Education's final include equal the two audit 15 replacement strings character for character. Both survive projection and prompt rendering. | Resolved |
| AI-R3: subject before quote | Assignment rule 5, bullet 2 equals audit 15's replacement exactly. Replacing only that bullet in run AI's base reproduces the entire current prompt, including checkout CRLF conversion. Rule 4 and every other prompt byte are unchanged. | Resolved |

The complete candidate and decision were independently reconstructed from the
run-AI base using only those specified repairs. Both match their current JSON
objects exactly. Separate serialization reproduces both current files byte for
byte; the required composer `--check` also exits 0. Replaying all decision edits
onto approved v2 reconstructs the complete v3 node list: 12 field edits on six
shelves. Relative to the rejected v3 candidate, only the two AI-R2 cue strings
change operative node content.

All 11 IDs, paths, names, parent IDs and retired flags remain unchanged from v2.
The five complete preserved nodes are News and Current Events, Space and Science,
AI Agents and Automation, Generative Media and Spaceflight. There is no additional
edit, node addition, deletion, reparenting or retirement.

The boundary review below uses the projected definition/include/exclude fields
and assignment rules 1, 4 and 5. Cues describe the established subject of the
whole excerpt set; a passing mention does not establish that subject.

| Boundary | Direction one | Reverse direction | Ruling |
|---|---|---|---|
| R1: Education / Developer Tools | A tutorial, workshop, lecture or conceptual explanation with examples goes to Education when its purpose is teaching. Education's hands-on and conceptual includes explicitly take precedence over Developer Tools. | A coding-tool product, comparison or workflow described without a teaching purpose fits Developer Tools. Its definition preserves that subject; Education excludes announcements and release notes without teaching. | PASS |
| R1: Education / Frontier Models | Teaching a model, architecture or capability evaluation goes to Education, including a conceptual lesson with detailed evaluation. Both the Education include and Frontier exclusion now state that priority. | A model release, architecture discussion or capability evaluation without a teaching purpose retains Frontier's definition and includes. Education's directed exclusion returns non-teaching release coverage. | PASS |
| R2: AI and ML parent / children | Generic model task-fit, AI hardware throughput or passing company/product references stay at the parent when no child subject is established. Developer Tools, Frontier and Industry carry directed returns for those cases. | Rule 4 requires an established child subject to take the child. Coding tooling, model evaluation, teaching, agent action, finished generated artifacts, safety and industry analysis retain their respective child cues. | PASS |
| R2b: Industry / parent | Enterprise adoption, labour/task economics and accelerator competition with company implications establish Industry; its includes and rule 4 require the child. | A company or acquisition mentioned in passing during throughput/capability discussion, with no business analysis or other child subject, returns to AI and ML. | PASS |
| R3: Industry / Frontier Models | Dominant scaling, post-training or training-pipeline discussion goes to Frontier even with secondary economics; Frontier's precedence and Industry's exclusion agree. | Dominant adoption, labour/task economics or accelerator competition goes to Industry; Frontier's directed exclusion and Industry's includes agree. Rule 5 determines the subject before choosing a quote. | PASS |
| R4: Security / parent | Catastrophic-outcome, existential-risk and AI-safety warnings as the subject explicitly take Security over the parent. | Broad AI discussion with no safety/security or other child subject remains at the parent. Security's original exclusions remain operative. | PASS |
| R5: Developer Tools / Agents | Personal speech, screen or task assistance for a non-engineer goes to Agents. Developer Tools' exclusion agrees with Agents' sensing/acting and non-engineering task includes. | Coding-specific harnesses, IDE tools and SDKs for engineers go to Developer Tools under Agents' directed exclusion. Teaching still uses R1. | PASS |

Audit 15's synthetic counterexample now resolves to **Education**: "Today's
conceptual explanation teaches how a transformer architecture works. The examples
trace attention weights and explain the model's information flow. A detailed
benchmark evaluation then develops that explanation across twelve tasks."
The detailed evaluation no longer defeats teaching precedence. A non-teaching
architecture or benchmark report still fits Frontier Models. This is a semantic
review of the instructions, with no observed model prediction claimed.

For AI-R3's development case `2095783502306545664`, choosing an economic or
post-training quote cannot change the subject under the repaired rule: explicit
precedence comes first, then the dominant subject of all supplied excerpts, then
the supporting quote. This removes the selected-quote denominator rejected by
audit 15. Predictive accuracy remains a question for the sealed evaluation.

An independent eight-field projection equals the composer output, validator
normalization and the runner's pure normalization function. The pure runner and
validator renderers produce identical output; decoding the taxonomy JSON in
that output restores every node exactly. Escaped `\u003e` preserves directed
`->` cues. No database or service approval call was made in this audit.

| Projection or lineage identity | Value |
|---|---|
| Approved v1 revision | `2f283053bbaca2e94c2dbd340f19c62a89f529457ac40ae5b1d2d84379d22d98` |
| Approved v2 revision | `bd9e7f9d572a709a9e0f939b5433932fb36840278929946c2c6870ac0158dd97` |
| Approved v3 revision | `8a1b16033eb4d6acd57c91c6a5d5e7f2af6d6f60f3adef92502b62d81ba28d04` |
| Canonical projected service document plus LF, 12,203 bytes | `26d8801caf7092a3f4039d961621a2fec49c071e4a85255dbe5654202d272c2f` |
| Prompt read in universal-newline text mode | `ad6d5e59d357a5c8cd4668b3f6c8fc1ddca78ce9d956e7abe099f2c426a33255` |
| Text-mode prompt with normalized taxonomy rendered and `{{CARDS}}` retained, 19,644 UTF-8 bytes | `2287389295e947cbc4157cf82149deaf8107bc0c80753bacce2181bd66be5ffa` |

Canonical structured hashes use sorted-key UTF-8 JSON, `ensure_ascii=False`,
separators `(',', ':')`, and no trailing newline unless stated. These projection
identities are offline expectations. Fable must observe the service request and
response on the execution duplicate before starting the measured pass.

The packet binding passes in full. Its 60 unique cards occur in ascending
`video_id` order across strata, as required by the labelling packet; the hold-out
selection hash separately uses timed-then-text order. Each card's stratum, full
content, source revision and recomputed card hash match its frozen row and the
last card in both the original and stage 2 archives. The packet binds the original
archive hash `2b4e824ea9f93999de6c5108406e60a5c81f108de0b279c52fee2e96d622469c`;
the v3 selection seed binds stage 2's archive hash
`294941ba84eec02bf607aa7044ed45454634f99b8dcbf0b4adc9fe35349017b4`.
These serve different purposes, and the card equality check reconciles them.

The packet's 11 nodes equal the candidate's complete five operative fields,
with no sibling cues. Its version, parent and candidate-file hash agree. The
builder retains the legacy `kind: holdout-v2-labelling-packet` string, but its
explicit `holdout_version`, frozen-file hash and all 60 cards identify v3.
That schema tag does not change the evaluated set. Keep the packet unchanged.

Approval changes no operative node or revision. Therefore compliant labels
bound to packet SHA-256 `9bfb7901753377bd18b76ec3927240aa28871594a09784c422ae9416539b5063`
remain usable for approved SHA-256 `c3fdb4fb0c3f89c68b06676f7613c75d3a293787d28c32b0a5adb9fa91e4fdf7`.
Bind both identities and this equivalence ruling when sealing. The packet's
`proposal_sha256` continues to name the preserved candidate; it must not be
rewritten to claim that the labellers saw the approved wrapper. No v3 label file
was opened or certified in this audit.

A local identity and normalized eight-token scan found zero overlaps between
the taxonomy cues/prompt and the 11 development cards plus 60 v3 cards. V3 text
was processed for equality and leakage checks, without printing it or using it
to author repairs. The authored differences contain generic subject rules.
This check addresses direct copying; it cannot establish absence of every
paraphrase or unknown prior exposure.

The following are the stage 3 **Before execution** requirements for Fable,
carried forward from the [stage 3 gate](STAGE3-GATE-2026-09-07.md):

1. Preserve the candidate and publish the exact approved export above. Record
   the decision, approved-file, revision and final audit-record SHA-256 values,
   the final integrated Git SHA and any dirty entries. Obtain independent review
   of Astra's validator/freeze changes under orchestration rule 3. This report's
   final-file hash belongs in the execution record and collection receipt;
   embedding it in this file would make it self-referential.
2. Preserve Gemini's and Grok's original blind files. Validate them against this
   exact packet; Astra adjudicates in the later assigned step. Seal separate
   immutable gold and mapping artifacts for all 60 identities. Record both
   labeller-file hashes, packet hash, taxonomy/rules identities, adjudication
   artifact/hash, adjudicator, seal timestamp and commit. Freeze
   `strict-mapped-primary-v2`, including every unmappable mapping decision.
3. Reproduce both identity freezes and then bind
   `proof/manifest-stage3-2026-09-07.json`: all 548 ordered source identities,
   revisions, cards and bounded heads, zero exclusions, repaired prompt bytes
   and rendered template, and approved v1 -> v2 -> v3 lineage. Record the
   manifest hash, cards/heads/profile hashes and all implementation fingerprints.
   The source-copy fingerprint remains
   `2765cc359805fb12f7a90aecd3dd0b34d884aa8cb3015785011bf400da3b4dfc`, dated
   2026-09-04. No source copy was opened here. The current `.gitattributes` now
   protects `docs/library/proof/holdout-v3-*.json` with `-text`, resolving the
   gate's earlier EOL warning for the freeze and packet. Verify actual bytes
   again after integration.
4. Bind a separate execution record to the manifest and this approval. Observe
   the authorized source and disposable paths, source date/hash/size, disposable
   before-state hash/size/schema, active revision, memberships, pins, policies
   and projection revision. Record the actual v3 approval request/response bytes
   and service-returned revision. The offline projection above cannot substitute
   for that observation.
5. Observe the installed subscription client's version, executable path/hash,
   model `claude-sonnet-5`, exact argv with `--effort high`, tools disabled,
   session persistence disabled and `ANTHROPIC_API_KEY` unset. Bind the stage 3
   brief's subscription/corpus-egress authorization, batch 8, concurrency 4,
   at most one reasoning retry per item, 7,200,000 ms wall budget, deadline,
   error-rate guard 0.10 after at least 20 attempts, isolated non-5179 endpoint
   and cleanup owner. Confirm apply is disabled and preview refuses application.
6. In the execution dispatch, run the single measured pass, preserving
   failed/aborted calls, original exchanges, retries, cancellations and counters.
   Keep labels, mappings, prior predictions and hold-out membership out of
   assignment prompts and client egress. Require timed coverage at least 38/47
   and text-only coverage at least 11/13, with strict precision at least 0.90
   separately per stratum and valid evidence for every accepted membership.
   Reconcile real receipts and unchanged state on the actual execution SHA.
   No subset rerun or changed denominator can replace that result.

These checkout fingerprints are observed audit inputs; Fable must record the
execution checkout's bytes again, including runner, validator and scorer:

| Input | Checkout SHA-256 |
|---|---|
| [Approved v1 file](taxonomy-v1-2026-09-04.json) | `700f8dc09831fa14491a89f4ca68417ac721a17d45bcd2a9dc6c7ede484d11df` |
| [Approved v2 file](taxonomy-v2-2026-09-05.json) | `015260a496f45322609573956401139f15522d0497e45b263b7e5b8b269696e6` |
| [Composer](../../scripts/librarian/compose_taxonomy_v3.py) | `c79c8ef62b1f863dd37f2f7fa96ea5095757e53f302a6a270f28a2fbcab2055d` |
| [Projection code](../../scripts/librarian/taxonomy_from_proposal.py) | `67761c436d50a97d247d2de1e8fb245e90b069b8f4c6b935661606a9964d1031` |
| [Runner and renderer](../../scripts/librarian/proof_run.py) | `085e92cbcd5d517431dfae87018e0f553b9f3c10b5b0f8aced7f02500483fd17` |
| [Validator](../../tests/validate_proof_receipts.py) | `0b4192c99df419cf6c3dd92eb1ebbd94319b4d56fd0bb0d8826502a9660cbfbf` |
| [Scorer](../../scripts/librarian/proof_score.py) | `6331f16d9f534d476bf38def26b6a34781690480326aaf406b3a2939a03cfb40` |
| [Service](../../library_work.py) | `4dcc2122bf6292d46cf6a088fe887fa2d6018d371409e6661ffab1bbbc75ed09` |
| [Card builder and serializer](../../library_cards.py) | `a848cc02d451478548ac0a3d5968a14604919f3c0744a0ee88332dc615b1a10a` |

Validation completed with `PYTHONUTF8=1` and `PYTHONDONTWRITEBYTECODE=1`:

```powershell
python -B scripts/librarian/compose_taxonomy_v3.py --check
python -B tests/validate_proof_receipts.py --verify-stage3-freezes
python -B tests/validate_proof_receipts.py --verify-stage2-freezes
python -B _scratch/proof/run-aj/audit_v3.py
git diff --check
```

All final checks passed, along with the scratch export and its `--check` command
above. Both freezes reproduce: 47 timed and 13 text-only v3 identities, eligible
evidence for all 60, and zero overlap with the 225 induction identities, old 60
or v2's 60. The initial scratch probe used an incorrect exception class; changing
that local catch to the validator's actual `ValueError` made the five negative
probes pass. No project repair was needed. The probe, measurements and export
copies are ignored local evidence under `_scratch/proof/run-aj/`; the only
delivery file is this report. The full repository suite, execution-manifest
freeze, installed-client checks, label adjudication and measured pass were
outside this dispatch.

No model, helper, network client, database, port 5179 or live index was used.
No runner, prompt, scorer, composer, decision, canonical candidate, frozen packet
or label file was edited. No commit or merge was made. Fable owns collection,
approved-file promotion and the remaining stage 3 preparation.
