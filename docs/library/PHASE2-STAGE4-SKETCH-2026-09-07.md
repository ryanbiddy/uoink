Stage 4 should repair the evidence-card asymmetry, use `claude-opus-5` at default
effort, and retain **coverage >=0.80 and strict primary precision >=0.90 in each
stratum**. Freeze the repaired cards and relabel the same 60 v3 identities before
the 16-item execution probe and full 548-item pass. The [stage 3 audit](STAGE3-AUDIT-2026-09-07.md)
records P2-7 FAIL and the guard repair that must precede either execution.

Plan owner: Astra. Integrator and dispatch owner: Fable, under
[orchestration v1](ORCHESTRATION-V1-2026-09-04.md). Base inspected in AO:
`b9d8c0937b8c50c964aa76b05dea79c04c43f473`. Ryan's September 7 authorization
covers stage 4. Fable should proceed through these preparation and review gates
under that authorization; this sketch does not request it again. AO runs no
model or helper and implements none of the proposed product changes.
`librarian_apply_enabled=false` throughout. Paid API spend, activation and main
merge remain separate Ryan decisions.

The archive supports a specific repair hypothesis. Nine timed non-assignments
have eligible original prose beside thin or irrelevant clips. Seven are
mappable in the sealed gold; two are unmappable. The tenth timed non-assignment
is a video rejected twice for overlong secondary quotes. The fourteen wrong
primaries include one unmappable over-assignment. Adding prose cannot be assumed
to fix all these cases. The old cards expose 96 eligible timed cards with
nonempty prose hints, including 21 v3 cards; the actual changed-content count
must come from the new builder replay.

| Freeze surface | Stage 4 decision | Required receipt |
|---|---|---|
| Source and targets | Same named September 4 copy, SHA-256 `2765cc359805fb12f7a90aecd3dd0b34d884aa8cb3015785011bf400da3b4dfc`; same ordered 548 IDs and source revisions; zero exclusions | Original/duplicate hashes and schemas; exact ordered source manifest |
| Bounded heads | Same stage 1 raw heads, at most 8,192 bytes per item; no corpus refetch | Exact per-head bytes/hashes and unchanged aggregate identity |
| Taxonomy | Approved v3, revision `8a1b16033eb4d6acd57c91c6a5d5e7f2af6d6f60f3adef92502b62d81ba28d04`; retain v1 -> v2 -> v3 lineage | Approved file, decision, audit 16 and service-returned revision hashes |
| Prompt | Exact stage 3 run 2 assignment template: file SHA `cd22a3c1819f693bc921033847e21b18dfac6bbac138da6162af3a0244d12f32`, text-mode SHA `e4ff00598d1e58ab436d1ca31796b67776e261535849fb52d70a59d9ca413aa9` | File and rendered-template hashes; no new examples or tuning |
| Cards | Card contract v2, new selection version, same librarian limits: six excerpts, 240 characters each, 8,192 UTF-8 bytes including wrapper | Complete new card/profile hashes and per-item old/new diff ledger |
| Evaluation identities | Original v3 IDs and original 47 timed / 13 text-only strata, unchanged | Separate stage 4 binding file linked to immutable v3 identity freeze |
| Labels / scoring | New packet and labels under the same excerpt-only subject rule as assignment; `strict-mapped-primary-v2` unchanged | Two original label files, independent review, adjudication, gold and 60 mapping decisions sealed before execution |
| Assignment execution | Subscription `claude-opus-5`; default effort; batch 8, concurrency 4, at most one reasoning retry | Installed client identity, exact argv, declared/default effort, resolved model usage and subscription environment |
| Guard / budget | Amended v2: distinct failed completed attempts plus anonymous events; strict >10% after N>=20; full pass <=7,200,000 ms | Rule identifier and parameters in manifest, execution record and receipts; runner/validator parity probes |

