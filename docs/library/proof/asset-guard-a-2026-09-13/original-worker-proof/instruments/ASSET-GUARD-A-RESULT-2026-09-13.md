# Asset guard A result — 2026-09-13

Product patch A and its eleven synthetic contracts pass in the isolated worktree
at detached base `4067de31e0ab3f0d1c1377b60c8a3db1fa6c76ed`. The only product
changes are `whisper_runner.py` and new
`tests/test_whisper_cache_consent.py`. No existing test, dependency pin, shared
staging file or companion B source was changed. No commit or push was made.

| Run | Scope | Actual result |
| --- | --- | --- |
| agw01 | New synthetic cache/consent file | 11 passed; 13 subtests passed; zero failures/errors/skips; pytest/verifier/launcher exit 0. |
| agw02 | New file plus all seven parent-named existing suites | 144 passed; 13 subtests passed; zero failures/errors/skips; 30 datetime.utcnow deprecation warnings; pytest/verifier/launcher exit 0. |

JUnit counts include the subtest entries: 24 for agw01 and 157 for agw02. These
are not additional independent top-level tests. The union includes Phase 6,
podcast background/watch/workflow truth, library adapters, packaged decoder
loader and installer dependency lock. It is not a complete-tree run.

The new test file's entire ProductGuardContracts class and its two helpers have
unchanged ASTs from the reviewed proposal. Setup changes are confined to a
worktree-derived source path, removal of the companion/CLI code and unused
imports, and a scope docstring. `agw-test-extraction.json` records all eleven
method names, hashes and exact adaptation differences.

Both runs used the declared heavy-import blocker before collection. No heavy
package was already loaded. agw01 made no heavy-import attempt; agw02 blocked
two WhisperX import attempts, allowing the existing runner's unavailable-runtime
branch. The guard remained installed through each session. Existing tests used
their own mocks, including inert DLL registration. No fake runner replaced the
product module, and no model, decoder, download, inference or diarization was
executed. These results provide no native/model qualification credit.

The source and instrument hashes recorded before each launch were unchanged
afterward. The sealed original 24-payload proposal was verified before extraction
and remains unchanged. `git diff --check` passed. There were no failed runs or
fixture corrections in this implementation.

Post-change source SHA-256:
`6586d9f19fea0d20054d6e317b48b9914904e1126bbc7b788ba255633251996f`.
New test SHA-256:
`5a8f90dae1f4d711b8f3beab888afb15f8cbfd8611c632fae897288b5455c448`.

Independent integration still needs to apply both files, repeat the same
declared verification in the checkout, and record its own commit. Structural
cache readiness does not close the immutable asset manifest, tokenizer fallback
companion, unrestricted default VAD or model-stack qualification blockers.

Receipts are under `_scratch/agw01`, `_scratch/agw01-launch`, `_scratch/agw02`
and `_scratch/agw02-launch`. The frozen proof copy includes only named
instruments, source files and run receipts; temporary test profiles and their
generated tokens/databases are excluded.
