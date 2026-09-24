**REJECT taxonomy-v2-2026-09-05 as currently proposed and archived.** Five new nodes lack five subject-relevant supports after review. The archive also fails byte validation on this checkout. Preserve this result; taxonomy approval and the measured pass remain blocked. Apply stays disabled.

Auditor: Codex, GPT-6 Astra, independent auditor and plan owner under [orchestration v1](ORCHESTRATION-V1-2026-09-04.md). Scope: [run W](HOLDOUT-V2-LABELLING-BRIEF-2026-09-05.md), [audit plan B1–B9](STAGE2-AUDIT-PLAN-2026-09-05.md), and the [stage-2 gate](STAGE2-GATE-2026-09-05.md). Audited checkout: `78d96e876b44b7ede831637fce6d619553512d27`. Historical attempt-6 execution SHA: `2b90453ae7c50f44d1fffef0644009088ce2151a`. This audit does not certify a later integration SHA.

The [independent replay script](proof/audit-induction-2026-09-05.py) writes [measurements](proof/audit-induction-measurements-2026-09-05.json). It implements serialization, key expansion, quote normalization, evidence checks, ledger counts and accounting independently, then calls contract v1.2 helpers for comparison. Manual subject-relevance judgments are identified separately and bound to the exact proposal hash. Every file the script reads has a recorded SHA-256. No model, helper, database, live index, port 5179 or network client was used. No runner, prompt, scorer or archived input was edited. Nothing was committed.

The observed induction receipt SHA-256 is `c8668c24b675f09f3556ea40ff255e635ade65ccc915d07af0ad51a0881f9caf`; the proposal SHA-256 is `26212e67eb871bc4a7a2224d61af5541c50f8693539c2fa37596a0f3e477104f`.

The per-check verdicts follow. Subrows distinguish evidence that passes from defects in the same plan check. Reproduction references name JSON sections in the measurements; running the script below regenerates them from the archive.

