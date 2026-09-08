# Phase 5 brief: useful change reports before contradiction claims (2026-09-08)

Fable's dispatch under `ORCHESTRATION-V1-2026-09-04.md`, from `ASTRA-PHASE-PLAN-2026-09-04.md`
("Phase 5"). Ryan's 2026-09-07 authorization covers this phase. No worker runs a model, the
resident helper, or touches port 5179 or the live index. No paid spend. Phases 2 to 4 continue
in parallel; this run must not touch `library_work.py`, `library_cards.py`,
`source_subscriptions.py`, `library_resources.py`, the proof harness, prompts, or Phase 2/3/4
tests.

## Scope (from the phase plan, frozen here)

Phase 5 is split. **Part A (this phase):** descriptive source and shelf counts and changes
with explicit capture-date versus publication-date semantics; they need no claims. **Part B
(deferred):** term bursts only with adequate observation history, creator deduplication and
denominators; claim extraction and disagreeing sentence pairs later, as client-run work.
The measured copy has no claims, which blocks a contradiction product, not an activity
report.

What the data offers at this base, as source observations: `yoinks.yoinked_at` is the capture
time; publication time exists only where a source carries it (`podcast_episodes.published_at`,
`source_subscriptions` observations' `published_at_ms`, sidecar metadata for YouTube uploads);
`channel` and `author` are creator hints, not deduplicated identities; `library_applies`
carries every applied membership change with `operation_sequence`; `shelf_versions` and
`library_runs` carry taxonomy and projection revisions; `engagement_events` carries
per-item engagement. Deleted items have `deleted_at`. There is no report table and no
migration is reserved for Part A; if one is needed, `0029` must be named in the contract and
justified.

## Fable's reservations

1. **Base:** the commit this brief lands in.
2. **Owners:** Astra = `docs/library/PHASE5-CONTRACT-2026-09-08.md` (report definitions,
   denominators, date semantics, provenance and invalidation rules, evaluation requirements
   as gates, registry read tool and dashboard report contract) and later provenance and
   statistical review of the implementation. Gemini = `docs/library/PHASE5-EVALUATION-2026-09-08.md`:
   evaluation design and labeled counterexamples (backlog import posing as a trend; repeated
   clips and cross-posts as one creator; deleted or corrected inputs; single-source
   observations), each as a fixture the implementation must reproduce. Claude worker =
   `library_analysis.py` pure aggregation plus `index.py` query helpers, after the contract
   freezes (run AZ). Grok = `docs/library/PHASE5-COST-AUDIT-2026-09-08.md`: audit of what the
   report costs to compute and display on a 548-item library and a 10,000-item one, with the
   queries named; if Grok's session ends without output, Gemini writes it in the next run.
3. **Sequence:** this run (AY) freezes the contract, the evaluation design and the cost audit.
   Run AZ implements the module, the registry read tool and the dashboard report UI with
   tests. Run BA is Astra's review and acceptance on the integrated candidate.

## Gates (acceptance requirements, from the plan)

A backlog import cannot masquerade as a current publication trend. Repeated clips and
cross-posts do not count as independent creators. Deleted or corrected inputs invalidate
derived reports. Every displayed count and change links to its evidence and time range.
The direction's cross-creator minimum and faithfulness target are evaluation requirements,
not claims of achieved accuracy. When support is too thin, show a single-source observation
or no trend. Narration (client-run, later) must not add facts beyond the computed packet.
Deterministic detection is frozen independently of any narration client.

## codex (GPT-6 Astra): the Phase 5 contract

Write `docs/library/PHASE5-CONTRACT-2026-09-08.md` after inspecting `index.py`, the
migrations named above, `library_work.py`'s applied-journal shapes (read only), `claims.py`,
and `PHASE4-CONTRACT-2026-09-08.md`'s `whats-new` prompt (Phase 5 reports must agree with
it or supersede it explicitly). Freeze: the report set for Part A (at least: captures per
interval by source type and creator hint; shelf membership changes per interval from the
applied journal; shelf size and churn; sources with activity, with the observation window
each source actually has); the interval grammar (half-open UTC, capture time by default,
publication time only when the source carries it and labelled as such); denominators and
the history-coverage rule (no inference of old changes from today's state); creator
deduplication rules for Part A (what is and is not merged); invalidation (a deleted or
corrected input marks dependent reports stale and they recompute; nothing cached survives
a source revision change); provenance (every number carries the query, revision and
interval it came from); the read tool `get_library_activity(interval, ...)` in the shared
registry and its wire budget; the dashboard report surface (read-only, no new capability);
the evaluation requirements as gates with test names; and the exact Part B deferral. Name
every ambiguity you resolve. Do not write code. Do not commit.

## gemini: evaluation design and labeled counterexamples

Write `docs/library/PHASE5-EVALUATION-2026-09-08.md`: for each gate above, a fixture (a
small synthetic index state and the expected report) that the implementation must reproduce
exactly, including at least: a 200-item backlog import on one day versus a steady capture
rate; the same clip text captured from three cross-posts; a creator under two channel
names; a deletion after a report was computed; a correction (undo) after a report; a
single-source interval; an interval before any observation history exists. State the
faithfulness requirement for future narration as a measurable check. Do not write code.
Do not commit.

## grok: cost audit

Write `docs/library/PHASE5-COST-AUDIT-2026-09-08.md`: the queries the Part A reports need
over the tables named above, their expected cost on 548 and 10,000 items with the existing
indexes, which indexes are missing, and the display budget for the dashboard. Cite the
schema lines. Do not write code. Do not commit.
