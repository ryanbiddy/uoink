# Asset guard A — integration verdict, 2026-09-13

**The ordinary ASR cache/consent repair passed independent worker and checkout
qualification.** Random or incomplete cache contents no longer bypass download
consent. The runner resolves and checks a local ASR snapshot before construction,
then passes its local path with `local_files_only=True`. All six model choices,
the existing consented download flow and transcript shape remain available.

| Observation | Worker agv01 | Checkout agc01 |
| --- | --- | --- |
| Passed cases | 144 | 144 |
| Passed subtests | 13 | 13 |
| Failures / errors / skips | 0 / 0 / 0 | 0 / 0 / 0 |
| JUnit `tests` attribute / actual testcase elements | 157 / 144 | 157 / 144 |
| Elapsed pytest time | 9.97 s | 9.85 s |

Both independent runs used `--runxfail`, had matching case IDs, and returned
zero from pytest and the verifier. Each reported 30 existing datetime.utcnow
deprecation warnings. Inputs stayed unchanged during each run. The shared
heavy-import guard had no preloaded runtime packages, blocked two WhisperX
import attempts, and remained installed through session completion. Existing
tests kept their own stubs; no fake runner replaced product code.

The selected union covers the new eleven cache tests, Phase 6, podcast
background/watch/workflow truth, library adapters, packaged decoder loader and
installer dependency lock. These are synthetic and regression results, not a
complete-tree, installed-native, model-quality or release acceptance result.
Original worker agw01/agw02 results remain archived separately with their
11+13 and 144+13 counts; they did not include `--runxfail` and reported no xfail.

The parent integrated the raw worker diff with `git apply --3way` from checkout
base `0cedaa68fde378546d0389fcc2bf47099e84346e`. Only `whisper_runner.py` and
new `tests/test_whisper_cache_consent.py` are product changes. Existing test
assertions and dependency pins stayed unchanged. The new test class and its
helpers retain the reviewed proposal's ASTs; only test setup/import selection
was adapted.

Final checkout SHA-256:

- `whisper_runner.py`:
  `6586d9f19fea0d20054d6e317b48b9914904e1126bbc7b788ba255633251996f`
- `tests/test_whisper_cache_consent.py`:
  `2595fee1b281d77856918ddfd1fb8ef17e432313b6e1ea1e73c44db3d63f9ea3`

The worker test file's raw hash is
`5a8f90dae1f4d711b8f3beab888afb15f8cbfd8611c632fae897288b5455c448`.
Its LF bytes and the checkout's CRLF bytes normalize identically; the raw copies
and both hashes are retained. The runner bytes match across roots.

The checks establish minimum cache structure, not a complete trusted artifact
manifest or atomic protection against filesystem replacement. The separate
faster-whisper tokenizer-constructor proposal, unrestricted default PyAnnote VAD
loader and model-stack qualification remain open. This change neither approves
that derivative nor adds speaker attribution or model execution claims.

The [proof bundle](E:/AI/projects/uoink/checkouts/Yoink-library/docs/library/proof/asset-guard-a-2026-09-13/SHA256.json)
preserves original seals, the explicit count correction, raw runs, integration
receipts, instrument/source inputs and matching case membership. The initial
integration receipt's `checkout_tests_run=false` describes its pre-test creation
time; the later agc01 receipts provide checkout qualification. No historical
receipt has been rewritten.
