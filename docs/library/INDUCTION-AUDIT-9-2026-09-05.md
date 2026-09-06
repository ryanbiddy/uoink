**REJECT taxonomy-v2-2026-09-05 (attempt 9).** Named defects: B4-R, B5-X, B6-S and B6-M. AI Agents and Automation and Career and Entrepreneurship each retain only three subject-relevant cards in their selected five. One coverage row still omits its support-omission explanation. Definition/cue conflicts and the unrecorded disposition of Product Launches also remain. Apply and the measured pass stay disabled.

Codex / GPT-6 Astra, independent auditor and plan owner under [orchestration v1](ORCHESTRATION-V1-2026-09-04.md), responding to the [run Y brief](INDUCTION-REPAIR-BRIEF-2026-09-05.md). Audited checkout: `9418a4e11ffec0cfe4bd6c4f43c5bc7e49520296`. Attempt 9 execution SHA: `23f77ab07ab557c0cf5ce1d3f89c689f9919f797`; its reused batches originate at attempt 8 execution SHA `7802adce39f86b5d379df2f229985df6bf770611`. This report does not certify a later integration SHA.

The [parameterized replay script](proof/audit-induction-2026-09-05.py) writes [attempt-9 measurements](proof/audit-induction-9-measurements-2026-09-05.json). The run W measurements remain unchanged, SHA-256 `16b995b563c4dae5b623d43f665ca75eed1b65e17f3a492caf2afc450a248620`. No model, helper, database, live index, network client or port 5179 was used. Historical checkout paths were read as receipt strings only. No runner, prompt, scorer, archive or label file was edited; no commit or merge was made.

| Bound artifact | SHA-256 |
|---|---|
| Attempt-9 receipts | `22206eafd81b4703060e6a4f578f6cdd25dd8c6183351c0687cb9b9c03fa91d9` |
| Attempt-9 proposal | `37db6a1ee53e3ee286d32986f633bb7b12b9dfa4594a462504feb13b1a283997` |
| Attempt-8 source receipts | `fd781970f3bf5f4bafac3b54a418ceeccb28f1b5bb490698f31786e5d5d1d663` |
| Attempt-9 labelling packet | `c96c19001a5ee262df47da6b1cb2dec69000293e3c782c374ec45e447cbe5d35` |

The packet's proposal binding and all candidate node fields, including sibling cues, match the audited proposal. I did not open either worker's labels.