| Check | Observed | Expected | Verdict | Reproduction for FAIL |
|---|---|---|---|---|
| B1 — manifest binding | Original proof receipts rehash to `2b4e824ea9f93999de6c5108406e60a5c81f108de0b279c52fee2e96d622469c`. Replaying 548 terminal attempts yields exactly the manifest's 225 unmapped IDs, in order, with 23 old-holdout members. Source revisions, self-recomputed card hashes, source-manifest binding and terminal target rows agree. | Exact identities and old-holdout flags derived from archived attempts. | PASS | — |
| B2 — accepted call records | Ten distinct call records and ten stdin/stdout/stderr files: nine batches of 25 librarian cards and one consolidation. All 30 call-artifact hashes, schema hashes, argv schema arguments and usage records match. Maximum serialized card: 8,153 bytes. Timeline encloses all calls; consolidation follows every batch. Proposal artifact, receipt proposal and original structured output agree. | One authenticated record per represented process; batches ≤25; exact call input/output identities. | PASS | — |
| B2-H — preceding attempts | Nine batch records are identical in all five preceding receipts and attempt 6. Six historical consolidation stdin/stdout artifacts are unavailable by recorded hash: one stdin for each timeout attempt, plus attempt 4 stdin and stdout. There is no explicit resume-source field in attempt 6. | Replayable failed processes and explicit provenance for reuse; preserved failures. | FAIL | Inspect `B2.prior_attempts[*].missing_raw_call_artifacts` and `resume_metadata_fields`. The matching batch files cannot reproduce any earlier consolidation stdin or attempt 4 stdout. |
| B3 — prompt containment | All ten stdin files rebuild byte for byte. Zero v2 ID, excerpt-ID, excerpt-text or archived-reason hits. But all nine batch prompts contain the non-v1 gold path `AI and ML / Developer Tools / Coding Assistants` as a template example; it is also the gold path for `episode_9ddb44f98b2`. No forced shelf count or junk shelf is requested. | No gold paths in induction input, alongside exact prompt reconstruction and evaluation exclusion. | FAIL | `B3.nonbaseline_gold_path_hits`; compare `prompts/batch_prompt.md`, “Node Specification Requirements,” with that gold row. This is a literal exclusion failure, not proof that an item's label was copied into the prompt. |
| B4 — evidence identities and quotation | Seven additions each select five distinct cards: 35 node supports. With 143 ledger supports, all 178 selected references pass source/card/excerpt binding, eligible source type, one-excerpt occurrence and the NFC/whitespace 1–24-word rule. | ≥5 distinct valid source cards per new node; each selected reference valid. | PASS | — |
| B4-R — subject relevance | Six selected supports fail to establish the node's subject, leaving five nodes below five grounded cards. Details below. | Quote occurrence must also establish relevance; company/product names alone do not establish subject membership. | FAIL | `B4.manual_relevance_gaps` contains each full support and its complete frozen excerpt. Compare with the node definition/include/exclude fields in `proposal.json`. |
| B5 — ledger structure | Exactly 225 distinct manifest IDs: 106 proposed, 37 existing, 74 still unmapped, 8 unsupported. All 143 mapped rows have valid evidence; refusals have reasons and no assigned shelf/evidence. | Complete ledger, approved vocabulary references, evidence or reason. | PASS | — |
| B5-X — proposed-to-support traceability | 35 proposed rows occur in their named node's five supports; 71 do not. Those 71 reasons explain the classification, without saying why the card was omitted from node support. | A proposed row's node supports that card, or its reason explains the omission. | FAIL | `B5.proposed_without_node_support`, e.g. `c019`, reason “War/military conflict footage description.” Its news node selects c006, c007, c009, c010 and c011. The prompt's exactly-five cap explains the producer's constraint, but the required per-row explanation is absent. |
| B6 — shape and v1 diff | Fourteen unique IDs/paths: four roots, ten level-2 nodes. All seven v1 IDs preserve path, definition, include and exclude fields exactly. Every include cue has a nonempty alternative/evidence pair. Diff: seven preserved, seven added, no renamed/merged/split/retired v1 nodes. | Stable v1 IDs, complete explicit diff, paths 1–3 levels and paired cues. | PASS | — |
| B6-S — operational sibling boundaries | Product Launches & Demos overlaps Generative Media on creative-output launches, and AI Agents on consumer agent launches. Those nodes lack mutual precedence rules. The Generative Media definition requires creative-media generation, while its companion-builder cue does not. Archiving sibling cues alone would also remove them from the approved taxonomy given to the assignment client. | Evidence must distinguish confusing siblings consistently for labels and predictions. | FAIL | Compare the product node's generative-demo cue with the Generative Media definition using c033/c069; compare the agent-launch product support c026 with AI Agents. Compare the companion cue with c058's sole excerpt. Read `assign.md` rule 5 and `library_work.py:approve_taxonomy`'s allowed node fields. |
| B6-P — pin impact | Proposal contains only `silent_redirects=false, items=[]`. There is no induction-state pin count. | Pin-impact report states zero pins explicitly and identifies the measured state. | FAIL | Inspect `B6.pin_impact_report` and the receipt's top-level fields in `B8`. Empty impact rows do not establish an observed zero-pin population. |
| B6 — rejected proposals | One rejected concept, Robotics & Computer Vision, is retained with its three-card threshold reason. The 19 batch candidate occurrences otherwise have corresponding adopted concepts, including business, culture and agent synonyms. | Rejections retained; candidate merges distinguishable from changes to existing v1 IDs. | PASS | — |
| B7 — accounting | Ten distinct CLI sessions. All four usage counters, every Haiku/Sonnet `modelUsage` object and estimates reconcile once per call. Accepted-call estimate: USD 7.6077142. Paid cost is unavailable. Prior-history limitations are disclosed below. | Deduplicated raw-envelope accounting; retain every model; estimates remain estimates. | PASS | — |
| B8 — execution isolation evidence | Relative artifact references are contained and no `:5179` appears in the induction receipt. The recorded runner reads archived files and has no DB/helper operation in its induction path. But receipts omit cwd/checkout identity, isolation configuration, API-key-unset assertion, HTTP/no-service declaration and before/after state evidence. | Reproducible no-write/no-egress evidence and explicit API-key-unset assertion. | FAIL | `B8` inventories the missing fields. `_claude_call` in the archived runner inherits the environment in `subprocess.run`; it neither records nor clears `ANTHROPIC_API_KEY`. Static code and `--tools ""` cannot prove the historical environment. |
| B9 — validator on delivered archive | The unmodified CLI exits 1: `INVALID: Artifact bytes/hash mismatch`. Three archive files disagree with their recorded bytes. | Exit 0 with `INDUCTION_RECEIPTS_VALID_AUDIT_REQUIRED`; independent/common counts agree. | FAIL | Run the validator command below. `artifact_checks` identifies all three files. |
| B9 — helper agreement | Independent call bytes, key table, expanded proposal, per-node distinct-card counts, ledger counts/dispositions, quote normalizer and accounting agree with the helpers. A scratch-only CRLF reconstruction passes the full validator with 225 targets, ten calls and `proposal_approved=false`. | Agreement on shared mechanical checks, without treating validation as semantic approval. | PASS | — |

