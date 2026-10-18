**REJECT taxonomy-v2-2026-09-05 (revision decision 3).** Two findings block approval and the measured pass: **B5-R3**, three further sampled ledger destinations unsupported by their cited excerpts, and **C3-EOL**, the bound measurement file's checkout bytes prevent the required composer replay. All eleven edits requested in audit 11 are correct. B6-S-Agents-Security and B5-R2 are resolved. Apply stays disabled.

Codex / GPT-6 Astra, independent auditor and plan owner under [orchestration v1](ORCHESTRATION-V1-2026-09-04.md), responding to the [run AD brief](INDUCTION-REVISION-3-BRIEF-2026-09-06.md). Audited checkout: `44a80ae38cf4e74c9d8e39b6cd929fde2a460fa5`. This report does not certify a later integration SHA. B1-B3 and B7-B9 retain the findings in [audit 10](INDUCTION-AUDIT-10-2026-09-05.md); this dispatch replays composition and B4-B6.

The [decision-3 replay](proof/audit-decision-3-2026-09-06.py) adapts the decision-2 audit without changing the earlier script or measurements. Its [measurements](proof/audit-decision-3-measurements-2026-09-06.json) contain input fingerprints, complete cited excerpts, per-edit digests, sampling identities, judgments and exact replacement rows. The script compares independent evidence checks and projection with the public validator and composer. The inherited `human_reason` fields contain this auditor's judgments, not scores inferred by the validator or a separate human review.

The measurement file's SHA-256 is `63351e9ff8d2b16c82e32cead5eee058fe9efb437e4fe167a440d6a3416ab0a1`; the replay script's SHA-256 is `9721436ae5057407732d938bbba493d5b6f0797f419c0be4d7b034cb89984e36`. Both files use UTF-8/LF.

| Artifact | SHA-256 |
|---|---|
| Decision 3, exact file bytes | `308860a0c1cf42aadf9f309f44c0a44a5358d97defdee95950d2027d0c94a16e` |
| Decision 2, matching `successor_of` | `27e010cea18a4a4b6c9ac20b0061dd264754fea94e088e1e8fdc8e71452b19bd` |
| Decision-2 measurements, hash bound by decision 3 | `cf7eb83b1e8e8ffb396fbf59c0fb2f36f5317df7271a52de0dd1624a73db8016` |
| Decision-2 measurements, actual CRLF checkout bytes | `78a9c5ea9b974ed1c3099227695a82284735d841c9cea0b32e887c6d23f5f639` |
| Packet 12 | `e571d4d82a5e80b67adef14d4fa336693bce41d2da724a92d0ac4ddfead926e0` |
| Attempt-10 proposal / receipts | `bb3d51e4b6eecf542355ba0e5f5fbb0d09b1e0ad692eb1c5d1674f315a25cd7c` / `fb26d4f0a6814fc32c00cb51ea7dbc076150b775c545d90cbdc43cd1e16ee0c2` |
| Attempt-9 donor proposal / receipts | `37db6a1ee53e3ee286d32986f633bb7b12b9dfa4594a462504feb13b1a283997` / `22206eafd81b4703060e6a4f578f6cdd25dd8c6183351c0687cb9b9c03fa91d9` |

The eleven recorded edits replay independently against decision 2: every before-value matches, every after-value changes its target, and the reconstructed full proposal equals decision 3. A second reconstruction uses only audit 11's exact Agents strings and its measurement replacement objects; that also equals the full proposal. Both strings occur verbatim in [audit 11](INDUCTION-AUDIT-11-2026-09-06.md). All unlisted proposal fields and the `sources` object are unchanged. The successor, repair specification, author, rationale and edit inventory are the new decision wrapper.

| Edits | Target | Result |
|---|---|---|
| 1-3 | Agents include, sibling cue and exclusion | Exact requested strings; only include index 4, its mirrored sibling string and the appended Security exclusion change. PASS. |
| 4-11 | c087, c095, c123, c143, c158, c177, c182, c215 | Complete rows equal audit 11's eight replacement objects. Destinations and reasons pass on rereading. PASS. |

C3-EOL is reproducible with `python -B scripts/librarian/compose_revision_decision_3.py --check`: exit **1**, `MISMATCH: decision file differs from the deterministic composition`. The decision itself has the advertised hash and LF bytes. The bound decision-2 measurements contain 3,452 CRLF pairs; replacing those pairs with LF reproduces their bound hash exactly. `git ls-files --eol` reports `i/lf w/crlf attr/text=auto` for that file. The existing `.gitattributes` protections cover decisions and execution archives, but omit audit measurements.

The recomposed object differs from decision 3 only at `repair_specification.measurements_sha256`. An in-memory diagnostic replacing that value with the verified LF hash reproduces every decision byte. This establishes the cause; it does not turn the failed command into a pass.