| Check | Observed | Expected | Verdict / reproduction |
|---|---|---|---|
| B1 — manifest | Rehashed stage-1 receipts: `2b4e824ea9f93999de6c5108406e60a5c81f108de0b279c52fee2e96d622469c`. Replayed 548 terminal IDs; exactly 225 unmapped, in manifest order, including 23 old-holdout members. Source revisions, card self-hashes and source-manifest binding agree. | Exact identities derived from raw archived attempts. | PASS. Measurements `B1`. |
| B2 — processes and artifacts | Ten records and ten files of each stream type; nine 25-card batches and one consolidation. All artifact, schema/argv, usage and proposal bindings agree. Maximum card: 8,153 bytes. All calls exit 0, ordered correctly, maximum concurrency 4; longest call 656.24768 seconds, below the recorded 1,800-second limit. | One authenticated record per represented process, complete inputs and bounded batches. | PASS. `B2`, `artifact_checks`. |
| B2-H — resume | Source receipt hash matches. All nine batch records equal attempt 8's receipt and persisted records; all 27 stream files match byte for byte. Attempt 8 has no resume. Attempt 9 has one new persisted consolidation record. Attempt 8's rejected consolidation and raw streams remain available. | Explicit origin binding and unchanged reused processes. | PASS for this lineage. `B2.resume`, `B2.attempt8_consolidation`. Earlier history limitations remain historical. |
| B3 — containment | All ten stdin files rebuild byte for byte. No holdout-v2 IDs, excerpt IDs/text, archived reasons, old split payload, result markers or gold-path literals found. The batch example is Home and Garden / Woodworking / Hand Tools. No forced counts or catch-all shelf. | Frozen cards, baseline vocabulary and current proposals only. | PASS. `B3`. |
| B4 — mechanical evidence | Five additions each have five distinct valid candidate-kind supports. All 25 node and 104 ledger references pass identity, source eligibility, excerpt ownership, occurrence and word-count checks. Node quotes: 8–21 words; all selected quotes: 4–24. | At least five distinct grounded cards per addition; valid references. | PASS on mechanics. `B4`, `B9.helper_comparison`. |
| B4-R — relevance | Four selected supports fail the cited-excerpt subject test, leaving Agents and Career at 3/5 each. | Five subject-relevant selected cards per new node. | FAIL. `B4.manual_relevance_review` and `manual_relevance_gaps`; every judgment is listed below. |
| B5 — ledger | Exactly 225 unique manifest IDs: 75 proposed, 29 existing, 96 still unmapped, 25 unsupported. All mapped evidence passes mechanical checks; refusals have reasons. | Complete ledger with valid vocabulary and evidence or reason. | PASS on structure. `B5`. This is not a semantic endorsement of every assignment. |
| B5-X — omissions | Of 50 proposed rows outside their node's support set, 49 explain the omission. c177 only says “NVIDIA infrastructure certification deal.” Its card is not among the Industry node's supports. | Every such row explains why it is not a support. | FAIL. `B5.omission_explanation_failures`: c177 / `2093098700612517888`. |
| B6 — shape/diff/cues | Twelve unique IDs/paths, four roots and eight level-2 nodes. All seven v1 nodes preserve path, definition, include and exclude exactly. Every include cue has a matching alternative/evidence pair, including Developer Tools, Education, Security and Frontier Models. Diff accounts for seven preserved and five added IDs. | Valid hierarchy, stable IDs and complete diff/cue pairs. | PASS on structure. `B6`. |
| B6-S — operative rules | The three new AI siblings now carry mutual exclusions. Images still appear in Generative Media's cues outside its definition; Agents' installation and single-office-task cues exceed its autonomous multi-step definition. Frontier Models has no reciprocal creative-output precedence. | Definitions and cues agree; overlapping nodes carry usable, consistent precedence. | FAIL. `B6.operative_rule_review` and proposal node fields. |
| B6-P — pins | Recomputed stage-1 before-state: zero pins, memberships and item policies; v1 active. Receipt and proposal explicitly identify that measured population and agree. | Explicit measured counts and no silent redirects. | PASS. `B6.pin_state_replay`, `pin_measurements_match`. This does not measure the live library. |
| B6-M — candidate disposition | Four rejected candidates are retained. Product Launches is neither retained as a node nor recorded as rejected; its six support cards are distributed between two functionally different nodes. | Preserve every non-adopted candidate; exception applies to equivalent-candidate merges. | FAIL. `B6.batch_candidates`, batch 02 Product Launches; ruling below. |
| B7 — accounting | Ten distinct CLI sessions. Four top-level counters, all Haiku/Sonnet modelUsage objects and the USD 8.2994778 estimate reconcile once per represented call. Only USD 1.2916582 is the new consolidation estimate. | Deduplicated raw accounting, estimates separate from paid costs. | PASS. `B7`. Paid cost unavailable. |
| B8 — isolation | Receipts contain cwd, checkout, input/output paths, model/effort/concurrency/timeout, per-call environment policy and explicit no-database/no-helper declarations. Archived runner explicitly supplies the child environment and cwd, removes the API key, and persists stdin before launch. Both executions' fingerprints match their Git objects after documented newline normalization. | Archive-only evidence profile permitted by run W, with explicit launch environment and bound files. | PASS under that profile. `B8`. No claim of independent OS network telemetry or historical database snapshots. |
| B9 — validator | Unmodified validator exits 0 for attempts 9 and 6 with `INDUCTION_RECEIPTS_VALID_AUDIT_REQUIRED`, 225 targets, ten calls, `proposal_approved=false`. Independent keys, expansion, counts, normalizer, accounting and projection agree with contract helpers. | Portable exact-byte replay and mechanical agreement. | PASS. `B9`. Attempt 8 still fails on disposition-kind node support, as expected. |