The public validator returns only target and call counts. The B4/B5 comparison uses its independently expanded proposal; it does not claim the CLI publishes metrics it lacks. Subject relevance, per-row support omissions and B8 induction isolation are audit obligations the current validator does not enforce.

The relevance review covered every selected node support. The following six gaps are auditor judgments, separate from the successful quote checks. Each cited card has only one frozen excerpt, so no other eligible excerpt supplies the missing context.

| Node | Selected support | What the excerpt establishes | Missing subject evidence |
|---|---|---|---|
| News and Current Events | c007-1 / `2077870396075094016` | Testosterone effects on focus, endurance and muscle mass. | A political/civic event or news report. A speaker or channel identity cannot supply that context. |
| AI Product Launches & Demos | c037-1 / `2080091059644964864` | A comparison involving school blackboards in China. | Any AI function or AI-powered product. The ledger's AI-branded description exceeds the excerpt. |
| AI Industry and Business | c045-1 / `2080714082626293760` | A wheeled robot, military potential and a Europe/China comparison. | AI-industry economics or AI strategy. Recognizing Unitree's name cannot supply the missing AI subject evidence. |
| Generative Media | c058-1 / `2082506081365008384` | A no-code companion that sees, hears, acts and remembers. | Creative-media generation, required by the definition. The matching companion include cue is itself broader than that definition. |
| AI Agents | c110-1 / `2087221157787525120` | Requests to send NDAs and count employees. | Identification of an AI agent autonomously executing those requests. |
| AI Agents | c116-1 / `2088306674813775872` | A favorable Grok Bot reaction and criticism of its marketing. | Autonomous or multi-step task execution. Product-name comparison is insufficient. |

| New node | Distinct cards passing mechanical checks | Remaining subject-relevant supports in the selected set | Five-card requirement |
|---|---:|---:|---|
| News and Current Events | 5 | 4 | FAIL |
| Sports and Streaming Culture | 5 | 5 | PASS |
| AI Product Launches & Demos | 5 | 4 | FAIL |
| AI Industry and Business | 5 | 4 | FAIL |
| Generative Media | 5 | 4 | FAIL |
| AI Culture & Memes | 5 | 5 | PASS |
| AI Agents | 5 | 3 | FAIL |

These counts concern the selected supports in the immutable proposal. Other batch evidence might support a reviewed replacement, but it cannot silently rescue the recorded proposal. A repair must retain the original output and record a separate reviewer-authored decision or newly dispatched candidate with its evidence and hashes. No model or subset rerun is requested here.

The two pre-verification failures are accurately excluded. `c115-1` has a six-word non-occurring quote; `c119-1` has a nineteen-word non-occurring quote. Neither fails the word cap. They are the only invalid supports among all 254 derived keys (109 candidate, 145 disposition). Both are named under “Unusable support keys” in the recorded consolidation prompt, and neither appears among the 178 accepted references. Node quotes range from 5 to 22 words; all accepted references range from 4 to 24 words.

Resume provenance is visible through identical records, rather than an explicit resume field. All nine batch records, including argv, times and artifact hashes, match attempt 1 unchanged. Their stdin also matches what attempt 6 would render. The consolidation argv alone adds `--effort low`; it has a new timestamp, session and output. The ten-call accounting therefore represents nine reused historical processes and one newly launched process, not ten new processes in attempt 6. The receipt timeline deliberately starts at the earliest reused call. Preserve those original times and add a provenance sidecar binding each prior receipt hash, origin run/commit and reused call; do not relabel the batches as having run under attempt 6's runner fingerprint.