Card contract v2 belongs in the pure `library_cards.py` builder. For
`page`, `x_article`, `x_thread`, `reddit_thread` and `note` with nonempty original
opening prose, emit its bounded `text_only` excerpt even when clips exist.
Use the same hashed source inputs and original-prose extraction; do not promote
a title, description, generated summary or video-origin prose into admissible
evidence. Text excerpts have null start/end and `not_timed` timing. Quotes still
need one matching excerpt and the 1-to-24-word NFC/whitespace rule.

For the measured librarian profile, reserve one of the six slots for prose and
choose up to five timed excerpts by a frozen deterministic rule. Preserve a
timed excerpt on previously timed evaluation cards. Use the existing excerpt-ID
derivation for identical source excerpts; disclose when selecting five instead
of six changes which timed excerpts survive. Specify ordering, ties, truncation
flags and byte accounting before inspecting stage 4 predictions. Remove
optional hints before evidence under byte pressure, and protect the reserved
prose slot. If the promised mixed evidence cannot fit, fail the freeze with the
affected identities; do not silently discard prose or move a hold-out row to
another stratum. Smaller explicit limits and the full-card profile need
deterministic compatibility tests too.

One hash consequence must be explicit: `selection_version` is inside each
hashed card. A global version bump changes **all 548 card hashes**, even where
the visible content stays the same. Separate metadata-only changes from added,
removed or truncated evidence in the diff ledger. Do not predict that only the
96 mixed-content candidates get new hashes. Source revisions should remain
unchanged because their inputs already include the original clips and prose;
any source-revision difference is a freeze failure to investigate.

Create new files, with their actual freeze date, following these names:
`proof/manifest-stage4-<date>.json`,
`proof/holdout-v3-stage4-bindings-<date>.json`,
`proof/holdout-v3-stage4-labelling-packet-<date>.json`,
`proof/card-contract-v2-diff-<date>.json`, and separate stage 4 label, gold,
mapping and execution records. Every binding row carries the unchanged ID,
original stratum, source revision, old card hash and new card hash. Bind the
original v3 file hash and the new manifest/profile hashes. Leave all stage 1,
stage 2, stage 3 and aborted-run artifacts untouched.

**Relabel all 60 rows. Do not carry the sealed v3 labels forward as stage 4 gold.**
The former labellers could use up to 600 characters of eligible original prose
in `summary_hint` to determine a subject, then quote an incidental clip. New
cards add only a bounded 240-character prose excerpt and may displace timed
evidence. Byte trimming may also change visible content. Neither admissible
evidence nor the whole subject context is equivalent by construction.

Give both labellers exactly the new packet and unchanged taxonomy/rules, with
no predictions, old labels, outcomes, score tables or prior rationales. They
must determine the subject from admissible `excerpts`, just as the unchanged
assignment prompt requires. `summary_hint`, title and channel supply no
independent shelf justification. Require a supporting quote from one of those
excerpts, all 60 identities exactly once, and retain unsupported/unmappable
cases in the denominators. Preserve disagreements and adjudication reasons;
seal file hashes and timestamps before the probe. Record each reviewer's prior
v3 exposure. These identities have already informed the repair, so stage 4 is a
reused evaluation set, even with fresh label sessions. It cannot establish an
unseen-data generalization result.

Fable should reserve one owner per file in the next dispatch, on a named base.
The following allocation is proposed; no worker is dispatched by this document.

| Owner | Files / work | Independent acceptance |
|---|---|---|
| Gemini | `library_cards.py` and focused card tests; deterministic prose reservation, budgets, hash and provenance behavior | Astra reviews full corpus diff and synthetic edge cases |
| Grok | `scripts/librarian/proof_run.py`, `scripts/librarian/stage2_execution_record.py` and runner tests; stage 4 profile/model variables, AO-G1 guard repair, execution identity capture and abort receipts | Astra replays synthetic failure traces and reviews the integrated runner |
| Astra | `tests/validate_proof_receipts.py`, focused stage 4 validator tests, identity re-binding specification, gate and freeze artifacts | Fable independently reviews Astra's implementation and freeze; Astra's own tests cannot be its only certification |
| Fable | Label-packet/sealing adapters, `scripts/librarian/proof_score.py` only where stage 4 bindings require it, integration and immutable archive collection | Astra checks score/refusal parity; strict scoring logic and prompt remain fixed |
| Gemini and Grok, separate label sessions | Original stage 4 label files, each with allowed-input list and exposure declaration | Astra adjudicates from the common packet; Fable verifies and seals the result before execution |
| Fable | Pre-execution observation, isolated probe/full pass, cleanup, result document and Ryan-facing decisions | Astra performs final C1-C4 audit on the integrated execution candidate |