I read all 25 selected quotes and all 59 frozen excerpts on their cards. A support's judgment uses its cited excerpt; another excerpt does not silently replace the selected evidence. These are auditor judgments bound to the proposal hash, separate from lexical validity. Statements about products, events, revenue and awards below describe what the source says, not independently verified real-world facts.

| Node | Key | Cited-excerpt finding | Subject relevance |
|---|---|---|---|
| News | c006-1 | Explicit left/center political debate. | PASS |
| News | c009-1 | Murder charge and overnight shooting at a named location. | PASS |
| News | c010-1 | Home intrusion, death, police response and charges. | PASS |
| News | c011-1 | Police radio declares a riot and reports a capitol breach. | PASS |
| News | c019-1 | Original post describes a missile strike at a named air base. | PASS |
| Generative Media | c033-1 | Says the animation was made with Seedance and supplies its generation prompt. | PASS |
| Generative Media | c038-1 | Describes a created film receiving an AI-film award. | PASS |
| Generative Media | c104-1 | Explicitly describes an AI cat-vlog video. | PASS |
| Generative Media | c140-1 | Describes using Gemini to generate a specific video. | PASS |
| Generative Media | c128-1 | Explicit AI animated film, made with genAI and human art. | PASS |
| Agents | c088-1 | Internet-using model orders food, books flights, shops and researches. | PASS |
| Agents | c106-1 | AI agents sell cars, underwrite loans and run an operation. | PASS |
| Agents | c089-1 | Claude reads ads and extracts winning patterns through an MCP integration. | PASS |
| Agents | c110-1 | Requests NDAs and employee information; identifies no AI actor or autonomous completion. The only excerpt is unchanged from run W. | FAIL |
| Agents | c070-1 | Describes installing an offline AI agent, with no task or multi-step execution. The broader include cue cannot supply that missing behavior. | FAIL |
| Industry | c213-1 | Reports OpenAI ARR, qualified as an estimate in the excerpt. | PASS |
| Industry | c223-1 | Explicit OpenAI/Anthropic revenue comparison. | PASS |
| Industry | c178-1 | Acquisition discussion explicitly concerns open-source AI. | PASS |
| Industry | c082-1 | AI-company competition discussed through infrastructure. | PASS |
| Industry | c130-1 | Government restrictions and access to a lab's models. | PASS |
| Career | c201-1 | Advises job seekers against mass applications. | PASS |
| Career | c202-1 | App backlog and feature shipping; cited excerpt establishes neither an independent business nor a creative career. The separate buy-button excerpt was not selected. | FAIL |
| Career | c203-1 | Describes a programmer's self-taught, non-traditional path. | PASS |
| Career | c209-1 | Concrete release-timing advice for a musician. | PASS |
| Career | c221-1 | Interview announcement plus “How to start a startup” chapter heading; no founding advice or firsthand account. Its distinguishing cue expressly requires generalizable advice. | FAIL |

The four failing cards are `2087221157787525120`, `2083169868891684864`, `D4fkiQfzw_I` and `x_811cef5397c`, respectively. Their complete cited excerpts and all other frozen excerpts are preserved in the measurements. The resulting support counts are News 5/5, Generative Media 5/5, Agents 3/5, Industry 5/5 and Career 3/5. The Agents failures independently block approval even if the two Career judgments are disputed.

Among all 198 derived keys (87 candidate, 111 disposition), only c061-1 fails mechanical evidence validation: its 11-word quote does not occur in its excerpt. The consolidation prompt explicitly bans it, and the proposal never selects it. Attempt 9 has no skipped identities. The invalid-key repairs therefore pass without implying that the selected quotes establish the right subjects.

