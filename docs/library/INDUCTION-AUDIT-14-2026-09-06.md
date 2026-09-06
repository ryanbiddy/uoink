**APPROVE taxonomy-v2-2026-09-05 (revision decision 5).** B5-R4 is resolved. The actual decision reproduces exactly, and its full proposal and 225-row ledger match audit 13's reviewed replacement hashes. This approves the taxonomy content at integrated candidate `ce0a8ea91c7f27f581ce00a4bbaa56d61c74ce9c`. Apply stays disabled. The measured pass still requires sealed labels/mapping, a frozen stage-2 manifest and observed execution identities.

Approver: **Codex / GPT-6 Astra (INDUCTION-AUDIT-14)**, independent auditor and plan owner under [orchestration v1](ORCHESTRATION-V1-2026-09-04.md). Approval timestamp: **2026-09-06T06:01:23Z**, observed UTC; the filename follows the dispatch date. Scope: the [run AF brief](INDUCTION-APPROVAL-BRIEF-2026-09-06.md) and [audit 13's successor acceptance standard](INDUCTION-AUDIT-13-2026-09-06.md). The decision, predecessor, decision 3 and bound measurements have the same exact bytes as their Git blobs at the named candidate. This report does not certify a later execution SHA.

The [measurements](proof/audit-decision-5-measurements-2026-09-06.json) are reproducible with the [offline audit replay](proof/audit-decision-5-2026-09-06.py). Measurement SHA-256: `d80f00b34115d7ef7775429669ba876f2d33f295931468284967e41139f6b3ad`. They record the complete before/after edit inventory, input fingerprints, source bindings, preservation checks, validator results and calculated projection identities. No new semantic sample was taken: exact equality satisfies the acceptance standard after audit 13's exhaustive mapped-row review.

| Check | Observed | Required | Verdict |
|---|---|---|---|
| Composition | Composer `--check` exits 0; independent reconstruction and full UTF-8/LF serialization match the actual decision. | Exact successor, including wrapper and source bindings. | PASS |
| Measurement binding | Decision 5 binds decision 4 and the exact audit-13 measurements; those measurements bind decision 4. | No substituted predecessor or repair specification. | PASS |
| B5 repairs | 20 exact replacements: 17 destination changes and three reason-only changes, c046/c055/c089. Other 205 rows unchanged. | All and only the reviewed replacements. | PASS |
| B5 whole proposal | Both canonical hashes below match; 225 unique rows: 44 proposed, 37 existing, 120 unmapped, 24 unsupported. | Reviewed content and predicted counts. | PASS |
| B4 evidence | All 20 node supports unchanged; all 81 retained ledger references keep their original evidence. Removed mappings have empty shelf/evidence arrays. | Preserve reviewed supports and pass full evidence validation. | PASS |
| B6 preservation | Eleven nodes identical to decisions 3 and 4 as data and literal UTF-8 fragments. Rejections, pin fields and diff unchanged. Seven normalized v1 nodes preserved across all eight service fields. | No unreviewed node or preservation change. | PASS |
| Full proposal validator | Delivered decision passes schema, hierarchy, provenance, evidence and ledger checks; each addition has five distinct candidate-kind supports. | Complete validator success. | PASS |
| Source receipts | Attempts 9 and 10 each return `INDUCTION_RECEIPTS_VALID_AUDIT_REQUIRED`, 225 targets, ten calls. | Exact archived source validity. | PASS; their raw proposals remain unapproved |
| Projection | Independent eight-field projection equals the generator and public validator normalization. | Deterministic service input for this decision. | PASS; calculated only |

Canonical proposal and ledger serialization is UTF-8 JSON with sorted keys, `ensure_ascii=False`, separators `(',', ':')`, and no trailing newline. Exact-file hashes below use the files' actual bytes.

| Bound artifact | SHA-256 |
|---|---|
| [Decision 5](proof/taxonomy-v2-revision-decision-5-2026-09-06.json), exact bytes | `f01bd7c2938894211a3efc86c8e08c36f979a737542aecfa29cf45a2578f5ba7` |
| Full canonical proposal | `9863d85647c2fb8781b42993c3eec52255bd68b7bbae240393543906d96cd469` |
| Full canonical ledger | `d43012b6f70fbe6ac626e245819343a8456d733995d55845d594549b13d81f70` |
| Decision 4, predecessor | `44702821492c0e27082bafe9dec6e430cc9ce01e0194ade089a1d61a7e90d32a` |
| Audit-13 measurements, bound repair specification | `2b9ddf14fcc6d3b86638fb65f02b8ba1360c535037f7df33ce43d9d42a142748` |
| Attempt-10 source proposal | `bb3d51e4b6eecf542355ba0e5f5fbb0d09b1e0ad692eb1c5d1674f315a25cd7c` |
| Attempt-10 source receipts | `fb26d4f0a6814fc32c00cb51ea7dbc076150b775c545d90cbdc43cd1e16ee0c2` |
| Attempt-9 donor proposal | `37db6a1ee53e3ee286d32986f633bb7b12b9dfa4594a462504feb13b1a283997` |
| Attempt-9 donor receipts | `22206eafd81b4703060e6a4f578f6cdd25dd8c6183351c0687cb9b9c03fa91d9` |
| Archived stage-1 receipts, including measured pin state | `2b4e824ea9f93999de6c5108406e60a5c81f108de0b279c52fee2e96d622469c` |

The finding dispositions below are part of this approval. Earlier failed runs retain their historical findings; acceptance of the successor does not rewrite them. B1-B3 and B7-B9 retain [audit 10's findings](INDUCTION-AUDIT-10-2026-09-05.md), with source receipt validation rerun here. Semantic findings carry through the identical reviewed content.

| Finding | Disposition for this successor |
|---|---|
| B2-H, B3, B8, B9 | Accepted source lineage, prompt exclusion, archive-only isolation profile and byte validation established in audit 10. B8 retains its stated limit: no independent historical OS egress telemetry. |
| B4-R, B5-X | Node support relevance repaired by decision 2/audit 11; omission explanations passed audit 10 and remain in the reviewed proposal. |
| B6-S, B6-M, B6-P | Operative boundaries and candidate accounting accepted through audits 11-13. Explicit archived pin measurements pass again here. |
| B5-R | Audit-10 destination repairs accepted in audit 11. |
| B5-R2, B6-S-Agents-Security | Resolved in audit 12; repaired node fields remain identical. |
| B5-R3, C3-EOL | Resolved in audit 13; current composition succeeds on actual checkout bytes. |
| B5-R4 | Resolved here by all 20 exact rows and full reviewed-hash equality. No open taxonomy finding. |

Fable must bind this approval record and its final exact-file hash under the [run-W requirements](INDUCTION-AUDIT-2026-09-05.md). The fixed portion consists of the decision/source hashes above, this resolving audit and finding dispositions, the projection algorithm and hashes below, preserved IDs, parent revision, rejected concepts, measured pin impact, approver and timestamp. Preserve the immutable decision's supporting evidence, sibling cues and ledger as the approval's evidence. Operative distinctions already survive in definition/include/exclude fields.

The seven preserved IDs are `ai-and-ml`, `space-and-science`, `developer-tools`, `education`, `frontier-models`, `security`, and `spaceflight`. Added IDs are `news-and-current-events`, `ai-agents-and-automation`, `ai-industry-and-business`, and `generative-media`. Parent version is `taxonomy-v1-2026-09-04`; its revision is `2f283053bbaca2e94c2dbd340f19c62a89f529457ac40ae5b1d2d84379d22d98`.

All 21 batch candidates retain their reviewed accounting: 15 adopted/equivalent and six rejected. The rejected concepts are Political and Social Commentary; Breaking News: Crime and Conflict; Sports Highlights and Commentary; Livestreamer and Creator Culture; AI and ML / Product Launches; and Career and Entrepreneurship. Their exact reasons remain in the decision and measurements. The archived before-state records zero pins, zero memberships and zero item policies, with v1 active. The receipt agrees; the pin-impact report states zero pins/memberships, no impact items and `silent_redirects=false`. These measurements describe the archived state. The execution database must be measured separately.

Fable should generate the approved taxonomy with exactly this command, then use the same command with `--check` and rehash the output bytes. **This export command was not executed in run AF**; the audit called `build()` in memory with these exact parameters.

```powershell
python -B scripts/librarian/taxonomy_from_proposal.py --proposal docs/library/proof/taxonomy-v2-revision-decision-5-2026-09-06.json --parent docs/library/taxonomy-v1-2026-09-04.json --out docs/library/taxonomy-v2-2026-09-05.json --approved-by "Codex / GPT-6 Astra (INDUCTION-AUDIT-14)" --approval-record docs/library/INDUCTION-AUDIT-14-2026-09-06.md
```

Projection retains `shelf_id`, NFC-normalized `path`, `definition`, `include`, and `exclude`; derives `name=path[-1]` and `parent_shelf_id` from the path hierarchy; and sets `retired=false` for these nodes. It sorts by path depth, path, then shelf ID. Supporting evidence, sibling cues, ledger, diff, pin report and rejections remain in the archived decision. The revision hash is SHA-256 of the canonical normalized node array. The metadata export uses `json.dumps(..., ensure_ascii=False, indent=2)` plus one LF. Its approval metadata binds the complete decision file, including the wrapper.

| Projection identity | Calculated value |
|---|---|
| Metadata export, 12,991 UTF-8/LF bytes | `015260a496f45322609573956401139f15522d0497e45b263b7e5b8b269696e6` |
| Expected service revision | `bd9e7f9d572a709a9e0f939b5433932fb36840278929946c2c6870ac0158dd97` |
| Canonical service document plus LF, 9,548 bytes | `a4b9daf4c544341ea1e6bb5458624baae294ce4849d9d17ba561273bb6f0f739` |
| Service-returned revision | **Pending observation; null in measurements.** |

The canonical service document contains only schema version, version ID, parent version ID, normalized nodes and revision hash. It has a different serialization and field set from the metadata export. The generator's fixed `created_at` is not the approval timestamp recorded above.

Before the measured pass, Fable must bind a separate execution receipt to this approval's exact hash and fill these fields from observation. Do not replace pending observations with calculated hashes or historical identities.

| Execution field | Required observation |
|---|---|
| `service_returned_revision_hash` | Actual disposable-service approval response, request/response artifact hashes and timestamp; require equality with the expected revision above. |
| Authorized disposable database identity | Authorization, actual staged source and disposable paths, source date/hash, disposable before-state hash/size/schema, active revision and pin/membership/policy counts; isolated non-5179 endpoint and cleanup owner. Run W binds source `uoink-index-copy-2026-09-04-upgraded.db`, dated 2026-09-04, SHA-256 `2765cc359805fb12f7a90aecd3dd0b34d884aa8cb3015785011bf400da3b4dfc`, 71,733,248 bytes, original schema 25. Record the execution copy's observations separately. |
| Integrated execution SHA | Full actual Git SHA after export, adjudication and freeze, file fingerprints and acceptance results on that candidate. The current approved-content SHA cannot certify later code or conflict resolutions. Fable must independently inspect this audit's tooling. |
| Sealed labels and mapping | Separate immutable paths/hashes, original blind-label provenance, adjudicator, taxonomy/rule binding and seal timestamp/commit before execution. |
| Stage-2 manifest | Exact path `docs/library/proof/manifest-stage2-2026-09-05.json`, schema/profile version, file hash, freeze timestamp/commit and approval/execution-record bindings. |

Audit 13's packet-12 carry-forward ruling remains valid because candidate nodes and operative rules are unchanged. Preserve the original label files and packet-12 provenance; adjudication must bind their actual hashes, the equivalence ruling and this approved decision. This audit opened no labels and certifies no label quality or blind process. Run AG must seal the adjudicated labels and all 60 `strict-mapped-primary-v2` mapping decisions, including unmappable cases.

The remaining run-W execution freeze requirements continue unchanged: preserve all 548 ordered source identities, revisions, cards and bounded heads with zero exclusions; bind both exact prompt bytes and rendered-template bytes; fingerprint runner, validator, scorer, service, renderer and card builder; and keep labels/mapping out of execution inputs and egress. Record the supported installed client/model, environment assertion, egress authorization, paid-spend decision, budget, deadline, concurrency/retry/guard settings and isolation before any measured process. A taxonomy approval supplies none of those pending observations or authorizations.

Validation performed:

```powershell
python -B scripts/librarian/compose_revision_decision_n.py --base docs/library/proof/taxonomy-v2-revision-decision-4-2026-09-06.json --measurements docs/library/proof/audit-decision-4-measurements-2026-09-06.json --audit docs/library/INDUCTION-AUDIT-13-2026-09-06.md --expected-counts 44,37,120,24 --out docs/library/proof/taxonomy-v2-revision-decision-5-2026-09-06.json --check
python -B tests/validate_proof_receipts.py --receipt-kind induction --receipts docs/library/proof/induction-run-9-2026-09-05/receipts.json --require-real
python -B tests/validate_proof_receipts.py --receipt-kind induction --receipts docs/library/proof/induction-run-10-2026-09-05/receipts.json --require-real
python -B docs/library/proof/audit-decision-5-2026-09-06.py
python -B docs/library/proof/audit-decision-5-2026-09-06.py --check
git diff --check
```

All exit 0. The replay calls the full validator on the delivered decision and compares an independent projection with the generator and validator; repeated replay matches the measurement bytes. Its `--check` binds this checkout SHA and input fingerprints, so a later checkout needs its own acceptance receipt. Preserve these approval measurements. Application tests are outside this archive-only scope.

Only this report, its replay script and its measurements were added. No runner, prompt, scorer or decision was edited. No model, helper, database, live index, network client or port 5179 was used. No taxonomy export, commit or merge was made. Fable's next steps are the exact export, run-AG adjudication/sealing, stage-2 freeze and observed execution receipt.