| Attempt | Archived status | Independent observation |
|---|---|---|
| 1 | Aborted | Consolidation exit -1, timed out, zero stdout bytes reported; nine batch records reused later. |
| 2 | Aborted | Same batches; a distinct consolidation timeout. |
| 3 | Aborted | Same batches; a distinct consolidation timeout. |
| 4 | Completed | Consolidation exit 0. Archived proposal has 224 ledger rows, two missing manifest IDs, one extra mistyped ID and one invalid node `card_hash`. Its original consolidation stdin/stdout are absent. |
| 5 | Aborted | Same batches; a distinct consolidation timeout. |
| 6 | Completed | Same batches plus the new successful short-key consolidation; original output is preserved. |

Thus “five attempts before consolidation completed” is inaccurate: attempt 4 completed but failed validation. Attempts 1–6 contain 15 distinct process records after deduplicating reused calls: nine batches and six consolidations. Four timeout calls have unavailable usage/cost. The known estimate across unique records is USD 8.9921952, including attempt 4's receipt-reported USD 1.384481; that earlier amount cannot be authenticated against its missing stdout. Neither figure is a complete cost of the induction work or an invoice. The separately archived three-batch probe log is also not a complete process archive and is outside that six-attempt sum.

| Raw accepted-call accounting | Recomputed value |
|---|---:|
| stdin bytes | 1,213,807 |
| stdout bytes | 555,364 |
| stderr bytes | 0 |
| schema bytes | 20,930 |
| stdin + schema bytes | 1,234,737 |
| CLI input tokens | 20 |
| CLI output tokens | 471,596 |
| CLI cache-read input tokens | 761,576 |
| CLI cache-creation input tokens | 570,795 |
| Haiku modelUsage input / output tokens | 455,409 / 162 |
| Haiku modelUsage cost estimate, USD | 0.456219 |
| Sonnet modelUsage cost estimate, USD | 7.1514952 |

The top-level CLI counters and per-model counters are distinct reported quantities; they are not added together. Full modelUsage objects, including thinking-token and model metadata fields, remain in the measurements.

The manifest newline discrepancy is benign content equivalence, but exact receipt bytes still matter. `git show HEAD:<path>` confirms the LF-normalized bytes equal the committed blobs, not merely parsed-equivalent JSON.

| Artifact | Materialized CRLF SHA-256 | Committed LF SHA-256 |
|---|---|---|
| Induction manifest | `9a759f68890a30e9e8403e2f1364cfb9464f335e342e0a70f75e4ddc6dab422d` | `20122edb273544eacaa0396c51b47f5ba6e9e6ce231048fe45ca35a8d4949840` |
| Holdout v2 | `0d5be9a11c8589dcbde79a7b2bbb08a23ad6e9e299a6da2f224439583772b309` | `28fdb16a096deb4cd62e6f7007e5e9792741ab876050d8497e4c29932d328d78` |

The current validator binds `induction_manifest_sha256` to the materialized file's exact bytes: the CRLF hash here. The gate lists the LF blob hash. Record both identities and the explicit CRLF→LF relation in stage 2, and archive the actual bound bytes under relative paths protected from text conversion. A portable replay must validate those archived bytes rather than rebind history to the checkout's newline convention. Do not weaken receipt checks to accept arbitrary reserialization.

There is a separate export defect: these three files inside the supposedly byte-preserved induction archive contain LF bytes although their references require CRLF. Existing `-text` attributes preserve the bytes already stored; they cannot restore bytes normalized before archival.

| Archive path | Observed bytes | Required bytes | Observed SHA-256 | Required SHA-256 |
|---|---:|---:|---|---|
| `taxonomy.json` | 5,414 | 5,591 | `0ecad26328ea2eb9b03858f672e7b92f9d975d45f8e01b6382c8faa3aa2c4907` | `700f8dc09831fa14491a89f4ca68417ac721a17d45bcd2a9dc6c7ede484d11df` |
| `fingerprints/validator` | 108,318 | 109,896 | `af687818e9e2a87a442f62479ee4082beaebb788069212c3bfe63e8bc22ea1e4` | `9c84480b1e0987c632fc9e574f0544c0d3c65cf6bf17a3184c9f3c35484dfe76` |
| `fingerprints/card_builder` | 9,721 | 9,931 | `64c9fe900408f709f3d2462979b07e740c9688d0a9244d10f9ff8818fef9d096` | `a848cc02d451478548ac0a3d5968a14604919f3c0744a0ee88332dc615b1a10a` |

