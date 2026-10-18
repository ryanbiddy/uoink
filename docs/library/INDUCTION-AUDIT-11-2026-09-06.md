**REJECT taxonomy-v2-2026-09-05 (revision decision 2).** Two findings block approval and the measured pass: **B6-S-Agents-Security**, an operative distinction lost during projection, and **B5-R2**, eight sampled ledger destinations unsupported by their cited excerpts. Apply stays disabled. No further model induction is needed; exact reviewer-authored repairs are specified below.

The three destination repairs requested in audit 10 pass, and all 20 selected node supports now pass subject relevance. The composition also passes: all 18 recorded edits have correct before-values, reproduce their after-values, and account for every change to the proposal. The remaining failures concern the revised document as a whole, including ledger rows inherited unchanged from attempt 10.

Codex / GPT-6 Astra, independent auditor and plan owner under [orchestration v1](ORCHESTRATION-V1-2026-09-04.md), responding to the [run AB brief](INDUCTION-REVISION-2-BRIEF-2026-09-06.md). Audited checkout: `000367e0cba8901cd5d3efd6d5cd689bd3fdfdc1`. This report does not certify a later integration SHA. B1-B3 and B7-B9 stand from [audit 10](INDUCTION-AUDIT-10-2026-09-05.md), as the brief directs; they were not rerun here.

The [decision replay script](proof/audit-decision-2-2026-09-06.py) writes [decision-2 measurements](proof/audit-decision-2-measurements-2026-09-06.json). It reuses the prior independent audit's key, ownership, normalization and occurrence checks, then compares its results separately with the public proposal validator and composer. Human relevance judgments are identified as such and bound to the decision hash. Exit 0 means the replay completed, not that the proposal passed.

| Bound artifact | SHA-256 |
|---|---|
| Revision decision 2 | `27e010cea18a4a4b6c9ac20b0061dd264754fea94e088e1e8fdc8e71452b19bd` |
| Decision 1, matching `successor_of` | `7028edf7471a3624345257e59c6eb7627c011a65424df439a126d906df77098f` |
| Attempt-10 proposal | `bb3d51e4b6eecf542355ba0e5f5fbb0d09b1e0ad692eb1c5d1674f315a25cd7c` |
| Attempt-10 receipts | `fb26d4f0a6814fc32c00cb51ea7dbc076150b775c545d90cbdc43cd1e16ee0c2` |
| Attempt-9 donor proposal | `37db6a1ee53e3ee286d32986f633bb7b12b9dfa4594a462504feb13b1a283997` |
| Attempt-9 donor receipts | `22206eafd81b4703060e6a4f578f6cdd25dd8c6183351c0687cb9b9c03fa91d9` |
| Candidate labelling packet 11 | `35af2d0f7e5d4bffccb1f6146759d08c92aef5d20270a204c8419e66b613f464` |
| Inherited attempt-10 measurements | `21639c57b4e5dcd3f8127da425be1689dd9d31b25b844abf3567188d040bb616` |

The proposal was reconstructed independently by applying the recorded edits to decision 1, without calling the composer for that reconstruction. Full proposal equality proves that no other proposal field changed. A separate comparison against `compose()` matches the complete UTF-8/LF file bytes, including the new provenance wrapper. The source hashes and unchanged `sources` object match decision 1. The wrapper's successor, author and repair metadata are separate from the 18 proposal edits.