B6-S has concrete consequences. A still-image-only generation card matches Generative Media's include list, while its definition lists only video, animation and film. An offline-agent installation matches Agents' last include cue without showing any autonomous task. A foundation-model release demonstrating a creative output can match both Frontier Models and Generative Media: the latter excludes evaluations *without* a creative output, while the former still includes multimodal model releases without a converse rule. Freezing v1 fields and requiring new reciprocal exclusions in those same fields are incompatible instructions for that case; the plan needs an explicit resolution. Archiving sibling cues does not resolve it because those cues are removed from the service projection.

The Product Launches omission is **not covered by the equivalent-candidate merge exception**. The batch candidate groups announcements of consumer, creator and agent applications; the two final destinations classify different functions. c056, c058, c060 and c070 go to Agents; c064 and c069 go to Generative Media. This is redistribution of a broader concept, not consolidation of equivalent candidates. c060 illustrates the problem: its excerpt describes a Mac app for capturing material and prompts while working with AI, not autonomous task execution. Record why Product Launches was not adopted as a standalone node and review the redistributed cards against the destination definitions. Keep the v1 `diff.merged`/`split` arrays empty: this finding concerns a batch candidate, not an existing shelf.

Each run W finding has the following disposition:

| Finding | Disposition | Evidence |
|---|---|---|
| B2-H | Resolved for attempt 9; old missing artifacts not applicable to this clean batch lineage. | Hash-bound attempt-8 resume, nine identical persisted records and 27 identical stream files. Attempts 1–6 remain historical, with their previously recorded limitations. |
| B3 | Resolved. | Neutral example and byte-rebuilt inputs; zero forbidden-content hits. |
| B4-R | Still open. | c110 persists; c070 and two Career supports introduce further gaps. The other five previously rejected support keys are not selected as node supports. |
| B5-X | Still open, narrowed to one row. | 49 repaired omission explanations; c177 missing. |
| B6-S | Still open, partly repaired. | Mutual rules among the new AI siblings now survive projection; definition/cue conflicts and the Frontier boundary remain. |
| B6-P | Resolved. | Explicit counts independently agree with the archived before-state. |
| B8 | Resolved for this archive-only run. | Explicit launch provenance, environment policy and file-only execution declaration, plus fingerprint review. This does not retroactively establish attempt 6's environment. |
| B9 | Resolved. | Both delivered archives validate without byte reconstruction or validator modification. |

As validator owner, I **accept Fable's contract v1.3 implementation** in commits `7802adc` and `23f77ab`, including the four changed fixture expectations. `tests/validate_proof_receipts.py` remains unchanged in this worktree, exact SHA-256 `4d753c47b11ee7b86de067eb825c35874ad96b812efc4f24c38e0b63cf23c14f`.

| Owner review | Observed | Ruling |
|---|---|---|
| `derive_induction_keys` | Unkeyable identities receive no key; omissions retain call, kind and row/support positions in output order. Independent replay of actual attempt-7b stdout reproduces exactly seven skipped disposition supports in batch 03. Empty `skipped` stays absent, preserving v1.2 input bytes. Selected keys still undergo origin, ownership and full source checks. | ACCEPT. No recovery of missing evidence is implied. |
| Four negative expectations | Wrong support owner, disposition owner, batch ledger and batch node mutations change the derived input; each fails consolidation-byte binding. The old comment claiming derivation itself failed was stale. | ACCEPT expectations; amended comment. |
| `with_optional` | Deep-copies the base schema, retains required fields and closed outer objects. Optional fields admit historical provenance without requiring it on old archives. `database_opened` and `helper_opened`, when present, must be false. | ACCEPT. Open JSON subobjects and free-text declarations are audit inputs, not validated proof of B8 semantics. |
| Added regression cases | Exercise successful skipping with unchanged valid keys; stale-input rejection; unknown-key rejection after a legitimate re-render; non-string and non-object supports; old-schema compatibility; required-field, type and additional-property rejection. | PASS. 79 induction tests; validator offline self-test reports 167 cases. |

