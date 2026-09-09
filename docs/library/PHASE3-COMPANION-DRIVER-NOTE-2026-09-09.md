# Phase 3 companion driver limitation after mirror isolation

The planned broader Phase 3 check on `239dbbd` ran the unchanged historical
`run_phase3_companions.py` driver. Its Phase 4 group failed 17 tests and passed
15. The driver's audit output records repeated rejected `subprocess.Popen`
events; the current mirror requires its isolated child writer. These outcomes
remain failed. They are separate from the corrected full tree's 20 failures.

Do not modify that existing driver or any test fixture. For the next planned
mirror verification after a documented product repair, run the same complete
`tests/library_work_astra/test_phase4_aw_acceptance.py` selector through the
current isolated integrator runner used by the corrected full tree. That
runner permits ordinary fixture subprocesses and rejects real model processes,
external networking, the live index and port 5179. Preserve both commands,
guards and results. This changes the external verification invocation, not
an assertion or fixture, and does not convert the old driver result into a pass.

The AS-7/8/9 focused check passed 22 and failed the unrecorded AT6 exit check;
the strict Phase 3 check passed 181 and failed that same check. Historical
companion groups overlap these suites and must not be summed as unique tests.
The full candidate still requires its own final run after product integration.

After the documented lifecycle repair integrated at `1063843`, the complete
unchanged AW acceptance file ran within the guarded Phase 4 checkout union:
**31 passed, one failed**. The remaining failure is the purge temporary-file
interception case. The complete union was 163 passed / eight failed; its XML
and guard are sealed under `proof/ryan-phase4-integration-2026-09-09/`.
This supplies the planned current-driver observation without repeating the
suite or changing the historical 15-pass / 17-fail companion result.