| Edit | Repair item | Target | Judgment |
|---|---|---|---|
| 1 | 1 | Agents definition | Separately admits task agents, sensing/acting companions and proposed persistent monitors. Resolves the prior scope defect. |
| 2 | 1 | Agents include | Aligns companion and monitor cues; adds non-engineering priority over Developer Tools. |
| 3 | 1 | Agents sibling cues | Removes unsupported monitoring/action requirement and mirrors include strings. Introduces Security as a confusing alternative without carrying that distinction into operative fields: B6-S-Agents-Security. |
| 4 | 1 | Agents exclude | Replaces narrow task-demo language with agent/assistant and product behavior. Consistent with the broader scope. |
| 5 | 1 | c058 reason | Describes sensing, hearing, acting, remembering and understanding; no invented multi-step task. |
| 6 | 1 | c124 reason | Describes proposed screen/meeting observation; no invented execution. |
| 7 | 2 | Media include | Adds explicit priority over Frontier for an artifact-centered foundation-model release. |
| 8 | 2 | Media sibling cues | Mirrors the added include and records the artifact-versus-model distinction. |
| 9 | 2 | Media exclude | Sends architecture/scaling/benchmark release coverage without a finished artifact to Frontier. |
| 10 | 2 | Industry include | Gives external government policy priority over technical Security. |
| 11 | 2 | Industry sibling cues | Mirrors the changed policy include string. |
| 12 | 2 | Industry exclude | Sends technical safety and defenses to Security. |
| 13 | 2 | News include | Gives incident-centered reporting priority over every AI shelf. |
| 14 | 2 | News sibling cues | Mirrors the changed incident include string. |
| 15 | 3 | c007 row | Exactly restores attempt 10's `still_unmapped` row. |
| 16 | 3 | c064 row | Moves feature announcement to `ai-and-ml`, retaining its own disposition key. |
| 17 | 3 | c069 row | Moves video-model release announcement to `ai-and-ml`, retaining its own disposition key. |
| 18 | 3 | Product Launches rejection reason | Accounts for exactly its six candidate cards and their actual destinations; removes c088. |

Every edit addresses its named repair item. That does not make the full repair complete: edit 3 adds a boundary that still needs an operative rule. The replay records a digest of every before/after value in `composition.per_edit`.

| Check | Observed | Expected | Verdict / measurement |
|---|---|---|---|
| B4 evidence mechanics | 20 node references and 95 ledger references; all identities, ownership, eligibility, normalized occurrence and word caps pass. Selected node quotes span 7-19 words. No auditor-rejected or mechanically banned key is accepted. | Valid evidence from bound cards; candidate-kind node supports. | PASS, `B4`; full proposal validator also passes. |
| B4-R subject relevance | Five distinct subject-relevant supports for each of Agents, Industry, Media and News. | Five per added concept under its operative scope. | PASS, `B4.manual_relevance_review`. |
| B5 ledger structure | 225 unique manifest cards: 62 proposed, 33 existing, 106 unmapped, 24 unsupported. Every mapped row has its own disposition evidence. | Complete ledger, correct identities and disposition structure. | PASS, `B5`. |
| B5 omissions | All 42 proposed rows outside their node's support set have an explicit omission suffix. | Every omitted support explained. | PASS on structure. The five-card cap explains selection, not destination relevance. |
| B5 original repairs | c007 unmapped; c064/c069 at AI parent; c058/c124 reasons agree with the broader scope. | Resolve audit 10's named destinations. | PASS, `B5.repaired_destinations_pass`. |
| B5-R2 destination sample | 29 rows reviewed: 27 mapped plus two unmapped controls. Nineteen mapped destinations pass; eight fail. | Each assigned subject established by the cited excerpt. | FAIL, `B5.sample_records`; exact replacements included. |
| B6 hierarchy/diff | Eleven unique nodes: three roots, eight children. Seven preserved, four added; other diff operations empty. | Complete hierarchy and stable v1 identities. | PASS, `B6`. |
| B6 frozen v1 | All eight service fields of every reconstructed v1 node equal the v1 document; canonical UTF-8 node bytes also match. | Preserve all seven v1 service nodes. | PASS, `B6.frozen_v1_checks`. This does not assert identical formatting of differently shaped source JSON objects. |
| B6 cues and scope | Every include string has an identical sibling entry with a nonempty alternative and distinction; include kinds fit definitions. | Cue identity and definition agreement. | PASS. |
| B6-S operative precedence | Agents' personal-monitoring/security-control distinction exists only in a field projection drops. | Both directions against every named confusing v1 alternative survive projection. | FAIL, `B6.boundary_failure`. |
| B6 candidates | All 21 batch candidates accounted for: 15 adopted/equivalently merged, six explicitly rejected. | No unexplained non-adopted candidate. | PASS, `B6.candidate_dispositions`. |
| B6 pins | Archived before-state: zero pins, memberships and item policies; v1 active. Receipt and proposal agree; redirects prohibited. | Explicit measured population and pin impact. | PASS for the archive, with no claim about the live library. |

