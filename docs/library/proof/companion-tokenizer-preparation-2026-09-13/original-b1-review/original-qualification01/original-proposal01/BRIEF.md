# ASR cache and tokenizer repair proposal — 2026-09-13

Prepare an inert patch against the current `whisper_runner.py`. Ordinary product
repairs are already authorized. This task applies no product change, imports no
product or staged runtime, runs no model or native library, fetches nothing,
changes no existing test, and makes no commit or push.

The current readiness predicate accepts any file under the model cache. The
runner then lets WhisperX resolve/download the ASR model inside its constructor.
Captured faster-whisper 1.2.1 constructs CTranslate2 before checking its tokenizer
and has an independent remote tokenizer fallback. Repair the ordinary product
boundary without pretending that this qualifies the held model stack.

## Constraints read before this proposal

- `docs/library/RELEASE-OWNER-DECISIONS-2026-09-12.md`: an exact model-stack
  source/dependency patch and isolated execution protocol still need Ryan's
  review; no model target or frozen compatibility-test change is approved.
- `tests/test_installer_dependency_lock.py`: faster-whisper 1.2.1, WhisperX
  3.8.6 and Torch 2.8.0 are frozen. No changes to these assertions or pins.
- `tests/test_phase6_evaluation.py:1443–1505`: preserve strict defaults
  `diarize=False`, `consent_given=False`, separate download consent, and 412
  refusal before queue/model work. Synthetic extraction of the real function
  body is already used to avoid module-level runtime probes.
- `tests/test_podcast_background_jobs.py`: preserve the exact 412 response,
  serialized jobs, durable progress and DONE transcript reuse.
- `tests/test_podcast_watch.py:1–15,205–212`: standing capture does not imply
  model-download consent; unavailable setup refuses nonterminally.
- `tests/test_packaged_decoder_loader.py`: retain the installed DLL boundary;
  do not replace its assertions or import the whole runner in new unit tests.
- `tests/test_podcast_workflow_truth.py` and the Phase 6 contract's download
  consent section: retain existing local transcription and explicit opt-in
  behavior. No silent feature removal or claim of speaker readiness.

## Proposed split

**A. Ordinary product repair, reviewable now:** keep public signatures and output
shape. Resolve the existing six model names to their current faster-whisper
repositories. Health/preflight reads only the expected Hub cache reference and
snapshot, and requires nonempty `model.bin`, `config.json` and `tokenizer.json`
under that repository's cache. Preserve normal Hub file links that remain inside
the repository cache. An arbitrary file, partial download or redirected path is
not ready. Do not claim these three checks form a complete trusted manifest.

When no structurally ready cache exists, `consent_given=False` raises before the
downloader or model constructor. With explicit consent, use the same
faster-whisper download helper and existing model scope, validate its returned
snapshot, then call WhisperX with that local snapshot and
`local_files_only=True`. Keep all six model options and the lazy-download flow.
This separates ASR acquisition from construction and catches a stably missing
tokenizer before construction. It does not fix VAD or prove artifact trust.

**B. Exact companion third-party source proposal:** move local tokenizer
construction ahead of CTranslate2 in faster-whisper 1.2.1, and reject a missing
tokenizer when `local_files_only=True`. Preserve the upstream non-local fallback
for other callers. This closes the local-only fallback itself, including a file
disappearance between checks. A product preflight alone cannot make that stronger
claim. Keep this companion separate: do not patch shared staging, silently ship
modified upstream bytes under unchanged provenance, or alter frozen tests.

No new Ryan decision is needed to implement and synthetically test A. The narrow
remaining decision for B is review of the exact faster-whisper source delta and
its derivative provenance/compatibility expectations as part of the already-held
model-stack migration. No model download, conversion, inference or target stack
approval is bundled with that choice.

## Deliverables and verification boundary

Write proposed source and new synthetic test bodies as `.txt`, unified diffs as
inert text, an input hash record, and a short verdict. New tests must extract only
named runner functions/constants, stub every download/model/device seam and use
temporary synthetic cache files. The runner module's import-time probe must not
execute. Include a real-function constructor-order test for the companion using
AST extraction and strict inert fake objects, never importing faster-whisper.

This task may parse proposed Python and patch structure as text. It must not run
the proposed tests or production functions. Later integration runs should record
real counts and commit IDs under a separate repair brief, preserve every existing
assertion, and retain remaining manifest/VAD/runtime blockers explicitly.
