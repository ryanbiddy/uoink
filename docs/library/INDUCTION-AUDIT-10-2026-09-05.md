**REJECT taxonomy-v2-2026-09-05 (revision decision).** Named defects: B4-R, B6-S and B5-R. Agents retains three subject-relevant supports under its stated definition. Its definition and cues still disagree, and the required precedence over frozen Frontier Models is missing from Generative Media. The imported News ledger row c007 and two redistributed Product Launches rows also claim subjects their cited excerpts do not establish under the destination definitions. Apply and the measured pass stay disabled.

**A reviewer-authored repair is acceptable.** The composition method passes: it preserves the two source proposals, records its edits, and reproduces deterministically. No eleventh model run is needed. The current composition repairs attempt 10's missing News parent, but a donor node's five passing supports do not certify all of its ledger rows. A bounded repair is specified below.

Codex / GPT-6 Astra, independent auditor and plan owner under [orchestration v1](ORCHESTRATION-V1-2026-09-04.md), responding to the [run AA brief](INDUCTION-REVISION-BRIEF-2026-09-05.md). Audited checkout: `603bb7d888eba540b8041f97abf8dad70e9c34ab`. Attempt 10 executed at `5c7c72fbcb1e933d03652b9115412d308c3ff466`; its batches originate in attempt 8 at `7802adce39f86b5d379df2f229985df6bf770611`, through attempt 9 at `23f77ab07ab557c0cf5ce1d3f89c689f9919f797`. This report does not certify a later integration SHA.

The [replay script](proof/audit-induction-2026-09-05.py) now includes an attempt-10 branch and writes [attempt-10 measurements](proof/audit-induction-10-measurements-2026-09-05.json), including the revision decision review. Earlier measurement files remain untouched. No model, helper, database, live index, network client or port 5179 was used. Historical checkout and scratch paths were inspected as receipt strings only. No worker labels were opened. No runner, prompt, scorer, decision, proposal or receipt was edited; no commit or merge was made.

| Bound artifact | SHA-256 |
|---|---|
| Attempt-10 receipts | `fb26d4f0a6814fc32c00cb51ea7dbc076150b775c545d90cbdc43cd1e16ee0c2` |
| Attempt-10 proposal | `bb3d51e4b6eecf542355ba0e5f5fbb0d09b1e0ad692eb1c5d1674f315a25cd7c` |
| Attempt-9 donor receipts | `22206eafd81b4703060e6a4f578f6cdd25dd8c6183351c0687cb9b9c03fa91d9` |
| Attempt-9 donor proposal | `37db6a1ee53e3ee286d32986f633bb7b12b9dfa4594a462504feb13b1a283997` |
| Attempt-8 source receipts | `fd781970f3bf5f4bafac3b54a418ceeccb28f1b5bb490698f31786e5d5d1d663` |
| Revision decision | `7028edf7471a3624345257e59c6eb7627c011a65424df439a126d906df77098f` |
| Candidate labelling packet | `d647aa62d22f20b44b2de6b122f7e0c6c8fd75441d91b68076b62aecffb9613a` |

The following table replays section B of the [stage-2 audit plan](STAGE2-AUDIT-PLAN-2026-09-05.md). Mechanical validity and subject relevance have separate verdicts.