I read all 20 selected quotes in their complete frozen cited excerpts. These judgments concern what the excerpts establish, not verification of their claims about products, revenue, awards or events. A truncated excerpt was read to its recorded end; missing continuation was not inferred.

| Node | Support | Cited-excerpt finding | Verdict |
|---|---|---|---|
| Agents | c058-1 | Companion builder sees, hears, acts, remembers and understands. The revised companion branch admits it. | PASS |
| Agents | c088-1 | Internet-using model orders food, books flights, shops and researches. | PASS |
| Agents | c106-1 | Agents sell cars, underwrite loans, coach mechanics and run an operation. | PASS |
| Agents | c141-1 | Agents autonomously plan, execute and deliver on a goal; no particular finished artifact appears. | PASS |
| Agents | c124-1 | Speaker proposes a ChatGPT descendant watching screens and meetings. The revised monitor branch admits this proposal. | PASS |
| Industry | c082-1 | AI-company competitive ranking argued through infrastructure. | PASS |
| Industry | c130-1 | Government restrictions affect access to an AI company's models. | PASS |
| Industry | c144-1 | Competition against OpenAI and Anthropic is the subject. | PASS |
| Industry | c169-1 | AI token usage compared with revenue capture. | PASS |
| Industry | c213-1 | AI-company ARR, expressly qualified as a rough estimate. | PASS |
| Media | c033-1 | Made-with attribution followed by an animation prompt. | PASS |
| Media | c038-1 | Created film described as winning an AI-film award. | PASS |
| Media | c128-1 | AI animated film blending genAI and human art. | PASS |
| Media | c091-1 | Finished visual website made with AI image/video models. | PASS |
| Media | c104-1 | Firsthand description of AI cat-vlog video content. | PASS |
| News | c006-1 | Explicit left/center political debate. | PASS |
| News | c009-1 | Murder charge and shooting at a named location. | PASS |
| News | c010-1 | Home intrusion, death, police response and charges. | PASS |
| News | c011-1 | Radio declares a riot and reports a capitol breach. | PASS |
| News | c019-1 | Original post reports missiles striking a named air base. | PASS |

The accepted frozen-shelf amendment remains in force: both directions may live in the new node, preserving v1. The operative-field review covers these alternatives, including alternatives named in exclusions as well as sibling cues. Array indices below are zero-based.

| Pair | Operative rule reviewed | Verdict |
|---|---|---|
| Agents / Developer Tools | `include[1]` gives non-engineering task completion priority; `exclude[0]` sends coding harnesses, IDEs and SDKs to Developer Tools. | PASS |
| Agents / Frontier | Definition admits acting products and the separate assistant kinds; `exclude[1]` sends architecture/benchmark coverage without agent/assistant behavior to Frontier. | PASS |
| Agents / Security | `sibling_cues[4]` says personal assistance rather than security control; definition/include/exclude contain no Security distinction. | FAIL |
| Industry / Frontier | Industry's business/usage scope and `exclude[0]` separate technical evaluation; Frontier already excludes general AI business news. | PASS |
| Industry / Developer Tools | Business dynamics versus coding-tool usage/IDE/SDK steps in `exclude[3]`; Developer Tools excludes nontechnical end-user products. | PASS |
| Industry / Security | `include[1]` gives external policy priority; `exclude[4]` sends technical safety to Security. | PASS |
| Media / Frontier | `include[5]` gives an artifact-centered model release priority; `exclude[0]` routes the specified technical release without a finished artifact to Frontier. | PASS for these named cases |
| Media / Developer Tools | Definition and visual-website include establish the output subject; `exclude[3]` sends the coding/SDK workflow to Developer Tools. | PASS |
| News / AI parent and children | `include[0]` prioritizes the incident over every AI shelf; exclusions return product, model and company-business subjects to AI shelves. | PASS |

