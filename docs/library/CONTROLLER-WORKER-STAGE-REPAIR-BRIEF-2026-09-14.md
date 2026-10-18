# Controller worker-stage repair — 2026-09-14

Repair the post-consumption controller check before attempting the child
connection again. Gemini run `05a3bf93` failed source review: its coordinator
does not match the called APIs or durable startup sequence, and its proposed
tests substitute fabricated ownership objects. Preserve that complete delivery
and all 17 unexecuted tests. This is a new, smaller source unit, not a rerun.

Work only under `_scratch/controller-worker-stage-repair01`. Derive the accepted
`_scratch/real-startup-authority-repair01/asr_loading_adapter.py` (28,922 bytes,
SHA256 `6482b782c545adbcd524a68ae85ba2abb3f081683379a9d53ada66d03a5ddb51`).
Preserve every byte of that file as the prefix; append the new stage checks.
Do not derive from failed `65a0715e`, modify the accepted pre-worker validator,
or copy the failed coordinator/fixture into a runnable input map.

Bind the actual current lifecycle inputs before writing. The qualified durable
lifecycle is `_scratch/real-startup-authority-repair01/inputs/durable_lifecycle.py`
(32,833 bytes, SHA256
`3c8963eaa02bbc1d810ee2632d0363303bfe05ec6ceeef73771ca8005a00ece3`).
Use the other exact sources in the startup81 proposal's `SOURCE-INPUTS.json`,
especially `snapshot_lifecycle.py`, `snapshot_reservations.py`,
`test_reservations.py` and the isolated startup fixture. The native delegate
contract is the saved native02 `win32_worker_connection.py` and
`generated_worker_flow.py`; these are reference text only in this unit.

Implement an explicit stage API with mandatory startup, permit, session, worker
and stage arguments. Its common checks retain the exact issued startup and
consuming session, current release/profile/admission/selection, active lease,
reservation, protection, record and manager configuration. Keep the established
manager-then-reservation lock order. Do not call a callback or perform I/O while
checking those records.

Cover only two post-resume stages reached by the existing durable factory:

- During fixed `finish_start`: record is `NATIVE_RESERVED`, reservation is
  `WORKER_BOUND`, resume was attempted, `token.worker` and
  `manager._kernel._starts[permit.identity]` retain the same non-None worker,
  and `session._worker` is still None.
- After factory publication: the same reservation/start binding remains,
  record is `NATIVE_RUNNING`, and `session._worker` is that exact worker.

Refuse every other state pair, missing/foreign/copied authority, pending or
revoked reservation, changed worker binding, changed configuration and reuse
after close. A resume-attempt flag alone is not an observation that Windows
resumed. These checks establish local lifecycle bindings; native assigned-job,
read-set, pipe/source authentication and effect-boundary checks remain in the
later fixed connection unit. Do not advertise them as established here.

Create proposed controls using the existing separately loaded startup fixture
pair and actual release parsing, lease, session, reservation and factory paths.
Generate only inert metadata and use the existing in-memory lower services.
Obtain the worker through the delegate's actual `create_suspended` return,
then let the unchanged durable implementation retain/bind/resume/publish it.
Use fixed lower-service hooks to observe `finish_start`; do not assign
`record.worker`, insert a pretend startup into product registries, replace
validators or directly seed product ownership to make a positive case pass.
Exercise both allowed stages, refused transitions, identity substitutions,
configuration changes, revocation and preserved first error/retained custody.
Keep the existing 81 cases and generated39 assertions unchanged.

Deliver source and fixture/test files, immutable before copies, complete diffs,
an exact source map, declared case IDs and a short honest report. Any draft
correction needs its before copy and reason. Freeze new controls before the
first execution. No Python startup/import/compile/test, native calls, model
construction, model/support binary access, D1/D2 reread, physical journal access,
fetch, live index or port5179 is admitted by this brief. All real authority
globals and entry refusals stay closed. Root and an independent peer must
review the complete source and guarded qualification instrument before any
separate fake-service execution admission.
