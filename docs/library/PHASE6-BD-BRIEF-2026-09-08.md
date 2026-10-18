# Phase 6 acceptance brief (run BD, 2026-09-08)

Fable's dispatch under `ORCHESTRATION-V1-2026-09-04.md`. Reviewer: Astra (codex). Contract
`phase6-v1` ([PHASE6-CONTRACT-2026-09-08.md](PHASE6-CONTRACT-2026-09-08.md)) as amended in
[PHASE6-BD0-2026-09-08.md](PHASE6-BD0-2026-09-08.md) (migration 0030 with `IF NOT EXISTS`).
Candidate: the commit this brief lands in, on `cc/living-library`, which contains BC-1
(`library_media.py`, 0030, `export_cited_range`, your 19 tests) and BC-2 (`fd1825c`: the
seven BD-0 rulings and the inspection items; the worker's own `tests/test_phase6_bc2.py`,
11 tests, with two integrator fixes to those tests recorded in the commit message).

## Part 1: acceptance on the integrated candidate

Rule on each BD-0 ruling (1-7) and each "Further BC-2 requirements from inspection"
item against the code. Run:

- `python -B -m pytest -q -p no:cacheprovider tests/test_phase6_evaluation.py tests/test_phase6_bc2.py`
- `python -B -m pytest -q -p no:cacheprovider tests/test_c01_mcp_stdio.py tests/test_phase4_stdio.py tests/test_stdio_clip_tools.py tests/test_phase0_registry_capture.py tests/test_docs_live_contracts.py tests/test_library_adapters.py tests/test_podcast_corpus_bridge.py tests/test_clips.py tests/test_library_resources.py`
- the Phase 3 suites with `PHASE3_REQUIRE_IMPLEMENTATION=1` (the podcast publication path changed shape; `tests/library_work_astra/test_phase3_*.py`)

Two shape changes the worker flagged for your ruling: the podcast Markdown transcript
section is now the shared renderer's output, and a YouTube corpus with held captions or
chapters uses the shared `## Chapters` + `## Transcript` block instead of the legacy
`### Chapter:` grouping. Rule whether either breaks a contract or a consumer.

## Part 2: the measured navigation study (contract, "Freeze the mandatory study")

Inputs prepared by Fable, sealed before any annotation:
`docs/library/proof/bd-study-2026-09-08/` (`README.md`, `study-inputs-manifest.json`,
`SHA256SUMS`, `items/<video_id>/chapters.json`, `items/<video_id>/clips-pre-phase6.json`).

- Candidate SHA and the read-only measured index copy's hash are in the manifest.
- 35 items hold at least two real source chapters; 25 are in the measured copy with at
  least one pre-Phase 6 clip and are eligible (the rule is in the manifest). One video id
  appears under two corpus paths; treat it as one item.
- Allowed artifacts: the extracted chapter/identity fields (with the held `metadata.json`
  hash recorded inside each file) and the unchanged pre-Phase 6 clip rows. No media, no
  transcripts, no caption tables. No fetch of any kind is authorized (Ryan's gate).
- You are the independent annotator (independent of the BC workers): before running any
  Phase 6 code on these items, select at least ten eligible items and 50 chapter-start
  navigation targets (at most five per item), record target chapter, source start and the
  acceptable interval, hash the task manifest, and record the pre-Phase 6 clip output hash
  per item from the manifest.
- Then compute baseline (existing containing clip's seek start, gap rule as frozen) and
  Phase 6 (source chapter seek start via `library_media.chapters_from_metadata` and the
  publication path on a disposable copy of the measured index; rebind every path inside
  your worktree's scratch directory), pair the absolute errors, and report per-item and
  aggregate values with the exact arithmetic. Every frozen task stays in the denominator.
- The "real supported-player observation" the contract requires: state precisely what
  observation would satisfy it (for example one YouTube deep link with the Phase 6 seek
  start opened in a browser) so Fable can execute it in Chrome once; do not open external
  URLs yourself.
- Speaker gate (step 4): the measured copy holds no diarization run output and no human
  annotations; report the gate blocked with what Ryan would need to supply, not as
  passed or failed.
- Diagnostics (step 5) only if cheap; record denominators and selection.

## Output

`docs/library/PHASE6-BD-2026-09-08.md` (verdict, per-ruling dispositions, the study's task
manifest hash, raw results and arithmetic, gate outcomes, what remains) and reproductions in
`tests/library_work_astra/test_phase6_bd_acceptance.py` for open items. Study artifacts
under `docs/library/proof/bd-study-2026-09-08/astra/` (task manifest, raw results,
SHA256SUMS). Do not edit implementation, existing tests or Fable's sealed inputs. No models,
no resident helper, no port 5179, no live index, no `ANTHROPIC_API_KEY`. Do not commit.
