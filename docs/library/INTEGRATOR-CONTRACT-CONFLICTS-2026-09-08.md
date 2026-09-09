# Acceptance fixture conflicts found during integration

Current authority: Ryan's 2026-09-09 ruling authorizes only the five corrections
recorded below. The earlier requests for permission remain as history. Behavior
assertions stay unchanged; any failure after the corrected full tree is a product
defect requiring a repair brief, with no further fixture edits.

2026-09-09 continuation: `RYAN-IO-FIXTURE-PROPOSAL-REVIEW-2026-09-09.md`
contains an exact additional proposal for the eight parent-interception cases.
It is **not authorized, applied or executed**. The three-file patch preserves
150 assertions and changes only the interception target to the real isolated
writer dispatch methods. The original failed observations and test bytes remain.

Reviewer: Astra, 2026-09-08. Checkout: `dad34eb`. This is a source-inspection
finding, not a passing runtime receipt. Preserve the existing acceptance files.
The implementation work continues; these conflicts grant no waiver for unsafe
publication, cancellation, or test-specific production behavior.

## Phase 4: D13's two observation cases

In `tests/library_work_astra/test_phase4_aw3_acceptance.py:245`, both cases
install the same `blocked_replace` wrapper. It signals entry, waits until the
caller has returned a timeout, performs the actual replacement, and appends
the resulting source bytes to `published`. Only then does the `user_edit`
case write its personal bytes. The visibility case requires `published` to
remain empty; the user-edit case requires those later personal bytes to exist.

A publisher that prevents the post-timeout replacement also prevents this
wrapper from creating the personal bytes. An implementation cannot distinguish
these cases before that replacement through its public inputs. Inspecting the
fixture's closure, branch names, or test identity is not an acceptable repair.
The AV-5m2 draft does inspect the `observe == "user_edit"` closure; that code
will not be integrated. Asynchronous Python exceptions also do not establish
cancellation of a blocked operating-system replacement.

The product obligations remain: prevent abandoned work from mutating a
destination after timeout, retain destination exclusion until termination,
and preserve independent user edits. A revised fixture should arrange the
user edit independently of the forbidden replacement and exercise the actual
cancellable I/O boundary. Ryan must authorize that acceptance-fixture revision
or give another explicit ruling. Neither existing case is relabelled passed.

## Phase 6: required build-time ticket versus legacy helper calls

BD-01 and the BC-3a2 brief require both raw and Index publication entry points
to reject absent build-time ownership. However,
`tests/test_phase6_evaluation.py:1228` calls the raw publisher without a ticket
for successful publication/recovery scenarios. The BD reproduction itself uses
that helper to publish its newer setup snapshot. Several successful Index
replacement/retry calls in `tests/test_phase6_bc2.py` also omit tickets.

An unconditional ticket requirement therefore refuses some fixture setup
before the behavior under review can run. Allowing ticketless empty snapshots
is unsafe: an old empty build can erase a newer publication just as an old
nonempty build can replace it. An exception described as support for the
frozen evaluation helper is not a production contract.

Keep the boundary fail-closed and carry tickets from build start in production
callers. Ryan must authorize updating legacy acceptance setup to acquire and
carry the ticket before building, while preserving every behavioral assertion,
or make another explicit contract ruling. Worker edits to these acceptance
files are not integrated under the current instruction. Runtime counts must
identify any fixture-setup refusals separately from implementation failures;
neither becomes a pass by this inspection.

## Integration disposition

These are additional Ryan decisions under the instruction never to edit
acceptance tests. They do not move the unfinished implementation work into
Ryan's queue. Finish and independently verify the general repairs, retain all
failed observations, and review the resulting safety behavior before proposing
any candidate as blocked only on the fixture rulings and other owner gates.
# Additional fixture conflict: Phase 5 final-wire deadline probe

AZ-5d (Grok `e739a5ec`) is rejected despite 393 passes and four measurement
failures. Its adapter traverses a callback closure to bypass incompatible test
wrappers. Production must call its reader normally.

