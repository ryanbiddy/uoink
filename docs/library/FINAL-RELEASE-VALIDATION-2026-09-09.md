# Candidate verification, 2026-09-09

Candidate `80a4fa8e6182901c3e0f5a7ddeb806839a180050`: **2,451 passed, one failed,
three skipped and one xfailed**, 183 warnings, 1,427.78 seconds. The complete
result remains **FAIL** because the historical AT6 process-exit record is
missing. Its original audit assertion is unchanged. No current observation can
recreate that old exit or change the failed archive into a pass.

[Complete raw proof](proof/ryan-security-final-tree-01-2026-09-09/SHA256.json)
contains commands, environment, every case, original XML/log and comparison with
12ce8a5. All twelve former fixture/setup failures now pass. No case is missing,
no new failure appears, and ten independent credential regressions were added.
The approved corrections and exact assertion audits have separate reviews.
Only tests/library_work_astra/test_phase3_s21.py is excluded.

The skips are POSIX build execution on Windows, unavailable symlink privilege,
and ffmpeg absent from this native test environment's PATH. SEC-06 remains an
existing expected failure: the search query parser strips non-ASCII characters.
These limits are not counted as passes. The installer supplies its own ffmpeg;
its actual bundled runtime is a separate observation.

A further instrument defect was found by source inspection before Setup: the
C22 verifier treats one dontcopy setup script as an installed application file.
Gemini's bounded correction has 35 worker passes; Astra independently repeated
35 passes in 6.23 seconds. It remains outside this frozen tree until integration.
The repair brief requires a new committed complete tree afterward. No existing
test or installer behavior changes are authorized by that correction.

The previous 12ce8a5 observation stays **2,429 passed / 13 failed / three skipped /
one xfailed** in [its original proof](proof/ryan-final-kit-tree-01-2026-09-09/SHA256.json).
The old package and bundled C22/P4 observations are also historical; neither is
an installed receipt for the repaired source. Actual new-package installation,
reinstallation and installed/browser/client review remain next. No main merge,
new fetch, speaker claim, paid API or Phase 5 Part B is included.