The exact C3-EOL repair is to add `docs/library/proof/audit-*-measurements-*.json -text` to `.gitattributes` and restore `proof/audit-decision-2-measurements-2026-09-06.json` to its existing LF content. Its resulting hash must be `cf7eb83b1e8e8ffb396fbf59c0fb2f36f5317df7271a52de0dd1624a73db8016`, and the unmodified composer command must exit 0. Preserve the decision's bound hash. Neither the attributes nor earlier measurement bytes were edited in this audit.

| Check | Observed | Expected | Verdict |
|---|---|---|---|
| B4 mechanics | 20 node references, 92 ledger references; identities, ownership, eligibility, normalized occurrence and 1-24-word limits pass. No rejected/banned key is selected. | Every selected reference valid; candidate-kind node supports. | PASS |
| B4 relevance | Five distinct subject-relevant supports each for Agents, Industry, Media and News. | Five per new concept under its operative scope. | PASS |
| B5 structure | Exactly 225 unique manifest cards: 59 proposed, 33 existing, 109 unmapped, 24 unsupported. | Complete ledger and predicted counts. | PASS |
| B5 omissions | All 39 proposed rows outside their node's selected supports have an explicit omission suffix. | Every omitted support explained. | PASS on structure |
| B5 prior repairs | All eight B5-R2 rows pass; c007/c064/c069 and c058/c124 retain their earlier passing repairs. | Resolve the named prior findings. | PASS |
| B5 fresh sample | 35 rows: 30 mapped, five unmapped controls. Three mapped destinations fail; the other 32 rows pass. | Each mapped subject established by its cited excerpt. | FAIL: B5-R3 |
| B6 hierarchy and v1 preservation | Eleven nodes, three roots/eight children; seven preserved/four added. All eight service fields and canonical bytes of each preserved node equal v1. | Stable IDs and complete hierarchy/diff. | PASS |
| B6 scope and cues | All includes mirror sibling cues; definitions and includes agree. Personal-assistance/security distinction survives projection. | Operative distinctions retained. | PASS |
| B6 candidates and pins | All 21 candidates accounted for: 15 adopted/equivalent, six rejected. Archived pins, memberships and item policies are zero; v1 active; no silent redirects. | Complete candidate disposition and explicit measured pin impact. | PASS for the archived state |
| Complete proposal validator | Accepts decision 3 and, separately, the three proposed ledger repairs together. | Schema/evidence/ledger validity. | PASS on mechanics |

I reread all 20 selected node supports in their complete frozen cited excerpts. Agents' companion and proposed-monitor branches still justify c058/c124 after the personal-assistance qualification. Industry's five supports concern competition, external restrictions, usage/revenue and qualified ARR estimates. Media's five establish finished creative outputs; News's five establish political debate or specific incidents. These judgments assess what the excerpts establish, without verifying their external claims or inferring missing continuations.

The B6 synthetic case from audit 11 now resolves to **Security**: a proposed AI security assistant continuously watches the user's screen to detect prompt injection and enforce runtime guardrails. Agents `exclude[4]` explicitly sends that case to Security. Conversely, a proposed assistant watching screens and meetings for personal help falls under Agents `include[4]`, which states its priority over Security for that case. Both fields survive projection. These are auditor-created boundary cases, not observed classifier predictions.

| Other boundary replayed | Operative distinction | Verdict |
|---|---|---|
| Agents / Developer Tools | Non-engineering task completion takes Agents; coding-specific harnesses/IDE/SDK tools go to Developer Tools. | PASS |
| Agents / Frontier | Acting agent/assistant products versus architecture or benchmark coverage without that behavior. | PASS |
| Industry / Frontier | Market, financial and usage dynamics versus technical model evaluation; Frontier excludes general AI business news. | PASS |
| Industry / Developer Tools | Business dynamics versus coding-tool usage and IDE/SDK workflow steps. | PASS |
| Industry / Security | External government policy has Industry priority; technical safety/defenses go to Security. | PASS |
| Media / Frontier | Artifact-centered releases have Media priority; specified technical releases without a finished artifact go to Frontier. | PASS for those named cases |
| Media / Developer Tools and Security | Creative output versus the coding workflow or technical safety mechanism. | PASS |
| News / AI parent and children | Incident-centered reporting has News priority; product/model/business subjects return to AI shelves. | PASS |
| New AI children / AI parent | A narrower child requires its own subject; generic AI features may stay at the parent. | PASS |
| Each new node / Education, Space and Science, Spaceflight | Teaching ML, empirical scientific inquiry and real flight/mission operations retain their v1 scopes. A product, market claim, fictional artifact or incident alone does not establish those subjects. | PASS |

B5 uses the same nine repair/redistribution/control seeds and recalculates first/middle/last in ledger order for every populated shelf. It also retains all eight repaired rows, as the brief requires. The resulting 35-row union adds c078, c106, c134, c150, c153 and c186 to audit 11's sample. c106's business agents, c134's AI-search partnership and c153's generated procedural episode pass. This remains a sample, not semantic certification of all 225 rows.