No migration is reserved. The existing service reads
`library_cards.SELECTION_VERSION` into its policy. Runner policy constructors
and validator checks still hard-code `spread-longest-v1`; they must read a
validated, frozen profile for stage 4 while retaining stage 1-3 compatibility.
Fable must reserve any necessary `library_work.py` change separately; no broad
service edit is implied here. Scorer and packet/sealing adapters may learn the
new artifact bindings, but cannot change the strict rule or select a favorable gold file.

Astra's validator work must add `--stage4` and a separate stage 4 manifest route.
Replace the blanket `stage >= 2` requirement that cards equal stage 1 with
stage-specific checks: stages 2/3 retain exact historical card equality; stage 4
retains source, ordered identities, source revisions and raw heads, then checks
every new card against the v2 profile. Do not weaken historical validation to
admit stage 4 cards. Validate both sides of each hold-out binding, every packet
card, all label/mapping references and original stratum membership. Reject mixed
selection versions, stale card hashes, wrong source revisions, substitutions,
duplicates, omitted IDs, changed heads, wrong taxonomy/prompt and changed strata.

The existing partial API is
`validate_receipts(..., require_real=True, require_whole_manifest=False)`.
It still requires a completed run and all original artifacts. It is not an
aborted-receipt waiver, and the current CLI exposes no partial switch. Add an
explicit probe entry point using that API; return `whole_manifest_checked=false`
and a probe-only result. Full acceptance and the scorer must keep
`require_whole_manifest=True` and refuse probe or aborted receipts. Include
negative tests proving that a 16-item success cannot establish P2-7.

Repair AO-G1 by including anonymous transport events once, with timestamp and
unique-event checks. Use integer threshold comparisons in runner and validator.
Test exact 10%, first excess, linked rejection/event duplication, multiple events
on one attempt, eventual successful submissions after transport failure,
anonymous events, events on unfinished attempts, interleaved batches and
post-abort cleanup. Keep all real process, attempt and exchange rows, including
late in-flight work; run 1's 28 completion rows without retained attempts are a
specific abort-archive regression case. Preserve failed runs, including their
incomplete artifacts when cleanup itself fails, without labelling them valid.

The runner must capture Git SHA, dirty status and code/prompt fingerprints
before the first model process, then capture them again at finish. Execution-code
drift invalidates the affected measurement. Separate launch SHA from archive-time
SHA, and explicitly reconcile harmless document-only additions. Include the
supplementary log in the new checksum inventory. Record the installed client's
version/executable hash and supported model identifier without silently falling
back to another model. For default effort, record `effort: null` (meaning CLI
default) and no `--effort` flag, plus the client version defining that default.
`ANTHROPIC_API_KEY` must be unset; tools and session persistence disabled. Keep
top-level usage, per-model usage, estimates and invoice-backed cost separate.

| Gate, in order | Required evidence before proceeding |
|---|---|
| 1. Offline implementation review | Integrated SHA; card/hash/budget/provenance tests; guard/abort probes; stage 1-3 compatibility; independent review of Astra's validator changes; no model/helper needed |
| 2. Freeze and label seal | All 548 v2 cards rebuilt from staged source and archived heads; old/new diff ledger; exact v3 re-binding; both label files and adjudication; all 60 mappings; fresh feasibility report and no changed denominators |
| 3. Execution observation | Authorized copy staged within the execution worktree, writable duplicate, hash/schema/state observations, approved v3 service revision, installed subscription client/model, endpoint other than 5179, cleanup owner, apply disabled and preview refusal |
| 4. Sixteen-item real probe | Fixed IDs from development data, full original artifacts, completed probe, partial real validation and independent review; preserve any failure |
| 5. Full measured pass | All 548 targets on a fresh disposable duplicate, one frozen candidate/prompt/taxonomy/profile/model configuration, original receipts and full real validation |
| 6. Independent audit | Astra C1-C4 replay of the actual full archive, per-stratum strict gate, evidence on all accepted memberships, state invariants and development diagnostics; Fable publishes the result |