| Check | Observed | Expected | Verdict / reproduction |
|---|---|---|---|
| B1 — manifest | Archived stage-1 receipts rehash to `2b4e824ea9f93999de6c5108406e60a5c81f108de0b279c52fee2e96d622469c`. Replayed 548 terminal targets, exactly 225 unmapped, including 23 old-holdout members. Manifest order, revisions, card hashes and source binding agree. | Exact identities derived from the archive. | PASS. Measurements `B1`. |
| B2 — calls | Ten records and ten files of each stream type; nine batches of 25 librarian cards, then one consolidation. Every artifact hash, byte count, schema/argv binding, usage record and raw proposal binding matches. Maximum concurrency 4; longest call 656.24768 seconds against 1,800 allowed. | Complete records and bounded batches. | PASS. `B2`, `artifact_checks`. |
| B2-H — resume | Both source receipt hashes match. All nine batch records and all 27 streams are identical on each link, 10 → 9 → 8. Attempt-8 persisted records match. Attempt 8 has no resume. Three separate consolidations remain archived with matching persisted records. | Unchanged reused processes, explicit origin, no accounting duplication. | PASS. `B2.resume_chain`, `lineage_consolidations`. Attempt 9's historical `_scratch/induction-attempt8/receipts.json` resolves through its exact receipt hash to the local archive export. |
| B3 — inputs | All ten stdin files rebuild byte for byte. Zero holdout-v2 IDs, excerpt IDs/text, archived reasons, gold-path literals, split payloads or result markers. No forced shelf count or catch-all shelf. | Frozen cards, v1 taxonomy, batch output and disclosed audit feedback only. | PASS. `B3`. |
| B3-R — rejected keys | c070-1, c110-1, c202-1, c221-1 and their audit reasons occur in `execution.auditor_rejected_keys` and the recorded prompt. None appears in any accepted node or ledger support in either proposal. Mechanically invalid c061-1 is also banned and unused. | Recorded exclusions survive consolidation. | PASS. `B3.auditor_rejected_keys`, `B4`, `revision_decision.accepted_rejected_keys`. |
| B4 — evidence mechanics | Attempt 10: 15 node and 90 ledger references. Decision: 20 node and 96 ledger references. All pass identity, ownership, source eligibility, occurrence and 1–24-word checks. Four decision additions have five distinct candidate-kind cards each. | Valid selected references, at least five distinct cards per new concept. | PASS on mechanics. `B4`, `revision_decision`. |
| B4-R — subject relevance | Agents 3/5; Industry, Media and News 5/5 each. c058-1 and c124-1 do not establish Agents' required autonomous multi-step execution. | Five selected subject-relevant cards per addition. | FAIL in both attempt 10 and the decision. Full cited excerpts and judgments are in `manual_relevance_review`. |
| B5 — ledger and omissions | Attempt 10: 59 proposed, 31 existing, 111 unmapped, 24 unsupported. Decision: 65 proposed, 31 existing, 105 unmapped, 24 unsupported. Each covers 225 distinct cards. All 44/45 proposed rows outside their node's support set have omission explanations, respectively; c177 is repaired. | Complete ledger, own-card evidence or reason, every omission explained. | PASS on structure. `B5`, `revision_decision.ledger_counts`, `omission_explanation_failures`. |
| B5-R — reviewed destinations | Donated c007 cites testosterone effects, not a policy debate. c064/c069 describe generation features or a release, without a finished artifact. c058/c124 ledger reasons inherit the Agents evidence gap. | Evidence establishes the claimed destination under its definition. | FAIL. `revision_decision.focused_ledger_evidence`; cases below. This is a focused destination review, not a semantic certification of all 225 rows. |
| B6 — hierarchy and diff | Attempt 10 has ten nodes; decision eleven, with three roots and eight children. All seven v1 nodes preserve their contract fields. Every include cue has its alternative/evidence pair. Decision diff lists seven preserved and four added, with other operations empty. | Stable identities, complete hierarchy/diff and cue pairs. | PASS on structure. `B6`, `revision_decision.preserved_fields_equal`, full proposal validator. |
| B6-S — operative rules | The three new AI siblings carry exclusions. Agents' persona/monitoring cues exceed its governing definition. Media sends abstract model coverage to Frontier, but never states when it takes priority over a model release. | Definition/cue agreement and usable precedence that survives projection. | FAIL. Node fields and recorded consolidation prompt rules; explanation below. |
| B6-M — candidates | Raw attempt 10 leaves the News parent neither adopted nor rejected. Composition restores it. All 21 batch candidates are then accounted for: 15 adopted/equivalently merged and six explicit rejections. Career is rejected with at most four eligible candidate cards. Product Launches now has a redistribution entry. | Every non-adopted, non-equivalent candidate recorded. | FAIL for raw attempt 10; PASS for decision accounting. Destination evidence remains B5-R. `revision_decision.candidate_disposition_review`. |
| B6-P — pins | Archived before-state has zero pins, memberships and item policies; v1 active. Receipt and pin report agree and explicitly prohibit redirects. | Measured population stated, zero pins explicit. | PASS. `B6.pin_state_replay`, `pin_measurements_match`. No claim about the live library. |
| B7 — accounting | Ten distinct represented CLI sessions; USD 8.2433548 estimated, including USD 1.2355352 for the new consolidation. All four counters and Haiku/Sonnet usage objects reconcile once per call. | Deduplicated estimates, paid cost separate. | PASS. `B7`. Paid cost unavailable. |
| B8 — isolation | All three executions' runner, validator and card-builder fingerprints match their recorded Git objects after newline normalization. Recorded input/output paths, cwd, child environment and no-database/no-helper declarations agree with the archived runner. | Accepted archive-only profile with bound code and file inputs. | PASS under the run-W amendment. `B8`. No independent OS egress telemetry or historical database-snapshot claim. |
| B9 — agreement | Public validator returns `INDUCTION_RECEIPTS_VALID_AUDIT_REQUIRED`, 225 targets, ten calls, `proposal_approved=false`. Independent keys, expansion, evidence counts, accounting and normalized projection agree. The complete proposal validator also accepts the composed decision. | Exact-byte replay and mechanical agreement. | PASS. `B9`, `revision_decision.full_proposal_validator_passed`. These validators do not judge the failing semantics. |