The repaired attempt-6 files now match their original receipt bindings exactly:

| File | Bytes | SHA-256 |
|---|---:|---|
| `taxonomy.json` | 5,591 | `700f8dc09831fa14491a89f4ca68417ac721a17d45bcd2a9dc6c7ede484d11df` |
| `fingerprints/validator` | 109,896 | `9c84480b1e0987c632fc9e574f0544c0d3c65cf6bf17a3184c9f3c35484dfe76` |
| `fingerprints/card_builder` | 9,931 | `a848cc02d451478548ac0a3d5968a14604919f3c0744a0ee88332dc615b1a10a` |

Attempt 9's represented-call totals are 1,181,542 stdin bytes, 497,149 stdout bytes, zero stderr bytes and 20,930 schema bytes: 1,202,472 input-plus-schema bytes. CLI counters are 22 input, 514,682 output, 835,384 cache-read and 636,879 cache-creation tokens. Per-model estimates are USD 0.438021 for Haiku and USD 7.8614568 for Sonnet. They are not added to the top-level estimate again. Reused batches account for USD 7.0078196; the new consolidation accounts for USD 1.2916582. Including attempt 8's separate rejected consolidation gives eleven unique processes and USD 9.8700438 in CLI estimates. That is neither total induction-history cost nor an invoice.

Attempts 7a and 7b retain stream files and logs but have no receipts or persisted per-process record files in their archived directories. The record-persistence change followed 7b. Those failures remain preserved with incomplete process provenance; neither supplies the batches reused by attempt 9. Their costs are outside the eleven-process total above.

The storage projection is mechanically valid but **not approved**. Keep `shelf_id`, `path`, `definition`, `include`, `exclude`; derive `name` from the last path segment, `parent_shelf_id` from the parent path, and `retired=false`. Sort nodes by `(path depth, path, shelf_id)`. The service revision is SHA-256 of the compact, sorted-key UTF-8 node array. Wrap it in the schema/version/parent/nodes/revision document and append one LF for the projected file. This produces 8,952 bytes, projected-file SHA-256 `3554194d53f2319f0f6bf4dc531ef5ccd30c80f378e060f693b3c63a6de25abe`, and expected service revision `89649d2373d5377fbbffe3778a9931bdbfeab166b1601676b6e31ca447c837e1`. The validator independently reproduces the normalized document. No service was invoked; this is a calculated revision, not a service-returned approval.

No approval record should be written for this proposal. A replacement must resolve the named defects and receive a separate audit bound to its own bytes; the full approval-record requirements in [run W](INDUCTION-AUDIT-2026-09-05.md) remain in force. Preserve attempt 9 and its blind labels as history. Any changed definitions or operative rules require a matching candidate packet and fresh independent adjudication before a measured pass.

Validation performed from this worktree:

```powershell
python -B docs/library/proof/audit-induction-2026-09-05.py --archive docs/library/proof/induction-run-9-2026-09-05 --self-test
python -B tests/validate_proof_receipts.py --receipt-kind induction --receipts docs/library/proof/induction-run-9-2026-09-05/receipts.json --require-real
python -B tests/validate_proof_receipts.py --receipt-kind induction --receipts docs/library/proof/induction-run-2026-09-05/receipts.json --require-real
python -B -m pytest tests/library_work_astra/test_induction_contract.py -q -p no:cacheprovider --basetemp _scratch/audit9-pytest
python -B tests/validate_proof_receipts.py --self-test --mock
git diff --check
```

Replay completes with eight audit self-checks. Both archive validators exit 0; 79 induction tests pass; the shared validator self-test reports 167 cases, zero model calls and zero helper calls. Fable must review the added audit/test code and rerun affected checks on the collected integration SHA. The approval decision remains REJECT even though these mechanical checks pass.