For the probe, select 16 distinct IDs from the existing 225 development
identities, excluding v3. Freeze the IDs and deterministic selection rule before
execution: eight timed (including eligible prose-plus-clip cards and video-origin
controls) and eight text-only. If that allocation cannot be populated, resolve
it in the dispatch before any model call. Do not choose probe rows from v3 errors
or replace hard probe rows. Two batches of eight at the declared configuration
are sufficient for a plumbing check; they do not demonstrate peak concurrency
four. Synthetic tests cover that limit.

Give the probe a separately recorded 900,000 ms wall budget, batch 8 and
concurrency cap 4, with at most one retry per item and the same guard. Require
all 16 terminal outcomes, zero rejected/errored completions or transport
failures, valid evidence on every accepted membership, correct identity and
unchanged state. Legitimate unmapped/unsupported outcomes do not fail this
plumbing gate. With 16 first attempts, the N>=20 error guard is not reached;
the zero-failure probe criterion is therefore explicit. Partial validation alone
cannot certify guard activation or classifier quality.

On a clean probe, proceed to the full pass without changing any frozen inputs.
Start a new run and fresh disposable database. All 548 targets, including those
16 development rows, receive full-pass attempts; never splice probe results
into the scored archive. A failed probe is preserved and routed to its owner.
A documented repair needs a new candidate/freeze and reviewed probe before the
full run; it is not a silent restart. Never tune taxonomy, prompt or hold-out
identity selection from probe or stage 4 predictions.

The full audit must reconstruct every stdin, reconcile raw outputs, counters,
HTTP exchanges, registry and database snapshots, and independently replay each
guard boundary. It must validate primaries and secondaries, preserve client
errors separately from original replies, and distinguish dispositions from
terminal service states. Publish coverage and strict precision per fixed stratum,
exact/descendant diagnostics, unmappable over-assignment and sibling errors.
Retain historical old60, v2 and v3 scores under their original freezes. Publish
current outcomes on old60, v2 and all 225 development identities with overlaps
disclosed. When card or gold content changes, show paired differences and label
changes; do not attribute a score change solely to Opus or solely to the cards.
Installed-client, apply/recovery and standing-capture acceptance remain separate.

**Recommendation to Ryan: retain 0.90 for stage 4.** The verified original-label
scores are Grok 42/46 timed and 7/11 text-only; Gemini 39/47 and 9/11. Only
Grok's timed score reaches 0.90. These are comparisons against gold adjudicated
from the same labels, under a broader evidence allowance than assignment, so
they establish neither an independent reader ceiling nor a lower acceptable
precision target. With just 11 text assignments, 9 correct is 0.818 and 10
correct is 0.909; one decision crosses the gate.

The current gold contains 45 mapped timed items and 11 mapped text-only items.
Both strata can mathematically meet the existing coverage and precision gate;
that is a feasibility observation, not proof that the bounded v2 cards suffice.
At minimum coverage, stage 4 still needs 38/47 timed assignments with at least
35 correct, and 11/13 text-only assignments with at least 10 correct. At larger
assignment counts require `correct >= ceil(0.90 * assigned)` separately. Every
unsupported or unmappable selected item stays in N.

A different target would need an independent review under the identical v2
evidence rule, stable label reliability by stratum, documented irreducible
ambiguities and Ryan's explicit acceptance of the resulting false-assignment
rate. Seal any new target before its measured pass. A low observed model score,
a two-labeller disagreement count, or post-result threshold adjustment is not
that evidence. If new labels expose a feasibility conflict, preserve the fixed
identities and put the concrete conflict and options to Ryan; do not drop rows
or loosen the rule in the scorer.