I read every one of the decision's 20 selected quotes in its complete frozen cited excerpt. The following are judgments about what those excerpts establish, not external verification of their claims about products, revenue, awards or events.

| Node | Key | Cited-excerpt finding | Relevance |
|---|---|---|---|
| Agents | c058-1 | Companion-builder application sees, hears, acts, remembers and understands; no autonomous multi-step task described. | FAIL |
| Agents | c088-1 | Internet-using model orders food, books flights, shops and researches. | PASS |
| Agents | c106-1 | AI agents sell cars, underwrite loans, coach mechanics and run an operation. | PASS |
| Agents | c141-1 | Agents autonomously plan, execute and deliver on a goal; the excerpt describes the workflow. | PASS |
| Agents | c124-1 | Speaker imagines a ChatGPT descendant watching screens and meetings; no action or multi-step execution appears. | FAIL |
| Industry | c082-1 | AI competitive ranking argued through infrastructure. | PASS |
| Industry | c130-1 | Government restrictions on an AI lab and access to its models. | PASS |
| Industry | c144-1 | Explicit competition against OpenAI and Anthropic. | PASS |
| Industry | c169-1 | AI token usage compared with revenue capture. | PASS |
| Industry | c213-1 | AI-company ARR, expressly qualified as a rough estimate. | PASS |
| Media | c033-1 | Animation said to be made with Seedance, followed by its generation prompt. | PASS |
| Media | c038-1 | Created film described as winning an AI-film award. | PASS |
| Media | c128-1 | AI animated film blending genAI and human art. | PASS |
| Media | c091-1 | Finished visual website described as made with AI image/video models. | PASS |
| Media | c104-1 | Firsthand description of AI cat-vlog video content. | PASS |
| News | c006-1 | Explicit left/center political debate. | PASS |
| News | c009-1 | Murder charge and shooting at a named location. | PASS |
| News | c010-1 | Home intrusion, death, police response and charges. | PASS |
| News | c011-1 | Police radio declares a riot and reports a capitol breach. | PASS |
| News | c019-1 | Original post reports missiles striking a named air base. | PASS |

B4-R is also a definition/cue conflict. Agents begins “AI agent products that autonomously execute real-world, multi-step tasks and workflows.” Appending “including sensing/acting personas” and “persistent monitoring assistants” does not remove that governing requirement. c058's only excerpt describes capabilities without a task. c124's only excerpt describes hoped-for continuous observation; its include cue and ledger reason add acting for the user. The cited text stops before any such action. These excerpts could support an explicitly broader assistant concept, but they do not prove the narrower claim in this document. Industry's revised supports pass. Media's finished-visual-artifact scope and its image/video-generated website cue agree; the attempt-9 standalone-image cue conflict is resolved.

**Fable's ruling on frozen v1 shelves is accepted as a plan amendment.** Both directions may live in the new node's operative fields, leaving v1 untouched. The implementation still fails that rule. The archived consolidation prompt expressly requires a positive priority statement in the new node's include list or definition. No such statement appears in Generative Media. Its Frontier exclusion covers architecture, scaling or benchmarks “in the abstract.” A multimodal foundation-model release that also demonstrates a prompt-generated claymation animation satisfies Frontier's release cue and Media's animation cue without triggering that exclusion. This is a synthetic boundary case, not a claimed source quotation. Neither projected node decides priority. Putting the choice only in `sibling_cues` would still fail because projection removes that field.

B5-R has three independently reproducible destination cases:

| Row / support | Evidence in the cited excerpt | Conflict / required disposition review |
|---|---|---|
| c007 / c007-3, video `2077870396075094016` | Discusses low testosterone, focus, endurance and muscle mass. | Imported reason says “Panel debate over policy topic.” The excerpt supplies no policy or social-ideology debate. It is the same excerpt rejected as a News support in run W; changing its key kind does not change its subject. Restore `still_unmapped` unless a permitted, recorded disposition support establishes the destination. |
| c064 / c064-2, video `2082842696650043392` | Google Vids lets users generate an AI avatar from a script. | Establishes a creation feature, but no particular finished artifact. Media's definition requires demonstrated finished output. Review for the broad AI parent under the current scope. |
| c069 / c069-2, video `2083066957230915584` | Seedance release, AI video creation and forthcoming enterprise API access. | Establishes a release/feature announcement, without finished output. Review for the broad AI parent unless a specific v1 child is justified by the evidence. |

The Product Launches entry now accounts for all six of its candidate cards: c058 to Agents, c056/c060 to `ai-and-ml`, c064/c069 to Media, c070 unmapped. It also names c088, which belongs to another batch's Agents candidate; remove that extra attribution when repairing the entry. The standalone-candidate omission is resolved, but the recorded destinations still require the corrections above. News' five selected supports remain valid even if c007 stays unmapped.