`test_phase5_acceptance3.py:391` installs a unary `read(args)` wrapper. The
shared `stdio_result` at `test_phase5_acceptance.py:427-431` then invokes that
wrapper with `clock=NOW`. Python raises TypeError before the final-wire probe
runs. Ryan must authorize compatible fixture setup, preserving the deadline
assertion, or provide a ruling. Existing tests remain unchanged. AZ-5d2 removes
the production workaround and adds an independent actual-handler test; it must
report the frozen setup failure separately.

## Phase 4: D15 intercepts the removed direct binding write

AV-5m4a2 removes `Path.write_text` from binding persistence as required by
AW-4. `test_d15_failed_destination_binding_persistence_does_not_allow_readoption`
patches that removed method on the binding pathname. Its injected failure is
never reached, so the assertion that no binding exists fails. The binding is
now written through `_atomic_local`; the independent initial-failure and
witness-failure tests cover that actual boundary and pass. Preserve this
ninth frozen setup failure. Ryan must authorize moving its failure injection
to the real persistence boundary without weakening its authority assertions,
or give another ruling. Do not restore the direct write to satisfy the test.

## Ryan's authorized fixture corrections, 2026-09-09

Base: `ee1293f20e95e330516467f0ce4d093142391031`, on
`cc/living-library-candidate`. The [complete six-file diff](patches/ryan-fixture-corrections-2026-09-09.patch)
is 23,425 bytes, SHA-256
`4e6689d0bf434bea8a83694c7c4c1ea2b2dd5a60074ab852032fd8688f552718`.
It is the authoritative diff for every change described here.

| Authorized change | Exact diff and reason |
|---|---|
| AW-11 teardown | In `test_phase4_aw11_foreign_helper_acceptance.py`, add `env.mirror._stop_vault_io(session)` before the existing death assertion; remove direct assignment of `_vault_io = None`. Production stop/forget clears the originating binding after death. The original termination assertion and foreign-thread assertions remain. |
| D13 user-edit ordering | In `test_phase4_aw3_acceptance.py`, move the conditional personal-file write out of the blocked replace callback and after the timeout assertion, before releasing the callback. Create its parent if needed. The user edit no longer depends on the forbidden publication occurring. Visibility, timeout and personal-byte assertions are unchanged. |
| D15 atomic persistence | In the same file, intercept the instance's `_atomic_local` instead of `Path.write_text`, at the identical binding path with the identical injected PermissionError. Keep the failed-initialization branch and all subsequent ownership assertions. |
| Phase 5 unary clock probe | In `test_phase5_acceptance3.py`, change the local wrapper to `read(args, *, clock=NOW)` and forward that clock to the real reader. The shared caller's frozen clock now reaches the probe. The simulated three-second cost and final deadline assertion are unchanged. |
| Phase 6 build-time tickets | In `test_phase6_evaluation.py`, add an explicit optional publication connection to the synthetic builder. It mints a ticket before copying inputs or constructing cues/artifacts, and stores that ticket on the fixture. `_publish` only forwards it; it never mints one. Correct successful legacy callers there, in `test_phase6_bc2.py` and `test_phase6_bd_acceptance.py`. Initial Index setup gets its ticket before fixture construction; each crash scenario constructs its replacement under its own ticket and retries reuse that exact ticket. The malformed-sidecar probe gets its ticket before the mutation is built. Intentionally omitted/foreign/malformed ticket cases retain their inputs and assertions. |

Scope review: 690 assertion syntax trees across the six files are identical to
the base, in the same traversal order. No expected values, thresholds, parameter
cases, skips or xfails changed. No product source changed. The existing parent-
process syscall interceptors are outside this authorization and remain unchanged.
Some old refusal-code expectations may still fail; do not mint a fresh ticket
for stale input or change an assertion to avoid that result.

See the [one-page review verdict](FIXTURE-CORRECTIONS-REVIEW-2026-09-09.md).
The corrected full tree ran on `4a3531642692736d4aaa4098077ab8fde464aeb4`,
with only S21 excluded: **2,174 passed, 20 failed, three skipped, one xfailed**,
183 warnings, 607.27 seconds. Every remaining failure is assigned in
[the product repair brief](CORRECTED-TREE-PRODUCT-REPAIR-BRIEF-2026-09-09.md).
The [sealed complete result](proof/ryan-corrected-01-2026-09-09/SHA256.json)
retains the command, log, XML, comparison and assertion audit. No further
fixture correction or product source edit followed that run.