| Populated shelf | First / middle / last |
|---|---|
| Agents | c058 / c106 / c141 |
| AI parent | c001 / c064 / c196 |
| Industry | c041 / c134 / c223 |
| Developer Tools | c150 / c186 / c208 |
| Frontier | c062 / c078 / c108 |
| Media | c033 / c104 / c153 |
| News | c006 / c010 / c019 |

B5-R3 has three reproducible cases. Each card has only one archived excerpt and one recorded disposition key; no unseen continuation or alternate excerpt resolves the destination.

| Row / key | Evidence and failing destination | Exact repair |
|---|---|---|
| c078 / c078-1 | A seven-day 90%-off promotion compares provider prices on comparable tasks. The excerpt ends at `while sti`; it establishes no capability result or benchmark. Frontier's business-news exclusion applies. | `proposed_concept`, `["ai-industry-and-business"]`; keep c078-1. |
| c150 / c150-1 | Generic ELI5 slash-command instructions name Anthropic and request an HTML explanation. No AI system, coding task, SDK, IDE or ML lesson is established. The row's reason adds Claude and an agent workflow. Neither Developer Tools nor Education is justified; company identity alone cannot justify the AI parent. | `still_unmapped`, empty shelves and evidence. |
| c186 / c186-1 | Portable Grok-bot access and switching establish an AI app. Planned animation/response tweaks do not establish a coding-specific harness; the truncated `will open-s` supplies no missing development workflow. | `existing_concept`, `["ai-and-ml"]`; keep c186-1. |

Use the three complete `B5.sample_records[].exact_proposed_replacement` objects in the new measurements as the successor's after-values. Their exact reasons are:

```text
c078: AI model price promotion and provider price comparison are market economics; not a support: five-card cap
c150: ELI5 slash-command instructions; the cited excerpt establishes neither an AI system nor a software-engineering workflow.
c186: Portable Grok-bot access and switching; no coding-specific harness, IDE, SDK or developer workflow is established.
```

Those three row replacements pass the complete proposal validator together in memory. Expected counts become **60 proposed, 31 existing, 110 unmapped, 24 unsupported**. They require no node, prompt or model change. Approval of a successor still requires review of its full document and recalculated sample; this preflight does not certify unsampled destinations.

Projection is mechanically valid for these rejected bytes. With `taxonomy_from_proposal.build()` using `approved_by="Codex / GPT-6 Astra (INDUCTION-AUDIT-12)"` and `approval_record="docs/library/INDUCTION-AUDIT-12-2026-09-06.md"`, independent nodes and validator normalization agree. The diagnostic metadata export is 12,991 UTF-8/LF bytes, SHA-256 `aec3f9d8a8adb46ca6a07552a28ab8f29fd2034259f56f3a07c6aaef1938dd20`. Its calculated service revision is `bd9e7f9d572a709a9e0f939b5433932fb36840278929946c2c6870ac0158dd97`. The compact sorted-key service document plus LF is 9,548 bytes, SHA-256 `a4b9daf4c544341ea1e6bb5458624baae294ce4849d9d17ba561273bb6f0f739`. No projected file was written or installed; `service_returned_revision_hash` remains null.

**Fable must not bind an approval record for decision 3.** For an accepted successor, the [run-W requirements](INDUCTION-AUDIT-2026-09-05.md) still require exact decision/source-receipt hashes, the resolving audit and every finding's disposition, projection algorithm/fields and file hash, an observed service-returned revision, all seven preserved IDs and parent revision, rejected concepts, measured pin impact, approver/timestamp and authorized disposable database identity. The parent revision remains `2f283053bbaca2e94c2dbd340f19c62a89f529457ac40ae5b1d2d84379d22d98`. A calculated revision cannot fill the observed-service field.

Packet 12's hash, decision binding and all candidate fields match. No worker labels were opened, no hold-out predictions were produced, and no hold-out content informed these repairs. The blind labels belong to their exact packet; retain that provenance while the successor is reviewed. Sealed adjudicated labels, mapping and the other run-W freeze requirements remain prerequisites to the measured pass.

Validation performed:

```powershell
python -B scripts/librarian/compose_revision_decision_3.py --check
python -B docs/library/proof/audit-decision-3-2026-09-06.py --decision docs/library/proof/taxonomy-v2-revision-decision-3-2026-09-06.json --output docs/library/proof/audit-decision-3-measurements-2026-09-06.json --self-test
git diff --check
```

Composer check exits 1 for C3-EOL. The audit replay exits 0 with `approval=false` and 11 mutation/normalization checks passed. Those checks cover unrecorded edits, wrong before-values/findings, missing edits, deviations from the exact audit repairs, overlong/invented quotes, foreign revision/card support and Unicode normalization. Exit 0 means the replay completed. The complete public proposal validator accepts the current proposal and repair preflight; it does not adjudicate the three destination failures.

Only this report, the new replay script and its measurements were added. All tracked files and prior measurement bytes remain unchanged. No runner, prompt, scorer or decision was edited. No model, helper, database, live index, network client or port 5179 was used. No commit or merge was made. Fable must inspect the new review code and rerun the affected replay on the collected integration SHA; Astra's own tests do not independently certify Astra-authored tooling.