The composition replay independently reconstructs the decision from attempt 10 plus the donor News node, donor rows c006/c007/c009/c010/c011/c019, and one appended `diff.added` ID. All 229 unchanged node/ledger subtrees match the base. The donor node and six rows match their literal JSON fragments, allowing only the two additional spaces of wrapper indentation. All string contents remain byte-identical. The complete generated document matches the on-disk UTF-8/LF bytes and the dispatched hash; source proposal and receipt hashes also agree. Both source attempts derive the same key table from identical batch outputs.

`compose_revision_decision.py --check` passes. I additionally ran `validate_induction_proposal` on the independently expanded composed proposal, including its complete schema, hierarchy, provenance and ledger checks. This matters because the composition script's own `verify` routine performs selected checks rather than calling that whole validator. Both pass; neither establishes subject relevance. The labelling packet hash, proposal binding and every candidate node field match the decision. Labels produced for these bytes must remain archived against this rejected candidate.

For a final reviewer-authored repair, keep the frozen inputs and record each additional edit in a successor decision:

1. Resolve the Agents scope explicitly. Either retain autonomous multi-step execution and select five genuinely qualifying candidate-kind supports, or author a broader definition that separately admits task-execution agents, sensing/acting companions, and proposed persistent screen/meeting monitors. The latter is an acceptable scope choice under this plan; remove the unsupported requirement that monitoring evidence also shows action, and align the include cues, sibling distinctions and ledger reasons. Rewording must describe what c058/c124 actually say, not attribute execution to them.
2. Put the frozen-shelf priority in operative fields. For the identified Frontier/Media case, state that a release whose excerpt centers on a finished generated visual artifact takes Media priority; architecture, scaling or benchmark coverage without that artifact focus goes to Frontier. Encode both directions in the new node, and reconcile every confusing-v1 alternative named by the new nodes, including developer workflows and technical security versus external policy. Preserve all seven v1 definitions/cues.
3. Restore c007 to unmapped unless eligible recorded evidence justifies News. Reconcile c064/c069 with Media's finished-output requirement, and repair c058/c124 under the chosen Agents scope. Keep the omission explanations and update Product Launches' redistribution reason to match the resulting ledger exactly.
4. Hash and independently audit the successor decision and its projection. Regenerate the candidate packet and obtain fresh blind labels/adjudication for changed definitions or operative rules before the measured pass. A further model induction is unnecessary. No approval of unseen replacement bytes is implied.

The decision's projection is mechanically valid but unapproved. `taxonomy_from_proposal.py` correctly unwraps `proposal`; its node result agrees with independent service normalization. For these rejected bytes, the compact sorted-key service document plus one LF is 8,527 bytes, SHA-256 `06385da89160b9b265dd4b6ef19e2e27d5830eefe308002e5d91fa2a8c393671`; the calculated service revision is `12ca37e6152012caceb27d43754cf81b040ffbd4539eea260bba86a46ee91cc3`. These are diagnostic hashes, not a service-returned approval or the hash of a metadata-rich approved export. No projected file was installed or approved. Fable must not write an approval record for this decision. The [run-W approval-record requirements](INDUCTION-AUDIT-2026-09-05.md) remain in force for a replacement.

Attempt 10 represents 1,183,579 stdin bytes, 497,706 stdout bytes, zero stderr bytes and 20,930 schema bytes: 1,204,509 input-plus-schema bytes. CLI counters are 22 input, 508,735 output, 835,384 cache-read and 637,594 cache-creation tokens. Model estimates are USD 0.438508 for Haiku and USD 7.8048468 for Sonnet, already included in the top-level estimate. The nine reused batches account for USD 7.0078196. Including all three consolidations across attempts 8–10 gives twelve unique processes and USD 11.105579 in CLI estimates. This is neither total induction-history cost nor an invoice.

Validation performed in this worktree:

```powershell
python -B docs/library/proof/audit-induction-2026-09-05.py --archive docs/library/proof/induction-run-10-2026-09-05 --output docs/library/proof/audit-induction-10-measurements-2026-09-05.json --self-test
python -B tests/validate_proof_receipts.py --receipt-kind induction --receipts docs/library/proof/induction-run-10-2026-09-05/receipts.json --require-real
python -B scripts/librarian/compose_revision_decision.py --check
git diff --check
```

The replay completes with eight rejection/normalization/accounting self-checks; both validation commands exit 0. The audit extension records the resume chain, independent composition, complete proposal-validation comparison and all 20 human relevance judgments. The audit script is review tooling, and these passing checks do not independently certify my added code: Fable must inspect it and rerun the affected replay on the collected integration SHA. Earlier measurements retain SHA-256 `16b995b563c4dae5b623d43f665ca75eed1b65e17f3a492caf2afc450a248620` (run W) and `b719111970654e59ab5cecfc1bfe32b651665d0f98261ab94bb26a33c3f87844` (attempt 9).
