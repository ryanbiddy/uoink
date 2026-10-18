# Phase 2 stage 4 build brief (run AP, 2026-09-07)

Fable's dispatch under `ORCHESTRATION-V1-2026-09-04.md`. The specification is Astra's
[stage 4 sketch](PHASE2-STAGE4-SKETCH-2026-09-07.md); the stage 3 audit is
[STAGE3-AUDIT-2026-09-07.md](STAGE3-AUDIT-2026-09-07.md) (P2-7 FAIL; guard rule v2 admitted with
AO-G1 outstanding). Base: the commit this brief lands in. Ryan's 2026-09-07 authorization
covers stage 4 (subscription execution, `claude-opus-5`). Apply stays disabled. Nobody runs a
model, the resident helper, or touches port 5179 or the live index. Do not commit; Fable
integrates in dependency order and runs every test.

## Fable's reservations

1. Card contract v2 keeps the librarian limits (six excerpts, 240 characters, 8,192 bytes)
   and reserves one slot for the bounded original-prose excerpt of prose-eligible sources
   (`page`, `x_article`, `x_thread`, `reddit_thread`, `note`) whenever prose exists, with up
   to five timed excerpts chosen by the existing spread rule; `SELECTION_VERSION` becomes
   `spread-longest-v2`. The sketch's ordering, tie, truncation and byte-pressure rules apply;
   a card that cannot fit both kinds fails the freeze with its identity named.
2. Taxonomy v3, the stage 3 run 2 prompt, hold-out v3 identities and the strict rule are
   unchanged. New label sessions for all 60 rows (excerpt-only subject rule). No packet,
   label or execution artifact from stages 1 to 3 is modified.
3. Execution variables: `claude-opus-5`, default effort, batch 8, concurrency 4, guard rule
   v2 with anonymous events (AO-G1), two-hour wall budget, a 16-item real probe through the
   validator's partial API before the full pass.
4. Owners this run: Gemini = `library_cards.py` and `tests/test_library_cards*.py`. Grok =
   `scripts/librarian/proof_run.py`, `scripts/librarian/stage2_execution_record.py`,
   `tests/test_proof_run.py`. Astra = `tests/validate_proof_receipts.py`,
   `tests/library_work_astra/**`, `docs/library/STAGE4-GATE-2026-09-07.md`, the stage 4
   binding specification. Claude worker = Phase 3 legacy-suite alignment (below). Fable =
   packet/seal adapters, scorer bindings, `library_work.py` policy read if needed, integration.
5. File naming per the sketch: `proof/manifest-stage4-<date>.json`,
   `proof/holdout-v3-stage4-bindings-<date>.json`,
   `proof/holdout-v3-stage4-labelling-packet-<date>.json`,
   `proof/card-contract-v2-diff-<date>.json`.

## gemini: card contract v2

Implement the sketch's "Card contract v2" section in `library_cards.py`: prose excerpt for
prose-eligible sources even when clips exist; reserved slot; deterministic timed selection
(up to five) with disclosed displacement; unchanged excerpt-id derivation for identical
source excerpts; byte accounting that drops optional hints before evidence and protects the
reserved prose slot; a freeze-time failure signal when mixed evidence cannot fit; unchanged
`source_revision` inputs (verify with a test that old and new builders produce the same
source revision for the same row); `SELECTION_VERSION = "spread-longest-v2"` with the full
profile untouched in behaviour except the version string. Add a deterministic diff helper
that, given old and new cards for one identity, classifies the change as metadata-only,
added prose, displaced timed excerpt, truncation change, or other. Tests: `tests/test_library_cards_v2.py`
with synthetic cards for every rule in the sketch, plus a replay over the archived stage 1
cards (from `docs/library/proof/run-2026-09-05/receipts.json` packet cards; no database).
Do not edit any other file.

## grok: runner stage 4 profile and AO-G1

In `scripts/librarian/proof_run.py`: AO-G1 (count anonymous transport events once, with
timestamp and unique-event checks, integer comparisons), the abort path must retain all
attempt rows including in-flight work (run 1's 28 completion rows without attempts is the
regression case), read the frozen card profile/selection version from the manifest instead
of hard-coding `spread-longest-v1`, record the guard rule identifier and parameters in the
receipts, and accept `--model claude-opus-5`. In `scripts/librarian/stage2_execution_record.py`:
a `--stage 4` entry with the sketch's identities (bindings file, diff ledger, profile,
guard rule, model, probe receipt). Tests in `tests/test_proof_run.py`: the sketch's guard
cases (exact 10%, first excess, linked duplication, multiple events on one attempt, later
successful submit after a transport failure, anonymous events, events on unfinished
attempts, interleaved batches, post-abort cleanup). Do not edit any other file.

## codex (GPT-6 Astra): validator stage 4 route, bindings, gate

Implement `--stage4` in `tests/validate_proof_receipts.py` per the sketch: stage-specific
card checks (stages 2/3 keep exact historical equality; stage 4 keeps source, ordered ids,
source revisions and raw heads and validates every card against the v2 profile), the
hold-out v3 stage 4 binding file (`holdout-v3-stage4-bindings-<date>.json`: id, original
stratum, source revision, old and new card hash; bind the original v3 freeze hash),
validation of packet cards, label and mapping references and strata, rejection of mixed
selection versions and stale hashes, an explicit probe entry point returning
`whole_manifest_checked=false`, and negative tests proving a probe cannot establish P2-7.
Write `docs/library/STAGE4-GATE-2026-09-07.md` (same table as stage 3 with the unchanged
denominators, the identities, the declared variables, the "Before execution" list). Your
tests under `tests/library_work_astra/`. Do not edit runner, cards, prompt, scorer, or any
archived artifact.

## claude (Fable 5.1 worker): Phase 3 legacy-suite alignment

Separate work, same base. The Phase 3 integration commit `560c062` left thirteen legacy
tests red because they encode pre-contract semantics: `tests/test_podcast_watch.py` (4),
`tests/test_auto_uoink_poll.py` (3), `tests/test_phase0_podcast_repair.py` (4),
`tests/test_quiet_notifications.py` (1), `tests/test_library_adapters.py` already adjusted.
Rewrite each to assert the contract semantics (`PHASE3-CONTRACT-2026-09-07.md`: no capture
from detection; `add_feed` projects an off source; the daily cap from the ledger; cutover
hold; taste scan records discovery without enqueue), keeping every Phase 0 protection that
still applies (backlog bounds, quiet notifications, liveness). Where a legacy test's
purpose no longer exists, delete it and say why in your final message. You cannot run a
shell: keep changes minimal and list the exact pytest command. Do not edit non-test files.
