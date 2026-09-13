# Asset guard A implementation and synthetic verification — 2026-09-13

Base: detached `4067de31e0ab3f0d1c1377b60c8a3db1fa6c76ed` in
`E:\AI\projects\uoink\worktrees\asset-guard-a`. Apply only the previously
reviewed product-A patch to `whisper_runner.py`. Input hash is
`71bd744fd4bc4f44243a2642a918958426dd21f0c06d341cc2c758cb27ce1ef5`;
patch hash is
`76ee9deca5530370ffaf856a5bd3cc72c22186f151a1cf4e91fcdb3c9eb1d8c0`.
The sealed 24-file proposal in the root checkout stays unchanged.

Add `tests/test_whisper_cache_consent.py` by extracting only the eleven
ProductGuardContracts and their runner AST helper. Preserve all assertion bodies.
Replace CLI source selection with the worktree runner path; remove companion B,
its imports and its constructor-prefix execution entirely. Record an AST
comparison of each original and extracted test method and every setup change.
The new tests execute selected pure runner function bodies with fake
WhisperX/download/device seams; they never import the runner module or an actual
WhisperX/faster-whisper/Torch/native runtime. Files are synthetic local placeholders.

Use the existing root-checkout `_scratch/integrator_verify.py` and
`_scratch/ig-native/Scripts/python.exe`, with new labels `agw01` and `agw02`.
Scrub provider keys/tokens by environment-variable name without printing values.
Keep the literal forbidden live-index path in `IG_FORBIDDEN_LIVE`, set offline
flags, and retain real command exits, logs and JUnit counts. First run only the
eleven-case new file under `agw01`.

The proposed `agw02` union is the new file plus Phase 6 evaluation, podcast
background/watch/workflow-truth, library adapters, packaged decoder loader and
installer dependency lock. Preflight found that the existing podcast/library
tests import server and therefore the actual runner module; the packaged decoder
test executes copied runner source. The existing verifier does not prohibit
heavy imports. Do not run this union until that conflicts-with-no-runner-import
boundary is resolved by the parent. Do not alter existing tests or substitute a
fake runner to claim those original suites ran unchanged.

On a failure, preserve it and write a precise product/instrument repair brief
before any rerun. No companion B, shared staging, pins, existing tests, full
tree, model/native execution, model downloads, diarization, installed UI,
website/marketing, credentials, commit or push. Freeze the worktree after the
results for independent integration review. Structural ASR readiness does not
close artifact-manifest, default-VAD or model-stack qualification blockers.