B6-S-Agents-Security has a reproducible synthetic case: **a proposed AI security assistant continuously watches the user's screen to detect prompt injection and enforce runtime guardrails**. This is an auditor-created boundary case, not a source quote. Agents' `include[4]` admits the persistent screen assistant. Security admits prompt-injection defenses and runtime governance. The only text distinguishing personal assistance from a security control is `sibling_cues[4].evidence_needed`, which the approved projection discards. The case therefore loses the required choice after projection.

Resolve it with three recorded field edits in a successor decision:

1. Replace Agents `include[4]` with `proposed persistent assistant that continuously watches the user's screen or meetings for personal assistance, rather than technical safety or security control (takes precedence over AI and ML / Security for this personal-assistance case)`.
2. Copy that exact string into `sibling_cues[4].include_cue`.
3. Append Agents exclusion `technical AI safety or security controls, including monitoring to detect prompt injection or enforce runtime guardrails -> AI and ML / Security`.

The ledger sample was selected by rule: the repaired/redistributed/control rows c007, c058, c124, c064, c069, c056, c060, c070 and c177, plus the first, middle and last ledger row for every populated shelf, deduplicated. The resulting 29 keys and all cited excerpts are in the measurements. This is a destination sample, not a semantic certification of all 225 rows.

| B5-R2 row / key | Why the current destination fails | Exact destination repair using the current evidence key |
|---|---|---|
| c087 / c087-1 | Potato-counting AI vision system; no SDK, source code, IDE or engineering-tool workflow. Reason adds Ultralytics SDK absent from the excerpt. | `existing_concept`, `shelf_ids: ["ai-and-ml"]`; keep c087-1. |
| c095 / c095-2 | Generic claim that models can do computer work; no agent/assistant product, autonomous multi-step task, companion or persistent monitor. | `existing_concept`, `["ai-and-ml"]`; keep c095-2. |
| c123 / c123-1 | Model download count establishes adoption. It does not state open weights, architecture, a benchmark or a release. | `proposed_concept`, `["ai-industry-and-business"]`; keep c123-1 and add the omission suffix. |
| c143 / c143-2 | LLMs described as a critical resource in enterprise contexts; no competitive, financial or policy dynamic, and no control dispute. | `existing_concept`, `["ai-and-ml"]`; keep c143-2. |
| c158 / c158-2 | Model-generated robot design described in prose; no finished visual artifact or its medium is established. | `existing_concept`, `["ai-and-ml"]`; keep c158-2. |
| c177 / c177-2 | Hypervisor certification and vertical integration establish a technology/business announcement. NVIDIA's name cannot supply the missing AI subject. | `still_unmapped`, empty shelves and evidence. |
| c182 / c182-1 | Database-load simulation tool without an AI component; the AI parent's exclusion of traditional non-AI software applies. | `still_unmapped`, empty shelves and evidence. |
| c215 / c215-1 | Metaphorical guardrails around an unnamed experiment; no technical AI safety subject is established. Anthropic's name alone cannot establish it. | `still_unmapped`, empty shelves and evidence. |

For each of these eight rows, `B5.sample_records[].exact_proposed_replacement` contains the complete replacement, including the exact reason text. Use those objects as the edits' after-values. An alternative destination requires an eligible recorded disposition key whose own excerpt establishes it; no new evidence or unsupported continuation is authorized by this report. The proposed replacements and three Agents field edits pass the complete proposal validator together in memory. Their expected ledger counts are 59 proposed, 33 existing, 109 unmapped and 24 unsupported. No successor file was written or approved.

