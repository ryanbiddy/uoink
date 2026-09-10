# Integrator repair supplement, 2026-09-09

The original Gemini credential patch independently passes 117 cases with one
existing expected failure in credential-w1. Preserve that diff and observation.
Before integration, expand its profile digest from 16 to 32 hex characters and
remove the alternate unresolved-path fallback: a resolution error must not select
a different credential identity. Keep settings and credentials on the same active
validated binding, including the supported bound_isolation context. Existing
acceptance files stay unchanged. Run the original companion union in the worker
and checkout after this specific change, using fresh credential-w2/c2 labels.
All keyring calls in new regressions use the recording fake; no real key is read.

The worker report omits an intermediate observation: isolated-cred-companions-01
had 103 passed, four failed and one expected failure. All four failures are mirror
exports finding no output file. Preserve it alongside the later observations;
the final 117-case union passes independently, but the omitted failures cannot
be replaced by that result. No claim of complete test-order independence follows.

Gemini receipt role C (269acc98) ended after 20 minutes with three modified files,
no report, no raw delivery patch and no completed verification record. Control
Room's completed status does not make this an accepted delivery. Archive its
partial diff. Review the installer argument and profile-path corrections against
the implemented contract, then complete the synthetic helper's missing podcast
API as an instrument repair. Its observations remain synthetic. A canned route
response must not bypass the scenario's state, ownership, or all-success oracle.
Verify the complete C22/P4 instrument suites under a fresh guarded label after
the concrete reviewed correction; preserve any failure and repair product or
instrument code, without weakening the existing behavior assertions.

No installer execution, live index, port 5179, real credentials, paid API, models
or new source-media fetch is authorized by these verification commands.