Reconstructing CRLF in a scratch copy reproduces all three required hashes and lengths exactly. Fable can restore those exact bound bytes with an export-repair record and rerun the validator; receipts and prompts need no change. This diagnostic does not change the FAIL on the delivered archive.

Projection to the eight service contract fields is technically valid as a storage operation, once semantic approval is earned. Removing `sibling_cues` and `supporting_evidence`, deriving `name`, `parent_shelf_id` and `retired=false`, and sorting as the service does yields a 9,350-byte canonical taxonomy document. Its proposed revision hash is `4f954c529079eacb7fe279261a4de76f1c488dc9492453953933fe0996b23810`. The helper independently reproduces that document. This is a calculated candidate identity, not an approved revision.

An approval record must bind the exact proposal and receipt hashes, this audit and disposition of every finding, the projection algorithm/field list, projected-file hash and service-returned revision hash, all seven preserved IDs, the v1 parent revision, rejected concepts and explicit measured pin impact, the approver and approval timestamp, and the authorized disposable database identity. Preserve supports and sibling cues in the immutable proposal and link that evidence from the approval record.

Keeping sibling cues only in the archived proposal is insufficient if they govern labels but never reach predictions. Resolve B6-S before sealing the mapping: either encode all operative distinctions in the service's allowed definition/include/exclude fields, or bind and render a separate immutable sibling-rule artifact in every assignment input. The latter requires a declared renderer/input contract and a hash; an unrendered archival link does not suffice. Any changed definitions or rules require an updated candidate packet and fresh independent adjudication against that exact version before execution. Current blind-worker files remain preserved preliminary labels.

As plan owner, I accept Fable's proposed stage-2 `freeze_inputs` profile and output path, with the following amendments. It must bind `docs/library/taxonomy-v2-2026-09-05.json`, `docs/library/proof/holdout-v2-2026-09-05.json`, the sealed adjudicated labels, the separate adjudicated mapping table, and `scripts/librarian/prompts/assign.md`, writing `docs/library/proof/manifest-stage2-2026-09-05.json`. Bind the sibling-rule artifact and renderer too if that option is chosen. The present proposal cannot yet supply the approved taxonomy input.

The profile must preserve the stage-1 evidence freeze exactly: all 548 ordered IDs, source revisions, card hashes, card profile, bounded-head hashes, and an empty exclusion set. Prefer consuming the authorized archived source/heads already staged inside the worktree. If rebuilding cards, compare every identity and both aggregate hashes to stage 1 and stop on any difference. Do not reopen the live index or discover new corpus paths. Old gold/split artifacts stay frozen as regression inputs; stage-2 scoring must use the new sealed mapping without fallback to v1. Expose labels and mapping only to the independent scorer/reviewer, never to prompt construction or the execution client.

The execution manifest needs both exact file-byte hashes and the actual UTF-8 prompt-template hash after the renderer's documented newline handling, plus archived bytes for replay. It must fingerprint the integrated runner, validator, scorer, service, renderer and card builder. Preserve the historical execution manifest. Check these bindings before the first model process; any mismatch blocks execution. A profile that merely swaps four filenames in the old freeze is incomplete.

Before execution, Fable must fill and sign the following identities; pending entries are required fields, not defaults or authorization:

| Identity to record | Exact known value or required pending record |
|---|---|
| Integrated candidate | New full Git SHA after repair, file fingerprints, independent review of Astra-owned changes, and acceptance results on that SHA. The audited worker SHA above cannot stand in for it. |
| Stage-2 manifest | Relative path above, schema/profile version, exact SHA-256, freeze timestamp/commit before execution, and approval-record hash. |
| Original source | `uoink-index-copy-2026-09-04-upgraded.db`, date 2026-09-04, SHA-256 `2765cc359805fb12f7a90aecd3dd0b34d884aa8cb3015785011bf400da3b4dfc`; 71,733,248 bytes, original schema 25. Record actual staged path and upgraded disposable copy's hashes/schema separately. |
| Target manifest | 548 targets; `213ef46f6853ba2512f584dd202227bb86ccc18691dacd0f76fb0ca636ed8d35`; zero exclusions. |
| Cards and bounded heads | `cards_hash=b30f4918c51cc7be2c688482d79088d39f69091db02b37024a952b2cc78f6865`; `corpus_heads_hash=1bb2d1c953a93c1597c3e35b64734ee604172033cca794b49a361ae7e76d7af9`; archive each head's original bytes and relative reference. |
| Card builder/profile | Exact Windows builder hash `a848cc02d451478548ac0a3d5968a14604919f3c0744a0ee88332dc615b1a10a`; LF content hash `64c9fe900408f709f3d2462979b07e740c9688d0a9244d10f9ff8818fef9d096`. Profile hash `6e265b0b2822ba3db6865cfa4002824d94538d2bfc0b5366e3f210504ac6bd14`: librarian, schema 1, spread-longest-v1, six clips, 240 characters/clip, 8,192-byte card/head budgets. |
| Evaluation identity | Holdout v2's two hashes above, exact 47 timed/13 text-only identities and revisions, no replacements; labelling-packet hash `0db345809e6806e6be08fd24f9953ceda24f6d161344a0e2af62aeb0279f18e1`. Rehash any replacement packet after taxonomy changes. |
| Sealed labels and mapping | Separate immutable paths and exact SHA-256 values; labeller identities, adjudicator identity, blind-access provenance, seal timestamp or commit preceding execution, and taxonomy/rule version. Both hashes are pending. |
| Mapping/scoring rule | `strict-mapped-primary-v2`; NFC and trimmed path segments, preserved case, deepest unambiguous approved ancestor, strict primary equality. Freeze the actual 60 mapping decisions, including unmappable cases. |
| Approved taxonomy | `taxonomy-v2-2026-09-05`, v1 parent `taxonomy-v1-2026-09-04`, parent revision `2f283053bbaca2e94c2dbd340f19c62a89f529457ac40ae5b1d2d84379d22d98`; approved projected-file hash and service-returned revision are pending. Do not substitute the calculated rejected-candidate hash. |
| Assignment prompt/rules | Current checkout file SHA-256 `92a25e2b960c51ef8c306b3eddbd49fdb431a6f84d55c8482b24bb6f2ad816c8`; LF/rendered-template SHA-256 `662e8ee8133110beefb59b948e4dcebf9e64104c1e6f97deb08aee4000221ae1`. Rehash after any repair. Bind exact schema, taxonomy serialization, sibling rules and renderer. |
| Installed subscription client/model | Record supported client name/version, executable path and binary hash, model ID, effort, exact argv and installed-client verification receipt. Historical calls used `claude-sonnet-5`; that is not evidence of the future installed client's availability or support. Record `ANTHROPIC_API_KEY` unset at launch without recording secrets. |
| Allowed corpus egress | Ryan/Fable's authorization identity and timestamp, permitted provider/client, exact corpus/card fields and scope, tools disabled, and prohibition on labels/gold/mapping egress. No execution authority is inferred from this audit. |
| Budget and isolation | Ryan's paid-spend decision, cost ceiling and accounting basis; two-hour deadline, concurrency ≤4, one reasoning retry, strict >10% guard after 20 completions, no hidden restarts. Record worktree/cwd, disposable DB and output paths, non-5179 port, apply disabled, before-state hashes and cleanup ownership. |

B8's snapshot requirement was written for a disposable database, while this induction runner uses archived files only. For a future archive-only induction, the plan may explicitly record “no database/helper opened” with bound input/output paths, launch cwd, environment and permitted model egress. That amendment cannot create missing historical observations. Fable must recover contemporaneous evidence or retain the limitation; a new snapshot cannot prove the old execution state.

Validation performed:

```powershell
python -B docs/library/proof/audit-induction-2026-09-05.py --self-test
python -B tests/validate_proof_receipts.py --receipt-kind induction --receipts docs/library/proof/induction-run-2026-09-05/receipts.json --require-real
git diff --check
```

The audit completes with exit 0 and eight rejection/normalization/accounting self-checks passed. Exit 0 denotes completed replay, not approval. The original validator command fails as recorded in B9. The script's isolated diagnostic at `_scratch/proof/audit-induction-2026-09-05/eol-diagnostic` passes the same validator after the three exact-hash CRLF reconstructions. No application test suite or model execution was run for this archive-only assignment.

Fable's next review packet must resolve B2-H, B3, B4-R, B5-X, B6-S, B6-P, B8 and B9, preserve the original run and preliminary labels, and name the repaired integrated candidate. The measured pass must wait for a separately approved taxonomy and sealed labels/mapping against its final rules.
