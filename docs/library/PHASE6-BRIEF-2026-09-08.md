# Phase 6 brief: media depth where it changes retrieval (2026-09-08)

Fable's dispatch under `ORCHESTRATION-V1-2026-09-04.md`, from `ASTRA-PHASE-PLAN-2026-09-04.md`
("Phase 6"). Ryan's 2026-09-07 authorization covers this phase. No worker runs a model, a
transcription engine, the resident helper, or touches port 5179 or the live index. No paid
spend. Phases 2 to 5 continue in parallel; this run must not touch `library_work.py`,
`library_cards.py`, `source_subscriptions.py`, `library_resources.py`, `library_analysis.py`,
the proof harness, prompts, or Phase 2 to 5 tests.

## Scope (from the phase plan, frozen here)

Honest timing and bounded excerpt handling already moved into the repair increment. Phase 6
adds: chapter rows; source-local speaker labels in clips and Markdown; cited range export.
Cross-video speaker identity stays deferred until source-local labels prove useful and a
labeled evaluation set exists: a label such as `Speaker 1` is not an identity. Twitch stays
notify-only. Encrypted sync and X watching are out of scope.

Source observations at this base: `whisper_runner.py` already runs optional WhisperX
diarization and emits per-segment `speaker` labels (`SPEAKER_00`) with a `diarization_ran`
flag; `clips.py` merges cues into windows (`merge_cues`, `build_clips_for_video`,
`rebuild_all_clips`) with `timing_kind` and deep links, and carries no speaker or chapter
field; no `chapters` table or column exists in any migration; `yt_extract.py` does not read
chapter metadata. `0029` is reserved to Phase 4 if it needs it; Phase 6's migration is
`0030` and must be named in the contract.

## Fable's reservations

1. **Base:** the commit this brief lands in.
2. **Owners:** Astra (codex) = `docs/library/PHASE6-CONTRACT-2026-09-08.md`: schema
   (`0030`: chapter rows bound to item and source revision; speaker label storage on cues
   and clips as source-local labels with the run that produced them; nothing that implies
   identity), the deterministic projection from cues to clips with labels, the cited range
   export format, rebuild and re-extraction rules, and acceptance gates as tests. Gemini =
   `docs/library/PHASE6-EVALUATION-2026-09-08.md`: transcript, chapter and speaker evaluation
   design and export checks (fixtures with known chapters and known speaker turns, player
   seek and exported range equality with source timing, missing-data cases). Grok =
   `docs/library/PHASE6-ADAPTER-RESTRICTIONS-2026-09-08.md`: which sources can supply
   chapters and speaker turns at all (YouTube chapter metadata, podcast feeds, X, pages,
   notes), what each adapter may and may not fetch, and Twitch's notify-only boundary. Claude
   worker = capture and UI wiring after the contract freezes (run BC).
3. **Sequence:** this run (BB) freezes the contract, the evaluation design and the adapter
   restrictions. Run BC implements schema, projection, capture wiring, export and tests. Run
   BD is Astra's review and acceptance, including the retrieval or navigation improvement
   demonstration the plan requires before any cross-source entity resolution.

## Gates (acceptance requirements, from the plan)

Rebuild preserves labeled evidence and quote provenance. Missing chapter or speaker data is
explicit, never inferred. Re-extraction does not silently change old citations (Phase 2's
evidence ids and Phase 4's excerpt identities keep resolving or refuse with the frozen
codes). Player seeking and exported ranges match source timing. Optional diarization stays
opt-in and off by default. A retrieval or navigation improvement is demonstrated on the
measured copy before any cross-source entity work is proposed.

## codex (GPT-6 Astra): the Phase 6 contract

Write `docs/library/PHASE6-CONTRACT-2026-09-08.md` after inspecting `whisper_runner.py`,
`clips.py`, `yt_extract.py`, `podcasts.py`'s transcript path, the corpus and sidecar
writers, `migrations/0024_clips.sql` and `0026_provenance_precedence.sql`, and the Phase 2
and Phase 4 identity rules. Freeze: the `0030` DDL; chapter and speaker data shapes and
their provenance (source metadata versus diarization run versus absent); how clips carry a
source-local label without changing clip identity or Phase 2 evidence ids; the Markdown
corpus rendering of labels and chapters; the cited range export (input: item, start, end
or excerpt id; output: verbatim text with timing, source link with seek where the source
supports it, and provenance; refusal when timing is coarse); rebuild rules; the
opt-in and default-off setting for diarization; the evaluation gates as tests; and the
exact deferral of cross-video identity. Name every ambiguity you resolve. Do not write
code. Do not commit.

## gemini: evaluation design and export checks

Write `docs/library/PHASE6-EVALUATION-2026-09-08.md`: fixtures with known chapter
boundaries and known speaker turns; expected clip labels after projection; expected export
output for timed, coarse and text-only items; player seek versus exported range equality
checks; missing-data cases (no chapters, diarization off, diarization ran with one
speaker); and the measurable retrieval or navigation improvement the plan requires,
defined before implementation. Do not write code. Do not commit.

## grok: adapter restrictions

Write `docs/library/PHASE6-ADAPTER-RESTRICTIONS-2026-09-08.md`: per source type, whether
chapters and speaker turns exist at the source, what the adapter may fetch to obtain them
under the existing allow-lists, what it must not fetch, and the Twitch notify-only
boundary with its authorization and delivery unknowns. Cite the adapter file and line for
each restriction. Write the file early and refine it; a session that ends without the file
is a failed run. Do not write code. Do not commit.
