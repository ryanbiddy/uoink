# Astra stable-handle continuation

Work started from the independently verified 39-case stage. Its source SHA256
is `1f8088426c766ab3c93e81df41e6a9b25edec4cee94e40f3a3b4c639660bbc16`.
Original source and all four synthetic files are under
`_scratch/astra-authority-repair03/baseline`. No result is claimed for the new
repair until its guarded run completes.

The change retains the original parent handle, opens and holds each candidate
child handle before the final Toolhelp relationship check, and compares full
native creation times for child ordering. Millisecond lease fields keep their
existing format. Verified child handles stay retained for later mutation.
Borrowed Popen handles retain the owner object until their last user finishes.

Pending discovery retains destination exclusion. Cancellation records intent
and returns without waiting for native discovery; the last discovery completes
deferred cleanup. No cancellation state lock spans native calls. Each handle
release belongs to a successful acquisition.

All 35 worker and four Astra behavior assertions remain frozen. Any additional
inert native setup will have its before bytes, diff and reason retained. Only
synthetic probes are authorized here. No real process suite, writer gate,
installed state, live index, port 5179, network, provider, model, website, push,
or commit is part of this assignment.

## Results and source binding

Worktree HEAD remains `4b8dc95912ae74fcdcc0dccf5f9d862d08207fb2`. Source is
uncommitted and has not been integrated. Each run used the existing native
guarded verifier, `--runxfail`, offline flags, the forbidden-live-path guard,
and scrubbed provider keys/tokens/endpoint overrides. No real process suite ran.

| Fresh run label | Result | Source SHA256 |
|---|---|---|
| `astra-authority-repair03-01` | 44 passed, 0 failed, 0 skipped; 0.59 s; exit 0 | `738217f0ca20a34bf3e917125aaf5e99db5ab4a561fc8183089eec15ce1ecf82` |
| `astra-authority-repair03-02` | 46 passed, 0 failed, 0 skipped; 0.61 s; exit 0 | `8a6b50a2b92e45713f573323650d64d379dd876db17b4c036568dbcba4d62665` |
| `astra-authority-repair03-03` | 49 passed, 0 failed, 0 skipped; 0.61 s; exit 0 | `67432bf13905b8c28c2048ce51bbebd74490d463f8b1a4e08fdd3ce4e53a0a23` |

The final union is the unchanged 39 prior cases plus ten new stable-handle
cases. Selectors are `test_library_mirror_process_authority.py`,
`test_mirror_process_identity_boundaries.py`,
`test_mirror_process_handle_lifetime.py`, `test_mirror_authority_review02.py`,
and `test_mirror_stable_handle_discovery.py`, all under `tests/`.

Raw `results.json`, `tests.log`, and `tests.xml` remain under each corresponding
`_scratch/<run-label>/`. Each prior source/test stage, pre-run reason and exact
diff remains in `_scratch/astra-authority-repair03/`. The report does not replace
the raw receipts; the integrator will seal them with the final reviewed patch.

Attempt02 followed source-review repairs to writer fallback validation and
candidate-handle transfer cleanup. Attempt03 followed the integrator's review:
canonical writer publication now checks cancellation under the state lock,
and dropping a borrowed owner's final reference occurs outside the handle
guard. No failed test was hidden or relabeled; all three synthetic runs passed.

## Assertions, setup, and retained owner repair

The four prior synthetic files gained one fixture import each. Their complete
ASTs are otherwise identical to the preserved 39-pass baseline. New fixture
`tests/_mirror_stable_native_fixture.py` supplies inert original/child handles
using those files' existing fake process observations. New behavior assertions
use a separate fake kernel that refuses PID reuse while an original handle is
retained and fails on unconfigured native calls.

`_scratch/astra-authority-repair03/review-input-audit.json` records the static
comparison and hashes. All 18 checks pass: the four prior modules' ASTs,
accepted exclusion-owner class, accepted prepare method, and test bodies from
the 44- and 46-case stages remain unchanged where required.

The first static-audit interpreter launch was refused before opening its
script because that separate command omitted IG_FORBIDDEN_LIVE. Its rejection
and repair reason are retained. Static audit attempt02 used the correct guard
environment and exited 0. Neither static launch is counted as a test run.

## Review boundary

The source is frozen for the integrator's independent review. Pending discovery
prevents cleanup from dropping exclusion; the last discovery owns deferred
termination. Already proved children retain their native handles after parent
exit. A child operation that lacks a retained handle is refused, and unresolved
owned identities keep their existing conservative liveness behavior.

No claim is made that these synthetic repairs explain tree08's fifty failures.
The sequential real Phase 4 suites, both-root integration checks, complete
tree, packaging and release decision remain the integrator's work.