c007's restored reason is retained as rejected-candidate history, not as a claim that its testosterone excerpt establishes politics. c064 describes an avatar-generation feature; c069 describes an AI video-model release and forthcoming API access. Neither cited excerpt establishes a finished visual artifact or a narrower v1 child. Their AI-parent placements pass. c056's generic ChatGPT assistance and c060's AI prompt-capture app also fit the parent. Product Launches now records exactly c058 to Agents; c056/c060/c064/c069 to the parent; c070 unmapped.

The six rejected candidates remain accounted for. The political-commentary child has two candidate cards, the crime/conflict child four, Sports four, and Creator Culture two, all below five before any semantic subtraction. Career has six candidate cards with two expressly rejected excerpts, leaving at most four. Product Launches is rejected as a standalone concept with the six-card redistribution above. The 15 adopted/equivalent candidates comprise one News parent, two Agents candidates, seven Industry candidates and five Media candidates. c177's omission suffix now exists; its destination fails separately.

Projection works mechanically. `taxonomy_from_proposal.py` unwraps `proposal`, binds the hash of the whole decision file, and produces nodes equal to both the independent projection and validator normalization. The seven preserved IDs are `ai-and-ml`, `space-and-science`, `developer-tools`, `security`, `frontier-models`, `education`, and `spaceflight`. Parent revision: `2f283053bbaca2e94c2dbd340f19c62a89f529457ac40ae5b1d2d84379d22d98`.

For these **rejected bytes**, the compact sorted-key service document plus one LF is 9,249 bytes, SHA-256 `86245d8e878440172c303eeb75c1df875f64ab83bf722c31288138d8aa892ca9`. The calculated service revision is `e8263edcd7354412f2de4b9946aa3ee11126d25e2774d085c971f46479ddd2a5`. The metadata export produced in memory with `approved_by="Codex / GPT-6 Astra"` and `approval_record="docs/library/INDUCTION-AUDIT-11-2026-09-06.md"` would be 12,662 bytes, SHA-256 `72647d7149e7728910f73bdfb2467e2d5eae556811cecd7d26d3967ba37893c4`. That diagnostic invocation does not grant approval. No projected file was written or installed; no service-returned revision was observed.

**Fable must not write an approval record for decision 2.** The [run-W approval-record requirements](INDUCTION-AUDIT-2026-09-05.md) remain in force for an accepted successor: bind exact decision/source receipt hashes, the resolving audit and findings, projection fields and file hash, service-returned revision, preserved IDs and parent revision, rejected concepts and measured pin impact, approver/timestamp, and authorized disposable database identity. A calculated hash cannot fill the service-returned field.

Packet 11's hash, decision binding and every candidate node field match. Its labels belong to this rejected candidate. The Agents operative repair changes the taxonomy rules, so obtain fresh blind labels/adjudication against the successor packet and seal labels/mapping before the measured pass. No worker label file was opened in this audit. The packet was opened for binding verification; hold-out predictions were neither produced nor used to tune these findings.

Validation performed:

```powershell
python -B scripts/librarian/compose_revision_decision_2.py --check
python -B docs/library/proof/audit-decision-2-2026-09-06.py --decision docs/library/proof/taxonomy-v2-revision-decision-2-2026-09-05.json --output docs/library/proof/audit-decision-2-measurements-2026-09-06.json --self-test
git diff --check
```

Both Python commands exit 0. The replay passes nine mutation/normalization checks: unrecorded change, wrong before-value, missing edit, wrong repair item, overlong quote, invented quote, foreign revision, Unicode normalization, and foreign-card ledger evidence. The public complete proposal validator passes both the audited composition and the proposed repair preflight. These checks establish mechanical validity; the human findings still require rejection.

Only this report, the new audit script and its measurements were added. Earlier measurements retain their hashes, and no runner, prompt, scorer, decision or proposal was edited. No model, helper, database, network client, live index or port 5179 was used. No commit or merge was made. Fable must inspect the new review code and rerun the affected replay on the collected integration SHA; Astra's tests alone do not independently certify Astra-authored tooling.
